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
# TEXT HELPERS
# ==========================================================

def clean_text(value):

    return re.sub(
        r"\s+",
        " ",
        str(value or "")
    ).strip()


def normalize_for_header(value):

    text = str(
        value or ""
    ).lower()

    # Replace line breaks/tabs with spaces
    text = re.sub(
        r"[\r\n\t]+",
        " ",
        text
    )

    # Collapse multiple spaces
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    # Normalise variations
    text = (
        text
        .replace("t.t.", "tt")
        .replace("t. t.", "tt")
        .replace("o / w", "o/w")
        .replace("o/ w", "o/w")
        .replace("o /w", "o/w")
    )

    return text.strip()


def compact_text(value):

    return re.sub(
        r"[^a-z0-9/]+",
        "",
        normalize_for_header(value)
    )


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
# PDF -> TEXT
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

    patterns = [

        r"\bTIME\s*[:\-]?\s*"
        r"(\d{1,2}:\d{2}:\d{2}\s*[AP]M)",

        r"\bTIME\s*[:\-]?\s*"
        r"(\d{1,2}:\d{2}\s*[AP]M)",

        # fallback: any nearby time
        r"\b"
        r"(\d{1,2}:\d{2}:\d{2}\s*[AP]M)"
        r"\b",

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
# HDFC OUTWARD HEADER DETECTION
# ==========================================================

def is_outward_sell_header(
    value
):

    normalized = normalize_for_header(
        value
    )

    compact = compact_text(
        value
    )

    has_sell = (
        "selling" in normalized
        or
        "sell" in normalized
        or
        "selling" in compact
    )

    has_outward = (
        "o/w" in normalized
        or
        "outward" in normalized
        or
        "o/w" in compact
    )

    has_remittance = (
        "rem" in normalized
        or
        "remittance" in normalized
        or
        "rem" in compact
    )

    return (
        has_sell
        and
        has_outward
        and
        has_remittance
    )


def document_has_outward_header(
    text
):

    normalized = normalize_for_header(
        text
    )

    compact = compact_text(
        text
    )

    # Handles:
    #
    # TT Selling (O/w Rem)
    #
    # and:
    #
    # T.T. Selling (O/w
    # Rem)

    patterns = [

        r"tt\s*selling.*?o/w.*?rem",

        r"ttselling.*?o/w.*?rem",

        r"selling.*?o/w.*?rem",

    ]

    for pattern in patterns:

        if re.search(
            pattern,
            normalized,
            re.IGNORECASE
        ):

            return True

    if (
        "selling" in compact
        and
        "o/w" in compact
        and
        "rem" in compact
    ):

        return True

    return False


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
# TEXT EXTRACTION
# ==========================================================

def extract_from_text(
    text,
    source_date,
    source_time
):

    print(
        "HDFC Agent: extracting rates from PDF text."
    )

    if not document_has_outward_header(
        text
    ):

        raise RuntimeError(
            "HDFC T.T. Selling "
            "(O/w Rem) header "
            "could not be verified."
        )

    print(
        "HDFC T.T. Selling (O/w Rem) header verified."
    )

    normalized = clean_text(
        text
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

        # HDFC row commonly appears as:
        #
        # US Dollar USD
        # 93.24 98.13 95.27 97.61 95.46 97.33 ...
        #
        # We take the 6th value = T.T. Selling (O/w Rem)

        patterns = [

            re.compile(
                rf"(?:{name_pattern})"
                rf"\s+{currency}\s+"
                r"((?:-|\d+(?:\.\d+)?)"
                r"(?:\s+(?:-|\d+(?:\.\d+)?)){5,})",
                re.IGNORECASE
            ),

            re.compile(
                rf"\b{currency}\b\s+"
                rf"(?:{name_pattern})\s+"
                r"((?:-|\d+(?:\.\d+)?)"
                r"(?:\s+(?:-|\d+(?:\.\d+)?)){5,})",
                re.IGNORECASE
            ),

            # Fallback: code itself followed by rates

            re.compile(
                rf"\b{currency}\b\s+"
                r"((?:-|\d+(?:\.\d+)?)"
                r"(?:\s+(?:-|\d+(?:\.\d+)?)){5,})",
                re.IGNORECASE
            ),

        ]

        match = None

        for pattern in patterns:

            match = pattern.search(
                normalized
            )

            if match:
                break

        if not match:

            print(
                "HDFC missing:",
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

        if len(values) < 6:

            print(
                "HDFC insufficient values:",
                currency
            )

            continue

        # Official HDFC table order:
        #
        # 0 Cash Buying
        # 1 Cash Selling
        # 2 Bills Buying
        # 3 Bills Selling
        # 4 TT Buying
        # 5 TT Selling (O/w Rem)

        tt_sell_value = (
            values[5]
        )

        if tt_sell_value == "-":

            print(
                "HDFC TT Sell missing:",
                currency
            )

            continue

        rate = float(
            tt_sell_value
        )

        if not rate_is_reasonable(
            currency,
            rate
        ):

            print(
                "HDFC rejected suspicious rate:",
                currency,
                rate
            )

            continue

        record = build_record(
            currency,
            rate,
            source_date,
            source_time
        )

        records.append(
            record
        )

        print(
            "HDFC",
            currency,
            "TT Sell:",
            rate
        )

    return records


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
    # PDF TEXT
    # ------------------------------------------------------

    text = extract_pdf_text(
        pdf_bytes
    )

    # ------------------------------------------------------
    # SOURCE DATE + TIME
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

    if not source_date:

        raise RuntimeError(
            "HDFC PDF downloaded, "
            "but source date "
            "could not be verified."
        )

    if determine_status(
        source_date
    ) != "current":

        raise RuntimeError(
            "HDFC rate card is not current. "
            f"Source date: {source_date}"
        )

    # ------------------------------------------------------
    # EXTRACT RATES
    # ------------------------------------------------------

    records = extract_from_text(
        text,
        source_date,
        source_time
    )

    records = deduplicate(
        records
    )

    # ------------------------------------------------------
    # REQUIRE ALL 8 CURRENCIES
    # ------------------------------------------------------

    found = {
        record["currency"]
        for record in records
    }

    missing = (
        set(CURRENCIES)
        - found
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
