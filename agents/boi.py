import html
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


BANK_NAME = "Bank of India"
SOURCE_URL = "https://bankofindia.bank.in/forexcard-rate"

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
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://bankofindia.bank.in/",
}


def now_ist():
    return datetime.now(IST)


def html_to_text(page):
    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        page,
        flags=re.I | re.S,
    )
    text = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_source_date(text):
    patterns = [
        r"\bDate\s*:\s*(\d{1,2})/(\d{1,2})/(20\d{2})\b",
        r"\bDate\s*:\s*(\d{1,2})-(\d{1,2})-(20\d{2})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            day, month, year = map(int, match.groups())
            return datetime(year, month, day).strftime("%Y-%m-%d")

    return None


def is_current(source_date):
    if not source_date:
        return False
    return source_date == now_ist().strftime("%Y-%m-%d")


def reasonable(currency, rate):
    low, high = RANGES[currency]
    return low <= float(rate) <= high


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


def extract_rate_from_text(text, currency):
    """
    BOI publishes rows in this order:

        Currency | TTS | TTB | TCS | TCB

    We need TTS, therefore the FIRST numeric value after the
    currency code is the outward-remittance TT Selling rate.
    """

    pattern = re.compile(
        rf"\b{re.escape(currency)}\b\s+"
        r"(\d+(?:\.\d+)?)\s+"
        r"(\d+(?:\.\d+)?)\s+"
        r"(\d+(?:\.\d+)?)\s+"
        r"(\d+(?:\.\d+)?)\b",
        re.I,
    )

    match = pattern.search(text)

    if not match:
        return None

    tts = float(match.group(1))
    ttb = float(match.group(2))
    tcs = float(match.group(3))
    tcb = float(match.group(4))

    print(
        f"BOI {currency} | "
        f"TTS: {tts} | "
        f"TTB: {ttb} | "
        f"TCS: {tcs} | "
        f"TCB: {tcb}"
    )

    return tts


def collect():

    print()
    print("==============================")
    print("BANK OF INDIA AGENT")
    print("==============================")

    print("BOI Agent: downloading official Forex Card Rate page")
    print(SOURCE_URL)

    session = requests.Session()
    session.headers.update(HEADERS)

    # Visiting the homepage first can help when the bank requires
    # a normal browser-style session before opening the rate page.
    try:
        session.get(
            "https://bankofindia.bank.in/",
            timeout=30,
        )
    except requests.RequestException:
        pass

    response = session.get(
        SOURCE_URL,
        timeout=60,
        allow_redirects=True,
    )

    print("HTTP:", response.status_code)
    print("Content-Type:", response.headers.get("Content-Type"))
    print("Characters:", len(response.text))

    if response.status_code == 403:
        raise RuntimeError(
            "Bank of India blocked the automated request with HTTP 403."
        )

    response.raise_for_status()

    if len(response.text) < 500:
        raise RuntimeError(
            "Bank of India returned an unexpectedly small response."
        )

    text = html_to_text(response.text)

    # Validate that we are parsing the intended BOI rate card,
    # not another page returned by a redirect/security layer.
    if "Forex Card Rate" not in text:
        raise RuntimeError(
            "Bank of India Forex Card Rate heading was not found."
        )

    # The BOI table uses TTS / TTB / TCS / TCB.
    for header in ["TTS", "TTB", "TCS", "TCB"]:
        if not re.search(rf"\b{header}\b", text, re.I):
            raise RuntimeError(
                f"Bank of India {header} header was not found."
            )

    print("BOI TTS / TTB / TCS / TCB headers verified.")

    source_date = parse_source_date(text)

    print("BOI source date:", source_date)

    if not source_date:
        raise RuntimeError(
            "Bank of India source date could not be verified."
        )

    if not is_current(source_date):
        raise RuntimeError(
            "Bank of India rate page is not current. "
            f"Source date: {source_date}"
        )

    records = []

    for currency in CURRENCIES:

        rate = extract_rate_from_text(text, currency)

        if rate is None:
            print("BOI missing:", currency)
            continue

        if not reasonable(currency, rate):
            print(
                "BOI rejected suspicious rate:",
                currency,
                rate,
            )
            continue

        record = build_record(
            currency,
            rate,
            source_date,
        )

        records.append(record)

        print(
            "BOI",
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
            "Bank of India Agent missing currencies: "
            + ", ".join(sorted(missing))
        )

    if len(records) != 8:
        raise RuntimeError(
            f"Bank of India expected 8 rates but extracted {len(records)}."
        )

    print(
        "Bank of India Agent completed:",
        len(records),
        "rates",
    )

    return records
