"""Profile new bank statement formats with LLM."""

from __future__ import annotations

import re

from app.llm.gemini_client import generate_json


def slugify(text: str) -> str:
    slug = re.sub(r'[^a-zA-Z0-9]+', '_', text.strip().lower()).strip('_')
    return slug or "unknown_bank"


def profile_format(first_page_text: str, bank_hint: str = "") -> dict:
    hint_line = f"Bank hint: {bank_hint}\n" if bank_hint else ""
    prompt = (
        "You are an assistant that profiles bank statement formats.\n"
        "Return ONLY a JSON object with this shape:\n"
        "{\n"
        '  "bank_name": "string",\n'
        '  "detection_keywords": ["string", "string", "..."]\n'
        "}\n"
        "Rules:\n"
        "- detection_keywords should be short phrases likely to appear on the first page.\n"
        "- Prefer bank name, header labels, or unique column names.\n"
        f"{hint_line}"
        "First page text:\n"
        f"{first_page_text}\n"
    )
    return generate_json(prompt)


def render_generated_parser(bank_name: str, keywords: list[str]) -> str:
    class_name = f"{_classify(bank_name)}Parser"
    keywords_list = ", ".join([repr(k) for k in keywords])
    return (
        '"""Generated parser scaffold (LLM-assisted)."""\n\n'
        "from pathlib import Path\n\n"
        "from app.llm.statement_extractor import parse_statement_with_llm\n"
        "from app.models.domain import ParseResult\n"
        "from app.parsers.base import BaseBankParser\n\n\n"
        f"class {class_name}(BaseBankParser):\n"
        f"    bank_name = {bank_name!r}\n\n"
        "    @staticmethod\n"
        "    def can_handle(first_page_text: str) -> bool:\n"
        "        text = first_page_text.lower()\n"
        f"        keywords = [{keywords_list}]\n"
        "        return any(k.lower() in text for k in keywords if k)\n\n"
        "    def parse(self, pdf_path: Path, password: str | None = None) -> ParseResult:\n"
        "        return parse_statement_with_llm(pdf_path, password=password, bank_hint=self.bank_name)\n"
    )


def _classify(text: str) -> str:
    parts = re.split(r'[^a-zA-Z0-9]+', text.strip())
    parts = [p.capitalize() for p in parts if p]
    return "".join(parts) or "Generated"
