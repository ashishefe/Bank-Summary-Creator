"""Transaction categorization engine."""

import re
from typing import Optional

from app.categorizer.rules import get_deposit_rules, get_withdrawal_rules
from app.models.domain import BankAccount, Transaction


class CategorizationEngine:
    """Rule-based transaction categorizer.

    Applies ordered regex rules to transaction descriptions.
    First matching rule wins.
    """

    def __init__(
        self,
        deposit_rules: Optional[list[tuple[str, str]]] = None,
        withdrawal_rules: Optional[list[tuple[str, str]]] = None,
        known_account_numbers: Optional[list[str]] = None,
    ):
        self.deposit_rules = deposit_rules or get_deposit_rules()
        self.withdrawal_rules = withdrawal_rules or get_withdrawal_rules()
        self.known_accounts = set(known_account_numbers or [])

    def categorize_transaction(self, txn: Transaction) -> str:
        """Categorize a single transaction based on its description."""
        desc = txn.description

        rules = self.deposit_rules if txn.is_credit else self.withdrawal_rules

        for pattern, category in rules:
            if re.search(pattern, desc, re.IGNORECASE):
                # Special handling for transfers between own accounts
                if category in ("Transfer from own account", "Transfer to own account"):
                    if self._is_own_account_transfer(desc):
                        return category
                    # Fall through to next rule
                    continue
                return category

        return "Personal receipts" if txn.is_credit else "Personal expenses"

    def categorize_account(self, account: BankAccount) -> None:
        """Categorize all transactions in an account."""
        for txn in account.transactions:
            txn.category = self.categorize_transaction(txn)

    def categorize_all(self, accounts: list[BankAccount]) -> None:
        """Categorize transactions across all accounts.

        Also builds the known accounts set from all account numbers
        for cross-account transfer detection.
        """
        # Build known account numbers from all accounts
        for acct in accounts:
            if acct.account_number:
                self.known_accounts.add(acct.account_number)
                # Also add last 4-6 digits (often used in remarks)
                if len(acct.account_number) >= 4:
                    self.known_accounts.add(acct.account_number[-4:])
                    self.known_accounts.add(acct.account_number[-6:])

        for acct in accounts:
            self.categorize_account(acct)

    def _is_own_account_transfer(self, description: str) -> bool:
        """Check if a transfer references one of the known account numbers."""
        for acc_num in self.known_accounts:
            if acc_num in description:
                return True
        return False


def categorize_accounts(accounts: list[BankAccount]) -> None:
    """Convenience function to categorize all accounts."""
    engine = CategorizationEngine()
    engine.categorize_all(accounts)
