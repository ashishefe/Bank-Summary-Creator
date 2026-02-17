"""Domain models for bank statements and transactions."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class Transaction:
    """A single bank transaction."""
    date: date
    description: str
    debit: Optional[Decimal] = None
    credit: Optional[Decimal] = None
    balance: Optional[Decimal] = None
    category: str = "Uncategorized"
    reference: str = ""
    value_date: Optional[date] = None

    @property
    def amount(self) -> Decimal:
        """Positive for credits, negative for debits."""
        if self.credit and self.credit > 0:
            return self.credit
        if self.debit and self.debit > 0:
            return -self.debit
        return Decimal("0")

    @property
    def is_credit(self) -> bool:
        return self.credit is not None and self.credit > 0

    @property
    def is_debit(self) -> bool:
        return self.debit is not None and self.debit > 0


@dataclass
class BankAccount:
    """Parsed bank account with its transactions."""
    bank_name: str
    account_number: str
    holder_name: str = ""
    ifsc_code: str = ""
    branch: str = ""
    transactions: list[Transaction] = field(default_factory=list)
    opening_balance: Optional[Decimal] = None
    statement_start: Optional[date] = None
    statement_end: Optional[date] = None
    source_file: str = ""

    @property
    def closing_balance(self) -> Optional[Decimal]:
        if self.transactions:
            return self.transactions[-1].balance
        return self.opening_balance


@dataclass
class ParseResult:
    """Result from parsing a PDF file."""
    success: bool
    accounts: list[BankAccount] = field(default_factory=list)
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    bank_name: str = ""
    file_name: str = ""


@dataclass
class ClientSession:
    """A client session tracking uploaded files and parsed accounts."""
    session_id: str
    client_name: str = ""
    assessment_year: str = "2025-2026"
    accounts: list[BankAccount] = field(default_factory=list)
    parse_results: list[ParseResult] = field(default_factory=list)
