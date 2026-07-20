"""Topic-based help: short index + per-term detail pages."""

from __future__ import annotations

import re

from . import format as fmt
from .world import KINDS

# Canonical term -> aliases (first is primary index label)
_TOPIC_ALIASES: dict[str, tuple[str, ...]] = {
    "look": ("look", "l"),
    "go": ("go", "g"),
    "run": ("run", "activate", "use", "enter", "open"),
    "lock": ("lock", "unlock"),
    "logout": ("logout", "logoff", "log-out"),
    "portal": ("portal",),
    "locate": ("locate", "status", "sit", "situation", "whereami", "where"),
    "exits": ("exits", "x", "paths", "path", "ways", "waypoints", "way"),
    "map": ("map", "graph"),
    "inv": ("inv", "inventory", "i"),
    "take": ("take", "get"),
    "drop": ("drop",),
    "examine": ("examine", "exam", "inspect", "in"),
    "wiki": ("wiki",),
    "who": ("who",),
    "talk": ("talk",),
    "dialogs": ("dialogs", "dialog"),
    "book": ("book", "read", "folio"),
    "record": ("record", "records", "lore"),
    "dig": ("dig",),
    "link": ("link", "unlink", "delink"),
    "@desc": ("@desc", "desc"),
    "studio-text": ("studio-text", "studio", "studio text", "markup"),
    "create": ("create", "/c"),
    "spawn": ("spawn", "/s"),
    "rename": ("rename", "call"),
    "instances": ("instances", "inst"),
    "history": ("history", "hist"),
    "retime": ("retime", "retimes", "when-set"),
    "put": ("put", "install"),
    "despawn": ("despawn", "lose", "reclaim", "lost"),
    "elevate": ("elevate",),
    "vens": ("vens", "ven", "export", "collector"),
    "lineage": ("lineage", "ancestry"),
    "compose": ("compose", "composition", "parts"),
    "kinds": ("kinds", "kind"),
    "timeline": ("timeline", "timelines", "tl"),
    "realm": ("realm", "realms"),
    "undo": ("undo", "u"),
    "text": ("text", "textlog", "revisions"),
    "clear": ("clear", "clr"),
    "cls": ("cls", "refresh", "ref", "blink"),
    "help": ("help", "?"),
    "quit": ("quit", "exit", "q"),
    "concepts": ("concepts", "ven", "vens-model", "model"),
}


def resolve_topic(term: str) -> str | None:
    """Map user term to canonical topic key, or None if unknown."""
    t = term.strip().lower()
    if not t:
        return None
    if t in _TOPIC_ALIASES:
        return t
    for canon, aliases in _TOPIC_ALIASES.items():
        if t in aliases or t == canon:
            return canon
    # partial unique match on canon names
    hits = [c for c in _TOPIC_ALIASES if t in c or c.startswith(t)]
    if len(hits) == 1:
        return hits[0]
    return None


# Grouped index: related actions share a category number; items use letter codes
# (e.g. look → 11). Adding topics: place them under the matching category.
# Category titles are ALL CAPS on the cheat sheet; labels here stay short.
_HELP_INDEX_CATEGORIES: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "MOVEMENT",
        [
            ("look", "Describe the place you are in"),
            ("go", "Travel a path by label"),
            ("run", "Portal travel (open/enter/run; unlock if locked)"),
            ("logout", "Leave a run session → where you entered from"),
            ("locate", "Where your avatar is (locate self); later: codes"),
            ("paths", "List paths from here (aliases: exits, ways, x)"),
            ("map", "Local multiverse map (path tree)"),
        ],
    ),
    (
        "ENV CONTROLS",
        [
            ("inv", "What you carry"),
            ("take / drop", "Pick up, take from <box>, or drop"),
            ("examine", "Detail a thing (aliases: exam, inspect, in)"),
            ("put", "Into box, person, or nearby room (alias: install)"),
            ("portal", "Bind thing → place world for run"),
            ("lock", "Lock / unlock portal doors (optional keys)"),
        ],
    ),
    (
        "COMMUNICATION",
        [
            ("who", "People present"),
            ("talk", "Dialog with a person until /fin"),
            ("dialogs", "Dialogs here; dialogs all for every place"),
        ],
    ),
    (
        "RECORDS",
        [
            ("wiki", "VEN/instance dossier (notes=records, sub-links)"),
            ("folio", "Folio open/read · leaves · soft TUI reader (book)"),
            ("record", "Place records; record ven … for prime records"),
        ],
    ),
    (
        "BUILD CONTROLS",
        [
            ("dig", "Create a place [realm …] [timeline …]"),
            ("link", "Connect / rename / unlink paths between places"),
            ("@desc", "Place or instance description (@desc on <item>)"),
            ("studio-text", "Opt-in markup for desc / records (bold, rules, fences)"),
            ("text", "Editor save history (text log / show / restore)"),
        ],
    ),
    (
        "CREATOR TOOLS",
        [
            ("create", "Prime VEN · roots + kind/subtype (/c)"),
            ("spawn", "Instance a VEN; prefer: spawn x as Title (/s)"),
            ("rename", "Retitle thing or place: rename here as …"),
            ("instances", "List all copies of a prime VEN"),
            ("history", "Story when @N / @unknown · life of item"),
            ("retime", "Fix story when on an HST event (all legs)"),
            ("despawn", "Lose instance to Lost Dept · reclaim · lost"),
            ("elevate", "Instance → new prime (rebind + parent lineage)"),
        ],
    ),
    (
        "MANAGEMENT TOOLS",
        [
            ("vens", "List primes · export/load collector packs"),
            ("lineage", "Specialization path root › … › ven"),
            ("compose", "Prime-level parts (symbol / archetype / …)"),
            ("kinds", "Lean roots · person place bin thing folio sense event…"),
            ("concepts", "VEN model: codes, lineage, composition, instances"),
        ],
    ),
    (
        "LAYERS",
        [
            ("timeline", "List / create / assign timelines"),
            ("realm", "List / create / assign realms"),
        ],
    ),
    (
        "SESSION",
        [
            ("undo", "Undo last builder action"),
            ("clear", "Clear the log (go also clears after a move)"),
            ("cls", "Clear the log and look (refresh / blink)"),
            ("help", "Cheat sheet · 1–9 section · 11 topic · all catalog"),
            ("quit", "Leave the studio"),
        ],
    ),
]


def _index_letter(i: int) -> str:
    """Legacy letter suffix (0 → a); prefer :func:`topic_code` digits for nav."""
    if i < 0:
        i = 0
    chars: list[str] = []
    n = i
    while True:
        chars.append(chr(ord("a") + (n % 26)))
        n = n // 26 - 1
        if n < 0:
            break
    return "".join(reversed(chars))


def topic_code(cat_i: int, item_i: int) -> str:
    """
    Fast numpad code: section digit + 1-based item digit.

    look → ``11``, go → ``12``, first ENV item → ``21``.
    (Sections have ≤9 items today; item 10+ would need a longer scheme.)
    """
    return f"{cat_i}{item_i + 1}"


def topic_index_entries() -> list[tuple[str, str, str, str]]:
    """(code, term, summary, category_title) for the grouped help index.

    Codes are pure digits for rapid typing: category + item
    (e.g. look → ``11``). Letter forms ``1a`` still resolve as aliases.
    """
    out: list[tuple[str, str, str, str]] = []
    for cat_i, (cat_title, items) in enumerate(_HELP_INDEX_CATEGORIES, start=1):
        for item_i, (term, summary) in enumerate(items):
            code = topic_code(cat_i, item_i)
            out.append((code, term, summary, cat_title))
    return out


def topic_index_terms() -> list[tuple[str, str]]:
    """(term, one-line summary) for the short help list (category order)."""
    return [(term, summary) for _code, term, summary, _cat in topic_index_entries()]


