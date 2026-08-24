import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pdfplumber
import requests


# ==========================================================
# PATHS
# ==========================================================

DATA_DIR = Path("data")

LATEST_FILE = DATA_DIR / "latest.json"

HISTORY_FILE = DATA_DIR / "history.csv"


# ==========================================================
# TIMEZONE
# ==========================================================

IST = ZoneInfo("Asia/Kolkata")


# ==========================================================
# CURRENCIES
# ==========================================================

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
# OFFICIAL BANK SOURCES
# ==========================================================

SBI_PDF_URL = (
    "https://sbi.co.in/documents/16012/1400784/"
    "FOREX_CARD_RATES.pdf"
)

HDFC_PDF_URL = (
    "https://v.hdfcbank.com/content/dam/"
    "hdfc-aem-microsites/common-pdfs/pdf/"
    "forex_rates/rates.pdf"
)


# ==========================================================
# REQUEST HEADERS
# ==========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/129 Safari/537.36"
    )
}


# ==========================================================
# TIME
# ==========================================================

def now_ist():

    return datetime.now(IST)


# ==========================================================
# DOWNLOAD PDF
# ==========================================================

def download_pdf(url):

    print("\nDownloading:")
    print(url)

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=45
    )

    response.raise_for_status()

    content_type = (
        response.headers
        .get("content-type", "")
        .lower()
    )

    print(
        "Content-Type:",
        content_type
    )

    return response.content


# ==========================================================
# EXTRACT PDF TEXT
# ==========================================================

def extract_pdf_text(pdf_bytes):

    text = ""

    with pdfplumber.open(
        io.BytesIO(pdf_bytes)
    ) as pdf:

        for page in pdf.pages:

            page_text = (
                page.extract_text()
                or ""
            )

            text += (
                page_text
                + "\n"
            )

    return text


# ==========================================================
# BUILD STANDARD RECORD
# ==========================================================

def build_record(
    bank,
    currency,
    bank_rate,
    source_url,
    source_date=None
):

    current_time = now_ist()

    return {

        "date":
            current_time.strftime(
                "%Y-%m-%d"
            ),

        "time":
            current_time.strftime(
                "%H:%M:%S"
            ),

        "bank":
            bank,

        "currency":
            currency,

        "rate_type":
            "TT Selling / Outward Remittance",

        "bank_rate":
            float(bank_rate),

        "market_rate":
            None,

        "markup_percent":
            None,

        "source_url":
            source_url,

        "source_date":
            source_date
            or current_time.strftime(
                "%Y-%m-%d"
            ),

        "fetched_at":
            current_time.isoformat(),

        "status":
            "current"

    }


# ==========================================================
# RATE VALIDATION
# ==========================================================

def validate_record(record):

    currency = record[
        "currency"
    ]

    rate = record[
        "bank_rate"
    ]


    ranges = {

        "USD":
            (50, 150),

        "CAD":
            (30, 120),

        "AUD":
            (30, 120),

        "GBP":
            (70, 200),

        "EUR":
            (60, 180),

        "SGD":
            (30, 120),

        "AED":
            (10, 50),

        "NZD":
            (25, 100),

    }


    if currency not in ranges:

        print(
            "Unknown currency:",
            currency
        )

        return False


    low, high = ranges[
        currency
    ]


    if not (
        low <= rate <= high
    ):

        print(
            "Rejected suspicious rate:",
            record
        )

        return False


    return True


# ==========================================================
# SBI PARSER
# ==========================================================

def parse_sbi():

    print(
        "\n===================="
    )

    print(
        "FETCHING SBI"
    )

    print(
        "===================="
    )


    pdf_bytes = download_pdf(
        SBI_PDF_URL
    )


    text = extract_pdf_text(
        pdf_bytes
    )


    records = []


    aliases = {

        "USD":
            "USD/INR",

        "CAD":
            "CAD/INR",

        "AUD":
            "AUD/INR",

        "GBP":
            "GBP/INR",

        "EUR":
            "EUR/INR",

        "SGD":
            "SGD/INR",

        "AED":
            "AED/INR",

        "NZD":
            "NZD/INR",

    }


    lines = text.splitlines()


    for currency, pair in aliases.items():

        found = False


        for line in lines:

            if pair not in line:

                continue


            cleaned = re.sub(
                r"\s+",
                " ",
                line.strip()
            )


            print(
                "SBI candidate:",
                cleaned
            )


            pair_index = (
                cleaned.find(
                    pair
                )
            )


            after_pair = cleaned[
                pair_index
                + len(pair):
            ]


            values = re.findall(
                r"\d+\.\d+|\d+",
                after_pair
            )


            # SBI layout usually gives
            # TT BUY first
            # TT SELL second

            if len(values) >= 2:

                tt_sell = float(
                    values[1]
                )


                record = build_record(

                    bank="SBI",

                    currency=currency,

                    bank_rate=tt_sell,

                    source_url=SBI_PDF_URL

                )


                if validate_record(
                    record
                ):

                    records.append(
                        record
                    )

                    print(
                        f"SBI {currency}:",
                        tt_sell
                    )

                    found = True

                    break


        if not found:

            print(
                f"SBI {currency}: NOT FOUND"
            )


    if not records:

        raise RuntimeError(
            "SBI parser returned no valid rates."
        )


    return records


