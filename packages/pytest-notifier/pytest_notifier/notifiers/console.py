from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from pytest_notifier.models import TestResults

from .base import NotifierBase


class ConsoleNotifier(NotifierBase):
    """Notifier that outputs results to the terminal."""

    def is_enabled(self) -> bool:
        """Check the configured channel availability.

        :return: whether the settings are sufficient for sending.
        """
        return True  # Terminal notifications are always available.

    def send(self, results: TestResults) -> None:
        """Print information about failed tests to the console."""
        console = Console()

        # Header
        parts = []
        if results.failed:
            parts.append(f"Failed tests: {results.failed}")
        if results.error:
            parts.append(f"Errors: {results.error}")

        title = f"[bold red]{' | '.join(parts)}[/bold red]"
        console.print(Panel(title, expand=False))

        all_failures = results.failures + results.errors
        for idx, failure in enumerate(all_failures, 1):
            # Test information
            table = Table(show_header=False, box=None)
            table.add_row("[bold]Test:[/bold]", f"[cyan]{failure.nodeid}[/cyan]")
            table.add_row("[bold]File:[/bold]", failure.file_path)
            table.add_row("[bold]Duration:[/bold]", f"{failure.duration:.2f}s")
            table.add_row("[bold]Error:[/bold]", f"[red]{failure.error_message}[/red]")

            console.print(f"\n[bold white on red] {idx} [/bold white on red] {failure.name}")
            console.print(table)

            if failure.traceback:
                console.print("\n[bold]Traceback:[/bold]")
                syntax = Syntax(
                    failure.traceback,
                    "python",
                    theme="monokai",
                    line_numbers=True,
                    background_color="default",
                )
                console.print(syntax)

        console.print("\n")
