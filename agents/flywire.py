import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright


# ============================================================
# CONFIGURATION
# ============================================================

IST = ZoneInfo("Asia/Kolkata")

PAY_URL = "https://pay.flywire.com/"

ROOT_DIR = Path(__file__).resolve().parent.parent

DEBUG_DIR = ROOT_DIR / "data" / "flywire_debug"

DEBUG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


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


# ============================================================
# TIME
# ============================================================

def now_ist():

    return datetime.now(IST)


# ============================================================
# DEBUG
# ============================================================

def save_debug(
    page,
    prefix="flywire_failure",
):

    stamp = now_ist().strftime(
        "%Y%m%d_%H%M%S"
    )

    screenshot = (
        DEBUG_DIR
        / f"{prefix}_{stamp}.png"
    )

    html_file = (
        DEBUG_DIR
        / f"{prefix}_{stamp}.html"
    )

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

    print(
        "Debug screenshot:",
        screenshot,
    )

    print(
        "Debug HTML:",
        html_file,
    )


# ============================================================
# PRIVACY POPUP
# ============================================================

def dismiss_privacy_popup(page):

    possible_texts = [
        "Opt Out",
        "Accept",
        "Accept All",
        "Close",
    ]

    for text in possible_texts:

        try:

            locator = page.get_by_text(
                text,
                exact=True,
            )

            for i in range(
                locator.count()
            ):

                item = locator.nth(i)

                if item.is_visible():

                    item.click(
                        timeout=3000
                    )

                    page.wait_for_timeout(
                        500
                    )

                    print(
                        "Privacy popup handled."
                    )

                    return

        except Exception:

            pass


# ============================================================
# EXACT TEXT CLICKER
# ============================================================

def click_visible_exact_text(
    page,
    text,
    timeout=10000,
):

    locator = page.get_by_text(
        re.compile(
            rf"^\s*{re.escape(text)}\s*$",
            re.I,
        )
    )

    for i in range(
        locator.count()
    ):

        item = locator.nth(i)

        try:

            if not item.is_visible():

                continue

            tag = item.evaluate(
                "el => el.tagName.toLowerCase()"
            )

            if tag == "input":

                continue

            item.click(
                timeout=timeout
            )

            return True

        except Exception:

            continue

    # Accessible option fallback

    try:

        options = page.get_by_role(
            "option",
            name=re.compile(
                rf"^\s*{re.escape(text)}\s*$",
                re.I,
            ),
        )

        for i in range(
            options.count()
        ):

            option = options.nth(i)

            if option.is_visible():

                option.click(
                    timeout=timeout
                )

                return True

    except Exception:

        pass

    return False


# ============================================================
# COUNTRY SELECTION
# ============================================================

def choose_country(
    page,
    country,
):

    print(
        "Selecting institution country:",
        country,
    )

    # IMPORTANT:
    # Exact CSS selector instead of get_by_placeholder regex.
    #
    # Previous version failed because "/" in country/region
    # was converted into an invalid selector.

    country_input = page.locator(
        'input[placeholder="Start typing the country/region name"]'
    )

    if country_input.count() == 0:

        raise RuntimeError(
            "Institution-country search input was not found."
        )

    field = country_input.first

    field.wait_for(
        state="visible",
        timeout=20000,
    )

    field.click()

    field.fill(
        country
    )

    print(
        "Country search entered:",
        country,
    )

    page.wait_for_timeout(
        1200
    )

    # Click returned United States option.
    #
    # DO NOT type the country again.

    selected = (
        click_visible_exact_text(
            page,
            country,
        )
    )

    if not selected:

        raise RuntimeError(
            f'Country result "{country}" '
            "could not be selected."
        )

    print(
        "Institution country selected:",
        country,
    )

    # Institution field becomes active after
    # the country has been selected.

    page.wait_for_timeout(
        1800
    )


# ============================================================
# INSTITUTION SELECTION
# ============================================================

