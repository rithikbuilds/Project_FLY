import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_DIR = Path("data")

LATEST_FILE = DATA_DIR / "latest.json"
HISTORY_FILE = DATA_DIR / "history.csv"

CURRENCIES = [
    "USD",
    "CAD",
    "AUD",
    "GBP",
    "EUR",
    "SGD",
    "AED",
    "NZD",
]

IST = ZoneInfo("Asia/Kolkata")


def now_ist():
    return datetime.now(IST)


def calculate_markup(bank_rate, market_rate):

    if not bank_rate or not market_rate:
        return None

    return round(
        ((bank_rate / market_rate) - 1) * 100,
        4
    )


def save_latest(records):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    payload = {
        "updated_at": now_ist().isoformat(),
        "rate_type": "TT Selling / Outward Remittance",
        "rates": records
    }

    with open(
        LATEST_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            payload,
            file,
            indent=2,
            ensure_ascii=False
        )


def append_history(records):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    file_exists = HISTORY_FILE.exists()

    fields = [
        "date",
        "time",
        "bank",
        "currency",
        "rate_type",
        "bank_rate",
        "market_rate",
        "markup_percent",
        "source_url",
        "source_date",
        "fetched_at",
        "status"
    ]

    with open(
        HISTORY_FILE,
        "a",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fields
        )

        if not file_exists:
            writer.writeheader()

        for record in records:

            writer.writerow({
                key: record.get(key, "")
                for key in fields
            })


def main():

    print("Starting FX rate collector...")

    current_time = now_ist()

    print(
        "Run time:",
        current_time.isoformat()
    )

    records = []

    # SBI collector will be added here
    # HDFC collector will be added here
    # Market-rate collector will be added here

    save_latest(records)

    if records:
        append_history(records)

    print(
        f"Finished. {len(records)} rates collected."
    )


if __name__ == "__main__":
    main()
