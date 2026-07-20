# Origin

**Digital Office Spaces (DOS)** was branched from **World Builder Studio** on 2026-07-20 as a product-focused copy, not a git fork with full history.

| | |
|--|--|
| Source tree | `C:\Builds\world-studio` |
| Source remote (at branch time) | `https://github.com/kitten-lab/aidm-world-studio.git` |
| Source branch tip | `polish/desc-commit-lore-flags-arrow` (plus local uncommitted polish in that tree — copy used on-disk files at branch time) |
| This repo | `C:\Builds\dos` · GitHub `kitten-lab/dos` |
| Package / module / CLI | `dos` |
| Product | Digital Office Spaces (**DOS** — again) |

## Why a clean history

- New product identity and commit story (office collab, not multiverse WBS changelog).
- No baggage from world-studio branches, worlds, or backup DBs.
- Ready for a dedicated GitHub repository and tidy initial commit.

## What was copied

- Python package (renamed `world_studio` → `dos`)
- Tests, docs stubs, scripts, schema, seeds
- Excluded: `.git`, `__pycache__`, egg-info, `worlds/`, `backup-worlds/`, virtualenvs

## Product intent (DOS)

Focus the tool on a **world space builder for collaborative digital offices**: agents and humans working across the world and wires; starting with collaborative human storage of **data, schedules, and chats** inside a **TUI** (other front ends optional later; TUI continues).

## Rename note (2026-07-20)

First layout used `digital-office-spaces` / `digital_office_spaces`. Renamed to **`dos`** everywhere that matters (folder, package, module, CLI, GitHub) so the pun lands: terminal DOS, office DOS.
