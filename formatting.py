from rich.columns import Columns
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()

STATUS_STYLES = {
    "active": "green",
    "new": "yellow",
    "off": "red",
    "archive": "red",
}


def _cell(title, value):
    """Build a Text renderable for a cell. Text() is inserted verbatim (never
    parsed as markup), so a droplet/tag/snapshot name containing '[' can't be
    misread as a style tag."""
    if title == "Status":
        style = STATUS_STYLES.get(str(value).lower(), "white")
        return Text(str(value), style=style)
    return Text(str(value))


def print_table(headers, results=None, preamble=None, footer=None):
    """headers: {column title: data key}. results: list of dicts, each providing every data key."""
    if preamble:
        console.print(preamble, style="bold cyan", markup=False)

    if results:
        table = Table(header_style="bold cyan")
        for title in headers.keys():
            table.add_column(str(title))
        for row in results:
            table.add_row(*[_cell(title, row[key]) for title, key in headers.items()])
        console.print(table)

    if footer:
        for line in footer:
            console.print(line, style="dim", markup=False)


def print_dict(data, preamble=None, footer=None):
    if preamble:
        console.print(preamble, style="bold cyan", markup=False)

    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="bold")
    table.add_column()
    for key, value in data.items():
        table.add_row(Text(str(key)), _cell(key, value))
    console.print(table)

    if footer:
        for line in footer:
            console.print(line, style="dim", markup=False)


def print_columns(items, preamble=None):
    if preamble:
        console.print(preamble, style="bold cyan", markup=False)
    console.print(Columns([Text(str(item)) for item in items]))


def success(message):
    console.print(message, style="green", markup=False)


def error(message):
    console.print(message, style="bold red", markup=False)


def warning(message):
    console.print(message, style="yellow", markup=False)
