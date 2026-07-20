"""Import ven-minter tree packs (nested contents)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dos.db import connect
from dos.seed import seed_world_void
from dos.ven_pack import import_pack
from dos.world import World


def _world() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_void(conn)
    return World(conn)


class TreePackImportTests(unittest.TestCase):
    def test_import_tree_puts_nested_contents(self) -> None:
        world = _world()
        loc = world.player_location()
        assert loc is not None

        pack = {
            "format": "aidm.ven",
            "version": 3,
            "pack_kind": "tree",
            "seq": 1,
            "provenance": {
                "origin_world": "ven-minter",
                "home_code": "BIN-099",
                "pack_kind": "tree",
                "tool": "ven-minter",
            },
            "node": {
                "prime": {
                    "name": "Desk Kit",
                    "kind": "bin",
                    "subtype": None,
                    "description": "Portable kit.",
                    "slug": "desk-kit",
                    "code": "BIN-099",
                },
                "lore": [],
                "instance": {"short_ref_digits": "0001", "slot": "interior"},
                "contents": [
                    {
                        "prime": {
                            "name": "Black Pen",
                            "kind": "thing",
                            "description": "A simple pen.",
                            "slug": "black-pen",
                            "code": "THG-099",
                        },
                        "lore": [
                            {"title": "Care", "body": "Wipe the nib.", "author": "minter"}
                        ],
                        "instance": {"short_ref_digits": "0001", "slot": "interior"},
                        "contents": [],
                    },
                    {
                        "prime": {
                            "name": "Notebook",
                            "kind": "thing",
                            "subtype": "notebook",
                            "description": "Blank.",
                            "slug": "notebook",
                            "code": "THG-100",
                        },
                        "lore": [],
                        "instance": {"short_ref_digits": "0001", "slot": "interior"},
                        "contents": [],
                    },
                ],
            },
        }

        ven_id, code, inst_id, _note = import_pack(
            world,
            pack,
            target_world_label="Test Void",
            place_instance_id=loc.id,
        )
        self.assertIsNotNone(inst_id)
        assert inst_id is not None
        kit = world.get_instance(inst_id)
        assert kit is not None
        self.assertEqual(kit.name, "Desk Kit")
        self.assertEqual(kit.ven_kind, "bin")

        kids = world.contents(inst_id)
        names = {c.name for c in kids}
        self.assertEqual(names, {"Black Pen", "Notebook"})

        pen = next(c for c in kids if c.name == "Black Pen")
        lore = list(world.lore_for("instance", pen.id))
        self.assertTrue(any("Wipe the nib" in (r["body"] or "") for r in lore))


if __name__ == "__main__":
    unittest.main()
