"""Kotak Mahindra Bank statement parser.

Kotak format (text-based extraction, tables don't work well):
- Columns: Sr No, Transaction Date, Value Date, Transaction Details, Chq/Ref No,
           Debit/Credit (INR), Balance (INR)
- Combined Debit/Credit column: negative = debit (with - prefix), positive = credit (with + prefix)
- Date format: DD/MM/YYYY (may include timestamps)
- Multi-line transaction descriptions
- Account info in header
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


class KotakParser(BaseBankParser):
    bank_name = "Kotak Mahindra Bank"

    @staticmethod
    def can_handle(first_page_text: str) -> bool:
        text = first_page_text.lower()
        # KKBK is IFSC prefix for Kotak Mahindra Bank
        has_kkbk = "kkbk" in text
        has_kotak = "kotak" in text and ("mahindra" in text or "kmbk" in text or "kotak bank" in text)
        # Kotak format: DEBIT/CREDIT(₹) column with +/- amounts
        has_kotak_format = "debit/credit" in text and ("balance" in text)
        return has_kotak or has_kkbk or (has_kotak_format and "kotak" in text)

    def parse(self, pdf_path: Path, password: Optional[str] = None) -> ParseResult:
        try:
            with pdfplumber.open(pdf_path, password=password) as pdf:
                first_text = pdf.pages[0].extract_text() or ""
                account = self._extract_account_info(first_text)
                account.source_file = pdf_path.name

                # Kotak tables don't extract well; use text-based parsing
                all_text_lines = []
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    all_text_lines.extend(text.split('\n'))

                transactions = self._parse_text_lines(all_text_lines)
                account.transactions = transactions

                if transactions:
                    account.statement_start = transactions[0].date
                    account.statement_end = transactions[-1].date
                    # Opening balance from first transaction
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
                error=f"Kotak parser error: {e}",
                bank_name=self.bank_name,
            )

    def _extract_account_info(self, text: str) -> BankAccount:
        account = BankAccount(bank_name=self.bank_name, account_number="")

        # Account number - Kotak uses various patterns
        m = re.search(r'(?:Account\s*(?:No|Number|#)|A/c\s*No)\s*:?\s*(\d+)', text, re.IGNORECASE)
        if m:
            account.account_number = m.group(1)

        # Customer name - Kotak puts name after account/branch info
        m = re.search(r'(?:Customer Name|Account Name|Name)\s*:?\s*([A-Za-z][A-Za-z\s]+)', text, re.IGNORECASE)
        if m:
            account.holder_name = m.group(1).strip()
        # Try: name is on a line by itself after the date range line
        if not account.holder_name:
            lines = text.split('\n')
            for i, line in enumerate(lines):
                if re.match(r'\d{2}\s+\w{3}\s+\d{4}\s*-\s*\d{2}\s+\w{3}\s+\d{4}', line.strip()):
                    # Next line is typically the name
                    if i + 1 < len(lines):
                        name_candidate = lines[i + 1].strip()
                        if re.match(r'^[A-Za-z][A-Za-z\s]+$', name_candidate) and len(name_candidate) > 3:
                            account.holder_name = name_candidate
                    break

        # Branch
        m = re.search(r'(?:Branch|Home Branch)\s*:?\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        if m:
            account.branch = m.group(1).strip()

        # IFSC
        m = re.search(r'IFSC\s*:?\s*([A-Z]{4}0[A-Z0-9]{6})', text, re.IGNORECASE)
        if m:
            account.ifsc_code = m.group(1).upper()

        return account

    def _parse_text_lines(self, lines: list[str]) -> list[Transaction]:
        """Parse Kotak transactions from text lines.

        Actual Kotak format:
        Line: "1 02 Apr 2024 02 Apr 2024 LOCKER RENT FOR 75/R3/0157 CMS-210709000010 -1,770.00 4,09,870.52"
        Next line may have time: "02:12 AM"
        Or continuation of description.

        Key: serial number, two dates (DD Mon YYYY), description, ref, +/-amount, balance
        """
        transactions: list[Transaction] = []
        in_transactions = False

        # Pattern: starts with serial number, then "DD Mon YYYY DD Mon YYYY"
        txn_start = re.compile(
            r'^\s*(\d+)\s+'
            r'(\d{2}\s+\w{3}\s+\d{4})\s+'    # Transaction date
            r'(\d{2}\s+\w{3}\s+\d{4})\s+'    # Value date
            r'(.+?)\s+'                        # Description + ref
            r'([+-][\d,]+\.?\d*)\s+'           # Amount with +/-
            r'([\d,]+\.?\d*)\s*$'              # Balance
        )

        # Simpler start detection: serial number + date pattern
        date_detect = re.compile(r'^\s*(\d+)\s+(\d{2}\s+\w{3}\s+\d{4})')

        i = 0
        while i < len(lines):
            line = lines[i]

            # Detect start of transaction section
            if not in_transactions:
                if 'transaction date' in line.lower() or 'debit/credit' in line.lower():
                    in_transactions = True
                i += 1
                continue

            line_stripped = line.strip()

            # Skip empty lines
            if not line_stripped:
                i += 1
                continue

            # Skip page headers/footers
            if any(marker in line_stripped.lower() for marker in [
                'account statement', 'page ', 'branch ', 'statement summary',
                'total debit', 'total credit', 'effective balance',
                '# transaction date', 'transaction details',
            ]):
                i += 1
                continue

            # Try to match a full transaction line
            m = txn_start.match(line)
            if m:
                txn_date = parse_date_flexible(m.group(2))
                value_date = parse_date_flexible(m.group(3))
                desc_and_ref = m.group(4).strip()
                amount_str = m.group(5)
                balance_str = m.group(6)

                if not txn_date:
                    i += 1
                    continue

                amount = parse_indian_number(amount_str)
                balance = parse_indian_number(balance_str)

                # Split description and reference (ref is typically last token with specific patterns)
                description = clean_text(desc_and_ref)
                reference = ""
                ref_match = re.search(r'\s+([\w-]{10,})\s*$', desc_and_ref)
                if ref_match:
                    reference = ref_match.group(1)
                    description = clean_text(desc_and_ref[:ref_match.start()])

                debit = None
                credit = None
                if amount is not None:
                    if amount < 0:
                        debit = abs(amount)
                    else:
                        credit = amount

                txn = Transaction(
                    date=txn_date,
                    value_date=value_date,
                    description=description,
                    debit=debit,
                    credit=credit,
                    balance=balance,
                    reference=reference,
                )

                # Collect continuation lines (time stamps, description overflow)
                i += 1
                while i < len(lines):
                    next_line = lines[i].strip()
                    if not next_line:
                        i += 1
                        break
                    # Check if next line is a new transaction
                    if date_detect.match(lines[i]):
                        break
                    # Skip time-only lines
                    if re.match(r'^\d{2}:\d{2}\s*(AM|PM)?$', next_line, re.IGNORECASE):
                        i += 1
                        continue
                    # Skip page markers
                    if any(marker in next_line.lower() for marker in [
                        'account statement', 'page ', 'branch ', 'statement summary',
                        'total debit', 'total credit', '# transaction date', 'ifsc',
                    ]):
                        i += 1
                        continue
                    # Description continuation
                    txn.description += " " + clean_text(next_line)
                    i += 1

                transactions.append(txn)
                continue

            # Also try matching without the full pattern (partial line)
            dm = date_detect.match(line)
            if dm:
                # Line starts with serial + date but didn't match full pattern
                # Try to extract what we can
                rest = line[dm.end():].strip()
                txn_date = parse_date_flexible(dm.group(2))

                # Look for second date
                date2_match = re.match(r'(\d{2}\s+\w{3}\s+\d{4})\s+(.*)', rest)
                if date2_match and txn_date:
                    value_date = parse_date_flexible(date2_match.group(1))
                    remainder = date2_match.group(2)

                    # Try to extract amount and balance from end
                    amt_match = re.search(r'([+-][\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s*$', remainder)
                    if amt_match:
                        desc = clean_text(remainder[:amt_match.start()])
                        amount = parse_indian_number(amt_match.group(1))
                        balance = parse_indian_number(amt_match.group(2))

                        debit = None
                        credit = None
                        if amount is not None:
                            if amount < 0:
                                debit = abs(amount)
                            else:
                                credit = amount

                        txn = Transaction(
                            date=txn_date,
                            value_date=value_date,
                            description=desc,
                            debit=debit,
                            credit=credit,
                            balance=balance,
                        )

                        # Collect continuation lines
                        i += 1
                        while i < len(lines):
                            next_line = lines[i].strip()
                            if not next_line:
                                i += 1
                                break
                            if date_detect.match(lines[i]):
                                break
                            if re.match(r'^\d{2}:\d{2}\s*(AM|PM)?$', next_line, re.IGNORECASE):
                                i += 1
                                continue
                            if any(marker in next_line.lower() for marker in [
                                'account statement', 'page ', 'branch ', 'statement summary',
                            ]):
                                i += 1
                                continue
                            txn.description += " " + clean_text(next_line)
                            i += 1

                        transactions.append(txn)
                        continue

            i += 1

        return transactions
