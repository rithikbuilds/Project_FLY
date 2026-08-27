import csv
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.flywire import (
    USD_AMOUNTS,
    collect_usd_denominations,
)


DATA_DIR = ROOT_DIR / "data"
LATEST_FILE = DATA_DIR / "flywire_latest.json"
HISTORY_FILE = DATA_DIR / "flywire_history.csv"

HISTORY_FIELDS = [
    "timestamp",
    "currency",
    "amount",
    "inr_quote",
    "effective_rate",
    "institution_country",
    "institution",
    "payment_country",
    "funding_type",
    "loan_provider_type",
    "loan_provider",
    "payment_method",
    "source_url",
    "status",
]


def save_latest(records):
    """
    Rebuild flywire_latest.json from the latest successful run.
    """
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not records:
        raise RuntimeError(
            "No Flywire quote records were captured."
        )

    quotes = {}

    for record in records:
        currency = record["currency"]
        amount = str(record["amount"])

        quotes.setdefault(
            currency,
            {},
        )[amount] = record

    payload = {
        "updated_at": max(
            record["timestamp"]
            for record in records
        ),
        "source": "pay.flywire.com",
        "payment_route":
            "India -> Full Loan Financing -> Bank -> SBI -> Offline bank transfer",
        "institution":
            "Harvard University",
        "denominations":
            USD_AMOUNTS,
        "quotes":
            quotes,
    }

    LATEST_FILE.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def append_history(records):
    """
    Append one CSV row for every successful quote.
    """
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    exists = (
        HISTORY_FILE.exists()
        and HISTORY_FILE.stat().st_size > 0
    )

    with HISTORY_FILE.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=HISTORY_FIELDS,
            extrasaction="ignore",
        )

        if not exists:
            writer.writeheader()

        for record in records:
            writer.writerow(
                {
                    field:
                        record.get(
                            field,
                            "",
                        )
                    for field in HISTORY_FIELDS
                }
            )


def print_summary(records):
    print()
    print("================================")
    print("USD FLYWIRE QUOTE SUMMARY")
    print("================================")

    print(
        f"{'Amount':>10} | "
        f"{'INR Quote':>14} | "
        f"{'Effective Rate':>14}"
    )

    print(
        "-" * 45
    )

    for record in records:
        print(
            f"USD {record['amount']:>6,} | "
            f"₹{record['inr_quote']:>12,.2f} | "
            f"₹{record['effective_rate']:>13.4f}"
        )


def main():
    print()
    print("================================")
    print("PROJECT FLY - FLYWIRE CONTROLLER")
    print("================================")
    print(
        "Phase V3.2: Harvard / USD "
        "5,000 to 30,000"
    )
    print(
        "Denominations:",
        ", ".join(
            f"{amount:,}"
            for amount in USD_AMOUNTS
        ),
    )

    records = collect_usd_denominations(
        headless=True,
    )

    save_latest(
        records
    )

    append_history(
        records
    )

    print_summary(
        records
    )

    print()
    print(
        "flywire_latest.json updated."
    )
    print(
        f"{len(records)} rows appended to "
        "flywire_history.csv."
    )
    print(
        "Flywire controller completed successfully."
    )


if __name__ == "__main__":
    main()
