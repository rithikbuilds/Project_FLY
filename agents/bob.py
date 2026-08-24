import html
import re
import requests

from datetime import datetime
from zoneinfo import ZoneInfo


# ==========================================================
# CONFIGURATION
# ==========================================================

IST = ZoneInfo("Asia/Kolkata")

BANK_NAME = "Bank of Baroda"

RATE_TYPE = "TT Selling / Outward Remittance"

SOURCE_URL = (
    "https://bankofbaroda.bank.in/"
    "business-banking/treasury/forex-card-rates"
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


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/129 Safari/537.36"
    ),
    "Accept": (
        "text/html,"
        "application/xhtml+xml,"
        "application/xml;q=0.9,"
        "*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ==========================================================
# TIME
# ==========================================================

def now_ist():

    return datetime.now(IST)


# ==========================================================
# DOWNLOAD
# ==========================================================

def download_page():

    print(
        "BOB Agent: downloading official Forex Card Rates page"
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

    page = response.text

    if len(page) < 1000:

        raise RuntimeError(
            "Bank of Baroda returned an unexpectedly small page."
        )

    print(
        "BOB Agent: page downloaded successfully"
    )

    print(
        "HTTP:",
        response.status_code
    )

    print(
        "Characters:",
        len(page)
    )

    return page


# ==========================================================
# HTML → CLEAN TEXT
# ==========================================================

def html_to_text(page):

    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        page,
        flags=re.IGNORECASE | re.DOTALL
    )

    text = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = html.unescape(
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ==========================================================
# SOURCE DATE
# ==========================================================

def extract_source_date(text):

    patterns = [
        r"\bDate\s*[:\-]?\s*"
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


    month_match = re.search(
        r"\b"
        r"(\d{1,2})[-\s]"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"[-\s](20\d{2})"
        r"\b",
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
# SOURCE TIME
# ==========================================================

def extract_source_time(text):

    patterns = [
        r"\bTime\s*[:\-]?\s*"
        r"(\d{1,2}:\d{2}(?::\d{2})?\s*[AP]M)",

        r"\b"
        r"(\d{1,2}:\d{2}(?::\d{2})?\s*[AP]M)"
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
# VERIFY TABLE
# ==========================================================

def verify_rate_table(text):

    lower = text.lower()

    required_headers = [
        "currency",
        "ttsell",
        "bill sell",
        "ttbuy",
    ]

    for header in required_headers:

        if header not in lower:

            raise RuntimeError(
                "Bank of Baroda expected header not found: "
                + header
            )

    print(
        "BOB Currency / TTSell / TTBuy headers verified."
    )


# ==========================================================
# EXTRACT TT SELL RATES
# ==========================================================

def extract_rates(text):

    rates = {}

    for currency in CURRENCIES:

        """
        BOB row structure:

        Currency
        TTSell
        BillSell
        TTBuy
        BillBuy
        TCBuy
        TCSell
        CNBuy
        CNSell

        We only need the first numeric rate
        after the currency code = TTSell.
        """

        pattern = re.compile(
            rf"\b{currency}\b\s+"
            r"(\d+(?:\.\d+)?)\s+"
            r"(\d+(?:\.\d+)?)\s+"
            r"(\d+(?:\.\d+)?)\s+"
            r"(\d+(?:\.\d+)?)",
            re.IGNORECASE
        )

        match = pattern.search(
            text
        )

        if not match:

            print(
                "BOB missing:",
                currency
            )

            continue

        tt_sell = float(
            match.group(1)
        )

        print(
            "BOB",
            currency,
            "TTSell:",
            tt_sell
        )

        rates[currency] = (
            tt_sell
        )

    return rates


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
# MAIN AGENT
# ==========================================================

def collect():

    print()

    print(
        "=============================="
    )

    print(
        "BANK OF BARODA AGENT"
    )

    print(
        "=============================="
    )

    page = download_page()

    text = html_to_text(
        page
    )

    verify_rate_table(
        text
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
        "BOB source date:",
        source_date
    )

    print(
        "BOB source time:",
        source_time
    )

    if not source_date:

        raise RuntimeError(
            "Bank of Baroda rate-card date "
            "could not be verified."
        )

    if determine_status(
        source_date
    ) != "current":

        raise RuntimeError(
            "Bank of Baroda rate page is not current. "
            f"Source date: {source_date}"
        )

    rates = extract_rates(
        text
    )

    if not rates:

        raise RuntimeError(
            "Bank of Baroda Agent returned no rates."
        )

    required = set(
        CURRENCIES
    )

    missing = (
        required
        - set(rates.keys())
    )

    if missing:

        raise RuntimeError(
            "Bank of Baroda Agent missing currencies: "
            + ", ".join(
                sorted(missing)
            )
        )

    records = []

    for currency in CURRENCIES:

        rate = rates[
            currency
        ]

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
            "BOB",
            currency,
            rate,
            record["status"]
        )

    print(
        "Bank of Baroda Agent completed:",
        len(records),
        "rates"
    )

    return records
