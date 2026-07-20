"""print ticket — Temporary Data Fragments (TDF slips)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dos.commands import dispatch
from dos.db import connect
from dos.format import plain
from dos.ids import parse_tdf_code
from dos.seed import seed_world_office
from dos.tdf import parse_range_text
from dos.world import World


def _office() -> World:
    tmp = tempfile.NamedTemporaryFile(suffix=".world.db", delete=False)
    tmp.close()
    conn = connect(Path(tmp.name))
    seed_world_office(conn)
    return World(conn)


class RangeParseTests(unittest.TestCase):
    def test_range_split(self) -> None:
        r = parse_range_text("Jan 20 - Feb 15 2026")
        self.assertEqual(r["start"], "Jan 20")
        self.assertEqual(r["end"], "Feb 15 2026")
        self.assertIn("Jan 20", r["raw"])


class PrintTicketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = _office()

    def test_print_date_range_ticket(self) -> None:
        r = dispatch(
            self.world,
            "print ticket -t date -k range -n Global Release Date "
            "-d Jan 20 - Feb 15 2026",
        )
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Printed ticket", text)
        self.assertIn("Global Release Date", text)
        self.assertIn("TDF-", text)
        self.assertIn("date", text.lower())
        self.assertIn("range", text.lower())

        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Global Release Date", look)
        # Brick + id + details + kind
        self.assertIn("TICKET:DATE", look)
        self.assertIn("Jan 20", look)
        self.assertIn("Feb 15", look)
        self.assertRegex(look, r"Jan 20.*Feb 15")
        self.assertIn("range", look.lower())

        # recover code from print message
        code = None
        for token in text.replace("\n", " ").split():
            if parse_tdf_code(token):
                code = parse_tdf_code(token)
                break
        self.assertIsNotNone(code, msg=text)

        exam = plain(dispatch(self.world, f"examine {code}").message)
        self.assertIn("Global Release Date", exam)
        self.assertIn("TDF", exam)
        self.assertTrue(
            "Jan 20" in exam and "Feb 15" in exam,
            msg=exam,
        )

    def test_ticket_takeable(self) -> None:
        dispatch(
            self.world,
            "print ticket -t date -k due -n Ship Window -d 2026-03-01",
        )
        r = dispatch(self.world, "take Global Release Date")
        # may fail if not that name — take ship window
        r = dispatch(self.world, "take Ship Window")
        self.assertTrue(r.ok, msg=r.message)
        inv = plain(dispatch(self.world, "inv").message)
        self.assertIn("Ship Window", inv)

    def test_one_ticket_prime_many_slips(self) -> None:
        dispatch(
            self.world,
            "print ticket -t date -k range -n A -d Jan 1 - Jan 2",
        )
        dispatch(
            self.world,
            "print ticket -t date -k range -n B -d Feb 1 - Feb 2",
        )
        ticket_vens = [
            v for v in self.world.list_vens() if (v.kind or "") == "ticket"
        ]
        self.assertEqual(len(ticket_vens), 1, msg=[v.name for v in ticket_vens])
        slips = [
            i
            for i in self.world.resolve_here_candidates()
            if self.world.is_tdf(i.id)
        ]
        self.assertGreaterEqual(len(slips), 2)

    def test_tdf_code_resolve(self) -> None:
        dispatch(
            self.world,
            "print ticket -t date -k range -n Resolve Me -d Mar 1 - Mar 2",
        )
        slips = [
            i
            for i in self.world.resolve_here_candidates()
            if self.world.is_tdf(i.id) and i.name == "Resolve Me"
        ]
        self.assertEqual(len(slips), 1)
        code = self.world.tdf_payload(slips[0].id)["code"]
        hit = self.world.resolve_here_named(code)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.id, slips[0].id)


if __name__ == "__main__":
    unittest.main()
