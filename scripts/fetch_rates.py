import csv
import io
import json
import re
import time

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pdfplumber
import requests


# ==========================================================
# CONFIGURATION
# ==========================================================

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


# ==========================================================
# OFFICIAL BANK SOURCES
# ==========================================================

SBI_PDF_URLS = [

    "https://sbi.co.in/documents/16012/1400784/"
    "FOREX_CARD_RATES.pdf",

]


HDFC_PDF_URLS = [

    # Try this static HDFC endpoint first
    "https://v.hdfcbank.com/content/dam/"
    "hdfc-aem-microsites/common-pdfs/pdf/"
    "forex_rates/rates.pdf",

    # Official HDFC content repository fallback
    "https://www.hdfcbank.com/content/bbp/repositories/"
    "723fb80a-2dde-42a3-9793-7ae1be57c87f/"
    "?path=%2FPersonal%2FHome%2Fcontent%2Frates.pdf",

]


# ==========================================================
# HTTP SETTINGS
# ==========================================================

HEADERS = {

    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/129.0 Safari/537.36"
    ),

    "Accept": (
        "application/pdf,"
        "text/html,"
        "application/xhtml+xml,"
        "*/*"
    ),

    "Accept-Language":
        "en-US,en;q=0.9",

}


# ==========================================================
# BASIC HELPERS
# ==========================================================

def now_ist():

    return datetime.now(IST)


def normalize_text(value):

    return re.sub(
        r"\s+",
        " ",
        str(value or "")
    ).strip()


def parse_number(value):

    if value is None:
        return None

    match = re.search(
        r"\d+(?:\.\d+)?",
        str(value)
    )

    if not match:
        return None

    try:

        return float(
            match.group()
        )

    except ValueError:

        return None


# ==========================================================
# PDF DATE
# ==========================================================

def parse_source_date(text):

    patterns = [

        r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b",

    ]


    for pattern in patterns:

        match = re.search(
            pattern,
            text
        )

        if not match:
            continue


        day = int(
            match.group(1)
        )

        month = int(
            match.group(2)
        )

        year = int(
            match.group(3)
        )


        try:

            parsed = datetime(
                year,
                month,
                day
            )


            return parsed.strftime(
                "%Y-%m-%d"
            )


        except ValueError:

            continue


    # 24-Aug-2026

    match = re.search(

        r"\b(\d{1,2})[-\s]"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"[-\s](20\d{2})\b",

        text,

        re.IGNORECASE

    )


    if match:

        raw = (
            f"{match.group(1)}-"
            f"{match.group(2)}-"
            f"{match.group(3)}"
        )


        try:

            parsed = datetime.strptime(
                raw,
                "%d-%b-%Y"
            )


            return parsed.strftime(
                "%Y-%m-%d"
            )


        except ValueError:

            pass


    return None


# ==========================================================
# PDF TIME
# ==========================================================

def parse_source_time(text):

    patterns = [

        r"\bTIME\s*[:\-]?\s*"
        r"(\d{1,2}:\d{2}(?::\d{2})?\s*[AP]M)",

        r"\bTime\s*[:\-]?\s*"
        r"(\d{1,2}:\d{2}(?::\d{2})?\s*[AP]M)",

    ]


    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )


        if match:

            return normalize_text(
                match.group(1)
            )


    return None


# ==========================================================
# CURRENT / STALE
# ==========================================================

def determine_status(source_date):

    if not source_date:

        return "date_unverified"


    today = now_ist().strftime(
        "%Y-%m-%d"
    )


    if source_date == today:

        return "current"


    return "stale"


# ==========================================================
# DOWNLOAD WITH RETRIES + FALLBACK URLS
# ==========================================================

def download_pdf_from_sources(
    bank_name,
    urls
):

    errors = []


    for url in urls:


        for attempt in range(
            1,
            4
        ):


            try:

                print(
                    f"\n{bank_name}: "
                    f"trying source"
                )

                print(
                    url
                )

                print(
                    f"Attempt {attempt}/3"
                )


                response = requests.get(

                    url,

                    headers=HEADERS,

                    timeout=30,

                    allow_redirects=True

                )


                response.raise_for_status()


                content = (
                    response.content
                )


                print(
                    "HTTP:",
                    response.status_code
                )


                print(
                    "Content-Type:",
                    response.headers.get(
                        "content-type",
                        ""
                    )
                )


                # PDF signature validation

                if not content.startswith(
                    b"%PDF"
                ):


                    raise RuntimeError(
                        "Source returned something "
                        "other than a PDF."
                    )


                print(
                    f"{bank_name}: "
                    "PDF downloaded successfully."
                )


                return (
                    content,
                    url
                )


            except Exception as error:


                message = (
                    f"{url} | "
                    f"attempt {attempt} | "
                    f"{error}"
                )


                errors.append(
                    message
                )


                print(
                    f"{bank_name}: "
                    f"download attempt failed:"
                )


                print(
                    str(error)
                )


                if attempt < 3:

                    time.sleep(
                        3
                    )


    raise RuntimeError(

        f"{bank_name}: "
        "all PDF sources failed.\n"

        + "\n".join(
            errors
        )

    )


