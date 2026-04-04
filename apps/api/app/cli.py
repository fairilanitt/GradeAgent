from __future__ import annotations

import argparse
import asyncio
import cmd
import shlex
from types import SimpleNamespace
from uuid import uuid4

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.config import get_settings
from app.schemas.api import ExamSessionGradingTaskCreate, ExamSessionGradingTaskResult
from app.services.browser_navigation import BrowserNavigationService
from app.services.llm_provider import (
    grading_model_name,
    grading_reasoning_mode,
    normalize_provider,
    resolve_browser_model_name,
    resolve_google_model_name,
    resolve_provider_model_name,
)
from browser_use.skill_cli.utils import find_chrome_executable


def parse_start_grading_args(args: list[str]) -> SimpleNamespace:
    parser = argparse.ArgumentParser(prog="start grading", add_help=False)
    parser.add_argument("--instructions", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--submit-after-typing", action="store_true")
    parser.add_argument("--max-steps", type=int, default=260)
    namespace = parser.parse_args(args=args)
    return SimpleNamespace(
        instructions=namespace.instructions,
        dry_run=namespace.dry_run,
        submit_after_typing=namespace.submit_after_typing,
        max_steps=namespace.max_steps,
    )


class GradeAgentShell(cmd.Cmd):
    prompt = "gradeagent> "
    intro = ""

    def __init__(self) -> None:
        super().__init__()
        self.console = Console()
        self.settings = get_settings().model_copy(
            update={
                "browser_headless": False,
                "browser_attach_to_existing_chrome": False,
            }
        )
        self.browser_service = BrowserNavigationService(self.settings)
        self.last_result: ExamSessionGradingTaskResult | None = None
        self.last_instructions: str | None = None
        cleanup_result = self.browser_service.cleanup_browser_artifacts()
        self._print_cleanup_summary(cleanup_result, prefix="Startup cleanup")

    def preloop(self) -> None:
        self._render_welcome()

    def emptyline(self) -> bool:
        return False

    def do_help(self, arg: str) -> None:
        self._render_welcome()
        if arg:
            self.console.print(f"No additional help for: [bold]{arg}[/bold]")

    def do_status(self, _: str) -> None:
        standard_model_label = self.settings.model_router_standard_model
        complex_model_label = self.settings.model_router_complex_model
        browser_model_label = resolve_browser_model_name(self.settings)
        visual_backend_label = self.browser_service.resolved_visual_backend_label()
        visual_model_label = self.browser_service.resolved_visual_model_label()
        sanomapro_provider_label, sanomapro_model_label = resolve_provider_model_name(
            self.settings.sanomapro_exercise_grading_provider,
            self.settings.sanomapro_exercise_grading_model,
            self.settings,
        )
        if normalize_provider(self.settings.model_router_provider) in {"google", "vertex_ai"}:
            standard_model_label = grading_model_name(self.settings, "standard")
            complex_model_label = grading_model_name(self.settings, "complex")
        if normalize_provider(self.settings.browser_agent_provider) == "google":
            browser_model_label = resolve_google_model_name(browser_model_label, self.settings)
        chrome_profile_label = (
            self.settings.browser_chrome_profile_directory or "Default"
            if self.settings.browser_use_system_chrome
            else "-"
        )
        persistent_profile_label = (
            self.settings.browser_persistent_profile_dir or "artifacts/browser/browser-use-user-data-dir-gradeagent"
        )
        system_chrome_path = find_chrome_executable() if self.settings.browser_use_system_chrome else None

        config_table = Table(title="Current configuration", show_header=False, box=None, pad_edge=False)
        config_table.add_column("Setting", style="cyan", no_wrap=True)
        config_table.add_column("Value", style="white")
        config_table.add_row("Router provider", self.settings.model_router_provider)
        config_table.add_row("Simple model", self.settings.model_router_simple_model)
        config_table.add_row("Standard model", standard_model_label)
        config_table.add_row("Complex model", complex_model_label)
        config_table.add_row("Sanoma grader", f"{sanomapro_provider_label}/{sanomapro_model_label}")
        config_table.add_row(
            "Grading think",
            " ".join(
                [
                    f"simple={grading_reasoning_mode(self.settings, 'simple')}",
                    f"standard={grading_reasoning_mode(self.settings, 'standard')}",
                    f"complex={grading_reasoning_mode(self.settings, 'complex')}",
                ]
            ),
        )
        config_table.add_row("Browser model", browser_model_label)
        config_table.add_row("Agent vision", str(self.settings.browser_agent_use_vision))
        config_table.add_row("Force vision model", str(self.settings.browser_agent_force_vision))
        config_table.add_row("Visual backend", visual_backend_label)
        config_table.add_row("Visual model", visual_model_label)
        config_table.add_row("Visual image side", str(self.settings.browser_visual_max_image_side))
        config_table.add_row("Browser think", str(self.settings.browser_agent_use_thinking))
        config_table.add_row("Ollama host", self.settings.ollama_host)
        if normalize_provider(self.settings.model_router_provider) == "google" or normalize_provider(
            self.settings.browser_agent_provider
        ) == "google":
            config_table.add_row("Free tier only", str(self.settings.google_api_free_tier_only))
        if sanomapro_provider_label == "vertex_ai" or normalize_provider(self.settings.model_router_provider) == "vertex_ai":
            config_table.add_row("Vertex project", self.settings.vertex_ai_project or "-")
            config_table.add_row("Vertex location", self.settings.vertex_ai_location)
        config_table.add_row("Headless", str(self.settings.browser_headless))
        config_table.add_row("Attach Chrome", str(self.settings.browser_attach_to_existing_chrome))
        if self.settings.browser_attach_to_existing_chrome:
            config_table.add_row("CDP URL", self.browser_service._resolved_existing_chrome_cdp_url())
        config_table.add_row("System Chrome", str(self.settings.browser_use_system_chrome))
        config_table.add_row("Chrome binary", system_chrome_path or "-")
        config_table.add_row("Chrome profile", chrome_profile_label)
        config_table.add_row("Direct profile", str(self.settings.browser_direct_persistent_profile))
        config_table.add_row("Extensions", str(self.settings.browser_enable_default_extensions))
        config_table.add_row("Login profile", persistent_profile_label)
        self.console.print()
        self.console.print(config_table)

        if self.last_result is None:
            self.console.print("\nNo grading run has finished yet.")
            return

        self.console.print()
        self.console.print(self._result_panel(self.last_result, title="Last grading run"))

    def do_quit(self, _: str) -> bool:
        self.console.print("Exiting GradeAgent CLI.")
        return True

    def do_exit(self, arg: str) -> bool:
        return self.do_quit(arg)

    def default(self, line: str) -> bool | None:
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            self.console.print(f"Could not parse command: {exc}", style="bold red")
            return None

        if not tokens:
            return None

        if len(tokens) >= 2 and tokens[0] == "start" and tokens[1] == "grading":
            try:
                args = parse_start_grading_args(tokens[2:])
            except SystemExit:
                self.console.print(
                    'Usage: start grading --instructions "YOUR RULES" [--dry-run] [--submit-after-typing]',
                    style="yellow",
                )
                return None
            self._run_start_grading(args)
            return None

        self.console.print(f"Unknown command: {line}", style="bold red")
        self.console.print('Try: start grading --instructions "YOUR RULES"', style="yellow")
        return None

    def _print_cleanup_summary(self, cleanup_result: dict[str, int], *, prefix: str) -> None:
        removed_paths = cleanup_result.get("removed_paths", 0)
        removed_bytes = cleanup_result.get("removed_bytes", 0)
        if removed_paths <= 0:
            return
        removed_megabytes = removed_bytes / (1024 * 1024)
        self.console.print(
            f"{prefix}: removed {removed_paths} old browser artifact(s), freed {removed_megabytes:.1f} MB.",
            style="dim",
        )

    def _render_welcome(self) -> None:
        title = Text("GradeAgent CLI", style="bold cyan")
        body = "\n".join(
            [
                "This command line opens a dedicated GradeAgent browser for exam grading.",
                "",
                "How to use it:",
                '1. Run: start grading --instructions "YOUR GRADING RULES"',
                "2. Sign in if needed and open the actual exam review page in the dedicated browser.",
                "3. Return here and press Enter to begin grading.",
                "",
                "Main commands:",
                '  start grading --instructions "..."',
                "  status",
                "  help",
                "  quit",
            ]
        )
        self.console.print(Panel(body, title=title, border_style="blue", expand=False))

    def _render_tabs(self, detected_tabs: list[dict[str, str]]) -> None:
        tabs_table = Table(title="Detected tabs", expand=True)
        tabs_table.add_column("#", style="cyan", no_wrap=True)
        tabs_table.add_column("Title", style="white")
        tabs_table.add_column("URL", style="green")
        for index, tab in enumerate(detected_tabs, start=1):
            tabs_table.add_row(str(index), tab["title"] or "-", tab["url"] or "-")
        self.console.print()
        self.console.print(tabs_table)

    def _result_panel(self, result: ExamSessionGradingTaskResult, *, title: str) -> Panel:
        summary_table = Table(show_header=False, box=None, pad_edge=False)
        summary_table.add_column("Field", style="cyan", no_wrap=True)
        summary_table.add_column("Value", style="white")
        summary_table.add_row("Status", result.status)
        summary_table.add_row("Processed answers", str(result.processed_answers))
        summary_table.add_row("Skipped dark blue boxes", str(result.skipped_dark_blue_boxes))
        summary_table.add_row("Completed columns", str(result.completed_exercise_columns))
        summary_table.add_row("Filled point fields", str(result.filled_point_fields))
        summary_table.add_row("Current exercise", result.current_exercise_label or "-")
        summary_table.add_row("Current student", result.current_student_name or "-")
        summary_table.add_row("Report", result.report_path or "-")
        summary_table.add_row("Screenshot", result.screenshot_path or "-")
        summary_table.add_row("Summary", result.summary)
        return Panel(summary_table, title=title, border_style="green", expand=False)

    def _run_start_grading(self, args: SimpleNamespace) -> None:
        job_id = str(uuid4())
        loop = asyncio.new_event_loop()
        browser_session = None

        try:
            asyncio.set_event_loop(loop)

            self.console.print()
            self.console.print(Panel("Step 1 of 5: Launching the dedicated GradeAgent browser.", border_style="cyan"))
            if self.settings.browser_use_system_chrome:
                self.console.print(
                    "Using your installed Chrome with a slim GradeAgent profile that keeps login and site data.",
                    style="white",
                )
            else:
                self.console.print(
                    "Using the persistent GradeAgent browser profile. Logins in this browser should carry over to the next run.",
                    style="white",
                )
            _, browser_session = loop.run_until_complete(
                self.browser_service.launch_interactive_browser(
                    job_id,
                )
            )

            self.console.print(Panel("Step 2 of 5: Browser is open.", border_style="cyan"))
            self.console.print(
                "Open the actual exam review/grading page in the dedicated GradeAgent browser. When the correct page is visible, come back here and press Enter.",
                style="white",
            )
            input()

            detected_tabs = loop.run_until_complete(self.browser_service.list_open_tabs(browser_session))
            if detected_tabs:
                self._render_tabs(detected_tabs)

            current_url = loop.run_until_complete(self.browser_service.get_current_page_url(browser_session))
            self.console.print(
                Panel(
                    f"Step 3 of 5: Starting grading from: {current_url or 'unknown page'}",
                    border_style="cyan",
                )
            )

            payload = ExamSessionGradingTaskCreate(
                instructions=args.instructions,
                dry_run=args.dry_run,
                submit_after_typing=args.submit_after_typing,
                max_steps=args.max_steps,
            )
            result = loop.run_until_complete(
                self.browser_service.grade_exam_from_current_page(
                    payload=payload,
                    job_id=job_id,
                    browser_session=browser_session,
                )
            )

            self.console.print(Panel("Step 4 of 5: Grading run finished.", border_style="cyan"))
            self.last_result = result
            self.last_instructions = args.instructions

            self.console.print()
            self.console.print(self._result_panel(result, title="Run summary"))

            if result.steps:
                steps_table = Table(title="Steps", expand=True)
                steps_table.add_column("Name", style="cyan")
                steps_table.add_column("Status", style="white")
                steps_table.add_column("Detail", style="green")
                for step in result.steps:
                    steps_table.add_row(step.name, step.status, step.detail)
                self.console.print()
                self.console.print(steps_table)

            self.console.print()
            self.console.print(Panel("Step 5 of 5: Done.", border_style="green"))
        except KeyboardInterrupt:
            report_path = self.browser_service.exam_grading_report_path(job_id)
            if report_path.exists():
                self.console.print(
                    f"\nGrading interrupted by user. Partial report saved to {report_path}.",
                    style="bold yellow",
                )
            else:
                self.console.print("\nGrading interrupted by user.", style="bold yellow")
        except Exception as exc:
            self.console.print(f"\nGrading failed: {exc}", style="bold red")
        finally:
            if browser_session is not None:
                try:
                    loop.run_until_complete(browser_session.kill())
                except Exception:
                    pass
            cleanup_result = self.browser_service.cleanup_browser_artifacts(current_job_id=job_id)
            self._print_cleanup_summary(cleanup_result, prefix="Run cleanup")
            loop.close()
            asyncio.set_event_loop(None)


def main() -> None:
    shell = GradeAgentShell()
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        shell.console.print("\nExiting GradeAgent CLI.")


if __name__ == "__main__":
    main()
