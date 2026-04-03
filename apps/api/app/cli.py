from __future__ import annotations

import argparse
import asyncio
import cmd
import shlex
from types import SimpleNamespace
from uuid import uuid4

from app.config import get_settings
from app.schemas.api import ExamSessionGradingTaskCreate, ExamSessionGradingTaskResult
from app.services.browser_navigation import BrowserNavigationService
from app.services.llm_provider import grading_model_name, grading_reasoning_mode, normalize_provider, resolve_google_model_name
from browser_use.skill_cli.utils import find_chrome_executable


WELCOME_TEXT = """
===========================================================
 GradeAgent CLI
===========================================================

This program runs in your terminal.

What to do:
1. Type: start grading --instructions "YOUR GRADING RULES"
2. A browser window will open.
3. Keep the managed browser on the correct exam page.
4. Come back here and press Enter.
5. The agent will use the current page and grade vertically by exercise column.

Main commands:
  start grading --instructions "..."
  status
  help
  quit
""".strip()


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
    intro = WELCOME_TEXT

    def __init__(self) -> None:
        super().__init__()
        self.settings = get_settings().model_copy(update={"browser_headless": False})
        self.browser_service = BrowserNavigationService(self.settings)
        self.last_result: ExamSessionGradingTaskResult | None = None
        self.last_instructions: str | None = None
        cleanup_result = self.browser_service.cleanup_browser_artifacts()
        self._print_cleanup_summary(cleanup_result, prefix="Startup cleanup")

    def emptyline(self) -> bool:
        return False

    def do_help(self, arg: str) -> None:
        print(WELCOME_TEXT)
        if arg:
            print(f"\nNo additional help for: {arg}")

    def do_status(self, _: str) -> None:
        standard_model_label = self.settings.model_router_standard_model
        complex_model_label = self.settings.model_router_complex_model
        browser_model_label = self.settings.browser_agent_model
        if normalize_provider(self.settings.model_router_provider) == "google":
            standard_model_label = grading_model_name(self.settings, "standard")
            complex_model_label = grading_model_name(self.settings, "complex")
        if normalize_provider(self.settings.browser_agent_provider) == "google":
            browser_model_label = resolve_google_model_name(self.settings.browser_agent_model, self.settings)
        chrome_profile_label = (
            self.settings.browser_chrome_profile_directory or "Default"
            if self.settings.browser_use_system_chrome
            else "-"
        )
        persistent_profile_label = (
            self.settings.browser_persistent_profile_dir or "artifacts/browser/browser-use-user-data-dir-gradeagent"
        )
        system_chrome_path = find_chrome_executable() if self.settings.browser_use_system_chrome else None
        print("\nCurrent configuration")
        print("---------------------")
        print(f"Router provider: {self.settings.model_router_provider}")
        print(f"Simple model:    {self.settings.model_router_simple_model}")
        print(f"Standard model:  {standard_model_label}")
        print(f"Complex model:   {complex_model_label}")
        print(
            "Grading think:   "
            f"simple={grading_reasoning_mode(self.settings, 'simple')} "
            f"standard={grading_reasoning_mode(self.settings, 'standard')} "
            f"complex={grading_reasoning_mode(self.settings, 'complex')}"
        )
        print(f"Browser model:   {browser_model_label}")
        print(f"Browser think:   {self.settings.browser_agent_use_thinking}")
        print(f"Ollama host:     {self.settings.ollama_host}")
        if normalize_provider(self.settings.model_router_provider) == "google" or normalize_provider(
            self.settings.browser_agent_provider
        ) == "google":
            print(f"Free tier only:  {self.settings.google_api_free_tier_only}")
        print(f"Headless:        {self.settings.browser_headless}")
        print(f"System Chrome:   {self.settings.browser_use_system_chrome}")
        print(f"Chrome binary:   {system_chrome_path or '-'}")
        print(f"Chrome profile:  {chrome_profile_label}")
        print(f"Direct profile:  {self.settings.browser_direct_persistent_profile}")
        print(f"Extensions:      {self.settings.browser_enable_default_extensions}")
        print(f"Login profile:   {persistent_profile_label}")
        if self.last_result is None:
            print("\nNo grading run has finished yet.")
            return

        print("\nLast grading run")
        print("----------------")
        print(f"Status:                  {self.last_result.status}")
        print(f"Processed answers:       {self.last_result.processed_answers}")
        print(f"Skipped dark blue boxes: {self.last_result.skipped_dark_blue_boxes}")
        print(f"Completed columns:       {self.last_result.completed_exercise_columns}")
        print(f"Filled point fields:     {self.last_result.filled_point_fields}")
        print(f"Current exercise:        {self.last_result.current_exercise_label or '-'}")
        print(f"Current student:         {self.last_result.current_student_name or '-'}")
        print(f"Screenshot:              {self.last_result.screenshot_path or '-'}")
        print(f"Summary:                 {self.last_result.summary}")

    def do_quit(self, _: str) -> bool:
        print("Exiting GradeAgent CLI.")
        return True

    def do_exit(self, arg: str) -> bool:
        return self.do_quit(arg)

    def default(self, line: str) -> bool | None:
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            print(f"Could not parse command: {exc}")
            return None

        if not tokens:
            return None

        if len(tokens) >= 2 and tokens[0] == "start" and tokens[1] == "grading":
            try:
                args = parse_start_grading_args(tokens[2:])
            except SystemExit:
                print('Usage: start grading --instructions "YOUR RULES" [--dry-run] [--submit-after-typing]')
                return None
            self._run_start_grading(args)
            return None

        print(f"Unknown command: {line}")
        print('Try: start grading --instructions "YOUR RULES"')
        return None

    def _print_cleanup_summary(self, cleanup_result: dict[str, int], *, prefix: str) -> None:
        removed_paths = cleanup_result.get("removed_paths", 0)
        removed_bytes = cleanup_result.get("removed_bytes", 0)
        if removed_paths <= 0:
            return
        removed_megabytes = removed_bytes / (1024 * 1024)
        print(f"{prefix}: removed {removed_paths} old browser artifact(s), freed {removed_megabytes:.1f} MB.")

    def _run_start_grading(self, args: SimpleNamespace) -> None:
        job_id = str(uuid4())
        loop = asyncio.new_event_loop()
        browser_session = None

        try:
            asyncio.set_event_loop(loop)

            print("\n[1/5] Launching managed browser window...")
            if self.settings.browser_use_system_chrome:
                print(
                    "Using your installed Chrome with a slim GradeAgent profile that keeps login/site data and avoids most extra browser state. "
                    "If you need a fresh import, close Chrome and delete the GradeAgent login profile folder first."
                )
            else:
                print(
                    "Using the persistent GradeAgent browser profile. "
                    "If you log in once in this browser, the session should be reused on the next run."
                )
            _, browser_session = loop.run_until_complete(
                self.browser_service.launch_interactive_browser(
                    job_id,
                    navigate_to_start_url=False,
                )
            )

            print("[2/5] Browser is open.")
            print("GradeAgent assumes the managed browser is already on the correct exam page.")
            print("If the wrong page is open, navigate manually to the correct exam page, then come back here and press Enter.")
            input()

            current_url = loop.run_until_complete(self.browser_service.get_current_page_url(browser_session))
            print(f"[3/5] Starting grading from current page: {current_url or 'unknown page'}")

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

            print("[4/5] Grading run finished.")
            self.last_result = result
            self.last_instructions = args.instructions

            print("\nRun summary")
            print("-----------")
            print(f"Status:                  {result.status}")
            print(f"Processed answers:       {result.processed_answers}")
            print(f"Skipped dark blue boxes: {result.skipped_dark_blue_boxes}")
            print(f"Completed columns:       {result.completed_exercise_columns}")
            print(f"Filled point fields:     {result.filled_point_fields}")
            print(f"Current exercise:        {result.current_exercise_label or '-'}")
            print(f"Current student:         {result.current_student_name or '-'}")
            print(f"Screenshot:              {result.screenshot_path or '-'}")
            print(f"Summary:                 {result.summary}")

            if result.steps:
                print("\nSteps")
                print("-----")
                for step in result.steps:
                    print(f"- {step.name}: {step.status} | {step.detail}")

            print("[5/5] Done.\n")
        except KeyboardInterrupt:
            print("\nGrading interrupted by user.")
        except Exception as exc:
            print(f"\nGrading failed: {exc}")
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
        print("\nExiting GradeAgent CLI.")


if __name__ == "__main__":
    main()
