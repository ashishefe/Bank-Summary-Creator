# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bank Summary Creator is a FastAPI web application that processes Indian bank statement PDFs, auto-categorizes transactions, and generates CA (Chartered Accountant)-ready Excel summaries organized by Indian Financial Year (April–March).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application (default: http://localhost:8000)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest tests/

# Run a single test file
pytest tests/test_parsers/test_icici.py -v

# Run tests with output
pytest tests/ -v -s
```

No linting or type checking tools are currently configured.

## Environment Variables

Set in `.env.local` (gitignored):
- `GEMINI_API_KEY` — Google Gemini API key for LLM-based parsing fallback
- `GEMINI_MODEL` — Gemini model name (e.g., `gemini-3.0-flash`)

## Architecture

### Request Flow

User creates a **session** (client name + assessment year) → uploads PDF bank statements → reviews auto-categorized transactions → generates Excel summary → downloads output.

Routes are defined in `app/main.py`. All responses are HTML (Jinja2 templates) except file downloads.

### Multi-Stage Parsing Pipeline

```
PDF → Bank Detection (bank_detector.py)
  → Known bank? → Use hardcoded parser (icici, sbi, kotak, idbi, india_post)
  → Generated parser exists? → Use it (app/parsers/generated/)
  → Neither? → LLM fallback via Gemini (llm/statement_extractor.py)
  → User can also teach new formats via /format endpoint (llm/format_profiler.py)
```

Each parser extends `BaseBankParser` (`parsers/base.py`) and returns a `ParseResult` containing `BankAccount` objects with `Transaction` lists.

### Key Modules

- **`app/parsers/`** — Bank-specific PDF parsers. Each handles a different statement format (column layouts, date formats, multi-line remarks). `bank_detector.py` routes to the correct parser by scanning PDF text for bank-specific keywords.
- **`app/categorizer/`** — Rule-based transaction categorization. `rules.py` defines regex patterns ordered by priority (first match wins). `engine.py` applies rules and detects cross-account transfers.
- **`app/generator/`** — `summary_builder.py` aggregates transactions into monthly buckets by FY. `excel_writer.py` produces Excel files with native formulas (SUM, balance chains) — not hardcoded values.
- **`app/llm/`** — Gemini integration. `gemini_client.py` wraps the API. `statement_extractor.py` extracts transactions from unknown formats. `format_profiler.py` generates new parser files dynamically.
- **`app/models/`** — `domain.py` has core dataclasses (Transaction, BankAccount, ParseResult, ClientSession). `database.py` has SQLAlchemy models. `schemas.py` has Pydantic schemas.

### Data Model Conventions

- All monetary values use `Decimal` (never float) for precision.
- Dates parsed via `python-dateutil`; Indian formats vary by bank (DD/MM/YYYY, D Mon YYYY, etc.).
- Financial year runs April (month index 0) through March (month index 11). See `config.py: FY_MONTHS`.
- Sessions are stored in-memory (`dict`) and persisted to SQLite (`bank_summary.db`). DB is auto-initialized on app startup via `init_db()`.

### Adding a New Bank Parser

1. Create `app/parsers/<bank>_parser.py` extending `BaseBankParser`.
2. Implement `detect(text) -> bool` and `parse(pages) -> ParseResult`.
3. Register it in `bank_detector.py`'s parser list.
4. Alternatively, users can auto-generate parsers via the `/format` UI endpoint which uses Gemini to profile the PDF and writes to `app/parsers/generated/`.

### File Locations

- Uploaded PDFs: `uploads/<session_id>/`
- Generated Excel files: `output/`
- LLM-generated parsers: `app/parsers/generated/`
- Database: `bank_summary.db` (project root)
- Templates: `app/templates/`
- Static assets: `app/static/`
