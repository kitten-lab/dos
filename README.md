# Digital Office Spaces (DOS)

**Collaborative digital office world builder** for humans and agents working from anywhere — shared places, data, schedules, and chats inside a **TUI terminal environment** (other front ends may come later; TUI is the focus for now).

This repository is a **clean product branch** of [World Builder Studio](https://github.com/kitten-lab/aidm-world-studio) (`world-studio`): same VEN / instance / place kernel, reoriented toward **office spaces** rather than general multiverse storytelling.

Parked ideas: [`IDEAS.md`](IDEAS.md). Product lineage notes: [`docs/product-map.md`](docs/product-map.md). Lineage / fork note: [`ORIGIN.md`](ORIGIN.md).

## North star

| Focus | Meaning |
|--------|---------|
| **Office space** | Rooms, floors, desks, meeting nooks as navigable VENs / instances |
| **Collaboration** | Humans + agents sharing the same world file / session model |
| **Storage in place** | Documents, schedules, and chat threads live *inside* the space (not only as side panels) |
| **TUI-first** | Terminal REPL + optional Textual UI; portable, scriptable, agent-friendly |
| **Wires worldwide** | Built for remote co-presence: clear locations, exits, and shared state |

Inherited engine concepts (still active under the hood):

| Concept | Meaning |
|--------|---------|
| **VEN** | Prime / canonical virtual entity (place, person, object, …) |
| **Instance** | A situated occurrence of a VEN (this desk *here*, this thread *now*) |
| **Containment** | Any instance may hold others (room → people/objects; person → bag) |
| **Links** | Typed exits between places |
| **Lore / revisions** | Append-only history on a place or entity |

Storage is a single **SQLite** world file (`worlds/*.world.db`). The DB is the source of truth.

## Requirements

- Python 3.11+
- `pip install -r requirements.txt` (or `pip install -e .`)

## Quick start

```powershell
cd C:\Builds\digital-office-spaces
py -3.12 -m pip install -e .
py -3.12 -m digital_office_spaces --reseed
# or, after install:
dos --reseed
```

CLI entry points: `dos`, `digital-office-spaces`, and `python -m digital_office_spaces`.

Default seed is still the inherited **story** world (useful for kernel smoke tests). Office-oriented seeds will land as the product focus hardens.

```powershell
py -3.12 -m digital_office_spaces --reseed --seed bootstrap
py -3.12 -m digital_office_spaces --reseed --seed void
```

### Textual TUI

```powershell
python -m digital_office_spaces --textual --reseed
# or: dos --textual --reseed
```

Plain REPL shows a **situation strip** above each `›` prompt. Use **`locate self`** (or bare **`locate`**) for avatar location. **↑ / ↓** recalls previous commands.

### One-shot commands (scripts / tests)

```powershell
python -m digital_office_spaces -c look -c inv
```

## Development

```powershell
cd C:\Builds\digital-office-spaces
py -3.12 -m pip install -e .
py -3.12 -m pytest tests -q
```

Local world files under `worlds/` are **gitignored** (player/session data — publish deliberately).

## GitHub (clean history)

This tree was initialized with a **fresh git history** (not a clone of world-studio), so the first push is a single clean baseline. See [`GITHUB.md`](GITHUB.md) for remote setup.

## License / attribution

Kernel and command surface derived from World Builder Studio / AIDM world-studio lineage. DOS is the office-collaboration product cut of that engine.
