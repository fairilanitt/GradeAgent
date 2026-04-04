from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, ClassVar

from PIL import Image


class MLXVLMUnavailableError(ImportError):
    """Raised when mlx-vlm is not installed for local visual inference."""


@dataclass
class _MLXVLMModelBundle:
    model: Any
    processor: Any
    config: Any
    generate: Any
    apply_chat_template: Any


class MLXVLMVisualClient:
    _cache: ClassVar[dict[str, _MLXVLMModelBundle]] = {}
    _cache_lock: ClassVar[Lock] = Lock()

    @classmethod
    def is_available(cls) -> bool:
        try:
            cls._load_imports()
            return True
        except MLXVLMUnavailableError:
            return False

    @staticmethod
    def _load_imports() -> tuple[Any, Any, Any, Any]:
        try:
            from mlx_vlm import generate, load
            from mlx_vlm.prompt_utils import apply_chat_template
            from mlx_vlm.utils import load_config
        except ModuleNotFoundError as exc:
            raise MLXVLMUnavailableError(
                "mlx-vlm is required for the local MLX vision backend. Install it with "
                "`pip install -e './apps/api[mlx]'`."
            ) from exc
        return load, generate, apply_chat_template, load_config

    @classmethod
    def _get_bundle(cls, model_name: str) -> _MLXVLMModelBundle:
        with cls._cache_lock:
            cached = cls._cache.get(model_name)
            if cached is not None:
                return cached

        load, generate, apply_chat_template, load_config = cls._load_imports()
        model, processor = load(model_name)
        config = load_config(model_name)
        bundle = _MLXVLMModelBundle(
            model=model,
            processor=processor,
            config=config,
            generate=generate,
            apply_chat_template=apply_chat_template,
        )

        with cls._cache_lock:
            cls._cache[model_name] = bundle
        return bundle

    @classmethod
    def classify_image(
        cls,
        *,
        model_name: str,
        image: Image.Image,
        prompt: str,
        max_tokens: int,
    ) -> str:
        bundle = cls._get_bundle(model_name)
        formatted_prompt = bundle.apply_chat_template(
            bundle.processor,
            bundle.config,
            prompt,
            num_images=1,
        )
        result = bundle.generate(
            bundle.model,
            bundle.processor,
            formatted_prompt,
            [image.convert("RGB")],
            verbose=False,
            max_tokens=max_tokens,
            temperature=0.0,
        )
        return getattr(result, "text", str(result)).strip()
