"""FastAPI application for Bank Summary Creator."""

import uuid
from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.categorizer.engine import CategorizationEngine
from app.config import OUTPUT_DIR, UPLOAD_DIR
from app.llm.format_profiler import profile_format, render_generated_parser, slugify
from app.llm.gemini_client import GeminiError
from app.llm.statement_extractor import extract_pdf_text
from app.generator.dashboard_builder import build_dashboard_data
from app.generator.excel_writer import generate_excel
from app.generator.summary_builder import build_account_summary
from app.models.database import init_db
from app.parsers.bank_detector import detect_and_parse

app = FastAPI(title="Bank Summary Creator")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# In-memory session store (simple for v1.0; backed by SQLite for persistence later)
sessions: dict[str, dict] = {}

init_db()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/summary", response_class=HTMLResponse)
async def summary_start(request: Request):
    return templates.TemplateResponse("summary_start.html", {"request": request})


@app.post("/session/create")
async def create_session(
    request: Request,
    client_name: str = Form(""),
    assessment_year: str = Form("2025-2026"),
):
    session_id = uuid.uuid4().hex[:12]
    sessions[session_id] = {
        "client_name": client_name,
        "assessment_year": assessment_year,
        "accounts": [],
        "parse_results": [],
        "files": [],
    }
    return RedirectResponse(url=f"/upload/{session_id}", status_code=303)


@app.get("/upload/{session_id}", response_class=HTMLResponse)
async def upload_page(request: Request, session_id: str):
    session = sessions.get(session_id)
    if not session:
        return RedirectResponse(url="/")
    return templates.TemplateResponse("upload.html", {
        "request": request,
        "session_id": session_id,
        "session": session,
    })


@app.post("/upload/{session_id}")
async def upload_files(
    request: Request,
    session_id: str,
    files: list[UploadFile] = File(...),
    password: Optional[str] = Form(None),
):
    session = sessions.get(session_id)
    if not session:
        return RedirectResponse(url="/")

    results = []

    for file in files:
        if not file.filename:
            continue

        # Save uploaded file
        session_dir = UPLOAD_DIR / session_id
        session_dir.mkdir(exist_ok=True)
        file_path = session_dir / file.filename

        content = await file.read()
        file_path.write_bytes(content)

        # Parse the file (auto-detect or LLM fallback)
        parse_result = detect_and_parse(file_path, password=password)

        file_info = {
            "filename": file.filename,
            "status": "parsed" if parse_result.success else "error",
            "bank_name": parse_result.bank_name,
            "error": parse_result.error,
            "warnings": parse_result.warnings,
            "account_count": len(parse_result.accounts),
            "transaction_count": sum(
                len(a.transactions) for a in parse_result.accounts
            ),
        }
        session["files"].append(file_info)
        session["parse_results"].append(parse_result)

        if parse_result.success:
            for account in parse_result.accounts:
                session["accounts"].append(account)

        results.append(file_info)

    # Auto-categorize all accounts
    if session["accounts"]:
        engine = CategorizationEngine()
        engine.categorize_all(session["accounts"])

    return templates.TemplateResponse("upload.html", {
        "request": request,
        "session_id": session_id,
        "session": session,
        "upload_results": results,
    })


@app.get("/format", response_class=HTMLResponse)
async def format_page(request: Request):
    return templates.TemplateResponse("add_format.html", {"request": request})


@app.post("/format")
async def format_upload(
    request: Request,
    file: UploadFile = File(...),
    bank_name: str = Form(""),
):
    result = {"status": "error", "message": "", "parser_file": "", "bank_name": ""}

    if not file or not file.filename:
        result["message"] = "Please upload a PDF file."
        return templates.TemplateResponse("add_format.html", {"request": request, "result": result})

    # Save uploaded file
    job_id = uuid.uuid4().hex[:12]
    session_dir = UPLOAD_DIR / "format" / job_id
    session_dir.mkdir(parents=True, exist_ok=True)
    file_path = session_dir / file.filename
    content = await file.read()
    file_path.write_bytes(content)

    # Extract first page text for profiling
    try:
        first_page_text = extract_pdf_text(file_path, max_pages=1, max_chars=15000)
    except Exception as exc:
        result["message"] = f"Could not read PDF: {exc}"
        return templates.TemplateResponse("add_format.html", {"request": request, "result": result})

    if len(first_page_text.strip()) < 50:
        result["message"] = "Scanned/image PDFs are not supported. Please upload a text-based PDF."
        return templates.TemplateResponse("add_format.html", {"request": request, "result": result})

    try:
        profile = profile_format(first_page_text, bank_hint=bank_name.strip())
    except GeminiError as exc:
        result["message"] = f"LLM profiling failed: {exc}"
        return templates.TemplateResponse("add_format.html", {"request": request, "result": result})

    detected_bank = (profile.get("bank_name") or bank_name or "Unknown Bank").strip()
    keywords = profile.get("detection_keywords") or []
    if not isinstance(keywords, list):
        keywords = []
    if not keywords and detected_bank:
        keywords = [detected_bank]

    parser_code = render_generated_parser(detected_bank, keywords)
    parser_slug = slugify(detected_bank)
    parser_path = Path(__file__).parent / "parsers" / "generated" / f"{parser_slug}_parser.py"
    parser_path.write_text(parser_code, encoding="utf-8")

    result.update({
        "status": "success",
        "message": "New bank format added. The parser uses LLM-based extraction.",
        "parser_file": str(parser_path),
        "bank_name": detected_bank,
    })
    return templates.TemplateResponse("add_format.html", {"request": request, "result": result})

