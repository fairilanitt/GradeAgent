from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel


class PromptTemplate(BaseModel):
    prompt_id: str
    title: str
    body: str
    built_in: bool = False


DEFAULT_PROMPT_TEMPLATES: tuple[PromptTemplate, ...] = (
    PromptTemplate(
        prompt_id="default-2p-lauseet-swe-fin",
        title="2p Lauseet [SWE -> FIN]",
        built_in=True,
        body="""
The student was tasked with translating the swedish phrase "(TARGET)" to finnish. They submitted "(ANSWER)". Proceed to grade this from a scale of:

2/2 points:

The answer is concise, grammatically correct and succeeds in conveying the message of the original swedish phrase.

1.5/2 points:

The answer is coherent, but has small grammatical mistakes. It is understandable and conveys the message of the original swedish phrase well.

1/2 points:

The answer is semi-understandable, but has grammatical mistakes and the full meanining of the swedish sentence is not conveyed.

0.5 points:

The answer is barely understandable and has grammatical mistakes. The message conveyed is lost in translation.

0 points:

The answer is not understandable, and not legible
""".strip(),
    ),
)


class PromptLibraryService:
    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or Path("artifacts/prompt-library.json")

    def _ensure_parent_dir(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_custom_prompts(self) -> list[PromptTemplate]:
        if not self.storage_path.exists():
            return []
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        prompts: list[PromptTemplate] = []
        for item in payload if isinstance(payload, list) else []:
            try:
                prompt = PromptTemplate.model_validate(item)
            except Exception:
                continue
            prompts.append(prompt)
        return prompts

    def load_prompts(self) -> list[PromptTemplate]:
        built_in_prompts = [prompt.model_copy() for prompt in DEFAULT_PROMPT_TEMPLATES]
        built_in_prompt_ids = {prompt.prompt_id for prompt in built_in_prompts}
        built_in_by_id = {prompt.prompt_id: prompt for prompt in built_in_prompts}
        custom_only_prompts: list[PromptTemplate] = []

        for prompt in self._load_custom_prompts():
            if prompt.prompt_id in built_in_prompt_ids:
                built_in_by_id[prompt.prompt_id] = prompt.model_copy(update={"built_in": True})
            else:
                custom_only_prompts.append(prompt.model_copy(update={"built_in": False}))

        ordered_built_ins = [built_in_by_id[prompt.prompt_id] for prompt in built_in_prompts]
        return ordered_built_ins + custom_only_prompts

    def get_prompt(self, prompt_id: str) -> PromptTemplate | None:
        return next((prompt for prompt in self.load_prompts() if prompt.prompt_id == prompt_id), None)

    def new_custom_prompt(self) -> PromptTemplate:
        return PromptTemplate(
            prompt_id=f"custom-{uuid4()}",
            title="Uusi kriteeri",
            body="",
            built_in=False,
        )

    def save_prompt(self, prompt: PromptTemplate) -> PromptTemplate:
        self._ensure_parent_dir()
        custom_prompts = self._load_custom_prompts()
        updated_prompts: list[PromptTemplate] = []
        replaced = False
        for existing in custom_prompts:
            if existing.prompt_id == prompt.prompt_id:
                updated_prompts.append(prompt.model_copy())
                replaced = True
            else:
                updated_prompts.append(existing)
        if not replaced:
            updated_prompts.append(prompt.model_copy())
        self.storage_path.write_text(
            json.dumps([item.model_dump() for item in updated_prompts], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return prompt
