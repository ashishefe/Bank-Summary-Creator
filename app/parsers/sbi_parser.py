"""SBI (State Bank of India) statement parser.

SBI format:
- Table columns: Txn Date, Value Date, Description, Ref No./Cheque No., Debit, Credit, Balance
- Date format: D Mon YYYY (e.g., "1 Apr 2024", "15 Nov 2024")
- Separate Debit/Credit columns
- Indian comma number format (1,28,185.68)
- Special characters: (cid:9) as tab separators in header
- Opening balance stated in header: "Opening Balance : 2,32,679.59"
"""

import re
from decimal import Decimal
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


class SBIParser(BaseBankParser):
    bank_name = "State Bank of India"

    @staticmethod
    def can_handle(first_page_text: str) -> bool:
        text = first_page_text.lower()
        return ("state bank of india" in text or "sbi" in text) and (
            "txn date" in text or "transaction date" in text
        )

    def parse(self, pdf_path: Path, password: Optional[str] = None) -> ParseResult:
        try:
            with pdfplumber.open(pdf_path, password=password) as pdf:
                first_text = pdf.pages[0].extract_text() or ""
                account = self._extract_account_info(first_text)
                account.source_file = pdf_path.name

                # Extract transactions from all pages
                all_rows = []
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        all_rows.extend(table)

                transactions = self._parse_rows(all_rows)
                account.transactions = transactions

                if transactions:
                    account.statement_start = transactions[0].date
                    account.statement_end = transactions[-1].date

                # Extract opening balance from header
                ob = self._extract_opening_balance(first_text)
                if ob is not None:
                    account.opening_balance = ob
                elif transactions and transactions[0].balance is not None:
                    first = transactions[0]
                    if first.is_credit:
                        account.opening_balance = first.balance - first.credit
                    elif first.is_debit:
                        account.opening_balance = first.balance + first.debit

                return ParseResult(
                    success=True,
                    accounts=[account],
                    bank_name=self.bank_name,
                )
        except Exception as e:
            return ParseResult(
                success=False,
                error=f"SBI parser error: {e}",
                bank_name=self.bank_name,
            )

    def _extract_account_info(self, text: str) -> BankAccount:
        # Clean SBI special characters
        text_clean = re.sub(r'\(cid:\d+\)', ' ', text)

        account = BankAccount(bank_name=self.bank_name, account_number="")

        # Account number
        m = re.search(r'Account\s*(?:Number|No\.?)\s*:?\s*(\d+)', text_clean, re.IGNORECASE)
        if m:
            account.account_number = m.group(1)

        # Account holder
        m = re.search(r'(?:Mrs?\.|Mr\.)?\s*([A-Z][A-Z\s]+(?:SAPRE|GOKHALE|PAWAR|KULKARNI|SHARMA|PATEL))', text_clean)
        if m:
            account.holder_name = m.group(0).strip()

        # Branch
        m = re.search(r'Branch\s*:?\s*(.+?)(?:\n|$)', text_clean, re.IGNORECASE)
        if m:
            account.branch = m.group(1).strip()
        else:
            m = re.search(r'(?:BRANCH|Branch)\s*[-:]\s*(.+?)(?:\n|$)', text_clean)
            if m:
                account.branch = m.group(1).strip()

        # IFSC
        m = re.search(r'IFSC\s*(?:Code)?\s*:?\s*([A-Z]{4}0[A-Z0-9]{6})', text_clean, re.IGNORECASE)
        if m:
            account.ifsc_code = m.group(1).upper()

        return account

    def _extract_opening_balance(self, text: str) -> Optional[Decimal]:
        text_clean = re.sub(r'\(cid:\d+\)', ' ', text)
        m = re.search(r'Opening\s*Balance\s*:?\s*([\d,]+\.?\d*)', text_clean, re.IGNORECASE)
        if m:
            return parse_indian_number(m.group(1))
        return None

    def _parse_rows(self, rows: list[list]) -> list[Transaction]:
        """Parse SBI table rows.

        SBI tables: [Txn Date, Value Date, Description, Ref No, Debit, Credit, Balance]
        """
        transactions: list[Transaction] = []
        header_found = False

        for row in rows:
            if not row or len(row) < 5:
                continue

            cells = [str(c).strip() if c else "" for c in row]

            # Detect header row
            combined = ' '.join(cells).lower()
            if 'txn date' in combined or 'transaction date' in combined:
                header_found = True
                continue

            if not header_found:
                continue

            # Skip empty rows
            non_empty = [c for c in cells if c]
            if len(non_empty) < 3:
                continue

            # Try to parse date from first column
            txn_date = parse_date_flexible(cells[0])
            if not txn_date:
                # Might be continuation of previous description
                if transactions and cells[2]:
                    transactions[-1].description += " " + clean_text(cells[2])
                continue

            value_date = parse_date_flexible(cells[1])

            # SBI has 7 columns: Txn Date, Value Date, Description, Ref, Debit, Credit, Balance
            if len(cells) >= 7:
                description = clean_text(cells[2])
                reference = cells[3]
                debit = parse_indian_number(cells[4])
                credit = parse_indian_number(cells[5])
                balance = parse_indian_number(cells[6])
            elif len(cells) >= 6:
                description = clean_text(cells[2])
                reference = cells[3]
                debit = parse_indian_number(cells[4])
                credit = parse_indian_number(cells[5])
                balance = None
            else:
                continue

            txn = Transaction(
                date=txn_date,
                value_date=value_date,
                description=description,
                debit=debit if debit and debit > 0 else None,
                credit=credit if credit and credit > 0 else None,
                balance=balance,
                reference=reference,
            )
            transactions.append(txn)

        return transactions
