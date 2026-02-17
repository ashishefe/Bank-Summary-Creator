"""India Post / Post Office Savings statement parser (best-effort)."""

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


class IndiaPostParser(BaseBankParser):
    bank_name = "India Post"

    @staticmethod
    def can_handle(first_page_text: str) -> bool:
        text = first_page_text.lower()
        return any(kw in text for kw in [
            "india post", "post office", "postal", "dop ", "department of posts"
        ])

    def parse(self, pdf_path: Path, password: Optional[str] = None) -> ParseResult:
        try:
            with pdfplumber.open(pdf_path, password=password) as pdf:
                first_text = pdf.pages[0].extract_text() or ""

                if len(first_text.strip()) < 50:
                    return ParseResult(
                        success=False,
                        error="India Post PDF appears to be a scanned image. Only digital PDFs are supported.",
                        bank_name=self.bank_name,
                    )

                account = BankAccount(
                    bank_name=self.bank_name,
                    account_number="",
                    source_file=pdf_path.name,
                )

                # Extract account info
                m = re.search(r'Account\s*(?:No|Number)\s*:?\s*(\d+)', first_text, re.IGNORECASE)
                if m:
                    account.account_number = m.group(1)

                m = re.search(r'(?:Name|Customer)\s*:?\s*([A-Z][A-Z\s]+)', first_text)
                if m:
                    account.holder_name = m.group(1).strip()

                # Try table extraction
                all_rows = []
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        all_rows.extend(table)

                transactions = self._parse_rows(all_rows)

                # Fallback to text
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
                    if first.balance:
                        if first.is_credit:
                            account.opening_balance = first.balance - first.credit
                        elif first.is_debit:
                            account.opening_balance = first.balance + first.debit

                warnings = []
                if not transactions:
                    warnings.append("No transactions extracted. This may be a scanned PDF.")

                return ParseResult(
                    success=len(transactions) > 0,
                    accounts=[account] if transactions else [],
                    bank_name=self.bank_name,
                    warnings=warnings,
                    error="" if transactions else "No transactions found in India Post statement.",
                )
        except Exception as e:
            return ParseResult(
                success=False,
                error=f"India Post parser error: {e}",
                bank_name=self.bank_name,
            )

    def _parse_rows(self, rows: list[list]) -> list[Transaction]:
        transactions: list[Transaction] = []
        header_found = False

        for row in rows:
            if not row or len(row) < 4:
                continue

            cells = [str(c).strip() if c else "" for c in row]
            combined = ' '.join(cells).lower()

            if 'date' in combined and ('debit' in combined or 'credit' in combined or 'deposit' in combined or 'withdrawal' in combined):
                header_found = True
                continue

            if not header_found:
                continue

            txn_date = parse_date_flexible(cells[0])
            if not txn_date:
                continue

            description = clean_text(cells[1]) if len(cells) > 1 else ""
            debit = None
            credit = None
            balance = None

            # Try various column layouts
            for idx in range(2, len(cells)):
                amt = parse_indian_number(cells[idx])
                if amt is not None:
                    if debit is None and idx < len(cells) - 1:
                        debit = amt if amt > 0 else None
                    elif credit is None and idx < len(cells) - 1:
                        credit = amt if amt > 0 else None
                    else:
                        balance = amt

            txn = Transaction(
                date=txn_date,
                description=description,
                debit=debit,
                credit=credit,
                balance=balance,
            )
            transactions.append(txn)

        return transactions

    def _parse_text_lines(self, lines: list[str]) -> list[Transaction]:
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

            amounts = re.findall(r'([\d,]+\.\d{2})', line)
            if not amounts:
                continue

            rest = line[m.end():].strip()
            # Simple heuristic for description
            parts = re.split(r'\s{2,}', rest)
            description = clean_text(parts[0]) if parts else ""

            balance = parse_indian_number(amounts[-1])
            debit = None
            credit = None

            if len(amounts) >= 2:
                amt = parse_indian_number(amounts[0])
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
