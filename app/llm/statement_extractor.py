"""LLM-based statement parsing for unknown formats."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Optional

import pdfplumber

from app.llm.gemini_client import GeminiError, generate_json
from app.models.domain import BankAccount, ParseResult, Transaction
from app.parsers.utils import parse_date_flexible, parse_indian_number


def extract_pdf_text(
    pdf_path: Path,
    password: Optional[str] = None,
    max_pages: int = 5,
    max_chars: int = 40000,
) -> str:
    """Extract text from a PDF, capped by pages and size."""
    text_chunks: list[str] = []
    with pdfplumber.open(pdf_path, password=password) as pdf:
        for page in pdf.pages[:max_pages]:
            page_text = page.extract_text() or ""
            if page_text:
                text_chunks.append(page_text)
            if sum(len(t) for t in text_chunks) >= max_chars:
                break
    text = "\n".join(text_chunks).strip()
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


def parse_statement_with_llm(
    pdf_path: Path,
    password: Optional[str] = None,
    bank_hint: str = "",
) -> ParseResult:
    """Parse a statement using Gemini for unknown formats."""
    try:
        text = extract_pdf_text(pdf_path, password=password)
    except Exception as exc:
        return ParseResult(
            success=False,
            error=f"LLM fallback could not read PDF: {exc}",
            file_name=pdf_path.name,
        )

    if len(text.strip()) < 50:
        return ParseResult(
            success=False,
            error="This PDF appears to be a scanned image. Only digital/text PDFs are supported.",
            file_name=pdf_path.name,
            warnings=["OCR-based parsing is not supported."],
        )

    prompt = _build_prompt(text, bank_hint=bank_hint)
    try:
        data = generate_json(prompt)
    except GeminiError as exc:
        return ParseResult(
            success=False,
            error=f"LLM fallback failed: {exc}",
            file_name=pdf_path.name,
        )

    account, warnings = _to_account(data, bank_hint=bank_hint)
    if not account.transactions:
        return ParseResult(
            success=False,
            error="LLM fallback could not extract transactions.",
            file_name=pdf_path.name,
            warnings=warnings,
        )

    return ParseResult(
        success=True,
        accounts=[account],
        bank_name=account.bank_name,
        file_name=pdf_path.name,
        warnings=warnings,
    )


def _build_prompt(text: str, bank_hint: str = "") -> str:
    hint_line = f"Bank hint: {bank_hint}\n" if bank_hint else ""
    return (
        "You are an assistant that extracts bank statement data into strict JSON.\n"
        "Return ONLY a valid JSON object with this shape:\n"
        "{\n"
        '  "bank_name": "string",\n'
        '  "account_number": "string",\n'
        '  "holder_name": "string",\n'
        '  "ifsc_code": "string",\n'
        '  "branch": "string",\n'
        '  "transactions": [\n'
        "    {\n"
        '      "date": "YYYY-MM-DD",\n'
        '      "description": "string",\n'
        '      "debit": "number or empty",\n'
        '      "credit": "number or empty",\n'
        '      "balance": "number or empty",\n'
        '      "reference": "string",\n'
        '      "value_date": "YYYY-MM-DD or empty"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- If a transaction is a debit, put the amount in debit and leave credit empty.\n"
        "- If a transaction is a credit, put the amount in credit and leave debit empty.\n"
        "- Use ISO dates (YYYY-MM-DD). If uncertain, leave empty.\n"
        "- Do not invent transactions.\n"
        f"{hint_line}"
        "Statement text:\n"
        f"{text}\n"
    )


def _to_decimal(value: object) -> Optional[Decimal]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return parse_indian_number(text)


def _to_account(data: dict, bank_hint: str = "") -> tuple[BankAccount, list[str]]:
    warnings: list[str] = ["Parsed via LLM fallback."]
    bank_name = (data.get("bank_name") or bank_hint or "Unknown Bank").strip()
    account = BankAccount(
        bank_name=bank_name,
        account_number=str(data.get("account_number") or "").strip(),
        holder_name=str(data.get("holder_name") or "").strip(),
        ifsc_code=str(data.get("ifsc_code") or "").strip(),
        branch=str(data.get("branch") or "").strip(),
    )

    txns = []
    for raw in data.get("transactions", []) or []:
        date_str = str(raw.get("date") or "").strip()
        desc = str(raw.get("description") or "").strip()
        if not date_str or not desc:
            continue
        date_val = parse_date_flexible(date_str)
        if not date_val:
            continue

        debit = _to_decimal(raw.get("debit"))
        credit = _to_decimal(raw.get("credit"))
        balance = _to_decimal(raw.get("balance"))
        reference = str(raw.get("reference") or "").strip()
        value_date = parse_date_flexible(str(raw.get("value_date") or "").strip())

        if debit is None and credit is None:
            continue

        txns.append(
            Transaction(
                date=date_val,
                description=desc,
                debit=debit,
                credit=credit,
                balance=balance,
                reference=reference,
                value_date=value_date,
            )
        )

    account.transactions = txns
    if txns:
        account.statement_start = txns[0].date
        account.statement_end = txns[-1].date
        account.opening_balance = txns[0].balance
    return account, warnings
