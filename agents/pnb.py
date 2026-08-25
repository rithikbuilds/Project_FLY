import io
import re
import requests
import pdfplumber

from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
RATE_TYPE = "TT Selling / Outward Remittance"

CURRENCIES = ["USD","CAD","AUD","GBP","EUR","SGD","AED","NZD"]

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

def now_ist():
    return datetime.now(IST)

def status_from_date(source_date):
    if not source_date:
        return "date_unverified"
    return "current" if source_date == now_ist().strftime("%Y-%m-%d") else "stale"

def reasonable(currency, rate):
    low, high = RANGES[currency]
    return low <= float(rate) <= high

def build_record(bank, currency, rate, source_url, source_date, source_time):
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


BANK_NAME = "Punjab National Bank"
SOURCE_URL = "https://www.pnb.bank.in/downloadprocess.aspx?fid=A+rrvZeJc+PIaxfEqVTIQQ%3D%3D"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/pdf,*/*",
}

def extract_text(pdf_bytes):
    parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)

def extract_source_date(text):
    m = re.search(r"Card\s+Rate\s+dated\s+(\d{1,2})/(\d{1,2})/(20\d{2})", text, re.I)
    if not m:
        return None
    d, mo, y = map(int, m.groups())
    return datetime(y, mo, d).strftime("%Y-%m-%d")

def extract_source_time(text):
    m = re.search(r"Card\s+Rate\s+dated\s+\d{1,2}/\d{1,2}/20\d{2}\s+(\d{1,2}:\d{2}\s*[AP]M)", text, re.I)
    return m.group(1).upper() if m else None

def extract_rate(text, currency):
    m = re.search(
        rf"(?m)^\s*\d+\s+{re.escape(currency)}\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)",
        text
    )
    return float(m.group(2)) if m else None

def collect():
    print("\n==============================")
    print("PUNJAB NATIONAL BANK AGENT")
    print("==============================")
    print("PNB Agent: downloading official Treasury card-rate PDF")
    print(SOURCE_URL)

    r = requests.get(SOURCE_URL, headers=HEADERS, timeout=60)
    r.raise_for_status()
    content = r.content
    print("HTTP:", r.status_code)
    print("Bytes:", len(content))

    if not content.startswith(b"%PDF"):
        raise RuntimeError("PNB source did not return a PDF.")

    text = extract_text(content)
    if "TT BUY" not in text.upper() or "TT SELL" not in text.upper():
        raise RuntimeError("PNB TT BUY / TT SELL headers not found.")

    source_date = extract_source_date(text)
    source_time = extract_source_time(text)
    print("PNB source date:", source_date)
    print("PNB source time:", source_time)

    if not source_date:
        raise RuntimeError("PNB card-rate date could not be verified.")
    if status_from_date(source_date) != "current":
        raise RuntimeError(
            f"PNB card-rate PDF is not current. Source date: {source_date}. "
            "PNB may have rotated the daily PDF link."
        )

    records = []
    for currency in CURRENCIES:
        rate = extract_rate(text, currency)
        if rate is None:
            print("PNB missing:", currency)
            continue
        if not reasonable(currency, rate):
            print("PNB rejected suspicious rate:", currency, rate)
            continue
        rec = build_record(BANK_NAME, currency, rate, SOURCE_URL, source_date, source_time)
        records.append(rec)
        print("PNB", currency, rate, rec["status"])

    missing = set(CURRENCIES) - {r["currency"] for r in records}
    if missing:
        raise RuntimeError("PNB Agent missing currencies: " + ", ".join(sorted(missing)))

    print("PNB Agent completed:", len(records), "rates")
    return records
