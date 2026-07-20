"""Seed sample multiverses: story, classic, void, tavern, bootstrap."""

from __future__ import annotations

import sqlite3

from .db import init_schema, set_meta
from .world import World

SEED_FLAVORS = ("story", "classic", "void", "tavern", "bootstrap")


def seed_world(conn: sqlite3.Connection, flavor: str = "story") -> None:
    """Seed a new world. flavor: story | classic | void | tavern | bootstrap."""
    flavor = (flavor or "story").lower().strip()
    if flavor == "classic":
        seed_world_classic(conn)
    elif flavor in ("void", "blank", "empty"):
        seed_world_void(conn)
    elif flavor in ("bootstrap", "bare", "minimal", "nothing"):
        seed_world_bootstrap(conn)
    elif flavor in ("tavern", "wick", "whisper", "lantern"):
        seed_world_tavern(conn)
    else:
        seed_world_story(conn)


def seed_world_classic(conn: sqlite3.Connection) -> None:
    """Original cathedral / mirror / shattered sample."""
    init_schema(conn)
    w = World(conn)

    realm_material = w.create_ven(
        "Material",
        "realm",
        "The dense plane of ordinary physics and stone.",
    )
    realm_archive = w.create_ven(
        "Memory-Archive",
        "realm",
        "A library-dimension where years shelf themselves.",
    )
    tl_prime = w.create_ven(
        "Prime",
        "timeline",
        "The primary linear epoch.",
    )
    tl_shattered = w.create_ven(
        "Shattered",
        "timeline",
        "After the break; echoes misalign.",
    )

    r_mat = w.instantiate(realm_material)
    r_arc = w.instantiate(realm_archive)
    t_prime = w.instantiate(tl_prime)
    t_shat = w.instantiate(tl_shattered)

    cathedral_ven = w.create_ven(
        "The Cathedral of Ordinary Light",
        "place",
        "White stone, dust in sunbeams, a cracked mirror set into the north wall.",
        tags=["sacred", "threshold"],
    )
    nave = w.instantiate(
        cathedral_ven,
        realm_instance_id=r_mat,
        timeline_instance_id=t_prime,
    )

    archive_hall_ven = w.create_ven(
        "Hall of Shelved Years",
        "place",
        "Stacks rise without ceiling. Each shelf hums a different decade.",
        tags=["archive", "time"],
    )
    hall_prime = w.instantiate(
        archive_hall_ven,
        realm_instance_id=r_arc,
        timeline_instance_id=t_prime,
    )
    hall_shattered = w.instantiate(
        archive_hall_ven,
        name_override="Hall of Shelved Years Shattered",
        description_override=(
            "The same stacks, but books bleed into one another. "
            "Some shelves face directions that do not exist in Prime."
        ),
        realm_instance_id=r_arc,
        timeline_instance_id=t_shat,
    )

    cloister_ven = w.create_ven(
        "Moon Cloister",
        "place",
        "An open walk around a dry fountain. Night feels thicker here.",
    )
    cloister = w.instantiate(
        cloister_ven,
        realm_instance_id=r_mat,
        timeline_instance_id=t_prime,
    )

    w.link(nave, cloister, "south", "spatial", bidirectional=True, reverse_label="north")
    w.link(
        nave,
        hall_prime,
        "through the mirror",
        "dimensional",
        bidirectional=True,
        reverse_label="through the returning glass",
    )
    w.link(
        hall_prime,
        hall_shattered,
        "years later",
        "temporal",
        bidirectional=True,
        reverse_label="years earlier",
    )

    silver_ven = w.create_ven(
        "Silver Thread",
        "material",
        "A recurring motif: thin metal light that binds what timelines fray.",
        tags=["motif", "binding"],
        is_prime=True,
    )
    thread = w.instantiate(silver_ven, realm_instance_id=r_mat, timeline_instance_id=t_prime)
    w.put_in(thread, nave, slot="interior")

    ash_ven = w.create_ven(
        "Ash of the First Fire",
        "material",
        "Grey dust that remembers ignition.",
        tags=["motif"],
    )
    ash = w.instantiate(ash_ven, realm_instance_id=r_arc, timeline_instance_id=t_prime)
    w.put_in(ash, hall_prime, slot="interior")

    hush_ven = w.create_ven(
        "Liturgical Hush",
        "feeling",
        "The pressure of unspoken vows.",
    )
    hush = w.instantiate(hush_ven)
    w.put_in(hush, nave, slot="feeling")

    builder_ven = w.create_ven(
        "Builder",
        "person",
        "You — author and walker of this multiverse studio.",
    )
    builder = w.instantiate(
        builder_ven,
        realm_instance_id=r_mat,
        timeline_instance_id=t_prime,
    )
    w.put_in(builder, nave, slot="interior")
    w.set_player(builder)

    archivist_ven = w.create_ven(
        "The Archivist",
        "person",
        "A thin figure who shelves decades like fragile glass.",
    )
    archivist = w.instantiate(
        archivist_ven,
        realm_instance_id=r_arc,
        timeline_instance_id=t_prime,
    )
    w.put_in(archivist, hall_prime, slot="interior")

    patience_ven = w.create_ven("Endless Patience", "feeling", "Time does not hurry them.")
    patience = w.instantiate(patience_ven)
    w.put_in(patience, archivist, slot="feeling")

    w.add_lore(
        "instance",
        nave,
        body="Founded as a simple nave for travelers between markets.",
        title="Founding",
        timeline_instance_id=t_prime,
        when_label="Mythic-Before",
        author="seed",
    )
    w.add_lore(
        "instance",
        nave,
        body="The mirror was set into the north wall after the first dream-leak.",
        title="The Mirror",
        timeline_instance_id=t_prime,
        when_label="Prime Year 12",
        author="seed",
    )
    w.add_lore(
        "instance",
        hall_shattered,
        body="After the break, the Hall refuses a single chronology; shelves argue.",
        title="Post-Shatter state",
        timeline_instance_id=t_shat,
        when_label="Shattered +0",
        author="seed",
    )
    w.add_lore(
        "ven",
        silver_ven,
        body="Silver Thread appears wherever a story risks unraveling across realms.",
        title="Motif note",
        author="seed",
    )

    set_meta(conn, "world_name", "Seed Multiverse")
    set_meta(conn, "seed_version", "classic-1")


