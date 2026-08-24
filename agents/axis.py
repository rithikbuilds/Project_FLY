import re
import requests

from datetime import datetime
from zoneinfo import ZoneInfo


# ==========================================================
# CONFIG
# ==========================================================

IST = ZoneInfo("Asia/Kolkata")

BANK_NAME = "Axis Bank"

RATE_TYPE = "TT Selling / Outward Remittance"

SOURCE_URL = (
    "https://application.axis.bank.in/"
    "webforms/corporatecardrate/index.aspx"
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
# DOWNLOAD PAGE
# ==========================================================

def download_page():

    print("Axis Agent: downloading official rate page")
    print(SOURCE_URL)

    response = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=60
    )

    response.raise_for_status()

    html = response.text

    if len(html) < 1000:
        raise RuntimeError(
            "Axis returned an unexpectedly small page."
        )

    print(
        "Axis Agent: page downloaded successfully"
    )

    print(
        "HTTP:",
        response.status_code
    )

    print(
        "Characters:",
        len(html)
    )

    return html


# ==========================================================
# HTML → CLEAN TEXT
# ==========================================================

def html_to_text(html):

    # Remove scripts
    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        html,
        flags=re.IGNORECASE | re.DOTALL
    )

    # Remove styles
    text = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL
    )

    # Convert table cells / rows into spaces
    text = re.sub(
        r"</?(?:td|th|tr|table|tbody|thead)[^>]*>",
        " ",
        text,
        flags=re.IGNORECASE
    )

    # Remove remaining HTML tags
    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    # Common HTML entities
    text = (
        text
        .replace("&nbsp;", " ")
        .replace("&#160;", " ")
        .replace("&amp;", "&")
    )

    # Collapse whitespace
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ==========================================================
# SOURCE DATE / TIME
# ==========================================================

def extract_source_datetime(text):

    """
    Axis publishes text similar to:

    The above exchange rates are published on
    Aug 24,2026 at 06:40 PM
    """

    pattern = re.compile(
        r"published\s+on\s+"
        r"([A-Za-z]{3})\s+"
        r"(\d{1,2})\s*,\s*"
        r"(20\d{2})\s+"
        r"at\s+"
        r"(\d{1,2}:\d{2}\s*[AP]M)",
        re.IGNORECASE
    )

    match = pattern.search(text)

    if not match:
        return None, None

    month_text = match.group(1)
    day = match.group(2)
    year = match.group(3)
    source_time = match.group(4).upper()

    raw_date = (
        f"{month_text} {day} {year}"
    )

    try:

        parsed = datetime.strptime(
            raw_date,
            "%b %d %Y"
        )

    except ValueError:

        return None, None

    source_date = parsed.strftime(
        "%Y-%m-%d"
    )

    return (
        source_date,
        source_time
    )


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
# EXTRACT RATES
# ==========================================================

def extract_rates(text):

    """
    Axis table structure:

    Currency Name
    Currency Code
    TT Buy
    TT Sell
    Bill Buy
    Bill Sell
    TC Buy
    TC Sell
    CCY Buy
    CCY Sell

    We dynamically identify the currency code,
    then take the second numeric value = TT Sell.
    """

    rates = {}

    for currency in CURRENCIES:

        pattern = re.compile(
            rf"\b{currency}\b\s+"
            r"(\d+(?:\.\d+)?)\s+"
            r"(\d+(?:\.\d+)?)\s+"
            r"(\d+(?:\.\d+)?)\s+"
            r"(\d+(?:\.\d+)?)\s+"
            r"(\d+(?:\.\d+)?)\s+"
            r"(\d+(?:\.\d+)?)\s+"
            r"(\d+(?:\.\d+)?)\s+"
            r"(\d+(?:\.\d+)?)",
            re.IGNORECASE
        )

        match = pattern.search(text)

        if not match:

            print(
                "Axis missing:",
                currency
            )

            continue

        tt_buy = float(
            match.group(1)
        )

        tt_sell = float(
            match.group(2)
        )

        print(
            currency,
            "TT Buy:",
            tt_buy,
            "| TT Sell:",
            tt_sell
        )

        rates[currency] = tt_sell

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
        "date": fetched.strftime(
            "%Y-%m-%d"
        ),

        "time": fetched.strftime(
            "%H:%M:%S"
        ),

        "bank": BANK_NAME,

        "currency": currency,

        "rate_type": RATE_TYPE,

        "bank_rate": float(rate),

        "market_rate": None,

        "markup_percent": None,

        "source_url": SOURCE_URL,

        "source_date": source_date,

        "source_time": source_time,

        "fetched_at": fetched.isoformat(),

        "status": determine_status(
            source_date
        ),
    }


# ==========================================================
# MAIN AGENT
# ==========================================================

def collect():

    print()
    print("==============================")
    print("AXIS BANK AGENT")
    print("==============================")

    html = download_page()

    text = html_to_text(
        html
    )

    # ------------------------------------------------------
    # Verify correct table
    # ------------------------------------------------------

    if "TT Buy" not in text:
        raise RuntimeError(
            "Axis TT Buy header not found."
        )

    if "TT Sell" not in text:
        raise RuntimeError(
            "Axis TT Sell header not found."
        )

    print(
        "Axis TT Buy / TT Sell headers verified."
    )

    # ------------------------------------------------------
    # Extract official publication date/time
    # ------------------------------------------------------

    source_date, source_time = (
        extract_source_datetime(
            text
        )
    )

    print(
        "Axis source date:",
        source_date
    )

    print(
        "Axis source time:",
        source_time
    )

    if not source_date:

        raise RuntimeError(
            "Axis publication date could not "
            "be verified."
        )

    # ------------------------------------------------------
    # Reject stale page
    # ------------------------------------------------------

    status = determine_status(
        source_date
    )

    if status != "current":

        raise RuntimeError(
            "Axis rate page is not current. "
            f"Source date: {source_date}"
        )

    # ------------------------------------------------------
    # Extract TT Sell
    # ------------------------------------------------------

    rates = extract_rates(
        text
    )

    if not rates:

        raise RuntimeError(
            "Axis Agent returned no rates."
        )

    # ------------------------------------------------------
    # Require our major currencies
    # ------------------------------------------------------

    required = {
        "USD",
        "CAD",
        "AUD",
        "GBP",
        "EUR",
        "SGD",
        "AED",
        "NZD",
    }

    missing = (
        required - set(rates.keys())
    )

    if missing:

        raise RuntimeError(
            "Axis Agent missing currencies: "
            + ", ".join(
                sorted(missing)
            )
        )

    # ------------------------------------------------------
    # Build normalized records
    # ------------------------------------------------------

    records = []

    for currency in CURRENCIES:

        rate = rates[currency]

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
            "Axis",
            currency,
            rate,
            record["status"]
        )

    print(
        "Axis Agent completed:",
        len(records),
        "rates"
    )

    return records
