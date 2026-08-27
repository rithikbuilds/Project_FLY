import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright


IST = ZoneInfo("Asia/Kolkata")
PAY_URL = "https://pay.flywire.com/"

ROOT_DIR = Path(__file__).resolve().parent.parent
DEBUG_DIR = ROOT_DIR / "data" / "flywire_debug"
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


def save_debug(page, prefix="flywire_failure"):
    stamp = now_ist().strftime("%Y%m%d_%H%M%S")

    screenshot = DEBUG_DIR / f"{prefix}_{stamp}.png"
    html_file = DEBUG_DIR / f"{prefix}_{stamp}.html"

    try:
        page.screenshot(
            path=str(screenshot),
            full_page=True,
        )
    except Exception:
        pass

    try:
        html_file.write_text(
            page.content(),
            encoding="utf-8",
        )
    except Exception:
        pass

    print("Debug screenshot:", screenshot)
    print("Debug HTML:", html_file)


def dismiss_privacy_popup(page):
    """
    The privacy popup is not always shown, but dismiss it when possible
    so it cannot interfere with later controls.
    """

    possible_buttons = [
        "Opt Out",
        "Accept",
        "Accept All",
        "Close",
    ]

    for text in possible_buttons:
        try:
            locator = page.get_by_text(
                text,
                exact=True,
            )

            if locator.count() > 0:
                for i in range(locator.count()):
                    item = locator.nth(i)

                    if item.is_visible():
                        item.click(timeout=3000)
                        print("Privacy popup handled.")
                        page.wait_for_timeout(500)
                        return
        except Exception:
            pass


def get_visible_inputs(page):
    visible = []

    inputs = page.locator("input")

    for i in range(inputs.count()):
        field = inputs.nth(i)

        try:
            if field.is_visible():
                visible.append(field)
        except Exception:
            pass

    return visible


def choose_country(page, country):
    print("Selecting institution country:", country)

    page.wait_for_timeout(1000)

    inputs = get_visible_inputs(page)

    if not inputs:
        raise RuntimeError(
            "No visible input was found for institution country."
        )

    # On Flywire's opening screen the first visible input is
    # the institution-country search field.
    country_input = inputs[0]

    country_input.click()
    country_input.fill(country)

    print("Country search entered:", country)

    page.wait_for_timeout(1200)

    # IMPORTANT:
    # Do not type again.
    # The previous version typed the country twice.
    exact_results = page.get_by_text(
        re.compile(
            rf"^\s*{re.escape(country)}\s*$",
            re.I,
        )
    )

    clicked = False

    for i in range(exact_results.count()):
        result = exact_results.nth(i)

        try:
            if not result.is_visible():
                continue

            # Don't click the text inside the input itself.
            tag = result.evaluate(
                "el => el.tagName.toLowerCase()"
            )

            if tag == "input":
                continue

            result.click(timeout=10000)
            clicked = True
            break

        except Exception:
            continue

    if not clicked:
        # The first dropdown result can also be exposed as an option.
        options = page.get_by_role(
            "option",
            name=re.compile(
                rf"^\s*{re.escape(country)}\s*$",
                re.I,
            ),
        )

        for i in range(options.count()):
            option = options.nth(i)

            try:
                if option.is_visible():
                    option.click(timeout=10000)
                    clicked = True
                    break
            except Exception:
                continue

    if not clicked:
        raise RuntimeError(
            f'Country result "{country}" appeared to be unavailable.'
        )

    print("Institution country selected:", country)

    # Flywire loads/enables the institution field after this.
    page.wait_for_timeout(1800)


def choose_institution(page, institution):
    print("Selecting institution:", institution)

    page.wait_for_timeout(1000)

    inputs = get_visible_inputs(page)

    if len(inputs) < 2:
        raise RuntimeError(
            "Institution input did not become available "
            "after selecting the country."
        )

    # The second visible input on the opening form is institution search.
    institution_input = inputs[1]

    try:
        if institution_input.is_disabled():
            raise RuntimeError(
                "Institution input is still disabled."
            )
    except Exception as exc:
        if "still disabled" in str(exc):
            raise

    institution_input.click()
    institution_input.fill(institution)

    print("Institution search entered:", institution)

    page.wait_for_timeout(1500)

    # Again: fill ONCE and click the returned result.
    exact_results = page.get_by_text(
        re.compile(
            rf"^\s*{re.escape(institution)}\s*$",
            re.I,
        )
    )

    clicked = False

    for i in range(exact_results.count()):
        result = exact_results.nth(i)

        try:
            if not result.is_visible():
                continue

            tag = result.evaluate(
                "el => el.tagName.toLowerCase()"
            )

            if tag == "input":
                continue

            result.click(timeout=10000)
            clicked = True
            break

        except Exception:
            continue

    if not clicked:
        options = page.get_by_role(
            "option",
            name=re.compile(
                rf"^\s*{re.escape(institution)}\s*$",
                re.I,
            ),
        )

        for i in range(options.count()):
            option = options.nth(i)

            try:
                if option.is_visible():
                    option.click(timeout=10000)
                    clicked = True
                    break
            except Exception:
                continue

    if not clicked:
        raise RuntimeError(
            f'Institution result "{institution}" could not be selected.'
        )

    print("Institution selected:", institution)

    page.wait_for_timeout(800)


