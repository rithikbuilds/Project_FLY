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
# CONFIG
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
# OFFICIAL SOURCES
# ==========================================================

SBI_PDF_URL = (
    "https://sbi.co.in/documents/"
    "16012/1400784/FOREX_CARD_RATES.pdf"
)


# IMPORTANT:
# This is the current HDFC repository source.
# The old v.hdfcbank.com 2022 PDF has been removed.

HDFC_PDF_URL = (
    "https://www.hdfcbank.com/content/bbp/repositories/"
    "723fb80a-2dde-42a3-9793-7ae1be57c87f/"
    "?path=%2FPersonal%2FHome%2Fcontent%2Frates.pdf"
)


# ==========================================================
# HTTP
# ==========================================================

HEADERS = {

    "User-Agent": (
        "Mozilla/5.0 "
        "(Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/149.0 Safari/537.36"
    ),

    "Accept": (
        "application/pdf,"
        "text/html,"
        "application/xhtml+xml,"
        "*/*"
    ),

    "Accept-Language":
        "en-US,en;q=0.9",

    "Connection":
        "keep-alive",

}


# ==========================================================
# TIME
# ==========================================================

def now_ist():

    return datetime.now(
        IST
    )


# ==========================================================
# TEXT HELPERS
# ==========================================================

def clean_text(value):

    return re.sub(
        r"\s+",
        " ",
        str(value or "")
    ).strip()


def get_number(value):

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
# SOURCE DATE
# ==========================================================

