"""Auto-detect bank from PDF content."""

import importlib
from pathlib import Path
from typing import Optional

import pdfplumber

from app.config import FOREIGN_BANKS, IMAGE_EXTENSIONS, SUPPORTED_EXTENSIONS
from app.llm.statement_extractor import parse_statement_with_llm
from app.models.domain import ParseResult
from app.parsers.base import BaseBankParser
from app.parsers.icici_parser import ICICIParser
from app.parsers.sbi_parser import SBIParser
from app.parsers.kotak_parser import KotakParser
from app.parsers.idbi_parser import IDBIParser
from app.parsers.india_post_parser import IndiaPostParser

# Ordered list of parsers to try
PARSERS: list[type[BaseBankParser]] = [
    ICICIParser,
    SBIParser,
    KotakParser,
    IDBIParser,
    IndiaPostParser,
]


def _load_generated_parsers() -> list[type[BaseBankParser]]:
    parsers: list[type[BaseBankParser]] = []
    generated_dir = Path(__file__).parent / "generated"
    if not generated_dir.exists():
        return parsers

    for parser_file in generated_dir.glob("*_parser.py"):
        module_name = f"app.parsers.generated.{parser_file.stem}"
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue

        # Prefer a class ending with Parser
        parser_cls = None
        for attr in dir(module):
            if attr.endswith("Parser"):
                parser_cls = getattr(module, attr)
                break
        if parser_cls:
            parsers.append(parser_cls)
    return parsers


def detect_and_parse(file_path: Path, password: Optional[str] = None) -> ParseResult:
    """Detect bank type and parse the PDF.

    Returns ParseResult with success=False and appropriate error for:
    - Image files
    - Password-protected PDFs (if no password provided)
    - Foreign bank statements
    - Unrecognized formats
    """
    suffix = file_path.suffix.lower()

    # Reject image files
    if suffix in IMAGE_EXTENSIONS:
        return ParseResult(
            success=False,
            error=f"Image files ({suffix}) are not supported. Only PDF statements can be processed.",
            file_name=file_path.name,
        )

    # Check for supported extension
    if suffix not in SUPPORTED_EXTENSIONS:
        return ParseResult(
            success=False,
            error=f"Unsupported file type: {suffix}",
            file_name=file_path.name,
        )

    # Try to open the PDF
    try:
        pdf = pdfplumber.open(file_path, password=password)
    except Exception as e:
        error_str = str(e).lower()
        if "password" in error_str or "encrypted" in error_str:
            return ParseResult(
                success=False,
                error="This PDF is password-protected. Please provide the password.",
                file_name=file_path.name,
            )
        return ParseResult(
            success=False,
            error=f"Could not open PDF: {e}",
            file_name=file_path.name,
        )

    with pdf:
        # Check if PDF has any pages
        if not pdf.pages:
            return ParseResult(
                success=False,
                error="PDF has no pages.",
                file_name=file_path.name,
            )

        # Extract text from first page
        first_page_text = pdf.pages[0].extract_text() or ""

        # Check if it's a scanned/image PDF (no extractable text)
        if len(first_page_text.strip()) < 50:
            return ParseResult(
                success=False,
                error="This PDF appears to be a scanned image. Only digital/text PDFs are supported.",
                file_name=file_path.name,
                warnings=["OCR-based parsing is not supported in v1.0"],
            )

        # Check for foreign banks
        text_lower = first_page_text.lower()
        for foreign_bank in FOREIGN_BANKS:
            if foreign_bank in text_lower:
                return ParseResult(
                    success=False,
                    error=f"Foreign bank detected ({foreign_bank.title()}). Only Indian bank statements are supported.",
                    file_name=file_path.name,
                    bank_name=foreign_bank.title(),
                )

    # Try each parser (including generated)
    parsers = PARSERS + _load_generated_parsers()
    for parser_cls in parsers:
        if parser_cls.can_handle(first_page_text):
            parser = parser_cls()
            result = parser.parse(file_path, password=password)
            result.file_name = file_path.name
            return result

    # LLM fallback for unrecognized formats
    return parse_statement_with_llm(file_path, password=password)
