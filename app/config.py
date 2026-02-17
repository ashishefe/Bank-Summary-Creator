"""Application configuration and constants."""

from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
DB_PATH = BASE_DIR / "bank_summary.db"
GENERATED_PARSERS_DIR = BASE_DIR / "app" / "parsers" / "generated"

_env_local = BASE_DIR / ".env.local"
if _env_local.exists():
    load_dotenv(_env_local)

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
GENERATED_PARSERS_DIR.mkdir(exist_ok=True)

# Indian Financial Year months: April (index 0) through March (index 11)
FY_MONTHS = ["APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC", "JAN", "FEB", "MAR"]
FY_MONTH_NUMBERS = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}

# Foreign banks to reject
FOREIGN_BANKS = ["bank of america", "citibank usa", "chase", "wells fargo"]