def seed_world_story(conn: sqlite3.Connection) -> None:
    """
    Story-center seed: open as builder at the hearth of unfinished maps,
    ancient stories and lovers across time nearby. Shatter exists but is
    several steps away (optional side path).
    """
    init_schema(conn)
    w = World(conn)

    # ── Layers ───────────────────────────────────────────────────────────
    realm_woven = w.create_ven(
        "Woven",
        "realm",
        "The everyday weave where ink dries and maps get folded.",
    )
    realm_story = w.create_ven(
        "Story-Deep",
        "realm",
        "Where told tales keep their own weather and furniture.",
    )
    tl_told = w.create_ven(
        "Told-Time",
        "timeline",
        "The spine of stories as they are still being written.",
    )
    tl_echo = w.create_ven(
        "Echo",
        "timeline",
        "Soft after-images of the same places, slightly out of step.",
    )
    tl_shattered = w.create_ven(
        "Shattered",
        "timeline",
        "After a break far from the hearth; echoes misalign. Optional side path.",
    )

    r_woven = w.instantiate(realm_woven)
    r_story = w.instantiate(realm_story)
    t_told = w.instantiate(tl_told)
    t_echo = w.instantiate(tl_echo)
    t_shat = w.instantiate(tl_shattered)

    # ── Opening: builder hearth ──────────────────────────────────────────
    hearth_ven = w.create_ven(
        "The Hearth of Unfinished Maps",
        "place",
        (
            "A low fire, a table of half-inked coasts, and a chair still warm.\n"
            "You are invited to name what is not yet true. The room smells of paper and cedar."
        ),
        tags=["threshold", "maker", "hearth"],
    )
    hearth = w.instantiate(
        hearth_ven,
        realm_instance_id=r_woven,
        timeline_instance_id=t_told,
    )

    gallery_ven = w.create_ven(
        "Gallery of First Names",
        "place",
        "Soft light on plaques that have not finished deciding who they are for.",
        tags=["maker", "names"],
    )
    gallery = w.instantiate(
        gallery_ven,
        realm_instance_id=r_woven,
        timeline_instance_id=t_told,
    )

    # ── Ancient stories ──────────────────────────────────────────────────
    hall_ven = w.create_ven(
        "Hall of Stories Still Being Told",
        "place",
        (
            "Shelves hold voices, not only volumes. Some pages turn themselves "
            "when you pass, as if remembering an audience."
        ),
        tags=["archive", "story", "ancient"],
    )
    hall = w.instantiate(
        hall_ven,
        realm_instance_id=r_story,
        timeline_instance_id=t_told,
    )

    # ── Lovers across time ───────────────────────────────────────────────
    overlook_ven = w.create_ven(
        "Twin Overlook",
        "place",
        (
            "Two stone benches face the same empty road from slightly different years. "
            "A shared silence sits between them like a third person."
        ),
        tags=["lovers", "threshold"],
    )
    overlook = w.instantiate(
        overlook_ven,
        realm_instance_id=r_woven,
        timeline_instance_id=t_told,
    )

    overlook_echo = w.instantiate(
        overlook_ven,
        name_override="Twin Overlook Echo",
        description_override=(
            "The same benches, softer edges. One cup is still warm. "
            "The road below holds footprints that arrive out of order."
        ),
        realm_instance_id=r_woven,
        timeline_instance_id=t_echo,
    )

    # ── Far shatter (optional, not on the opening tour) ──────────────────
    far_ven = w.create_ven(
        "Far Archive of Broken Shelves",
        "place",
        (
            "A wing of the story-deep that remembers a harder ending. "
            "Books lean into each other as if bracing for weather."
        ),
        tags=["archive", "shatter", "side-path"],
    )
    far_archive = w.instantiate(
        far_ven,
        realm_instance_id=r_story,
        timeline_instance_id=t_told,
    )
    far_shattered = w.instantiate(
        far_ven,
        name_override="Far Archive Shattered",
        description_override=(
            "Shelves argue. Decades spill. This is a possible ending, not the only one."
        ),
        realm_instance_id=r_story,
        timeline_instance_id=t_shat,
    )

    # Links: hearth → gallery / hall / overlook; hall → far; overlook temporal; far temporal
    w.link(hearth, gallery, "east", "spatial", bidirectional=True, reverse_label="west")
    w.link(
        hearth,
        hall,
        "into the living shelves",
        "dimensional",
        bidirectional=True,
        reverse_label="back to the hearth",
    )
    w.link(
        hearth,
        overlook,
        "along the story road",
        "narrative",
        bidirectional=True,
        reverse_label="back toward unfinished maps",
    )
    w.link(
        overlook,
        overlook_echo,
        "a generation later",
        "temporal",
        bidirectional=True,
        reverse_label="a generation earlier",
    )
    w.link(
        hall,
        far_archive,
        "deeper into the side wing",
        "spatial",
        bidirectional=True,
        reverse_label="toward the main hall",
    )
    w.link(
        far_archive,
        far_shattered,
        "years after the break",
        "temporal",
        bidirectional=True,
        reverse_label="years before the break",
    )

    # ── Motifs / objects ─────────────────────────────────────────────────
    quill_ven = w.create_ven(
        "Unfinished Quill",
        "material",
        "Still wet enough to write a first true sentence.",
        tags=["motif", "maker"],
    )
    quill = w.instantiate(quill_ven, realm_instance_id=r_woven, timeline_instance_id=t_told)
    w.put_in(quill, hearth, slot="interior")

    letter_ven = w.create_ven(
        "Half-Written Letter",
        "material",
        "Addressed to someone who answers from another century.",
        tags=["motif", "lovers"],
    )
    letter = w.instantiate(letter_ven, realm_instance_id=r_woven, timeline_instance_id=t_told)
    w.put_in(letter, overlook, slot="interior")

    coin_ven = w.create_ven(
        "Coin Warm on Both Sides",
        "material",
        "It never cools completely; each face remembers a different hand.",
        tags=["motif", "lovers"],
    )
    coin = w.instantiate(coin_ven, realm_instance_id=r_woven, timeline_instance_id=t_echo)
    w.put_in(coin, overlook_echo, slot="interior")

    # ── Feelings ─────────────────────────────────────────────────────────
    invitation_ven = w.create_ven(
        "Quiet Invitation",
        "feeling",
        "The room waits without urgency.",
    )
    invitation = w.instantiate(invitation_ven)
    w.put_in(invitation, hearth, slot="feeling")

    # ── Characters ───────────────────────────────────────────────────────
    builder_ven = w.create_ven(
        "Builder",
        "person",
        "You — author walking the spine of a story still willing to change.",
    )
    builder = w.instantiate(
        builder_ven,
        realm_instance_id=r_woven,
        timeline_instance_id=t_told,
    )
    w.put_in(builder, hearth, slot="interior")
    w.set_player(builder)

    lover_a_ven = w.create_ven(
        "The Cartographer of Returns",
        "person",
        "Maps roads that only exist when someone is missed enough.",
    )
    lover_a = w.instantiate(
        lover_a_ven,
        realm_instance_id=r_woven,
        timeline_instance_id=t_told,
    )
    w.put_in(lover_a, overlook, slot="interior")

    lover_b_ven = w.create_ven(
        "The Keeper of Unsent Replies",
        "person",
        "Answers arrive late and still exactly on time.",
    )
    lover_b = w.instantiate(
        lover_b_ven,
        realm_instance_id=r_woven,
        timeline_instance_id=t_echo,
    )
    w.put_in(lover_b, overlook_echo, slot="interior")

    longing_ven = w.create_ven(
        "Patient Longing",
        "feeling",
        "Distance is a kind of loyalty.",
    )
    longing = w.instantiate(longing_ven)
    w.put_in(longing, lover_a, slot="feeling")

    # Archetype on the cartographer — inner life visible in who/examine
    mapper_arch_ven = w.create_ven(
        "The Road-Mapper",
        "archetype",
        "One who charts what has not yet been walked.",
    )
    mapper_arch = w.instantiate(mapper_arch_ven)
    w.put_in(mapper_arch, lover_a, slot="archetype")

    storyteller_ven = w.create_ven(
        "The Storyteller",
        "person",
        "An old voice that treats every shelf as a guest room.",
    )
    storyteller = w.instantiate(
        storyteller_ven,
        realm_instance_id=r_story,
        timeline_instance_id=t_told,
    )
    w.put_in(storyteller, hall, slot="interior")

    # ── Lore ─────────────────────────────────────────────────────────────
    w.add_lore(
        "instance",
        hearth,
        body="Raised where builders rest between namings. No finished map hangs here on purpose.",
        title="First Naming",
        timeline_instance_id=t_told,
        when_label="Before the Roads Had Numbers",
        author="seed",
    )
    w.add_lore(
        "instance",
        hall,
        body="The oldest stories are still being revised by people who love them.",
        title="Living Canon",
        timeline_instance_id=t_told,
        when_label="Ancient Continuance",
        author="seed",
    )
    w.add_lore(
        "instance",
        overlook,
        body=(
            "Two lovers keep missing and finding each other across Told-Time and Echo. "
            "Their story is a road, not a wound."
        ),
        title="Across the Road",
        timeline_instance_id=t_told,
        when_label="Told-Time",
        author="seed",
    )
    w.add_lore(
        "ven",
        letter_ven,
        body="The letter is never fully sent; that is how it stays true in both centuries.",
        title="Motif note",
        author="seed",
    )
    w.add_lore(
        "instance",
        far_shattered,
        body="A possible hard ending lives here, far from the hearth. Optional to visit.",
        title="Side Path · After the Break",
        timeline_instance_id=t_shat,
        when_label="Shattered +0",
        author="seed",
    )

    set_meta(conn, "world_name", "Story Spine")
    set_meta(conn, "seed_version", "story-1")