# ==========================================================
# HDFC HEADER MATCHER
# ==========================================================

def looks_like_hdfc_tt_sell_header(
    text
):

    text = (
        text
        .lower()
        .replace("\n", " ")
    )


    text = re.sub(
        r"\s+",
        " ",
        text
    )


    has_sell = (
        "selling" in text
        or "sell" in text
    )


    has_outward = (

        "o/w rem" in text

        or "o/w" in text

        or "outward" in text

        or "remittance" in text

        or "rem" in text

    )


    return (
        has_sell
        and has_outward
    )


# ==========================================================
# HDFC PARSER
# ==========================================================

def parse_hdfc():

    print(
        "\n===================="
    )

    print(
        "FETCHING HDFC"
    )

    print(
        "===================="
    )


    pdf_bytes = download_pdf(
        HDFC_PDF_URL
    )


    records = []


    with pdfplumber.open(
        io.BytesIO(
            pdf_bytes
        )
    ) as pdf:


        for page_number, page in enumerate(
            pdf.pages,
            start=1
        ):


            tables = (
                page.extract_tables()
                or []
            )


            print(
                f"HDFC page {page_number}: "
                f"{len(tables)} tables found"
            )


            for table_number, table in enumerate(
                tables,
                start=1
            ):


                if not table:

                    continue


                print(
                    f"Checking table "
                    f"{table_number}"
                )


                # --------------------------------
                # FIND HEADER DYNAMICALLY
                # --------------------------------

                header_index = None

                currency_col = None

                tt_sell_col = None


                for row_index, row in enumerate(
                    table
                ):


                    if not row:

                        continue


                    cleaned_row = [

                        re.sub(
                            r"\s+",
                            " ",
                            str(
                                cell
                                or ""
                            )
                        ).strip()

                        for cell
                        in row

                    ]


                    print(
                        "HDFC header candidate:",
                        cleaned_row
                    )


                    for col_index, cell in enumerate(
                        cleaned_row
                    ):


                        lower = (
                            cell.lower()
                        )


                        # ------------------------
                        # FIND CURRENCY COLUMN
                        # ------------------------

                        if (

                            "currency" in lower

                            or lower in [
                                "ccy",
                                "curr",
                                "currency code"
                            ]

                        ):


                            if currency_col is None:

                                currency_col = (
                                    col_index
                                )


                        # ------------------------
                        # FIND TT SELLING COLUMN
                        # ------------------------

                        if looks_like_hdfc_tt_sell_header(
                            cell
                        ):


                            tt_sell_col = (
                                col_index
                            )


                    if (
                        currency_col is not None
                        and
                        tt_sell_col is not None
                    ):


                        header_index = (
                            row_index
                        )


                        print(
                            "HDFC HEADER FOUND"
                        )


                        print(
                            "Header row:",
                            cleaned_row
                        )


                        print(
                            "Currency column:",
                            currency_col
                        )


                        print(
                            "TT Sell column:",
                            tt_sell_col
                        )


                        break


                # --------------------------------
                # DO NOT GUESS
                # --------------------------------

                if header_index is None:

                    print(
                        "No usable header "
                        "in this table."
                    )

                    continue


                # --------------------------------
                # READ DATA ROWS
                # --------------------------------

                for row in table[
                    header_index + 1:
                ]:


                    if not row:

                        continue


                    cleaned_row = [

                        re.sub(
                            r"\s+",
                            " ",
                            str(
                                cell
                                or ""
                            )
                        ).strip()

                        for cell
                        in row

                    ]


                    if (

                        currency_col
                        >= len(cleaned_row)

                        or

                        tt_sell_col
                        >= len(cleaned_row)

                    ):


                        continue


                    currency_cell = (

                        cleaned_row[
                            currency_col
                        ]
                        .upper()
                    )


                    # --------------------------------
                    # DETECT CURRENCY CODE
                    # --------------------------------

                    currency = None


                    for candidate in CURRENCIES:

                        if re.search(

                            rf"\b{candidate}\b",

                            currency_cell

                        ):


                            currency = (
                                candidate
                            )

                            break


                    if not currency:

                        continue


                    # --------------------------------
                    # GET OUTWARD TT SELL RATE
                    # --------------------------------

                    rate_text = (

                        cleaned_row[
                            tt_sell_col
                        ]
                    )


                    rate_match = re.search(

                        r"\d+(?:\.\d+)?",

                        rate_text

                    )


                    if not rate_match:

                        print(
                            f"HDFC {currency}: "
                            "rate missing"
                        )

                        continue


                    tt_sell = float(

                        rate_match.group()

                    )


                    record = build_record(

                        bank="HDFC",

                        currency=currency,

                        bank_rate=tt_sell,

                        source_url=HDFC_PDF_URL

                    )


                    if validate_record(
                        record
                    ):


                        print(
                            f"HDFC {currency}:",
                            tt_sell
                        )


                        records.append(
                            record
                        )


    # ======================================================
    # REMOVE DUPLICATES
    # ======================================================

    unique = {}


    for record in records:

        unique[
            record["currency"]
        ] = record


    records = list(
        unique.values()
    )


    # ======================================================
    # SAFETY CHECK
    # ======================================================

    if not records:

        raise RuntimeError(

            "HDFC TT Selling / "
            "Outward Remittance "
            "column could not be "
            "detected safely. "
            "No HDFC rates saved."

        )


    return records


