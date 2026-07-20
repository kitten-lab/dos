"""Seed digital office worlds: office (default), empty, bootstrap.

You start *inside* the digital office network — infrastructure for companies
(humans and agents) collaborating across the wire. Narrative multiverse seeds
(story / cathedral / tavern) live in World Builder Studio, not here.
"""

from __future__ import annotations

import sqlite3

from .db import init_schema, set_meta
from .world import World

SEED_FLAVORS = ("office", "empty", "bootstrap")

# Old WBS flavor names → DOS office (scripts / muscle memory)
_LEGACY_TO_OFFICE = frozenset(
    {
        "story",
        "classic",
        "tavern",
        "wick",
        "whisper",
        "lantern",
        "default",
    }
)
_EMPTY_ALIASES = frozenset({"empty", "void", "blank", "shell", "suite", "bare-room"})
_BOOTSTRAP_ALIASES = frozenset({"bootstrap", "bare", "minimal", "nothing"})


def seed_world(conn: sqlite3.Connection, flavor: str = "office") -> None:
    """Seed a new world. flavor: office | empty | bootstrap."""
    flavor = (flavor or "office").lower().strip()
    if flavor in _LEGACY_TO_OFFICE or flavor == "office":
        seed_world_office(conn)
    elif flavor in _EMPTY_ALIASES:
        seed_world_empty(conn)
    elif flavor in _BOOTSTRAP_ALIASES:
        seed_world_bootstrap(conn)
    else:
        seed_world_office(conn)


