#!/usr/bin/env python3
"""
snip - A fast terminal-based snippet manager for code examples and cheat sheets
"""

import os
import sys
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import click
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Input, ListView, ListItem, Label, Static
from textual.binding import Binding
from textual import on
from rich.console import Console
from rich.markdown import Markdown as RichMarkdown
from rich.panel import Panel


# Configuration
#SNIP_DIR = Path.home() / ".snippets"

SNIP_DIR = Path(".snippets")
FILES_DIR = SNIP_DIR / "files"
DB_PATH = SNIP_DIR / "snippets.db"

# Ensure directories exist
SNIP_DIR.mkdir(exist_ok=True)
FILES_DIR.mkdir(exist_ok=True)

console = Console()


class Database:
    """SQLite database manager for snippets"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = None
        self._init_db()
    
    def _init_db(self):
        """Initialize database with schema"""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS snippets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                tags TEXT NOT NULL,
                description TEXT,
                filepath TEXT NOT NULL,
                created DATETIME NOT NULL,
                modified DATETIME NOT NULL
            )
        """)
        
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tags ON snippets(tags)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_title ON snippets(title)")
        self.conn.commit()
    
    def add_snippet(self, title: str, tags: List[str], description: str, filepath: str) -> int:
        """Add a new snippet to the database"""
        now = datetime.now().isoformat()
        tags_str = ",".join(tags)
        
        cursor = self.conn.execute(
            "INSERT INTO snippets (title, tags, description, filepath, created, modified) VALUES (?, ?, ?, ?, ?, ?)",
            (title, tags_str, description, filepath, now, now)
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def update_snippet(self, snippet_id: int, title: str = None, tags: List[str] = None, description: str = None):
        """Update snippet metadata"""
        updates = []
        params = []
        
        if title:
            updates.append("title = ?")
            params.append(title)
        if tags is not None:
            updates.append("tags = ?")
            params.append(",".join(tags))
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        
        if updates:
            updates.append("modified = ?")
            params.append(datetime.now().isoformat())
            params.append(snippet_id)
            
            query = f"UPDATE snippets SET {', '.join(updates)} WHERE id = ?"
            self.conn.execute(query, params)
            self.conn.commit()
    
    def delete_snippet(self, snippet_id: int):
        """Delete a snippet from database"""
        self.conn.execute("DELETE FROM snippets WHERE id = ?", (snippet_id,))
        self.conn.commit()
    
    def search_snippets(self, query: str = "") -> List[Dict]:
        """Search snippets by query (matches title, tags, description)"""
        if not query:
            cursor = self.conn.execute(
                "SELECT * FROM snippets ORDER BY modified DESC"
            )
        else:
            # Split query into terms and search for all of them
            terms = query.lower().split()
            conditions = []
            params = []
            
            for term in terms:
                conditions.append("(LOWER(title) LIKE ? OR LOWER(tags) LIKE ? OR LOWER(description) LIKE ?)")
                search_term = f"%{term}%"
                params.extend([search_term, search_term, search_term])
            
            where_clause = " AND ".join(conditions)
            cursor = self.conn.execute(
                f"SELECT * FROM snippets WHERE {where_clause} ORDER BY modified DESC",
                params
            )
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_snippet(self, snippet_id: int) -> Optional[Dict]:
        """Get a single snippet by ID"""
        cursor = self.conn.execute("SELECT * FROM snippets WHERE id = ?", (snippet_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


def open_editor(filepath: Path, template: str = "") -> bool:
    """Open file in user's preferred editor"""
    # Write template if file doesn't exist
    if template and not filepath.exists():
        filepath.write_text(template)
    
    editor = os.environ.get('EDITOR', os.environ.get('VISUAL', 'vim'))
    
    try:
        subprocess.call([editor, str(filepath)])
        return True
    except Exception as e:
        console.print(f"[red]Error opening editor: {e}[/red]")
        return False


def create_snippet_file(title: str, tags: List[str], description: str) -> Tuple[Optional[Path], Optional[str]]:
    """Create a new snippet file using editor"""
    # Create safe filename from title
    filename = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in title.lower())
    filepath = FILES_DIR / f"{filename}.md"
    
    # Avoid overwrites
    counter = 1
    while filepath.exists():
        filepath = FILES_DIR / f"{filename}_{counter}.md"
        counter += 1
    
    # Create template
    template = f"""# {title}

{description}

## Example

```
// Write your code examples here
// You can use multiple code blocks, add notes, explanations, etc.
```

## Notes

- Add any important points, gotchas, or reminders here
"""
    
    # Open editor
    if open_editor(filepath, template):
        # Check if file has content beyond template
        content = filepath.read_text()
        if content.strip() and len(content) > len(template) * 0.5:  # User added something
            return filepath, content
        else:
            # User didn't add content, delete file
            if filepath.exists():
                filepath.unlink()
            return None, None
    
    return None, None


class SnippetViewer(Container):
    """Widget to display snippet content"""
    
    DEFAULT_CSS = """
    SnippetViewer {
        overflow-y: auto;
        padding: 1 2;
    }
    """
    
    def compose(self) -> ComposeResult:
        from textual.widgets import Markdown
        yield Markdown("", id="markdown_viewer")
    
    def show_snippet(self, snippet: Dict, content: str):
        """Display a snippet with metadata and content"""
        # Build display
        tags_list = snippet['tags'].split(',') if snippet['tags'] else []
        
        header = f"# {snippet['title']}\n\n"
        if tags_list:
            header += f"**Tags:** {', '.join(f'`{tag.strip()}`' for tag in tags_list)}\n\n"
        if snippet['description']:
            header += f"**Description:** {snippet['description']}\n\n"
        header += "---\n\n"
        
        full_content = header + content
        from textual.widgets import Markdown
        markdown_widget = self.query_one("#markdown_viewer", Markdown)
        markdown_widget.update(full_content)
    
    def clear_display(self):
        """Clear the display"""
        from textual.widgets import Markdown
        markdown_widget = self.query_one("#markdown_viewer", Markdown)
        markdown_widget.update("")


class SnippetApp(App):
    """TUI for browsing and searching snippets"""
    
    CSS = """
    Screen {
        background: $background;
    }
    
    #search_container {
        height: auto;
        padding: 1;
        background: $panel;
    }
    
    #main_container {
        height: 1fr;
    }
    
    #snippet_list {
        width: 40%;
        border-right: solid $primary;
    }
    
    #snippet_viewer {
        width: 60%;
    }
    
    .snippet-item {
        padding: 1;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("enter", "open_snippet", "Open"),
    ]
    
    def __init__(self, initial_query: str = ""):
        super().__init__()
        self.db = Database(DB_PATH)
        self.snippets: List[Dict] = []
        self.initial_query = initial_query
    
    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="search_container"):
            yield Input(placeholder="Search snippets by title, tags, or description...", id="search_input")
        with Horizontal(id="main_container"):
            yield ListView(id="snippet_list")
            yield SnippetViewer(id="snippet_viewer")
        yield Footer()
    
    def on_mount(self) -> None:
        """Load snippets when app starts"""
        search_input = self.query_one("#search_input", Input)
        if self.initial_query:
            search_input.value = self.initial_query
        else:
            self.update_list()
        search_input.focus()
    
    def update_list(self, query: str = ""):
        """Update snippet list based on search query"""
        snippet_list = self.query_one("#snippet_list", ListView)
        viewer = self.query_one("#snippet_viewer", SnippetViewer)
        
        # Search database
        self.snippets = self.db.search_snippets(query)
        
        # Update list
        snippet_list.clear()
        for snippet in self.snippets:
            tags = snippet['tags'].split(',') if snippet['tags'] else []
            tags_str = f"[{', '.join(t.strip() for t in tags)}]" if tags else ""
            desc = snippet['description'][:60] + "..." if len(snippet['description']) > 60 else snippet['description']
            
            label_text = f"{snippet['title']}\n{tags_str}\n{desc}" if desc else f"{snippet['title']}\n{tags_str}"
            snippet_list.append(ListItem(Label(label_text)))
        
        # Show first snippet if any
        if self.snippets:
            snippet_list.index = 0
            self.show_snippet_at_index(0)
        else:
            viewer.clear_display()
    
    def show_snippet_at_index(self, index: int):
        """Display snippet at given index"""
        if 0 <= index < len(self.snippets):
            snippet = self.snippets[index]
            viewer = self.query_one("#snippet_viewer", SnippetViewer)
            
            # Read file content
            filepath = Path(snippet['filepath'])
            if filepath.exists():
                content = filepath.read_text()
                viewer.show_snippet(snippet, content)
            else:
                viewer.update(f"Error: File not found at {filepath}")
    
    @on(Input.Changed, "#search_input")
    def on_search_change(self, event: Input.Changed) -> None:
        """Update list when search changes"""
        self.update_list(event.value)
    
    @on(ListView.Highlighted)
    def on_list_highlight(self, event: ListView.Highlighted) -> None:
        """Show snippet when highlighted"""
        snippet_list = self.query_one("#snippet_list", ListView)
        if snippet_list.index is not None:
            self.show_snippet_at_index(snippet_list.index)
    
    def action_open_snippet(self) -> None:
        """Open selected snippet in editor"""
        snippet_list = self.query_one("#snippet_list", ListView)
        if snippet_list.index is not None and 0 <= snippet_list.index < len(self.snippets):
            snippet = self.snippets[snippet_list.index]
            filepath = Path(snippet['filepath'])
            if filepath.exists():
                open_editor(filepath)
                # Reload the snippet after editing
                self.show_snippet_at_index(snippet_list.index)


# CLI Commands
@click.group()
def cli():
    """snip - Fast snippet manager for code examples and cheat sheets
    
    Examples:
      snip                  Open browser
      snip python files     Search for snippets with 'python' and 'files'
      snip add              Add a new snippet
    """
    pass


@cli.command()
def add():
    """Add a new snippet interactively"""
    console.print("[bold cyan]Add New Snippet[/bold cyan]\n")
    
    title = click.prompt("Title")
    if not title.strip():
        console.print("[red]Title cannot be empty[/red]")
        return
    
    tags_input = click.prompt("Tags (comma-separated, e.g. 'python,files,io')")
    tags = [t.strip() for t in tags_input.split(',') if t.strip()]
    if not tags:
        console.print("[red]At least one tag is required[/red]")
        return
    
    description = click.prompt("Description (short summary)", default="")
    
    console.print(f"\n[yellow]Opening {os.environ.get('EDITOR', 'vim')} to write your snippet...[/yellow]")
    console.print("[dim]Write your code examples, notes, and explanations. Save and close when done.[/dim]\n")
    
    filepath, content = create_snippet_file(title, tags, description)
    
    if filepath and content:
        # Add to database
        db = Database(DB_PATH)
        snippet_id = db.add_snippet(title, tags, description, str(filepath))
        db.close()
        
        console.print(f"\n[green]✓[/green] Snippet '[bold]{title}[/bold]' created successfully!")
        console.print(f"[dim]ID: {snippet_id} | File: {filepath}[/dim]")
    else:
        console.print("[yellow]Snippet creation cancelled (no content added)[/yellow]")


@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
def import_file(file_path):
    """Import an existing markdown file as a snippet"""
    filepath = Path(file_path)
    
    if not filepath.suffix == '.md':
        console.print("[red]Only markdown (.md) files can be imported[/red]")
        return
    
    console.print(f"[bold cyan]Importing: {filepath.name}[/bold cyan]\n")
    
    # Read file to show preview
    content = filepath.read_text()
    console.print(Panel(content[:300] + "..." if len(content) > 300 else content, 
                       title="Preview", border_style="dim"))
    console.print()
    
    # Prompt for metadata
    title = click.prompt("Title", default=filepath.stem)
    tags_input = click.prompt("Tags (comma-separated)")
    tags = [t.strip() for t in tags_input.split(',') if t.strip()]
    
    if not tags:
        console.print("[red]At least one tag is required[/red]")
        return
    
    description = click.prompt("Description", default="")
    
    # Copy file to snippets directory
    new_filepath = FILES_DIR / filepath.name
    counter = 1
    while new_filepath.exists():
        new_filepath = FILES_DIR / f"{filepath.stem}_{counter}{filepath.suffix}"
        counter += 1
    
    new_filepath.write_text(content)
    
    # Add to database
    db = Database(DB_PATH)
    snippet_id = db.add_snippet(title, tags, description, str(new_filepath))
    db.close()
    
    console.print(f"\n[green]✓[/green] Imported '[bold]{title}[/bold]' successfully!")
    console.print(f"[dim]ID: {snippet_id} | File: {new_filepath}[/dim]")


@cli.command()
def list():
    """List all snippets"""
    db = Database(DB_PATH)
    snippets = db.search_snippets()
    db.close()
    
    if not snippets:
        console.print("[yellow]No snippets found. Use 'snip add' to create one![/yellow]")
        return
    
    console.print(f"[bold cyan]Found {len(snippets)} snippets:[/bold cyan]\n")
    
    for snippet in snippets:
        tags = snippet['tags'].split(',') if snippet['tags'] else []
        tags_str = f"[{', '.join(t.strip() for t in tags)}]"
        
        console.print(f"[bold]{snippet['title']}[/bold] {tags_str}")
        if snippet['description']:
            console.print(f"  [dim]{snippet['description']}[/dim]")
        console.print()


@cli.command()
def stats():
    """Show statistics about your snippets"""
    db = Database(DB_PATH)
    snippets = db.search_snippets()
    db.close()
    
    if not snippets:
        console.print("[yellow]No snippets yet![/yellow]")
        return
    
    # Collect stats
    all_tags = []
    for snippet in snippets:
        tags = snippet['tags'].split(',') if snippet['tags'] else []
        all_tags.extend([t.strip() for t in tags])
    
    from collections import Counter
    tag_counts = Counter(all_tags)
    
    console.print(f"[bold cyan]Snippet Statistics[/bold cyan]\n")
    console.print(f"Total snippets: [bold]{len(snippets)}[/bold]")
    console.print(f"Unique tags: [bold]{len(tag_counts)}[/bold]\n")
    console.print("[bold]Top 10 tags:[/bold]")
    
    for tag, count in tag_counts.most_common(10):
        console.print(f"  {tag}: {count}")


@cli.command()
def dir():
    """Show the snippets directory path"""
    console.print(f"[cyan]Snippets directory:[/cyan] {SNIP_DIR}")
    console.print(f"[cyan]Files directory:[/cyan] {FILES_DIR}")
    console.print(f"[cyan]Database:[/cyan] {DB_PATH}")


if __name__ == "__main__":
    # Handle the case where no command is given or search terms are provided
    # If first arg is not a known command, treat everything as search
    known_commands = ['add', 'import-file', 'list', 'stats', 'dir']
    
    if len(sys.argv) == 1:
        # No arguments - open TUI
        app = SnippetApp(initial_query="")
        app.run()
    elif sys.argv[1] not in known_commands and not sys.argv[1].startswith('-'):
        # User is searching, not running a command
        search_query = " ".join(sys.argv[1:])
        app = SnippetApp(initial_query=search_query)
        app.run()
    else:
        # Run normal Click command handling
        cli()
