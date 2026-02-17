"""Build dashboard data from account summaries for visual display."""

from decimal import Decimal

from app.config import FY_MONTHS
from app.generator.summary_builder import AccountSummary
from app.models.domain import BankAccount

LARGE_TXN_THRESHOLD = Decimal("100000")  # 1 lakh


def build_dashboard_data(
    accounts: list[BankAccount],
    summaries: list[AccountSummary],
) -> dict:
    """Aggregate summaries into a dashboard-ready dict with float values.

    All Decimal values are converted to float so that Jinja2's tojson filter
    can serialize the result for Chart.js consumption.
    """
    # --- Overview totals ---
    total_credits = Decimal("0")
    total_debits = Decimal("0")
    total_txn_count = 0
    uncategorized_count = 0
    large_transactions: list[dict] = []

    for account in accounts:
        for txn in account.transactions:
            total_txn_count += 1
            if txn.is_credit:
                total_credits += txn.credit
            if txn.is_debit:
                total_debits += txn.debit
            if txn.category == "Uncategorized":
                uncategorized_count += 1
            amount = txn.credit if txn.is_credit else (txn.debit if txn.is_debit else Decimal("0"))
            if amount and amount >= LARGE_TXN_THRESHOLD:
                large_transactions.append({
                    "date": txn.date.strftime("%d/%m/%Y"),
                    "description": txn.description[:80],
                    "amount": float(amount),
                    "type": "Credit" if txn.is_credit else "Debit",
                    "bank": account.bank_name,
                    "account": account.account_number,
                })

    net_cash_flow = total_credits - total_debits

    # --- Monthly cash flow (aggregated across all accounts) ---
    agg_monthly_deposits = [Decimal("0")] * 12
    agg_monthly_withdrawals = [Decimal("0")] * 12
    for s in summaries:
        for i in range(12):
            agg_monthly_deposits[i] += s.monthly_deposits_total[i]
            agg_monthly_withdrawals[i] += s.monthly_withdrawals_total[i]

    # --- Category breakdown (aggregated, sorted by total descending) ---
    # Collect totals and individual transactions per category
    dep_cat_totals: dict[str, Decimal] = {}
    wdl_cat_totals: dict[str, Decimal] = {}
    dep_cat_txns: dict[str, list[dict]] = {}
    wdl_cat_txns: dict[str, list[dict]] = {}

    for account in accounts:
        for txn in account.transactions:
            txn_dict = {
                "date": txn.date.strftime("%d/%m/%Y"),
                "description": txn.description[:80],
                "amount": float(txn.credit if txn.is_credit else txn.debit),
                "bank": account.bank_name,
                "account": account.account_number,
            }
            if txn.is_credit:
                dep_cat_totals[txn.category] = dep_cat_totals.get(txn.category, Decimal("0")) + txn.credit
                dep_cat_txns.setdefault(txn.category, []).append(txn_dict)
            elif txn.is_debit:
                wdl_cat_totals[txn.category] = wdl_cat_totals.get(txn.category, Decimal("0")) + txn.debit
                wdl_cat_txns.setdefault(txn.category, []).append(txn_dict)

    dep_cats_sorted = sorted(dep_cat_totals.items(), key=lambda x: x[1], reverse=True)
    wdl_cats_sorted = sorted(wdl_cat_totals.items(), key=lambda x: x[1], reverse=True)

    # --- Per-account summary cards ---
    account_cards = []
    for s in summaries:
        account_cards.append({
            "bank_name": s.bank_name,
            "account_number": s.account_number,
            "holder_name": s.holder_name,
            "opening_balance": float(s.opening_balance),
            "closing_balance": float(s.final_closing_balance),
            "total_deposits": float(sum(s.monthly_deposits_total)),
            "total_withdrawals": float(sum(s.monthly_withdrawals_total)),
        })

    # Sort large transactions by amount descending, cap at 20
    large_transactions.sort(key=lambda x: x["amount"], reverse=True)

    return {
        "overview": {
            "total_credits": float(total_credits),
            "total_debits": float(total_debits),
            "net_cash_flow": float(net_cash_flow),
            "transaction_count": total_txn_count,
        },
        "monthly_chart": {
            "labels": list(FY_MONTHS),
            "deposits": [float(d) for d in agg_monthly_deposits],
            "withdrawals": [float(w) for w in agg_monthly_withdrawals],
        },
        "categories": {
            "deposits": [
                {"category": c, "total": float(t), "transactions": dep_cat_txns.get(c, [])}
                for c, t in dep_cats_sorted
            ],
            "withdrawals": [
                {"category": c, "total": float(t), "transactions": wdl_cat_txns.get(c, [])}
                for c, t in wdl_cats_sorted
            ],
        },
        "accounts": account_cards,
        "flags": {
            "uncategorized_count": uncategorized_count,
            "large_transactions": large_transactions[:20],
            "large_txn_count": len(large_transactions),
        },
    }
