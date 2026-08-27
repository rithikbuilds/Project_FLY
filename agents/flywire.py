import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

IST = ZoneInfo("Asia/Kolkata")
PAY_URL = "https://pay.flywire.com/"
DEBUG_DIR = Path(__file__).resolve().parent.parent / "data" / "flywire_debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class QuoteConfig:
    currency: str
    institution_country: str
    institution: str
    amount: int
    payment_country: str = "India"


USD_5000 = QuoteConfig(
    currency="USD",
    institution_country="United States",
    institution="Harvard University",
    amount=5000,
)


def now_ist():
    return datetime.now(IST)


def parse_inr(text: str) -> float:
    match = re.search(r"₹\s*([\d,]+(?:\.\d{1,2})?)", text)
    if not match:
        raise RuntimeError(f"Could not find INR amount in text: {text[:500]}")
    return float(match.group(1).replace(",", ""))


def click_text(page, text: str, timeout=12000):
    candidates = [
        page.get_by_role("button", name=re.compile(re.escape(text), re.I)),
        page.get_by_text(text, exact=True),
        page.get_by_text(re.compile(rf"^\s*{re.escape(text)}\s*$", re.I)),
    ]
    last_error = None
    for locator in candidates:
        try:
            if locator.count() > 0:
                locator.first.click(timeout=timeout)
                return
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f'Could not click "{text}". Last error: {last_error}')


def select_or_type(page, label_pattern: str, value: str, timeout=12000):
    label_re = re.compile(label_pattern, re.I)

    try:
        control = page.get_by_label(label_re)
        if control.count() > 0:
            first = control.first
            tag = first.evaluate("el => el.tagName.toLowerCase()")
            if tag == "select":
                try:
                    first.select_option(label=value, timeout=timeout)
                except Exception:
                    first.select_option(value=value, timeout=timeout)
                return
            first.click(timeout=timeout)
            try:
                first.fill(value, timeout=timeout)
            except Exception:
                pass
            option = page.get_by_text(value, exact=True)
            if option.count() > 0:
                option.first.click(timeout=timeout)
                return
    except Exception:
        pass

    try:
        combos = page.get_by_role("combobox")
        for i in range(combos.count()):
            combo = combos.nth(i)
            aria = " ".join(filter(None, [
                combo.get_attribute("aria-label"),
                combo.get_attribute("placeholder"),
                combo.get_attribute("name"),
            ]))
            if re.search(label_pattern, aria or "", re.I):
                combo.click(timeout=timeout)
                try:
                    combo.fill(value, timeout=timeout)
                except Exception:
                    pass
                page.get_by_text(value, exact=True).first.click(timeout=timeout)
                return
    except Exception:
        pass

    try:
        label = page.get_by_text(label_re).first
        parent = label.locator("xpath=..")
        for _ in range(4):
            native = parent.locator("select")
            if native.count():
                try:
                    native.first.select_option(label=value)
                except Exception:
                    native.first.select_option(value=value)
                return
            fields = parent.locator("input, [role='combobox'], button")
            if fields.count():
                field = fields.first
                field.click()
                try:
                    field.fill(value)
                except Exception:
                    pass
                page.get_by_text(value, exact=True).first.click()
                return
            parent = parent.locator("xpath=..")
    except Exception:
        pass

    raise RuntimeError(f'Could not select "{value}" for control matching "{label_pattern}".')


def fill_amount(page, amount: int):
    try:
        field = page.get_by_label(re.compile(r"Amount", re.I))
        if field.count():
            field.first.fill(str(amount))
            return
    except Exception:
        pass

    try:
        field = page.locator("input[type='number']")
        if field.count():
            field.first.fill(str(amount))
            return
    except Exception:
        pass

    try:
        receives = page.get_by_text(re.compile(r"receives", re.I)).first
        parent = receives.locator("xpath=..")
        for _ in range(5):
            inputs = parent.locator("input")
            if inputs.count():
                inputs.first.fill(str(amount))
                return
            parent = parent.locator("xpath=..")
    except Exception:
        pass

    raise RuntimeError("Could not find destination amount input.")