def click_button(page, name):
    button = page.get_by_role(
        "button",
        name=re.compile(
            rf"^\s*{re.escape(name)}\s*$",
            re.I,
        ),
    )

    for i in range(button.count()):
        candidate = button.nth(i)

        try:
            if candidate.is_visible():
                candidate.click(timeout=15000)
                return
        except Exception:
            pass

    # Fallback for clickable cards/text.
    text = page.get_by_text(
        re.compile(
            rf"^\s*{re.escape(name)}\s*$",
            re.I,
        )
    )

    for i in range(text.count()):
        candidate = text.nth(i)

        try:
            if candidate.is_visible():
                candidate.click(timeout=15000)
                return
        except Exception:
            pass

    raise RuntimeError(
        f'Could not click "{name}".'
    )


def fill_destination_amount(page, amount):
    print("Entering destination amount:", amount)

    # First try labelled Amount input.
    amount_fields = page.get_by_label(
        re.compile(r"Amount", re.I)
    )

    for i in range(amount_fields.count()):
        field = amount_fields.nth(i)

        try:
            if field.is_visible():
                field.fill(str(amount))
                print("Destination amount entered.")
                return
        except Exception:
            pass

    # Fallback based on nearby "receives" section.
    inputs = get_visible_inputs(page)

    for field in inputs:
        try:
            metadata = " ".join(
                [
                    field.get_attribute("name") or "",
                    field.get_attribute("placeholder") or "",
                    field.get_attribute("aria-label") or "",
                ]
            )

            if re.search(
                r"amount",
                metadata,
                re.I,
            ):
                field.fill(str(amount))
                print("Destination amount entered.")
                return
        except Exception:
            pass

    raise RuntimeError(
        "Could not locate destination amount field."
    )


def choose_payment_country(page, country):
    print("Selecting payment origin:", country)

    inputs = get_visible_inputs(page)

    candidate = None

    for field in inputs:
        try:
            metadata = " ".join(
                [
                    field.get_attribute("placeholder") or "",
                    field.get_attribute("aria-label") or "",
                    field.get_attribute("name") or "",
                ]
            )

            if re.search(
                r"country|region",
                metadata,
                re.I,
            ):
                candidate = field
        except Exception:
            pass

    if candidate is None:
        # At this stage the country selector is normally one of
        # the last visible searchable inputs.
        if not inputs:
            raise RuntimeError(
                "Could not find payment-country input."
            )

        candidate = inputs[-1]

    candidate.click()
    candidate.fill(country)

    page.wait_for_timeout(1000)

    results = page.get_by_text(
        re.compile(
            rf"^\s*{re.escape(country)}\s*$",
            re.I,
        )
    )

    for i in range(results.count()):
        result = results.nth(i)

        try:
            if result.is_visible():
                result.click(timeout=10000)

                print(
                    "Payment origin selected:",
                    country,
                )

                return
        except Exception:
            pass

    raise RuntimeError(
        f'Could not select payment origin "{country}".'
    )


def parse_inr(text):
    match = re.search(
        r"₹\s*([\d,]+(?:\.\d{1,2})?)",
        text,
    )

    if not match:
        raise RuntimeError(
            "Could not find INR quote."
        )

    return float(
        match.group(1).replace(",", "")
    )


def extract_offline_quote(page):
    print("Looking for Offline bank transfer quote...")

    labels = page.get_by_text(
        re.compile(
            r"Offline bank transfer",
            re.I,
        )
    )

    payment_label = None

    for i in range(labels.count()):
        candidate = labels.nth(i)

        try:
            if candidate.is_visible():
                payment_label = candidate
                break
        except Exception:
            pass

    if payment_label is None:
        raise RuntimeError(
            "Offline bank transfer payment method was not found."
        )

    node = payment_label

    # Walk upward through the payment-method card until
    # we find its displayed INR amount.
    for _ in range(10):
        try:
            text = node.inner_text()

            if "₹" in text:
                return parse_inr(text)
        except Exception:
            pass

        node = node.locator("xpath=..")

    raise RuntimeError(
        "Offline bank transfer was found, "
        "but its INR quote could not be extracted."
    )


