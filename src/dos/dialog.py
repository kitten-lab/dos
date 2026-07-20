"""Talk sessions: back-and-forth dialog until /fin."""

from __future__ import annotations

from dataclasses import dataclass, field

from .ids import display_name


FIN_TOKEN = "/fin"
# Indent for spoken lines under a speaker cue (script / play layout)
_SPEECH_INDENT = "    "


@dataclass
class DialogSession:
    """In-progress talk between player and a person instance."""

    partner_id: str
    partner_name: str
    player_id: str
    player_name: str
    place_id: str | None
    timeline_id: str | None
    title: str = ""
    when_label: str | None = None
    turns: list[tuple[str, str]] = field(default_factory=list)
    expect_player: bool = True

    def append_line(self, raw: str) -> tuple[str, str]:
        """
        Append a dialog turn. Returns (speaker_name, text).

        Prefixes:
          /you <text>   — force player line
          /them <text>  — force partner line
        Otherwise alternates player → partner → player …
        """
        line = raw.rstrip("\n\r")
        text = line.strip()
        if not text:
            raise ValueError("Empty line — say something, or /fin to end.")

        low = text.lower()
        if low.startswith("/you "):
            speaker = self.player_name
            text = text[5:].strip()
            self.expect_player = False
        elif low.startswith("/them "):
            speaker = self.partner_name
            text = text[6:].strip()
            self.expect_player = True
        elif self.expect_player:
            speaker = self.player_name
            self.expect_player = False
        else:
            speaker = self.partner_name
            self.expect_player = True

        if not text:
            raise ValueError("Empty line after speaker prefix.")
        self.turns.append((speaker, text))
        return speaker, text

    def transcript_text(self) -> str:
        lines = [f"{sp}: {tx}" for sp, tx in self.turns]
        return "\n".join(lines)

    def display_title(self) -> str:
        return self.title.strip() or "Untitled dialog"


def parse_talk_args(arg: str) -> tuple[str, str, str | None]:
    """
    Parse talk command args → (person_query, title, when_label).

      talk <person>
      talk <person> | <title>
      talk <person> | when <stamp> | <title>
      talk <person> | @<stamp> | <title>
    """
    arg = arg.strip()
    if not arg:
        raise ValueError("Talk to whom?  Usage: talk <person> [| when <stamp> | title]")

    when_label: str | None = None
    title = ""

    if "|" in arg:
        person, rest = arg.split("|", 1)
        person = person.strip()
        rest = rest.strip()
        low = rest.lower()
        if low.startswith("when "):
            rest = rest[5:].strip()
            if "|" in rest:
                stamp, rest = rest.split("|", 1)
                when_label = stamp.strip() or None
                title = rest.strip()
            else:
                # when <stamp> alone treated as stamp with empty title
                when_label = rest.strip() or None
                title = ""
        elif rest.startswith("@"):
            rest = rest[1:]
            if "|" in rest:
                stamp, rest = rest.split("|", 1)
                when_label = stamp.strip() or None
                title = rest.strip()
            else:
                when_label = rest.strip() or None
                title = ""
        else:
            title = rest
    else:
        person = arg

    if not person:
        raise ValueError("Talk to whom?  Name the person before | …")
    return person, title, when_label


def parse_transcript_turns(transcript: str | None) -> list[tuple[str, str]]:
    """
    Parse stored transcript lines ``Speaker: text`` into (speaker, text) turns.

    Lines without ``: `` attach to the previous turn when present (rare multi-line).
    """
    if not transcript or not str(transcript).strip():
        return []
    turns: list[tuple[str, str]] = []
    for raw in str(transcript).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            continue
        if ": " in line:
            sp, tx = line.split(": ", 1)
            turns.append((sp.strip(), tx))
        elif turns:
            prev_sp, prev_tx = turns[-1]
            turns[-1] = (prev_sp, prev_tx + "\n" + line.strip())
        else:
            turns.append(("", line.strip()))
    return turns