def choose_institution(
    page,
    institution,
):

    print(
        "Selecting institution:",
        institution,
    )

    # Exact CSS partial placeholder match.

    institution_input = page.locator(
        'input[placeholder*="Start typing payment recipient"]'
    )

    if institution_input.count() == 0:

        raise RuntimeError(
            "Institution search input was not found."
        )

    field = institution_input.first

    field.wait_for(
        state="visible",
        timeout=20000,
    )

    # Wait for institution field to become enabled
    # after selecting United States.

    enabled = False

    for _ in range(20):

        try:

            if field.is_enabled():

                enabled = True

                break

        except Exception:

            pass

        page.wait_for_timeout(
            500
        )

    if not enabled:

        raise RuntimeError(
            "Institution input did not become enabled "
            "after selecting United States."
        )

    field.click()

    field.fill(
        institution
    )

    print(
        "Institution search entered:",
        institution,
    )

    page.wait_for_timeout(
        1500
    )

    selected = (
        click_visible_exact_text(
            page,
            institution,
        )
    )

    if not selected:

        raise RuntimeError(
            f'Institution result "{institution}" '
            "could not be selected."
        )

    print(
        "Institution selected:",
        institution,
    )

    page.wait_for_timeout(
        800
    )


# ============================================================
# GENERIC BUTTON / CARD CLICKER
# ============================================================

def click_action(
    page,
    text,
    timeout=15000,
):

    try:

        buttons = page.get_by_role(
            "button",
            name=re.compile(
                rf"^\s*{re.escape(text)}\s*$",
                re.I,
            ),
        )

        for i in range(
            buttons.count()
        ):

            button = buttons.nth(i)

            if button.is_visible():

                button.click(
                    timeout=timeout
                )

                return

    except Exception:

        pass

    if click_visible_exact_text(
        page,
        text,
        timeout=timeout,
    ):

        return

    raise RuntimeError(
        f'Could not click "{text}".'
    )


# ============================================================
# EDITABLE INPUTS
# ============================================================

def get_editable_inputs(page):

    # Explicitly exclude cookie checkbox,
    # radio buttons and hidden controls.

    selector = (
        "input:not([type='checkbox'])"
        ":not([type='radio'])"
        ":not([type='hidden'])"
        ":not([type='submit'])"
        ":not([type='button'])"
    )

    locator = page.locator(
        selector
    )

    result = []

    for i in range(
        locator.count()
    ):

        field = locator.nth(i)

        try:

            if (
                field.is_visible()
                and field.is_enabled()
            ):

                result.append(
                    field
                )

        except Exception:

            continue

    return result


# ============================================================
# AMOUNT
# ============================================================

def fill_destination_amount(
    page,
    amount,
):

    print(
        "Entering destination amount:",
        amount,
    )

    # First try labels.

    try:

        labelled = page.get_by_label(
            re.compile(
                r"Amount",
                re.I,
            )
        )

        for i in range(
            labelled.count()
        ):

            field = labelled.nth(i)

            if (
                field.is_visible()
                and field.is_enabled()
            ):

                tag = field.evaluate(
                    "el => el.tagName.toLowerCase()"
                )

                if tag == "input":

                    field.fill(
                        str(amount)
                    )

                    print(
                        "Destination amount entered."
                    )

                    return

    except Exception:

        pass

    # Metadata fallback.

    for field in get_editable_inputs(
        page
    ):

        try:

            metadata = " ".join(
                [
                    field.get_attribute(
                        "placeholder"
                    )
                    or "",

                    field.get_attribute(
                        "aria-label"
                    )
                    or "",

                    field.get_attribute(
                        "name"
                    )
                    or "",

                    field.get_attribute(
                        "id"
                    )
                    or "",
                ]
            )

            if re.search(
                r"amount|receiv",
                metadata,
                re.I,
            ):

                field.fill(
                    str(amount)
                )

                print(
                    "Destination amount entered."
                )

                return

        except Exception:

            continue

    # Search near "receives".

    try:

        receives = page.get_by_text(
            re.compile(
                r"receives",
                re.I,
            )
        )

        for i in range(
            receives.count()
        ):

            label = receives.nth(i)

            if not label.is_visible():

                continue

            parent = label.locator(
                "xpath=.."
            )

            for _ in range(6):

                inputs = parent.locator(
                    "input:not([type='checkbox'])"
                    ":not([type='radio'])"
                    ":not([type='hidden'])"
                )

                for j in range(
                    inputs.count()
                ):

                    field = inputs.nth(j)

                    if (
                        field.is_visible()
                        and field.is_enabled()
                    ):

                        field.fill(
                            str(amount)
                        )

                        print(
                            "Destination amount entered."
                        )

                        return

                parent = parent.locator(
                    "xpath=.."
                )

    except Exception:

        pass

    raise RuntimeError(
        "Could not locate the destination amount field."
    )


