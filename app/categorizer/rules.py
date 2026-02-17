"""Category rules for transaction classification.

Rules are ordered by priority - first match wins.
Each rule is a (pattern, category) tuple where pattern is a regex applied to
the transaction description/remarks.
"""

# Deposit categories (credit transactions)
DEPOSIT_RULES: list[tuple[str, str]] = [
    # Interest categories
    (r'(?:Int\.?\s*Pd|CREDIT\s*INTEREST|INT\s*ON\s*SAV|Savings?\s*(?:A/?c)?\s*Interest|IntPd)', "Savings Interest"),
    (r'(?:Int\s*on\s*FD|Int\s*on\s*RD|TD\s*Int|FD\s*INT|Term\s*Dep(?:osit)?\s*Int|INTT\s*ON\s*TD)', "Interest from Bank Term Deposits"),
    (r'(?:Int(?:erest)?\s*on\s*PPF|PPF\s*Int)', "Interest on PPF"),

    # Dividends
    (r'(?:DIV(?:IDEND)?|IntDiv|Interim\s*Dividend|Final\s*Dividend)', "Dividends"),
    (r'(?:ACH/.*DIV|CMS/.*(?:Div|DIVIDEND))', "Dividends"),
    # ACH credits from known listed companies (typically dividends/debenture interest)
    (r'ACH/(?:REC LIMITED|COAL INDIA|POWER GRID|POWER FINANCE|DABUR|RELIANCE INDUSTRIES|GODREJ AGROVET|MARUTI SUZUKI|GENERAL INSURANCE|NTPC|BHARATFRG|ALKEM|HDFCBANKLTD|KPIT TECHNOLOGIES|BSL|TML)', "Dividends"),
    (r'CMS/(?:KIRLOSKAR|Bata|Bharat Forge)', "Dividends"),

    # Salary
    (r'(?:SALARY|SAL\s*CR|Halliburton|salary\s*for)', "Salary"),

    # Pension
    (r'(?:PENSION|GOVT\s*OF|CPPC|pension)', "Pension"),

    # Insurance payouts/maturity
    (r'(?:LIC\s*(?:OF\s*INDIA)?\s*(?:CR|MAT|PAYOUT)|INS(?:URANCE)?\s*(?:PAYOUT|CLAIM|MATURITY))', "Insurance payout"),
    (r'(?:Kotak\s*Life.*CR|MAX\s*LIFE.*CR|ICICI\s*Prud.*CR|Mediclaim\s*reimb)', "Insurance payout"),
    (r'(?:SBI\s*LIFE\s*INS)', "Insurance payout"),

    # FD maturity
    (r'(?:FD\s*MAT(?:URITY)?|MATURED\s*FD|FD\s*MATURITY\s*PROCEEDS|FD\s*(?:Closure|Proceeds))', "FD Maturity Proceeds"),
    (r'(?:Closure\s*proceeds|(?:FDR?|TD)\s*(?:MAT|MATURITY|Closure))', "FD Maturity Proceeds"),

    # Income tax refund
    (r'(?:INCOME\s*TAX\s*REFUND|IT\s*REFUND|CPC\s*REFUND|NSDL.*refund)', "Income tax refund"),

    # Mutual fund / investment redemptions
    (r'(?:MF\s*REDEM|MUTUAL\s*FUND.*REDEM|Redemption)', "Mutual Fund Redemptions"),

    # Professional / business receipts
    (r'(?:Dialectica|Professional\s*(?:Fees|Receipt)|Consultancy\s*fees|FP\s*India)', "Business/Professional receipts"),

    # Rent received
    (r'(?:RENT\s*(?:CR|REC|RECEIVED)|rent\s*from)', "Rent"),

    # Bond interest
    (r'(?:IRFC\s*Bond|Bond\s*Int)', "Bond Interest"),

    # Reverse sweep / auto-sweep returns
    (r'(?:Reverse\s*Sweep|SWEEP\s*REV|Auto\s*Sweep\s*Rev)', "Reverse Sweep"),

    # Transfers from own accounts (will be refined with known account numbers)
    (r'(?:BIL/INFT|BIL/ONL|NEFT.*(?:self|own)|Transfer\s*from\s*(?:SB|Savings|own))', "Transfer from own account"),
    (r'(?:trf\s*from|Transfer\s*from)', "Transfer from own account"),

    # UPI / generic credits
    (r'(?:UPI[-/]CR|UPI.*(?:CR|credit)|UPI/)', "Personal receipts"),

    # Cash deposit
    (r'(?:CASH\s*DEP|Cash\s*Deposit|CDM)', "Cash deposit"),

    # Default deposit
    (r'.+', "Personal receipts"),
]

