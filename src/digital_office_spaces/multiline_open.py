"""Parse << / <<studio openers for desc, book page, and lore."""

from __future__ import annotations

import re

from .text_editor import MultilineSession, editor_title_for

_END_MARKERS = ("<<studio", "<<")


def _strip_heredoc(s: str) -> tuple[str, bool] | None:
    """Remove trailing << or <<studio; return (rest, studio) or None."""
    raw = s.strip()
    low = raw.lower()
    for end in _END_MARKERS:
        if low.endswith(end):
            rest = raw[: -len(end)].strip()
            studio = end == "<<studio" or "studio" in low
            # bare <<studio without trailing only
            if end == "<<studio":
                studio = True
            elif end == "<<":
                studio = False
            return rest, studio
    return None


def is_multiline_opener(line: str) -> bool:
    """True if line is a known << / <<studio text-insert opener."""
    return parse_multiline_opener(line) is not None


def parse_multiline_opener(line: str) -> MultilineSession | None:
    """
    Parse a command line that opens the buffer editor.

    Supported:
      @desc <<  ·  @desc <<studio  ·  @desc on <match> <<studio
      book page add|edit … <<[studio]
      lore add … <<[studio]
      lore on <match> add … <<[studio]
      lore ven <name> add … <<[studio]
    """
    s = line.strip()
    if not s or "<<" not in s:
        return None
    low = s.lower()

    if low.startswith("@desc"):
        return _parse_desc(s)
    if low.startswith(
        ("book page ", "folio page ", "book leaf ", "folio leaf ")
    ):
        return _parse_book(s)
    if low.startswith("lore "):
        return _parse_lore(s)
    return None


def _parse_desc(s: str) -> MultilineSession | None:
    # @desc …
    rest = s[5:].strip()  # after @desc
    stripped = _strip_heredoc(rest)
    if stripped is None:
        # whole rest is only <<
        low = rest.lower()
        if low in ("<<", "<<studio", "{", "{studio"):
            studio = "studio" in low
            sess = MultilineSession(kind="desc", studio=studio, desc_rest="")
            sess.title = editor_title_for(sess)
            return sess
        return None
    body_prefix, studio = stripped
    # body_prefix may be "on quill" or empty or garbage; do not allow leftover text as set
    # if body_prefix has non-on content that's not empty without on — only allow on …
    if body_prefix and not body_prefix.lower().startswith("on "):
        # e.g. @desc something << — invalid for multiline (use one-line @desc)
        # unless empty was already handled
        if body_prefix.strip():
            # allow only "on <match>"
            return None
    sess = MultilineSession(
        kind="desc",
        studio=studio,
        desc_rest=body_prefix.strip(),
    )
    sess.title = editor_title_for(sess)
    return sess


def _parse_book(s: str) -> MultilineSession | None:
    # Delayed import avoids circular load with cli
    from . import cli as cli_mod

    meta = cli_mod._parse_book_page_multiline_start(s)
    if meta is None:
        return None
    sess = MultilineSession(
        kind="book_page",
        studio=bool(meta.get("studio")),
        book_meta=meta,
    )
    sess.title = editor_title_for(sess)
    return sess


