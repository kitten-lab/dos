"""SQLite connection and schema bootstrap."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)
    migrate_schema(conn)
    conn.commit()


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Idempotent additive migrations for older world.db files."""
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(vens)").fetchall()
    }
    if cols and "parent_ven_id" not in cols:
        conn.execute(
            "ALTER TABLE vens ADD COLUMN parent_ven_id TEXT "
            "REFERENCES vens(id) ON DELETE SET NULL"
        )
    if cols:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_vens_parent ON vens(parent_ven_id)"
        )
    # Compact VEN codes (RLM-001) — typeable handle alongside long cute slugs
    if cols and "code" not in cols:
        conn.execute("ALTER TABLE vens ADD COLUMN code TEXT")
    if cols or "code" in {
        row[1] for row in conn.execute("PRAGMA table_info(vens)").fetchall()
    }:
        from .ids import mint_office_ven_code, parse_ven_code

        rows = conn.execute(
            "SELECT id, kind, code, slug, name FROM vens "
            "ORDER BY kind, created_at, id"
        ).fetchall()
        taken = {
            (r["code"] or "").strip().lower()
            for r in rows
            if (r["code"] or "").strip()
        }
        for r in rows:
            if parse_ven_code(r["code"] or ""):
                continue
            # New / missing: office face from slug (not kind-serial genesis)
            code = mint_office_ven_code(
                r["slug"] or r["name"] or r["kind"] or "item",
                taken=taken,
            )
            taken.add(code)
            conn.execute("UPDATE vens SET code = ? WHERE id = ?", (code, r["id"]))
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_vens_code ON vens(code)"
        )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ven_parts (
            id              TEXT PRIMARY KEY,
            whole_ven_id    TEXT NOT NULL REFERENCES vens(id) ON DELETE CASCADE,
            part_ven_id     TEXT NOT NULL REFERENCES vens(id) ON DELETE CASCADE,
            role            TEXT NOT NULL DEFAULT 'part',
            ordinal         INTEGER NOT NULL DEFAULT 0,
            notes           TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (whole_ven_id, part_ven_id, role)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ven_parts_whole ON ven_parts(whole_ven_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ven_parts_part ON ven_parts(part_ven_id)"
    )
    # Records poster: multiuser-ready author instance / ven ids
    lore_info = conn.execute("PRAGMA table_info(lore_revisions)").fetchall()
    if lore_info:
        lore_cols = {row[1] for row in lore_info}
        if "author_instance_id" not in lore_cols:
            conn.execute(
                "ALTER TABLE lore_revisions ADD COLUMN author_instance_id TEXT"
            )
        if "author_ven_id" not in lore_cols:
            conn.execute(
                "ALTER TABLE lore_revisions ADD COLUMN author_ven_id TEXT"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lore_author_inst "
            "ON lore_revisions(author_instance_id)"
        )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS text_revisions (
            id              TEXT PRIMARY KEY,
            subject_type    TEXT NOT NULL,
            subject_id      TEXT NOT NULL,
            field           TEXT NOT NULL DEFAULT 'body',
            title           TEXT NOT NULL DEFAULT '',
            body            TEXT NOT NULL DEFAULT '',
            format          TEXT NOT NULL DEFAULT 'plain',
            author          TEXT NOT NULL DEFAULT 'builder',
            note            TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_text_rev_subject "
        "ON text_revisions(subject_type, subject_id, created_at)"
    )

    # Dialogs: cute typeable slug (FIRST-MEETING) alongside opaque dlg_ id
    dlg_info = conn.execute("PRAGMA table_info(dialogs)").fetchall()
    if dlg_info:
        dlg_cols = {row[1] for row in dlg_info}
        if "slug" not in dlg_cols:
            conn.execute("ALTER TABLE dialogs ADD COLUMN slug TEXT")
        from .ids import cute_name

        rows = conn.execute(
            "SELECT id, title, slug FROM dialogs ORDER BY created_at, id"
        ).fetchall()
        used: set[str] = set()
        for r in rows:
            existing = (r["slug"] or "").strip()
            if existing:
                used.add(existing.casefold())
                continue
            base = cute_name(r["title"] or "") or "DIALOG"
            if base in ("UNNAMED", ""):
                base = "DIALOG"
            candidate = base
            n = 2
            while candidate.casefold() in used:
                candidate = f"{base}-{n}"
                n += 1
            used.add(candidate.casefold())
            conn.execute(
                "UPDATE dialogs SET slug = ? WHERE id = ?",
                (candidate, r["id"]),
            )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_dialogs_slug ON dialogs(slug)"
        )

    # Story-time nodes + material history (life of item)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS timeline_nodes (
            id                      TEXT PRIMARY KEY,
            timeline_instance_id    TEXT NOT NULL REFERENCES instances(id)
                ON DELETE CASCADE,
            node_index              INTEGER NOT NULL,
            name                    TEXT NOT NULL DEFAULT '',
            description             TEXT NOT NULL DEFAULT '',
            created_at              TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (timeline_instance_id, node_index)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_timeline_nodes_tl "
        "ON timeline_nodes(timeline_instance_id, node_index)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS history_entries (
            id                      TEXT PRIMARY KEY,
            subject_type            TEXT NOT NULL,
            subject_id              TEXT NOT NULL,
            event_code              TEXT NOT NULL DEFAULT '',
            place_instance_id       TEXT REFERENCES instances(id)
                ON DELETE SET NULL,
            place_name              TEXT NOT NULL DEFAULT '',
            realm_instance_id       TEXT REFERENCES instances(id)
                ON DELETE SET NULL,
            realm_name              TEXT NOT NULL DEFAULT '',
            timeline_instance_id    TEXT REFERENCES instances(id)
                ON DELETE SET NULL,
            timeline_name           TEXT NOT NULL DEFAULT '',
            story_when              TEXT NOT NULL DEFAULT '@unknown',
            node_index              INTEGER,
            verb                    TEXT NOT NULL DEFAULT 'record',
            note                    TEXT NOT NULL DEFAULT '',
            created_at              TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    # Older DBs: add event_code and backfill HST-NNN per row
    hist_cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(history_entries)").fetchall()
    }
    if hist_cols and "event_code" not in hist_cols:
        conn.execute(
            "ALTER TABLE history_entries ADD COLUMN event_code TEXT "
            "NOT NULL DEFAULT ''"
        )
        hist_cols.add("event_code")
    if hist_cols and "event_code" in hist_cols:
        from .ids import format_ven_code

        orphans = conn.execute(
            """
            SELECT id FROM history_entries
            WHERE event_code IS NULL OR TRIM(event_code) = ''
            ORDER BY created_at, id
            """
        ).fetchall()
        if orphans:
            max_n = 0
            for r in conn.execute(
                "SELECT event_code FROM history_entries "
                "WHERE event_code GLOB 'HST-[0-9]*'"
            ).fetchall():
                code = (r["event_code"] or "").strip().upper()
                if code.startswith("HST-"):
                    try:
                        max_n = max(max_n, int(code.split("-", 1)[1]))
                    except ValueError:
                        pass
            for r in orphans:
                max_n += 1
                code = format_ven_code("HST", max_n)
                conn.execute(
                    "UPDATE history_entries SET event_code = ? WHERE id = ?",
                    (code, r["id"]),
                )
    # Place + snapshotted names for where-the-act-happened context
    for col, decl in (
        ("place_instance_id", "TEXT"),
        ("place_name", "TEXT NOT NULL DEFAULT ''"),
        ("realm_name", "TEXT NOT NULL DEFAULT ''"),
        ("timeline_name", "TEXT NOT NULL DEFAULT ''"),
    ):
        if hist_cols and col not in hist_cols:
            conn.execute(
                f"ALTER TABLE history_entries ADD COLUMN {col} {decl}"
            )
            hist_cols.add(col)
    # Best-effort fill of missing name snapshots from current instance titles
    # (instances have name_override; formal name lives on the prime VEN)
    _inst_title = (
        "COALESCE(NULLIF(TRIM(i.name_override), ''), v.name, '')"
    )
    if hist_cols and "place_name" in hist_cols:
        conn.execute(
            f"""
            UPDATE history_entries
            SET place_name = COALESCE(
                (
                    SELECT {_inst_title}
                    FROM instances i
                    JOIN vens v ON v.id = i.ven_id
                    WHERE i.id = history_entries.place_instance_id
                ),
                place_name, ''
            )
            WHERE (place_name IS NULL OR TRIM(place_name) = '')
              AND place_instance_id IS NOT NULL
            """
        )
        conn.execute(
            f"""
            UPDATE history_entries
            SET realm_name = COALESCE(
                (
                    SELECT {_inst_title}
                    FROM instances i
                    JOIN vens v ON v.id = i.ven_id
                    WHERE i.id = history_entries.realm_instance_id
                ),
                realm_name, ''
            )
            WHERE (realm_name IS NULL OR TRIM(realm_name) = '')
              AND realm_instance_id IS NOT NULL
            """
        )
        conn.execute(
            f"""
            UPDATE history_entries
            SET timeline_name = COALESCE(
                (
                    SELECT {_inst_title}
                    FROM instances i
                    JOIN vens v ON v.id = i.ven_id
                    WHERE i.id = history_entries.timeline_instance_id
                ),
                timeline_name, ''
            )
            WHERE (timeline_name IS NULL OR TRIM(timeline_name) = '')
              AND timeline_instance_id IS NOT NULL
            """
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_subject "
        "ON history_entries(subject_type, subject_id, created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_timeline "
        "ON history_entries(timeline_instance_id, node_index)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_event_code "
        "ON history_entries(event_code)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_place "
        "ON history_entries(place_instance_id)"
    )


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return row["value"]


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
