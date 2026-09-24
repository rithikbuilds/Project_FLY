import io
import re
import requests
import pdfplumber

from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

RATE_TYPE = "TT Selling / Outward Remittance"

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

BANK_NAME = "Union Bank of India"

SOURCE_URL = (
    "https://www.unionbankofindia.bank.in/"
    "pdf/foreign-exchange-card-rates-applicable-to-various-forex-transactions.pdf"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def now_ist():
    return datetime.now(IST)


def reasonable(currency, rate):
    low, high = RANGES[currency]
    return low <= float(rate) <= high


def extract_text(pdf_bytes):
    parts = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""

            print(
                f"Union PDF page {page_number}: "
                f"{len(text)} characters"
            )

            parts.append(text)

    return "\n".join(parts)


def extract_source_date(text):
    patterns = [
        # Standard Union Bank format
        r"Card\s+Rates\s+of\s+Currencies\s+As\s+On\s+"
        r"(\d{1,2})[-/]([A-Za-z]{3})[-/](20\d{2})",

        # Numeric date fallback
        r"Card\s+Rates\s+of\s+Currencies\s+As\s+On\s+"
        r"(\d{1,2})[-/](\d{1,2})[-/](20\d{2})",
    ]

    for pattern in patterns:

        m = re.search(pattern, text, re.IGNORECASE)

        if not m:
            continue

        d, month, year = m.groups()

        try:
            if month.isdigit():
                dt = datetime.strptime(
                    f"{d}-{month}-{year}",
                    "%d-%m-%Y",
                )
            else:
                dt = datetime.strptime(
                    f"{d}-{month}-{year}",
                    "%d-%b-%Y",
                )

            return dt.strftime("%Y-%m-%d")

        except ValueError:
            continue

    return None


def extract_source_time(text):
    patterns = [
        r"Card\s+Rates\s+of\s+Currencies\s+As\s+On\s+"
        r"\d{1,2}[-/][A-Za-z0-9]+[-/]20\d{2}\s+"
        r"(\d{1,2}:\d{2}(?::\d{2})?)",

        r"As\s+On\s+.*?"
        r"(\d{1,2}:\d{2}(?::\d{2})?)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)

        if m:
            return m.group(1)

    return None


def extract_rate(text, currency):
    """
    Extract the TT Selling rate from the Union Bank table.

    Expected table structure:

    Currency
    TT Selling
    Bill Selling
    TT Buying
    ...

    Example:
    USD 95.55 95.57 94.89 ...
    """

    pattern = (
        rf"(?m)^\s*{re.escape(currency)}\s+"
        rf"(\d+(?:\.\d+)?)\s+"
    )

    m = re.search(pattern, text)

    if not m:
        return None

    return float(m.group(1))


def status_from_date(source_date):
    if not source_date:
        return "date_unverified"

    today = now_ist().strftime("%Y-%m-%d")

    if source_date == today:
        return "current"

    return "stale"


def build_record(
    bank,
    currency,
    rate,
    source_url,
    source_date,
    source_time,
):
    fetched = now_ist()

    return {
        "date": fetched.strftime("%Y-%m-%d"),
        "time": fetched.strftime("%H:%M:%S"),
        "bank": bank,
        "currency": currency,
        "rate_type": RATE_TYPE,
        "bank_rate": float(rate),
        "market_rate": None,
        "markup_percent": None,
        "source_url": source_url,
        "source_date": source_date,
        "source_time": source_time,
        "fetched_at": fetched.isoformat(),
        "status": status_from_date(source_date),
    }


def collect():

    print()
    print("==============================")
    print("UNION BANK OF INDIA AGENT")
    print("==============================")

    # Cache-busting query parameter.
    # The official URL stays the same, but this prevents
    # intermediate caching from repeatedly returning an old PDF.
    cache_buster = int(datetime.now().timestamp())

    request_url = f"{SOURCE_URL}?_={cache_buster}"

    print("Union Agent: downloading official Treasury card-rate PDF")
    print("Source:", SOURCE_URL)
    print("Request:", request_url)

    response = requests.get(
        request_url,
        headers=HEADERS,
        timeout=60,
    )

    response.raise_for_status()

    content = response.content

    print("HTTP:", response.status_code)
    print("Bytes:", len(content))
    print(
        "Content-Type:",
        response.headers.get("Content-Type"),
    )

    if not content.startswith(b"%PDF"):
        raise RuntimeError(
            "Union Bank source did not return a PDF."
        )

    text = extract_text(content)

    print()
    print("Union PDF text preview:")
    print(text[:2000])
    print()

    if "TT Selling" not in text:
        raise RuntimeError(
            "Union Bank TT Selling header not found."
        )

    if "TT Buying" not in text:
        raise RuntimeError(
            "Union Bank TT Buying header not found."
        )

    source_date = extract_source_date(text)
    source_time = extract_source_time(text)

    print("Union source date:", source_date)
    print("Union source time:", source_time)

    if not source_date:
        raise RuntimeError(
            "Union Bank source date could not be verified."
        )

    status = status_from_date(source_date)

    print("Union source status:", status)

    # IMPORTANT:
    # Do not fail just because Union's PDF is missing a time.
    # Time is optional.
    #
    # We DO continue to reject an old/stale card-rate PDF.
    if status != "current":
        raise RuntimeError(
            "Union Bank rate card is not current. "
            f"Source date: {source_date}"
        )

    records = []

    for currency in CURRENCIES:

        rate = extract_rate(text, currency)

        if rate is None:
            print(
                "Union missing:",
                currency,
            )
            continue

        if not reasonable(currency, rate):
            print(
                "Union rejected suspicious rate:",
                currency,
                rate,
            )
            continue

        record = build_record(
            BANK_NAME,
            currency,
            rate,
            SOURCE_URL,
            source_date,
            source_time,
        )

        records.append(record)

        print(
            f"Union {currency}: "
            f"{rate} | "
            f"{record['status']}"
        )

    found = {
        record["currency"]
        for record in records
    }

    missing = set(CURRENCIES) - found

    if missing:
        raise RuntimeError(
            "Union Bank Agent missing currencies: "
            + ", ".join(sorted(missing))
        )

    print()
    print(
        "Union Bank Agent completed:",
        len(records),
        "rates",
    )

    return records
