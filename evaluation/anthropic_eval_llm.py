"""Anthropic-native RAGAS evaluator LLM with explicit prompt caching support."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from langchain_core.outputs import Generation, LLMResult
from ragas.llms.base import BaseRagasLLM
from ragas.run_config import RunConfig

log = logging.getLogger(__name__)

EVAL_SYSTEM_PROMPT = (
    "You are an evaluation assistant. Follow the provided rubric exactly and "
    "return only the required format."
)


@dataclass
class AnthropicCachedEvalLLM(BaseRagasLLM):
    """RAGAS-compatible LLM wrapper that calls Anthropic directly."""

    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    cache_enabled: bool = False
    cache_ttl: str = "5m"

    def __post_init__(self) -> None:
        """Initialize base wrapper internals."""
        super().__post_init__()
        self.set_run_config(RunConfig())

    def _cache_control(self) -> Optional[dict[str, str]]:
        """Return cache control payload when prompt caching is enabled."""
        if not self.cache_enabled:
            return None
        ttl = self.cache_ttl if self.cache_ttl in {"5m", "1h"} else "5m"
        payload: dict[str, str] = {"type": "ephemeral"}
        if ttl == "1h":
            payload["ttl"] = "1h"
        return payload

    def _usage_cache_tokens(self, usage: Any) -> tuple[int, int]:
        """Extract cache usage fields from Anthropic response usage."""
        created = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        return created, read

    def _call_anthropic(self, prompt_text: str, temperature: float) -> LLMResult:
        """Call Anthropic Messages API and map response to LLMResult."""
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for evaluator LLM")
        client = anthropic.Anthropic(api_key=api_key)
        system_block: Any = [{"type": "text", "text": EVAL_SYSTEM_PROMPT}]
        cache_control = self._cache_control()
        if cache_control:
            system_block[0]["cache_control"] = cache_control
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=temperature,
            system=system_block,
            messages=[{"role": "user", "content": prompt_text}],
        )
        text_parts = [b.text for b in response.content if getattr(b, "type", "") == "text"]
        text = "\n".join(text_parts).strip()
        created, read = self._usage_cache_tokens(response.usage)
        log.info(
            "Eval LLM call tokens in/out=%d/%d cache create/read=%d/%d",
            int(getattr(response.usage, "input_tokens", 0) or 0),
            int(getattr(response.usage, "output_tokens", 0) or 0),
            created,
            read,
        )
        return LLMResult(
            generations=[
                [
                    Generation(
                        text=text,
                        generation_info={"stop_reason": response.stop_reason},
                    )
                ]
            ],
            llm_output={
                "stop_reason": response.stop_reason,
                "cache_creation_input_tokens": created,
                "cache_read_input_tokens": read,
            },
        )

    def generate_text(
        self,
        prompt: Any,
        n: int = 1,
        temperature: float = 0.01,
        stop: Optional[list[str]] = None,
        callbacks: Any = None,
    ) -> LLMResult:
        """Generate sync text result for RAGAS prompts."""
        del n, stop, callbacks
        return self._call_anthropic(prompt.to_string(), temperature)

    async def agenerate_text(
        self,
        prompt: Any,
        n: int = 1,
        temperature: Optional[float] = 0.01,
        stop: Optional[list[str]] = None,
        callbacks: Any = None,
    ) -> LLMResult:
        """Generate async text result for RAGAS prompts."""
        return await asyncio.to_thread(
            self.generate_text,
            prompt,
            n,
            temperature if temperature is not None else 0.01,
            stop,
            callbacks,
        )

    def is_finished(self, response: LLMResult) -> bool:
        """Return False when Anthropic stops due to max token limit."""
        for group in response.generations:
            for generation in group:
                reason = str(
                    (generation.generation_info or {}).get("stop_reason", "")
                ).lower()
                if reason in {"max_tokens", "length"}:
                    return False
        return True
