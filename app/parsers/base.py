"""Base class for bank statement parsers."""

from abc import ABC, abstractmethod
from pathlib import Path

from app.models.domain import ParseResult


class BaseBankParser(ABC):
    """Abstract base class for bank-specific PDF parsers."""

    bank_name: str = "Unknown"

    @abstractmethod
    def parse(self, pdf_path: Path, password: str | None = None) -> ParseResult:
        """Parse a PDF file and return extracted transactions."""
        ...

    @staticmethod
    def can_handle(first_page_text: str) -> bool:
        """Check if this parser can handle the given PDF based on first page text."""
        return False
