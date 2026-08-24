import html
import re
import requests

from datetime import datetime
from zoneinfo import ZoneInfo


# ==========================================================
# CONFIGURATION
# ==========================================================

IST = ZoneInfo("Asia/Kolkata")

BANK_NAME = "ICICI Bank"

RATE_TYPE = "TT Selling / Outward Remittance"

SOURCE_URL = (
    "https://www.icici.bank.in/"
    "corporate/global-markets/forex/forex-card-rate"
)

CURRENCIES = [
    "USD",
    "CAD",
    "AUD",
    "GBP",
    "EUR",
    "SGD",
]


CURRENCY_NAMES = {

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
        "ICICI Agent: downloading official Forex Rates page"
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
            "ICICI returned an unexpectedly small page."
        )


    print(
        "ICICI Agent: page downloaded successfully"
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

    patterns = [

        # Date: 24-08-2026
        r"\bDate\s*:\s*"
        r"(\d{1,2})[-/](\d{1,2})[-/](20\d{2})",

        # fallback without Date:
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

    match = re.search(

        r"\bTime\s*:\s*"
        r"(\d{1,2}:\d{2}"
        r"(?::\d{2})?\s*[AP]M)",

        text,

        re.IGNORECASE

    )


    if not match:

        return None


    return (
        match.group(1)
        .strip()
        .upper()
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
# VERIFY TABLE
# ==========================================================

def verify_rate_table(text):

    required_headers = [

        "TT Buying",

        "TT Selling",

    ]


    lower = text.lower()


    for header in required_headers:

        if header.lower() not in lower:

            raise RuntimeError(

                "ICICI expected rate header "
                f"not found: {header}"

            )


    print(
        "ICICI TT Buying / TT Selling headers verified."
    )


# ==========================================================
# EXTRACT RATE ROW
# ==========================================================

def extract_currency_rate(
    text,
    currency
):

    names = CURRENCY_NAMES[
        currency
    ]


    name_pattern = "|".join(

        re.escape(name)

        for name in names

    )


    """
    ICICI rate table currently exposes:

    Currency

    Bank Buying Rate:
      TT Buying
      Bills Buying
      Currency Notes
      Forex Prepaid Card
      Demand Draft

    Bank Selling Rate:
      TT Selling
      Bills Selling
      Currency Notes
      Forex Prepaid Card
      Demand Draft

    We locate the currency row and read
    the numeric values from that row.

    TT Selling is the first value
    under Bank Selling Rate.

    Because the webpage can include
    null / blank Demand Draft fields,
    we parse the row carefully rather
    than assuming every field is numeric.
    """


    pattern = re.compile(

        rf"(?:{name_pattern})"
        rf"\s*\({currency}\)"
        r"\s+"
        r"(.{0,450})",

        re.IGNORECASE

    )


    match = pattern.search(
        text
    )


    if not match:

        print(
            "ICICI missing currency:",
            currency
        )

        return None


    row = match.group(1)


    # Stop before next known currency
    # if possible.

    stop_patterns = [

        r"Euro\s*\(EUR\)",

        r"Great Britain Pound\s*\(GBP\)",

        r"Australian Dollar\s*\(AUD\)",

        r"Canadian Dollar\s*\(CAD\)",

        r"Singapore Dollar\s*\(SGD\)",

        r"United States Dollar\s*\(USD\)",

    ]


    for stop in stop_patterns:

        stop_match = re.search(

            stop,

            row,

            re.IGNORECASE

        )


        if stop_match:

            row = row[
                :stop_match.start()
            ]


    tokens = re.findall(

        r"\bnull\b"
        r"|"
        r"\b\d+(?:\.\d+)?\b",

        row,

        re.IGNORECASE

    )


    print(
        "ICICI",
        currency,
        "raw values:",
        tokens[:12]
    )


    """
    Expected logical order:

    0 TT Buying
    1 Bills Buying
    2 Currency Notes Buy
    3 Forex Prepaid Buy
    4 Demand Draft Buy (often null)

    5 TT Selling
    6 Bills Selling
    7 Currency Notes Sell
    8 Forex Prepaid Sell
    9 Demand Draft Sell
    """


    if len(tokens) < 6:

        print(
            "ICICI insufficient values:",
            currency
        )

        return None


    tt_sell_token = (
        tokens[5]
    )


    if (
        tt_sell_token.lower()
        == "null"
    ):

        print(
            "ICICI TT Sell is null:",
            currency
        )

        return None


    try:

        tt_sell = float(
            tt_sell_token
        )

    except ValueError:

        return None


    return tt_sell


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
        "ICICI BANK AGENT"
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
        "ICICI source date:",
        source_date
    )


    print(
        "ICICI source time:",
        source_time
    )


    if not source_date:

        raise RuntimeError(

            "ICICI rate-card date "
            "could not be verified."

        )


    if determine_status(
        source_date
    ) != "current":

        raise RuntimeError(

            "ICICI rate page is not current. "
            f"Source date: {source_date}"

        )


    records = []


    for currency in CURRENCIES:


        rate = extract_currency_rate(

            text,

            currency

        )


        if rate is None:

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

            "ICICI",

            currency,

            rate,

            record["status"]

        )


    if not records:

        raise RuntimeError(

            "ICICI Agent returned no rates."

        )


    print(

        "ICICI Agent completed:",

        len(records),

        "rates"

    )


    return records
