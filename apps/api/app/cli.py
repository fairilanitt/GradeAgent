from __future__ import annotations

import argparse
import asyncio
import cmd
import os
import plistlib
import shlex
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
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


GUI_API_HOST = os.environ.get("GRADEAGENT_GUI_API_HOST", "127.0.0.1")
GUI_API_PORT = int(os.environ.get("GRADEAGENT_GUI_API_PORT", "8765"))


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


def parse_interface_args(args: list[str]) -> tuple[SimpleNamespace, list[str]]:
    parser = argparse.ArgumentParser(prog="gradeagent", add_help=False)
    parser.add_argument("--interface", choices=("cli", "gui"))
    namespace, remaining = parser.parse_known_args(args=args)
    return SimpleNamespace(interface=namespace.interface), remaining


def prompt_control_interface(console: Console, *, input_func=input) -> str:
    console.print(
        Panel(
            "Choose the control interface:\n\n1. CLI\n2. GUI",
            title="GradeAgent",
            border_style="cyan",
            expand=False,
        )
    )
    while True:
        choice = input_func("Select interface [1/2 or cli/gui]: ").strip().lower()
        if choice in {"1", "cli"}:
            return "cli"
        if choice in {"2", "gui"}:
            return "gui"
        console.print("Please choose CLI or GUI.", style="yellow")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _api_workdir() -> Path:
    return Path(__file__).resolve().parents[1]


def _swiftui_package_dir() -> Path:
    return _repo_root() / "apps" / "macos" / "GradeAgentMacApp"


def _gui_backend_base_url() -> str:
    return f"http://{GUI_API_HOST}:{GUI_API_PORT}/api"


def _gui_artifact_dir() -> Path:
    path = _repo_root() / "artifacts" / "gui"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _gui_backend_log_path() -> Path:
    return _gui_artifact_dir() / "gui-backend.log"


def _gui_backend_healthcheck_url() -> str:
    return f"{_gui_backend_base_url()}/health"


def _gui_backend_state_url() -> str:
    return f"{_gui_backend_base_url()}/gui/state"


def _swiftui_executable_path() -> Path:
    return _swiftui_package_dir() / ".build" / "debug" / "GradeAgentMacApp"


def _swiftui_app_bundle_dir() -> Path:
    return _gui_artifact_dir() / "GradeAgent.app"