def collect_quote(
    config=USD_5000,
    headless=True,
):

    print()
    print("================================")
    print("FLYWIRE QUOTE AGENT")
    print("================================")
    print(
        "Institution country:",
        config.institution_country,
    )
    print(
        "Institution:",
        config.institution,
    )
    print(
        "Destination currency:",
        config.currency,
    )
    print(
        "Destination amount:",
        config.amount,
    )
    print(
        "Payment origin:",
        config.payment_country,
    )
    print(
        "Route: Full Loan Financing -> "
        "Bank -> SBI -> Offline bank transfer"
    )

    timestamp = now_ist()

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        context = browser.new_context(
            locale="en-US",
            timezone_id="Asia/Kolkata",
            viewport={
                "width": 1440,
                "height": 1100,
            },
        )

        page = context.new_page()

        page.set_default_timeout(15000)

        try:

            print("Opening:", PAY_URL)

            page.goto(
                PAY_URL,
                wait_until="domcontentloaded",
                timeout=90000,
            )

            page.wait_for_timeout(3000)

            page.get_by_text(
                re.compile(
                    r"MAKE A PAYMENT",
                    re.I,
                )
            ).first.wait_for(
                state="visible",
                timeout=30000,
            )

            dismiss_privacy_popup(page)

            # ==========================================
            # PAGE 1
            # ==========================================

            choose_country(
                page,
                config.institution_country,
            )

            choose_institution(
                page,
                config.institution,
            )

            # Debug checkpoint
            page.screenshot(
                path=str(
                    DEBUG_DIR /
                    "checkpoint_harvard_selected.png"
                ),
                full_page=True,
            )

            print(
                "Country + institution completed successfully."
            )

            click_button(
                page,
                "Continue",
            )

            page.wait_for_timeout(2500)

            # ==========================================
            # PAGE 2
            # ==========================================

            fill_destination_amount(
                page,
                config.amount,
            )

            choose_payment_country(
                page,
                config.payment_country,
            )

            try:
                click_button(
                    page,
                    "Next",
                )
            except Exception:
                click_button(
                    page,
                    "Continue",
                )

            page.wait_for_timeout(2500)

            # ==========================================
            # SOURCE OF FUNDS
            # ==========================================

            print(
                "Selecting Full Loan Financing..."
            )

            click_button(
                page,
                "Full Loan Financing",
            )

            page.wait_for_timeout(1200)

            # ==========================================
            # LOAN PROVIDER TYPE
            # ==========================================

            print(
                "Selecting Bank..."
            )

            click_button(
                page,
                "Bank",
            )

            page.wait_for_timeout(1200)

            # ==========================================
            # SBI
            # ==========================================

            print(
                "Selecting SBI loan..."
            )

            click_button(
                page,
                "I have taken a loan from SBI",
            )

            page.wait_for_timeout(700)

            try:
                click_button(
                    page,
                    "Continue",
                )
            except Exception:
                pass

            page.wait_for_timeout(2500)

            # ==========================================
            # QUOTE
            # ==========================================

            inr_quote = extract_offline_quote(
                page
            )

            effective_rate = round(
                inr_quote / config.amount,
                4,
            )

            record = {
                "timestamp":
                    timestamp.isoformat(),

                "currency":
                    config.currency,

                "amount":
                    config.amount,

                "inr_quote":
                    inr_quote,

                "effective_rate":
                    effective_rate,

                "institution_country":
                    config.institution_country,

                "institution":
                    config.institution,

                "payment_country":
                    config.payment_country,

                "funding_type":
                    "Full Loan Financing",

                "loan_provider_type":
                    "Bank",

                "loan_provider":
                    "SBI",

                "payment_method":
                    "Offline bank transfer",

                "source_url":
                    PAY_URL,

                "status":
                    "current",
            }

            print()
            print("================================")
            print("FLYWIRE QUOTE CAPTURED")
            print("================================")
            print(
                "INR Quote:",
                inr_quote,
            )
            print(
                "Effective Rate:",
                effective_rate,
            )
            print(
                "Timestamp:",
                timestamp.isoformat(),
            )

            return record

        except Exception as exc:

            print()
            print("FLYWIRE AGENT FAILED:")
            print(str(exc))

            save_debug(page)

            raise

        finally:

            context.close()
            browser.close()


def collect_usd_5000(
    headless=True,
):
    return collect_quote(
        USD_5000,
        headless=headless,
    )


if __name__ == "__main__":
    collect_usd_5000()
