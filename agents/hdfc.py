import io
import re
import requests
import pdfplumber

from datetime import datetime
from zoneinfo import ZoneInfo


# ==========================================================
# CONFIGURATION
# ==========================================================

IST = ZoneInfo("Asia/Kolkata")

BANK_NAME = "HDFC Bank"

RATE_TYPE = "TT Selling / Outward Remittance"

SOURCE_URL = (
    "https://www.hdfc.bank.in/content/dam/hdfcbankpws/"
    "in/en/personal-banking/discover-products/interest-rates/"
    "hdfc-bank-treasury-forex-card-rates.pdf"
)


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


CURRENCY_NAMES = {

    "USD": [
        "US Dollar",
        "United States Dollar",
    ],

    "CAD": [
        "Canadian Dollar",
    ],

    "AUD": [
        "Australian Dollar",
    ],

    "GBP": [
        "British Pound",
        "Great Britain Pound",
    ],

    "EUR": [
        "Euro",
    ],

    "SGD": [
        "Singapore Dollar",
    ],

    "AED": [
        "UAE Dirham",
        "U.A.E. Dirham",
    ],

    "NZD": [
        "New Zealand Dollar",
    ],

}


HEADERS = {

    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/129 Safari/537.36"
    ),

    "Accept": (
        "application/pdf,"
        "application/octet-stream,"
        "*/*"
    ),

    "Accept-Language":
        "en-US,en;q=0.9",

}


# ==========================================================
# TIME
# ==========================================================

def now_ist():

    return datetime.now(IST)


# ==========================================================
# CLEAN TEXT
# ==========================================================

def clean_text(value):

    return re.sub(
        r"\s+",
        " ",
        str(value or "")
    ).strip()


# ==========================================================
# DOWNLOAD PDF
# ==========================================================

def download_pdf():

    print(
        "HDFC Agent: downloading official Treasury Forex Card Rates PDF"
    )

    print(
        SOURCE_URL
    )


    response = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=60
    )


    response.raise_for_status()


    content = response.content


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


    if not content.startswith(
        b"%PDF"
    ):

        raise RuntimeError(
            "HDFC source did not return a valid PDF."
        )


    print(
        "HDFC Agent: PDF downloaded successfully."
    )


    return content


# ==========================================================
# PDF → TEXT
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
# SOURCE DATE
# ==========================================================

def extract_source_date(text):

    """
    Supports HDFC formats such as:

    DATE : 24-08-2026
    DATE: 24/08/2026
    24-08-2026
    """


    patterns = [

        r"\bDATE\s*[:\-]?\s*"
        r"(\d{1,2})[-/](\d{1,2})[-/](20\d{2})",

        r"\b"
        r"(\d{1,2})[-/](\d{1,2})[-/](20\d{2})"
        r"\b",

    ]


    for pattern in patterns:


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


    return None


# ==========================================================
# SOURCE TIME
# ==========================================================

def extract_source_time(text):

    """
    Example:

    TIME : 09:24:24 AM
    """


    patterns = [

        r"\bTIME\s*[:\-]?\s*"
        r"(\d{1,2}:\d{2}:\d{2}\s*[AP]M)",

        r"\bTIME\s*[:\-]?\s*"
        r"(\d{1,2}:\d{2}\s*[AP]M)",

    ]


    for pattern in patterns:


        match = re.search(

            pattern,

            text,

            re.IGNORECASE

        )


        if match:


            return (
                match.group(1)
                .strip()
                .upper()
            )


    return None


# ==========================================================
# STATUS
# ==========================================================

def determine_status(
    source_date
):

    if not source_date:

        return "date_unverified"


    today = now_ist().strftime(
        "%Y-%m-%d"
    )


    if source_date == today:

        return "current"


    return "stale"


# ==========================================================
# VALID RATE RANGE
# ==========================================================

def rate_is_reasonable(
    currency,
    rate
):

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


    return (
        low
        <= rate
        <= high
    )


# ==========================================================
# HEADER DETECTION
# ==========================================================

def is_currency_header(
    value
):

    text = (
        clean_text(
            value
        )
        .lower()
    )


    return (

        "currency" in text

        or

        text == "ccy"

    )


def is_outward_sell_header(
    value
):

    text = (
        clean_text(
            value
        )
        .lower()
    )


    # Remove extra spaces so variants still work

    compact = re.sub(
        r"\s+",
        "",
        text
    )


    selling = (

        "selling" in text

        or

        "sell" in text

    )


    outward = (

        "o/w" in text

        or

        "o/w" in compact

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
        and
        outward
        and
        remittance

    )


