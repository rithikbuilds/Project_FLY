import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pdfplumber
import requests


DATA_DIR = Path("data")

LATEST_FILE = DATA_DIR / "latest.json"
HISTORY_FILE = DATA_DIR / "history.csv"

IST = ZoneInfo("Asia/Kolkata")


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


SBI_PDF_URL = (
    "https://sbi.co.in/documents/16012/1400784/"
    "FOREX_CARD_RATES.pdf"
)

HDFC_PDF_URL = (
    "https://v.hdfcbank.com/content/dam/"
    "hdfc-aem-microsites/common-pdfs/pdf/"
    "forex_rates/rates.pdf"
)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/129 Safari/537.36"
    )
}


def now_ist():

    return datetime.now(IST)


def format_date():

    return now_ist().strftime("%Y-%m-%d")


def format_time():

    return now_ist().strftime("%H:%M:%S")


def download_pdf(url):

    print(f"Downloading: {url}")

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=40
    )

    response.raise_for_status()

    if "pdf" not in response.headers.get(
        "content-type",
        ""
    ).lower():

        print(
            "Warning: response content-type is",
            response.headers.get(
                "content-type"
            )
        )

    return response.content


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
# SBI
# ==========================================================

def parse_sbi():

    print("\nFetching SBI...")

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

            if pair in line:

                cleaned = re.sub(
                    r"\s+",
                    " ",
                    line.strip()
                )

                print(
                    "SBI candidate:",
                    cleaned
                )


                numbers = re.findall(
                    r"\d+\.\d+|\d+",
                    cleaned
                )


                """
                SBI rows normally look like:

                UNITED STATES DOLLAR
                USD/INR
                TT BUY
                TT SELL
                BILL BUY
                BILL SELL
                ...

                Therefore after the pair,
                the first number is normally
                TT BUY and the second number
                is TT SELL.
                """


                pair_index = cleaned.find(
                    pair
                )


                after_pair = cleaned[
                    pair_index
                    + len(pair):
                ]


                values = re.findall(
                    r"\d+\.\d+|\d+",
                    after_pair
                )


                if len(values) >= 2:

                    tt_sell = float(
                        values[1]
                    )


                    if tt_sell > 0:

                        records.append(

                            build_record(

                                bank="SBI",

                                currency=currency,

                                bank_rate=tt_sell,

                                source_url=SBI_PDF_URL

                            )

                        )

                        found = True

                        break


        if not found:

            print(
                f"SBI: could not find {currency}"
            )


    return records


# ==========================================================
# HDFC
# ==========================================================

def parse_hdfc():

    print("\nFetching HDFC...")

    pdf_bytes = download_pdf(
        HDFC_PDF_URL
    )

    text = extract_pdf_text(
        pdf_bytes
    )

    records = []


    lines = text.splitlines()


    for currency in CURRENCIES:

        found = False


        for line in lines:

            cleaned = re.sub(
                r"\s+",
                " ",
                line.strip()
            )


            """
            HDFC rows contain:

            Currency Name
            Currency Code
            Cash Buying
            Cash Selling
            Bills Buying
            Bills Selling
            TT Buying
            TT Selling (O/w Rem)
            ...

            Currency code is followed
            by several rate numbers.

            TT Selling is normally
            the sixth numeric rate
            after the currency code.
            """


            if re.search(
                rf"\b{currency}\b",
                cleaned
            ):

                code_index = cleaned.find(
                    currency
                )


                after_code = cleaned[
                    code_index
                    + len(currency):
                ]


                values = re.findall(
                    r"-|\d+\.\d+|\d+",
                    after_code
                )


                numeric_values = []


                for value in values:

                    if value == "-":
                        continue

                    try:

                        numeric_values.append(
                            float(value)
                        )

                    except ValueError:

                        pass


                print(
                    "HDFC candidate:",
                    cleaned
                )


                """
                HDFC order:
                1 Cash Buy
                2 Cash Sell
                3 Bills Buy
                4 Bills Sell
                5 TT Buy
                6 TT Sell
                """


                if len(
                    numeric_values
                ) >= 6:

                    tt_sell = (
                        numeric_values[5]
                    )


                    if tt_sell > 0:

                        records.append(

                            build_record(

                                bank="HDFC",

                                currency=currency,

                                bank_rate=tt_sell,

                                source_url=HDFC_PDF_URL

                            )

                        )

                        found = True

                        break


        if not found:

            print(
                f"HDFC: could not find {currency}"
            )


    return records


# ==========================================================
# VALIDATION
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
# SAVE HISTORY
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


    existing_keys = set()


    if HISTORY_FILE.exists():

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            reader = csv.DictReader(
                file
            )


            for row in reader:

                existing_keys.add(

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


            """
            Store one closing observation
            per bank/currency/day for now.

            Later we can change this to
            intraday snapshots if wanted.
            """


            if key in existing_keys:

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


# ==========================================================
# MAIN
# ==========================================================

def main():

    print(
        "Starting outward FX collector"
    )

    print(
        "IST:",
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


    for name, collector in collectors:

        try:

            bank_records = (
                collector()
            )


            records.extend(
                bank_records
            )


            print(
                f"{name}: "
                f"{len(bank_records)} "
                f"rates collected"
            )


        except Exception as error:

            print(
                f"{name} FAILED:",
                str(error)
            )


    records = [

        record

        for record
        in records

        if validate_record(
            record
        )

    ]


    save_latest(
        records
    )


    if records:

        append_history(
            records
        )


    print(
        "\nFinished."
    )

    print(
        "Total valid rates:",
        len(records)
    )


if __name__ == "__main__":

    main()
