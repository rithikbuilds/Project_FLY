import html
import re
import requests

from datetime import datetime
from zoneinfo import ZoneInfo


# ==========================================================
# CONFIGURATION
# ==========================================================

IST = ZoneInfo("Asia/Kolkata")

BANK_NAME = "Canara Bank"

RATE_TYPE = "TT Selling / Outward Remittance"

SOURCE_URL = (
    "https://www.canarabank.bank.in/"
    "pages/forex-card-rates"
)

CURRENCIES = [
    "USD",
    "CAD",
    "AUD",
    "GBP",
    "EUR",
    "SGD",
    "AED",
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

    "Accept-Language":
        "en-US,en;q=0.9",
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
        "Canara Agent: downloading official Forex Card Rates page"
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
            "Canara returned an unexpectedly small page."
        )

    print(
        "Canara Agent: page downloaded successfully"
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
# HTML → TEXT
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

    """
    Canara currently publishes:

    DATE : 24/Aug/26
    """

    pattern = re.compile(
        r"\bDATE\s*:\s*"
        r"(\d{1,2})/"
        r"([A-Za-z]{3})/"
        r"(\d{2,4})",
        re.IGNORECASE
    )

    match = pattern.search(
        text
    )

    if not match:

        return None

    day = match.group(1)
    month = match.group(2)
    year = match.group(3)

    if len(year) == 2:
        year = "20" + year

    raw = (
        f"{day}-{month}-{year}"
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
# VERIFY RATE TABLE
# ==========================================================

def verify_rate_table(text):

    lower = text.lower()

    required = [
        "selling rates",
        "tt/dds",
        "currency",
    ]

    for value in required:

        if value not in lower:

            raise RuntimeError(
                "Canara expected table header "
                f"not found: {value}"
            )

    print(
        "Canara SELLING RATES / TT-DDS headers verified."
    )


# ==========================================================
# EXTRACT TT/DDS SELLING RATES
# ==========================================================

def extract_rates(text):

    rates = {}

    for currency in CURRENCIES:

        """
        Official Canara row pattern:

        USD/INR 96.0525 96.2425 95.2975 95.2325

        Columns:

        Selling TT/DDS
        Selling BILL
        Buying TT/CHQ
        Buying BILL

        Therefore the first rate after
        CURRENCY/INR is the outward
        TT/DDS selling rate.
        """

        pattern = re.compile(
            rf"\b{currency}/INR\b\s+"
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
                "Canara missing:",
                currency
            )

            continue

        tt_dds_sell = float(
            match.group(1)
        )

        print(
            "Canara",
            currency,
            "TT/DDS Sell:",
            tt_dds_sell
        )

        rates[currency] = (
            tt_dds_sell
        )

    return rates


# ==========================================================
# BUILD STANDARD RECORD
# ==========================================================

def build_record(
    currency,
    rate,
    source_date
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
            None,

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
        "CANARA BANK AGENT"
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

    print(
        "Canara source date:",
        source_date
    )

    if not source_date:

        raise RuntimeError(
            "Canara rate-card date "
            "could not be verified."
        )

    if determine_status(
        source_date
    ) != "current":

        raise RuntimeError(
            "Canara rate page is not current. "
            f"Source date: {source_date}"
        )

    rates = extract_rates(
        text
    )

    if not rates:

        raise RuntimeError(
            "Canara Agent returned no rates."
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
            "Canara Agent missing currencies: "
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
            source_date
        )

        records.append(
            record
        )

        print(
            "Canara",
            currency,
            rate,
            record["status"]
        )

    print(
        "Canara Agent completed:",
        len(records),
        "rates"
    )

    return records