def extract_source_date(text):

    """
    Supports formats such as:

    24-08-2026
    24/08/2026
    24-8-2026
    24 Aug 2026
    24-Aug-2026
    """

    # DD-MM-YYYY / DD/MM/YYYY

    numeric_patterns = [

        r"\bDATE\s*[:\-]?\s*"
        r"(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b",

        r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b",

    ]


    for pattern in numeric_patterns:


        match = re.search(

            pattern,

            text,

            re.IGNORECASE

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

            value = datetime(

                year,

                month,

                day

            )


            return value.strftime(
                "%Y-%m-%d"
            )


        except ValueError:

            continue


    # DD-MMM-YYYY

    month_match = re.search(

        r"\b(?:DATE\s*[:\-]?\s*)?"
        r"(\d{1,2})[-\s]"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"[-\s](20\d{2})\b",

        text,

        re.IGNORECASE

    )


    if month_match:


        raw = (

            f"{month_match.group(1)}-"

            f"{month_match.group(2)}-"

            f"{month_match.group(3)}"

        )


        try:

            value = datetime.strptime(

                raw,

                "%d-%b-%Y"

            )


            return value.strftime(
                "%Y-%m-%d"
            )


        except ValueError:

            pass


    return None


# ==========================================================
# SOURCE TIME
# ==========================================================

def extract_source_time(text):

    patterns = [

        r"\bTIME\s*[:\-]?\s*"
        r"(\d{1,2}:\d{2}(?::\d{2})?\s*[AP]M)",

        r"\b(\d{1,2}:\d{2}:\d{2}\s*[AP]M)\b",

    ]


    for pattern in patterns:


        match = re.search(

            pattern,

            text,

            re.IGNORECASE

        )


        if match:


            return clean_text(
                match.group(1)
            )


    return None


# ==========================================================
# STATUS
# ==========================================================

def get_status(source_date):

    if not source_date:

        return "date_unverified"


    today = now_ist().strftime(
        "%Y-%m-%d"
    )


    if source_date == today:

        return "current"


    return "stale"


# ==========================================================
# DOWNLOAD PDF
# ==========================================================

def download_pdf(
    bank,
    url,
    attempts=3,
    read_timeout=120
):

    errors = []


    session = requests.Session()

    session.headers.update(
        HEADERS
    )


    for attempt in range(
        1,
        attempts + 1
    ):


        try:


            print(
                f"\n{bank}: downloading"
            )

            print(
                url
            )

            print(
                f"Attempt {attempt}/{attempts}"
            )


            response = session.get(

                url,

                timeout=(
                    20,
                    read_timeout
                ),

                allow_redirects=True,

                stream=False

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


            print(
                "Bytes:",
                len(content)
            )


            # Do not parse an HTML error page.

            if not content.startswith(
                b"%PDF"
            ):


                raise RuntimeError(

                    "Server response was not "
                    "a valid PDF."

                )


            print(
                f"{bank}: PDF downloaded."
            )


            return content


        except Exception as error:


            message = (

                f"Attempt {attempt}: "
                f"{error}"

            )


            errors.append(
                message
            )


            print(
                f"{bank}:",
                message
            )


            if attempt < attempts:

                print(
                    "Waiting 5 seconds "
                    "before retry..."
                )

                time.sleep(
                    5
                )


    raise RuntimeError(

        f"{bank} PDF download failed.\n"

        + "\n".join(
            errors
        )

    )


# ==========================================================
# PDF TEXT
# ==========================================================

def pdf_to_text(
    pdf_bytes
):

    result = []


    with pdfplumber.open(
        io.BytesIO(
            pdf_bytes
        )
    ) as pdf:


        for page in pdf.pages:


            result.append(

                page.extract_text()
                or ""

            )


    return "\n".join(
        result
    )


# ==========================================================
# RECORD
# ==========================================================

def make_record(
    bank,
    currency,
    rate,
    source_url,
    source_date,
    source_time
):

    current = now_ist()


    return {

        "date":
            current.strftime(
                "%Y-%m-%d"
            ),

        "time":
            current.strftime(
                "%H:%M:%S"
            ),

        "bank":
            bank,

        "currency":
            currency,

        "rate_type":
            "TT Selling / Outward Remittance",

        "bank_rate":
            float(rate),

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
            current.isoformat(),

        "status":
            get_status(
                source_date
            ),

    }


# ==========================================================
# VALIDATION
# ==========================================================

def validate_rate(
    record
):

    ranges = {

        "USD":
            (70, 130),

        "CAD":
            (40, 100),

        "AUD":
            (40, 100),

        "GBP":
            (90, 180),

        "EUR":
            (80, 160),

        "SGD":
            (45, 110),

        "AED":
            (15, 40),

        "NZD":
            (30, 90),

    }


    currency = (
        record["currency"]
    )


    rate = (
        record["bank_rate"]
    )


    if currency not in ranges:

        return False


    low, high = (
        ranges[currency]
    )


    valid = (
        low
        <= rate
        <= high
    )


    if not valid:


        print(

            "Rejected suspicious rate:",

            record["bank"],

            currency,

            rate

        )


    return valid


# ==========================================================
# SBI
# ==========================================================

def collect_sbi():

    print(
        "\n================================"
    )

    print(
        "SBI"
    )

    print(
        "================================"
    )


    pdf_bytes = download_pdf(

        "SBI",

        SBI_PDF_URL,

        attempts=3,

        read_timeout=60

    )


    text = pdf_to_text(
        pdf_bytes
    )


    source_date = (
        extract_source_date(
            text
        )
    )


    source_time = (
        extract_source_time(
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


    pairs = {

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


    records = []


    for currency, pair in (
        pairs.items()
    ):


        found = False


        for raw_line in (
            text.splitlines()
        ):


            if pair not in raw_line:

                continue


            line = clean_text(
                raw_line
            )


            position = (
                line.find(
                    pair
                )
            )


            after = line[

                position
                + len(pair):

            ]


            values = re.findall(

                r"\d+(?:\.\d+)?",

                after

            )


            if len(values) < 2:

                continue


            # SBI current layout:
            #
            # 1 = TT BUY
            # 2 = TT SELL

            tt_sell = float(
                values[1]
            )


            record = make_record(

                bank="SBI",

                currency=currency,

                rate=tt_sell,

                source_url=SBI_PDF_URL,

                source_date=source_date,

                source_time=source_time

            )


            if validate_rate(
                record
            ):


                records.append(
                    record
                )


                print(

                    "SBI",

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

            "SBI returned no "
            "valid outward rates."

        )


    return records


# ==========================================================
# HDFC HEADER DETECTION
# ==========================================================

def hdfc_is_currency_header(
    value
):

    text = (
        clean_text(
            value
        )
        .lower()
    )


    return (

        "currency (in rs" in text

        or

        text == "currency"

        or

        text == "currency code"

        or

        text == "ccy"

    )


def hdfc_is_outward_header(
    value
):

    text = (
        clean_text(
            value
        )
        .lower()
    )


    selling = (

        "selling" in text

        or

        "sell" in text

    )


    outward = (

        "o/w" in text

        or

        "o / w" in text

        or

        "outward" in text

    )


    remittance = (

        "rem" in text

        or

        "remittance" in text

    )


    return (

        selling
        and outward
        and remittance

    )


# ==========================================================
# HDFC TABLE PARSER
# ==========================================================

def hdfc_parse_table(
    pdf_bytes,
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


            for table_number, table in enumerate(
                tables,
                start=1
            ):


                if not table:

                    continue


                currency_column = None

                outward_column = None

                header_row = None


                # ==================================
                # FIND HEADER BY NAME
                # ==================================

                for row_index, row in enumerate(
                    table
                ):


                    if not row:

                        continue


                    cells = [

                        clean_text(
                            value
                        )

                        for value in row

                    ]


                    for column_index, cell in enumerate(
                        cells
                    ):


                        if hdfc_is_currency_header(
                            cell
                        ):


                            currency_column = (
                                column_index
                            )


                        if hdfc_is_outward_header(
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


                        header_row = (
                            row_index
                        )


                        print(

                            "HDFC table header found"

                        )


                        print(

                            "Currency column:",

                            currency_column

                        )


                        print(

                            "TT Selling O/w column:",

                            outward_column

                        )


                        break


                if header_row is None:

                    continue


                # ==================================
                # READ CURRENCY ROWS
                # ==================================

                for row in table[
                    header_row + 1:
                ]:


                    if not row:

                        continue


                    cells = [

                        clean_text(
                            value
                        )

                        for value in row

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
                        ]
                        .upper()

                    )


                    currency = None


                    for possible in CURRENCIES:


                        if re.search(

                            rf"\b{possible}\b",

                            currency_text

                        ):


                            currency = (
                                possible
                            )


                            break


                    if not currency:

                        continue


                    rate = get_number(

                        cells[
                            outward_column
                        ]

                    )


                    if rate is None:

                        continue


                    record = make_record(

                        bank="HDFC",

                        currency=currency,

                        rate=rate,

                        source_url=HDFC_PDF_URL,

                        source_date=source_date,

                        source_time=source_time

                    )


                    if validate_rate(
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

def hdfc_text_fallback(
    text,
    source_date,
    source_time
):

    print(
        "Trying HDFC text fallback"
    )


    text = clean_text(
        text
    )


    lower = (
        text.lower()
    )


    # We only permit fallback if
    # the document proves the
    # outward-remittance column exists.

    outward_exists = (

        (
            "t.t. selling"
            in lower
        )

        and

        (
            "o/w rem"
            in lower

            or

            "o / w rem"
            in lower

            or

            "outward"
            in lower
        )

    )


    if not outward_exists:


        raise RuntimeError(

            "HDFC outward TT Selling "
            "header could not be verified."

        )


    names = {

        "USD": [
            "United States Dollar",
            "US Dollar",
        ],

        "CAD": [
            "Canadian Dollar",
        ],

        "AUD": [
            "Australian Dollar",
        ],

        "GBP": [
            "Great Britain Pound",
            "British Pound",
        ],

        "EUR": [
            "Euro",
        ],

        "SGD": [
            "Singapore Dollar",
        ],

        "AED": [
            "U.A.E. Dirham",
            "UAE Dirham",
        ],

        "NZD": [
            "New Zealand Dollar",
        ],

    }


    records = []


    for currency in CURRENCIES:


        currency_names = (

            "|".join(

                re.escape(
                    item
                )

                for item in (
                    names[currency]
                )

            )

        )


        pattern = re.compile(

            rf"(?:{currency_names})"
            rf"\s+{currency}\s+"
            r"((?:-|\d+(?:\.\d+)?)"
            r"(?:\s+(?:-|\d+(?:\.\d+)?)){5,})",

            re.IGNORECASE

        )


        match = pattern.search(
            text
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


        # Official HDFC table:
        #
        # 0 Cash Buy
        # 1 Cash Sell
        # 2 Bills Buy
        # 3 Bills Sell
        # 4 TT Buy
        # 5 TT Selling O/w Rem
        #
        # We only use this position after
        # verifying that the named
        # outward header exists.

        value = (
            values[5]
        )


        if value == "-":

            continue


        rate = float(
            value
        )


        record = make_record(

            bank="HDFC",

            currency=currency,

            rate=rate,

            source_url=HDFC_PDF_URL,

            source_date=source_date,

            source_time=source_time

        )


        if validate_rate(
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

def collect_hdfc():

    print(
        "\n================================"
    )

    print(
        "HDFC"
    )

    print(
        "================================"
    )


    # HDFC repository can respond slowly.
    # Give it 2 minutes per read attempt.

    pdf_bytes = download_pdf(

        "HDFC",

        HDFC_PDF_URL,

        attempts=3,

        read_timeout=120

    )


    text = pdf_to_text(
        pdf_bytes
    )


    source_date = (
        extract_source_date(
            text
        )
    )


    source_time = (
        extract_source_time(
            text
        )
    )


    print(

        "HDFC source date:",

        source_date

    )


    print(

        "HDFC source time:",

        source_time

    )


    # =========================================
    # DO NOT ACCEPT UNKNOWN DATE
    # =========================================

    if not source_date:


        raise RuntimeError(

            "HDFC PDF downloaded, "
            "but the rate-card date "
            "could not be verified."

        )


    # =========================================
    # DO NOT ACCEPT OLD RATE CARD
    # =========================================

    status = get_status(
        source_date
    )


    if status != "current":


        raise RuntimeError(

            "HDFC rate card is not current. "
            f"Document date: {source_date}. "
            "Rates will not be published."

        )


    # =========================================
    # TRY HEADER/TABLE METHOD
    # =========================================

    records = hdfc_parse_table(

        pdf_bytes,

        source_date,

        source_time

    )


    # =========================================
    # TRY SAFE TEXT FALLBACK
    # =========================================

    if not records:


        records = (
            hdfc_text_fallback(

                text,

                source_date,

                source_time

            )
        )


    # =========================================
    # DEDUPLICATE
    # =========================================

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

            "HDFC document was current, "
            "but outward rates could not "
            "be extracted safely."

        )


    return records


# ==========================================================
# PREVIOUS DATA
# ==========================================================

def load_previous():

    if not LATEST_FILE.exists():

        return []


    try:


        with open(

            LATEST_FILE,

            "r",

            encoding="utf-8"

        ) as file:


            data = json.load(
                file
            )


        return data.get(
            "rates",
            []
        )


    except Exception:

        return []


# ==========================================================
# PRESERVE FAILED BANK
# ==========================================================

def preserve_bank(
    bank,
    previous
):

    result = []


    for record in previous:


        if record.get(
            "bank"
        ) != bank:

            continue


        copy = dict(
            record
        )


        copy["status"] = (
            "stale"
        )


        result.append(
            copy
        )


    return result


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


    result = {

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

            result,

            file,

            indent=2,

            ensure_ascii=False

        )


# ==========================================================
# HISTORY
# ==========================================================

def history_keys():

    result = set()


    if not HISTORY_FILE.exists():

        return result


    with open(

        HISTORY_FILE,

        "r",

        encoding="utf-8"

    ) as file:


        reader = csv.DictReader(
            file
        )


        for row in reader:


            result.add(

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


    return result


def save_history(
    records
):

    DATA_DIR.mkdir(

        parents=True,

        exist_ok=True

    )


    columns = [

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


    existing = (
        history_keys()
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

            fieldnames=columns,

            extrasaction="ignore"

        )


        if not file_exists:

            writer.writeheader()


        for record in records:


            # Stale fallback values should
            # never become new history rows.

            if record.get(
                "status"
            ) != "current":

                continue


            key = (

                record.get(
                    "source_date"
                ),

                record.get(
                    "bank"
                ),

                record.get(
                    "currency"
                ),

            )


            if key in existing:

                continue


            writer.writerow({

                field:
                    record.get(
                        field,
                        ""
                    )

                for field in columns

            })


            existing.add(
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


    previous = (
        load_previous()
    )


    records = []


    collectors = [

        (
            "SBI",
            collect_sbi
        ),

        (
            "HDFC",
            collect_hdfc
        ),

    ]


    for bank, collector in (
        collectors
    ):


        try:


            bank_records = (
                collector()
            )


            records.extend(
                bank_records
            )


            print(

                bank,

                "SUCCESS:",

                len(bank_records),

                "rates"

            )


        except Exception as error:


            print(
                "\n"
                + bank
                + " FAILED:"
            )


            print(
                str(error)
            )


            old_records = (
                preserve_bank(

                    bank,

                    previous

                )
            )


            if old_records:


                print(

                    "Preserving",

                    len(old_records),

                    bank,

                    "records as stale."

                )


                records.extend(
                    old_records
                )


    # ======================================================
    # FINAL VALIDATION
    # ======================================================

    valid = []


    for record in records:


        if validate_rate(
            record
        ):


            valid.append(
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

        currency: index

        for index, currency
        in enumerate(
            CURRENCIES
        )

    }


    valid.sort(

        key=lambda row: (

            bank_order.get(
                row["bank"],
                99
            ),

            currency_order.get(
                row["currency"],
                99
            )

        )

    )


    # ======================================================
    # SAVE
    # ======================================================

    save_latest(
        valid
    )


    save_history(
        valid
    )


    # ======================================================
    # SUMMARY
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


    for record in valid:


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

        len(valid)

    )


if __name__ == "__main__":

    main()
