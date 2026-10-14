"""The experimental authority guard must run before any privileged action."""
import os
from unittest import TestCase, mock

from native import uid_probe


class UIDProbeGuardTests(TestCase):
    def test_developer_machine_rejected_before_staging_access(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(uid_probe.Path, 'stat') as probe:
            with self.assertRaisesRegex(RuntimeError, 'disposable'):
                uid_probe.guard()
            probe.assert_not_called()

    def test_environment_markers_do_not_replace_platform_and_uid_checks(self):
        markers = {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
                   'CEP_UID_EXPERIMENT': 'disposable-v1'}
        with mock.patch.dict(os.environ, markers, clear=True), mock.patch.object(uid_probe.sys, 'platform', 'darwin'), mock.patch.object(uid_probe.os, 'getuid', return_value=501), mock.patch.object(uid_probe.os, 'geteuid', return_value=501):
            with self.assertRaisesRegex(RuntimeError, 'disposable'):
                uid_probe.guard()

    def test_drop_rejects_root_and_existing_system_identity(self):
        with mock.patch.object(uid_probe.resource, 'setrlimit') as limits:
            for uid in (0, 501, 65534, -1):
                with self.subTest(uid=uid), self.assertRaises(RuntimeError):
                    uid_probe.drop(uid)
            limits.assert_not_called()

    def test_prerequisites_never_claim_production_qualification(self):
        self.assertIs(uid_probe.prerequisites()['production_qualified'], False)
