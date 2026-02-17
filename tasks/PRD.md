# Product Requirements Document: CA Office Tax Return Processing Tool

## Vision

A web application deployed at a Chartered Accountant's office that eliminates the grunt work of income tax return preparation. An employee picks a client, the tool asks for all relevant documents, ingests them regardless of format, and produces a prepared analysis — categorized transactions, cross-referenced data, flagged issues, follow-up questions, and a comprehensive financial dashboard — on which the CA's team can then work efficiently and accurately.

## Market Context

**Current pain points in CA offices:**
- Bank statement processing is the single largest time sink: 2-4 hours per statement manually, across 40+ Indian bank PDF formats
- AIS/26AS/Form 16 reconciliation is fully manual, done in Excel across 4+ data sources
- No existing tool covers the full workflow from document ingestion to ITR-ready analysis
- CAs use 4-7 different software platforms per client filing, with manual data transfer between them
- Over 1.5 lakh tax notices were issued in 2024 due to AIS/ITR mismatches — reconciliation accuracy is critical
- Peak season compression (May-July) means 60-70 hour weeks for CA staff

**Competitive gap:** Tools like Winman, CompuTax, and Genius handle ITR computation and filing. ClearTax and TaxBuddy handle consumer filing. Precisa handles bank statement extraction. But **no tool integrates document ingestion + intelligent analysis + reconciliation** in a single workflow for CA practices.

---

## Phase 1: Stabilize Bank Processing & Client Management

### Goal
Make the existing bank statement processing production-worthy. A CA employee should be able to create a client, upload bank statements, review categorized transactions, and generate reliable Excel summaries — with data persisting across server restarts.

### MVP Deliverables

**1.1 Session Persistence**
- Persist sessions to SQLite using the existing (but unused) DB schema
- Client list page: view all clients, resume any session, see processing status
- Session survives server restart — no data loss

**1.2 Client Management**
- Create client with: name, PAN (optional), assessment year
- List all clients with search/filter
- Per-client history: past sessions, uploaded files, generated outputs
- Delete/archive old sessions

**1.3 Parser Reliability**
- Fix opening balance inconsistencies across parsers (ICICI, SBI, Kotak each handle this differently; LLM fallback uses post-transaction balance incorrectly)
- Fix hardcoded surname extraction in SBI parser
- Add test coverage for each parser with real (anonymized) statement samples
- Improve error messages when parsing fails (actionable guidance, not stack traces)

**1.4 Categorization Improvements**
- When a user reassigns a transaction's category in the review step, remember that mapping for future transactions with similar descriptions (per-client learning)
- Add ability to create custom categories
- Improve transfer detection (currently relies on account number matching; should handle more patterns)

**1.5 UI Polish**
- Progress indicator during PDF processing (currently no feedback while parsing)
- Better error states: show which files failed and why, allow retry
- Mobile-responsive layout (CA employees sometimes work from tablets)

### MVP Success Criteria
- Employee creates a client, uploads 3 bank statements from different banks, reviews categorization, generates Excel — all in under 15 minutes
- Server restart preserves all client data and session state
- Parser success rate > 95% on supported banks
- Test suite covers all 5 parsers + categorizer + generator

---

## Phase 2: Form 26AS & AIS Ingestion + Cross-Referencing

### Goal
Bring in the IT department's view of the client's finances and automatically cross-reference it against bank data. This is the single highest-value addition — CAs currently do this manually in Excel across multiple downloads.

### Context: What These Documents Contain

**Form 26AS** (from TRACES): TDS/TCS credit statement in 10 parts
- Part I: TDS on salary, interest, professional fees, rent, contractor payments (deductor name, TAN, amount, TDS deducted/deposited)
- Part VI: Tax Collected at Source
- Part VII: Refunds issued
- Part X: TDS/TCS defaults

**AIS** (Annual Information Statement): Comprehensive financial activity
- All TDS/TCS data (superset of 26AS)
- SFT (Specified Financial Transactions): savings/FD interest, dividends, securities trades, MF transactions, property deals, cash deposits > 10L, foreign remittances, high-value credit card payments
- Tax payments (advance tax, self-assessment)
- Salary details

**TIS** (Taxpayer Information Summary): Aggregated, deduplicated version of AIS — this is what pre-fills the ITR.

### MVP Deliverables

**2.1 Form 26AS Parser**
- Parse Form 26AS PDF (password-protected with DOB in DDMMYYYY)
- Extract all TDS entries: deductor name, TAN, section, amount paid, TDS deducted, TDS deposited
- Extract tax payments (advance tax, self-assessment challans)
- Extract refund details
- Handle format variations across assessment years

