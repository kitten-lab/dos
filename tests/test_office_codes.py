"""DOS office face codes: slug3-hex, singleton bare, .2 multi."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dos.commands import dispatch
from dos.db import connect
from dos.format import plain
from dos.ids import (
    format_instance_short_ref,
    is_office_ven_code,
    mint_office_ven_code,
    parse_instance_ref_token,
    parse_ven_code,
    slug_face_prefix,
)
from dos.seed import seed_world_office
from dos.world import World


class OfficeCodeUnitTests(unittest.TestCase):
    def test_slug_face_prefix(self) -> None:
        self.assertEqual(slug_face_prefix("Company Handbook"), "com")
        self.assertEqual(slug_face_prefix("COMPANY-HANDBOOK"), "com")
        self.assertEqual(slug_face_prefix("Meeting Room"), "mee")
        self.assertEqual(slug_face_prefix("AB"), "abx")

    def test_mint_shape(self) -> None:
        code = mint_office_ven_code("Company Handbook")
        self.assertTrue(is_office_ven_code(code))
        self.assertTrue(code.startswith("com-"))
        self.assertEqual(code, code.lower())
        self.assertRegex(code, r"^com-[0-9a-f]{6}$")

    def test_parse_office_and_legacy(self) -> None:
        self.assertEqual(parse_ven_code("COM-7F3A2C"), "com-7f3a2c")
        self.assertEqual(parse_ven_code("com-7f3a2c.2"), "com-7f3a2c")
        self.assertEqual(parse_ven_code("RLM-001"), "RLM-001")
        self.assertEqual(parse_ven_code("rlm-1"), "RLM-001")

    def test_face_singleton_and_dot(self) -> None:
        face = format_instance_short_ref(
            "HANDBOOK", 1, ven_code="com-7f3a2c", singleton=False
        )
        self.assertEqual(face, "com-7f3a2c")
        face2 = format_instance_short_ref(
            "HANDBOOK", 2, ven_code="com-7f3a2c"
        )
        self.assertEqual(face2, "com-7f3a2c.2")
        self.assertEqual(
            format_instance_short_ref(
                "HANDBOOK", 2, ven_code="com-7f3a2c", singleton=True
            ),
            "com-7f3a2c",
        )

    def test_parse_instance_token(self) -> None:
        self.assertEqual(parse_instance_ref_token("com-7f3a2c"), "com-7f3a2c")
        self.assertEqual(
            parse_instance_ref_token("com-7f3a2c.2"), "com-7f3a2c.2"
        )


class OfficeCodeWorldTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
        tmp.close()
        conn = connect(Path(tmp.name))
        seed_world_office(conn)
        self.world = World(conn)

    def test_seed_codes_are_office_faces(self) -> None:
        handbook = None
        for c in self.world.resolve_here_candidates():
            if "Handbook" in (c.name or ""):
                handbook = c
                break
        self.assertIsNotNone(handbook)
        assert handbook is not None
        code = (handbook.ven_code or "").lower()
        self.assertTrue(is_office_ven_code(code), msg=code)
        self.assertTrue(code[0:3].isalpha() or code[0].isalnum())
        ref = self.world.short_ref_of(handbook.id)
        self.assertEqual(ref, code)  # singleton bare
        self.assertNotIn(".1", ref)
        self.assertNotRegex(ref, r"^[A-Z]{3}-\d{3}")

    def test_second_spawn_gets_dot_2(self) -> None:
        r = dispatch(self.world, "create folio Memo Pad | notes")
        self.assertTrue(r.ok, msg=r.message)
        self.assertTrue(dispatch(self.world, "spawn memo-pad").ok)
        a = self.world.resolve_here_named("Memo Pad")
        assert a is not None
        code = parse_ven_code(a.ven_code or "")
        self.assertTrue(is_office_ven_code(code))
        self.assertEqual(self.world.short_ref_of(a.id), code)
        self.assertTrue(
            dispatch(self.world, "spawn memo-pad as Memo Pad Two").ok
        )
        b = self.world.resolve_here_named("Memo Pad Two")
        assert b is not None
        self.assertEqual(self.world.short_ref_of(b.id), f"{code}.2")
        # resolve by face
        hit = self.world.resolve_here_named(f"{code}.2")
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.id, b.id)

    def test_look_shows_office_code_not_fol001(self) -> None:
        look = plain(dispatch(self.world, "look").message)
        self.assertNotIn("FOL-001", look)
        self.assertNotIn("PLC-001", look)


if __name__ == "__main__":
    unittest.main()
