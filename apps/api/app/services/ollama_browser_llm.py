from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeVar, overload

import httpx
from ollama import AsyncClient as OllamaAsyncClient
from ollama import Options
from pydantic import BaseModel

from browser_use.llm.base import BaseChatModel
from browser_use.llm.exceptions import ModelProviderError
from browser_use.llm.messages import BaseMessage
from browser_use.llm.ollama.serializer import OllamaMessageSerializer
from browser_use.llm.views import ChatInvokeCompletion

T = TypeVar("T", bound=BaseModel)


@dataclass
class EfficientBrowserUseChatOllama(BaseChatModel):
    model: str
    host: str | None = None
    timeout: float | httpx.Timeout | None = None
    client_params: dict[str, Any] | None = None
    ollama_options: Mapping[str, Any] | Options | None = None
    keep_alive: float | str | None = None
    think: bool | str | None = "low"

    @property
    def provider(self) -> str:
        return "ollama"

    def get_client(self) -> OllamaAsyncClient:
        return OllamaAsyncClient(host=self.host, timeout=self.timeout, **self.client_params or {})

    @property
    def name(self) -> str:
        return self.model

    @overload
    async def ainvoke(
        self, messages: list[BaseMessage], output_format: None = None, **kwargs: Any
    ) -> ChatInvokeCompletion[str]: ...

    @overload
    async def ainvoke(
        self, messages: list[BaseMessage], output_format: type[T], **kwargs: Any
    ) -> ChatInvokeCompletion[T]: ...

    async def ainvoke(
        self, messages: list[BaseMessage], output_format: type[T] | None = None, **kwargs: Any
    ) -> ChatInvokeCompletion[T] | ChatInvokeCompletion[str]:
        ollama_messages = OllamaMessageSerializer.serialize_messages(messages)

        try:
            if output_format is None:
                response = await self.get_client().chat(
                    model=self.model,
                    messages=ollama_messages,
                    options=self.ollama_options,
                    keep_alive=self.keep_alive,
                    think=self.think,
                )
                return ChatInvokeCompletion(completion=response.message.content or "", usage=None)

            schema = output_format.model_json_schema()
            response = await self.get_client().chat(
                model=self.model,
                messages=ollama_messages,
                format=schema,
                options=self.ollama_options,
                keep_alive=self.keep_alive,
                think=self.think,
            )

            completion = response.message.content or ""
            from app.services.llm_provider import extract_json_object

            cleaned_completion = extract_json_object(completion)
            parsed = output_format.model_validate_json(cleaned_completion)
            return ChatInvokeCompletion(completion=parsed, usage=None)
        except Exception as exc:
            raise ModelProviderError(message=str(exc), model=self.name) from exc
