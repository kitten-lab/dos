# GitHub — DOS

**Remote:** `https://github.com/kitten-lab/dos` (SSH: `git@github.com:kitten-lab/dos.git`)

Local tree: `C:\Builds\dos`.

## Auth / CLI

```powershell
# GitHub CLI (once): winget install --id GitHub.cli -e
gh auth login
gh auth status
```

## Push

```powershell
cd C:\Builds\dos
git push -u origin main
```

## Optional: rename repo to `dos-again`

If the pun wants a longer slug later:

```powershell
gh repo rename dos-again --yes
git remote set-url origin git@github.com:kitten-lab/dos-again.git
```

Folder can stay `C:\Builds\dos` either way.

## Commit hygiene

- Keep `worlds/` and `*.world.db` out of git (see `.gitignore`).
- Prefer small, focused commits.
- Do not force-push `main` unless you mean to rewrite history.
