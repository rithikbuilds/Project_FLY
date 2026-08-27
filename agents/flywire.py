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
    Close Flywire/CookieYes privacy UI without opening the Opt Out dialog.
    """
    try:
        modal_close = page.locator(".cky-modal.cky-modal-open .cky-btn-close")
        if modal_close.count() and modal_close.first.is_visible():
            modal_close.first.click(timeout=3000)
            page.wait_for_timeout(400)
            print("Privacy preferences modal closed.")
    except Exception:
        pass

    try:
        banner_close = page.locator(".cky-consent-container .cky-banner-btn-close")
        if banner_close.count() and banner_close.first.is_visible():
            banner_close.first.click(timeout=3000)
            page.wait_for_timeout(400)
            print("Privacy banner closed.")
    except Exception:
        pass
def click_visible_exact_text(page, text, timeout=10000):
    """
    Click a visible exact text match.
    Used for dropdown results/cards.
    """
    locator = page.get_by_text(
        re.compile(
            rf"^\s*{re.escape(text)}\s*$",
            re.I,
        )
    )

    for i in range(locator.count()):
        item = locator.nth(i)

        try:
            if not item.is_visible():
                continue

            tag = item.evaluate(
                "el => el.tagName.toLowerCase()"
            )

            # Never treat the input itself as the dropdown result.
            if tag == "input":
                continue

            item.click(timeout=timeout)
            return True

        except Exception:
            continue

    # Accessible-option fallback.
    try:
        options = page.get_by_role(
            "option",
            name=re.compile(
                rf"^\s*{re.escape(text)}\s*$",
                re.I,
            ),
        )

        for i in range(options.count()):
            option = options.nth(i)

            if option.is_visible():
                option.click(timeout=timeout)
                return True
    except Exception:
        pass

    return False


def choose_country(page, country):
    """
    Use Flywire's visible Select2 country widget so its real selection event
    fires and the institution selector gets enabled.
    """
    print("Selecting institution country:", country)

    country_select = page.locator("#countryDropdown")
    country_select.wait_for(state="attached", timeout=20000)

    visible_control = page.locator(
        "#countryDropdown + .select2 .select2-selection"
    )

    if visible_control.count() == 0:
        visible_control = page.locator(
            "[aria-labelledby='select2-countryDropdown-container']"
        )

    visible_control.first.wait_for(state="visible", timeout=15000)
    visible_control.first.click()

    search = page.locator(
        ".select2-container--open input.select2-search__field"
    )
    search.wait_for(state="visible", timeout=10000)
    search.fill(country)

    print("Country search entered:", country)

    page.wait_for_timeout(700)

    results = page.locator(
        ".select2-container--open .select2-results__option"
    )
    results.first.wait_for(state="visible", timeout=15000)

    matching = results.filter(has_text=country)

    if matching.count() == 0:
        available = []
        for i in range(min(results.count(), 10)):
            try:
                text = results.nth(i).inner_text().strip()
                if text:
                    available.append(text)
            except Exception:
                pass

        raise RuntimeError(
            f'Country result "{country}" was not found. '
            f'Visible Select2 results: {available}'
        )

    chosen = matching.first

    print("Country result found:", chosen.inner_text().strip())
    chosen.click(timeout=10000)

    page.wait_for_timeout(1000)

    selected_country = page.locator(
        "#select2-countryDropdown-container"
    ).inner_text().strip()

    selected_value = country_select.input_value()

    print(
        "Institution country selected:",
        selected_country,
        f"({selected_value})",
    )

    if country.lower() not in selected_country.lower():
        raise RuntimeError(
            f'Country selection verification failed. '
            f'Expected "{country}", got "{selected_country}".'
        )

    try:
        page.wait_for_function(
            """
            () => {
                const el = document.querySelector('#institutionDropdown');
                return el && !el.disabled;
            }
            """,
            timeout=20000,
        )
    except Exception:
        disabled = page.locator("#institutionDropdown").is_disabled()
        section_class = page.locator(
            "[data-testid='institution-section-dropdown']"
        ).get_attribute("class")

        raise RuntimeError(
            "Country was visibly selected, but Flywire did not enable "
            f"the institution selector. disabled={disabled}; "
            f"section_class={section_class}"
        )

    print("Institution selector enabled.")
def choose_institution(page, institution):
    """
    The institution selector is Select2 with remotely loaded results.
    Open its visible Select2 control, type into the temporary search input,
    then select the matching institution.
    """
    print("Selecting institution:", institution)

    institution_select = page.locator("#institutionDropdown")
    institution_select.wait_for(state="attached", timeout=20000)

    page.wait_for_function(
        """
        () => {
            const el = document.querySelector('#institutionDropdown');
            return el && !el.disabled;
        }
        """,
        timeout=20000,
    )

    # Select2 creates a visible selection element next to the hidden select.
    visible_control = page.locator(
        "#institutionDropdown + .select2 .select2-selection"
    )

    if visible_control.count() == 0:
        visible_control = page.locator(
            "[aria-labelledby='select2-institutionDropdown-container']"
        )

    visible_control.first.wait_for(state="visible", timeout=15000)
    visible_control.first.click()

    search = page.locator(
        ".select2-container--open input.select2-search__field"
    )

    search.wait_for(state="visible", timeout=15000)
    search.fill(institution)

    print("Institution search entered:", institution)

    # Give the remote institution lookup time to return.
    page.wait_for_timeout(1500)

    results = page.locator(
        ".select2-container--open .select2-results__option"
    )

    results.first.wait_for(state="visible", timeout=20000)

    matching = results.filter(
        has_text=institution
    )

    if matching.count() == 0:
        available = []
        for i in range(min(results.count(), 10)):
            try:
                text = results.nth(i).inner_text().strip()
                if text:
                    available.append(text)
            except Exception:
                pass

        raise RuntimeError(
            f'Institution result "{institution}" was not found. '
            f'Visible Select2 results: {available}'
        )

    chosen = matching.first
    chosen_text = chosen.inner_text().strip()

    print("Institution result found:", chosen_text)

    chosen.click(timeout=15000)
    page.wait_for_timeout(1000)

    selected_text = ""

    try:
        selected_text = page.locator(
            "#select2-institutionDropdown-container"
        ).inner_text().strip()
    except Exception:
        pass

    selected_value = institution_select.input_value()

    print("Institution selected:", selected_text or selected_value)

    if not selected_value:
        raise RuntimeError(
            f'Flywire did not retain the institution selection for '
            f'"{institution}".'
        )
def click_action(page, text, timeout=15000):
    """
    Click a normal Flywire button/card by visible label.
    """
    try:
        buttons = page.get_by_role(
            "button",
            name=re.compile(
                rf"^\s*{re.escape(text)}\s*$",
                re.I,
            ),
        )

        for i in range(buttons.count()):
            button = buttons.nth(i)

            if button.is_visible():
                button.click(timeout=timeout)
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


def get_editable_inputs(page):
    """
    Only return fillable user-entry inputs.

    This intentionally EXCLUDES the cookie/privacy checkbox that caused:
        Input of type "checkbox" cannot be filled
    """
    selector = (
        "input:not([type='checkbox'])"
        ":not([type='radio'])"
        ":not([type='hidden'])"
        ":not([type='submit'])"
        ":not([type='button'])"
    )

    locator = page.locator(selector)

    result = []

    for i in range(locator.count()):
        field = locator.nth(i)

        try:
            if field.is_visible() and field.is_enabled():
                result.append(field)
        except Exception:
            continue

    return result


def fill_destination_amount(page, amount):
    print("Entering destination amount:", amount)

    # Best path: labelled amount input.
    try:
        labelled = page.get_by_label(
            re.compile(
                r"Amount",
                re.I,
            )
        )

        for i in range(labelled.count()):
            field = labelled.nth(i)

            if field.is_visible() and field.is_enabled():
                tag = field.evaluate(
                    "el => el.tagName.toLowerCase()"
                )

                if tag == "input":
                    field.fill(str(amount))
                    print("Destination amount entered.")
                    return
    except Exception:
        pass

    # Metadata-based fallback.
    for field in get_editable_inputs(page):
        try:
            metadata = " ".join(
                [
                    field.get_attribute("placeholder") or "",
                    field.get_attribute("aria-label") or "",
                    field.get_attribute("name") or "",
                    field.get_attribute("id") or "",
                ]
            )

            if re.search(
                r"amount|receiv",
                metadata,
                re.I,
            ):
                field.fill(str(amount))
                print("Destination amount entered.")
                return
        except Exception:
            continue

    # Nearby "receives" fallback.
    try:
        receives = page.get_by_text(
            re.compile(
                r"receives",
                re.I,
            )
        )

        for i in range(receives.count()):
            label = receives.nth(i)

            if not label.is_visible():
                continue

            parent = label.locator("xpath=..")

            for _ in range(6):
                inputs = parent.locator(
                    "input:not([type='checkbox']):not([type='radio']):not([type='hidden'])"
                )

                for j in range(inputs.count()):
                    field = inputs.nth(j)

                    if field.is_visible() and field.is_enabled():
                        field.fill(str(amount))
                        print("Destination amount entered.")
                        return

                parent = parent.locator("xpath=..")
    except Exception:
        pass

    raise RuntimeError(
        "Could not locate the destination amount field."
    )


def choose_payment_country(page, country):
    print("Selecting payment origin:", country)

    # Try a placeholder/label that mentions country/region.
    candidates = []

    try:
        loc = page.get_by_placeholder(
            re.compile(
                r"country|region",
                re.I,
            )
        )
        for i in range(loc.count()):
            candidates.append(
                loc.nth(i)
            )
    except Exception:
        pass

    try:
        loc = page.get_by_label(
            re.compile(
                r"country|region|payment.*from",
                re.I,
            )
        )
        for i in range(loc.count()):
            candidates.append(
                loc.nth(i)
            )
    except Exception:
        pass

    for field in candidates:
        try:
            if not field.is_visible() or not field.is_enabled():
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

                print("Payment origin selected:", country)
                return

            if tag == "input":
                field.click()
                field.fill(country)
                page.wait_for_timeout(900)

                if click_visible_exact_text(
                    page,
                    country,
                ):
                    print("Payment origin selected:", country)
                    return

        except Exception:
            continue

    # Last fallback: inspect fillable inputs by metadata.
    for field in get_editable_inputs(page):
        try:
            metadata = " ".join(
                [
                    field.get_attribute("placeholder") or "",
                    field.get_attribute("aria-label") or "",
                    field.get_attribute("name") or "",
                ]
            )

            if not re.search(
                r"country|region",
                metadata,
                re.I,
            ):
                continue

            field.click()
            field.fill(country)

            page.wait_for_timeout(900)

            if click_visible_exact_text(
                page,
                country,
            ):
                print("Payment origin selected:", country)
                return

        except Exception:
            continue

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

    # Nearby body-text fallback.
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


def collect_quote(
    config=USD_5000,
    headless=True,
):

    print()
    print("================================")
    print("FLYWIRE QUOTE AGENT")
    print("================================")

    print("Institution country:", config.institution_country)
    print("Institution:", config.institution)
    print("Destination currency:", config.currency)
    print("Destination amount:", config.amount)
    print("Payment origin:", config.payment_country)

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

            print("Opening:", PAY_URL)

            page.goto(
                PAY_URL,
                wait_until="domcontentloaded",
                timeout=90000,
            )

            page.wait_for_timeout(
                3000
            )

            page.get_by_text(
                re.compile(
                    r"MAKE A PAYMENT",
                    re.I,
                )
            ).first.wait_for(
                state="visible",
                timeout=30000,
            )

            dismiss_privacy_popup(
                page
            )

            # ==================================================
            # PAGE 1
            # ==================================================

            choose_country(
                page,
                config.institution_country,
            )

            choose_institution(
                page,
                config.institution,
            )

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

            click_action(
                page,
                "Continue",
            )

            page.wait_for_timeout(
                2500
            )

            # ==================================================
            # PAGE 2
            # ==================================================

            fill_destination_amount(
                page,
                config.amount,
            )

            choose_payment_country(
                page,
                config.payment_country,
            )

            # Flywire re-renders the Next button after India is selected.
            # Do not keep an ElementHandle across that re-render; locate the
            # live button immediately before every click attempt.
            print("Clicking payment Next...")

            clicked_next = False
            last_next_error = None

            for attempt in range(1, 5):
                try:
                    # Give Flywire's origin-country request a moment to settle.
                    page.wait_for_timeout(1000)

                    btn = page.locator(
                        'button[data-testid="next"]:visible'
                    ).first

                    btn.wait_for(
                        state="visible",
                        timeout=15000,
                    )

                    # Playwright's locator click automatically waits for the
                    # current live element to be enabled/actionable. Because
                    # this is a Locator (not a saved ElementHandle), React may
                    # replace the DOM node without breaking the retry.
                    btn.click(
                        timeout=30000,
                    )

                    clicked_next = True
                    print(
                        f"Payment Next clicked (attempt {attempt})."
                    )
                    break

                except Exception as exc:
                    last_next_error = exc
                    print(
                        f"Payment Next attempt {attempt} did not complete; retrying..."
                    )

            if not clicked_next:
                raise RuntimeError(
                    "Could not click Flywire payment Next after 4 attempts. "
                    f"Last error: {last_next_error}"
                )

            # Confirm navigation by waiting for the next page itself.
            page.get_by_text(
                "What is the source of funds for this payment?",
                exact=False,
            ).first.wait_for(
                state="visible",
                timeout=30000,
            )

            print("Source of funds page loaded.")

            # ==================================================
            # SOURCE OF FUNDS
            # ==================================================

            print(
                "Selecting Full Loan Financing..."
            )

            # The debug HTML shows this is still the source-of-funds page.
            # Target the exact desktop Full Loan Financing card and its
            # Select button, then WAIT for the next page before Bank.
            source_card = page.locator(
                '[data-testid="desktop-sourceOfFunds-education_loan"]'
            )
            source_card.wait_for(
                state="visible",
                timeout=15000,
            )
            source_card.get_by_role(
                "button",
                name="Select",
                exact=True,
            ).click()

            page.get_by_text(
                "Select your loan provider",
                exact=False,
            ).first.wait_for(
                state="visible",
                timeout=20000,
            )

            print(
                "Full Loan Financing selected."
            )
            print(
                "Loan provider page loaded."
            )

            # ==================================================
            # LOAN PROVIDER TYPE
            # ==================================================

            print(
                "Selecting Bank..."
            )

            # The Bank option is itself the clickable element.
            # Debug HTML shows:
            #   role="button"
            #   aria-label="Bank"
            #   data-testid="loanProviderCategory-banks"
            # There is NO nested Select button on this screen.
            bank_card = page.locator(
                '[data-testid="loanProviderCategory-banks"]'
            )

            bank_card.wait_for(
                state="visible",
                timeout=15000,
            )

            bank_card.click(
                timeout=10000,
            )

            # Wait until the SBI/non-SBI screen has actually loaded.
            page.get_by_text(
                "I have taken a loan from SBI",
                exact=False,
            ).first.wait_for(
                state="visible",
                timeout=20000,
            )

            print(
                "Bank selected."
            )

            # ==================================================
            # SBI
            # ==================================================

            print(
                "Selecting SBI loan..."
            )

            sbi_text = page.get_by_text(
                "I have taken a loan from SBI",
                exact=False,
            ).first

            sbi_text.wait_for(
                state="visible",
                timeout=15000,
            )

            # Select the SBI option/card.
            try:
                sbi_text.click(
                    timeout=5000
                )
            except Exception:
                sbi_card = sbi_text.locator(
                    "xpath=ancestor::*[.//button[normalize-space()='Continue']][1]"
                )
                sbi_card.get_by_role(
                    "button",
                    name="Continue",
                    exact=True,
                ).click()

            page.wait_for_timeout(
                500
            )

            # If Flywire uses a shared Continue button after selecting SBI,
            # press it only when visible and enabled.
            continue_buttons = page.get_by_role(
                "button",
                name="Continue",
                exact=True,
            )

            for i in range(
                continue_buttons.count()
            ):
                btn = continue_buttons.nth(i)
                try:
                    if (
                        btn.is_visible()
                        and btn.is_enabled()
                    ):
                        btn.click(
                            timeout=5000
                        )
                        break
                except Exception:
                    pass

            print(
                "SBI loan provider selected."
            )

            page.wait_for_timeout(
                2500
            )

            # ==================================================
            # QUOTE
            # ==================================================

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


def collect_usd_5000(
    headless=True,
):
    return collect_quote(
        USD_5000,
        headless=headless,
    )


if __name__ == "__main__":
    collect_usd_5000()