def format_script_transcript(transcript: str | None) -> str:
    """
    Script / play layout for a stored transcript (Rich markup).

    Example::

        Builder
            Hello on the ridge.

        The Cartographer
            Hello returned.
    """
    from . import format as fmt

    turns = parse_transcript_turns(transcript)
    if not turns:
        return fmt.hint("(no turns)")
    blocks: list[str] = []
    for speaker, text in turns:
        name = display_name(speaker) if speaker else "—"
        blocks.append(f"[bold]{fmt.safe(name)}[/bold]")
        speech = (text or "").strip() or "…"
        for para in speech.split("\n"):
            p = para.strip() if para.strip() else "…"
            blocks.append(f"{_SPEECH_INDENT}{fmt.safe(p)}")
        blocks.append("")  # blank line between speeches
    # drop trailing blank
    while blocks and blocks[-1] == "":
        blocks.pop()
    return "\n".join(blocks)


def format_script_turn(speaker: str, text: str, *, you_label: str | None = None) -> str:
    """One live turn in the same script style as re-read."""
    from . import format as fmt

    name = display_name(speaker)
    cue = f"[bold]{fmt.safe(name)}[/bold]"
    if you_label:
        cue += f"  [dim]({fmt.safe(you_label)})[/dim]"
    speech = (text or "").strip() or "…"
    lines = [cue]
    for para in speech.split("\n"):
        p = para.strip() if para.strip() else "…"
        lines.append(f"{_SPEECH_INDENT}{fmt.safe(p)}")
    return "\n".join(lines)


def format_transcript_view(
    *,
    title: str,
    when_label: str | None,
    speaker_a: str,
    speaker_b: str,
    transcript: str,
    created_at: str,
    dialog_id: str,
    dialog_slug: str | None = None,
) -> str:
    """Full re-read view: title, cast, meta, script body (Rich markup)."""
    from . import format as fmt

    stamp = (when_label or "").strip() or "—"
    ttl = (title or "").strip() or "Untitled dialog"
    a = display_name(speaker_a)
    b = display_name(speaker_b)
    handle = (dialog_slug or "").strip() or dialog_id
    return fmt.join_blocks(
        fmt.title_line(ttl),
        fmt.hint(f"{a}  &  {b}"),
        fmt.hint(f"when {stamp}  ·  typed {created_at}  ·  {handle}"),
        format_script_transcript(transcript),
        gap=1,
    )


def parse_when_stamp(raw: str) -> str | None:
    """
    Parse a when-stamp payload (lore/talk style).

    Accepts:
      when Before the Roads
      @1704067200
      Before the Roads
      clear / - / none  → None (clear stamp)

    Returns the stamp string, or None to clear. Raises ValueError if empty
    after stripping keywords (and not a clear token).
    """
    from .textutil import unescape_desc

    s = (raw or "").strip()
    if not s:
        raise ValueError(
            "When stamp required.  e.g. when Before the Roads  ·  @2024-06-15  ·  clear"
        )
    low = s.lower()
    if low in ("clear", "-", "none", "off", "unset"):
        return None
    if low.startswith("when "):
        s = s[5:].strip()
    elif s.startswith("@"):
        s = s[1:].strip()
    if not s:
        raise ValueError("Empty when stamp.  Use clear to remove a stamp.")
    if s.lower() in ("clear", "-", "none", "off", "unset"):
        return None
    return unescape_desc(s)


def parse_dialog_when_line(line: str) -> str | None:
    """
    Mid-dialog meta: ``/when <stamp>`` → new when_label (or None if clear).

    Raises ValueError if not a /when line or stamp is invalid.
    """
    text = line.strip()
    low = text.lower()
    if not low.startswith("/when"):
        raise ValueError("not a when command")
    rest = text[5:].strip()  # after /when
    if rest.startswith(":"):
        rest = rest[1:].strip()
    return parse_when_stamp(rest if rest else "clear")


def dialog_teaser_line(
    *,
    title: str | None,
    when_label: str | None,
    transcript: str | None,
    max_cue: int = 48,
) -> str:
    """Short one-line teaser for last dialog (plain text, no markup)."""
    ttl = (title or "").strip() or "Untitled dialog"
    stamp = (when_label or "").strip()
    cue = ""
    if transcript:
        first = transcript.strip().split("\n", 1)[0].strip()
        if first:
            if len(first) > max_cue:
                first = first[: max_cue - 1] + "…"
            cue = first
    parts = [ttl]
    if stamp:
        parts.append(f"when {stamp}")
    if cue:
        parts.append(cue)
    return " · ".join(parts)


def person_inner_kinds() -> frozenset[str]:
    """VEN kinds treated as inner life on people (feelings, goals, archetypes, …)."""
    from .world import INNER_LIFE_KINDS

    return INNER_LIFE_KINDS
