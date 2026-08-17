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
        self.assertIn(".hermes/", str(context.exception))


if __name__ == "__main__":
    unittest.main()
