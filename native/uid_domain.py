"""Experimental read-only Darwin UID inventory; never proves containment.

PROC_UID_ONLY selects effective UID. Real/saved credentials are returned rather
than assumed equal. Two stable scans establish observed membership, not an atomic
kernel snapshot, and no process is killed or otherwise modified here.
"""

from __future__ import annotations

import ctypes
from dataclasses import asdict, dataclass
import errno
import platform
import struct

PROC_UID_ONLY = 4
PROC_PIDTBSDINFO = 3
BSD_INFO_BYTES = 136
PID_BYTES = 4
MAX_PIDS = 65_536
MAX_GROUPS = 128


class InventoryError(RuntimeError):
    """Inventory is unavailable, incomplete, unstable, or unsupported."""


class _Churn(InventoryError):
    pass


class _BSDInfo(ctypes.Structure):
    # Darwin SDK sys/proc_info.h struct proc_bsdinfo (64-bit ABI).
    _fields_ = [
        (field, ctypes.c_uint32)
        for field in (
            "flags",
            "status",
            "xstatus",
            "pid",
            "ppid",
            "uid",
            "gid",
            "ruid",
            "rgid",
            "svuid",
            "svgid",
            "reserved",
        )
    ] + [
        ("comm", ctypes.c_char * 16),
        ("name", ctypes.c_char * 32),
        ("nfiles", ctypes.c_uint32),
        ("pgid", ctypes.c_uint32),
        ("jobc", ctypes.c_uint32),
        ("tdev", ctypes.c_uint32),
        ("tpgid", ctypes.c_uint32),
        ("nice", ctypes.c_int32),
        ("start_seconds", ctypes.c_uint64),
        ("start_microseconds", ctypes.c_uint64),
    ]


@dataclass(frozen=True)
class ProcessRecord:
    pid: int
    uid: int
    euid: int
    ruid: int
    saved_uid: int
    ppid: int
    pgid: int
    start_seconds: int
    start_microseconds: int

    @property
    def start_identity(self):
        return self.pid, self.euid, self.start_seconds, self.start_microseconds

    def to_dict(self):
        return asdict(self)


def _uid(uid):
    if type(uid) is not int or not 0 <= uid < 0xFFFFFFFF:
        raise InventoryError(
            "UID must be a concrete uint32 value, excluding sentinel -1"
        )


def decode_pid_buffer(
    raw: bytes, returned_bytes: int, capacity_bytes: int
) -> tuple[int, ...]:
    """Validate a proc_listpids result without silently clipping or dropping PIDs."""
    if (
        not isinstance(raw, bytes)
        or type(returned_bytes) is not int
        or type(capacity_bytes) is not int
        or capacity_bytes <= 0
        or capacity_bytes > MAX_PIDS * PID_BYTES
        or capacity_bytes % PID_BYTES
        or len(raw) != capacity_bytes
        or returned_bytes < 0
        or returned_bytes % PID_BYTES
        or returned_bytes >= capacity_bytes
    ):
        raise InventoryError("PID inventory buffer is invalid or potentially truncated")
    pids = tuple(value[0] for value in struct.iter_unpack("=i", raw[:returned_bytes]))
    if any(pid <= 0 for pid in pids) or len(pids) != len(set(pids)):
        raise InventoryError("PID inventory contains invalid or duplicate identity")
    return tuple(sorted(pids))


def decode_bsd_info(
    raw: bytes, *, expected_pid: int, expected_uid: int
) -> ProcessRecord:
    _uid(expected_uid)
    if type(expected_pid) is not int or not 0 < expected_pid <= 0x7FFFFFFF:
        raise InventoryError("concrete positive PID required")
    if (
        ctypes.sizeof(_BSDInfo) != BSD_INFO_BYTES
        or not isinstance(raw, bytes)
        or len(raw) != BSD_INFO_BYTES
    ):
        raise InventoryError("unsupported or partial Darwin BSD process-info layout")
    info = _BSDInfo.from_buffer_copy(raw)
    if info.pid != expected_pid or info.uid != expected_uid:
        raise _Churn("PID or effective UID changed during inventory")
    if info.start_seconds <= 0 or info.start_microseconds >= 1_000_000:
        raise InventoryError("invalid process birth identity")
    return ProcessRecord(
        pid=info.pid,
        uid=info.uid,
        euid=info.uid,
        ruid=info.ruid,
        saved_uid=info.svuid,
        ppid=info.ppid,
        pgid=info.pgid,
        start_seconds=info.start_seconds,
        start_microseconds=info.start_microseconds,
    )


def _library():
    if platform.system() != "Darwin":
        raise InventoryError("UID inventory experiment supports macOS only")
    if (
        ctypes.sizeof(ctypes.c_int) != PID_BYTES
        or ctypes.sizeof(_BSDInfo) != BSD_INFO_BYTES
    ):
        raise InventoryError("unsupported libproc ABI")
    try:
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        library.proc_listpids.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        library.proc_listpids.restype = ctypes.c_int
        library.proc_pidinfo.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint64,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        library.proc_pidinfo.restype = ctypes.c_int
        return library
    except (OSError, AttributeError) as error:
        raise InventoryError("native libproc inventory is unavailable") from error


