import io
import re
import requests
import pdfplumber

from datetime import datetime
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")

BANK_NAME = "SBI"

RATE_TYPE = "TT Selling / Outward Remittance"

SOURCE_URL = (
    "https://sbi.co.in/documents/"
    "16012/1400784/FOREX_CARD_RATES.pdf"
)


CURRENCIES = {
    "USD": "USD/INR",
    "CAD": "CAD/INR",
    "AUD": "AUD/INR",
    "GBP": "GBP/INR",
    "EUR": "EUR/INR",
    "SGD": "SGD/INR",
    "AED": "AED/INR",
    "NZD": "NZD/INR",
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/129 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
}


def now_ist():
    return datetime.now(IST)


def clean_text(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "")
    ).strip()


def download_pdf():

    print("SBI Agent: downloading rate card")
    print(SOURCE_URL)

    response = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=60
    )

    response.raise_for_status()

    content = response.content

    if not content.startswith(b"%PDF"):
        raise RuntimeError(
            "SBI source did not return a valid PDF."
        )

    print(
        "SBI Agent: PDF downloaded successfully"
    )

    return content


def extract_text(pdf_bytes):

    parts = []

    with pdfplumber.open(
        io.BytesIO(pdf_bytes)
    ) as pdf:

        for page in pdf.pages:

            parts.append(
                page.extract_text() or ""
            )

    return "\n".join(parts)


def extract_source_date(text):

    match = re.search(
        r"\b(\d{1,2})[-/]"
        r"(\d{1,2})[-/]"
        r"(20\d{2})\b",
        text
    )

    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))

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

        return None


def extract_source_time(text):

    match = re.search(
        r"\bTIME\s*[:\-]?\s*"
        r"(\d{1,2}:\d{2}"
        r"(?::\d{2})?\s*[AP]M)",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    return clean_text(
        match.group(1)
    )


def determine_status(source_date):

    if not source_date:
        return "date_unverified"

    today = now_ist().strftime(
        "%Y-%m-%d"
    )

    if source_date == today:
        return "current"

    return "stale"


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
        )
    }


def collect():

    print()
    print("==============================")
    print("SBI AGENT")
    print("==============================")

    pdf_bytes = download_pdf()

    text = extract_text(
        pdf_bytes
    )

    source_date = extract_source_date(
        text
    )

    source_time = extract_source_time(
        text
    )

    print(
        "Source date:",
        source_date
    )

    print(
        "Source time:",
        source_time
    )

    if not source_date:
        raise RuntimeError(
            "SBI rate-card date could not "
            "be verified."
        )

    records = []

    for currency, pair in CURRENCIES.items():

        rate_found = None

        for raw_line in text.splitlines():

            if pair not in raw_line:
                continue

            line = clean_text(
                raw_line
            )

            position = line.find(
                pair
            )

            after_pair = line[
                position + len(pair):
            ]

            numbers = re.findall(
                r"\d+(?:\.\d+)?",
                after_pair
            )

            if len(numbers) < 2:
                continue

            # SBI current rate-card structure:
            #
            # First numeric rate  = TT Buy
            # Second numeric rate = TT Sell
            #
            # We need TT Sell for
            # outward remittance.

            rate_found = float(
                numbers[1]
            )

            break

        if rate_found is None:

            print(
                currency,
                "NOT FOUND"
            )

            continue

        record = build_record(
            currency,
            rate_found,
            source_date,
            source_time
        )

        records.append(record)

        print(
            currency,
            rate_found,
            record["status"]
        )

    if not records:
        raise RuntimeError(
            "SBI Agent returned no rates."
        )

    print(
        "SBI Agent completed:",
        len(records),
        "rates"
    )

    return records