def seed_world_office(conn: sqlite3.Connection) -> None:
    """
    Default DOS seed: a small company office already on the wire.

    Lobby → open floor → meeting room + records. Shared calendar, team channel,
    and handbook model schedules, chats, and data *in place*.
    """
    init_schema(conn)
    w = World(conn)

    # --- layers: digital campus, not fantasy multiverse ---
    realm_ven = w.create_ven(
        "Wire",
        "realm",
        (
            "The continuum where digital offices live. "
            "Desks, doors, and dossiers share one address space for humans and agents."
        ),
        tags=["digital", "office", "network"],
    )
    tl_ven = w.create_ven(
        "Workday",
        "timeline",
        "Business time: shifts, standups, and shared calendars.",
        tags=["schedule", "office"],
    )
    r_wire = w.instantiate(realm_ven)
    t_day = w.instantiate(tl_ven)

    def _place(
        name: str,
        desc: str,
        *,
        tags: list[str] | None = None,
        name_override: str | None = None,
        description_override: str | None = None,
    ) -> str:
        ven = w.create_ven(name, "place", desc, tags=tags or ["office"])
        return w.instantiate(
            ven,
            name_override=name_override,
            description_override=description_override,
            realm_instance_id=r_wire,
            timeline_instance_id=t_day,
        )

    lobby = _place(
        "Lobby",
        (
            "Glass, soft light, a badge reader that does not care if you are flesh or code. "
            "Visitors and remote agents arrive here the same way: through the wire."
        ),
        tags=["office", "arrival", "public"],
        name_override="Company Lobby",
        description_override=(
            "Glass, soft light, a badge reader that does not care if you are flesh or code.\n"
            "A slim handbook rests on the reception ledge. Beyond the glass wall: the open floor.\n"
            "You are already inside Digital Office Spaces — this is a company site on the wire."
        ),
    )

    floor = _place(
        "Open Floor",
        "Collaborative work area: desks, ambient hum, room to leave work where others can find it.",
        tags=["office", "work", "collab"],
        name_override="Open Floor",
        description_override=(
            "Rows of light desks under a quiet skyline of monitors that may not exist in meatspace.\n"
            "The team channel log sits where anyone can open it. North: meeting room. South: records."
        ),
    )

    meeting = _place(
        "Meeting Room",
        "Closed glass for standups, 1:1s, and decisions that need a wall.",
        tags=["office", "meeting", "schedule"],
        name_override="Meeting Room",
        description_override=(
            "A long table, mute chairs, one shared calendar board on the wall.\n"
            "Time lives here as pages you can open — not only as a widget somewhere else."
        ),
    )

    records = _place(
        "Records Room",
        "Shared storage: dossiers, dumps, and the files the company must keep.",
        tags=["office", "storage", "data"],
        name_override="Records Room",
        description_override=(
            "Cool air. Labeled cabinets. This is collaborative human (and agent) storage of data —\n"
            "in place, not a side panel. Put what matters on the shelf; others will find it."
        ),
    )

    # Paths — office adjacency, spatial only for the default campus
    w.link(lobby, floor, "into the open floor", "spatial", bidirectional=True, reverse_label="to the lobby")
    w.link(floor, meeting, "north", "spatial", bidirectional=True, reverse_label="south")
    w.link(floor, records, "south", "spatial", bidirectional=True, reverse_label="north")

    # --- you: operator on the company site ---
    operator_ven = w.create_ven(
        "Operator",
        "person",
        (
            "A colleague with badge rights — human or agent. "
            "You build and use the office from the inside."
        ),
        tags=["colleague", "user"],
        meta={"subtype": "archetype"},
    )
    operator = w.instantiate(
        operator_ven,
        name_override="You",
        realm_instance_id=r_wire,
        timeline_instance_id=t_day,
    )
    w.put_in(operator, lobby, slot="interior")
    w.set_player(operator)

    # --- in-place collab surfaces: data, schedules, chats ---
    handbook_ven = w.create_ven(
        "Company Handbook",
        "book",
        "Orientation and policy — how this office expects work to move.",
        tags=["data", "onboarding", "book"],
    )
    handbook = w.instantiate(
        handbook_ven,
        realm_instance_id=r_wire,
        timeline_instance_id=t_day,
    )
    w.put_in(handbook, lobby, slot="interior")
    w.add_book_page(
        handbook,
        "Welcome to the wire",
        (
            "This is Digital Office Spaces (DOS).\n"
            "\n"
            "You are inside a company office that exists for collaboration across the world and wires.\n"
            "Humans and agents share the same places, the same shelves, the same calendars.\n"
            "\n"
            "Start with look. Walk into the open floor. Open the team channel. Check the calendar.\n"
            "When you need a room that does not exist yet: dig, spawn, @desc — then invite others in."
        ),
    )
    w.add_book_page(
        handbook,
        "What lives in place",
        (
            "Data — records room, cabinets, dossiers on desks.\n"
            "Schedules — shared calendar in the meeting room.\n"
            "Chats — team channel log on the open floor.\n"
            "\n"
            "Other front ends may come later. The TUI is the office terminal for now."
        ),
    )

    channel_ven = w.create_ven(
        "Team Channel",
        "book",
        "Persistent chat for the floor — threads as pages, not ephemera.",
        tags=["chat", "collab", "book"],
    )
    channel = w.instantiate(
        channel_ven,
        name_override="Team Channel Log",
        realm_instance_id=r_wire,
        timeline_instance_id=t_day,
    )
    w.put_in(channel, floor, slot="interior")
    w.add_book_page(
        channel,
        "#general",
        (
            "[system] Channel opened for this office site.\n"
            "[ops] Welcome. Drop status here; standups go in the meeting room calendar.\n"
            "[ops] Agents: same rules as humans — leave a trail others can open."
        ),
    )
    w.add_book_page(
        channel,
        "#ops",
        (
            "Operational notes live here.\n"
            "Example: deploy windows, on-call, who holds which cabinet key.\n"
            "Add pages as threads. Keep the log incomplete until the company closes — it shouldn't."
        ),
    )
    w.set_book_incomplete(channel, True)

    calendar_ven = w.create_ven(
        "Shared Calendar",
        "book",
        "Schedules pinned to the room — standups, reviews, ship windows.",
        tags=["schedule", "collab", "book"],
    )
    calendar = w.instantiate(
        calendar_ven,
        name_override="Shared Calendar Board",
        realm_instance_id=r_wire,
        timeline_instance_id=t_day,
    )
    w.put_in(calendar, meeting, slot="interior")
    w.add_book_page(
        calendar,
        "This week",
        (
            "Mon 09:00  Standup (this room)\n"
            "Wed 14:00  Design review — bring folio links\n"
            "Fri 16:00  Ship window / freeze check\n"
            "\n"
            "Edit pages as the week moves. Time is a document you share."
        ),
    )
    w.add_book_page(
        calendar,
        "How to book",
        (
            "1. Open this calendar (book open calendar / folio open …).\n"
            "2. Add a page for the meeting, or extend This week.\n"
            "3. Point colleagues here from the team channel.\n"
            "\n"
            "No separate SaaS required for the first mile — the room holds the schedule."
        ),
    )
    w.set_book_incomplete(calendar, True)

    cabinet_ven = w.create_ven(
        "Project Cabinet",
        "thing",
        "Shared storage unit for dossiers and working files.",
        tags=["storage", "data"],
    )
    cabinet = w.instantiate(
        cabinet_ven,
        name_override="Active Projects Cabinet",
        description_override=(
            "Labeled drawers for work-in-progress. Put instances inside; containment is the API."
        ),
        realm_instance_id=r_wire,
        timeline_instance_id=t_day,
    )
    w.put_in(cabinet, records, slot="interior")

    dossier_ven = w.create_ven(
        "Dossier",
        "thing",
        "A bundle of facts, links, and notes the company may need later.",
        tags=["data", "document"],
    )
    dossier = w.instantiate(
        dossier_ven,
        name_override="Sample Dossier — Office Charter",
        description_override=(
            "Charter stub: this office exists so distributed humans and agents can co-locate work — "
            "data, schedules, and chats — inside navigable space."
        ),
        realm_instance_id=r_wire,
        timeline_instance_id=t_day,
    )
    w.put_in(dossier, cabinet, slot="interior")

    w.add_lore(
        "instance",
        lobby,
        body=(
            "Site online. Operator present. Company offices on the wire are the product — "
            "not a story dungeon that happens to have rooms."
        ),
        title="Site open",
        timeline_instance_id=t_day,
        when_label="Workday",
        author="seed",
    )

    set_meta(conn, "world_name", "Digital Office")
    set_meta(conn, "seed_version", "office-1")
    set_meta(conn, "seed_flavor", "office")