def seed_world_void(conn: sqlite3.Connection) -> None:
    """
    Minimal canvas: one void place, no exits, no NPCs, no tour graph.

    Only a builder avatar and one strange romantic book — build from nothing.
    """
    init_schema(conn)
    w = World(conn)

    # Minimal layers (engine needs realm/timeline to situate instances)
    realm_void = w.create_ven(
        "Unformed",
        "realm",
        "Not yet a dimension — only the idea that somewhere could be.",
    )
    tl_first = w.create_ven(
        "First Breath",
        "timeline",
        "Before clocks. Before roads. The moment after nothing.",
    )
    r_void = w.instantiate(realm_void)
    t_first = w.instantiate(tl_first)

    void_ven = w.create_ven(
        "The Void",
        "place",
        (
            "No walls. No weather. A soft dark that does not press.\n"
            "You are the first footprint that has not yet been set.\n"
            "Somewhere near your hand, a book waits as if it has always been waiting."
        ),
        tags=["void", "blank", "threshold"],
    )
    void = w.instantiate(
        void_ven,
        realm_instance_id=r_void,
        timeline_instance_id=t_first,
    )

    builder_ven = w.create_ven(
        "Builder",
        "person",
        "You — author at the edge of an unwritten world.",
    )
    builder = w.instantiate(
        builder_ven,
        realm_instance_id=r_void,
        timeline_instance_id=t_first,
    )
    w.put_in(builder, void, slot="interior")
    w.set_player(builder)

    book_ven = w.create_ven(
        "A Book That Loves You Backwards",
        "book",
        (
            "Its cover is the color of a letter never sent. "
            "The spine hums when you are lonely. "
            "It is not a manual — it is a flirtation with the dark."
        ),
        tags=["book", "romance", "strange"],
    )
    book = w.instantiate(
        book_ven,
        name_override="A Book That Loves You Backwards",
        realm_instance_id=r_void,
        timeline_instance_id=t_first,
    )
    w.put_in(book, void, slot="interior")

    # Strange, romantic pages — invitation to build, not a finished tour
    w.add_book_page(
        book,
        "Invocation",
        (
            "Beloved stranger of the first dark—\n"
            "there is no map yet because maps are a kind of leaving.\n"
            "Stay. Touch the nothing until it blushes into a room.\n"
            "I will keep your name warm between these pages\n"
            "even before you have chosen one."
        ),
    )
    w.add_book_page(
        book,
        "How Worlds Begin",
        (
            "They say creation is a shout.\n"
            "Here it is a kiss withheld: almost, almost, almost—\n"
            "until the almost becomes a doorway you dig with dig,\n"
            "and a light you name with @desc,\n"
            "and a someone who was not here until you said spawn.\n"
            "\n"
            "I am only paper. You are the weather.\n"
            "Open me when the void feels too honest.\n"
            "Close me when you have made a home worth missing."
        ),
    )
    # Leave incomplete so status reads as unfinished romance, not a closed canon
    w.set_book_incomplete(book, True)

    w.add_lore(
        "instance",
        void,
        body=(
            "This place was not prepared for you. That is the gift. "
            "The book is the only other witness."
        ),
        title="Before Cartography",
        timeline_instance_id=t_first,
        when_label="First Breath",
        author="seed",
    )

    set_meta(conn, "world_name", "The Void")
    set_meta(conn, "seed_version", "void-1")


