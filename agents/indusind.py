import html
import re
import requests

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


BANK_NAME = "IndusInd Bank"
SOURCE_URL = "https://www.indusind.bank.in/in/en/personal/rates.html"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def html_to_text(page):
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", page, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()

def extract_source_date(text):
    m = re.search(r"As\s+on\s+(\d{1,2})[-/](\d{1,2})[-/](20\d{2})", text, re.I)
    if m:
        d, mo, y = map(int, m.groups())
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    m = re.search(r"Last\s+Updated\s+on\s*:\s*(20\d{2})-(\d{1,2})-(\d{1,2})", text, re.I)
    if m:
        y, mo, d = map(int, m.groups())
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    return None

def extract_source_time(text):
    m = re.search(r"Last\s+Updated\s+on\s*:\s*20\d{2}-\d{1,2}-\d{1,2}\s+(\d{1,2}:\d{2}:\d{2})", text, re.I)
    return m.group(1) if m else None

def extract_rate(text, currency):
    m = re.search(
        rf"\b{currency}\b\s+[A-Z][A-Z\s\.\-/&]+?\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)",
        text,
        re.I
    )
    return float(m.group(2)) if m else None

def collect():
    print("\n==============================")
    print("INDUSIND BANK AGENT")
    print("==============================")
    print("IndusInd Agent: downloading official rates page")
    print(SOURCE_URL)

    r = requests.get(SOURCE_URL, headers=HEADERS, timeout=60)
    r.raise_for_status()
    text = html_to_text(r.text)

    print("HTTP:", r.status_code)
    print("Characters:", len(r.text))

    if "TT Buy" not in text or "TT Sell" not in text:
        raise RuntimeError("IndusInd TT Buy / TT Sell headers not found.")

    source_date = extract_source_date(text)
    source_time = extract_source_time(text)
    print("IndusInd source date:", source_date)
    print("IndusInd source time:", source_time)

    if not source_date:
        raise RuntimeError("IndusInd source date could not be verified.")
    if status_from_date(source_date) != "current":
        raise RuntimeError(f"IndusInd rate page is not current. Source date: {source_date}")

    records = []
    for currency in CURRENCIES:
        rate = extract_rate(text, currency)
        if rate is None:
            print("IndusInd missing:", currency)
            continue
        if not reasonable(currency, rate):
            print("IndusInd rejected suspicious rate:", currency, rate)
            continue
        rec = build_record(BANK_NAME, currency, rate, SOURCE_URL, source_date, source_time)
        records.append(rec)
        print("IndusInd", currency, rate, rec["status"])

    missing = set(CURRENCIES) - {r["currency"] for r in records}
    if missing:
        raise RuntimeError("IndusInd Agent missing currencies: " + ", ".join(sorted(missing)))

    print("IndusInd Agent completed:", len(records), "rates")
    return records
