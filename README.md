# snip

## NOTE TO SELF 
**snip.py** may be better but should test both main.py and snip.py first

A fast terminal-first snippet manager for code examples and cheat sheets.

## Features

- Add snippets using your editor.
- Import existing Markdown files.
- Tag-based search.
- Terminal UI built with Textual and Rich Markdown rendering.
- Simple stats and listing commands.

## Install

```bash
git clone <repo>
cd <repo>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `requirements.txt` with:

```
textual
rich
click
```

## Usage

Open the TUI:

```bash
python3 snip.py
# or if installed as executable
snip
```

Search from shell:

```bash
snip python files
# or
python3 snip.py python files
```

Commands:

```
snip add
snip import-file /path/to/file.md
snip list
snip stats
snip dir
```

Config:

- Storage directory: `.snippets` in the current working directory.
- Files directory: `.snippets/files`
- DB file: `.snippets/snippets.db`
- Editor: `$EDITOR` or `$VISUAL` or `vim` by default.

## Notes and fixes included

- Ensures `.snippets` and `.snippets/files` directories are created with parents=True.
- Handles missing snippet descriptions safely.
- Displays a clear error message in the TUI when a snippet's file is missing.
- Ensures the TUI closes the DB connection on unmount.

## Recommendations

- Normalize tags on insert for consistent search and counts (lowercase + strip).
- Consider adding a migration table if you plan schema changes.