@app.get("/review/{session_id}", response_class=HTMLResponse)
async def review_page(request: Request, session_id: str):
    session = sessions.get(session_id)
    if not session:
        return RedirectResponse(url="/")

    accounts = session.get("accounts", [])
    account_views = []

    for i, account in enumerate(accounts):
        # Group transactions by category
        dep_groups: dict[str, list] = defaultdict(list)
        wdl_groups: dict[str, list] = defaultdict(list)

        for j, txn in enumerate(account.transactions):
            txn_view = {
                "index": j,
                "date": txn.date.strftime("%d/%m/%Y"),
                "description": txn.description[:100],
                "debit": float(txn.debit) if txn.debit else None,
                "credit": float(txn.credit) if txn.credit else None,
                "balance": float(txn.balance) if txn.balance else None,
                "category": txn.category,
            }
            if txn.is_credit:
                dep_groups[txn.category].append(txn_view)
            elif txn.is_debit:
                wdl_groups[txn.category].append(txn_view)

        account_views.append({
            "index": i,
            "bank_name": account.bank_name,
            "account_number": account.account_number,
            "holder_name": account.holder_name,
            "transaction_count": len(account.transactions),
            "opening_balance": float(account.opening_balance) if account.opening_balance else 0,
            "closing_balance": float(account.closing_balance) if account.closing_balance else 0,
            "deposit_groups": dict(dep_groups),
            "withdrawal_groups": dict(wdl_groups),
        })

    # Collect all unique categories
    all_deposit_cats = set()
    all_withdrawal_cats = set()
    for acct in accounts:
        for txn in acct.transactions:
            if txn.is_credit:
                all_deposit_cats.add(txn.category)
            elif txn.is_debit:
                all_withdrawal_cats.add(txn.category)

    return templates.TemplateResponse("review.html", {
        "request": request,
        "session_id": session_id,
        "session": session,
        "accounts": account_views,
        "all_deposit_categories": sorted(all_deposit_cats),
        "all_withdrawal_categories": sorted(all_withdrawal_cats),
    })


@app.post("/review/{session_id}/update-category")
async def update_category(
    request: Request,
    session_id: str,
):
    session = sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}

    form = await request.form()
    account_idx = int(form.get("account_index", 0))
    new_category = form.get("new_category", "").strip()
    txn_indices_str = form.get("transaction_indices", "")

    if not new_category or not txn_indices_str:
        return RedirectResponse(url=f"/review/{session_id}", status_code=303)

    txn_indices = [int(i) for i in txn_indices_str.split(",") if i.strip()]

    accounts = session.get("accounts", [])
    if 0 <= account_idx < len(accounts):
        account = accounts[account_idx]
        for idx in txn_indices:
            if 0 <= idx < len(account.transactions):
                account.transactions[idx].category = new_category

    return RedirectResponse(url=f"/review/{session_id}", status_code=303)


@app.post("/generate/{session_id}")
async def generate_summary(request: Request, session_id: str):
    session = sessions.get(session_id)
    if not session:
        return RedirectResponse(url="/")

    accounts = session.get("accounts", [])
    if not accounts:
        return RedirectResponse(url=f"/review/{session_id}", status_code=303)

    # Build summaries
    summaries = [build_account_summary(acct) for acct in accounts]

    # Generate Excel
    output_path = OUTPUT_DIR / f"{session_id}_Bank_Summary.xlsx"
    generate_excel(
        summaries=summaries,
        client_name=session.get("client_name", ""),
        assessment_year=session.get("assessment_year", "2025-2026"),
        output_path=output_path,
        accounts=accounts,
    )

    session["output_file"] = str(output_path)
    session["summaries"] = summaries

    return RedirectResponse(url=f"/dashboard/{session_id}", status_code=303)


@app.get("/dashboard/{session_id}", response_class=HTMLResponse)
async def dashboard_page(request: Request, session_id: str):
    session = sessions.get(session_id)
    if not session:
        return RedirectResponse(url="/")

    accounts = session.get("accounts", [])
    summaries = session.get("summaries")

    # Rebuild summaries if navigating directly (e.g. bookmark or back button)
    if not summaries:
        summaries = [build_account_summary(acct) for acct in accounts]
        session["summaries"] = summaries

    dashboard = build_dashboard_data(accounts, summaries)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "session_id": session_id,
        "session": session,
        "dashboard": dashboard,
        "chart_data": dashboard["monthly_chart"],
    })


@app.get("/download/{session_id}", response_class=HTMLResponse)
async def download_page(request: Request, session_id: str):
    session = sessions.get(session_id)
    if not session:
        return RedirectResponse(url="/")

    return templates.TemplateResponse("download.html", {
        "request": request,
        "session_id": session_id,
        "session": session,
        "has_file": "output_file" in session,
    })


@app.get("/download/{session_id}/file")
async def download_file(session_id: str):
    session = sessions.get(session_id)
    if not session or "output_file" not in session:
        return RedirectResponse(url="/")

    output_path = Path(session["output_file"])
    if not output_path.exists():
        return RedirectResponse(url=f"/download/{session_id}")

    client_name = session.get("client_name", "Client")
    filename = f"{client_name}_Bank_Summary.xlsx" if client_name else "Bank_Summary.xlsx"

    return FileResponse(
        path=output_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