def _pid_list(library, uid, max_pids):
    ctypes.set_errno(0)
    estimated = library.proc_listpids(PROC_UID_ONLY, uid, None, 0)
    error = ctypes.get_errno()
    if error or estimated < 0 or estimated % PID_BYTES:
        raise InventoryError(f"PID sizing failed (errno={error}, bytes={estimated})")
    maximum = max_pids * PID_BYTES
    capacity = max(64 * PID_BYTES, estimated + 32 * PID_BYTES)
    if capacity > maximum:
        raise InventoryError("PID inventory exceeds bounded capacity")
    for _ in range(4):
        buffer = ctypes.create_string_buffer(capacity)
        ctypes.set_errno(0)
        returned = library.proc_listpids(PROC_UID_ONLY, uid, buffer, capacity)
        error = ctypes.get_errno()
        if error or returned < 0 or returned > capacity or returned % PID_BYTES:
            raise InventoryError(
                f"PID enumeration failed (errno={error}, bytes={returned})"
            )
        if returned == capacity:
            capacity *= 2
            if capacity > maximum:
                raise InventoryError(
                    "PID inventory may be truncated at bounded capacity"
                )
            continue
        return decode_pid_buffer(buffer.raw, returned, capacity)
    raise InventoryError("PID inventory capacity did not stabilize")


def _process(library, pid, uid):
    buffer = ctypes.create_string_buffer(BSD_INFO_BYTES)
    ctypes.set_errno(0)
    returned = library.proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, buffer, BSD_INFO_BYTES)
    error = ctypes.get_errno()
    if error or returned != BSD_INFO_BYTES:
        if returned == 0 and error in {0, errno.ESRCH, errno.ENOENT}:
            raise _Churn(
                f"PID {pid} birth metadata unavailable (errno={error}); complete membership cannot be verified"
            )
        raise InventoryError(
            f"process metadata unavailable (pid={pid}, errno={error}, bytes={returned})"
        )
    return decode_bsd_info(buffer.raw, expected_pid=pid, expected_uid=uid)


def inventory_uid(
    uid: int, *, max_passes: int = 3, max_pids: int = MAX_PIDS
) -> list[ProcessRecord]:
    """Return stable observed effective-UID membership, or fail without partial output.

    Records are immutable. This bounded read-only inventory is not atomic and
    does not authorize cancellation, UID changes, or process termination.
    """
    _uid(uid)
    if type(max_passes) is not int or not 1 <= max_passes <= 5:
        raise InventoryError("one to five bounded inventory passes required")
    if type(max_pids) is not int or not 64 <= max_pids <= MAX_PIDS:
        raise InventoryError("bounded PID capacity required")
    library = _library()
    last = None
    for _ in range(max_passes):
        try:
            first = _pid_list(library, uid, max_pids)
            records = [_process(library, pid, uid) for pid in first]
            second = _pid_list(library, uid, max_pids)
            if first != second:
                raise _Churn("effective-UID membership changed during inventory")
            verified = [_process(library, pid, uid) for pid in second]
            if records != verified:
                raise _Churn(
                    "PID birth or credential metadata changed during inventory"
                )
            return records
        except _Churn as error:
            last = error
    raise InventoryError(
        "UID membership did not stabilize within bounded passes: " + str(last)
    ) from last


def decode_group_buffer(
    raw: bytes, returned_groups: int, capacity_groups: int
) -> list[int]:
    """Validate a complete POSIX gid_t array, retaining GID 0 as authority."""
    if (
        not isinstance(raw, bytes)
        or type(returned_groups) is not int
        or type(capacity_groups) is not int
        or not 1 <= capacity_groups <= MAX_GROUPS
        or not 0 <= returned_groups <= capacity_groups
        or len(raw) != capacity_groups * 4
    ):
        raise InventoryError("invalid or incomplete POSIX group buffer")
    groups = [item[0] for item in struct.iter_unpack("=I", raw[: returned_groups * 4])]
    if 0xFFFFFFFF in groups or len(groups) != len(set(groups)):
        raise InventoryError("group inventory contains a sentinel or duplicate GID")
    return groups


def _groups_library():
    if platform.system() != "Darwin":
        raise InventoryError("POSIX credential group experiment supports macOS only")
    if ctypes.sizeof(ctypes.c_int) != 4 or ctypes.sizeof(ctypes.c_uint32) != 4:
        raise InventoryError("unsupported POSIX group ABI")
    try:
        library = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        # Python's DARWIN_EXTSN variant can consult getpwuid and fail for a
        # deliberately accountless UID. The standard symbol reads kernel groups.
        function = library.getgroups
        function.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint32)]
        function.restype = ctypes.c_int
        return library
    except (OSError, AttributeError) as error:
        raise InventoryError("standard libSystem getgroups is unavailable") from error


def credential_groups() -> list[int]:
    """Read current kernel group credentials without account lookup or mutation.

    This observation does not prove privilege dropping, and any count churn,
    syscall error, unsupported ABI or excessive membership fails closed.
    """
    library = _groups_library()
    ctypes.set_errno(0)
    count = library.getgroups(0, None)
    error = ctypes.get_errno()
    if error or not 0 <= count <= MAX_GROUPS:
        raise InventoryError(
            f"POSIX group sizing failed (errno={error}, count={count})"
        )
    capacity = max(1, count)
    buffer = (ctypes.c_uint32 * capacity)()
    ctypes.set_errno(0)
    returned = library.getgroups(capacity, buffer)
    error = ctypes.get_errno()
    if error or returned != count:
        raise InventoryError(
            f"POSIX group membership changed or read failed (errno={error}, count={returned})"
        )
    groups = decode_group_buffer(bytes(buffer), returned, capacity)
    ctypes.set_errno(0)
    verified = library.getgroups(0, None)
    error = ctypes.get_errno()
    if error or verified != count:
        raise InventoryError(
            f"POSIX group count did not stabilize (errno={error}, count={verified})"
        )
    return groups
