"""Build monthly summary aggregations from categorized transactions."""

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from app.config import FY_MONTH_NUMBERS
from app.models.domain import BankAccount, Transaction
from app.parsers.utils import fy_month_index


@dataclass
class CategoryMonthly:
    """Monthly amounts for a single category."""
    category: str
    monthly: list[Decimal] = field(default_factory=lambda: [Decimal("0")] * 12)

    @property
    def total(self) -> Decimal:
        return sum(self.monthly)


@dataclass
class AccountSummary:
    """Summarized data for one bank account, ready for Excel output."""
    bank_name: str
    branch: str
    account_number: str
    ifsc_code: str
    holder_name: str
    opening_balance: Decimal
    deposit_categories: list[CategoryMonthly] = field(default_factory=list)
    withdrawal_categories: list[CategoryMonthly] = field(default_factory=list)

    @property
    def monthly_opening(self) -> list[Decimal]:
        """Opening balance for each month (chained from previous month's closing)."""
        openings = [Decimal("0")] * 12
        openings[0] = self.opening_balance
        for i in range(1, 12):
            openings[i] = self._closing_for_month(i - 1)
        return openings

    @property
    def monthly_deposits_total(self) -> list[Decimal]:
        """Total deposits per month."""
        totals = [Decimal("0")] * 12
        for cat in self.deposit_categories:
            for i in range(12):
                totals[i] += cat.monthly[i]
        return totals

    @property
    def monthly_withdrawals_total(self) -> list[Decimal]:
        """Total withdrawals per month."""
        totals = [Decimal("0")] * 12
        for cat in self.withdrawal_categories:
            for i in range(12):
                totals[i] += cat.monthly[i]
        return totals

    @property
    def monthly_closing(self) -> list[Decimal]:
        """Closing balance per month."""
        return [self._closing_for_month(i) for i in range(12)]

    def _closing_for_month(self, month_idx: int) -> Decimal:
        if month_idx > 0:
            opening = self._closing_for_month(month_idx - 1)
        else:
            opening = self.opening_balance
        dep = self.monthly_deposits_total[month_idx]
        wdl = self.monthly_withdrawals_total[month_idx]
        return opening + dep - wdl

    @property
    def final_closing_balance(self) -> Decimal:
        return self.monthly_closing[11]


def build_account_summary(account: BankAccount) -> AccountSummary:
    """Aggregate an account's categorized transactions into monthly buckets."""
    opening = account.opening_balance or Decimal("0")

    # Separate deposits and withdrawals by category
    deposit_map: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal("0")] * 12)
    withdrawal_map: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal("0")] * 12)

    # Track category order (first seen)
    deposit_order: list[str] = []
    withdrawal_order: list[str] = []

    for txn in account.transactions:
        mi = fy_month_index(txn.date)

        if txn.is_credit:
            if txn.category not in deposit_order:
                deposit_order.append(txn.category)
            deposit_map[txn.category][mi] += txn.credit
        elif txn.is_debit:
            if txn.category not in withdrawal_order:
                withdrawal_order.append(txn.category)
            withdrawal_map[txn.category][mi] += txn.debit

    # Build CategoryMonthly lists
    deposit_cats = [
        CategoryMonthly(category=cat, monthly=deposit_map[cat])
        for cat in deposit_order
    ]
    withdrawal_cats = [
        CategoryMonthly(category=cat, monthly=withdrawal_map[cat])
        for cat in withdrawal_order
    ]

    return AccountSummary(
        bank_name=account.bank_name,
        branch=account.branch,
        account_number=account.account_number,
        ifsc_code=account.ifsc_code,
        holder_name=account.holder_name,
        opening_balance=opening,
        deposit_categories=deposit_cats,
        withdrawal_categories=withdrawal_cats,
    )
