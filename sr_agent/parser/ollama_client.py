"""Client Ollama tối giản cho structured output.

Dùng /api/chat với `format=<json schema>` — Ollama ép model sinh JSON khớp
schema (constrained decoding), temperature=0 để tất định tối đa. Response
vẫn phải qua Pydantic validation lần cuối; fail -> SchemaValidationError
(Permanent, vào DLQ — retry LLM với cùng input là vô ích ở temperature 0).
"""

from __future__ import annotations

from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from sr_agent.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from sr_agent.errors import NetworkError, SchemaValidationError
from sr_agent.ingest.base import http_retry, raise_for_transient

T = TypeVar("T", bound=BaseModel)


class OllamaClient:
    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_MODEL,
        client: httpx.Client | None = None,
        timeout: float = 300.0,  # model 7B trên M4 có thể cần vài phút cho văn bản dài
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = client or httpx.Client(timeout=timeout)

    @http_retry
    def _chat(self, payload: dict) -> httpx.Response:
        try:
            response = self.client.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.TransportError as exc:
            raise NetworkError(f"Không kết nối được Ollama tại {self.base_url}: {exc}") from exc
        raise_for_transient(response)
        return response

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_model: type[T],
    ) -> T:
        """Gọi LLM và ép kết quả khớp 100% Pydantic schema."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": schema_model.model_json_schema(),
            "options": {"temperature": 0},
            "stream": False,
        }
        response = self._chat(payload)
        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError) as exc:
            raise SchemaValidationError(f"Ollama response sai cấu trúc: {exc}") from exc
        try:
            return schema_model.model_validate_json(content)
        except ValidationError as exc:
            raise SchemaValidationError(
                f"LLM output không qua được schema {schema_model.__name__}: {exc}"
            ) from exc

    def is_available(self) -> bool:
        try:
            return self.client.get(f"{self.base_url}/api/tags", timeout=2).status_code == 200
        except httpx.HTTPError:
            return False
