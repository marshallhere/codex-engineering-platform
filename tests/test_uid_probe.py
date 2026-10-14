"""The experimental authority guard must run before any privileged action."""

import os
from unittest import TestCase, mock

from native import uid_probe


class UIDProbeGuardTests(TestCase):
    def test_developer_machine_rejected_before_staging_access(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(uid_probe.Path, "stat") as probe,
        ):
            with self.assertRaisesRegex(RuntimeError, "disposable"):
                uid_probe.guard()
            probe.assert_not_called()

    def test_environment_markers_do_not_replace_platform_and_uid_checks(self):
        markers = {
            "GITHUB_ACTIONS": "true",
            "RUNNER_ENVIRONMENT": "github-hosted",
            "CEP_UID_EXPERIMENT": "disposable-v1",
        }
        with (
            mock.patch.dict(os.environ, markers, clear=True),
            mock.patch.object(uid_probe.sys, "platform", "darwin"),
            mock.patch.object(uid_probe.os, "getuid", return_value=501),
            mock.patch.object(uid_probe.os, "geteuid", return_value=501),
        ):
            with self.assertRaisesRegex(RuntimeError, "disposable"):
                uid_probe.guard()

    def test_drop_rejects_root_and_existing_system_identity(self):
        with mock.patch.object(uid_probe.resource, "setrlimit") as limits:
            for uid in (0, 501, 65534, -1):
                with self.subTest(uid=uid), self.assertRaises(RuntimeError):
                    uid_probe.drop(uid)
            limits.assert_not_called()

    def test_prerequisites_never_claim_production_qualification(self):
        self.assertIs(uid_probe.prerequisites()["production_qualified"], False)

    def test_darwin_primary_group_is_allowed_but_foreign_groups_are_rejected(self):
        # Test credential authorization without making any real UID/GID change.
        from contextlib import ExitStack
        from itertools import chain, repeat

        uid = 62001
        for groups, allowed in (
            ([uid], True),
            ([], False),
            ([uid, uid], False),
            ([uid, 0], False),
            ([20], False),
        ):
            with self.subTest(groups=groups), ExitStack() as stack:
                stack.enter_context(mock.patch.object(uid_probe.resource, "setrlimit"))
                stack.enter_context(
                    mock.patch.object(
                        uid_probe.os, "getuid", side_effect=chain([0], repeat(uid))
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        uid_probe.os, "geteuid", side_effect=chain([0], repeat(uid))
                    )
                )
                stack.enter_context(
                    mock.patch.object(uid_probe.os, "getgid", return_value=uid)
                )
                stack.enter_context(
                    mock.patch.object(uid_probe.os, "getegid", return_value=uid)
                )
                stack.enter_context(
                    mock.patch.object(
                        uid_probe, "credential_groups", return_value=groups
                    )
                )
                stack.enter_context(mock.patch.object(uid_probe.os, "setgroups"))
                stack.enter_context(
                    mock.patch.object(
                        uid_probe.os, "setuid", side_effect=[None, PermissionError()]
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        uid_probe.os, "seteuid", side_effect=PermissionError()
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        uid_probe.os, "setgid", side_effect=[None, PermissionError()]
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        uid_probe.os, "setegid", side_effect=PermissionError()
                    )
                )
                if allowed:
                    uid_probe.drop(uid)
                else:
                    with self.assertRaises(RuntimeError):
                        uid_probe.drop(uid)