# Withdrawal categories (debit transactions)
WITHDRAWAL_RULES: list[tuple[str, str]] = [
    # Tax payments
    (r'(?:DTAX|GIB/DTAX|Advance\s*Tax)', "Advance Tax"),
    (r'(?:INCOME\s*TAX|IT\s*PAYMENT|SA\s*Tax\s*paid|USINDIA\s*Tax)', "Income Tax"),
    (r'(?:Tax\s*Fees|TDS)', "Tax Fees"),

    # Insurance premiums
    (r'(?:LIC\s*(?:OF\s*INDIA)?(?:\s*(?:DR|DEB|PREMIUM))?|LIC\s*INS)', "Insurance - LIC"),
    (r'(?:New\s*India\s*(?:Assurance|Insurance)|NIACL)', "Insurance - New India"),
    (r'(?:Kotak\s*Life|K-?life)', "Insurance - Kotak Life"),
    (r'(?:MAX\s*LIFE|MAXLIFE)', "Insurance - Max Life"),
    (r'(?:ICICI\s*Prud|ICICI\s*Lombard)', "Insurance - ICICI"),
    (r'(?:Care\s*Health|CARE\s*INS)', "Insurance - Care Health"),
    (r'(?:Medical\s*(?:Ins|Insurance)|Mediclaim|Health\s*Ins)', "Medical Insurance"),
    (r'(?:Sanika\s*Insur)', "Insurance"),

    # FD/TD investment
    (r'(?:FD\s*(?:BOOK|INVEST|OPENING|PLACEMENT)|(?:New|Open)\s*FD|TO\s*FD|FDR?\s*(?:Book|Open))', "FD investment"),

    # PPF
    (r'(?:PPF|Public\s*Provident)', "Transfer to PPF"),

    # Credit card payments
    (r'(?:CC\s*(?:WHITE\s*)?PAY|Credit\s*Card|CCPAY|CC\s*BILL)', "Credit card payment"),

    # Investment - shares/MF
    (r'(?:Purchase\s*of\s*shares|MFP|EBA\s*NSE|EBA/MFP|Upstream\s*Pay)', "Investment"),
    (r'(?:NSDL|CDSL|DP\s*(?:CHARGES|CHG)|DMC|Demat)', "NSDL/CDSL charges"),

    # Bank charges
    (r'(?:SMSChgs|SMS\s*(?:CHARGES|Chgs)|Card\s*dues|Locker\s*Rent|Service\s*(?:Charge|Tax)|Bank\s*(?:Charges?|Chgs?)|GST\s*ON|Folio\s*Chgs|ANNUAL\s*FEE|MAINTENANCE\s*CHG)', "Bank charges"),

    # Maintenance / Society
    (r'(?:Maintenance|Society|FOREST\s*TRAIL|VIJAYDURG|Maint\s*flat)', "Maintenance/Society"),

    # Property tax / Municipal tax
    (r'(?:Property\s*Tax|PROP\s*TAX|Municipal\s*Corp|PMC|Pune\s*Municipal|Corporation\s*Tax)', "Property Tax"),

    # Donations
    (r'(?:Donat(?:ion)?|Aakar\s*Foundation)', "Donations"),

    # Cash withdrawals
    (r'(?:ATM\s*(?:WDL|WITHDR)|Cash\s*(?:WDL|Withdrawal)|ATM/CASH|NFS/)', "Cash withdrawals"),

    # Forex
    (r'(?:Purchase\s*of\s*GBP|Forex|FOREX)', "Forex Payment"),

    # Transfers to own accounts
    (r'(?:BIL/INFT|NEFT.*(?:self|own)|Transfer\s*to\s*(?:SB|Savings|own))', "Transfer to own account"),
    (r'(?:trf\s*to|Transfer\s*to)', "Transfer to 3rd party"),

    # UPI / generic debits -> Personal expenses
    (r'(?:UPI[-/]|UPI\s)', "Personal expenses"),

    # Cheque payments
    (r'(?:CLG/|CHQ|Cheque)', "Personal expenses"),

    # Default withdrawal
    (r'.+', "Personal expenses"),
]


def get_deposit_rules() -> list[tuple[str, str]]:
    return DEPOSIT_RULES.copy()


def get_withdrawal_rules() -> list[tuple[str, str]]:
    return WITHDRAWAL_RULES.copy()