def _parse_lore(s: str) -> MultilineSession | None:
    """
    lore add [when … | | @stamp |] [title] <<studio
    lore on <match> add [when … |] [title] <<studio
    lore ven <name> add [when … |] [title] <<studio
    """
    rest = s[5:].strip()  # after "lore "
    low = rest.lower()

    scope = "place"
    target = ""
    add_part = rest

    if low.startswith("on "):
        # lore on <match> add …
        after_on = rest[3:].strip()
        m = re.search(r"\s+add\b", after_on, flags=re.IGNORECASE)
        if not m:
            return None
        target = after_on[: m.start()].strip()
        add_part = after_on[m.end() :].strip()
        # drop leading "add" already consumed — add_part is after "add"
        scope = "on"
        if not target:
            return None
    elif low.startswith("ven "):
        after_ven = rest[4:].strip()
        m = re.search(r"\s+add\b", after_ven, flags=re.IGNORECASE)
        if not m:
            return None
        target = after_ven[: m.start()].strip()
        add_part = after_ven[m.end() :].strip()
        scope = "ven"
        if not target:
            return None
    elif low.startswith("add"):
        # lore add …
        add_part = rest[3:].strip()
        if add_part.lower().startswith("from "):
            return None  # not multiline
        scope = "place"
    else:
        return None

    stripped = _strip_heredoc(add_part if add_part else "<<")
    # allow "lore add <<studio" where add_part is "<<studio"
    if stripped is None:
        low_a = add_part.lower().strip()
        if low_a in ("<<", "<<studio") or not add_part:
            if low_a in ("<<", "<<studio"):
                studio = "studio" in low_a
                sess = MultilineSession(
                    kind="lore",
                    studio=studio,
                    lore_scope=scope,
                    lore_target=target,
                )
                sess.title = editor_title_for(sess)
                return sess
            return None
        return None

    head, studio = stripped
    title = ""
    when_label = ""
    # optional when / @stamp then title (no body — body is editor)
    if head:
        title, when_label = _parse_lore_head(head)

    sess = MultilineSession(
        kind="lore",
        studio=studio,
        lore_scope=scope,
        lore_target=target,
        lore_title=title,
        lore_when=when_label,
    )
    sess.title = editor_title_for(sess)
    return sess


def _parse_lore_head(head: str) -> tuple[str, str]:
    """Parse optional when-stamp and title from lore add head (no body)."""
    from .commands import parse_lore_add

    # Reuse parse_lore_add by appending empty body if needed
    # head might be "when X | Title" or "Title" or "@stamp | Title"
    h = head.strip()
    if not h:
        return "", ""
    # If parse_lore_add treats whole as body, use as title when no |
    if "|" not in h and not h.lower().startswith("when ") and not h.startswith("@"):
        return h, ""
    # Ensure a body slot so title/when parse
    trial = h if h.rstrip().endswith("|") else f"{h} |"
    parsed = parse_lore_add(trial + " _")
    if not parsed:
        # fallback: whole head is title
        return h, ""
    title, body, when_label = parsed
    if body.strip() in ("_", ""):
        return title, when_label or ""
    # if body absorbed text, prefer title from when form
    return title or h, when_label or ""


def seed_initial_body(world, session: MultilineSession) -> str:
    """Prefill editor buffer (e.g. book page edit, current desc)."""
    from .studio_text import strip_studio_header

    if session.kind == "desc":
        inst = _desc_target(world, session)
        if inst is None:
            return ""
        raw = inst.description or ""
        return strip_studio_header(raw) if session.studio else raw
    if session.kind == "book_page":
        meta = session.book_meta
        if meta.get("action") == "edit":
            from .commands import _resolve_book_here

            book, err = _resolve_book_here(world, meta["book_name"])
            if err or book is None:
                return ""
            try:
                page = world._book_page_row(book.id, int(meta["page"]))
            except Exception:  # noqa: BLE001
                return ""
            raw = page["body"] or ""
            return strip_studio_header(raw) if session.studio else raw
        return ""
    return ""


def seed_page_title(world, session: MultilineSession) -> str | None:
    """
    Prefill page-title chrome when editing an existing book page.

    Returns ``None`` when title chrome should be hidden (not a page edit).
    Returns ``""`` or the current title string when chrome should show.
    """
    if session.kind != "book_page":
        return None
    meta = session.book_meta
    if meta.get("action") != "edit":
        return None
    from .commands import _resolve_book_here

    book, err = _resolve_book_here(world, meta.get("book_name") or "")
    if err or book is None:
        return ""
    try:
        page = world._book_page_row(book.id, int(meta["page"]))
    except Exception:  # noqa: BLE001
        return ""
    return (page["title"] or "") if page is not None else ""