class UIDProbeFinalizationTests(TestCase):
    """Parent-only fault injection: no real fork, signals, UID changes or waits."""

    def mocks(self, stack, *, worker_diagnostic=b"", inventories=None, wait=None):
        from itertools import chain, count, repeat

        stack.enter_context(
            mock.patch.object(
                uid_probe.os, "pipe", side_effect=[(11, 12), (13, 14), (15, 16)]
            )
        )
        stack.enter_context(
            mock.patch.object(uid_probe.os, "fork", side_effect=[111, 222])
        )
        close = stack.enter_context(mock.patch.object(uid_probe.os, "close"))
        stack.enter_context(mock.patch.object(uid_probe.os, "set_blocking"))
        reads = {11: b"R", 13: worker_diagnostic, 15: b""}
        read = stack.enter_context(
            mock.patch.object(
                uid_probe.os, "read", side_effect=lambda fd, size: reads[fd]
            )
        )
        stack.enter_context(
            mock.patch.object(
                uid_probe.select,
                "select",
                side_effect=lambda readers, *args: (readers, [], []),
            )
        )
        waiter = stack.enter_context(
            mock.patch.object(
                uid_probe.os,
                "waitpid",
                side_effect=wait or (lambda pid, flags: (pid, 0)),
            )
        )
        killer = stack.enter_context(mock.patch.object(uid_probe.os, "kill"))
        stack.enter_context(
            mock.patch.object(uid_probe.time, "monotonic", side_effect=count(0, 0.25))
        )
        stack.enter_context(mock.patch.object(uid_probe.time, "sleep"))
        stack.enter_context(
            mock.patch.object(
                uid_probe,
                "inventory_uid",
                side_effect=inventories or chain([[object()]], repeat([])),
            )
        )
        return close, read, waiter, killer

    def test_detached_parent_zero_exit_cannot_hide_descendant_diagnostic(self):
        from contextlib import ExitStack

        with ExitStack() as stack:
            close, read, waiter, killer = self.mocks(
                stack,
                worker_diagnostic=b"RuntimeError:descendant failed after readiness",
            )
            with self.assertRaisesRegex(
                RuntimeError, "descendant failed after readiness"
            ):
                uid_probe.run_case(62001, "detached")
            self.assertIn(mock.call(13, 1024), read.call_args_list)
            self.assertIn(mock.call(15, 1024), read.call_args_list)
            self.assertEqual(
                {call.args[0] for call in close.call_args_list},
                {11, 12, 13, 14, 15, 16},
            )
            killer.assert_not_called()

    def test_inventory_failures_still_reap_collect_diagnostics_and_close_every_fd(self):
        from contextlib import ExitStack
        from itertools import chain, repeat

        errors = chain(
            [[object()]], repeat(uid_probe.InventoryError("birth metadata unavailable"))
        )
        with ExitStack() as stack:
            close, read, waiter, killer = self.mocks(
                stack,
                worker_diagnostic=b"RuntimeError:late descendant failure",
                inventories=errors,
            )
            with self.assertRaisesRegex(RuntimeError, "survivors=unknown") as caught:
                uid_probe.run_case(62001, "detached")
            message = str(caught.exception)
            self.assertIn("late descendant failure", message)
            self.assertIn("worker_status=0", message)
            self.assertIn("cleaner_status=0", message)
            self.assertIn("inventory_errors=", message)
            self.assertIn("birth metadata unavailable", message)
            self.assertEqual(
                {call.args[0] for call in waiter.call_args_list}, {111, 222}
            )
            self.assertIn(mock.call(13, 1024), read.call_args_list)
            self.assertIn(mock.call(15, 1024), read.call_args_list)
            self.assertEqual(
                {call.args[0] for call in close.call_args_list},
                {11, 12, 13, 14, 15, 16},
            )
            killer.assert_not_called()

    def test_wait_failure_does_not_bypass_diagnostic_collection(self):
        from contextlib import ExitStack

        def wait(pid, flags):
            if pid == 111:
                raise ChildProcessError("unknown worker wait status")
            return pid, 0

        with ExitStack() as stack:
            close, read, waiter, killer = self.mocks(stack, wait=wait)
            with self.assertRaisesRegex(RuntimeError, "unknown worker wait status"):
                uid_probe.run_case(62001, "detached")
            self.assertIn(mock.call(13, 1024), read.call_args_list)
            self.assertIn(mock.call(15, 1024), read.call_args_list)
            self.assertEqual(
                {call.args[0] for call in close.call_args_list},
                {11, 12, 13, 14, 15, 16},
            )
            killer.assert_not_called()

    def test_transient_inventory_failure_must_resolve_before_success(self):
        from contextlib import ExitStack

        with ExitStack() as stack:
            close, read, waiter, killer = self.mocks(
                stack,
                inventories=[
                    [object()],
                    uid_probe.InventoryError("temporary churn"),
                    [],
                ],
            )
            result = uid_probe.run_case(62001, "detached")
            self.assertEqual(result["survivors"], 0)
            self.assertEqual(result["inventory_errors"], 1)
            self.assertEqual(result["error_count"], 1)
            self.assertEqual(result["worker_status"], 0)
            killer.assert_not_called()
