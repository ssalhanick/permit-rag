"""Ollama-native RAGAS evaluator LLM wrapper for low-cost local runs."""

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
class OllamaEvalLLM(BaseRagasLLM):
    """RAGAS-compatible local evaluator wrapper using Ollama chat API."""

    model: str = "qwen2.5:14b-instruct-q4_K_M"
    max_tokens: int = 4096

    def __post_init__(self) -> None:
        """Initialize base wrapper internals."""
        super().__post_init__()
        self.set_run_config(RunConfig())

    def _call_ollama(self, prompt_text: str, temperature: float) -> LLMResult:
        """Call local Ollama runtime and map result to LLMResult."""
        import requests

        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        timeout_s = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "180"))

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": EVAL_SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": self.max_tokens,
            },
        }
        response = requests.post(
            f"{base_url}/api/chat",
            json=payload,
            timeout=timeout_s,
        )
        response.raise_for_status()
        body = response.json()
        text = str(body.get("message", {}).get("content", "")).strip()
        prompt_tokens = int(body.get("prompt_eval_count") or 0)
        completion_tokens = int(body.get("eval_count") or 0)
        log.info(
            "Ollama eval call tokens in/out=%d/%d (%s)",
            prompt_tokens,
            completion_tokens,
            self.model,
        )

        return LLMResult(
            generations=[[Generation(text=text, generation_info={"stop_reason": "stop"})]],
            llm_output={
                "stop_reason": "stop",
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "provider": "ollama",
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
        return self._call_ollama(prompt.to_string(), temperature)

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
        """Ollama responses are treated as complete when returned."""
        del response
        return True
