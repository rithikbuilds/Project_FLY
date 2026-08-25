import html
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


BANK_NAME = "Deutsche Bank India"
SOURCE_URL = "https://forms.deutsche.bank.in/DBForms/private/ViewRates"

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

RATE_TYPE = "TT Selling / Outward Remittance"

RANGES = {
    "USD": (70, 130),
    "CAD": (40, 100),
    "AUD": (40, 100),
    "GBP": (90, 180),
    "EUR": (80, 160),
    "SGD": (45, 110),
    "AED": (15, 40),
    "NZD": (30, 90),
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def now_ist():
    return datetime.now(IST)


def html_to_text(page):
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", page, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_source_date(text):
    month_names = (
        "January|February|March|April|May|June|"
        "July|August|September|October|November|December"
    )

    match = re.search(
        rf"\b({month_names})\s+(\d{{1,2}}),\s+(20\d{{2}})\b",
        text,
        re.I,
    )

    if not match:
        return None

    month, day, year = match.groups()

    return datetime.strptime(
        f"{month} {day} {year}",
        "%B %d %Y",
    ).strftime("%Y-%m-%d")


def is_current(source_date):
    if not source_date:
        return False

    return source_date == now_ist().strftime("%Y-%m-%d")


def reasonable(currency, rate):
    low, high = RANGES[currency]
    return low <= float(rate) <= high


def extract_rate(text, currency):
    """
    Deutsche Bank's official table is:

        Currency | TT Selling | TT Buying

    We use the FIRST numeric value after the currency code.
    """

    match = re.search(
        rf"\b{re.escape(currency)}\b\s+"
        r"(\d+(?:\.\d+)?)\s+"
        r"(\d+(?:\.\d+)?)\b",
        text,
        re.I,
    )

    if not match:
        return None

    tt_selling = float(match.group(1))
    tt_buying = float(match.group(2))

    print(
        f"Deutsche {currency} | "
        f"TT Selling: {tt_selling} | "
        f"TT Buying: {tt_buying}"
    )

    return tt_selling


def build_record(currency, rate, source_date):
    fetched = now_ist()

    return {
        "date": fetched.strftime("%Y-%m-%d"),
        "time": fetched.strftime("%H:%M:%S"),
        "bank": BANK_NAME,
        "currency": currency,
        "rate_type": RATE_TYPE,
        "bank_rate": float(rate),
        "market_rate": None,
        "markup_percent": None,
        "source_url": SOURCE_URL,
        "source_date": source_date,
        "source_time": None,
        "fetched_at": fetched.isoformat(),
        "status": "current" if is_current(source_date) else "stale",
    }


def collect():

    print()
    print("==============================")
    print("DEUTSCHE BANK INDIA AGENT")
    print("==============================")

    print("Deutsche Agent: downloading official Foreign Exchange Rates page")
    print(SOURCE_URL)

    response = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=60,
        allow_redirects=True,
    )

    print("HTTP:", response.status_code)
    print("Content-Type:", response.headers.get("Content-Type"))
    print("Characters:", len(response.text))

    response.raise_for_status()

    if len(response.text) < 500:
        raise RuntimeError(
            "Deutsche Bank returned an unexpectedly small response."
        )

    text = html_to_text(response.text)

    if "Foreign Exchange Rates" not in text:
        raise RuntimeError(
            "Deutsche Bank Foreign Exchange Rates heading was not found."
        )

    if not re.search(r"\bTT\s+Selling\b", text, re.I):
        raise RuntimeError(
            "Deutsche Bank TT Selling header was not found."
        )

    if not re.search(r"\bTT\s+Buying\b", text, re.I):
        raise RuntimeError(
            "Deutsche Bank TT Buying header was not found."
        )

    print("Deutsche TT Selling / TT Buying headers verified.")

    source_date = parse_source_date(text)

    print("Deutsche source date:", source_date)

    if not source_date:
        raise RuntimeError(
            "Deutsche Bank source date could not be verified."
        )

    if not is_current(source_date):
        raise RuntimeError(
            "Deutsche Bank rate page is not current. "
            f"Source date: {source_date}"
        )

    records = []

    for currency in CURRENCIES:

        rate = extract_rate(
            text,
            currency,
        )

        if rate is None:
            print(
                "Deutsche missing:",
                currency,
            )
            continue

        if not reasonable(
            currency,
            rate,
        ):
            print(
                "Deutsche rejected suspicious rate:",
                currency,
                rate,
            )
            continue

        record = build_record(
            currency,
            rate,
            source_date,
        )

        records.append(
            record
        )

        print(
            "Deutsche",
            currency,
            rate,
            "| source:",
            source_date,
            "| current",
        )

    found = {
        record["currency"]
        for record in records
    }

    missing = set(CURRENCIES) - found

    if missing:
        raise RuntimeError(
            "Deutsche Bank Agent missing currencies: "
            + ", ".join(sorted(missing))
        )

    if len(records) != 8:
        raise RuntimeError(
            "Deutsche Bank expected 8 rates "
            f"but extracted {len(records)}."
        )

    print(
        "Deutsche Bank India Agent completed:",
        len(records),
        "rates",
    )

    return records
