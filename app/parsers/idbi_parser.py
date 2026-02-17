"""IDBI Bank statement parser (best-effort)."""

import re
from pathlib import Path
from typing import Optional

import pdfplumber

from app.models.domain import BankAccount, ParseResult, Transaction
from app.parsers.base import BaseBankParser
from app.parsers.utils import (
    clean_text,
    parse_date_flexible,
    parse_indian_number,
)


class IDBIParser(BaseBankParser):
    bank_name = "IDBI Bank"

    @staticmethod
    def can_handle(first_page_text: str) -> bool:
        text = first_page_text.lower()
        return "idbi" in text and ("bank" in text or "statement" in text)

    def parse(self, pdf_path: Path, password: Optional[str] = None) -> ParseResult:
        try:
            with pdfplumber.open(pdf_path, password=password) as pdf:
                first_text = pdf.pages[0].extract_text() or ""

                if len(first_text.strip()) < 50:
                    return ParseResult(
                        success=False,
                        error="IDBI PDF appears to be a scanned image. Only digital PDFs are supported.",
                        bank_name=self.bank_name,
                    )

                account = self._extract_account_info(first_text)
                account.source_file = pdf_path.name

                # Try table extraction first
                all_rows = []
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        all_rows.extend(table)

                transactions = self._parse_rows(all_rows)

                # Fallback to text-based if no transactions found
                if not transactions:
                    all_lines = []
                    for page in pdf.pages:
                        text = page.extract_text() or ""
                        all_lines.extend(text.split('\n'))
                    transactions = self._parse_text_lines(all_lines)

                account.transactions = transactions

                if transactions:
                    account.statement_start = transactions[0].date
                    account.statement_end = transactions[-1].date
                    first = transactions[0]
                    if first.is_credit and first.balance:
                        account.opening_balance = first.balance - first.credit
                    elif first.is_debit and first.balance:
                        account.opening_balance = first.balance + first.debit

                warnings = []
                if not transactions:
                    warnings.append("No transactions could be extracted. This may be a scanned PDF.")

                return ParseResult(
                    success=len(transactions) > 0,
                    accounts=[account] if transactions else [],
                    bank_name=self.bank_name,
                    warnings=warnings,
                    error="" if transactions else "No transactions found in IDBI statement.",
                )
        except Exception as e:
            return ParseResult(
                success=False,
                error=f"IDBI parser error: {e}",
                bank_name=self.bank_name,
            )

    def _extract_account_info(self, text: str) -> BankAccount:
        account = BankAccount(bank_name=self.bank_name, account_number="")

        m = re.search(r'Account\s*(?:No|Number)\s*:?\s*(\d+)', text, re.IGNORECASE)
        if m:
            account.account_number = m.group(1)

        m = re.search(r'(?:Name|Customer)\s*:?\s*([A-Z][A-Z\s]+)', text)
        if m:
            account.holder_name = m.group(1).strip()

        m = re.search(r'IFSC\s*:?\s*([A-Z]{4}0[A-Z0-9]{6})', text, re.IGNORECASE)
        if m:
            account.ifsc_code = m.group(1).upper()

        m = re.search(r'Branch\s*:?\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        if m:
            account.branch = m.group(1).strip()

        return account

    def _parse_rows(self, rows: list[list]) -> list[Transaction]:
        transactions: list[Transaction] = []
        header_found = False

        for row in rows:
            if not row or len(row) < 5:
                continue

            cells = [str(c).strip() if c else "" for c in row]
            combined = ' '.join(cells).lower()

            if 'date' in combined and ('debit' in combined or 'credit' in combined):
                header_found = True
                continue

            if not header_found:
                continue

            non_empty = [c for c in cells if c]
            if len(non_empty) < 3:
                continue

            # Try first cell as date
            txn_date = parse_date_flexible(cells[0])
            if not txn_date:
                if transactions and len(cells) > 1 and cells[1]:
                    transactions[-1].description += " " + clean_text(cells[1])
                continue

            # Generic column mapping - try common IDBI patterns
            description = clean_text(cells[1]) if len(cells) > 1 else ""
            reference = cells[2] if len(cells) > 2 else ""
            debit = parse_indian_number(cells[3]) if len(cells) > 3 else None
            credit = parse_indian_number(cells[4]) if len(cells) > 4 else None
            balance = parse_indian_number(cells[5]) if len(cells) > 5 else None

            txn = Transaction(
                date=txn_date,
                description=description,
                debit=debit if debit and debit > 0 else None,
                credit=credit if credit and credit > 0 else None,
                balance=balance,
                reference=reference,
            )
            transactions.append(txn)

        return transactions

    def _parse_text_lines(self, lines: list[str]) -> list[Transaction]:
        """Fallback text-based parsing for IDBI statements."""
        transactions: list[Transaction] = []
        date_pattern = re.compile(r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            m = date_pattern.match(line)
            if not m:
                continue

            txn_date = parse_date_flexible(m.group(1))
            if not txn_date:
                continue

            # Find amounts at end of line
            amounts = re.findall(r'([\d,]+\.\d{2})', line)
            if len(amounts) < 1:
                continue

            # Description is between date and amounts
            rest = line[m.end():].strip()
            desc_end = rest.rfind(amounts[0]) if amounts else len(rest)
            description = clean_text(rest[:desc_end]) if desc_end > 0 else clean_text(rest)

            balance = parse_indian_number(amounts[-1]) if amounts else None
            debit = None
            credit = None

            if len(amounts) >= 2:
                # Heuristic: if balance decreased, it's a debit
                amt = parse_indian_number(amounts[-2])
                if amt and balance is not None and transactions:
                    prev_bal = transactions[-1].balance
                    if prev_bal and balance < prev_bal:
                        debit = amt
                    else:
                        credit = amt

            txn = Transaction(
                date=txn_date,
                description=description,
                debit=debit,
                credit=credit,
                balance=balance,
            )
            transactions.append(txn)

        return transactions