# ==========================================================
# PDF TEXT
# ==========================================================

def extract_pdf_text(
    pdf_bytes
):

    parts = []


    with pdfplumber.open(
        io.BytesIO(
            pdf_bytes
        )
    ) as pdf:


        for page in pdf.pages:


            parts.append(

                page.extract_text()
                or ""

            )


    return "\n".join(
        parts
    )


# ==========================================================
# RECORD
# ==========================================================

def build_record(
    bank,
    currency,
    bank_rate,
    source_url,
    source_date,
    source_time=None
):

    current_time = (
        now_ist()
    )


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
            float(
                bank_rate
            ),

        "market_rate":
            None,

        "markup_percent":
            None,

        "source_url":
            source_url,

        "source_date":
            source_date,

        "source_time":
            source_time,

        "fetched_at":
            current_time.isoformat(),

        "status":
            determine_status(
                source_date
            ),

    }


# ==========================================================
# RATE VALIDATION
# ==========================================================

def validate_record(
    record
):

    currency = (
        record["currency"]
    )

    rate = (
        record["bank_rate"]
    )


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


    if currency not in ranges:

        return False


    low, high = (
        ranges[currency]
    )


    if not (
        low <= rate <= high
    ):


        print(
            "REJECTED RATE:",
            record["bank"],
            currency,
            rate
        )


        return False


    return True


# ==========================================================
# SBI
# ==========================================================

def parse_sbi():

    print(
        "\n=============================="
    )

    print(
        "SBI"
    )

    print(
        "=============================="
    )


    pdf_bytes, used_url = (
        download_pdf_from_sources(

            "SBI",

            SBI_PDF_URLS

        )
    )


    text = extract_pdf_text(
        pdf_bytes
    )


    source_date = (
        parse_source_date(
            text
        )
    )


    source_time = (
        parse_source_time(
            text
        )
    )


    print(
        "SBI source date:",
        source_date
    )


    print(
        "SBI source time:",
        source_time
    )


    if not source_date:

        raise RuntimeError(
            "SBI source date "
            "could not be verified."
        )


    aliases = {

        "USD": "USD/INR",

        "CAD": "CAD/INR",

        "AUD": "AUD/INR",

        "GBP": "GBP/INR",

        "EUR": "EUR/INR",

        "SGD": "SGD/INR",

        "AED": "AED/INR",

        "NZD": "NZD/INR",

    }


    records = []


    for currency, pair in (
        aliases.items()
    ):


        found = False


        for line in (
            text.splitlines()
        ):


            if pair not in line:

                continue


            cleaned = normalize_text(
                line
            )


            position = cleaned.find(
                pair
            )


            after_pair = cleaned[

                position
                + len(pair):

            ]


            numbers = re.findall(

                r"\d+(?:\.\d+)?",

                after_pair

            )


            if len(numbers) < 2:

                continue


            # SBI:
            # 1st rate = TT BUY
            # 2nd rate = TT SELL

            tt_sell = float(
                numbers[1]
            )


            record = build_record(

                bank="SBI",

                currency=currency,

                bank_rate=tt_sell,

                source_url=used_url,

                source_date=source_date,

                source_time=source_time

            )


            if validate_record(
                record
            ):


                records.append(
                    record
                )


                print(
                    currency,
                    tt_sell,
                    record["status"]
                )


                found = True


                break


        if not found:


            print(
                "SBI missing:",
                currency
            )


    if not records:

        raise RuntimeError(
            "SBI returned "
            "no valid rates."
        )


    return records


# ==========================================================
# HDFC HEADER HELPERS
# ==========================================================

def is_currency_header(
    text
):

    lower = (
        normalize_text(
            text
        )
        .lower()
    )


    return (

        lower == "currency"

        or

        lower == "currency code"

        or

        "currency (in rs" in lower

        or

        lower == "ccy"

    )


def is_outward_sell_header(
    text
):

    lower = (
        normalize_text(
            text
        )
        .lower()
    )


    has_sell = (

        "selling" in lower

        or

        "sell" in lower

    )


    has_outward = (

        "o/w" in lower

        or

        "o / w" in lower

        or

        "outward" in lower

    )


    has_remittance = (

        "rem" in lower

        or

        "remittance" in lower

    )


    return (

        has_sell

        and

        has_outward

        and

        has_remittance

    )


# ==========================================================
# HDFC TABLE PARSER
# ==========================================================