def seed_world_bootstrap(conn: sqlite3.Connection) -> None:
    """
    Bare start: Base · Start · Place → Herenow · Builder (person/archetype).

    No props, no paths — dig your own ditch.
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


def seed_world_tavern(conn: sqlite3.Connection) -> None:
    """
    Mystic tavern latch: start at last call in The Wick & Whisper.

    Primes are *kinds* (Landing, Key, Door, Ledger…); flavor lives on instances
    (Unnumbered Landing, Key to Rooms Not Yet Built…). Incomplete folios + a
    locked suite door teach portal/key without flooding the VEN root.
    """
    init_schema(conn)
    w = World(conn)

    # ── Layers ───────────────────────────────────────────────────────────
    realm_wick = w.create_ven(
        "Candlelit",
        "realm",
        "Wherever a lamp is left low enough that secrets can pull up a chair.",
    )
    tl_last = w.create_ven(
        "Last Call",
        "timeline",
        "The hour that stretches. Closing never quite arrives.",
    )
    r_wick = w.instantiate(realm_wick)
    t_last = w.instantiate(tl_last)

    def _here(
        ven_id: str,
        *,
        name: str | None = None,
        desc: str | None = None,
    ) -> str:
        return w.instantiate(
            ven_id,
            name_override=name,
            description_override=desc,
            realm_instance_id=r_wick,
            timeline_instance_id=t_last,
        )

    # ── Place primes (kinds) → named rooms ───────────────────────────────
    room_ven = w.create_ven(
        "Tavern Room",
        "place",
        "A room that holds smoke, coin, and unfinished sentences.",
        tags=["tavern", "room"],
        meta={"subtype": "room"},
    )
    booth_ven = w.create_ven(
        "Booth",
        "place",
        "A private alcove; curtains optional, secrets less so.",
        tags=["tavern", "booth"],
        meta={"subtype": "booth"},
    )
    landing_ven = w.create_ven(
        "Landing",
        "place",
        "A stair end. Doors may or may not have decided to exist yet.",
        tags=["tavern", "landing"],
        meta={"subtype": "landing"},
    )
    cellar_ven = w.create_ven(
        "Cellar",
        "place",
        "Cool stone under a house that remembers pours.",
        tags=["tavern", "cellar"],
        meta={"subtype": "cellar"},
    )
    suite_ven = w.create_ven(
        "Suite",
        "place",
        "A room that opens only when someone means it.",
        tags=["tavern", "suite", "portal-dest"],
        meta={"subtype": "room"},
    )

    common = _here(
        room_ven,
        name="The Wick & Whisper",
        desc=(
            "Smoke and orange light. A long bar wears water-rings like years.\n"
            "Someone has left a guest ledger open to a blank line with your elbow on it.\n"
            "The room does not ask where you came from — only what you still owe the story."
        ),
    )
    booth = _here(
        booth_ven,
        name="The Quiet Booth",
        desc=(
            "Curtain half-drawn. One candle, two cups, and a folio open mid-sentence\n"
            "as if the author only stood up for more wine."
        ),
    )
    landing = _here(
        landing_ven,
        name="Unnumbered Landing",
        desc=(
            "A short stair ends in doors without numbers.\n"
            "Brass plates wait blank. The house says rooms appear when chapters do."
        ),
    )
    cellar = _here(
        cellar_ven,
        name="Cellar of Unfinished Toasts",
        desc=(
            "Cool stone. Bottles labeled with years that never finished bottling.\n"
            "Dust tastes like applause that never quite started."
        ),
    )
    soft_suite = _here(
        suite_ven,
        name="Soft Suite",
        desc=(
            "Lamp low. One window that faces a weather the street does not have.\n"
            "The bed is made as if someone might stay long enough to finish a chapter."
        ),
    )

    # Links from the common room (paths — not portals)
    w.link(
        common,
        booth,
        "into the quiet booth",
        "spatial",
        bidirectional=True,
        reverse_label="back to the common room",
    )
    w.link(
        common,
        landing,
        "up the unnumbered stairs",
        "spatial",
        bidirectional=True,
        reverse_label="down to the common room",
    )
    w.link(
        common,
        cellar,
        "down the rumor stair",
        "spatial",
        bidirectional=True,
        reverse_label="up into the light",
    )

    # ── Thing primes → named props ───────────────────────────────────────
    candle_ven = w.create_ven(
        "Candle",
        "thing",
        "Wax and wick; burns at the pace of the room.",
        tags=["prop", "light"],
    )
    key_ven = w.create_ven(
        "Key",
        "thing",
        "Teeth and silence. Each copy only opens what it was locked to.",
        tags=["prop", "key"],
        meta={"subtype": "key"},
    )
    bottle_ven = w.create_ven(
        "Bottle",
        "thing",
        "Glass that keeps a secret better than most people.",
        tags=["prop", "drink"],
    )
    door_ven = w.create_ven(
        "Door",
        "thing",
        "A portal token: not a path, a room that waits behind open/unlock.",
        tags=["prop", "door", "portal"],
        meta={"subtype": "door"},
    )

    candle = _here(
        candle_ven,
        name="Candle of Shared Endings",
        desc="Burns slower when someone nearby is mid-chapter.",
    )
    w.put_in(candle, common, slot="interior")

    suite_key = _here(
        key_ven,
        name="Key to Rooms Not Yet Built",
        desc=(
            "Cold brass. Fits the Brass Door on the landing — "
            "and only that copy, not every Key in the house."
        ),
    )
    w.put_in(suite_key, landing, slot="interior")

    bottle = _here(
        bottle_ven,
        name="Bottle of the Unsaid",
        desc="Sealed with wax the color of a withheld apology. Do not open sober.",
    )
    w.put_in(bottle, cellar, slot="interior")

    brass_door = _here(
        door_ven,
        name="Brass Door",
        desc=(
            "No number on the plate. The metal is warm, as if a room behind it "
            "has already decided you might come in — if you have the right key."
        ),
    )
    w.put_in(brass_door, landing, slot="interior")
    w.set_portal_to(brass_door, soft_suite)
    w.set_portal_key_instance_id(brass_door, suite_key)
    w.set_portal_locked(brass_door, True)
    w.set_portal_lock_deny(
        brass_door,
        "The plate stays blank. Somewhere a key is laughing quietly on the floor.",
    )

    # ── Sense primes → mood copies ───────────────────────────────────────
    mood_ven = w.create_ven(
        "Mood",
        "sense",
        "Weather that lives on people and rooms.",
        tags=["sense"],
    )
    hush = w.instantiate(
        mood_ven,
        name_override="Almost Last Call",
        description_override="The night is leaning in. One more page would not hurt.",
    )
    w.put_in(hush, common, slot="feeling")

    tease = w.instantiate(
        mood_ven,
        name_override="Teasing Omniscience",
        description_override=(
            "She has read the ending. She will not spoil it. She might refill your cup."
        ),
    )

    # ── Person primes → named people ─────────────────────────────────────
    builder_ven = w.create_ven(
        "Builder",
        "person",
        "The one who makes — ink under the nails, story half paid for.",
        tags=["player"],
    )
    builder = _here(
        builder_ven,
        name="Builder",
        desc="You — ink under the nails, coin still warm from the road, a story half paid for.",
    )
    w.put_in(builder, common, slot="interior")
    w.set_player(builder)

    innkeep_ven = w.create_ven(
        "Innkeep",
        "person",
        "Keeps the pours and the unfinished guests.",
        tags=["tavern", "keeper"],
    )
    innkeep = _here(
        innkeep_ven,
        name="Mirelle of the Last Pour",
        desc=(
            "Innkeep. Knows who left mid-sentence and who still owes a chapter.\n"
            "Smiles like a spoiler she will not say."
        ),
    )
    w.put_in(innkeep, common, slot="interior")
    w.put_in(tease, innkeep, slot="feeling")

    regular_ven = w.create_ven(
        "Regular",
        "person",
        "Always here. Rarely speaks. Finishes other people's silences.",
        tags=["tavern"],
    )
    regular = _here(
        regular_ven,
        name="The Regular Who Never Speaks",
        desc="Empty glass. Full attention. Has been finishing other people's silences for years.",
    )
    w.put_in(regular, booth, slot="interior")

    # ── Folio primes → named books ───────────────────────────────────────
    ledger_ven = w.create_ven(
        "Ledger",
        "folio",
        "A book that keeps accounts of people and pages.",
        tags=["folio", "ledger"],
    )
    ledger = _here(
        ledger_ven,
        name="Guest Ledger of the Wick & Whisper",
        desc=(
            "Bound in something that once was a coat. "
            "Names arrive in different hands. Many lines end in dash —"
        ),
    )
    w.put_in(ledger, common, slot="interior")
    w.add_book_page(
        ledger,
        "House Rules for the Unfinished",
        (
            "1. Pay in coin or in pages — the house accepts both.\n"
            "2. Do not close a book that is still breathing.\n"
            "3. If you leave mid-chapter, leave the key on the ledger.\n"
            "4. Mirelle already knows. Write anyway.\n"
            "\n"
            "— posted above the bar, rewritten whenever the ink fades"
        ),
    )
    w.add_book_page(
        ledger,
        "Tonight's Blank Lines",
        (
            "Guest: _______________\n"
            "Came from: _______________\n"
            "Owes the house: _______________\n"
            "First true sentence of the night:\n"
            "\n"
            "    _______________________________________________\n"
            "\n"
            "(Mirelle's hand in the margin: fill this or the stairs stay unnumbered.)\n"
            "\n"
            "Tip: folio page add ledger <title> <<studio\n"
            "Prime/instance: create thing/key Key · spawn key as Your Key Name"
        ),
    )
    w.set_book_incomplete(ledger, True)

    manuscript_ven = w.create_ven(
        "Manuscript",
        "folio",
        "A thin book mid-story; endings optional.",
        tags=["folio", "romance"],
    )
    chapter = _here(
        manuscript_ven,
        name="Chapter Left on the Table",
        desc=(
            "A slim romance someone abandoned between pours. "
            "The spine still warm. The ending is a dare."
        ),
    )
    w.put_in(chapter, booth, slot="interior")
    w.add_book_page(
        chapter,
        "I. The Door That Knew Your Name",
        (
            "They said the Wick & Whisper only appears to people who have a sentence left in them.\n"
            "You laughed — and then the door was there, lamp low, as if it had always been waiting\n"
            "with your coat already on the hook.\n"
            "\n"
            "Inside: orange light, a ledger open to a blank, and a woman behind the bar who looked\n"
            "at you the way a last page looks at a hand that might still write.\n"
            "\n"
            "\"Stay,\" she said, which was not an order.\n"
            "\"Or go upstairs. The rooms are shy until someone finishes them.\""
        ),
    )
    w.add_book_page(
        chapter,
        "II. (unwritten — your turn)",
        (
            "The next leaf is pale on purpose.\n"
            "\n"
            "Whoever sat here last wrote only this in the gutter:\n"
            "    if you love them, give them a room with a window\n"
            "    if you fear them, give them a cellar\n"
            "    if you are them — write\n"
            "\n"
            "folio page edit chapter 2 <<studio\n"
            "— or add leaf 3 and refuse to explain yourself"
        ),
    )
    w.set_book_incomplete(chapter, True)

    # ── Lore (on lived rooms, not only primes) ───────────────────────────
    w.add_lore(
        "instance",
        common,
        body=(
            "Raised on a crossroads that only exists at last call. "
            "Travelers who cannot finish a story find the door first."
        ),
        title="Where the Wick Was Lit",
        timeline_instance_id=t_last,
        when_label="Before the Numbers",
        author="seed",
    )
    w.add_lore(
        "instance",
        landing,
        body=(
            "Brass plates stay blank until a folio page is true enough to hang a number on. "
            "The Brass Door is a portal (not a path): unlock with the key on the floor, then open. "
            "Or dig your own suite and spawn another Door + Key pair."
        ),
        title="Unnumbered on Purpose",
        timeline_instance_id=t_last,
        when_label="Last Call",
        author="seed",
    )
    w.add_lore(
        "ven",
        ledger_ven,
        body=(
            "Ledger is the kind; Guest Ledger of the Wick & Whisper is tonight's copy. "
            "Add pages. The stairs notice."
        ),
        title="Motif · Debt of Pages",
        author="seed",
    )
    w.add_lore(
        "instance",
        booth,
        body=(
            "Lovers, rivals, and cowards all pick the same booth. "
            "The Regular never speaks; the manuscript does."
        ),
        title="Why the Curtain Stays Half-Drawn",
        timeline_instance_id=t_last,
        when_label="Last Call",
        author="seed",
    )
    w.add_lore(
        "instance",
        brass_door,
        body=(
            "Portal → Soft Suite. Locked to Key to Rooms Not Yet Built (this copy only). "
            "Sibling Keys from prime Key will not open it."
        ),
        title="How the Brass Door Works",
        timeline_instance_id=t_last,
        when_label="Last Call",
        author="seed",
    )

    set_meta(conn, "world_name", "Wick & Whisper")
    set_meta(conn, "seed_version", "tavern-2")
