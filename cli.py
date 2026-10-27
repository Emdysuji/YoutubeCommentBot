from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.status import Status
from datetime import datetime

console = Console()


def header(title="YouTube Auto Reply Bot"):
    console.clear()
    console.print(Panel.fit(
        f"[bold cyan]{title}[/bold cyan]",
        border_style="cyan"
    ))


def show_config(config, state):
    table = Table(show_header=False)
    table.add_row("Mode", config["mode"])
    table.add_row("Replies/hour", f'{state["replies_this_hour"]} / {config["max_replies_per_hour"]}')
    table.add_row("Poll interval", f'{config["poll_interval_seconds"]} sec')
    table.add_row("Last checked", state.get("last_checked", "Never"))

    console.print(table)


def status(message):
    console.print(f"[yellow]• {message}[/yellow]")


def success(message):
    console.print(f"[green]✔ {message}[/green]")


def error(message):
    console.print(f"[red]✖ {message}[/red]")


def info(message):
    console.print(f"[cyan]ℹ {message}[/cyan]")


def divider():
    console.print("-" * 50)
