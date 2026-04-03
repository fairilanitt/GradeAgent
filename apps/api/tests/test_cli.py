from app.cli import parse_start_grading_args
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
    assert "Never use the browser back button" in prompt
    assert "award partial points conservatively" in prompt