# ============================================================
# PAYMENT COUNTRY
# ============================================================

def choose_payment_country(
    page,
    country,
):

    print(
        "Selecting payment origin:",
        country,
    )

    candidates = []

    # Try placeholders.

    try:

        loc = page.locator(
            'input[placeholder*="country"]'
        )

        for i in range(
            loc.count()
        ):

            candidates.append(
                loc.nth(i)
            )

    except Exception:

        pass

    # Try labelled controls.

    try:

        loc = page.get_by_label(
            re.compile(
                r"country|region|payment.*from",
                re.I,
            )
        )

        for i in range(
            loc.count()
        ):

            candidates.append(
                loc.nth(i)
            )

    except Exception:

        pass

    for field in candidates:

        try:

            if (
                not field.is_visible()
                or not field.is_enabled()
            ):

                continue

            tag = field.evaluate(
                "el => el.tagName.toLowerCase()"
            )

            if tag == "select":

                try:

                    field.select_option(
                        label=country,
                    )

                except Exception:

                    field.select_option(
                        value=country,
                    )

                print(
                    "Payment origin selected:",
                    country,
                )

                return

            if tag == "input":

                field.click()

                field.fill(
                    country
                )

                page.wait_for_timeout(
                    1000
                )

                if click_visible_exact_text(
                    page,
                    country,
                ):

                    print(
                        "Payment origin selected:",
                        country,
                    )

                    return

        except Exception:

            continue

    # Metadata fallback.

    for field in get_editable_inputs(
        page
    ):

        try:

            metadata = " ".join(
                [
                    field.get_attribute(
                        "placeholder"
                    )
                    or "",

                    field.get_attribute(
                        "aria-label"
                    )
                    or "",

                    field.get_attribute(
                        "name"
                    )
                    or "",
                ]
            )

            if not re.search(
                r"country|region",
                metadata,
                re.I,
            ):

                continue

            field.click()

            field.fill(
                country
            )

            page.wait_for_timeout(
                1000
            )

            if click_visible_exact_text(
                page,
                country,
            ):

                print(
                    "Payment origin selected:",
                    country,
                )

                return

        except Exception:

            continue

    raise RuntimeError(
        f'Could not select payment origin "{country}".'
    )


# ============================================================
# INR PARSER
# ============================================================

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
        match.group(1).replace(
            ",",
            "",
        )
    )


# ============================================================
# OFFLINE BANK TRANSFER QUOTE
# ============================================================

def extract_offline_quote(page):

    print(
        "Looking for Offline bank transfer quote..."
    )

    labels = page.get_by_text(
        re.compile(
            r"Offline bank transfer",
            re.I,
        )
    )

    payment_label = None

    for i in range(
        labels.count()
    ):

        candidate = labels.nth(i)

        try:

            if candidate.is_visible():

                payment_label = candidate

                break

        except Exception:

            pass

    if payment_label is None:

        raise RuntimeError(
            "Offline bank transfer payment method "
            "was not found."
        )

    node = payment_label

    # Walk up payment card.

    for _ in range(10):

        try:

            text = node.inner_text(
                timeout=5000,
            )

            if "₹" in text:

                return parse_inr(
                    text
                )

        except Exception:

            pass

        node = node.locator(
            "xpath=.."
        )

    # Body text fallback.

    body = page.locator(
        "body"
    ).inner_text()

    position = body.lower().find(
        "offline bank transfer"
    )

    if position >= 0:

        nearby = body[
            position:
            position + 1500
        ]

        if "₹" in nearby:

            return parse_inr(
                nearby
            )

    raise RuntimeError(
        "Offline bank transfer was found, "
        "but its INR quote could not be extracted."
    )