def _topic_key_for_index_label(term: str) -> str | None:
    """Map an index label like 'take / drop' to a canonical help topic key."""
    import re

    for part in re.split(r"[/,]", term):
        key = resolve_topic(part.strip())
        if key:
            return key
    return resolve_topic(term)


def resolve_index_code(code: str) -> str | None:
    """
    Map an index code to a canonical topic key.

    Accepts:
      - digit codes ``11``, ``21`` (primary)
      - legacy letter codes ``1a``, ``2b``
    """
    raw = (code or "").strip().lower()
    if not raw:
        return None
    # Primary: exact match on digit codes
    for c, term, _summary, _cat in topic_index_entries():
        if c.lower() == raw:
            return _topic_key_for_index_label(term)
    # Legacy letter form: 1a → section 1, item 0
    m = re.fullmatch(r"(\d+)([a-z]+)", raw)
    if m:
        cat_i = int(m.group(1))
        letters = m.group(2)
        # single letter a–z only for legacy
        if len(letters) == 1 and "a" <= letters <= "z":
            item_i = ord(letters) - ord("a")
            if 1 <= cat_i <= len(_HELP_INDEX_CATEGORIES):
                items = _HELP_INDEX_CATEGORIES[cat_i - 1][1]
                if 0 <= item_i < len(items):
                    return _topic_key_for_index_label(items[item_i][0])
    return None


def render_help_index() -> str:
    """Default help: compact cheat sheet (same idea as TUI pane)."""
    from .help_ui import render_cheat_sheet

    return render_cheat_sheet()


def render_help_topic(term: str) -> str:
    """Detail page for a term, or unknown-term message."""
    key = resolve_topic(term)
    if key is None:
        # Alphanumeric index codes (1A, 2B, …)
        key = resolve_index_code(term)
    if key is None:
        return fmt.join_blocks(
            fmt.err(f"Unknown help term {term!r}."),
            fmt.hint("Type help for the index of terms."),
            gap=0,
        )
    body = _TOPICS.get(key)
    if body is None:
        return fmt.err(f"No page for {key!r}.")
    kinds = ", ".join(KINDS)
    text = body if "{kinds}" not in body else body.replace("{kinds}", kinds)
    return text


def _page(title: str, *blocks: str) -> str:
    return fmt.join_blocks(fmt.title_line(f"help · {title}"), *blocks, gap=1)


def _p(*paragraphs: str) -> str:
    return fmt.prose_block(*paragraphs)


# Static topic bodies (Rich markup; examples via example_line)
_TOPICS: dict[str, str] = {}


