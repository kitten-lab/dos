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
from datetime import date

from dos.tdf import (
    next_upcoming_starts,
    parse_range_text,
    parse_ticket_date_token,
    ticket_calendar_phase,
    ticket_list_sort_key,
    ticket_subtype_rank,
)
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

    def test_ticket_sort_keys(self) -> None:
        self.assertLess(ticket_subtype_rank("date"), ticket_subtype_rank("note"))
        self.assertLess(
            ticket_list_sort_key("date", {"start": "2026-01-01"}),
            ticket_list_sort_key("date", {"start": "2026-12-01"}),
        )
        self.assertLess(
            ticket_list_sort_key("date", {"start": "July 1 2026"}),
            ticket_list_sort_key("note", {"raw": "hello"}),
        )
        d = parse_ticket_date_token("2026-07-21")
        self.assertIsNotNone(d)
        assert d is not None
        self.assertEqual(d.isoformat(), "2026-07-21")

    def test_calendar_phases(self) -> None:
        today = date(2026, 7, 20)
        past = {"start": "2026-01-01", "end": "2026-01-31"}
        active = {"start": "2026-07-01", "end": "2026-07-31"}
        point_today = {"start": "2026-07-20"}
        soon = {"start": "2026-08-01"}
        later = {"start": "2026-12-01"}
        next_starts = next_upcoming_starts(
            [past, active, point_today, soon, later], today=today
        )
        self.assertEqual(next_starts, {date(2026, 8, 1)})
        self.assertEqual(
            ticket_calendar_phase(past, today=today, next_starts=next_starts),
            "OVER",
        )
        self.assertEqual(
            ticket_calendar_phase(active, today=today, next_starts=next_starts),
            "ACTIVE",
        )
        self.assertEqual(
            ticket_calendar_phase(
                point_today, today=today, next_starts=next_starts
            ),
            "ACTIVE",
        )
        self.assertEqual(
            ticket_calendar_phase(soon, today=today, next_starts=next_starts),
            "NEXT",
        )
        self.assertIsNone(
            ticket_calendar_phase(later, today=today, next_starts=next_starts)
        )


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
        # Brick face is the due-date bits (not a generic TICKET chip)
        self.assertNotIn("TICKET", look)
        self.assertIn("Jan 20", look)
        self.assertIn("Feb 15", look)
        self.assertRegex(look, r"Jan 20.*Feb 15")
        # Row: name then date brick then TDF id (phase may lead when dated)
        gr = next(ln for ln in look.splitlines() if "Global Release Date" in ln)
        self.assertLess(gr.index("Global Release Date"), gr.index("Jan 20"))
        self.assertRegex(gr, r"TDF-\d+")
        self.assertLess(gr.index("Jan 20"), gr.index("TDF-"))

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

    def test_look_sorts_tickets_by_type_and_date(self) -> None:
        # Print out of order: note first, late date, early date, label
        self.assertTrue(
            dispatch(
                self.world,
                "print ticket -t note -n Sticky Scribbles -d remember milk",
            ).ok
        )
        self.assertTrue(
            dispatch(
                self.world,
                "print ticket -t date -k due -n Late Ship -d 2026-12-01",
            ).ok
        )
        self.assertTrue(
            dispatch(
                self.world,
                "print ticket -t date -k due -n Early Ship -d 2026-03-01",
            ).ok
        )
        self.assertTrue(
            dispatch(
                self.world,
                "print ticket -t label -n Project Alpha -d ALPHA",
            ).ok
        )
        look = plain(dispatch(self.world, "look").message)
        early = look.index("Early Ship")
        late = look.index("Late Ship")
        label = look.index("Project Alpha")
        note = look.index("Sticky Scribbles")
        # date (chrono) · label · note
        self.assertLess(early, late)
        self.assertLess(late, label)
        self.assertLess(label, note)

    def test_print_assignment_requires_person_ven(self) -> None:
        r = dispatch(
            self.world,
            "print ass -n Sprint Owner -d NotAPerson -k lead",
        )
        msg = plain(r.message).lower()
        self.assertIn("person", msg)
        self.assertIn("no person", msg)

        # Create a non-person and refuse
        self.assertTrue(
            dispatch(self.world, "create thing Desk Lamp | bright").ok
        )
        r2 = dispatch(
            self.world,
            "print ass -n Lighting -d Desk Lamp -k tech",
        )
        msg2 = plain(r2.message).lower()
        self.assertIn("person", msg2)
        self.assertNotIn("printed ticket", msg2)

    def test_print_ass_assigns_person_and_look_lead(self) -> None:
        # Office seed has Operator (person)
        r = dispatch(
            self.world,
            "print ass -n Sprint Owner -d Operator -k lead",
        )
        self.assertTrue(r.ok, msg=r.message)
        text = plain(r.message)
        self.assertIn("Printed ticket", text)
        self.assertIn("assignment", text.lower())
        # Brick uses lived instance title (office Operator may be titled "You")
        self.assertTrue(
            "Operator" in text or "You" in text,
            msg=text,
        )

        look = plain(dispatch(self.world, "look").message)
        row = next(ln for ln in look.splitlines() if "Sprint Owner" in ln)
        # col1 staff kind · name · person brick · TDF — never "ass" on the row
        self.assertIn("lead", row)
        self.assertLess(row.index("lead"), row.index("Sprint Owner"))
        self.assertRegex(row, r"TDF-\d+")
        self.assertNotIn(" ass", row.lower())
        self.assertNotRegex(row, r"\bass\b")

        # Also accept print assignment and -t assignment
        r2 = dispatch(
            self.world,
            "print assignment -n On-call -d Operator -k oncall",
        )
        self.assertTrue(r2.ok, msg=r2.message)
        look2 = plain(dispatch(self.world, "look").message)
        oc = next(ln for ln in look2.splitlines() if "On-call" in ln)
        self.assertIn("oncall", oc)

    def test_print_ass_binds_person_instance_not_only_prime(self) -> None:
        """spawn Game Designer as Joshua → assign Joshua (lived instance)."""
        self.assertTrue(
            dispatch(
                self.world,
                "create person Game Designer | Makes the fun.",
            ).ok
        )
        self.assertTrue(
            dispatch(self.world, "spawn game-designer as Joshua").ok
        )
        r = dispatch(
            self.world,
            "print ass -n Design Lead -d Joshua -k designer",
        )
        self.assertTrue(r.ok, msg=r.message)
        self.assertIn("Joshua", plain(r.message))
        # Also works via prime name when only one spawn
        r2 = dispatch(
            self.world,
            "print ass -n Backup -d Game Designer -k support",
        )
        self.assertTrue(r2.ok, msg=r2.message)

        look = plain(dispatch(self.world, "look").message)
        row = next(ln for ln in look.splitlines() if "Design Lead" in ln)
        self.assertIn("designer", row)
        self.assertIn("Joshua", row)
        self.assertLess(row.index("designer"), row.index("Joshua"))
        # Payload bound the instance
        slips = [
            i
            for i in self.world.resolve_here_candidates()
            if self.world.is_tdf(i.id) and i.name == "Design Lead"
        ]
        self.assertEqual(len(slips), 1)
        data = (self.world.tdf_payload(slips[0].id) or {}).get("data") or {}
        self.assertIn("person_instance_id", data)
        self.assertEqual(data.get("person_name"), "Joshua")

    def test_destroy_ticket_and_undo(self) -> None:
        self.assertTrue(
            dispatch(
                self.world,
                "print ticket -t date -k due -n Burn Slip -d 2026-09-01",
            ).ok
        )
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("Burn Slip", look)
        r = dispatch(self.world, "destroy ticket Burn Slip")
        self.assertIn("Destroyed", plain(r.message), msg=r.message)
        look2 = plain(dispatch(self.world, "look").message)
        self.assertNotIn("Burn Slip", look2)
        # Not in Lost Dept either
        lost = plain(dispatch(self.world, "lost").message)
        self.assertNotIn("Burn Slip", lost)
        u = dispatch(self.world, "undo")
        self.assertTrue(u.ok, msg=u.message)
        look3 = plain(dispatch(self.world, "look").message)
        self.assertIn("Burn Slip", look3)

    def test_destroy_non_ticket_refused(self) -> None:
        self.assertTrue(
            dispatch(self.world, "create thing Coffee Mug | ceramic").ok
        )
        self.assertTrue(dispatch(self.world, "spawn coffee-mug").ok)
        r = dispatch(self.world, "destroy ticket Coffee Mug")
        msg = plain(r.message).lower()
        self.assertIn("not a ticket", msg)

    def test_look_date_ticket_phases(self) -> None:
        """Presence rows show OVER / ACTIVE / NEXT from real calendar today."""
        from datetime import timedelta

        today = date.today()
        past_a = (today - timedelta(days=90)).isoformat()
        past_b = (today - timedelta(days=60)).isoformat()
        act_a = (today - timedelta(days=3)).isoformat()
        act_b = (today + timedelta(days=3)).isoformat()
        nxt = (today + timedelta(days=14)).isoformat()
        far = (today + timedelta(days=120)).isoformat()

        self.assertTrue(
            dispatch(
                self.world,
                f"print ticket -t date -k range -n Winter Window "
                f"-d {past_a} - {past_b}",
            ).ok
        )
        self.assertTrue(
            dispatch(
                self.world,
                f"print ticket -t date -k range -n Summer Sprint "
                f"-d {act_a} - {act_b}",
            ).ok
        )
        self.assertTrue(
            dispatch(
                self.world,
                f"print ticket -t date -k due -n Next Gate -d {nxt}",
            ).ok
        )
        self.assertTrue(
            dispatch(
                self.world,
                f"print ticket -t date -k due -n Far Gate -d {far}",
            ).ok
        )
        look = plain(dispatch(self.world, "look").message)
        self.assertIn("OVER", look)
        self.assertIn("ACTIVE", look)
        self.assertIn("NEXT", look)
        # Far Gate is future-but-not-next — no phase word required on that line
        far_ln = next(ln for ln in look.splitlines() if "Far Gate" in ln)
        self.assertNotIn("NEXT", far_ln)
        self.assertNotIn("ACTIVE", far_ln)
        self.assertNotIn("OVER", far_ln)
        next_ln = next(ln for ln in look.splitlines() if "Next Gate" in ln)
        self.assertIn("NEXT", next_ln)


if __name__ == "__main__":
    unittest.main()
