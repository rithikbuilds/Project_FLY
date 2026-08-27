import csv
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.flywire import collect_usd_5000

DATA_DIR = ROOT_DIR / "data"
LATEST_FILE = DATA_DIR / "flywire_latest.json"
HISTORY_FILE = DATA_DIR / "flywire_history.csv"

HISTORY_FIELDS = [
    "timestamp", "currency", "amount", "inr_quote", "effective_rate",
    "institution_country", "institution", "payment_country", "funding_type",
    "loan_provider_type", "loan_provider", "payment_method", "source_url", "status",
]


def save_latest(record):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": record["timestamp"],
        "source": "pay.flywire.com",
        "payment_route": "India -> Full Loan Financing -> Bank -> SBI -> Offline bank transfer",
        "quotes": {record["currency"]: {str(record["amount"]): record}},
    }
    LATEST_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def append_history(record):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    exists = HISTORY_FILE.exists() and HISTORY_FILE.stat().st_size > 0
    with HISTORY_FILE.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({field: record.get(field, "") for field in HISTORY_FIELDS})


def main():
    print("\n================================")
    print("PROJECT FLY - FLYWIRE CONTROLLER")
    print("================================")
    print("Phase V3.1: Harvard / USD 5,000 only")

    record = collect_usd_5000(headless=True)
    save_latest(record)
    append_history(record)

    print("\nRESULT")
    print(record["currency"], record["amount"], "| INR:", record["inr_quote"], "| Effective Rate:", record["effective_rate"])
    print("Flywire controller completed successfully.")


if __name__ == "__main__":
    main()
