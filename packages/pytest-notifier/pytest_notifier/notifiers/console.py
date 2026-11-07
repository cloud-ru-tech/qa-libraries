from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from pytest_notifier.models import TestResults

from .base import NotifierBase


class ConsoleNotifier(NotifierBase):
    """Нотификатор для вывода результатов в терминал."""

    def is_enabled(self) -> bool:
        """Проверить доступность настроенного канала.

        :return: достаточно ли настроек для отправки.
        """
        return True  # Нотификация в терминал всегда доступна

    def send(self, results: TestResults) -> None:
        """Вывести информацию об упавших тестах в консоль."""
        console = Console()

        # Заголовок
        parts = []
        if results.failed:
            parts.append(f"Failed tests: {results.failed}")
        if results.error:
            parts.append(f"Errors: {results.error}")

        title = f"[bold red]{' | '.join(parts)}[/bold red]"
        console.print(Panel(title, expand=False))

        all_failures = results.failures + results.errors
        for idx, failure in enumerate(all_failures, 1):
            # Информация о тесте
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
