"""Tests for the standalone workflow identity migration tool."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "migrate_workflow.py"
SPEC = importlib.util.spec_from_file_location("matrixlab_migrate_workflow", TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load migration tool")
MIGRATION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MIGRATION
SPEC.loader.exec_module(MIGRATION)


class IdentityMigrationTests(unittest.TestCase):
    def test_mapping_covers_the_eight_reviewed_identity_changes(self):
        self.assertEqual(
            MIGRATION.IDENTITY_MIGRATIONS,
            {
                "MATRIX_SaveClean": "MATRIX_MetadataKiller",
                "MATRIXLAB_PromptDirector": "MATRIX_AutoPrompter",
                "MATRIXLAB_ImageBatchLoader": "MATRIX_ImageBatchLoader",
                "MATRIXLAB_Resolution": "MATRIX_Resolution",
                "MATRIXLAB_AIInfluencerResolution": "MATRIX_AIInfluencerResolution",
                "MATRIXLAB_AIInfluencerResolution2K4K": "MATRIX_AIInfluencerResolution2K4K",
                "MATRIXLAB_EasyCrop": "MATRIX_EasyCrop",
                "MATRIXSpectralSampler": "MATRIX_SpectralSampler",
            },
        )

    def test_ui_migration_is_pure_narrow_and_idempotent(self):
        source = {
            "nodes": [
                {
                    "id": 1,
                    "type": "MATRIX_SaveClean",
                    "properties": {
                        "Node name for S&R": "MATRIX_SaveClean",
                        "note": "MATRIX_SaveClean must remain here",
                    },
                    "widgets_values": ["MATRIX_SaveClean", 100],
                },
                {
                    "id": 2,
                    "type": "MATRIXLAB_PromptDirector",
                    "properties": {"Node name for S&R": "custom-alias"},
                },
                {"id": 3, "type": "MATRIX_Renoise"},
            ],
            "extra": {"prompt": "MATRIXLAB_PromptDirector"},
            "links": [[4, 1, 0, 2, 0, "IMAGE"]],
        }

        migrated, report = MIGRATION.migrate_workflow(source)

        self.assertEqual(source["nodes"][0]["type"], "MATRIX_SaveClean")
        self.assertEqual(migrated["nodes"][0]["type"], "MATRIX_MetadataKiller")
        self.assertEqual(
            migrated["nodes"][0]["properties"]["Node name for S&R"],
            "MATRIX_MetadataKiller",
        )
        self.assertEqual(migrated["nodes"][0]["properties"]["note"],
                         "MATRIX_SaveClean must remain here")
        self.assertEqual(migrated["nodes"][0]["widgets_values"], ["MATRIX_SaveClean", 100])
        self.assertEqual(migrated["extra"], source["extra"])
        self.assertEqual(migrated["links"], source["links"])
        self.assertEqual(migrated["nodes"][1]["properties"]["Node name for S&R"], "custom-alias")
        self.assertEqual(report.migrated_nodes,
                         {"MATRIX_SaveClean": 1, "MATRIXLAB_PromptDirector": 1})
        self.assertEqual(report.replaced_identity_fields, 3)
        self.assertEqual(report.retired_nodes, {"MATRIX_Renoise": 1})

        repeated, repeated_report = MIGRATION.migrate_workflow(migrated)
        self.assertEqual(repeated, migrated)
        self.assertEqual(repeated_report.migrated_nodes, {})
        self.assertEqual(repeated_report.replaced_identity_fields, 0)
        self.assertEqual(repeated_report.retired_nodes, {"MATRIX_Renoise": 1})

    def test_direct_and_enveloped_api_prompts_only_change_class_type(self):
        prompt = {
            str(index): {
                "class_type": old,
                "inputs": {"text": old},
                "_meta": {"title": old},
            }
            for index, old in enumerate(MIGRATION.IDENTITY_MIGRATIONS, start=1)
        }
        prompt["retired"] = {"class_type": "MATRIX_CameraLook", "inputs": {}}
        for source in (prompt, {"prompt": prompt, "client_id": "MATRIX_SaveClean"}):
            with self.subTest(enveloped="prompt" in source):
                migrated, report = MIGRATION.migrate_workflow(source)
                migrated_prompt = migrated.get("prompt", migrated)
                for index, (old, new) in enumerate(MIGRATION.IDENTITY_MIGRATIONS.items(), start=1):
                    with self.subTest(node_id=index):
                        node = migrated_prompt[str(index)]
                        self.assertEqual(node["class_type"], new)
                        self.assertEqual(node["inputs"], {"text": old})
                        self.assertEqual(node["_meta"], {"title": old})
                if "prompt" in source:
                    self.assertEqual(migrated["client_id"], "MATRIX_SaveClean")
                self.assertEqual(report.format, "api")
                self.assertEqual(report.retired_nodes, {"MATRIX_CameraLook": 1})

    def test_malformed_identity_fields_raise_clear_value_errors(self):
        for source, message in (
            ({"nodes": [{"type": ["MATRIX_SaveClean"]}]}, "UI node.type must be a string"),
            ({"1": {"class_type": ["MATRIX_SaveClean"]}},
             "API node.class_type must be a string"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                MIGRATION.migrate_workflow(source)

    def test_cli_writes_new_output_and_refuses_overwrites(self):
        source_document = {"1": {"class_type": "MATRIXSpectralSampler", "inputs": {}}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.json"
            output = root / "output.json"
            source.write_text(json.dumps(source_document), encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(TOOL_PATH), "--input", str(source), "--output", str(output)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["1"]["class_type"],
                             "MATRIX_SpectralSampler")
            original = source.read_bytes()

            existing = subprocess.run(
                [sys.executable, str(TOOL_PATH), "--input", str(source), "--output", str(output)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(existing.returncode, 0)
            self.assertIn("refusing existing output", existing.stderr)

            with mock.patch.object(Path, "exists", return_value=False):
                with self.assertRaisesRegex(SystemExit, "refusing existing output"):
                    MIGRATION.main(["--input", str(source), "--output", str(output)])
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["1"]["class_type"],
                             "MATRIX_SpectralSampler")

            same = subprocess.run(
                [sys.executable, str(TOOL_PATH), "--input", str(source), "--output", str(source)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(same.returncode, 0)
            self.assertIn("refusing to overwrite", same.stderr)
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
