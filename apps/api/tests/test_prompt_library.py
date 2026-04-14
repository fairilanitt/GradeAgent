from app.prompt_library import PromptLibraryService


def test_prompt_library_includes_default_two_point_swe_fin_prompt(tmp_path) -> None:
    library = PromptLibraryService(storage_path=tmp_path / "prompt-library.json")

    prompts = library.load_prompts()

    default_prompt = next(prompt for prompt in prompts if prompt.prompt_id == "default-2p-lauseet-swe-fin")
    assert default_prompt.title == "2p Lauseet"
    assert '(OBJECTIVE)' in default_prompt.body
    assert "(TARGET)" in default_prompt.body
    assert "(ANSWER)" in default_prompt.body
    assert 'The target phrase was "(TARGET)"' in default_prompt.body
    assert "2/2 points" in default_prompt.body
    assert default_prompt.model_provider == "vertex_ai"
    assert default_prompt.model_name == "gemini-3.1-pro-preview"
    assert default_prompt.reasoning_level == "medium"


def test_prompt_library_includes_default_two_point_listening_comprehension_prompt(tmp_path) -> None:
    library = PromptLibraryService(storage_path=tmp_path / "prompt-library.json")

    prompts = library.load_prompts()

    default_prompt = next(
        prompt for prompt in prompts if prompt.prompt_id == "default-2p-kuullunymmartaminen-swe-fin"
    )
    assert default_prompt.title == "2p Kuullun ymmärtäminen [SWE audio -> FIN vastaus]"
    assert "(QUESTION)" in default_prompt.body
    assert "(MODELANSWER)" in default_prompt.body
    assert "(ANSWER)" in default_prompt.body
    assert "NOT finnish grammar" in default_prompt.body
    assert "2/2 points:" in default_prompt.body
    assert default_prompt.model_provider == "vertex_ai"
    assert default_prompt.model_name == "gemini-3.1-pro-preview"
    assert default_prompt.reasoning_level == "medium"


def test_prompt_library_can_save_custom_prompt(tmp_path) -> None:
    library = PromptLibraryService(storage_path=tmp_path / "prompt-library.json")
    prompt = library.new_custom_prompt().model_copy(
        update={
            "title": "Oma kriteeri",
            "body": "Arvioi vastaus merkityksen perusteella.",
        }
    )

    library.save_prompt(prompt)
    prompts = library.load_prompts()

    saved_prompt = next(item for item in prompts if item.prompt_id == prompt.prompt_id)
    assert saved_prompt.title == "Oma kriteeri"
    assert saved_prompt.body == "Arvioi vastaus merkityksen perusteella."
    assert saved_prompt.model_provider == "vertex_ai"
    assert saved_prompt.model_name == "gemini-3.1-pro-preview"
    assert saved_prompt.reasoning_level == "medium"


def test_prompt_library_can_override_default_prompt_without_hiding_it(tmp_path) -> None:
    library = PromptLibraryService(storage_path=tmp_path / "prompt-library.json")
    default_prompt = next(
        prompt for prompt in library.load_prompts() if prompt.prompt_id == "default-2p-lauseet-swe-fin"
    )

    library.save_prompt(
        default_prompt.model_copy(
            update={
                "title": "2p Lauseet",
                "body": "Muokattu oletusprompti.",
                "model_provider": "google",
                "model_name": "gemini-2.5-flash-lite",
                "reasoning_level": "low",
                "built_in": True,
            }
        )
    )

    prompts = library.load_prompts()
    saved_prompt = next(item for item in prompts if item.prompt_id == "default-2p-lauseet-swe-fin")
    assert saved_prompt.body == "Muokattu oletusprompti."
    assert saved_prompt.built_in is True
    assert saved_prompt.model_provider == "vertex_ai"
    assert saved_prompt.model_name == "gemini-2.5-flash-lite"
    assert saved_prompt.reasoning_level == "low"