def _backend_python_executable() -> str:
    venv_python = _repo_root() / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _gui_backend_is_ready(timeout_seconds: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(_gui_backend_state_url(), timeout=timeout_seconds) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def _gui_backend_healthcheck_ready(timeout_seconds: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(_gui_backend_healthcheck_url(), timeout=timeout_seconds) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def _wait_for_gui_backend(timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _gui_backend_is_ready():
            return
        time.sleep(0.3)
    raise RuntimeError("The local GradeAgent GUI backend did not become ready in time.")


def _read_gui_backend_log_tail(max_chars: int = 4000) -> str:
    log_path = _gui_backend_log_path()
    if not log_path.exists():
        return ""
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    content = content.strip()
    if not content:
        return ""
    if len(content) > max_chars:
        return content[-max_chars:]
    return content


def _ensure_gui_backend_running() -> None:
    if _gui_backend_is_ready():
        return
    if _gui_backend_healthcheck_ready():
        raise RuntimeError(
            f"An API server is already running at {_gui_backend_base_url()}, but it does not expose the SwiftUI GUI routes. "
            "Stop the older backend process and try again."
        )

    backend_process = None
    log_path = _gui_backend_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(os.devnull, "rb") as null_in, open(log_path, "ab") as log_file:
        backend_process = subprocess.Popen(
            [
                _backend_python_executable(),
                "-m",
                "uvicorn",
                "app.gui_server:app",
                "--host",
                GUI_API_HOST,
                "--port",
                str(GUI_API_PORT),
            ],
            cwd=_api_workdir(),
            stdin=null_in,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
            close_fds=True,
        )

    deadline = time.time() + 30.0
    while time.time() < deadline:
        if _gui_backend_is_ready():
            return
        if backend_process.poll() is not None:
            log_tail = _read_gui_backend_log_tail()
            detail = f" Backend log:\n{log_tail}" if log_tail else ""
            raise RuntimeError(
                "The local GradeAgent GUI backend exited during startup."
                f"{detail}"
            )
        time.sleep(0.3)

    log_tail = _read_gui_backend_log_tail()
    detail = f" Backend log:\n{log_tail}" if log_tail else ""
    raise RuntimeError(
        "The local GradeAgent GUI backend did not become ready in time."
        f"{detail}"
    )


def _build_swiftui_app() -> Path:
    if shutil.which("swift") is None:
        raise RuntimeError("Swift was not found in PATH. Install Xcode command line tools or Xcode first.")

    package_dir = _swiftui_package_dir()
    if not package_dir.exists():
        raise RuntimeError(f"SwiftUI package was not found at {package_dir}.")

    build = subprocess.run(
        [
            "swift",
            "build",
            "--package-path",
            str(package_dir),
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        stderr = build.stderr.strip() or build.stdout.strip() or "Unknown Swift build error."
        raise RuntimeError(f"SwiftUI app build failed: {stderr}")

    executable_path = _swiftui_executable_path()
    if not executable_path.exists():
        raise RuntimeError(f"SwiftUI app executable was not produced at {executable_path}.")
    return executable_path


def _assemble_swiftui_app_bundle(executable_path: Path) -> Path:
    bundle_dir = _swiftui_app_bundle_dir()
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)

    contents_dir = bundle_dir / "Contents"
    macos_dir = contents_dir / "MacOS"
    resources_dir = contents_dir / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    bundled_binary_path = resources_dir / "GradeAgentMacApp.bin"
    shutil.copy2(executable_path, bundled_binary_path)
    bundled_binary_path.chmod(0o755)

    launcher_path = macos_dir / "GradeAgentMacApp"
    launcher_path.write_text(
        "\n".join(
            [
                "#!/bin/zsh",
                f'export GRADEAGENT_GUI_API_BASE_URL="{_gui_backend_base_url()}"',
                'APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"',
                'exec "$APP_ROOT/Resources/GradeAgentMacApp.bin" "$@"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    launcher_path.chmod(0o755)

    info_plist_path = contents_dir / "Info.plist"
    info_plist_path.write_bytes(
        plistlib.dumps(
            {
                "CFBundleDevelopmentRegion": "en",
                "CFBundleDisplayName": "GradeAgent",
                "CFBundleExecutable": "GradeAgentMacApp",
                "CFBundleIdentifier": "fi.gradeagent.macapp",
                "CFBundleInfoDictionaryVersion": "6.0",
                "CFBundleName": "GradeAgent",
                "CFBundlePackageType": "APPL",
                "CFBundleShortVersionString": "0.1.0",
                "CFBundleVersion": "1",
                "LSMinimumSystemVersion": "14.0",
                "NSHighResolutionCapable": True,
                "NSPrincipalClass": "NSApplication",
            }
        )
    )

    return bundle_dir


def launch_gui_interface() -> None:
    _ensure_gui_backend_running()
    executable_path = _build_swiftui_app()
    app_bundle_path = _assemble_swiftui_app_bundle(executable_path)

    with open(os.devnull, "rb") as null_in, open(os.devnull, "ab") as null_out:
        subprocess.Popen(
            ["open", "-n", str(app_bundle_path)],
            stdin=null_in,
            stdout=null_out,
            stderr=null_out,
            cwd=_repo_root(),
            start_new_session=True,
            close_fds=True,
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
        previous_signal_handlers: dict[int, signal.Handlers] = {}

        def _request_graceful_shutdown(signum, _frame) -> None:
            raise KeyboardInterrupt(f"Received signal {signum}")

        for signum_name in ("SIGTERM", "SIGHUP"):
            signum = getattr(signal, signum_name, None)
            if signum is None:
                continue
            try:
                previous_signal_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, _request_graceful_shutdown)
            except (ValueError, OSError):
                continue

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
            for signum, previous_handler in previous_signal_handlers.items():
                try:
                    signal.signal(signum, previous_handler)
                except (ValueError, OSError):
                    continue
            if browser_session is not None:
                try:
                    loop.run_until_complete(browser_session.kill())
                except Exception:
                    pass
            cleanup_result = self.browser_service.cleanup_browser_artifacts(current_job_id=job_id)
            self._print_cleanup_summary(cleanup_result, prefix="Run cleanup")
            loop.close()
            asyncio.set_event_loop(None)

def run_cli_shell() -> None:
    shell = GradeAgentShell()
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        shell.console.print("\nExiting GradeAgent CLI.")


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    console = Console()
    parsed_args, remaining = parse_interface_args(args)

    if remaining and parsed_args.interface is None:
        run_cli_shell()
        return

    interface = parsed_args.interface
    if interface is None:
        try:
            interface = prompt_control_interface(console)
        except EOFError:
            interface = "cli"

    if interface == "gui":
        try:
            launch_gui_interface()
        except Exception as exc:
            console.print(f"Could not launch the SwiftUI GUI: {exc}", style="bold red")
        return

    run_cli_shell()


if __name__ == "__main__":
    main()