def extract_offline_bank_transfer_quote(page) -> float:
    label = page.get_by_text(re.compile(r"Offline bank transfer", re.I)).first
    if label.count() == 0:
        raise RuntimeError("Offline bank transfer payment method was not found.")

    node = label
    for _ in range(8):
        text = node.inner_text(timeout=5000)
        if "₹" in text:
            return parse_inr(text)
        node = node.locator("xpath=..")

    page_text = page.locator("body").inner_text()
    method_pos = page_text.lower().find("offline bank transfer")
    if method_pos >= 0:
        nearby = page_text[method_pos: method_pos + 1000]
        return parse_inr(nearby)

    raise RuntimeError("Offline bank transfer was found, but its INR quote could not be extracted.")


def save_debug(page, prefix="flywire_failure"):
    stamp = now_ist().strftime("%Y%m%d_%H%M%S")
    screenshot = DEBUG_DIR / f"{prefix}_{stamp}.png"
    html_file = DEBUG_DIR / f"{prefix}_{stamp}.html"
    try:
        page.screenshot(path=str(screenshot), full_page=True)
    except Exception:
        pass
    try:
        html_file.write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    print("Debug screenshot:", screenshot)
    print("Debug HTML:", html_file)


def collect_quote(config: QuoteConfig = USD_5000, headless=True):
    print("\n================================")
    print("FLYWIRE QUOTE AGENT")
    print("================================")
    print("Institution country:", config.institution_country)
    print("Institution:", config.institution)
    print("Destination currency:", config.currency)
    print("Destination amount:", config.amount)
    print("Payment origin:", config.payment_country)
    print("Route: Full Loan Financing -> Bank -> SBI -> Offline bank transfer")

    fetched_at = now_ist()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        context = browser.new_context(
            locale="en-US",
            timezone_id="Asia/Kolkata",
            viewport={"width": 1440, "height": 1100},
        )
        page = context.new_page()
        page.set_default_timeout(15000)

        try:
            print("Opening:", PAY_URL)
            page.goto(PAY_URL, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(2500)

            select_or_type(page, r"country|region.*institution|institution.*country|country/region", config.institution_country)
            page.wait_for_timeout(800)
            select_or_type(page, r"institution", config.institution)
            page.wait_for_timeout(800)
            click_text(page, "Continue")
            page.wait_for_timeout(1800)

            fill_amount(page, config.amount)
            select_or_type(page, r"payment.*come from|country|region|bank account|card|wallet", config.payment_country)
            page.wait_for_timeout(700)
            try:
                click_text(page, "Next")
            except Exception:
                click_text(page, "Continue")
            page.wait_for_timeout(1800)

            click_text(page, "Full Loan Financing")
            page.wait_for_timeout(900)
            click_text(page, "Bank")
            page.wait_for_timeout(900)
            click_text(page, "I have taken a loan from SBI")
            page.wait_for_timeout(500)
            try:
                click_text(page, "Continue")
            except Exception:
                pass
            page.wait_for_timeout(1800)

            inr_quote = extract_offline_bank_transfer_quote(page)
            effective_rate = round(inr_quote / config.amount, 4)

            record = {
                "timestamp": fetched_at.isoformat(),
                "currency": config.currency,
                "amount": config.amount,
                "inr_quote": inr_quote,
                "effective_rate": effective_rate,
                "institution_country": config.institution_country,
                "institution": config.institution,
                "payment_country": config.payment_country,
                "funding_type": "Full Loan Financing",
                "loan_provider_type": "Bank",
                "loan_provider": "SBI",
                "payment_method": "Offline bank transfer",
                "source_url": PAY_URL,
                "status": "current",
            }

            print("\nFLYWIRE QUOTE CAPTURED")
            print("INR Quote:", inr_quote)
            print("Effective Rate:", effective_rate)
            print("Timestamp:", fetched_at.isoformat())
            return record

        except Exception as exc:
            print("\nFLYWIRE AGENT FAILED:")
            print(str(exc))
            save_debug(page)
            raise
        finally:
            context.close()
            browser.close()


def collect_usd_5000(headless=True):
    return collect_quote(USD_5000, headless=headless)


if __name__ == "__main__":
    collect_usd_5000()
