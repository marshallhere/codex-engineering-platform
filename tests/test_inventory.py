"""CEP-SETUP: portable metadata never exports local secrets or bindings."""

import json
from pathlib import Path
import tempfile
import unittest

from cep.inventory import inventory


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        return path

    def test_config_redacts_credentials_and_account_specific_endpoints(self):
        path = self.write(
            "config.toml",
            """
[mcp_servers.stripe]
url = "https://mcp.stripe.com?api_key=secret-canary"
bearer_token_env_var = "STRIPE_TOKEN"
[mcp_servers.stripe.http_headers]
Authorization = "Bearer header-canary"
[mcp_servers.stripe.env]
API_KEY = "canary"
[mcp_servers.sentry]
url = "https://private-company.invalid/account/private-id/project/private-name"
[mcp_servers.local]
command = "/some/private-machine-path/server"
args = ["--password", "argument-canary"]
""".replace('"canary"', json.dumps("environment-canary")),
        )
        result = inventory([path], [], [])
        text = json.dumps(result)
        for private in (
            "secret-canary",
            "header-canary",
            "environment-canary",
            "private-company",
            "private-id",
            "private-name",
            "private-machine-path",
            "argument-canary",
            str(self.root),
        ):
            self.assertNotIn(private, text)
        stripe = next(item for item in result["mcps"] if item["name"] == "stripe")
        self.assertEqual(stripe["endpoint"], "https://mcp.stripe.com")
        self.assertEqual(stripe["env_names"], ["API_KEY", "STRIPE_TOKEN"])
        self.assertEqual(result["provider_access"], "unverified")

    def test_duplicate_config_names_keep_source_provenance(self):
        paths = [
            self.write(
                f"root-{i}/config.toml",
                '[mcp_servers.github]\ncommand="npx"\nargs=["-y", "@example/github-mcp@1.2.3"]\n',
            )
            for i in (1, 2)
        ]
        report = inventory(paths, [], [])
        self.assertEqual(len(report["mcps"]), 2)
        self.assertEqual(
            {item["source"] for item in report["mcps"]}, {"config-1", "config-2"}
        )
        self.assertTrue(all(item["version_pinned"] for item in report["mcps"]))

    def test_skills_are_hashed_not_copied_and_plugin_licenses_are_not_copy_permission(
        self,
    ):
        self.write(
            "skills/sample/SKILL.md",
            "---\nname: sample\ndescription: Work\n---\nsecret-body-canary\n",
        )
        self.write(
            "plugins/sample/plugin.json",
            json.dumps(
                {
                    "name": "sample-plugin",
                    "version": "1.2.3",
                    "license": "MIT",
                    "private": "manifest-canary",
                }
            ),
        )
        report = inventory([], [self.root / "skills"], [self.root / "plugins"])
        text = json.dumps(report)
        self.assertNotIn("secret-body-canary", text)
        self.assertNotIn("manifest-canary", text)
        self.assertNotIn(str(self.root), text)
        self.assertEqual(len(report["skills"][0]["sha256"]), 64)
        plugin = report["plugins"][0]
        self.assertEqual(plugin["version"], "1.2.3")
        self.assertEqual(plugin["disposition"], "reference")
        self.assertEqual(plugin["license"]["redistribution"], "review-required")

    def test_symlink_metadata_and_auth_files_are_never_read(self):
        self.write("outside/SKILL.md", "---\nname: outside-private\n---\n")
        (self.root / "skills").mkdir()
        (self.root / "skills/external").symlink_to(
            self.root / "outside", target_is_directory=True
        )
        self.write(
            "plugins/auth/plugin.json", '{"name":"credential-canary","version":"1.0.0"}'
        )
        report = inventory([], [self.root / "skills"], [self.root / "plugins"])
        self.assertEqual(report["skills"][0]["name"], "external")
        self.assertEqual(report["skills"][0]["disposition"], "unavailable")
        self.assertIsNone(report["skills"][0]["sha256"])
        self.assertEqual(report["plugins"], [])

    def test_agent_metadata_and_plugin_skills_are_included_without_instructions(self):
        config = self.write("codex/config.toml", "")
        self.write(
            "codex/agents/reviewer.toml",
            'name="reviewer"\nmodel="gpt-6.1-sol"\ndeveloper_instructions="private-instruction-canary"\n',
        )
        self.write(
            "plugins/example/plugin.json", '{"name":"example","version":"1.0.0"}'
        )
        self.write(
            "plugins/example/skills/helper/SKILL.md",
            "---\nname: helper\ndescription: Example\n---\nprivate-skill-canary\n",
        )
        report = inventory([config], [], [self.root / "plugins"])
        self.assertEqual(report["agents"][0]["name"], "reviewer")
        self.assertEqual(report["skills"][0]["plugin"], "example")
        self.assertNotIn("canary", json.dumps(report))

    def test_missing_and_malformed_inputs_do_not_leak_exception_values(self):
        config = self.write("bad/config.toml", 'secret_name="secret-canary\n')
        report = inventory([config, self.root / "absent"], [], [])
        self.assertEqual(
            [item["state"] for item in report["inputs"]], ["unavailable", "unavailable"]
        )
        self.assertNotIn("secret-canary", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
