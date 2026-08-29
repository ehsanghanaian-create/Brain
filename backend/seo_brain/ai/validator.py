"""Validators check a provider response before it is accepted (and before it can influence memory)."""
from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from .types import AIResponse, AITask


class ValidationError(ValueError):
    pass


@runtime_checkable
class Validator(Protocol):
    def validate(self, task: AITask, response: AIResponse) -> AIResponse: ...


class NonEmptyValidator:
    def validate(self, task: AITask, response: AIResponse) -> AIResponse:
        if not response.text or not response.text.strip():
            raise ValidationError("empty response")
        return response


class JsonKeysValidator:
    """When the task requests JSON: parse it (tolerating ```json fences) and require the schema's `required`
    keys (or all `properties` when `required` is absent). Sets `response.parsed`."""

    def validate(self, task: AITask, response: AIResponse) -> AIResponse:
        if not task.json_schema:
            return response
        text = response.text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().lower() in ("```", "```json"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        # Some providers wrap an otherwise valid object in a short explanation.  Extract only a balanced outer
        # object; truncated JSON still fails and is retried/falls back instead of being guessed or repaired.
        if not text.startswith("{"):
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]
        try:
            data: Any = json.loads(text)
        except ValueError as e:
            raise ValidationError(f"response is not valid JSON: {e}") from e
        required = task.json_schema.get("required") or list((task.json_schema.get("properties") or {}).keys())
        if not isinstance(data, dict):
            raise ValidationError("JSON root must be an object")
        missing = [k for k in required if k not in data]
        if missing:
            raise ValidationError(f"missing keys: {missing}")
        response.parsed = data
        return response


class ChainValidator:
    def __init__(self, *validators: Validator):
        self.validators = validators

    def validate(self, task: AITask, response: AIResponse) -> AIResponse:
        for v in self.validators:
            response = v.validate(task, response)
        return response
