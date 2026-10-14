"""Read-only experimental inventory tests; no containment or termination claims."""

import ctypes
from dataclasses import FrozenInstanceError
import errno
import os
import platform
import struct
import unittest
from unittest.mock import patch

from native.uid_domain import (
    BSD_INFO_BYTES,
    InventoryError,
    _BSDInfo,
    _library,
    _pid_list,
    _process,
    credential_groups,
    decode_group_buffer,
    decode_bsd_info,
    decode_pid_buffer,
    inventory_uid,
)


class UIDInventoryTests(unittest.TestCase):
    def raw(self):
        info = _BSDInfo()
        info.pid = 123
        info.uid = 501
        info.ruid = 502
        info.svuid = 503
        info.ppid = 1
        info.pgid = 123
        info.start_seconds = 1_700_000_000
        info.start_microseconds = 123456
        return info

    def test_bsd_parser_preserves_effective_real_saved_and_birth_identity(self):
        self.assertEqual(ctypes.sizeof(_BSDInfo), BSD_INFO_BYTES)
        record = decode_bsd_info(bytes(self.raw()), expected_pid=123, expected_uid=501)
        self.assertEqual(
            (record.uid, record.euid, record.ruid, record.saved_uid),
            (501, 501, 502, 503),
        )
        self.assertEqual(record.start_identity, (123, 501, 1_700_000_000, 123456))
        with self.assertRaises(FrozenInstanceError):
            record.pid = 999

    def test_bsd_parser_rejects_partial_wrong_identity_and_invalid_birth(self):
        raw = bytes(self.raw())
        for content, pid, uid in (
            (raw[:-1], 123, 501),
            (raw + b"x", 123, 501),
            (raw, 124, 501),
            (raw, 123, 502),
        ):
            with self.assertRaises(InventoryError):
                decode_bsd_info(content, expected_pid=pid, expected_uid=uid)
        info = self.raw()
        info.start_microseconds = 1_000_000
        with self.assertRaises(InventoryError):
            decode_bsd_info(bytes(info), expected_pid=123, expected_uid=501)

    def test_pid_parser_validates_capacity_alignment_and_duplicate_identity(self):
        valid = struct.pack("=iiii", 20, 10, 0, 0)
        self.assertEqual(decode_pid_buffer(valid, 8, 16), (10, 20))
        self.assertEqual(decode_pid_buffer(valid, 0, 16), ())
        for raw, returned, capacity in (
            (valid, 16, 16),
            (valid, 20, 16),
            (valid, 7, 16),
            (valid, -4, 16),
            (valid, 8, 15),
            (valid[:8], 8, 16),
            (struct.pack("=iiii", 10, 10, 0, 0), 8, 16),
            (struct.pack("=iiii", 0, 10, 0, 0), 8, 16),
        ):
            with self.assertRaises(InventoryError):
                decode_pid_buffer(raw, returned, capacity)

    def test_unsupported_platform_and_invalid_uid_fail_closed(self):
        with patch("native.uid_domain.platform.system", return_value="Linux"):
            with self.assertRaises(InventoryError):
                inventory_uid(os.getuid())
        for uid in (-1, True, 0xFFFFFFFF, "501"):
            with self.assertRaises(InventoryError):
                inventory_uid(uid)

    def test_changing_membership_never_returns_partial_success(self):
        with (
            patch("native.uid_domain._library", return_value=object()),
            patch("native.uid_domain._pid_list", side_effect=[(123,), ()]),
            patch(
                "native.uid_domain._process",
                return_value=decode_bsd_info(
                    bytes(self.raw()), expected_pid=123, expected_uid=501
                ),
            ),
        ):
            with self.assertRaises(InventoryError):
                inventory_uid(501, max_passes=1)

    def test_list_capacity_saturation_grows_and_syscall_errors_fail_closed(self):
        class GrowingLibrary:
            capacities = []

            def proc_listpids(self, kind, uid, buffer, capacity):
                self_kind = kind
                if self_kind != 4 or uid != 501:
                    raise AssertionError("wrong native selector")
                if buffer is None:
                    return 4
                self.capacities.append(capacity)
                if len(self.capacities) == 1:
                    return capacity
                ctypes.memmove(buffer, struct.pack("=i", 123), 4)
                return 4

        library = GrowingLibrary()
        self.assertEqual(_pid_list(library, 501, 128), (123,))
        self.assertEqual(library.capacities, [256, 512])

        class DeniedLibrary:
            def proc_listpids(self, *args):
                ctypes.set_errno(errno.EPERM)
                return -1

        with self.assertRaises(InventoryError):
            _pid_list(DeniedLibrary(), 501, 128)

    def test_metadata_permission_failure_cannot_be_dropped(self):
        class DeniedLibrary:
            def proc_pidinfo(self, *args):
                ctypes.set_errno(errno.EPERM)
                return 0

        with self.assertRaisesRegex(InventoryError, "metadata unavailable"):
            _process(DeniedLibrary(), 123, 501)

    @unittest.skipUnless(
        platform.system() == "Darwin", "read-only macOS libproc inventory"
    )
    def test_actual_current_process_bsd_identity_matches_credentials(self):
        own = _process(_library(), os.getpid(), os.geteuid())
        self.assertEqual(own.pid, os.getpid())
        self.assertEqual(own.euid, os.geteuid())
        self.assertEqual(own.ruid, os.getuid())
        self.assertGreater(own.start_seconds, 0)

    @unittest.skipUnless(
        platform.system() == "Darwin", "read-only macOS libproc inventory"
    )
    def test_actual_unused_uid_has_stable_empty_membership(self):
        import pwd

        unused = 4_000_000_000
        with self.assertRaises(KeyError):
            pwd.getpwuid(unused)
        self.assertEqual(inventory_uid(unused), [])

    def test_group_parser_retains_root_authority_and_rejects_invalid_capacity(self):
        raw = struct.pack("=III", 0, 20, 501)
        self.assertEqual(decode_group_buffer(raw, 3, 3), [0, 20, 501])
        self.assertEqual(decode_group_buffer(raw, 0, 3), [])
        for content, returned, capacity in (
            (raw, 4, 3),
            (raw, -1, 3),
            (raw, 3, 129),
            (raw[:-1], 3, 3),
            (raw, True, 3),
            (struct.pack("=II", 20, 20), 2, 2),
            (struct.pack("=I", 0xFFFFFFFF), 1, 1),
        ):
            with self.assertRaises(InventoryError):
                decode_group_buffer(content, returned, capacity)

    def test_group_syscall_errors_excessive_and_unstable_counts_fail_closed(self):
        class FakeLibrary:
            def __init__(self, replies):
                self.replies = iter(replies)

            def getgroups(self, capacity, buffer):
                result, error = next(self.replies)
                ctypes.set_errno(error)
                if buffer is not None:
                    for index in range(min(capacity, max(0, result))):
                        buffer[index] = 20 + index
                return result

        for replies in (
            [(-1, errno.EINVAL)],
            [(129, 0)],
            [(1, 0), (-1, errno.EPERM)],
            [(1, 0), (0, 0)],
            [(1, 0), (1, 0), (2, 0)],
            [(0, 0), (0, 0), (-1, errno.EINVAL)],
        ):
            with (
                self.subTest(replies=replies),
                patch(
                    "native.uid_domain._groups_library",
                    return_value=FakeLibrary(replies),
                ),
            ):
                with self.assertRaises(InventoryError):
                    credential_groups()
        with patch(
            "native.uid_domain._groups_library",
            return_value=FakeLibrary([(1, 0), (1, 0), (1, 0)]),
        ):
            self.assertEqual(credential_groups(), [20])
        with patch("native.uid_domain.platform.system", return_value="Linux"):
            with self.assertRaises(InventoryError):
                credential_groups()

    @unittest.skipUnless(
        platform.system() == "Darwin", "read-only kernel POSIX group credentials"
    )
    def test_actual_current_effective_gid_is_in_kernel_group_inventory(self):
        groups = credential_groups()
        self.assertIn(os.getegid(), groups)
        self.assertTrue(all(type(group) is int for group in groups))