**2.2 AIS Parser**
- Parse AIS PDF download
- Extract all SFT categories: interest income, dividends, securities transactions, MF transactions, property transactions, cash deposits, foreign remittances
- Extract TDS/TCS entries
- Handle the nested, multi-section format

**2.3 Cross-Reference Engine**
- Match TDS entries in 26AS/AIS against bank statement credits (by amount, date proximity, deductor name patterns)
- Match AIS interest income against bank interest credits
- Match AIS dividend entries against bank dividend credits
- Identify: matched entries, unmatched 26AS/AIS entries (income the client may not have reported), unmatched bank entries (income not yet in AIS)
- Confidence scoring for each match (exact amount + date = high; approximate = medium; unmatched = flag)

**2.4 Reconciliation Dashboard**
- Side-by-side view: AIS/26AS entry ↔ matched bank transaction
- Color-coded: green (matched), yellow (approximate match), red (unmatched)
- Summary: total TDS claimable, total income per AIS vs per bank statements, discrepancies count
- Exportable reconciliation report (for CA's working papers)

**2.5 Discrepancy Flags**
- "AIS shows Rs. 45,000 interest from HDFC Bank FD — no matching credit found in uploaded bank statements. Is there an HDFC account not uploaded?"
- "Form 16 shows TDS of Rs. 1,20,000 from Infosys but 26AS shows only Rs. 90,000 — employer may have a filing error in Q4"
- "AIS shows MF redemption of Rs. 5,00,000 from SBI MF — this needs to be reported in Schedule CG"

### MVP Success Criteria
- Parse Form 26AS and AIS with > 90% field extraction accuracy
- Auto-match > 80% of TDS entries to bank transactions
- Surface all unmatched entries as actionable flags
- Reconciliation that previously took 2-3 hours in Excel is done in < 10 minutes of review

---

## Phase 3: Additional Document Types + Document Completeness Checker

### Goal
Ingest Form 16, capital gains statements, and deduction proofs. More importantly, build an intelligent "document completeness checker" that looks at what's been uploaded and tells the employee what's still missing.

### Context: Key Document Formats

**Form 16**: Two parts — Part A (TRACES-generated TDS details) and Part B (employer-prepared salary breakdown with all exemptions, deductions, and tax computation). Critical fields: gross salary breakup, HRA/LTA exemptions, Chapter VI-A deductions, tax computation.

**Capital Gains Statements**: From brokers (Zerodha Tax P&L, Groww, ICICI Direct) and RTAs (CAMS, KFintech). Need scrip-wise buy/sell data with dates for STCG/LTCG computation. For AY 2025-26: must split gains pre/post 23 July 2024 due to tax rate changes.

**Deduction Proofs**: Insurance certificates (80D), home loan interest certificates (24b), donation receipts (80G), PPF/ELSS/LIC statements (80C). Semi-structured PDFs — LLM extraction is the right approach here.

### MVP Deliverables

**3.1 Form 16 Parser**
- Extract Part A: employer details, TDS quarterly summary
- Extract Part B: salary breakup (basic, HRA, LTA, special allowance, perquisites), exemptions under Section 10, Chapter VI-A deductions, tax computation
- Cross-reference Part A TDS against 26AS entries
- Handle multiple Form 16s per client (job change during year)

**3.2 Capital Gains Processor**
- Parse Zerodha Tax P&L report (most common broker format)
- Parse CAMS consolidated account statement (mutual fund gains)
- Parse KFintech consolidated statement
- Compute STCG and LTCG with pre/post 23-July-2024 split
- Aggregate across all broker/RTA sources
- Cross-reference against AIS securities/MF transaction entries

**3.3 Deduction Document Extractor**
- LLM-based extraction for semi-structured deduction proofs
- Extract from insurance premium receipts: insurer, policy number, premium amount, period
- Extract from home loan certificates: lender, loan account, interest paid, principal repaid, outstanding balance
- Extract from donation receipts: donee name, PAN, 80G registration, amount, date
- Map extracted data to relevant ITR sections (80C, 80D, 80G, 24b)

**3.4 Document Completeness Checker**
- Based on uploaded documents, infer client profile (salaried? business? capital gains?)
- Generate a checklist of required documents with status: uploaded / missing / optional
- Smart inference: "Bank statement shows salary credits — Form 16 is required but not uploaded"
- Smart inference: "AIS shows MF redemptions — capital gains statement from CAMS/KFintech needed"
- Smart inference: "Bank shows LIC debit of Rs. 45,000 — LIC premium receipt needed for 80C claim"
- Smart inference: "Bank shows rent payments — is the client claiming HRA? Rent receipts needed"

**3.5 ITR Form Recommendation**
- Based on all ingested data, recommend the correct ITR form (1, 2, 3, or 4)
- Show reasoning: "Client has salary income + capital gains > 1.25L → ITR-2 required"
- Flag if client's situation changed from prior year

### MVP Success Criteria
- Form 16 parsing extracts salary breakup with > 95% accuracy
- Capital gains computation matches broker-reported figures within Rs. 100 tolerance
- Document completeness checker identifies > 90% of missing documents based on available data
- Correct ITR form recommended for > 95% of cases

---

## Phase 4: Intelligent Analysis, Follow-ups & Tax Computation

### Goal
Transform raw ingested data into actionable CA intelligence: auto-computed taxable income, old vs new regime comparison, smart follow-up questions for the end client, and a comprehensive dashboard that gives the CA employee everything they need to proceed.

### MVP Deliverables

**4.1 Income Aggregation Engine**
- Aggregate income under all heads from all uploaded documents:
  - **Salary**: From Form 16 (or bank credits if no Form 16)
  - **House Property**: From rent receipts / home loan certificate / bank rental income
  - **Capital Gains**: From broker/RTA statements (STCG + LTCG, split by asset type and date)
  - **Business/Profession**: From uploaded P&L or presumptive computation
  - **Other Sources**: Interest (bank + FD + savings), dividends, gifts, etc.
- Deduction aggregation: 80C (from investment proofs), 80D (insurance), 80G (donations), 24b (home loan interest), 80E (education loan), 80TTA/80TTB (savings interest)
- Show source traceability: every number links back to the document and line item it came from

**4.2 Tax Computation — Old vs New Regime**
- Compute tax liability under both old and new regime
- Side-by-side comparison showing which regime saves more
- Include: slab computation, rebate u/s 87A, surcharge, education cess (4%)
- Factor in: advance tax already paid, TDS credits from 26AS
- Show: tax payable / refund due under each regime
- Handle AY 2025-26 specifics: new regime zero-tax up to Rs. 12L (12.75L for salaried), updated LTCG/STCG rates

**4.3 Smart Follow-up Question Generator**
- Analyze all ingested data and generate a prioritized list of questions for the end client:
  - **Unexplained credits**: "Rs. 3,20,000 received from XYZ Corp on 15-Aug — is this salary, professional fees, or a personal receipt?"
  - **Large cash deposits**: "Cash deposit of Rs. 5,00,000 on 12-Jan — what is the source? This will likely be questioned by the IT department"
  - **Missing documentation**: "Your bank shows insurance debits totaling Rs. 72,000 but no insurance receipts were provided — please share for 80D claim"
  - **Regime choice**: "Under the old regime your tax is Rs. 2,45,000; under new regime Rs. 1,98,000. Do you want to opt for the new regime? Note: this means forgoing HRA and 80C deductions"
  - **AIS mismatches**: "AIS shows FD interest of Rs. 1,20,000 from ICICI Bank — your bank statement shows only Rs. 95,000. The difference may be accrued but unpaid interest. Should we report the AIS figure?"
  - **Potential issues**: "Total cash deposits across all accounts exceed Rs. 10,00,000 — this is reportable under SFT and may trigger scrutiny"
- Questions exportable as a formatted document (PDF/Word) to send to the client

**4.4 Comprehensive Dashboard**
- **Income Waterfall**: Visual breakdown of gross income → exemptions → deductions → taxable income → tax
- **Head-wise Income Summary**: Salary, House Property, Capital Gains, Business, Other Sources — with drill-down
- **Deduction Utilization**: How much of each deduction limit is used (80C: Rs. 1,12,000 / 1,50,000)
- **Monthly Cash Flow**: Enhanced version of current chart, now annotated with key events (salary months, large transactions, tax payments)
- **Reconciliation Summary**: AIS match rate, unresolved discrepancies count
- **Tax Liability Summary**: Old vs New regime comparison, advance tax credit, final payable/refund
- **Attention Flags**: Categorized as Critical (must resolve before filing), Warning (should review), Info (FYI)

**4.5 Audit Trail**
- Every auto-categorization decision logged with rule that triggered it
- Every cross-reference match logged with confidence score
- Every user override logged (who changed what, when)
- Exportable audit log for CA's working papers

### MVP Success Criteria
- Tax computation matches manual computation within Rs. 10 tolerance
- Old vs New regime recommendation is correct for > 98% of cases
- Follow-up questions are relevant and actionable (< 10% false positives)
- Dashboard loads in < 3 seconds with all data visualized
- Complete audit trail available for every auto-generated number

---

## Phase 5: Production Readiness & Deployment

### Goal
Make the tool deployable and sustainable at a CA's office with multiple employees, proper data management, and integration points with the filing workflow.

### MVP Deliverables

**5.1 Authentication & Multi-User**
- Simple login system (username + password; no need for OAuth complexity)
- Role-based access: Admin (manage users, settings), Preparer (full workflow), Reviewer (read-only + approve)
- Activity log: who did what, when

**5.2 Client Database & Year-over-Year**
- Persistent client database with PAN as unique identifier
- Year-over-year history: view any prior assessment year's data
- Carry forward: prior year's category mappings, custom rules, client notes
- Bulk client import from CSV (for initial migration from existing systems)

**5.3 Workflow Management**
- Per-client status tracking: Document Collection → Processing → Review → Ready for Filing
- Assignment: assign clients to specific employees
- Dashboard for firm admin: how many clients at each stage, who's handling what, bottlenecks

**5.4 Export & Integration**
- Export ITR-ready data as JSON (compatible with IT department's offline utility import format)
- Export reconciliation report as PDF (for working papers)
- Export follow-up questions as formatted document (for client communication)
- Export complete client package as ZIP (all documents + analysis + reports)

**5.5 Deployment & Operations**
- Docker containerization for easy deployment
- Automated database backups
- Data retention policies (configurable per firm)
- Performance: handle 200+ clients per assessment year without degradation
- Offline capability: core processing works without internet (LLM features degrade gracefully)

### MVP Success Criteria
- 3+ employees can work simultaneously without conflicts
- Client data persists reliably across updates and restarts
- Full client processing (all documents → analysis) completes in < 30 minutes of employee time
- Deployment on a standard office machine (no cloud dependency for core features)

---

## Technical Architecture Notes (Cross-Cutting)

### LLM Strategy
- **Primary**: Google Gemini for document extraction (already integrated)
- **Fallback**: Each document type should have a rule-based parser attempt first, LLM only as fallback
- **Cost control**: Cache LLM responses; don't re-parse unchanged documents
- **Accuracy**: Every LLM extraction should be reviewable and overridable by the user

### Data Model Evolution
- Phase 1: Extend existing SQLite schema for session persistence
- Phase 2: Add tables for 26AS/AIS entries and cross-reference matches
- Phase 3: Add tables for Form 16 data, capital gains, deductions
- Phase 4: Add tables for computed tax, follow-up questions, audit log
- Phase 5: Add users, roles, workflow states

### Testing Strategy
- Each parser: unit tests with anonymized real document samples
- Cross-reference engine: integration tests with known match scenarios
- Tax computation: test against manually computed cases (at least 10 client profiles)
- End-to-end: smoke test the full workflow per phase

### What We're NOT Building
- We are not an ITR e-filing portal (we prepare data; filing happens on the IT portal or via existing tools like Winman/CompuTax)
- We are not replacing the CA's judgment (we surface information; the CA makes decisions)
- We are not handling GST, TDS returns, or audit (those are separate workflows)
- We are not a client-facing portal (this is an internal CA office tool)

---

## Phase Sequencing Rationale

Each phase builds on the prior and delivers standalone value:

| Phase | Standalone Value | Depends On |
|-------|-----------------|------------|
| 1. Stabilize Bank Processing | Reliable bank statement → Excel tool for daily use | Nothing (current state) |
| 2. 26AS/AIS Cross-Reference | Automated reconciliation — saves 2-3 hours per client | Phase 1 (needs reliable bank data to cross-reference against) |
| 3. More Document Types | Complete document ingestion + "what's missing?" checker | Phase 2 (cross-referencing is most valuable when all sources are available) |
| 4. Intelligent Analysis | Tax computation, follow-ups, comprehensive dashboard | Phase 3 (needs all income sources to compute accurately) |
| 5. Production Deployment | Multi-user, persistent, deployable office tool | Phase 4 (deploy the complete product) |

The CA's office can start using the tool from Phase 1 onwards, gaining more value with each phase.