def _desc_target(world, session: MultilineSession):
    rest = session.desc_rest.strip()
    if rest.lower().startswith("on "):
        from .commands import _split_instance_target_and_rest

        thing, _r, err = _split_instance_target_and_rest(world, rest[3:])
        if err or thing is None:
            return None
        return thing
    return world.player_location()


def commit_multiline_session(
    world,
    session: MultilineSession,
    body: str,
    *,
    page_title: str | None = None,
):
    """
    Apply editor body to the world; record text_revision; return CommandResult.

    Shared by REPL and TUI after ``run_text_editor`` returns a non-empty body.
    When *page_title* is not ``None`` and this is a book page **edit**, also
    update the page title (single-page editor chrome).
    """
    from .commands import CommandResult, dispatch
    from . import format as fmt
    from .studio_text import is_studio, prepare_stored_text, with_studio_header
    from .cli import _commit_book_page_multiline

    body = body if body is not None else ""
    if not body.strip():
        return CommandResult(True, fmt.hint("Empty buffer; cancelled."))

    if session.kind == "desc":
        return _commit_desc(world, session, body)
    if session.kind == "book_page":
        line = _commit_book_page_multiline(world, session.book_meta, body)
        result = dispatch(world, line)
        _record_book_revision(world, session, body)
        if (
            result.ok
            and page_title is not None
            and session.book_meta.get("action") == "edit"
        ):
            title_note = _apply_book_page_title(
                world, session, page_title
            )
            if title_note and result.message:
                result = CommandResult(
                    result.ok,
                    result.message + title_note,
                    quit=result.quit,
                    clear_log=result.clear_log,
                    open_book_id=result.open_book_id,
                )
        return result
    if session.kind == "lore":
        return _commit_lore(world, session, body)
    return CommandResult(True, fmt.err(f"Unknown multiline kind {session.kind!r}"))


def _apply_book_page_title(world, session: MultilineSession, page_title: str) -> str:
    """Set page title after body save; returns a short message suffix or \"\"."""
    from .commands import _push_book_page_title_undo, _resolve_book_here
    from . import format as fmt

    meta = session.book_meta
    book, err = _resolve_book_here(world, meta.get("book_name") or "")
    if err or book is None:
        return ""
    try:
        pos = int(meta["page"])
        page = world._book_page_row(book.id, pos)
    except Exception:  # noqa: BLE001
        return ""
    new_title = (page_title or "").strip()
    prior_title = page["title"] or ""
    if new_title == prior_title:
        return ""
    world.set_book_page_title(book.id, pos, new_title)
    _push_book_page_title_undo(
        world,
        page["id"],
        prior_title,
        f"book page title {book.name} {pos}",
    )
    shown = fmt.safe(new_title) if new_title else "(untitled)"
    return f"  ·  title {shown}"


def _fmt_studio(body: str, studio: bool) -> str:
    from .studio_text import prepare_stored_text

    return prepare_stored_text(body, studio=studio)


def _commit_desc(world, session: MultilineSession, body: str):
    """
    Apply editor body to place or ``@desc on <match>`` target.

    Sets description directly (no one-line ``@desc … studio | …`` rebuild).
    Round-tripping through dispatch was gluing ``on <name> studio |`` into the
    body when the match name shared tokens with the payload.
    """
    from .commands import CommandResult
    from . import format as fmt
    from .ids import display_name
    from .studio_text import is_studio, prepare_stored_text

    inst = _desc_target(world, session)
    if inst is None:
        rest = session.desc_rest.strip()
        if rest.lower().startswith("on "):
            return CommandResult(
                False,
                fmt.err(
                    f"No match for {rest[3:].strip()!r}.  "
                    f"Try: examine / inv"
                ),
            )
        return CommandResult(True, fmt.hint("Nowhere."))

    prior = world.get_description_override(inst.id)
    stored = prepare_stored_text(body, studio=bool(session.studio))
    world.set_description(inst.id, stored)

    tid = inst.id
    world.undo_stack.push(
        f"@desc {display_name(inst.name)}",
        lambda w, iid=tid, p=prior: w.set_description(iid, p),
    )

    world.add_text_revision(
        "instance",
        tid,
        stored,
        field="description",
        format="studio" if session.studio or is_studio(stored) else "plain",
        note="editor save",
    )

    ref = world.short_ref_of(tid)
    msg = (
        f"Description updated · "
        f"{fmt.named_ref(display_name(inst.name), ref)}"
    )
    if session.studio or is_studio(stored):
        msg += "  ·  studio text"
    return CommandResult(True, fmt.ok(msg))


