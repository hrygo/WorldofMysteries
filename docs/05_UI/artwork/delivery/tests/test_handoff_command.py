"""Keep the copy-paste W1 finishing command aligned with its required crop anchor."""
import json
from pathlib import Path
import re
import shlex
import unittest


class HandoffCommandTests(unittest.TestCase):
    def test_w1_finishing_command_preserves_required_anchor(self):
        delivery = Path(__file__).resolve().parents[1]
        manifest = json.loads((delivery / "approved_sources.json").read_text())
        w1 = next(row for row in manifest["world_targets"] if row["task_id"] == "W1")
        text = (delivery.parent / "W1_macOS_Finishing_Backlog.md").read_text()
        section = text.split("### F6", 1)[1].split("### F7", 1)[0]
        blocks = re.findall(r"```bash\n(.*?)```", section, re.DOTALL)
        self.assertEqual(len(blocks), 1)
        args = shlex.split(blocks[0].replace("\\\n", " "))
        self.assertEqual(args[:3], ["xcrun", "swift", "docs/05_UI/artwork/tools/derive_world_artwork.swift"])
        self.assertIn("--wide-anchor", args)
        self.assertEqual(args[args.index("--wide-anchor") + 1], w1["wide_anchor"])
        self.assertEqual(w1["wide_anchor"], "top")


if __name__ == "__main__":
    unittest.main()