# ==========================================================
# TABLE-BASED EXTRACTION
# ==========================================================

def extract_from_tables(
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


            for table in tables:


                if not table:

                    continue


                currency_column = None

                outward_column = None

                header_row_index = None


                # ------------------------------------------
                # FIND HEADER ROW
                # ------------------------------------------

                for row_index, row in enumerate(
                    table
                ):


                    if not row:

                        continue


                    cells = [

                        clean_text(
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


                        header_row_index = (
                            row_index
                        )


                        print(
                            "HDFC table header detected."
                        )


                        print(
                            "Currency column:",
                            currency_column
                        )


                        print(
                            "T.T. Selling O/w column:",
                            outward_column
                        )


                        break


                if header_row_index is None:

                    continue


                # ------------------------------------------
                # READ DATA ROWS
                # ------------------------------------------

                for row in table[
                    header_row_index + 1:
                ]:


                    if not row:

                        continue


                    cells = [

                        clean_text(
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
                        ]
                        .upper()
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


                    rate_text = (
                        cells[
                            outward_column
                        ]
                    )


                    match = re.search(

                        r"\d+(?:\.\d+)?",

                        rate_text

                    )


                    if not match:

                        continue


                    rate = float(
                        match.group()
                    )


                    if not rate_is_reasonable(
                        currency,
                        rate
                    ):


                        print(
                            "HDFC rejected suspicious table rate:",
                            currency,
                            rate
                        )


                        continue


                    records.append(

                        build_record(

                            currency,
                            rate,
                            source_date,
                            source_time

                        )

                    )


                    print(
                        "HDFC table",
                        currency,
                        rate
                    )


    return records


# ==========================================================
# TEXT FALLBACK
# ==========================================================

def extract_from_text(
    text,
    source_date,
    source_time
):

    print(
        "HDFC Agent: trying text fallback."
    )


    normalized = clean_text(
        text
    )


    lower = normalized.lower()


    # ------------------------------------------------------
    # SAFETY:
    # Confirm correct outward-remittance header exists
    # ------------------------------------------------------

    outward_header_present = (

        (
            "t.t. selling" in lower

            or

            "tt selling" in lower
        )

        and

        (
            "o/w rem" in lower

            or

            "o / w rem" in lower

            or

            "outward" in lower
        )

    )


    if not outward_header_present:


        raise RuntimeError(

            "HDFC T.T. Selling "
            "(O/w Rem) header "
            "could not be verified."

        )


    records = []


    for currency in CURRENCIES:


        names = (
            CURRENCY_NAMES[
                currency
            ]
        )


        name_pattern = "|".join(

            re.escape(name)

            for name in names

        )


        # --------------------------------------------------
        # HDFC row
        #
        # Currency Name
        # Currency Code
        # followed by rate values
        # --------------------------------------------------

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


            # Some HDFC PDF extraction may show
            # currency code before currency name.

            pattern_reverse = re.compile(

                rf"\b{currency}\b\s+"
                rf"(?:{name_pattern})\s+"
                r"((?:-|\d+(?:\.\d+)?)"
                r"(?:\s+(?:-|\d+(?:\.\d+)?)){5,})",

                re.IGNORECASE

            )


            match = pattern_reverse.search(
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


        print(
            "HDFC",
            currency,
            "row values:",
            values[:10]
        )


        # --------------------------------------------------
        # HDFC official table order:
        #
        # 0 Cash Buying
        # 1 Cash Selling
        # 2 Bills Buying
        # 3 Bills Selling
        # 4 TT Buying
        # 5 TT Selling (O/w Rem)
        #
        # The header itself was verified above before
        # this fallback is allowed.
        # --------------------------------------------------

        if len(values) < 6:

            continue


        value = (
            values[5]
        )


        if value == "-":

            continue


        rate = float(
            value
        )


        if not rate_is_reasonable(
            currency,
            rate
        ):


            print(
                "HDFC rejected suspicious fallback rate:",
                currency,
                rate
            )


            continue


        records.append(

            build_record(

                currency,
                rate,
                source_date,
                source_time

            )

        )


        print(
            "HDFC fallback",
            currency,
            rate
        )


    return records


# ==========================================================
# BUILD STANDARD RECORD
# ==========================================================

def build_record(
    currency,
    rate,
    source_date,
    source_time
):

    fetched = now_ist()


    return {

        "date":
            fetched.strftime(
                "%Y-%m-%d"
            ),

        "time":
            fetched.strftime(
                "%H:%M:%S"
            ),

        "bank":
            BANK_NAME,

        "currency":
            currency,

        "rate_type":
            RATE_TYPE,

        "bank_rate":
            float(rate),

        "market_rate":
            None,

        "markup_percent":
            None,

        "source_url":
            SOURCE_URL,

        "source_date":
            source_date,

        "source_time":
            source_time,

        "fetched_at":
            fetched.isoformat(),

        "status":
            determine_status(
                source_date
            ),

    }


# ==========================================================
# REMOVE DUPLICATES
# ==========================================================

def deduplicate(
    records
):

    unique = {}


    for record in records:


        unique[
            record["currency"]
        ] = record


    return list(
        unique.values()
    )


# ==========================================================
# MAIN AGENT
# ==========================================================

def collect():

    print()

    print(
        "=============================="
    )

    print(
        "HDFC BANK AGENT"
    )

    print(
        "=============================="
    )


    # ------------------------------------------------------
    # DOWNLOAD
    # ------------------------------------------------------

    pdf_bytes = download_pdf()


    # ------------------------------------------------------
    # EXTRACT TEXT
    # ------------------------------------------------------

    text = extract_pdf_text(
        pdf_bytes
    )


    # ------------------------------------------------------
    # SOURCE DATE/TIME
    # ------------------------------------------------------

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


    # ------------------------------------------------------
    # REQUIRE SOURCE DATE
    # ------------------------------------------------------

    if not source_date:


        raise RuntimeError(

            "HDFC PDF downloaded, "
            "but source date "
            "could not be verified."

        )


    # ------------------------------------------------------
    # REQUIRE TODAY'S CARD
    # ------------------------------------------------------

    if determine_status(
        source_date
    ) != "current":


        raise RuntimeError(

            "HDFC rate card is not current. "
            f"Source date: {source_date}"

        )


    # ------------------------------------------------------
    # VERIFY OUTWARD HEADER
    # ------------------------------------------------------

    lower_text = (
        clean_text(
            text
        )
        .lower()
    )


    if not (

        (
            "t.t. selling" in lower_text

            or

            "tt selling" in lower_text
        )

        and

        (
            "o/w rem" in lower_text

            or

            "o / w rem" in lower_text

            or

            "outward" in lower_text
        )

    ):


        raise RuntimeError(

            "HDFC outward-remittance "
            "TT Selling header was not found."

        )


    print(
        "HDFC T.T. Selling (O/w Rem) header verified."
    )


    # ------------------------------------------------------
    # METHOD 1 — TABLE EXTRACTION
    # ------------------------------------------------------

    records = extract_from_tables(

        pdf_bytes,

        source_date,

        source_time

    )


    records = deduplicate(
        records
    )


    # ------------------------------------------------------
    # METHOD 2 — TEXT FALLBACK
    # ------------------------------------------------------

    if len(records) < len(
        CURRENCIES
    ):


        fallback_records = (
            extract_from_text(

                text,

                source_date,

                source_time

            )
        )


        records.extend(
            fallback_records
        )


        records = deduplicate(
            records
        )


    # ------------------------------------------------------
    # REQUIRE ALL 8
    # ------------------------------------------------------

    currencies_found = {

        record["currency"]

        for record in records

    }


    missing = (

        set(CURRENCIES)

        - currencies_found

    )


    if missing:


        raise RuntimeError(

            "HDFC Agent missing currencies: "

            + ", ".join(
                sorted(missing)
            )

        )


    # ------------------------------------------------------
    # SORT
    # ------------------------------------------------------

    order = {

        currency: index

        for index, currency
        in enumerate(
            CURRENCIES
        )

    }


    records.sort(

        key=lambda item:

            order.get(
                item["currency"],
                999
            )

    )


    # ------------------------------------------------------
    # OUTPUT
    # ------------------------------------------------------

    for record in records:


        print(

            "HDFC",

            record["currency"],

            record["bank_rate"],

            "| source:",

            record["source_date"],

            record["source_time"],

            "|",

            record["status"]

        )


    print(
        "HDFC Agent completed:",
        len(records),
        "rates"
    )


    return records
