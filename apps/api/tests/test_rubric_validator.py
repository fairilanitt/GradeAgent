from app.schemas.api import RubricProfileCreate
from app.services.rubric_validator import RubricValidator


def test_rubric_validator_rejects_empty_criteria() -> None:
    report = RubricValidator().validate_profile(RubricProfileCreate(name="Invalid rubric", criteria=[]))
    assert report["valid"] is False
    assert report["issues"]
