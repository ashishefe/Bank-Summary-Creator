"""Gemini client helpers."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import google.generativeai as genai


class GeminiError(RuntimeError):
    """Raised when Gemini configuration or responses fail."""


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON object from model response text."""
    if not text:
        raise GeminiError("Empty response from Gemini.")

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: find first JSON object in text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise GeminiError("Could not find JSON in Gemini response.")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise GeminiError(f"Invalid JSON from Gemini: {exc}") from exc


def _get_model() -> genai.GenerativeModel:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise GeminiError("Missing GEMINI_API_KEY in environment.")
    genai.configure(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    return genai.GenerativeModel(model_name)


def generate_json(prompt: str, temperature: float = 0.1) -> dict[str, Any]:
    """Generate a JSON response from Gemini."""
    model = _get_model()
    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": temperature,
            "response_mime_type": "application/json",
        },
    )
    return _extract_json(response.text if response else "")