def _record_book_revision(world, session: MultilineSession, body: str) -> None:
    from .commands import _resolve_book_here
    from .studio_text import is_studio, prepare_stored_text

    meta = session.book_meta
    stored = prepare_stored_text(body, studio=bool(meta.get("studio")))
    if meta.get("action") == "edit":
        book, err = _resolve_book_here(world, meta["book_name"])
        if err or book is None:
            return
        try:
            page = world._book_page_row(book.id, int(meta["page"]))
        except Exception:  # noqa: BLE001
            return
        world.add_text_revision(
            "book_page",
            page["id"],
            page["body"] or stored,
            field="body",
            title=page["title"] or "",
            format="studio" if is_studio(page["body"] or stored) else "plain",
            note="editor save",
        )
        return
    # add: resolve book and last page
    book_and_title = (meta.get("book_and_title") or "").strip()
    if not book_and_title:
        return
    # Best-effort: find book by first token path via resolve after dispatch
    book, err = _resolve_book_here(world, book_and_title.split()[0])
    if err or book is None:
        # try full string as name
        book, err = _resolve_book_here(world, book_and_title)
    if book is None:
        return
    pages = world.list_book_pages(book.id)
    if not pages:
        return
    page = pages[-1]
    world.add_text_revision(
        "book_page",
        page["id"],
        page["body"] or stored,
        field="body",
        title=page["title"] or "",
        format="studio" if is_studio(page["body"] or stored) else "plain",
        note="editor save",
    )


def _commit_lore(world, session: MultilineSession, body: str):
    from .commands import CommandResult, dispatch
    from .studio_text import prepare_stored_text, is_studio
    from .textutil import escape_desc

    stored = prepare_stored_text(body, studio=session.studio)
    esc = escape_desc(stored if not session.studio else body)
    # Build lore add line
    bits: list[str] = []
    if session.lore_when:
        if session.lore_when.startswith("@"):
            bits.append(session.lore_when)
        else:
            bits.append(f"when {session.lore_when}")
    if session.lore_title:
        bits.append(session.lore_title)
    if session.studio:
        # lore add studio | title | body
        head = " | ".join(bits) if bits else ""
        if head:
            payload = f"studio | {head} | {esc}"
        else:
            payload = f"studio | {esc}"
    else:
        if bits:
            payload = " | ".join(bits) + f" | {esc}"
        else:
            payload = esc

    if session.lore_scope == "on":
        line = f"lore on {session.lore_target} add {payload}"
    elif session.lore_scope == "ven":
        line = f"lore ven {session.lore_target} add {payload}"
    else:
        line = f"lore add {payload}"

    result = dispatch(world, line)
    if result.ok:
        # subject for text log
        if session.lore_scope == "ven":
            ven = world.find_ven(session.lore_target)
            if ven:
                world.add_text_revision(
                    "ven",
                    ven.id,
                    stored,
                    field="lore_body",
                    title=session.lore_title,
                    format="studio" if session.studio or is_studio(stored) else "plain",
                    note="editor lore save",
                )
        else:
            if session.lore_scope == "on":
                inst = world.resolve_here_named(session.lore_target)
            else:
                inst = world.player_location()
            if inst:
                world.add_text_revision(
                    "instance",
                    inst.id,
                    stored,
                    field="lore_body",
                    title=session.lore_title,
                    format="studio" if session.studio or is_studio(stored) else "plain",
                    note="editor lore save",
                )
    return result
