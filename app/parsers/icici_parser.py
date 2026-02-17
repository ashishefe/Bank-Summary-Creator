"""ICICI Bank statement parser.

ICICI format:
- Table columns: S No., Value Date, Transaction Date, Cheque Number,
                  Transaction Remarks, Withdrawal Amount, Deposit Amount, Balance
- Date format: DD/MM/YYYY
- Separate Withdrawal/Deposit columns
- Multi-line transaction remarks (description continues on next row)
- Account info in header text
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


class ICICIParser(BaseBankParser):
    bank_name = "ICICI Bank"

    @staticmethod
    def can_handle(first_page_text: str) -> bool:
        text = first_page_text.lower()
        # ICICI online export has "Transaction Remarks", "Withdrawal Amount", "Deposit Amount"
        # May or may not contain "ICICI Bank" explicitly
        has_icici_columns = (
            "transaction remarks" in text
            and ("withdrawal amount" in text or "withdrawal amt" in text)
            and ("deposit amount" in text or "deposit amt" in text)
        )
        has_icici_name = "icici" in text
        # ICICI JasperReports format: "DETAILED STATEMENT" + column headers
        is_icici_format = "detailed statement" in text and has_icici_columns
        # ICICI full statement format: "Particulars", "Withdrawals", "Deposits"
        has_statement_columns = (
            "particulars" in text
            and "withdrawals" in text
            and "deposits" in text
            and ("icic" in text or "icici" in text)
        )
        return has_icici_name or is_icici_format or has_icici_columns or has_statement_columns

    def parse(self, pdf_path: Path, password: Optional[str] = None) -> ParseResult:
        try:
            with pdfplumber.open(pdf_path, password=password) as pdf:
                # Extract header info from first page text
                first_text = pdf.pages[0].extract_text() or ""
                account = self._extract_account_info(first_text)
                account.source_file = pdf_path.name

                # Extract transactions from all pages
                all_rows = []
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        all_rows.extend(table)

                # Check for B/F (brought forward) opening balance in statement format
                bf_balance = self._extract_bf_balance(all_rows)

                transactions = self._parse_rows(all_rows)
                account.transactions = transactions

                if transactions:
                    account.statement_start = transactions[0].date
                    account.statement_end = transactions[-1].date

                # Determine opening balance
                if bf_balance is not None:
                    account.opening_balance = bf_balance
                elif transactions and transactions[0].balance is not None:
                    first = transactions[0]
                    if first.is_credit:
                        account.opening_balance = first.balance - first.credit
                    elif first.is_debit:
                        account.opening_balance = first.balance + first.debit
                    else:
                        account.opening_balance = first.balance

                return ParseResult(
                    success=True,
                    accounts=[account],
                    bank_name=self.bank_name,
                )
        except Exception as e:
            return ParseResult(
                success=False,
                error=f"ICICI parser error: {e}",
                bank_name=self.bank_name,
            )

    def _extract_account_info(self, text: str) -> BankAccount:
        account = BankAccount(bank_name=self.bank_name, account_number="")

        # Account number - ICICI format: "Account Number : 777701365568"
        m = re.search(r'Account\s*Number\s*:?\s*(\d+)', text, re.IGNORECASE)
        if m:
            account.account_number = m.group(1)

        # Account holder name - try multiple patterns
        # Pattern 1: "Account Number 777701365568(INR) - SARITA HEMANT GOKHALE"
        m = re.search(r'\(INR\)\s*-\s*([A-Z][A-Z\s]+)', text)
        if m:
            account.holder_name = m.group(1).strip()

        # Pattern 2: "Transactions List - NAME - ACCNUM"
        if not account.holder_name:
            m = re.search(r'Transactions\s*List\s*-\s*([A-Z][A-Z\s]+?)\s*-\s*\d+', text)
            if m:
                account.holder_name = m.group(1).strip()

        # Pattern 3: "Name : ..."
        if not account.holder_name:
            m = re.search(r'(?:Name|Customer Name)\s*:?\s*([A-Z][A-Z\s]+)', text)
            if m:
                account.holder_name = m.group(1).strip()

        # IFSC
        m = re.search(r'IFSC\s*:?\s*([A-Z]{4}0[A-Z0-9]{6})', text, re.IGNORECASE)
        if m:
            account.ifsc_code = m.group(1).upper()
        else:
            # Derive from account number prefix if possible
            m = re.search(r'(\d{4})\d+', account.account_number)
            if m:
                account.ifsc_code = f"ICIC000{m.group(1)}"

        # Branch
        m = re.search(r'Branch\s*:?\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        if m:
            account.branch = m.group(1).strip()

        return account

    def _extract_bf_balance(self, rows: list[list]) -> Optional[Decimal]:
        """Extract opening balance from B/F row in statement format."""
        for row in rows:
            if not row or len(row) < 2:
                continue
            cells = [str(c).strip() if c else "" for c in row]
            if cells[1] and cells[1].upper() == "B/F":
                # Balance in last column
                for cell in reversed(cells):
                    if cell and cell.upper() != "B/F":
                        bal = self._parse_balance_with_cr(cell)
                        if bal is not None:
                            return bal
        return None

    def _detect_format(self, rows: list[list]) -> str:
        """Detect which ICICI format we're dealing with."""
        for row in rows:
            if not row:
                continue
            cells = [str(c).strip().lower() if c else "" for c in row]
            combined = ' '.join(cells)
            if 's no' in combined and 'value date' in combined and 'transaction remarks' in combined:
                return "transaction_history"
            if 'date' in cells[0] and 'particulars' in combined and 'withdrawals' in combined:
                return "statement"
        return "unknown"

    def _parse_rows(self, rows: list[list]) -> list[Transaction]:
        """Parse table rows - auto-detects format."""
        fmt = self._detect_format(rows)
        if fmt == "statement":
            return self._parse_statement_rows(rows)
        return self._parse_history_rows(rows)

    def _parse_history_rows(self, rows: list[list]) -> list[Transaction]:
        """Parse ICICI Transaction History format (web export).

        Columns: [S No, Value Date, Txn Date, Cheque No, Remarks, Withdrawal, Deposit, Balance]
        """
        transactions: list[Transaction] = []
        header_found = False

        for row in rows:
            if not row or len(row) < 7:
                continue

            cells = [str(c).strip() if c else "" for c in row]

            if any(h in cells[0].lower() for h in ['s no', 'sr no', 'sl no', 'sno']):
                header_found = True
                continue

            if not header_found:
                combined = ' '.join(cells).lower()
                if 'value date' in combined or 'transaction date' in combined:
                    header_found = True
                    continue
                continue

            non_empty = [c for c in cells if c]
            if not non_empty:
                continue

            txn_date = None
            value_date = None

            if len(cells) > 2:
                value_date = parse_date_flexible(cells[1])
                txn_date = parse_date_flexible(cells[2])

            if txn_date:
                if len(cells) >= 8:
                    remarks = clean_text(cells[4])
                    withdrawal = parse_indian_number(cells[5])
                    deposit = parse_indian_number(cells[6])
                    balance = parse_indian_number(cells[7])
                elif len(cells) >= 7:
                    remarks = clean_text(cells[4])
                    withdrawal = parse_indian_number(cells[5])
                    deposit = parse_indian_number(cells[6])
                    balance = None
                else:
                    continue

                txn = Transaction(
                    date=txn_date,
                    value_date=value_date,
                    description=remarks,
                    debit=withdrawal if withdrawal and withdrawal > 0 else None,
                    credit=deposit if deposit and deposit > 0 else None,
                    balance=balance,
                    reference=cells[3] if len(cells) > 3 else "",
                )
                transactions.append(txn)

            elif transactions:
                continuation = ""
                for cell in cells:
                    if cell and not parse_indian_number(cell) and not parse_date_flexible(cell):
                        if len(cell) > 2:
                            continuation = cell
                            break
                if continuation:
                    prev = transactions[-1]
                    prev.description = f"{prev.description} {clean_text(continuation)}".strip()

        return transactions

    def _parse_balance_with_cr(self, text: str) -> Optional[Decimal]:
        """Parse ICICI balance format like '1,17,579.07 Cr' or '1,17,579.07 Dr'."""
        if not text:
            return None
        text = text.strip()
        is_dr = text.endswith('Dr')
        text = re.sub(r'\s*(Cr|Dr)\s*$', '', text).strip()
        val = parse_indian_number(text)
        if val is not None and is_dr:
            val = -val
        return val

    def _parse_statement_rows(self, rows: list[list]) -> list[Transaction]:
        """Parse ICICI Full Statement format (bank-generated PDF).

        Columns: [Date, Particulars, Chq.No., Withdrawals, Deposits, Autosweep, Reverse Sweep, Balance(INR)]
        """
        transactions: list[Transaction] = []
        header_found = False

        for row in rows:
            if not row or len(row) < 5:
                continue

            cells = [str(c).strip() if c else "" for c in row]
            combined = ' '.join(cells).lower()

            # Detect header
            if 'date' in cells[0].lower() and 'particulars' in combined:
                header_found = True
                continue

            if not header_found:
                continue

            non_empty = [c for c in cells if c]
            if not non_empty:
                continue

            # Try date from first column (DD-MM-YYYY format)
            txn_date = parse_date_flexible(cells[0])
            if not txn_date:
                # Continuation of previous description
                if transactions and cells[1]:
                    transactions[-1].description += " " + clean_text(cells[1])
                continue

            particulars = clean_text(cells[1]) if len(cells) > 1 else ""
            cheque_no = cells[2] if len(cells) > 2 else ""

            # Skip B/F (brought forward) entry - it's the opening balance
            if particulars.upper() == "B/F":
                # Extract opening balance from this row
                continue

            withdrawal = parse_indian_number(cells[3]) if len(cells) > 3 else None
            deposit = parse_indian_number(cells[4]) if len(cells) > 4 else None

            # Balance is in the last column, may have "Cr"/"Dr" suffix
            balance = None
            if len(cells) >= 8:
                balance = self._parse_balance_with_cr(cells[7])
            elif len(cells) >= 6:
                balance = self._parse_balance_with_cr(cells[-1])

            txn = Transaction(
                date=txn_date,
                description=particulars,
                debit=withdrawal if withdrawal and withdrawal > 0 else None,
                credit=deposit if deposit and deposit > 0 else None,
                balance=balance,
                reference=cheque_no,
            )
            transactions.append(txn)

        return transactions
