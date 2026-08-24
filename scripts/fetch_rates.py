import csv
import json
import sys

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


# ==========================================================
# PATH SETUP
# ==========================================================

ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from agents import sbi
from agents import axis
from agents import icici
from agents import canara
from agents import bob
from agents import hdfc
from agents import market


# ==========================================================
# CONFIGURATION
# ==========================================================

DATA_DIR = ROOT_DIR / "data"

LATEST_FILE = DATA_DIR / "latest.json"

HISTORY_FILE = DATA_DIR / "history.csv"

IST = ZoneInfo("Asia/Kolkata")

RATE_TYPE = "TT Selling / Outward Remittance"


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


# ==========================================================
# TIME
# ==========================================================

def now_ist():

    return datetime.now(IST)


# ==========================================================
# VALIDATION
# ==========================================================

def validate_record(record):

    ranges = {
        "USD": (70, 130),
        "CAD": (40, 100),
        "AUD": (40, 100),
        "GBP": (90, 180),
        "EUR": (80, 160),
        "SGD": (45, 110),
        "AED": (15, 40),
        "NZD": (30, 90),
    }


    required_fields = [
        "bank",
        "currency",
        "bank_rate",
        "source_url",
        "source_date",
        "status",
    ]


    for field in required_fields:

        if record.get(field) is None:

            print(
                "REJECTED:",
                record.get("bank"),
                record.get("currency"),
                "missing",
                field
            )

            return False


    currency = record["currency"]


    if currency not in ranges:

        print(
            "REJECTED unknown currency:",
            currency
        )

        return False


    try:

        rate = float(
            record["bank_rate"]
        )

    except (TypeError, ValueError):

        print(
            "REJECTED invalid rate:",
            record.get("bank"),
            currency,
            record.get("bank_rate")
        )

        return False


    low, high = ranges[
        currency
    ]


    if not low <= rate <= high:

        print(
            "REJECTED suspicious rate:",
            record.get("bank"),
            currency,
            rate
        )

        return False


    return True


# ==========================================================
# LOAD PREVIOUS LATEST
# ==========================================================