def seed_world_empty(conn: sqlite3.Connection) -> None:
    """
    Empty leased suite: one room, no exits, operator only.

    Build the company layout from inside — still *in* the digital office realm,
    just unfurnished.
    """
    init_schema(conn)
    w = World(conn)

    realm_ven = w.create_ven(
        "Wire",
        "realm",
        "The continuum where digital offices live.",
        tags=["digital", "office"],
    )
    tl_ven = w.create_ven(
        "Workday",
        "timeline",
        "Business time.",
        tags=["office"],
    )
    r_wire = w.instantiate(realm_ven)
    t_day = w.instantiate(tl_ven)

    suite_ven = w.create_ven(
        "Empty Suite",
        "place",
        "Unfurnished office volume on the wire — walls optional, purpose not yet claimed.",
        tags=["office", "empty", "build"],
    )
    suite = w.instantiate(
        suite_ven,
        name_override="Empty Suite",
        description_override=(
            "Bare floor plan. No furniture. No paths yet.\n"
            "The badge still works: you are inside Digital Office Spaces.\n"
            "Dig rooms, spawn desks, leave calendars and channel logs where the company will find them."
        ),
        realm_instance_id=r_wire,
        timeline_instance_id=t_day,
    )

    operator_ven = w.create_ven(
        "Operator",
        "person",
        "You — first badge in an empty suite.",
        tags=["colleague", "user"],
        meta={"subtype": "archetype"},
    )
    operator = w.instantiate(
        operator_ven,
        name_override="You",
        realm_instance_id=r_wire,
        timeline_instance_id=t_day,
    )
    w.put_in(operator, suite, slot="interior")
    w.set_player(operator)

    board_ven = w.create_ven(
        "Whiteboard",
        "thing",
        "Blank surface for plans, maps, and temporary truth.",
        tags=["tool", "planning"],
    )
    board = w.instantiate(
        board_ven,
        name_override="Blank Whiteboard",
        description_override="Nothing written yet. That is the point.",
        realm_instance_id=r_wire,
        timeline_instance_id=t_day,
    )
    w.put_in(board, suite, slot="interior")

    w.add_lore(
        "instance",
        suite,
        body="Empty suite provisioned. Operator may dig the company campus from here.",
        title="Lease start",
        timeline_instance_id=t_day,
        when_label="Workday",
        author="seed",
    )

    set_meta(conn, "world_name", "Empty Suite")
    set_meta(conn, "seed_version", "empty-1")
    set_meta(conn, "seed_flavor", "empty")


def seed_world_bootstrap(conn: sqlite3.Connection) -> None:
    """
    Bare engine start: Base · Start · Place → Herenow · Builder.

    For tests and kernel smoke — not the product welcome experience.
    """
    init_schema(conn)
    w = World(conn)

    realm_ven = w.create_ven(
        "Base",
        "realm",
        "Default dimensional layer.",
    )
    tl_ven = w.create_ven(
        "Start",
        "timeline",
        "Default temporal layer.",
    )
    r_base = w.instantiate(realm_ven)
    t_start = w.instantiate(tl_ven)

    place_ven = w.create_ven(
        "Place",
        "place",
        "A generic place.",
    )
    herenow = w.instantiate(
        place_ven,
        name_override="Herenow",
        description_override="You are here now. The rest is still unwritten.",
        realm_instance_id=r_base,
        timeline_instance_id=t_start,
    )

    builder_ven = w.create_ven(
        "Builder",
        "person",
        "You — the one who makes.",
        meta={"subtype": "archetype"},
    )
    builder = w.instantiate(
        builder_ven,
        realm_instance_id=r_base,
        timeline_instance_id=t_start,
    )
    w.put_in(builder, herenow, slot="interior")
    w.set_player(builder)

    set_meta(conn, "world_name", "Bootstrap")
    set_meta(conn, "seed_version", "bootstrap-3")
    set_meta(conn, "seed_flavor", "bootstrap")


# Alias: empty suite (void was the WBS blank canvas name)
seed_world_void = seed_world_empty
