"""Parsing utilities for Indian bank statements."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from dateutil import parser as dateutil_parser


def parse_indian_number(text: str) -> Optional[Decimal]:
    """Parse Indian-format numbers like '1,28,185.68' or '128185.68'.

    Indian numbering: 1,00,000 = 100000 (lakhs), 1,00,00,000 = 10000000 (crores)
    Also handles regular numbers and numbers with spaces.
    """
    if not text or not isinstance(text, str):
        return None

    text = text.strip()
    if not text:
        return None

    # Remove any currency symbols and whitespace
    text = re.sub(r'[₹\s]', '', text)

    # Handle negative indicators
    is_negative = False
    if text.startswith('-') or text.startswith('('):
        is_negative = True
        text = text.strip('-()').strip()

    if text.endswith('-') or text.endswith('Dr') or text.endswith('DR'):
        is_negative = True
        text = re.sub(r'[-]$|Dr$|DR$', '', text).strip()

    # Remove commas (handles both Indian and Western formats)
    text = text.replace(',', '')

    if not text:
        return None

    try:
        value = Decimal(text)
        return -value if is_negative else value
    except InvalidOperation:
        return None


def parse_date_flexible(text: str) -> Optional[date]:
    """Parse dates in various Indian bank statement formats.

    Supported formats:
    - DD/MM/YYYY (ICICI)
    - DD-MM-YYYY
    - D Mon YYYY (SBI: "1 Apr 2024")
    - DD Mon YYYY (SBI: "15 Apr 2024")
    - DD/MM/YYYY HH:MM:SS (Kotak with timestamps)
    - DD Mon YYYY HH:MM AM/PM
    """
    if not text or not isinstance(text, str):
        return None

    text = text.strip()
    if not text:
        return None

    # Remove time components for date-only parsing
    # Handle "15/04/2024 10:30:00" or "15/04/2024 10:30 AM"
    text = re.sub(r'\s+\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM|am|pm)?', '', text).strip()

    # Try DD/MM/YYYY or DD-MM-YYYY first (most common in Indian statements)
    m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$', text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(year, month, day)
        except ValueError:
            pass

    # Try "D Mon YYYY" or "DD Mon YYYY" (SBI format)
    m = re.match(r'^(\d{1,2})\s+(\w{3,9})\s+(\d{4})$', text)
    if m:
        try:
            dt = datetime.strptime(text, '%d %b %Y')
            return dt.date()
        except ValueError:
            try:
                dt = datetime.strptime(text, '%d %B %Y')
                return dt.date()
            except ValueError:
                pass

    # Fallback to dateutil
    try:
        dt = dateutil_parser.parse(text, dayfirst=True)
        return dt.date()
    except (ValueError, TypeError):
        return None


def fy_month_index(d: date) -> int:
    """Return the Indian FY month index (0=April, 11=March)."""
    month = d.month
    if month >= 4:
        return month - 4
    return month + 8


def clean_text(text: str) -> str:
    """Clean extracted PDF text."""
    if not text:
        return ""
    # Remove special characters from PDF extraction
    text = text.replace('\x00', '')
    text = re.sub(r'\(cid:\d+\)', ' ', text)  # SBI special chars
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def is_valid_transaction_row(row: list) -> bool:
    """Check if a table row likely contains transaction data (not headers or empty)."""
    if not row:
        return False
    non_empty = [cell for cell in row if cell and str(cell).strip()]
    return len(non_empty) >= 3


def extract_account_number(text: str) -> str:
    """Try to extract account number from text."""
    # Common patterns
    patterns = [
        r'Account\s*(?:Number|No\.?|#)\s*:?\s*(\d[\d\s-]+\d)',
        r'A/[Cc]\s*(?:No\.?|Number)\s*:?\s*(\d[\d\s-]+\d)',
        r'Account\s*:?\s*(\d{8,20})',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return re.sub(r'[\s-]', '', m.group(1))
    return ""


def extract_ifsc(text: str) -> str:
    """Extract IFSC code from text."""
    m = re.search(r'IFSC\s*(?:Code)?\s*:?\s*([A-Z]{4}0[A-Z0-9]{6})', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return ""
