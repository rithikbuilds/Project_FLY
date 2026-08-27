import csv
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.flywire import CURRENCY_ROUTES, QUOTE_AMOUNTS, collect_currency_denominations

DATA_DIR = ROOT_DIR / "data"
LATEST_FILE = DATA_DIR / "flywire_latest.json"
HISTORY_FILE = DATA_DIR / "flywire_history.csv"

HISTORY_FIELDS = [
    "timestamp","currency","amount","inr_quote","effective_rate",
    "institution_country","institution","payment_country","funding_type",
    "loan_provider_type","loan_provider","payment_method","source_url","status",
]


def load_latest():
    if LATEST_FILE.exists():
        try:
            return json.loads(LATEST_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "updated_at": None,
        "source": "pay.flywire.com",
        "payment_route": "India -> Full Loan Financing -> Bank -> SBI -> Offline bank transfer",
        "denominations": QUOTE_AMOUNTS,
        "quotes": {},
    }


def merge_latest(records):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = load_latest()
    payload["source"] = "pay.flywire.com"
    payload["payment_route"] = "India -> Full Loan Financing -> Bank -> SBI -> Offline bank transfer"
    payload["denominations"] = QUOTE_AMOUNTS
    payload["routes"] = CURRENCY_ROUTES
    quotes = payload.setdefault("quotes", {})

    for record in records:
        quotes.setdefault(record["currency"], {})[str(record["amount"])] = record

    timestamps = [
        r.get("timestamp")
        for currency_quotes in quotes.values()
        if isinstance(currency_quotes, dict)
        for r in currency_quotes.values()
        if isinstance(r, dict) and r.get("timestamp")
    ]
    payload["updated_at"] = max(timestamps) if timestamps else None
    LATEST_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def append_history(records):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    exists = HISTORY_FILE.exists() and HISTORY_FILE.stat().st_size > 0
    with HISTORY_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in HISTORY_FIELDS})


def print_summary(currency, records):
    print()
    print("================================")
    print(f"{currency} FLYWIRE QUOTE SUMMARY")
    print("================================")
    for r in records:
        print(
            f"{currency} {r['amount']:>6,} | "
            f"INR {r['inr_quote']:>12,.2f} | "
            f"Rate {r['effective_rate']:.4f}"
        )


def main():
    currencies = list(CURRENCY_ROUTES.keys())
    total = len(currencies) * len(QUOTE_AMOUNTS)

    print("================================")
    print("PROJECT FLY - FLYWIRE CONTROLLER")
    print("================================")
    print("Phase V3.4: Multi-currency quote capture")
    print("Currencies:", ", ".join(currencies))
    print("Denominations:", ", ".join(f"{a:,}" for a in QUOTE_AMOUNTS))
    print("Total planned quotes:", total)

    completed = 0

    for index, currency in enumerate(currencies, start=1):
        route = CURRENCY_ROUTES[currency]
        print()
        print("################################")
        print(f"CURRENCY {index}/{len(currencies)}: {currency}")
        print(f"{route['institution_country']} -> {route['institution']}")
        print("################################")

        records = collect_currency_denominations(currency, headless=True)

        # Save after each completed currency so earlier successful batches survive
        # if a later institution/currency needs selector/name adjustment.
        merge_latest(records)
        append_history(records)
        print_summary(currency, records)

        completed += len(records)
        print(f"Saved {completed}/{total} planned quotes.")

    print()
    print("================================")
    print("FLYWIRE V3.4 COMPLETE")
    print("================================")
    print(f"{completed} quotes captured successfully.")
    print("flywire_latest.json updated.")
    print("flywire_history.csv updated.")


if __name__ == "__main__":
    main()
