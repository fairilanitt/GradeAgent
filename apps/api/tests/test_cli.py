from rich.console import Console

from app.cli import main, parse_start_grading_args, prompt_control_interface
from app.config import Settings
from app.schemas.api import ExamSessionGradingTaskCreate
from app.services.browser_navigation import BrowserNavigationService


def test_parse_start_grading_args_extracts_instruction_text() -> None:
    args = parse_start_grading_args(
        [
            "--instructions",
            "Give full points for exact matches and partial points for close meaning.",
            "--dry-run",
            "--max-steps",
            "300",
        ]
    )

    assert args.instructions.startswith("Give full points")
    assert args.dry_run is True
    assert args.max_steps == 300


def test_exam_grading_prompt_contains_site_specific_rules() -> None:
    service = BrowserNavigationService(Settings())
    prompt = service.build_exam_grading_task(
        ExamSessionGradingTaskCreate(
            instructions="Use the model answer and award partial points conservatively.",
            dry_run=False,
            submit_after_typing=False,
        )
    )

    assert "Oppilaan vastaus" in prompt
    assert "Mallivastaus" in prompt
    assert "Poistu oppilaan vastauksista" in prompt
    assert "Pisteytys" in prompt
    assert "dark blue" in prompt
    assert "Never use browser back/history" in prompt
    assert "award partial points conservatively" in prompt


def test_prompt_control_interface_accepts_gui_choice() -> None:
    console = Console(record=True)
    answers = iter(["gui"])

    interface = prompt_control_interface(console, input_func=lambda _: next(answers))

    assert interface == "gui"


def test_main_launches_gui_when_selected(monkeypatch) -> None:
    launched = {"gui": False}

    monkeypatch.setattr("app.cli.prompt_control_interface", lambda console: "gui")
    monkeypatch.setattr("app.cli.run_cli_shell", lambda: (_ for _ in ()).throw(AssertionError("CLI should not start")))
    monkeypatch.setattr("app.cli.launch_gui_interface", lambda: launched.__setitem__("gui", True))

    main([])

    assert launched["gui"] is True
