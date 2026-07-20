-- VEN World Studio schema
-- Everything narratively real is a Virtual Entity (VEN) and/or an Instance of one.

PRAGMA foreign_keys = ON;

-- Prime / canonical virtual entities (archetypal identities)
CREATE TABLE IF NOT EXISTS vens (
    id              TEXT PRIMARY KEY,
    slug            TEXT NOT NULL UNIQUE,
    -- Compact typeable code: RLM-001, OBJ-014 (kind prefix + seq). Unique when set.
    code            TEXT,
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL,
    -- kind: place | person | object | event | archetype | feeling |
    --       goal | desire | purpose | realm | timeline | material |
    --       concept | book | other
    -- feeling-group may store meta_json.subtype (e.g. feeling/longing)
    description     TEXT NOT NULL DEFAULT '',
    is_prime        INTEGER NOT NULL DEFAULT 1,
    -- If this prime was elevated from a lived instance:
    elevated_from_instance_id TEXT,
    -- Conceptual specialization parent (FILE → Secret Document); NULL = root
    parent_ven_id   TEXT REFERENCES vens(id) ON DELETE SET NULL,
    tags_json       TEXT NOT NULL DEFAULT '[]',
    meta_json       TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_vens_kind ON vens(kind);
CREATE INDEX IF NOT EXISTS idx_vens_name ON vens(name);
-- idx_vens_code / idx_vens_parent created in migrate_schema when columns exist

-- Prime-level composition: whole VEN is made of other primes (concept/archetype/…)
-- Distinct from instance containment (rooms, inventory, inner life).
CREATE TABLE IF NOT EXISTS ven_parts (
    id              TEXT PRIMARY KEY,
    whole_ven_id    TEXT NOT NULL REFERENCES vens(id) ON DELETE CASCADE,
    part_ven_id     TEXT NOT NULL REFERENCES vens(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'part',
    -- role examples: part | concept | archetype | motif | material | feeling | other
    ordinal         INTEGER NOT NULL DEFAULT 0,
    notes           TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (whole_ven_id, part_ven_id, role)
);

CREATE INDEX IF NOT EXISTS idx_ven_parts_whole ON ven_parts(whole_ven_id);
CREATE INDEX IF NOT EXISTS idx_ven_parts_part ON ven_parts(part_ven_id);

-- Situated occurrences of a VEN in the multiverse
CREATE TABLE IF NOT EXISTS instances (
    id              TEXT PRIMARY KEY,
    ven_id          TEXT NOT NULL REFERENCES vens(id) ON DELETE CASCADE,
    name_override   TEXT,
    description_override TEXT,
    -- Optional layering (realm/timeline as instances of realm/timeline VENs)
    realm_instance_id    TEXT REFERENCES instances(id) ON DELETE SET NULL,
    timeline_instance_id TEXT REFERENCES instances(id) ON DELETE SET NULL,
    state_json      TEXT NOT NULL DEFAULT '{}',
    -- If this instance was promoted to a new prime VEN:
    became_prime_ven_id TEXT REFERENCES vens(id) ON DELETE SET NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_instances_ven ON instances(ven_id);
CREATE INDEX IF NOT EXISTS idx_instances_realm ON instances(realm_instance_id);
CREATE INDEX IF NOT EXISTS idx_instances_timeline ON instances(timeline_instance_id);

-- Flexible containment: places hold people/objects; people hold feelings/archetypes; etc.
CREATE TABLE IF NOT EXISTS containment (
    id                      TEXT PRIMARY KEY,
    container_instance_id   TEXT NOT NULL REFERENCES instances(id) ON DELETE CASCADE,
    contained_instance_id   TEXT NOT NULL UNIQUE REFERENCES instances(id) ON DELETE CASCADE,
    slot                    TEXT NOT NULL DEFAULT 'interior',
    -- slot examples: interior | inventory | worn | feeling | memory | motif | event
    ordinal                 INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_containment_container ON containment(container_instance_id);
CREATE INDEX IF NOT EXISTS idx_containment_slot ON containment(slot);

-- Directed links (exits, temporal jumps, dimensional gates, narrative threads)
CREATE TABLE IF NOT EXISTS links (
    id                  TEXT PRIMARY KEY,
    from_instance_id    TEXT NOT NULL REFERENCES instances(id) ON DELETE CASCADE,
    to_instance_id      TEXT NOT NULL REFERENCES instances(id) ON DELETE CASCADE,
    label               TEXT NOT NULL,
    link_type           TEXT NOT NULL DEFAULT 'spatial',
    -- link_type: spatial | dimensional | temporal | narrative | conditional
    requirements_json   TEXT NOT NULL DEFAULT '{}',
    meta_json           TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_links_from ON links(from_instance_id);
CREATE INDEX IF NOT EXISTS idx_links_to ON links(to_instance_id);

-- Lore revisions: robust history for a subject over in-world or real time
CREATE TABLE IF NOT EXISTS lore_revisions (
    id                  TEXT PRIMARY KEY,
    subject_type        TEXT NOT NULL CHECK (subject_type IN ('ven', 'instance')),
    subject_id          TEXT NOT NULL,
    timeline_instance_id TEXT REFERENCES instances(id) ON DELETE SET NULL,
    -- Optional in-world when-label (epoch name, year, "before the shatter")
    when_label          TEXT,
    title               TEXT NOT NULL DEFAULT '',
    body                TEXT NOT NULL,
    author              TEXT NOT NULL DEFAULT 'builder',
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_lore_subject ON lore_revisions(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_lore_timeline ON lore_revisions(timeline_instance_id);

-- Completed dialog transcripts (talk sessions ended with /fin)
CREATE TABLE IF NOT EXISTS dialogs (
    id                      TEXT PRIMARY KEY,
    slug                    TEXT,  -- cute typeable handle: FIRST-MEETING, RIDGE-TALK-2
    title                   TEXT NOT NULL DEFAULT '',
    when_label              TEXT,
    place_instance_id       TEXT REFERENCES instances(id) ON DELETE SET NULL,
    timeline_instance_id    TEXT REFERENCES instances(id) ON DELETE SET NULL,
    speaker_a_id            TEXT,
    speaker_b_id            TEXT,
    speaker_a_name          TEXT NOT NULL DEFAULT '',
    speaker_b_name          TEXT NOT NULL DEFAULT '',
    transcript              TEXT NOT NULL DEFAULT '',
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_dialogs_place ON dialogs(place_instance_id);
CREATE INDEX IF NOT EXISTS idx_dialogs_created ON dialogs(created_at);
-- idx_dialogs_slug created in migrate_schema after slug column is ensured
-- (CREATE TABLE IF NOT EXISTS leaves older dialogs tables without slug)

-- Ordered pages for book-kind instances (larger texts outside lore)
CREATE TABLE IF NOT EXISTS book_pages (
    id                  TEXT PRIMARY KEY,
    book_instance_id    TEXT NOT NULL REFERENCES instances(id) ON DELETE CASCADE,
    position            INTEGER NOT NULL,
    title               TEXT NOT NULL DEFAULT '',
    body                TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (book_instance_id, position)
);

CREATE INDEX IF NOT EXISTS idx_book_pages_book ON book_pages(book_instance_id, position);

-- Append-only snapshots from the nano-like text editor (<< / <<studio saves)
CREATE TABLE IF NOT EXISTS text_revisions (
    id              TEXT PRIMARY KEY,
    subject_type    TEXT NOT NULL,
    -- instance | ven | book_page | lore
    subject_id      TEXT NOT NULL,
    field           TEXT NOT NULL DEFAULT 'body',
    -- description | body | lore_body
    title           TEXT NOT NULL DEFAULT '',
    body            TEXT NOT NULL DEFAULT '',
    format          TEXT NOT NULL DEFAULT 'plain',
    -- plain | studio
    author          TEXT NOT NULL DEFAULT 'builder',
    note            TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_text_rev_subject
    ON text_revisions(subject_type, subject_id, created_at);

-- Active walker / builder avatar for this world file
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Timeline story-time nodes (numbered notches along a timeline instance)
CREATE TABLE IF NOT EXISTS timeline_nodes (
    id                      TEXT PRIMARY KEY,
    timeline_instance_id    TEXT NOT NULL REFERENCES instances(id) ON DELETE CASCADE,
    node_index              INTEGER NOT NULL,
    name                    TEXT NOT NULL DEFAULT '',
    description             TEXT NOT NULL DEFAULT '',
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (timeline_instance_id, node_index)
);

CREATE INDEX IF NOT EXISTS idx_timeline_nodes_tl
    ON timeline_nodes(timeline_instance_id, node_index);

-- Story-when history for materials (life of ven / instance / lore)
CREATE TABLE IF NOT EXISTS history_entries (
    id                      TEXT PRIMARY KEY,
    subject_type            TEXT NOT NULL,
    -- ven | instance | lore
    subject_id              TEXT NOT NULL,
    -- Shared across all legs of one act (put + receive, take + give + receive)
    event_code              TEXT NOT NULL DEFAULT '',
    -- Where the act happened (place + layers); names snapshotted at craft time
    place_instance_id       TEXT REFERENCES instances(id) ON DELETE SET NULL,
    place_name              TEXT NOT NULL DEFAULT '',
    realm_instance_id       TEXT REFERENCES instances(id) ON DELETE SET NULL,
    realm_name              TEXT NOT NULL DEFAULT '',
    timeline_instance_id    TEXT REFERENCES instances(id) ON DELETE SET NULL,
    timeline_name           TEXT NOT NULL DEFAULT '',
    story_when              TEXT NOT NULL DEFAULT '@unknown',
    -- @0, @3, @unknown
    node_index              INTEGER,
    verb                    TEXT NOT NULL DEFAULT 'record',
    note                    TEXT NOT NULL DEFAULT '',
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_history_subject
    ON history_entries(subject_type, subject_id, created_at);
CREATE INDEX IF NOT EXISTS idx_history_timeline
    ON history_entries(timeline_instance_id, node_index);
CREATE INDEX IF NOT EXISTS idx_history_event_code
    ON history_entries(event_code);
CREATE INDEX IF NOT EXISTS idx_history_place
    ON history_entries(place_instance_id);

