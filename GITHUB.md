# GitHub setup — Digital Office Spaces

Local repo is prepared with a clean initial commit on `main`. Create a remote, then push.

## Option A — GitHub CLI (`gh`)

```powershell
cd C:\Builds\digital-office-spaces

# Create under your user or org (pick one)
gh repo create digital-office-spaces --private --source=. --remote=origin --description "Digital Office Spaces (DOS) — collaborative office world builder (TUI)"
# or: gh repo create kitten-lab/digital-office-spaces --private --source=. --remote=origin ...

git push -u origin main
```

## Option B — Manual remote

1. Create an empty repo on GitHub (no README, no .gitignore).
2. Then:

```powershell
cd C:\Builds\digital-office-spaces
git remote add origin https://github.com/<owner>/digital-office-spaces.git
git push -u origin main
```

## Commit hygiene

- Keep `worlds/` and `*.world.db` out of git (see `.gitignore`).
- Prefer small, focused commits after this baseline.
- Do not force-push `main` unless you mean to rewrite history.

## Suggested next commits (product)

1. Office seed world (lobby / desks / meeting room) replacing story-default as product default.
2. First-class **schedule** and **chat** storage surfaces in-space.
3. Docs: collaboration model (human + agent sessions).