def parse_hdfc_tables(
    pdf_bytes,
    used_url,
    source_date,
    source_time
):

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
                "HDFC page",
                page_number,
                "tables:",
                len(tables)
            )


            for table in tables:


                if not table:

                    continue


                header_index = None

                currency_column = None

                outward_column = None


                for row_index, row in enumerate(
                    table
                ):


                    if not row:

                        continue


                    cells = [

                        normalize_text(
                            cell
                        )

                        for cell in row

                    ]


                    for column_index, cell in enumerate(
                        cells
                    ):


                        if is_currency_header(
                            cell
                        ):


                            currency_column = (
                                column_index
                            )


                        if is_outward_sell_header(
                            cell
                        ):


                            outward_column = (
                                column_index
                            )


                    if (

                        currency_column
                        is not None

                        and

                        outward_column
                        is not None

                    ):


                        header_index = (
                            row_index
                        )


                        print(
                            "HDFC header found."
                        )


                        print(
                            "Currency column:",
                            currency_column
                        )


                        print(
                            "Outward TT Sell column:",
                            outward_column
                        )


                        break


                if header_index is None:

                    continue


                for row in table[
                    header_index + 1:
                ]:


                    if not row:

                        continue


                    cells = [

                        normalize_text(
                            cell
                        )

                        for cell in row

                    ]


                    if (

                        currency_column
                        >= len(cells)

                        or

                        outward_column
                        >= len(cells)

                    ):

                        continue


                    currency_text = (
                        cells[
                            currency_column
                        ].upper()
                    )


                    currency = None


                    for candidate in CURRENCIES:


                        if re.search(

                            rf"\b{candidate}\b",

                            currency_text

                        ):


                            currency = (
                                candidate
                            )


                            break


                    if not currency:

                        continue


                    rate = parse_number(

                        cells[
                            outward_column
                        ]

                    )


                    if rate is None:

                        continue


                    record = build_record(

                        bank="HDFC",

                        currency=currency,

                        bank_rate=rate,

                        source_url=used_url,

                        source_date=source_date,

                        source_time=source_time

                    )


                    if validate_record(
                        record
                    ):


                        records.append(
                            record
                        )


                        print(
                            "HDFC",
                            currency,
                            rate
                        )


    return records


# ==========================================================
# HDFC TEXT FALLBACK
# ==========================================================

def parse_hdfc_text_fallback(
    text,
    used_url,
    source_date,
    source_time
):

    print(
        "Trying HDFC "
        "text fallback..."
    )


    normalized = (
        normalize_text(
            text
        )
    )


    lower = (
        normalized.lower()
    )


    outward_markers = [

        "t.t. selling (o/w rem)",

        "t.t.selling(o/w rem)",

        "tt selling (o/w rem)",

        "t.t. selling (o / w rem)",

        "t.t.selling(o / w rem)",

    ]


    marker_found = any(

        marker in lower

        for marker in outward_markers

    )


    if not marker_found:


        raise RuntimeError(

            "HDFC PDF downloaded, "
            "but the outward TT Selling "
            "header was not detected."

        )


    records = []


    currency_names = {

        "USD": [
            "United States Dollar",
            "US Dollar"
        ],

        "CAD": [
            "Canadian Dollar"
        ],

        "AUD": [
            "Australian Dollar"
        ],

        "GBP": [
            "British Pound",
            "Great Britain Pound"
        ],

        "EUR": [
            "Euro"
        ],

        "SGD": [
            "Singapore Dollar"
        ],

        "AED": [
            "UAE Dirham",
            "U.A.E. Dirham"
        ],

        "NZD": [
            "New Zealand Dollar"
        ],

    }


    for currency in CURRENCIES:


        names = currency_names[
            currency
        ]


        name_pattern = (

            "|".join(

                re.escape(name)

                for name in names

            )

        )


        pattern = re.compile(

            rf"(?:{name_pattern})"
            rf"\s+{currency}\s+"
            r"((?:-|\d+(?:\.\d+)?)"
            r"(?:\s+(?:-|\d+(?:\.\d+)?)){5,})",

            re.IGNORECASE

        )


        match = pattern.search(
            normalized
        )


        if not match:


            print(
                "HDFC fallback missing:",
                currency
            )


            continue


        values = re.findall(

            r"-|\d+(?:\.\d+)?",

            match.group(1)

        )


        if len(values) < 6:

            continue


        tt_sell_text = (
            values[5]
        )


        if tt_sell_text == "-":

            continue


        rate = float(
            tt_sell_text
        )


        record = build_record(

            bank="HDFC",

            currency=currency,

            bank_rate=rate,

            source_url=used_url,

            source_date=source_date,

            source_time=source_time

        )


        if validate_record(
            record
        ):


            records.append(
                record
            )


            print(
                "HDFC fallback",
                currency,
                rate
            )


    return records


