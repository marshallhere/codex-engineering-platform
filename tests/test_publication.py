"""Public releases must scan removed historical credentials, not just HEAD."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.check_publication import audit_repository


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.root), *args], capture_output=True, check=True
        ).stdout

    def commit(self, text):
        (self.root / "fixture.txt").write_text(text)
        self.git("add", "fixture.txt")
        self.git("commit", "-qm", "fixture")

    def test_removed_credential_in_history_blocks_without_printing_it(self):
        credential = "sk_" + "test_" + "A" * 32
        self.commit("credential=" + credential + "\n")
        self.commit("credential removed\n")
        result = audit_repository(self.root)
        self.assertEqual(result["status"], "blocked")
        self.assertIn(
            "stripe-secret", {finding["kind"] for finding in result["findings"]}
        )
        self.assertNotIn(credential, json.dumps(result))
        self.assertTrue(all("line" in finding for finding in result["findings"]))

    def test_current_tracked_and_index_only_content_are_scanned(self):
        self.commit("clean\n")
        (self.root / "fixture.txt").write_text("Bearer " + "B" * 32)
        self.git("add", "fixture.txt")
        (self.root / "fixture.txt").write_text('password = "' + "C" * 24 + '"\n')
        result = audit_repository(self.root)
        kinds = {item["kind"] for item in result["findings"]}
        self.assertIn("bearer-token", kinds)
        self.assertIn("secret-assignment", kinds)
        self.assertEqual(result["status"], "blocked")

    def test_placeholders_reserved_addresses_and_annotated_dummy_are_allowed(self):
        dummy = ".".join(["10", "0", "0", "1"])
        self.commit(
            'api_key="<API_KEY>"\npassword="REPLACE_ME"\nendpoint="192.0.2.1"\n'
            + dummy
            + " # publication: dummy-ip\n"
        )
        self.assertEqual(audit_repository(self.root)["status"], "passed")

    def test_no_blanket_exemption_for_tests_or_private_addresses(self):
        address = ".".join(["10", "7", "8", "9"])
        (self.root / "tests").mkdir()
        (self.root / "tests/case.py").write_text(address + " # publication: dummy-ip\n")
        self.git("add", "tests/case.py")
        self.git("commit", "-qm", "fixture")
        result = audit_repository(self.root)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("private-ip", {item["kind"] for item in result["findings"]})
        self.assertNotIn(address, json.dumps(result))

    def test_local_user_paths_are_found_without_echoing_the_identity(self):
        private_path = "/Users/" + "private-person" + "/credentials"
        self.commit(private_path)
        result = audit_repository(self.root)
        self.assertIn(
            "machine-user-path", {item["kind"] for item in result["findings"]}
        )
        self.assertNotIn("private-person", json.dumps(result))

    def test_symlink_contents_are_not_followed(self):
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / "credential.txt"
            outside.write_text("ghp_" + "Z" * 32)
            (self.root / "link.txt").symlink_to(outside)
            self.git("add", "link.txt")
            self.git("commit", "-qm", "fixture")
            result = audit_repository(self.root)
            self.assertEqual(result["status"], "passed")

    def test_deleted_sensitive_filename_in_history_blocks_without_echoing_it(self):
        name = "ghp_" + "N" * 32
        (self.root / name).write_text("clean content\n")
        (self.root / "a-harmless-name").write_text("clean content\n")
        self.git("add", name, "a-harmless-name")
        self.git("commit", "-qm", "fixture")
        self.git("rm", name)
        self.git("commit", "-qm", "remove fixture")
        result = audit_repository(self.root)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("history-path", {item["scope"] for item in result["findings"]})
        self.assertNotIn(name, json.dumps(result))

    def test_missing_repository_reports_only_generic_error(self):
        private = self.root / "private-machine-name"
        result = audit_repository(private)
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("private-machine-name", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
