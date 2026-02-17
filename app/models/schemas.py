"""Pydantic schemas for API request/response models."""

from pydantic import BaseModel
from typing import Optional


class FileUploadResponse(BaseModel):
    filename: str
    status: str  # "parsed", "error", "skipped"
    bank_name: str = ""
    account_number: str = ""
    transaction_count: int = 0
    error: str = ""
    warnings: list[str] = []


class TransactionView(BaseModel):
    date: str
    description: str
    debit: Optional[float] = None
    credit: Optional[float] = None
    balance: Optional[float] = None
    category: str = "Uncategorized"


class CategoryGroup(BaseModel):
    category: str
    type: str  # "deposit" or "withdrawal"
    transactions: list[TransactionView] = []
    total: float = 0.0


class AccountView(BaseModel):
    bank_name: str
    account_number: str
    holder_name: str
    transaction_count: int
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None
    categories: list[CategoryGroup] = []


class CategoryUpdate(BaseModel):
    account_index: int
    transaction_indices: list[int]
    new_category: str