# ============================================================
# MAIN QUOTE AGENT
# ============================================================

def collect_quote(
    config=USD_5000,
    headless=True,
):

    print()

    print(
        "================================"
    )

    print(
        "FLYWIRE QUOTE AGENT"
    )

    print(
        "================================"
    )

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

        page.set_default_timeout(
            15000
        )

        try:

            print(
                "Opening:",
                PAY_URL,
            )

            page.goto(
                PAY_URL,
                wait_until="domcontentloaded",
                timeout=90000,
            )

            page.wait_for_timeout(
                3000
            )

            # Wait for main page.

            page.get_by_text(
                re.compile(
                    r"MAKE A PAYMENT",
                    re.I,
                )
            ).first.wait_for(
                state="visible",
                timeout=30000,
            )

            # Privacy popup.

            dismiss_privacy_popup(
                page
            )

            # =================================================
            # STEP 1
            # INSTITUTION COUNTRY
            # =================================================

            choose_country(
                page,
                config.institution_country,
            )

            # =================================================
            # STEP 2
            # INSTITUTION
            # =================================================

            choose_institution(
                page,
                config.institution,
            )

            # Save checkpoint.

            try:

                page.screenshot(
                    path=str(
                        DEBUG_DIR
                        / "checkpoint_harvard_selected.png"
                    ),
                    full_page=True,
                )

            except Exception:

                pass

            print(
                "Country + institution completed successfully."
            )

            # =================================================
            # STEP 3
            # CONTINUE
            # =================================================

            click_action(
                page,
                "Continue",
            )

            page.wait_for_timeout(
                2500
            )

            # =================================================
            # STEP 4
            # USD AMOUNT
            # =================================================

            fill_destination_amount(
                page,
                config.amount,
            )

            # =================================================
            # STEP 5
            # PAYMENT COUNTRY = INDIA
            # =================================================

            choose_payment_country(
                page,
                config.payment_country,
            )

            # =================================================
            # STEP 6
            # NEXT
            # =================================================

            try:

                click_action(
                    page,
                    "Next",
                )

            except Exception:

                click_action(
                    page,
                    "Continue",
                )

            page.wait_for_timeout(
                2500
            )

            # =================================================
            # STEP 7
            # FULL LOAN FINANCING
            # =================================================

            print(
                "Selecting Full Loan Financing..."
            )

            click_action(
                page,
                "Full Loan Financing",
            )

            page.wait_for_timeout(
                1200
            )

            # =================================================
            # STEP 8
            # BANK
            # =================================================

            print(
                "Selecting Bank..."
            )

            click_action(
                page,
                "Bank",
            )

            page.wait_for_timeout(
                1200
            )

            # =================================================
            # STEP 9
            # SBI
            # =================================================

            print(
                "Selecting SBI loan..."
            )

            click_action(
                page,
                "I have taken a loan from SBI",
            )

            page.wait_for_timeout(
                700
            )

            try:

                click_action(
                    page,
                    "Continue",
                )

            except Exception:

                pass

            page.wait_for_timeout(
                2500
            )

            # =================================================
            # STEP 10
            # READ QUOTE
            # =================================================

            inr_quote = (
                extract_offline_quote(
                    page
                )
            )

            effective_rate = round(
                inr_quote
                / config.amount,
                4,
            )

            # =================================================
            # RESULT
            # =================================================

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

            print(
                "================================"
            )

            print(
                "FLYWIRE QUOTE CAPTURED"
            )

            print(
                "================================"
            )

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

            print(
                "FLYWIRE AGENT FAILED:"
            )

            print(
                str(exc)
            )

            save_debug(
                page
            )

            raise

        finally:

            context.close()

            browser.close()


# ============================================================
# PHASE V3.1 ENTRY POINT
# ============================================================

def collect_usd_5000(
    headless=True,
):

    return collect_quote(
        USD_5000,
        headless=headless,
    )


if __name__ == "__main__":

    collect_usd_5000()