def _init_topics() -> None:
    global _TOPICS
    if _TOPICS:
        return
    _TOPICS = {
        "look": _page(
            "look",
            _p(
                "Show the current place: location line, description, paths, "
                "and presence by *placement* (not kind). "
                "Loose items land under Here; each bin VEN is its own bucket "
                "with shallow (first-level) kids — empty bins still show. "
                "With --deep: one more layer inside those bins + full place records. "
                "With a target, same as examine — English glue works: "
                "look at door, look in drawer, look on table, look inside pack."
            ),
            fmt.section("Usage"),
            fmt.example_line("look", "Room + Here + bin buckets"),
            fmt.example_line(
                "look --deep",
                "Bins open one layer deeper + full place records",
            ),
            fmt.example_line("look deep", "Same (trailing deep)"),
            fmt.example_line("look at brass-door", "Examine (also: look door)"),
            fmt.example_line(
                "look in drawer",
                "Same as examine drawer / in drawer",
            ),
            fmt.example_line(
                "look on table",
                "Same as examine table",
            ),
            fmt.example_line(
                "look --deep at table",
                "Examine target with full records",
            ),
            fmt.example_line("l", "Short alias"),
            fmt.hint(
                "Prepositions: at · in · into · inside · on · onto · under · within · through."
            ),
            fmt.hint(
                "put titles in Q3 (bin); look lists them under Q3, not a Things bucket."
            ),
            fmt.hint("paths alone reprints the list; go <label> to travel."),
        ),
        "go": _page(
            "go",
            _p(
                "Move along a path (place→place link). Labels need not be compass directions. "
                "Partial labels work when unique. Inventory travels with you."
            ),
            fmt.section("Usage"),
            fmt.example_line("go south"),
            fmt.example_line("go through the mirror", "Dimensional path in the seed world"),
            fmt.example_line("g mirror", "Short form + partial match"),
            fmt.hint("App worlds use run, not go — portals never appear under paths."),
        ),
        "run": _page(
            "run",
            _p(
                "Travel into a real place through a portal-bound object — never a paths entry. "
                "Aliases: activate, use, enter. open also enters a portal when the name matches "
                "(otherwise folio read). unlock is separate — it only clears a lock (keys). "
                "Two patterns: (1) apps/games — only after put/install in a box or "
                "device (not from the floor); (2) door shells (thing/door, hatch…) — "
                "open from the floor when unlocked. logout returns."
            ),
            fmt.section("Usage"),
            fmt.example_line(
                "run mail from terminal",
                "App installed in a device",
            ),
            fmt.example_line(
                "put kcd in pillow-box  ·  run kcd",
                "Game only works when installed",
            ),
            fmt.example_line(
                "open brass-door",
                "Floor door shell (subtype door)",
            ),
            fmt.example_line(
                "enter hatch · activate mail · use kat",
                "Same travel family",
            ),
            fmt.section("Setup · locked door + key"),
            fmt.example_line("dig place/room Soft Suite | Soft lamp."),
            fmt.example_line("create thing/door Brass Door | Plate waits."),
            fmt.example_line("create thing/key Key | Blank teeth."),
            fmt.example_line("spawn key as Suite Key  ·  spawn brass-door"),
            fmt.example_line("portal brass-door -> Soft Suite"),
            fmt.example_line("lock brass-door with suite-key"),
            fmt.example_line(
                "unlock brass-door with suite-key  ·  open brass-door",
                "Key must be in reach (here or inv)",
            ),
            fmt.section("Setup · app / game in a box"),
            fmt.example_line("dig place/app Skalitz | Mud and steel."),
            fmt.example_line("create thing/game KCD | Henry's trouble."),
            fmt.example_line("spawn kcd  ·  portal kcd -> Skalitz"),
            fmt.example_line(
                "put kcd in pillow-box  ·  run kcd",
                "Not from the floor — install required",
            ),
            fmt.hint(
                "Floor open only for subtypes: door, hatch, gate, portal, shell, …"
            ),
            fmt.hint("Apps on the floor or loose in inv still need install."),
            fmt.hint("Ambiguous: run <app> from <device>"),
            fmt.hint("Leave with logout (returns to where you entered, not a room exit)."),
        ),
        "lock": _page(
            "lock",
            _p(
                "Lock or unlock a portal token (door, hatch, room shell). "
                "lock <door> with <key> binds that *key instance* — not the Key prime. "
                "Author one prime Key, spawn named copies (Cellar Key, Suite Key); each "
                "door remembers the copy you locked it with. Sibling keys of the same prime "
                "do not open each other's doors. open / enter / run refuse locked portals. "
                "unlock only clears the lock; it does not travel. Keyless: lock door (no with). "
                "Optional -d / --desc is flavor when open fails while locked."
            ),
            fmt.section("Usage"),
            fmt.example_line("create thing/key Key | Blank teeth."),
            fmt.example_line("spawn key as Cellar Key  ·  spawn key as Suite Key"),
            fmt.example_line("lock brass-door with cellar-key"),
            fmt.example_line(
                'lock brass-door with cellar-key -d "The latch laughs at bare hands."',
                "Deny line on failed open",
            ),
            fmt.example_line(
                "unlock brass-door with suite-key",
                "Fails — wrong copy",
            ),
            fmt.example_line("unlock brass-door with cellar-key"),
            fmt.example_line("unlock brass-door", "Auto if the bound copy is in reach"),
            fmt.example_line("open brass-door", "Enter after unlock"),
            fmt.hint("Prime = kind of thing; instance = this key in your hand."),
            fmt.hint("Keys stay in inventory or on the floor — not consumed."),
            fmt.hint("portal clear also clears lock, key bind, and -d deny line."),
            fmt.hint('lock … -d "" clears a previous deny line.'),
        ),

        "logout": _page(
            "logout",
            _p(
                "End a run session and return to the place you were standing when you "
                "ran the app. This is player session travel — not a link on the map. "
                "You can wander inside the app world; logout still snaps back to the "
                "entry room (and the device that held the app). Nested runs pop one "
                "frame at a time."
            ),
            fmt.section("Usage"),
            fmt.example_line("logout"),
            fmt.example_line("logoff", "Alias"),
            fmt.hint(
                "If you only linked a door back, that is a normal exit — different from logout."
            ),
        ),
        "portal": _page(
            "portal",
            _p(
                "Bind a thing instance to a place world for run / unlock / open. "
                "The binding lives on the token (state), not on the device — "
                "take / drop / put / install never clear it; only portal clear does. "
                "Two uses: app→place (install then run) or door→place (floor then unlock). "
                "Never appears on the room exit list — different from link/go."
            ),
            fmt.section("Usage"),
            fmt.example_line("portal mail -> Mailroom"),
            fmt.example_line(
                "portal room-001 -> Room 001",
                "Door/token → interior place",
            ),
            fmt.example_line(
                "portal kat-moire -> City of Soft Alibis",
                "Game cartridge → full story place",
            ),
            fmt.example_line("portal clear mail", "Remove binding"),
            fmt.example_line(
                "take mail from terminal  ·  install mail in terminal  ·  run mail",
                "No re-portal needed after take",
            ),
            fmt.hint(
                "Then: lock <door> with <key> · unlock · open / enter  ·  "
                "or install + run <app>"
            ),
        ),
        "locate": _page(
            "locate",
            _p(
                "Where something is in the multiverse. "
                "Today: locate self (or bare locate) shows who you are, place, "
                "place VEN, realm, timeline, coords, paths count, and inventory. "
                "Later: locate by VEN code or short ref to list instance positions."
            ),
            fmt.section("Usage"),
            fmt.example_line("locate self", "Avatar where-now"),
            fmt.example_line("locate", "Same as locate self"),
            fmt.example_line(
                "locate THG-001",
                "Later — instances of that prime / code",
            ),
            fmt.example_line("timeline here", "Also shows locate self"),
            fmt.section("Change layers"),
            fmt.example_line("timeline set SHATTERED"),
            fmt.example_line("realm set MEMORY-ARCHIVE"),
            fmt.hint(
                "Temporary aliases: status · sit · whereami · where → locate self. "
                "Prefer locate."
            ),
            fmt.hint(
                "In the plain REPL, a short strip above the prompt echoes you @ place + coords."
            ),
        ),
        "exits": _page(
            "paths",
            _p(
                "List paths from the current place (typed place→place links). "
                "Each row: type code · exit label → destination. "
                "Same list appears on look. Codes: sp spatial · di dimensional · "
                "te temporal · na narrative · co conditional. "
                "Not used for app portals — those use run / logout."
            ),
            fmt.section("Usage"),
            fmt.example_line("paths", "Preferred name"),
            fmt.example_line("exits", "Same command"),
            fmt.example_line("ways", "Alias (older name)"),
            fmt.example_line("x", "Short alias"),
            fmt.hint("For a multi-hop tree, use map."),
        ),
        "map": _page(
            "map",
            _p(
                "Show a local multiverse map: a path-tree from where you stand. "
                "Link types are colored (spatial, dimensional, temporal, narrative, "
                "conditional). Depth defaults to 2 hops (max 4). Cycles are marked; "
                "unexpanded leaves show (…)."
            ),
            fmt.section("Usage"),
            fmt.example_line("map", "Depth 2 from here"),
            fmt.example_line("map 1", "Direct paths only"),
            fmt.example_line("map 3", "Three hops"),
            fmt.example_line("map here 2", "Same as map 2"),
            fmt.example_line("graph", "Alias for map"),
            fmt.hint("paths is a flat list; map is the tree view."),
        ),
        "inv": _page(
            "inv",
            _p(
                "List what you carry (inventory slot), in the same placement "
                "language as look. Loose items under Carrying; each carried bin "
                "is its own bucket with contents underneath (empty bins still show). "
                "inv --deep opens nested bins one layer (drawers in a pack, …)."
            ),
            fmt.section("Usage"),
            fmt.example_line("inv"),
            fmt.example_line("inv --deep", "Nested bins one layer deeper"),
            fmt.example_line("inv deep", "Same"),
            fmt.example_line("inventory"),
            fmt.example_line("i"),
            fmt.hint("Same columns as look: prime · name · code."),
        ),
        "take": _page(
            "take",
            _p(
                "Pick things up into inventory. From the floor: take <thing>. "
                "From a box (on the floor or already in inventory): take <thing> from <box>. "
                "Empty a bin in one go: take all from <box> (or take * from …). "
                "You do not “go into” a carried box — open it with examine, then take from it. "
                "get is an alias for take. "
                "Each take writes movement history on the thing (and on the box for take from). "
                "Optional story when: when @N or --when N (default @unknown — not create time)."
            ),
            fmt.section("Usage"),
            fmt.example_line("take silver", "From the floor · story @unknown"),
            fmt.example_line(
                "take SILVER-THREAD from BOX",
                "Out of a container you can reach",
            ),
            fmt.example_line(
                "take all from bucket",
                "Pocket every direct takeable in the bin",
            ),
            fmt.example_line(
                "take * from Outer",
                "Same as take all from",
            ),
            fmt.example_line(
                "take hope from keeper when @2",
                "Story node on hope + give on keeper",
            ),
            fmt.example_line("get silver from box --when 0", "Flag form"),
            fmt.example_line("examine box", "See what is inside before taking"),
            fmt.example_line("history on silver", "Life of the instance"),
            fmt.hint(
                "take all is shallow: nested stuff stays inside a taken bin "
                "(take the bin, then take all from it)."
            ),
        ),
        "drop": _page(
            "drop",
            _p(
                "Drop something from your inventory onto the current place. "
                "Only top-level carried items (to free something nested, take it from the box first). "
                "Records drop history on the thing. Optional when @N / --when N (default @unknown)."
            ),
            fmt.section("Usage"),
            fmt.example_line("drop silver"),
            fmt.example_line("drop silver --when 1", "Story when on the drop"),
            fmt.example_line("drop box", "Box keeps its contents when dropped"),
        ),
        "examine": _page(
            "examine",
            _p(
                "Inspect a thing here or in inventory: description, ids, placement. "
                "Loose contents under Here; each nested bin opens as a named "
                "bucket with its first-level kids (empty bins still show). "
                "On people: last dialog teaser, related records counts. "
                "With --deep / deep: one more layer inside those bins, full records "
                "bodies, and deeper composition. "
                "Also: examine realm / examine timeline for the place you stand in."
            ),
            fmt.section("Usage"),
            fmt.example_line("examine archivist"),
            fmt.example_line("examine table", "Here + nested drawers opened one level"),
            fmt.example_line(
                "examine --deep cartographer",
                "Full lore + deep compose",
            ),
            fmt.example_line("look in drawer", "Same path via look"),
            fmt.example_line("look at door", "Same as examine door"),
            fmt.example_line("in --deep at silver", "Alias form"),
            fmt.example_line("in silver", "Short alias (also: exam, inspect)"),
            fmt.example_line("examine realm", "Current place's realm layer"),
            fmt.example_line("examine timeline", "Current place's timeline layer"),
        ),
        "wiki": _page(
            "wiki",
            _p(
                "Open a dossier for a real prime VEN or instance — not a second folio. "
                "In the TUI, opens the soft reader (same frame as folio). "
                "Shows identity, description, tags, notes (records), instances, and "
                "sub-links. Only names that resolve to actual entities open a page. "
                "In studio text, write [[Name]]; open with wiki Name."
            ),
            fmt.section("Usage"),
            fmt.example_line("wiki", "Dossier for this place’s prime VEN"),
            fmt.example_line("wiki Desire to Return", "By prime name"),
            fmt.example_line("wiki cartographer", "Instance here if unique"),
            fmt.example_line(
                "wiki Elon deep",
                "Dossier with nested composition tree",
            ),
            fmt.example_line(
                "wiki link Desire to Return cartographer",
                "Sub-link on the prime (meta wiki_links)",
            ),
            fmt.example_line("wiki unlink Desire to Return cartographer"),
            fmt.section("Notes & folios"),
            fmt.hint("Notes = record ven … add / record on <instance> add"),
            fmt.hint("Folios: wiki shows meta; read leaves with folio open …"),
            fmt.hint("TUI: Esc closes the wiki reader  ·  link/unlink stay in the log"),
            fmt.hint("No auto-create on missing [[links]]; no multi-page wiki articles."),
        ),
        "who": _page(
            "who",
            _p(
                "List people in the current place. Each person may show inner life "
                "(sense, archetypes…) and a short teaser of their most recent dialog."
            ),
            fmt.section("Usage"),
            fmt.example_line("who"),
        ),
        "talk": _page(
            "talk",
            _p(
                "Start a back-and-forth dialog with a person present here. "
                "Each line is a turn (alternating you and them) until you type /fin. "
                "Optional title and when-stamp work like records. "
                "Mid-dialog, replace the when-stamp with /when …"
            ),
            fmt.section("Usage"),
            fmt.example_line("talk archivist", "Start dialog (person must be here)"),
            fmt.example_line(
                "talk cartographer | First Meeting",
                "Title the dialog",
            ),
            fmt.example_line(
                "talk cartographer | when Before the Roads | First Meeting",
                "Mythic/event stamp + title",
            ),
            fmt.example_line(
                "talk cartographer | @1704067200 | Signal Chat",
                "Unix-style stamp + title",
            ),
            fmt.section("During dialog"),
            fmt.example_line("/when After the Break", "Replace when-stamp (active)"),
            fmt.example_line("/when when Before the Roads", "Same with when keyword"),
            fmt.example_line("/when @1704067200", "Unix/date stamp"),
            fmt.example_line("/when clear", "Remove when-stamp"),
            fmt.hint("In dialog: type lines · /you … · /them … · /when … · /fin to end"),
            fmt.hint("On /fin: transcript is saved with the current when; records note both characters."),
        ),
        "dialogs": _page(
            "dialogs",
            _p(
                "List and re-read completed dialog transcripts (after talk … /fin). "
                "Bare dialogs lists only transcripts that finished in this place. "
                "Rename a finished dialog or replace its when-stamp without re-recording turns."
            ),
            fmt.section("Usage"),
            fmt.example_line("dialogs", "List dialogs that took place here"),
            fmt.example_line(
                "dialogs all",
                "Every place (also: dialogs list · dialogs show list)",
            ),
            fmt.example_line("dialogs show 1", "Re-read by list number (here first)"),
            fmt.example_line(
                "dialogs show FIRST-MEETING",
                "Re-read by cute slug (shown in the list)",
            ),
            fmt.example_line("dialogs show First Meeting", "Re-read by title"),
            fmt.example_line(
                "dialogs rename 1 as Better Title",
                "Rename after /fin (also: dialogs title … as …)",
            ),
            fmt.example_line(
                "dialogs when 1 | when After the Break",
                "Replace when on completed dialog #1",
            ),
            fmt.example_line(
                "dialogs when First Meeting | @1704067200",
                "By title + @ stamp",
            ),
            fmt.hint(
                "Each dialog gets a cute slug from its title (FIRST-MEETING, "
                "FIRST-MEETING-2 on clash). Slug stays stable if you rename the title."
            ),
            fmt.hint("undo restores the previous title or when on a completed dialog."),
        ),
        "book": _page(
            "folio",
            _p(
                "A folio holds ordered leaves (chapters). Open it to read; "
                "edit one leaf at a time in STUDIO Writer."
            ),
            fmt.section("Usual path"),
            fmt.example_line(
                "create folio Field Notes | Working notebook.",
                "or: create book … (same kind)",
            ),
            fmt.example_line("spawn field-notes", "Put a copy here"),
            fmt.example_line("folio open field-notes", "Soft reader (alias: read · book open)"),
            fmt.section("In the reader"),
            fmt.hint("← / →   turn leaves"),
            fmt.hint("+       add leaf after current → opens STUDIO Writer"),
            fmt.hint("e       edit this leaf (title + body)"),
            fmt.hint("Esc     close reader"),
            fmt.hint(
                "F2/Alt+P preview · Ctrl+S save · Esc cancel in writer (quiet toasts)"
            ),
            fmt.section("CLI when you need it"),
            fmt.example_line("folio pages field-notes", "List leaf titles"),
            fmt.example_line(
                "folio page add field-notes Preface | It begins.",
                "Append a leaf (alias: book page …)",
            ),
            fmt.example_line(
                "folio page add field-notes Title <<studio",
                "Append via STUDIO Writer",
            ),
            fmt.example_line(
                "folio page edit field-notes 1 <<studio",
                "Rewrite leaf 1 in the writer",
            ),
            fmt.example_line(
                "folio incomplete field-notes",
                "Mark unfinished (yellow)",
            ),
            fmt.example_line(
                "folio complete field-notes",
                "Mark finished (green when leaves exist)",
            ),
            fmt.section("Also useful"),
            fmt.example_line(
                "folio open notes from pouch",
                "Open while nested — no take needed",
            ),
            fmt.example_line(
                "folio open field-notes#0001",
                "By short ref",
            ),
            fmt.hint(
                "Status: empty · incomplete · complete. "
                "book … still works as a full alias. "
                "Line surgery (folio line …) exists; prefer e / + in the reader. "
                "undo reverses the last edit."
            ),
            fmt.hint("Studio Text in a leaf: help studio-text"),
        ),
        "record": _page(
            "record",
            _p(
                "Records are an append-only revision log for the office. By default "
                "they attach to the place instance you stand in. Attach a record to "
                "any instance (item, person, …) with record on <match> — no elevate "
                "required. Prime VEN records (record ven …) are canon across all "
                "instances. Optional when-stamps set story/event time; the wall-clock "
                "moment you typed is always kept separately. "
                "Ending a talk with /fin also writes a dialog record note. "
                "Alias: lore still works (same command)."
            ),
            fmt.section("Current place"),
            fmt.example_line("record", "List records for this place"),
            fmt.section("Flags (free order)"),
            fmt.example_line(
                "record -a -t Founding -b Raised for travelers. -w 0",
                "-a add · -t title · -b body · -w when",
            ),
            fmt.example_line(
                'record --add --on me -n Note -d "Soft light." --when 1',
                "Target with --on; -d same as -b",
            ),
            fmt.example_line(
                "record on cartographer -a -t Whisper -b Heard at dusk.",
                "Instance then flags",
            ),
            fmt.hint(
                "-a/--add required for flag form. "
                "Title: -t/-n · Body: -b/-d · When: -w. "
                "Prose record add … still works."
            ),
            fmt.section("Prose (still works)"),
            fmt.example_line(
                "record add Founding | Raised for market travelers.",
                "Title | body  (title optional)",
            ),
            fmt.example_line("record add Just a body with no title."),
            fmt.example_line(
                "record add when Before the Roads | Founding | Raised for travelers.",
                "Mythic when-stamp + title + body",
            ),
            fmt.example_line(
                "record add @2024-06-15 14:30 | Eclipse note | The glass dimmed.",
                "Date/time stamp (free text)",
            ),
            fmt.example_line(
                "record add @1704067200 | Signal | A unix-style event stamp.",
                "Unix-style stamp as free text",
            ),
            fmt.example_line(
                r"record add Note | Line one.\nLine two.",
                "\\n in body becomes a real line break (same as @desc)",
            ),
            fmt.example_line(
                "record add from field-notes 1:2",
                "Stamp place lore from folio leaf 1 line 2 (title cites p1:2)",
            ),
            fmt.example_line(
                "record add from field-notes p1:3 | Quoted fragment",
                "Same with optional title override",
            ),
            fmt.hint(
                "Folio leaf/line edits and record add (including from folio) support undo."
            ),
            fmt.section("Any instance (item / person / …)"),
            fmt.example_line("record on quill", "List record on this copy only"),
            fmt.example_line(
                "record on quill add Bent nib | From last winter’s drafts.",
                "Add instance records (not shared with other spawns)",
            ),
            fmt.section("Current realm / timeline layers"),
            fmt.example_line(
                "record on realm",
                "Records on the realm of the place you stand in",
            ),
            fmt.example_line(
                "record on timeline",
                "Records on this place's timeline layer",
            ),
            fmt.example_line(
                "record on realm add Bound | The soft edge of Unformed.",
            ),
            fmt.example_line("record realm", "Shorthand for record on realm"),
            fmt.example_line(
                "record on Unformed",
                "Named layer by realm/timeline name when unique",
            ),
            fmt.example_line(
                "record on quill add when Before the Roads | Origin | Gifted at the hearth.",
                "When-stamp on instance records",
            ),
            fmt.example_line(
                "record on quill#0002 add Note | Only this short-ref copy.",
                "Target a specific instance of a prime",
            ),
            fmt.example_line(
                "record add studio | Note | **Bold** body\\n---\\nMore layout.",
                "Studio Text record body (help studio-text)",
            ),
            fmt.example_line(
                "record add Founding <<studio",
                "Buffer editor for a multi-line record body",
            ),
            fmt.example_line(
                "record on quill add <<studio",
                "Editor record on an instance",
            ),
            fmt.example_line("record search mirror", "Search all record text"),
            fmt.section("Prime VEN"),
            fmt.example_line(
                "record ven SILVER-THREAD",
                "List records on a VEN (cute slug or relaxed name)",
            ),
            fmt.example_line(
                "record ven SILVER-THREAD add Motif | Binds what timelines fray.",
                "Add a revision on that VEN",
            ),
            fmt.example_line(
                "record ven silver thread add when First Binding | Motif | Ties fray.",
                "VEN records with a mythic stamp",
            ),
            fmt.example_line(
                "record ven silver thread add | Body only.",
                "Relaxed typing still resolves when unique",
            ),
        ),
        "dig": _page(
            "dig",
            _p(
                "Make something here. "
                "Bare name or place[/subtype] → free-standing place (link after). "
                "Leading kind (bin, thing, folio, …) → prime + instance on this floor "
                "(takeable / put-into). "
                "Do not dig bin as if it were a place name — that used to make a "
                "floating place you could not take."
            ),
            fmt.section("Usage"),
            fmt.example_line("dig Quiet Gallery", "Free-standing place"),
            fmt.example_line(
                "dig place/app Mailroom",
                "App-world place (still a full place)",
            ),
            fmt.example_line(
                "dig bin Table | Oak.",
                "Bin on the floor here (take / put into)",
            ),
            fmt.example_line(
                "dig box/calendar Q3 2026",
                "box → bin; lands here",
            ),
            fmt.example_line("dig thing Pink Button | A button she found."),
            fmt.example_line("dig Mirror Box Chamber timeline SHATTERED"),
            fmt.hint(
                "Places: free-standing · link after. "
                "Bins/things: on this floor · take/drop/put."
            ),
        ),
        "timeline": _page(
            "timeline",
            _p(
                "Timelines are layer VENs. Every place (and optionally any instance) "
                "can sit on a timeline so you know where-in-time it is. "
                "Same idea for realms (dimensional layers)."
            ),
            fmt.section("Manage"),
            fmt.example_line("timeline", "List timelines and place counts"),
            fmt.example_line("timeline list"),
            fmt.example_line(
                "timeline create RITUAL-EVE | Night the mirror box is opened.",
            ),
            fmt.example_line("timeline places PRIME", "Places on that timeline"),
            fmt.section("Assign"),
            fmt.example_line(
                "timeline set SHATTERED",
                "Put the place you stand in on SHATTERED",
            ),
            fmt.example_line(
                "timeline set PRIME on SILVER-THREAD",
                "Assign a thing here (or unique place) to a timeline",
            ),
            fmt.example_line("timeline clear", "Remove timeline from current place"),
            fmt.example_line("timeline here", "Same as locate self"),
            fmt.section("Review current layer"),
            fmt.example_line("record on timeline", "List records on this place's timeline"),
            fmt.example_line("examine timeline", "Desc + meta for the layer"),
            fmt.example_line("@desc on timeline", "Show/set timeline description"),
            fmt.section("See also"),
            fmt.example_line("realm list"),
            fmt.example_line("locate self", "You / place / layers / inv"),
            fmt.example_line("help realm"),
        ),
        "realm": _page(
            "realm",
            _p(
                "Realms are dimensional layers (MATERIAL, MEMORY-ARCHIVE, …). "
                "Assign them like timelines so every place has a clear coords pair: "
                "realm / timeline."
            ),
            fmt.section("Manage"),
            fmt.example_line("realm", "List realms"),
            fmt.example_line("realm create MIRROR-BOX | Pocket inside the ritual."),
            fmt.example_line("realm places MATERIAL"),
            fmt.section("Assign"),
            fmt.example_line("realm set MEMORY-ARCHIVE"),
            fmt.example_line("realm set MATERIAL on Mirror Box"),
            fmt.example_line("realm clear"),
            fmt.section("Review current layer"),
            fmt.example_line("record on realm", "List records on this place's realm"),
            fmt.example_line("examine realm", "Desc + meta for the layer"),
            fmt.example_line("@desc on realm", "Show/set realm description"),
            fmt.section("See also"),
            fmt.example_line("help timeline"),
            fmt.example_line("locate self"),
        ),
        "link": _page(
            "link",
            _p(
                "Create, rename, or remove paths from the place you stand in. "
                "Optional type and both for reverse path on create/unlink."
            ),
            fmt.section("Create"),
            fmt.example_line("link north -> Quiet Gallery both"),
            fmt.example_line(
                "link through the tear -> Quiet Gallery dimensional both",
                "Types: spatial dimensional temporal narrative conditional",
            ),
            fmt.section("Rename / remove"),
            fmt.example_line(
                "link rename north as east",
                "Change path label here (does not move the destination)",
            ),
            fmt.example_line("unlink north", "Remove this path"),
            fmt.example_line(
                "unlink north both",
                "Also remove reverse path back here (same label, or sole reverse)",
            ),
            fmt.example_line("delink north", "Alias for unlink"),
            fmt.hint("undo reverses the last link / rename / unlink"),
        ),
        "@desc": _page(
            "@desc",
            _p(
                "Show, replace, or append a description. Default target is the "
                "place you stand in. Use @desc on <match> for any instance "
                "(thing, person, folio, …) without elevating it to a new VEN. "
                "Clear removes the instance override so the prime VEN text returns. "
                "Edits do not write material history until you @desc commit "
                "(optional when @N) — then a desc history row, text-log snapshot, "
                "and a record entry with the full description text. "
                "Use \\n for line breaks, or @desc << multiline ended with a lone ."
            ),
            fmt.section("Current place"),
            fmt.example_line("@desc", "Show current place description"),
            fmt.example_line("@desc Soft light on unfinished canvases."),
            fmt.example_line(
                "@desc commit",
                "Stamp history + records (title: description update)",
            ),
            fmt.example_line(
                "@desc commit -t Soft dusk when @2",
                "Optional lore title + story when",
            ),
            fmt.example_line(
                "@desc commit on me --title Portrait note",
                "Instance desc + titled record",
            ),
            fmt.example_line(
                r"@desc First line.\nSecond line.",
                "Line breaks via \\n",
            ),
            fmt.example_line("@desc + Another sentence.", "Append on a new line"),
            fmt.example_line("@desc ++ New paragraph.", "Append with a blank line"),
            fmt.example_line("@desc clear", "Clear place override; VEN default returns"),
            fmt.example_line(
                "@desc <<studio",
                "Open buffer editor for place desc (Ctrl+S save)",
            ),
            fmt.example_line("@desc <<", "Same editor, plain text"),
            fmt.section("Any instance (no elevate needed)"),
            fmt.example_line("@desc on quill", "Show this copy’s description"),
            fmt.example_line(
                "@desc on realm",
                "Current place's realm layer description",
            ),
            fmt.example_line(
                "@desc on timeline Soft light between years.",
                "Set this place's timeline description",
            ),
            fmt.example_line(
                "@desc on quill The nib is bent from last winter.",
                "Override description on this instance only",
            ),
            fmt.example_line("@desc on quill + A drop of ink remains.", "Append"),
            fmt.example_line(
                "@desc on quill#0002 clear",
                "Clear override on a specific short-ref copy",
            ),
            fmt.section("Studio Text (designed layout)"),
            fmt.example_line(
                "@desc studio | # Title\\n\\n**Bold** and _dim_ and [[wikilink]]",
                "Opt-in markup (stored with .format: studio)",
            ),
            fmt.example_line(
                "@desc on quill <<studio",
                "Editor for instance override description",
            ),
            fmt.hint(
                "<< / <<studio opens STUDIO Writer: move freely, F2 or Alt+P "
                "preview (no commit; avoids VS Code Ctrl+P), Ctrl+S save, "
                "Esc / Ctrl+Q cancel. text log lists editor save history."
            ),
            fmt.hint("See help studio-text for the full dialect. Default text stays plain."),
            fmt.hint(
                "Two spawns of the same prime keep separate overrides. "
                "examine shows the effective text (override or VEN)."
            ),
        ),
        "studio-text": _page(
            "studio-text",
            _p(
                "Studio Text is an opt-in markup for descriptions and records. "
                "Plain text (default) is fully escaped. Studio bodies start with "
                ".format: studio in storage and render through a whitelist only — "
                "no raw Rich injection."
            ),
            fmt.section("Enable"),
            fmt.example_line("@desc studio | **Hello** world"),
            fmt.example_line("@desc on coin alpha studio | # Coin story"),
            fmt.example_line(
                "@desc <<studio",
                "Multiline; live line echo; undo/u = last line",
            ),
            fmt.example_line(
                "record add studio | Note | **Bold** body with a rule:\\n---\\nMore.",
            ),
            fmt.example_line(
                "record on quill add studio | Seed | ```seed\\nliteral dots.....\\n```",
            ),
            fmt.section("Dialect"),
            fmt.hint("# Title (yellow)   ## Section   ### Dim heading"),
            fmt.hint("---  or  ====  or  .....   → dim horizontal rule (72 wide)"),
            fmt.hint("**bold**   _italic/dim_   `code`"),
            fmt.hint("{yellow}text{/}   or  {y}text{/y}   whitelist color spans"),
            fmt.hint(
                "colors: yellow/y red/r green/g cyan/c blue/b magenta/m white/w "
                "gold accent/a ok warn err dim bright"
            ),
            fmt.hint("> blockquote"),
            fmt.hint("``` / ```seed / ```map … ```   light box fence (ASCII art)"),
            fmt.hint("[[Name]]   pointer chip — open with wiki Name (real VEN/instance only)"),
            fmt.hint(
                "[label](https://…)  or bare https://…  — click opens your browser"
            ),
            fmt.hint("@tag  #tag   muted chips"),
            fmt.hint(
                ":Label: value   field row — contiguous rows share a value column "
                "(also bare Key: value)"
            ),
            fmt.hint(
                "Optional YAML frontmatter between --- lines "
                "(keys padded to one column)"
            ),
            fmt.section("Safety"),
            _p(
                "Unknown [brackets] and unknown {color} names in free text are escaped. "
                "Only the Studio Text whitelist emits markup (emphasis, colors, fences). "
                "Folio leaves use the same dialect as @desc / record."
            ),
        ),
        "undo": _page(
            "undo",
            _p(
                "Undo the last successful builder mutation in this session "
                "(descriptions, dig, link, take/drop, create, spawn, record, "
                "folio page/line edits, incomplete/complete, …). "
                "Not navigation (go). Not saved across restarts."
            ),
            fmt.section("Usage"),
            fmt.example_line("undo"),
            fmt.example_line("u", "Short alias"),
        ),
        "clear": _page(
            "clear",
            _p(
                "Wipe the session transcript to a blank log — no tips banner, "
                "no “cleared” notice. In the TUI this empties the world log; in "
                "the plain REPL it clears the terminal when possible. "
                "The studio header bar stays; only the scrollback goes."
            ),
            fmt.section("Usage"),
            fmt.example_line("clear"),
            fmt.example_line("clr", "Alias"),
            fmt.section("On travel"),
            _p(
                "A successful go / g also clears the log first, then shows the "
                "travel cue and a fresh look of the new place — so play stays "
                "readable after a long build session."
            ),
            fmt.example_line("go south", "Clears log, then shows the new room"),
            fmt.section("Also"),
            _p(
                "Want a blank log *and* a fresh room view?  "
                "Use cls (or refresh / blink) — clear + look in one silly step."
            ),
        ),
        "cls": _page(
            "cls",
            _p(
                "Clear the scrollback, then print a fresh look of where you are. "
                "DOS nostalgia (cls) with office utility — wipe the mess, see the room."
            ),
            fmt.section("Usage"),
            fmt.example_line("cls", "Clear log + look"),
            fmt.example_line("refresh", "Alias"),
            fmt.example_line("ref", "Short alias"),
            fmt.example_line("blink", "Silly alias"),
            fmt.example_line("cls deep", "Clear + look --deep"),
            fmt.section("vs clear"),
            _p(
                "clear / clr only empties the log. "
                "cls empties the log and reprints the place."
            ),
        ),
        "text": _page(
            "text",
            _p(
                "Every successful << / <<studio buffer save appends a full-body "
                "snapshot (git-style log). List, inspect, or restore prior saves. "
                "Works for descriptions, folio leaves, and record editor saves."
            ),
            fmt.section("Usage"),
            fmt.example_line("text log", "Place description saves"),
            fmt.example_line("text log on quill", "Instance description saves"),
            fmt.example_line("text log book field-notes page 1", "Also: folio …"),
            fmt.example_line("text log record", "Record bodies from the editor"),
            fmt.example_line("text show trev_…", "Full snapshot"),
            fmt.example_line("text restore trev_…", "Write snapshot back live"),
            fmt.section("Open the editor"),
            fmt.example_line("@desc <<studio"),
            fmt.example_line("folio page add notes Chapter <<studio"),
            fmt.example_line("record add Founding <<studio"),
            fmt.hint(
                "In the editor: F2/Alt+P preview · Ctrl+S save · Esc / Ctrl+Q cancel"
            ),
        ),
        "create": _page(
            "create",
            _p(
                "Make a prime VEN — the species the world knows. "
                "Then spawn lived copies into places."
            ),
            fmt.section("Pattern (flags — free order)"),
            fmt.example_line(
                "create --type sense/feeling --when 0 --name Satisfaction "
                "--desc The feeling of something working well.",
                "Markers; any order",
            ),
            fmt.example_line(
                "create -t thing -n Quill -d Soft graphite. -w 0",
                "Short flags",
            ),
            fmt.hint(
                "--type/--kind/-t  ·  --name/-n  ·  --desc/-d  ·  --when/-w  ·  --of parent"
            ),
            fmt.hint(
                "Roots: person · place · bin · thing · folio · symbol · sense · event  "
                "(aliases: box crate container → bin; feeling→sense; …)"
            ),
            fmt.section("Legacy (still works)"),
            fmt.example_line(
                "create folio Field Notes | Working notebook.",
                "kind name | desc",
            ),
            fmt.example_line(
                "create sense/longing Patient Longing | Distance is loyalty. when @0",
                "subtype + story when",
            ),
            fmt.example_line(
                "create thing Secret Document of File | Classified.",
                "Lineage: of parent",
            ),
            fmt.section("Then instance"),
            fmt.example_line(
                "spawn --ven field-notes -n Ritual Notes --when 0",
                "See help spawn",
            ),
            fmt.section("Old words still work"),
            fmt.hint(
                "book → folio/book · object → thing · material → thing/material · "
                "feeling → sense/feeling · goal/desire/purpose → sense/… · "
                "archetype → person/archetype · concept → symbol · "
                "event is a root (event/meeting, event/beat, …)"
            ),
            fmt.hint("Kinds: {kinds}"),
            fmt.hint("See also: help kinds · help spawn · help folio · help history"),
        ),
        "history": _page(
            "history",
            _p(
                "Story when along a timeline: numbered nodes (@0, @1, …) or @unknown. "
                "Craft time is always stored separately on each row. "
                "Each act gets a shared event code (HST-001, …) so put on hope and "
                "receive on the vessel show the same code. "
                "Create/spawn/record and movement (take / drop / put) write life-of-item rows. "
                "Spawn onto the floor also records on the place; take/drop also on you "
                "and the room. Prefer --when 0; trailing when @0 also works. "
                "Not the multiverse timeline layer command — this is material history."
            ),
            fmt.section("Pattern"),
            fmt.example_line(
                "create --type thing --name Quill --desc Soft. --when 2",
                "Preferred flags (any order)",
            ),
            fmt.example_line(
                "spawn quill -> Pocket Quill --when 2",
                "Instance + place receive · HST-…",
            ),
            fmt.example_line(
                "put hope in keeper when @3",
                "Shared HST on hope + keeper",
            ),
            fmt.example_line(
                "take hope from keeper --when 4",
                "take · give · receive (you)",
            ),
            fmt.example_line(
                "record add Note | Body. when @0",
                "Lore: freeform stamp and/or when @N",
            ),
            fmt.section("List"),
            fmt.example_line("history nodes", "Nodes on this place's timeline"),
            fmt.example_line("history here", "This place (spawns + drops + puts)"),
            fmt.example_line("history me", "You (Builder) — takes, drops, puts"),
            fmt.example_line("history on hope", "One instance (spawn + moves)"),
            fmt.example_line("history HST-003", "All legs of one event"),
            fmt.example_line(
                "retime HST-003 when @1",
                "Rewrite story when on every leg",
            ),
            fmt.example_line("history ven Quill", "Prime VEN"),
            fmt.hint(
                "Omitted when → @unknown (not the item's create time). "
                "Each act gets its own craft timestamp + shared HST code. "
                "Fix a stamp later: retime HST-NNN when @N. Bags/visit later."
            ),
        ),
        "retime": _page(
            "retime",
            _p(
                "Change the story-when stamp on an existing history event. "
                "Every leg that shares the HST code (thing, vessel, you, place) "
                "updates together. Craft time (created_at) is not changed — only "
                "story when (@N or @unknown). Ensures timeline nodes when needed."
            ),
            fmt.section("Usage"),
            fmt.example_line(
                "retime HST-003 when @2",
                "All legs of HST-003 → story @2",
            ),
            fmt.example_line(
                "retime #HST-003 --when 0",
                "Hash prefix optional",
            ),
            fmt.example_line(
                "retime HST-003 @unknown",
                "Clear story node",
            ),
            fmt.example_line(
                "retime HST-003 unknown",
                "Same as @unknown",
            ),
            fmt.example_line("history HST-003", "Confirm all legs"),
            fmt.example_line("undo", "Restore previous stamps on those legs"),
            fmt.hint("See also: help history"),
        ),
        "spawn": _page(
            "spawn",
            _p(
                "Create an instance of a prime. "
                "Things, folios, people, sense… land here. "
                "Places spawn free-standing (link them with link / go). "
                "Short ref: FOL-001-0001, THG-002-0001, … "
                "Optional story when: when @N or when @unknown."
            ),
            fmt.section("Pattern (flags — free order)"),
            fmt.example_line(
                "spawn --ven field-notes -n Ritual Notes --when 2",
                "Prime · lived title · story node",
            ),
            fmt.example_line(
                "spawn --ven field-notes -n Pocket Notes -w 0",
                "-n / --name / --title for lived name",
            ),
            fmt.section("Prose title (as or ->)"),
            fmt.example_line(
                "spawn <prime> as Title when @2",
                "Sentence-style as",
            ),
            fmt.example_line(
                "spawn <prime> -> Title when @2",
                "Arrow form (same as as)",
            ),
            fmt.example_line(
                "/s <prime> -> Title",
                "Maker shorthand",
            ),
            fmt.example_line(
                "spawn field-notes",
                "Bare spawn · auto-suffix · story @unknown",
            ),
            fmt.section("Places (templates)"),
            fmt.example_line(
                "create place Room | A generic chamber.",
                "Template prime first",
            ),
            fmt.example_line(
                "spawn room as Kitchen",
                "Room instance — unlinked until you connect it",
            ),
            fmt.example_line(
                "spawn room as Bedroom",
                "Another instance of the same prime",
            ),
            fmt.example_line("link north -> Kitchen both", "Then wire the map"),
            fmt.hint("Target later: folio open ritual  ·  #FOL-001-0002"),
        ),
        "rename": _page(
            "rename",
            _p(
                "Change an instance display title (name override) without elevating a new prime. "
                "Works on things here/in inv, the place you stand in, or any place by name. "
                "Writes a rename history row on that instance (shared HST code; optional when @N)."
            ),
            fmt.section("Usage"),
            fmt.example_line("rename pocket as Travel Notes"),
            fmt.example_line(
                "rename me -> Ada",
                "Arrow form (same as word as)",
            ),
            fmt.example_line(
                "rename me as Danyi",
                "Sentence-style as · history: Builder → Danyi",
            ),
            fmt.example_line("rename field-notes inv as Pack Journal"),
            fmt.example_line("call field-notes#FIELD-NOTES-0001 as First Copy"),
            fmt.example_line(
                "rename here as Quiet Gallery when @1",
                "Retitle this place · story @1",
            ),
            fmt.example_line(
                "rename Side Alcove as Memory Nook",
                "Retitle any place instance by name",
            ),
            fmt.example_line("history me", "See rename among other life rows"),
            fmt.hint("Aliases for current place: here, place, room, this, location"),
            fmt.hint(
                "Prime formal name: vens rename Builder as Ada  ·  "
                "vens rename Builder -> Ada (VEN, not instance)"
            ),
            fmt.hint("undo restores the previous title"),
        ),
        "instances": _page(
            "instances",
            _p(
                "List every instance of a prime VEN with short ref, location (here/inv), "
                "and folio leaf counts when relevant."
            ),
            fmt.section("Usage"),
            fmt.example_line("instances field-notes"),
            fmt.example_line("inst field-notes"),
        ),
        "put": _page(
            "put",
            _p(
                "Move a nearby or carried thing into a container, person, or nearby place. "
                "install is an alias for put (handy for apps into devices before run). "
                "Prepositions in / into / on / onto are the same placement "
                "(on/onto feel natural for tables, shelves, trays). "
                "Adjacent paths count as present: put into a path label or neighboring place name "
                "without picking the thing up first (works for people and things). "
                "Putting sense or person/archetype into a person auto-uses "
                "the matching inner-life slot (Inner life on examine). "
                "Writes put history on the thing and receive on the vessel. "
                "Optional when @N / --when N (default @unknown). "
                "From a box later: take <thing> from <container>."
            ),
            fmt.section("Usage"),
            fmt.example_line("put SILVER-THREAD in BOX"),
            fmt.example_line(
                "put quill on table",
                "on / onto = same as in / into",
            ),
            fmt.example_line(
                "install mail in terminal",
                "Same as put (run-friendly wording)",
            ),
            fmt.example_line(
                "put hope in cartographer when @1",
                "History on hope + receive on cartographer",
            ),
            fmt.example_line(
                "put Distant Thunder in The Archivist sense",
                "Or bare: put Distant Thunder in Archivist",
            ),
            fmt.example_line(
                "put Patient Longing in cartographer",
                "Auto slot=sense → Inner life",
            ),
            fmt.example_line(
                "put silver in north --when 0",
                "Into the place through that path",
            ),
            fmt.example_line(
                "put Archivist into Side Alcove",
                "Move a person to an adjacent room by name",
            ),
            fmt.example_line(
                "put silver in here",
                "Onto the floor of this place (from inv or a box)",
            ),
            fmt.example_line("take SILVER-THREAD from BOX", "Retrieve later"),
            fmt.example_line("history on hope", "Movement trail for one instance"),
            fmt.hint(
                "Slots: interior inventory worn sense archetype "
                "(legacy: feeling goal desire purpose memory motif event)"
            ),
        ),
        "despawn": _page(
            "despawn",
            _p(
                "Soft-remove an instance: it is not deleted. It is shelved in the mythic "
                "place Lost Dept (auto-created). Lore, folios, and short-refs travel with it. "
                "Reclaim later into inventory. Prefer this over destroying data."
            ),
            fmt.section("Usage"),
            fmt.example_line("despawn video game", "From inv or floor → Lost Dept"),
            fmt.example_line("lose silver", "Alias for despawn"),
            fmt.example_line("lost", "List what is shelved in Lost Dept"),
            fmt.example_line("reclaim video game", "Pull from Lost Dept into inventory"),
            fmt.example_line("unlose silver", "Alias for reclaim"),
            fmt.hint("undo reverses the last despawn or reclaim"),
            fmt.hint(
                "Cannot lose places, the player, or realm/timeline layers. "
                "No hard-delete of instances."
            ),
        ),
        "elevate": _page(
            "elevate",
            _p(
                "Promote a lived instance into a new Prime VEN whose parent is the "
                "origin prime, and rebind the lived copy as instance #0001 of the new prime. "
                "Further spawn of the elevated prime creates more instances."
            ),
            fmt.section("Usage"),
            fmt.example_line("elevate silver"),
            fmt.example_line(
                "elevate File 13.9 as The Rift Copy",
                "Name the new prime; lived item rebinds to it",
            ),
        ),
        "vens": _page(
            "vens",
            _p(
                "List prime VENs (optionally by kind), show the specialization tree, "
                "or move primes between worlds via the shared AIDM collector "
                "(~/.aidm/ven-collector). Export is prime-only: description, lore, "
                "soft wiki links, and folio leaf text when present. Instances stay behind."
            ),
            fmt.section("Catalog"),
            fmt.example_line("vens"),
            fmt.example_line(
                "vens types",
                "Kinds + subtypes in use (no prime names)",
            ),
            fmt.example_line("vens place"),
            fmt.example_line("vens folio"),
            fmt.example_line("vens sense"),
            fmt.example_line("vens tree", "All specialization roots"),
            fmt.example_line("vens tree File", "Subtree under File"),
            fmt.example_line(
                "vens rename Builder -> Ada",
                "Rename a prime formal name (code stays; optional reslug)",
            ),
            fmt.section("Collector (export / import)"),
            fmt.example_line(
                "vens export the-knock",
                "Prime → {seq}-{CODE}-{slug}.ven",
            ),
            fmt.example_line(
                "vens export ritual-notes",
                "If that folio is here: instance pack (title/leaves + prime)",
            ),
            fmt.example_line(
                "vens export inst field-notes",
                "Force instance export",
            ),
            fmt.example_line(
                "vens export prime field-notes",
                "Force prime-only export",
            ),
            fmt.example_line("ven load", "List packs (MODE = prime|inst)"),
            fmt.example_line(
                "ven load 0002-FOL-001-0001-ritual-notes",
                "Import instance into this place (+ ensure prime)",
            ),
            fmt.hint(
                "Instance packs move folios/things between worlds without elevating them. "
                "Provenance: origin world + home code; remap if code taken."
            ),
            fmt.hint("Collector path: ~/.aidm/ven-collector/"),
        ),
        "lineage": _page(
            "lineage",
            _p(
                "Show specialization path root › … › prime, optionally ending at a lived instance."
            ),
            fmt.section("Usage"),
            fmt.example_line("lineage Secret Document"),
            fmt.example_line("lineage File 13.9"),
        ),
        "compose": _page(
            "compose",
            _p(
                "Prime-level composition: a whole VEN is made of other primes "
                "(symbol, person/archetype, motif, …). Distinct from put/containment "
                "(lived instances inside rooms or people)."
            ),
            fmt.section("Usage"),
            fmt.example_line("compose Him"),
            fmt.example_line(
                "compose Elon deep",
                "Nested parts of parts (composition tree)",
            ),
            fmt.example_line("compose Him + Concept of Him as symbol"),
            fmt.example_line("compose Him + Archetype of Him as archetype"),
            fmt.example_line("compose Him - Concept of Him"),
        ),
        "kinds": _page(
            "kinds",
            _p(
                "Lean roots the studio understands. Flavors use kind/subtype "
                "(create folio/sketchbook …, sense/longing …, event/meeting …). "
                "Inner life (when put in a person): sense, person/archetype. "
                "Legacy names fold: book→folio, feeling→sense, object→thing, … "
                "For what this world actually uses: vens types."
            ),
            fmt.section("Usage"),
            fmt.example_line("kinds"),
            fmt.example_line("vens types", "Census of kind/sub in this world"),
            fmt.example_line("create sense/longing Soft Ache | Quieter cousin."),
            fmt.example_line(
                "create event/meeting Soft Kickoff | Room holds the beat.",
            ),
            fmt.hint("Roots: {kinds}"),
            fmt.hint("See also: help create · help put · help folio · help vens"),
        ),
        "help": _page(
            "help",
            _p(
                "Bare help or ? shows the short index. help <term> shows a detail page "
                "with examples."
            ),
            fmt.section("Usage"),
            fmt.example_line("help"),
            fmt.example_line("?"),
            fmt.example_line("help look"),
            fmt.example_line("help record"),
        ),
        "quit": _page(
            "quit",
            _p("Leave the studio."),
            fmt.section("Usage"),
            fmt.example_line("quit"),
            fmt.example_line("exit"),
            fmt.example_line("q"),
        ),
        "concepts": _page(
            "concepts",
            _p(
                "VEN — prime idea (person, place, bin, thing, folio, symbol, "
                "sense, event, realm, timeline).",
                "Instance — a situated copy you can place, hold, or walk into.",
                "Lineage — specialization tree: parent prime › child primes "
                "(FILE → Secret Document); create … of <parent> or elevate.",
                "Composition — prime-level parts (Him composed of symbol / archetype); "
                "compose + / compose -; not the same as inventory containment.",
                "Elevate — lived instance becomes a new prime under its origin; "
                "the lived copy rebinds to that prime.",
                "Containment — anything can hold anything "
                "(room→people; person→sense / archetype).",
                "Links — typed paths between places (spatial, dimensional, temporal, …).",
                "Realm / timeline — dimensional and temporal layers on instances; "
                "coords read as REALM / TIMELINE.",
                "Records — revision history on a place instance or on a prime VEN.",
                "Folio — ordered leaves (chapters); open with folio open …",
            ),
            fmt.section("See also"),
            fmt.example_line("help create"),
            fmt.example_line("help kinds"),
            fmt.example_line("help folio"),
            fmt.example_line("help timeline"),
            fmt.example_line("help realm"),
            fmt.example_line("help record"),
            fmt.example_line("help elevate"),
            fmt.example_line("help compose"),
            fmt.example_line("help lineage"),
        ),
    }


_init_topics()