# ==========================================================
# SAVE LATEST
# ==========================================================

def save_latest(records):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


    payload = {

        "updated_at":
            now_ist().isoformat(),

        "rate_type":
            "TT Selling / Outward Remittance",

        "rates":
            records

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
# LOAD HISTORY KEYS
# ==========================================================

def load_history_keys():

    keys = set()


    if not HISTORY_FILE.exists():

        return keys


    with open(
        HISTORY_FILE,
        "r",
        encoding="utf-8"
    ) as file:


        reader = csv.DictReader(
            file
        )


        for row in reader:


            keys.add(

                (

                    row.get(
                        "date"
                    ),

                    row.get(
                        "bank"
                    ),

                    row.get(
                        "currency"
                    ),

                )

            )


    return keys


# ==========================================================
# APPEND HISTORY
# ==========================================================

def append_history(records):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


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

        "status",

    ]


    existing_keys = (
        load_history_keys()
    )


    file_exists = (
        HISTORY_FILE.exists()
    )


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


            key = (

                record[
                    "date"
                ],

                record[
                    "bank"
                ],

                record[
                    "currency"
                ],

            )


            if key in existing_keys:

                print(
                    "History already exists:",
                    key
                )

                continue


            writer.writerow({

                field:
                    record.get(
                        field,
                        ""
                    )

                for field
                in fields

            })


            existing_keys.add(
                key
            )


            print(
                "History saved:",
                key
            )


# ==========================================================
# MAIN
# ==========================================================

def main():

    print(
        "\n================================"
    )

    print(
        "OUTWARD FX RATE COLLECTOR"
    )

    print(
        "================================"
    )


    print(
        "Run time:",
        now_ist().isoformat()
    )


    records = []


    collectors = [

        (
            "SBI",
            parse_sbi
        ),

        (
            "HDFC",
            parse_hdfc
        ),

    ]


    # ======================================================
    # RUN EACH BANK SEPARATELY
    # ======================================================

    for bank_name, collector in collectors:


        try:


            bank_records = (
                collector()
            )


            records.extend(
                bank_records
            )


            print(
                f"\n{bank_name}: "
                f"{len(bank_records)} "
                f"valid rates collected"
            )


        except Exception as error:


            print(
                f"\n{bank_name} FAILED"
            )


            print(
                str(error)
            )


    # ======================================================
    # FINAL VALIDATION
    # ======================================================

    valid_records = []


    for record in records:


        if validate_record(
            record
        ):


            valid_records.append(
                record
            )


    # ======================================================
    # SAVE
    # ======================================================

    save_latest(
        valid_records
    )


    if valid_records:

        append_history(
            valid_records
        )


    # ======================================================
    # SUMMARY
    # ======================================================

    print(
        "\n================================"
    )

    print(
        "COLLECTOR FINISHED"
    )

    print(
        "================================"
    )


    print(
        "Total valid rates:",
        len(valid_records)
    )


    for record in valid_records:


        print(

            record["bank"],

            record["currency"],

            record["bank_rate"]

        )


if __name__ == "__main__":

    main()
