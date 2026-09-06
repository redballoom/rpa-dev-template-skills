import argparse
import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update_trellis_progress.py"
SPEC = importlib.util.spec_from_file_location("update_trellis_progress", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class RetiredProgressWriterTests(unittest.TestCase):
    def test_legacy_writer_refuses_task_local_gate_updates(self) -> None:
        with self.assertRaises(MODULE.ProgressError) as context:
            MODULE.update_progress(argparse.Namespace())
        self.assertIn(".project-gates/", str(context.exception))

    def test_skill_defines_reviewable_management_commit_boundary(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        reference = (skill_root / "references" / "management-write-boundaries.md").read_text(encoding="utf-8")
        self.assertIn("management-write-boundaries.md", skill)
        self.assertIn("session_auto_commit: false", reference)
        self.assertIn("one focused commit", reference)
        self.assertIn("Business implementation", reference)
        self.assertIn("Governance and generated collaboration state", reference)


if __name__ == "__main__":
    unittest.main()