def load_previous_latest():

    if not LATEST_FILE.exists():

        return []


    try:

        with open(
            LATEST_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            payload = json.load(
                file
            )


        return payload.get(
            "rates",
            []
        )


    except Exception as error:

        print(
            "Could not read previous latest.json:",
            error
        )

        return []


# ==========================================================
# PRESERVE FAILED BANK
# ==========================================================

def preserve_failed_bank(
    bank_name,
    previous_records
):

    preserved = []


    for record in previous_records:

        if record.get("bank") != bank_name:

            continue


        copied = dict(
            record
        )


        copied["status"] = "stale"


        preserved.append(
            copied
        )


    return preserved


# ==========================================================
# DEDUPLICATE
# ==========================================================

def deduplicate(records):

    unique = {}


    for record in records:

        key = (
            record.get("bank"),
            record.get("currency")
        )


        existing = unique.get(
            key
        )


        if existing is None:

            unique[key] = record

            continue


        if (
            existing.get("status") != "current"
            and
            record.get("status") == "current"
        ):

            unique[key] = record


    return list(
        unique.values()
    )


# ==========================================================
# MARKET RATE ENRICHMENT
# ==========================================================

def apply_market_rates(
    records,
    market_result
):

    market_rates = (
        market_result.get(
            "rates",
            {}
        )
    )


    source_name = (
        market_result.get(
            "source"
        )
    )


    source_url = (
        market_result.get(
            "source_url"
        )
    )


    source_timestamp = (
        market_result.get(
            "source_timestamp"
        )
    )


    market_fetched_at = (
        market_result.get(
            "fetched_at"
        )
    )


    enriched = []


    for record in records:

        copied = dict(
            record
        )


        currency = copied.get(
            "currency"
        )


        bank_rate = copied.get(
            "bank_rate"
        )


        market_rate = market_rates.get(
            currency
        )


        copied["market_source"] = source_name

        copied["market_source_url"] = source_url

        copied["market_source_timestamp"] = (
            source_timestamp
        )

        copied["market_fetched_at"] = (
            market_fetched_at
        )


        if (
            market_rate is None
            or
            bank_rate is None
        ):

            copied["market_rate"] = None

            copied["markup_percent"] = None

            enriched.append(
                copied
            )

            continue


        try:

            bank_rate = float(
                bank_rate
            )

            market_rate = float(
                market_rate
            )

        except (TypeError, ValueError):

            copied["market_rate"] = None

            copied["markup_percent"] = None

            enriched.append(
                copied
            )

            continue


        markup = (
            (
                bank_rate
                /
                market_rate
            )
            - 1
        ) * 100


        copied["market_rate"] = round(
            market_rate,
            4
        )


        copied["markup_percent"] = round(
            markup,
            4
        )


        enriched.append(
            copied
        )


    return enriched


# ==========================================================
# SAVE LATEST
# ==========================================================

def save_latest(
    records,
    market_result
):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


    payload = {

        "updated_at":
            now_ist().isoformat(),

        "rate_type":
            RATE_TYPE,

        "market_reference": {

            "source":
                market_result.get(
                    "source"
                ),

            "source_url":
                market_result.get(
                    "source_url"
                ),

            "source_timestamp":
                market_result.get(
                    "source_timestamp"
                ),

            "fetched_at":
                market_result.get(
                    "fetched_at"
                ),

            "rates":
                market_result.get(
                    "rates",
                    {}
                ),
        },

        "rates":
            records,
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


# ==========================================================
# HISTORY
# ==========================================================

HISTORY_FIELDS = [
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
    "source_time",
    "fetched_at",
    "status",
    "market_source",
    "market_source_url",
    "market_source_timestamp",
    "market_fetched_at",
]


def load_history_keys():

    keys = set()


    if not HISTORY_FILE.exists():

        return keys


    try:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            reader = csv.DictReader(
                file
            )


            for row in reader:

                key = (
                    row.get("source_date"),
                    row.get("bank"),
                    row.get("currency"),
                )

                keys.add(
                    key
                )


    except Exception as error:

        print(
            "Could not read history.csv:",
            error
        )


    return keys


def append_history(records):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


    existing_keys = (
        load_history_keys()
    )


    file_exists = (
        HISTORY_FILE.exists()
        and
        HISTORY_FILE.stat().st_size > 0
    )


    with open(
        HISTORY_FILE,
        "a",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=HISTORY_FIELDS,
            extrasaction="ignore"
        )


        if not file_exists:

            writer.writeheader()


        for record in records:

            if record.get("status") != "current":

                continue


            source_date = record.get(
                "source_date"
            )


            if not source_date:

                continue


            key = (
                source_date,
                record.get("bank"),
                record.get("currency"),
            )


            if key in existing_keys:

                continue


            writer.writerow({

                field:
                    record.get(
                        field,
                        ""
                    )

                for field in HISTORY_FIELDS

            })


            existing_keys.add(
                key
            )


# ==========================================================
# AGENT RUNNER
# ==========================================================

def run_agent(
    bank_name,
    collector,
    previous_records
):

    print()

    print(
        "================================"
    )


    print(
        f"RUNNING {bank_name} AGENT"
    )


    print(
        "================================"
    )


    try:

        records = collector()


        valid = []


        for record in records:

            if validate_record(
                record
            ):

                valid.append(
                    record
                )


        if not valid:

            raise RuntimeError(
                f"{bank_name} agent returned no valid records."
            )


        print(
            f"{bank_name} AGENT SUCCESS:",
            len(valid),
            "valid rates"
        )


        return valid


    except Exception as error:

        print()

        print(
            f"{bank_name} AGENT FAILED:"
        )


        print(
            str(error)
        )


        stale = preserve_failed_bank(
            bank_name,
            previous_records
        )


        if stale:

            print(
                "Preserving",
                len(stale),
                bank_name,
                "previous rates as stale."
            )


        else:

            print(
                "No previous",
                bank_name,
                "rates available."
            )


        return stale


# ==========================================================
# SORTING
# ==========================================================

def sort_records(records):

    bank_order = {
        "SBI": 1,
        "Canara Bank": 2,
        "Bank of Baroda": 3,
        "HDFC Bank": 4,
        "ICICI Bank": 5,
        "Axis Bank": 6,
    }


    currency_order = {

        currency: index

        for index, currency
        in enumerate(
            CURRENCIES
        )

    }


    return sorted(

        records,

        key=lambda record: (

            currency_order.get(
                record.get("currency"),
                999
            ),

            (
                record.get(
                    "markup_percent"
                )
                if record.get(
                    "markup_percent"
                ) is not None
                else 999
            ),

            bank_order.get(
                record.get("bank"),
                999
            )

        )

    )


# ==========================================================
# MAIN CONTROLLER
# ==========================================================

def main():

    print()

    print(
        "================================"
    )


    print(
        "FX RATE AGENT CONTROLLER"
    )


    print(
        "================================"
    )


    print(
        "Run time:",
        now_ist().isoformat()
    )


    previous_records = (
        load_previous_latest()
    )


    final_records = []


    # ======================================================
    # ACTIVE BANK AGENTS
    # ======================================================

    agents = [

        (
            "SBI",
            sbi.collect
        ),

        (
            "Axis Bank",
            axis.collect
        ),

        (
            "ICICI Bank",
            icici.collect
        ),

        (
            "Canara Bank",
            canara.collect
        ),

        (
            "Bank of Baroda",
            bob.collect
        ),

        (
            "HDFC Bank",
            hdfc.collect
        ),

    ]


    for bank_name, collector in agents:

        bank_records = run_agent(
            bank_name,
            collector,
            previous_records
        )


        final_records.extend(
            bank_records
        )


    # ======================================================
    # CLEAN BANK RESULTS
    # ======================================================

    final_records = deduplicate(
        final_records
    )


    # ======================================================
    # MARKET RATE AGENT
    # ======================================================

    print()

    print(
        "================================"
    )


    print(
        "RUNNING MARKET RATE AGENT"
    )


    print(
        "================================"
    )


    market_result = market.collect()


    # ======================================================
    # ADD MARKET RATE + MARKUP
    # ======================================================

    final_records = apply_market_rates(
        final_records,
        market_result
    )


    # ======================================================
    # SORT
    # ======================================================

    final_records = sort_records(
        final_records
    )


    # ======================================================
    # SAVE
    # ======================================================

    save_latest(
        final_records,
        market_result
    )


    append_history(
        final_records
    )


    # ======================================================
    # SUMMARY
    # ======================================================

    print()

    print(
        "================================"
    )


    print(
        "FINAL RESULTS"
    )


    print(
        "================================"
    )


    for record in final_records:

        print(
            record.get("currency"),
            "|",
            record.get("bank"),
            "| Bank:",
            record.get("bank_rate"),
            "| Market:",
            record.get("market_rate"),
            "| Markup:",
            record.get("markup_percent"),
            "%",
            "| source:",
            record.get("source_date"),
            record.get("source_time"),
            "|",
            record.get("status")
        )


    print()


    print(
        "Total bank rates:",
        len(final_records)
    )


    print(
        "Market reference source:",
        market_result.get(
            "source"
        )
    )


    print(
        "Controller completed successfully."
    )


if __name__ == "__main__":

    main()