# ==========================================================
# HDFC
# ==========================================================

def parse_hdfc():

    print(
        "\n=============================="
    )

    print(
        "HDFC"
    )

    print(
        "=============================="
    )


    pdf_bytes, used_url = (
        download_pdf_from_sources(

            "HDFC",

            HDFC_PDF_URLS

        )
    )


    text = extract_pdf_text(
        pdf_bytes
    )


    source_date = (
        parse_source_date(
            text
        )
    )


    source_time = (
        parse_source_time(
            text
        )
    )


    print(
        "HDFC source URL:",
        used_url
    )


    print(
        "HDFC source date:",
        source_date
    )


    print(
        "HDFC source time:",
        source_time
    )


    if not source_date:


        raise RuntimeError(

            "HDFC PDF downloaded "
            "but source date "
            "could not be verified."

        )


    # METHOD 1:
    # Read actual table headers.

    records = parse_hdfc_tables(

        pdf_bytes,

        used_url,

        source_date,

        source_time

    )


    # METHOD 2:
    # Text fallback.

    if not records:


        records = (
            parse_hdfc_text_fallback(

                text,

                used_url,

                source_date,

                source_time

            )
        )


    # Deduplicate currency

    unique = {}


    for record in records:


        unique[
            record["currency"]
        ] = record


    records = list(
        unique.values()
    )


    if not records:


        raise RuntimeError(

            "HDFC outward TT Selling "
            "rates could not be "
            "extracted safely."

        )


    return records


# ==========================================================
# PREVIOUS LATEST DATA
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


            payload = (
                json.load(
                    file
                )
            )


        return payload.get(
            "rates",
            []
        )


    except Exception:

        return []


# ==========================================================
# PRESERVE FAILED BANK AS STALE
# ==========================================================

def preserve_failed_bank(
    bank_name,
    previous_records
):

    preserved = []


    for record in previous_records:


        if record.get(
            "bank"
        ) != bank_name:

            continue


        copied = dict(
            record
        )


        copied[
            "status"
        ] = "stale"


        preserved.append(
            copied
        )


    return preserved


# ==========================================================
# SAVE LATEST
# ==========================================================

def save_latest(
    records
):

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
                        "source_date"
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


def append_history(
    records
):

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

        "source_time",

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

            fieldnames=fields,

            extrasaction="ignore"

        )


        if not file_exists:

            writer.writeheader()


        for record in records:


            if record.get(
                "status"
            ) == "stale":

                continue


            source_date = (
                record.get(
                    "source_date"
                )
            )


            if not source_date:

                continue


            key = (

                source_date,

                record.get(
                    "bank"
                ),

                record.get(
                    "currency"
                ),

            )


            if key in existing_keys:

                continue


            writer.writerow({

                field:
                    record.get(
                        field,
                        ""
                    )

                for field in fields

            })


            existing_keys.add(
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


    previous_records = (
        load_previous_latest()
    )


    final_records = []


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


    for bank_name, collector in (
        collectors
    ):


        try:


            bank_records = (
                collector()
            )


            final_records.extend(
                bank_records
            )


            print(
                bank_name,
                "SUCCESS:",
                len(bank_records),
                "rates"
            )


        except Exception as error:


            print(
                bank_name,
                "FAILED:"
            )


            print(
                str(error)
            )


            stale = (
                preserve_failed_bank(

                    bank_name,

                    previous_records

                )
            )


            if stale:


                print(
                    "Keeping",
                    len(stale),
                    bank_name,
                    "old records as stale."
                )


                final_records.extend(
                    stale
                )


    # ======================================================
    # VALIDATE
    # ======================================================

    validated = []


    for record in final_records:


        if validate_record(
            record
        ):


            validated.append(
                record
            )


    # ======================================================
    # SORT
    # ======================================================

    bank_order = {

        "SBI": 1,

        "HDFC": 2,

    }


    currency_order = {

        value: index

        for index, value
        in enumerate(
            CURRENCIES
        )

    }


    validated.sort(

        key=lambda item: (

            bank_order.get(
                item["bank"],
                99
            ),

            currency_order.get(
                item["currency"],
                99
            )

        )

    )


    # ======================================================
    # SAVE
    # ======================================================

    save_latest(
        validated
    )


    append_history(
        validated
    )


    # ======================================================
    # RESULT SUMMARY
    # ======================================================

    print(
        "\n================================"
    )

    print(
        "FINAL RESULTS"
    )

    print(
        "================================"
    )


    for record in validated:


        print(

            record["bank"],

            record["currency"],

            record["bank_rate"],

            "| source:",

            record.get(
                "source_date"
            ),

            record.get(
                "source_time"
            ),

            "|",

            record.get(
                "status"
            )

        )


    print(
        "\nTotal:",
        len(validated)
    )


if __name__ == "__main__":

    main()
