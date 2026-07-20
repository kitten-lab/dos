# Changelog

Short record of **shipped** work. Newest first.  
Ideas and doctrine live in [IDEAS.md](IDEAS.md) and [docs/product-map.md](docs/product-map.md).

Format: dated bullets, one line each — what landed, not a full story.

---

## 2026-07-20 — Digital Office Spaces (product branch)

- **Fork baseline:** clean copy of world-studio engine into `dos` with **new git history** (no parent commit graph)
- Package rename: `world_studio` → `dos`; CLI `dos` / `dos`
- Product name **Digital Office Spaces (DOS)**; docs orient to collaborative office spaces (data, schedules, chats, TUI-first)
- Add [ORIGIN.md](ORIGIN.md), [GITHUB.md](GITHUB.md); refresh README / IDEAS / product-map intro for DOS
- **Seeds:** default **`office`** (company campus on the Wire — lobby, floor, meeting, records; handbook / channel / calendar / cabinet). **`empty`** suite for build-from-inside. **`bootstrap`** kept for kernel tests. Story / classic / tavern removed from product CLI (WBS fixtures remain under `tests/wbs_seed_fixtures.py` only)
- **Rename to `dos`:** package / module / CLI / folder / GitHub (`kitten-lab/dos`) — DOS, again

## 2026-07-16

- **locate self:** avatar where-now readout (replaces status as the preferred verb); bare `locate` same; `locate <code>` reserved/planned; temporary aliases status/sit/whereami/where
- **retime:** `retime HST-NNN when @N` (or `--when` / bare `@N` / `unknown`) rewrites story when on every leg of that event; undo restores prior stamps
- **History where:** each row stores place + realm + timeline ids and snapshotted names; list lines show `Place · Realm / Timeline`
- **Rename history:** `rename` / `call` writes a `rename` life-of-item row on the instance (`Old → New`, optional `when @N` / `--when`, shared `HST-…`)
- **History event codes:** shared `HST-NNN` on all legs of one act; `history HST-001` / `history event …` lists every subject; lines show the code
- **Movement legs expanded:** take/drop also record place + player; spawn onto floor records place `receive`; put/take-from keep vessel; `history me` / `history here`
- **Movement history:** `take` / `drop` / `put` write life-of-item rows; put and take-from also record the vessel (`receive` / `give`); optional `when @N` / `--when N` (default `@unknown`, own craft time per act)
- **Create/spawn flags:** free-order `--type/--name/--desc/--when` (and short `-t -n -d -w`); legacy `|` / `when @N` still work
- **History backbone:** timeline nodes + life-of-item `history_entries`; `create`/`spawn`/`lore` take `when @N` or `when @unknown`; `history nodes|here|on|ven` (extended bag/visit/fold ideas kept in product-map, not built)
- Add [docs/product-map.md](docs/product-map.md) — ADM / Silo / AIDM / Forestry / history doctrine in-repo
- Link product map from [IDEAS.md](IDEAS.md)
- Add this changelog

## 2026-07-16 — initial public tree

- Initial commit: World Studio core (`dos`) — lean VEN kinds, folio reader, wiki soft reader, bootstrap Herenow seed, paths vocabulary, tests
- Package name `dos` / module `dos`; product name AIDM World Studio
