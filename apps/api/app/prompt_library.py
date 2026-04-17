from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from app.services.llm_provider import (
    DEFAULT_VERTEX_AI_GRADING_MODEL,
    ProviderConfigurationError,
    normalize_reasoning_level,
    normalize_vertex_ai_grading_selection,
)


class PromptTemplate(BaseModel):
    prompt_id: str
    title: str
    body: str
    model_provider: str = "vertex_ai"
    model_name: str = DEFAULT_VERTEX_AI_GRADING_MODEL
    reasoning_level: str = "medium"
    built_in: bool = False


DEFAULT_PROMPT_TEMPLATES: tuple[PromptTemplate, ...] = (
    PromptTemplate(
        prompt_id="default-2p-lauseet-swe-fin",
        title="2p Lauseet",
        model_provider="vertex_ai",
        model_name=DEFAULT_VERTEX_AI_GRADING_MODEL,
        reasoning_level="medium",
        built_in=True,
        body="""
The student was tasked with "(OBJECTIVE)". The target phrase was "(TARGET)". They submitted "(ANSWER)". Proceed to grade this from a scale of:

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
    PromptTemplate(
        prompt_id="default-2p-kuullunymmartaminen-swe-fin",
        title="2p Kuullun ymmärtäminen [SWE audio -> FIN vastaus]",
        model_provider="vertex_ai",
        model_name=DEFAULT_VERTEX_AI_GRADING_MODEL,
        reasoning_level="medium",
        built_in=True,
        body="""
The student listened to a swedish audio clip. They were asked the following question in finnish: "(QUESTION)". 
The expected correct information (model answer) is: "(MODELANSWER)". 
The student submitted the following answer in finnish: "(ANSWER)". 

Because this is a listening comprehension exercise, evaluate the answer strictly based on information retrieval and understanding, NOT finnish grammar. Proceed to grade this from a scale of:

2/2 points:
The answer is completely correct. It contains all the key facts required by the model answer and directly answers the question. The student clearly understood the relevant part of the swedish audio.

1.5/2 points:
The answer captures the core message well but is slightly imprecise, or it misses a very minor detail present in the model answer. It still demonstrates a strong understanding of the audio.

1/2 points:
The answer is only partially correct. The student caught some relevant information from the audio, but a significant part of the expected answer is missing, or there is a clear misunderstanding of a key detail.

0.5 points:
The answer shows minimal understanding. The student may have recognized a single isolated swedish word or concept, but the overall answer fails to answer the actual question or is mostly guesswork.

0 points:
The answer is completely incorrect, off-topic, or illegible. The student did not understand the audio.
""".strip(),
    ),
    PromptTemplate(
        prompt_id="default-verbit-10p",
        title="Verbit 10p.",
        model_provider="vertex_ai",
        model_name=DEFAULT_VERTEX_AI_GRADING_MODEL,
        reasoning_level="medium",
        built_in=True,
        body="""
Your task is to grade a student's answer. The task was: "(OBJECTIVE)". The list of verbs are "(TARGET)". Proceed to grade the answer: "(ANSWER)" X out of 10 points based on:

1 point per successful verb objective completed (there are 10 numbered 1. 2. 3. etc.) (such as translation and/or conjugation).

If they are not successfully completed in a verb objective, grade it 0.5 or 0 depending on: If there are some correct conjugations and the translation is almost or fully correct, give 0.5 points. If only the translation is correct, give 0.25. If some conjugations are correct give 0.25. If a verb objective does not have the correct translation and conjugations, give 0 points.

Then add the points together to form the grade out of 10.
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
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Prompt library file is not valid JSON: {self.storage_path}") from exc
        if not isinstance(payload, list):
            raise RuntimeError(f"Prompt library file must contain a list of prompts: {self.storage_path}")
        prompts: list[PromptTemplate] = []
        for index, item in enumerate(payload):
            try:
                prompt = PromptTemplate.model_validate(item)
            except ValidationError as exc:
                raise RuntimeError(
                    f"Prompt library file contains an invalid prompt entry at index {index}: {self.storage_path}"
                ) from exc
            prompts.append(self._normalize_prompt(prompt))
        return prompts

    def _normalize_prompt(self, prompt: PromptTemplate) -> PromptTemplate:
        try:
            model_provider, model_name = normalize_vertex_ai_grading_selection(prompt.model_provider, prompt.model_name)
        except ProviderConfigurationError:
            model_provider, model_name = ("vertex_ai", DEFAULT_VERTEX_AI_GRADING_MODEL)
        try:
            reasoning_level = normalize_reasoning_level(prompt.reasoning_level)
        except ProviderConfigurationError:
            reasoning_level = "medium"
        return prompt.model_copy(
            update={
                "model_provider": model_provider,
                "model_name": model_name,
                "reasoning_level": reasoning_level,
            }
        )

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
            model_provider="vertex_ai",
            model_name=DEFAULT_VERTEX_AI_GRADING_MODEL,
            reasoning_level="medium",
            built_in=False,
        )

    def save_prompt(self, prompt: PromptTemplate) -> PromptTemplate:
        self._ensure_parent_dir()
        custom_prompts = self._load_custom_prompts()
        prompt = self._normalize_prompt(prompt)
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
