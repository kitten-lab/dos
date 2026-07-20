# Origin

**Digital Office Spaces (DOS)** was branched from **World Builder Studio** on 2026-07-20 as a product-focused copy, not a git fork with full history.

| | |
|--|--|
| Source tree | `C:\Builds\world-studio` |
| Source remote (at branch time) | `https://github.com/kitten-lab/aidm-world-studio.git` |
| Source branch tip | `polish/desc-commit-lore-flags-arrow` (plus local uncommitted polish in that tree — copy used on-disk files at branch time) |
| This repo | `C:\Builds\digital-office-spaces` |
| Package | `digital_office_spaces` |
| Product | Digital Office Spaces (**DOS**) |

## Why a clean history

- New product identity and commit story (office collab, not multiverse WBS changelog).
- No baggage from world-studio branches, worlds, or backup DBs.
- Ready for a dedicated GitHub repository and tidy initial commit.

## What was copied

- Python package (renamed `world_studio` → `digital_office_spaces`)
- Tests, docs stubs, scripts, schema, seeds
- Excluded: `.git`, `__pycache__`, egg-info, `worlds/`, `backup-worlds/`, virtualenvs

## Product intent (DOS)

Focus the tool on a **world space builder for collaborative digital offices**: agents and humans working across the world and wires; starting with collaborative human storage of **data, schedules, and chats** inside a **TUI** (other front ends optional later; TUI continues).
