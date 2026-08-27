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


def parse_inr(text: str) -> float:
    match = re.search(r"₹\s*([\d,]+(?:\.\d{1,2})?)", text)
    if not match:
        raise RuntimeError(
            "Could not find an INR amount in the payment-method text."
        )

    return float(
        match.group(1).replace(",", "")
    )


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


def click_first_visible(locator, timeout=15000):
    count = locator.count()

    for index in range(count):
        item = locator.nth(index)

        try:
            if item.is_visible():
                item.click(timeout=timeout)
                return True
        except Exception:
            continue

    return False


def choose_from_open_dropdown(page, value: str):
    """
    Choose a visible option after a Flywire dropdown has been opened.

    Flywire uses JavaScript dropdown widgets, so the option may be rendered
    outside the field itself (for example in a portal/listbox).
    """

    exact = page.get_by_text(
        re.compile(
            rf"^\s*{re.escape(value)}\s*$",
            re.I,
        )
    )

    if click_first_visible(exact, timeout=10000):
        return

    # Try accessible option role.
    option = page.get_by_role(
        "option",
        name=re.compile(
            rf"^\s*{re.escape(value)}\s*$",
            re.I,
        ),
    )

    if click_first_visible(option, timeout=10000):
        return

    raise RuntimeError(
        f'Dropdown opened, but option "{value}" was not found.'
    )


def flywire_comboboxes(page):
    """
    Return the currently visible Flywire dropdown/combobox elements.

    The landing page visually contains:
      0 = institution country/region
      1 = institution
    """

    selectors = [
        "[role='combobox']",
        "select",
        "button[aria-haspopup='listbox']",
        "input[aria-autocomplete]",
    ]

    items = []

    for selector in selectors:
        locator = page.locator(selector)

        for index in range(locator.count()):
            item = locator.nth(index)

            try:
                if not item.is_visible():
                    continue

                handle = item.element_handle()

                if handle is None:
                    continue

                # Avoid duplicates when different selectors refer to same node.
                if any(
                    existing.evaluate(
                        "(el, other) => el === other",
                        handle,
                    )
                    for existing in items
                ):
                    continue

                items.append(item)

            except Exception:
                continue

    return items


def select_landing_dropdown(
    page,
    index: int,
    value: str,
    description: str,
):
    """
    Select one of the two dropdowns on pay.flywire.com's opening form.

    This intentionally targets the dropdown POSITION rather than relying on
    the generic label matcher that failed on the institution field.
    """

    page.wait_for_timeout(500)

    # First preference: actual accessible comboboxes.
    combos = page.get_by_role("combobox")

    visible_combos = []

    for i in range(combos.count()):
        combo = combos.nth(i)

        try:
            if combo.is_visible():
                visible_combos.append(combo)
        except Exception:
            pass

    # Some versions expose the widgets as buttons instead.
    if len(visible_combos) <= index:
        buttons = page.locator(
            "button[aria-haspopup='listbox'], "
            "[role='button'][aria-haspopup='listbox']"
        )

        for i in range(buttons.count()):
            button = buttons.nth(i)

            try:
                if button.is_visible():
                    visible_combos.append(button)
            except Exception:
                pass

    if len(visible_combos) <= index:
        raise RuntimeError(
            f"Could not locate Flywire {description} dropdown. "
            f"Visible dropdown count: {len(visible_combos)}"
        )

    field = visible_combos[index]

    print(
        f"Selecting {description}:",
        value,
    )

    # Native select.
    try:
        tag = field.evaluate(
            "el => el.tagName.toLowerCase()"
        )

        if tag == "select":
            try:
                field.select_option(
                    label=value,
                    timeout=15000,
                )
            except Exception:
                field.select_option(
                    value=value,
                    timeout=15000,
                )

            print(
                f"{description} selected:",
                value,
            )
            return
    except Exception:
        pass

    # Custom dropdown.
    field.click(timeout=15000)

    page.wait_for_timeout(500)

    # Many React-style selects expose an input after opening.
    active = page.locator(":focus")

    try:
        active_tag = active.evaluate(
            "el => el.tagName.toLowerCase()"
        )

        if active_tag == "input":
            try:
                active.fill(value)
                page.wait_for_timeout(700)
            except Exception:
                pass
    except Exception:
        pass

    # If clicking the container exposes an inner input, type there.
    try:
        nearby_input = field.locator(
            "input"
        )

        if nearby_input.count():
            nearby_input.first.fill(value)
            page.wait_for_timeout(700)
    except Exception:
        pass

    # Keyboard search is a useful fallback for searchable dropdown widgets.
    try:
        page.keyboard.type(
            value,
            delay=35,
        )
        page.wait_for_timeout(700)
    except Exception:
        pass

    try:
        choose_from_open_dropdown(
            page,
            value,
        )
    except Exception:
        # React Select commonly accepts the highlighted result with Enter.
        try:
            page.keyboard.press("Enter")
            page.wait_for_timeout(600)
        except Exception:
            raise

    # Verify selection appears visibly on the page.
    visible_value = page.get_by_text(
        re.compile(
            rf"^\s*{re.escape(value)}\s*$",
            re.I,
        )
    )

    found = False

    for i in range(visible_value.count()):
        try:
            if visible_value.nth(i).is_visible():
                found = True
                break
        except Exception:
            pass

    if not found:
        raise RuntimeError(
            f'Attempted to select "{value}", but could not verify '
            f'the {description} selection.'
        )

    print(
        f"{description} selected:",
        value,
    )


def click_text(page, text: str, timeout=15000):
    patterns = [
        page.get_by_role(
            "button",
            name=re.compile(
                rf"^\s*{re.escape(text)}\s*$",
                re.I,
            ),
        ),
        page.get_by_text(
            re.compile(
                rf"^\s*{re.escape(text)}\s*$",
                re.I,
            )
        ),
    ]

    for locator in patterns:
        if click_first_visible(
            locator,
            timeout=timeout,
        ):
            return

    raise RuntimeError(
        f'Could not click "{text}".'
    )


def fill_amount(page, amount: int):
    print("Entering destination amount:", amount)

    # Prefer field associated with Amount.
    labelled = page.get_by_label(
        re.compile(r"amount", re.I)
    )

    for i in range(labelled.count()):
        item = labelled.nth(i)

        try:
            if item.is_visible():
                tag = item.evaluate(
                    "el => el.tagName.toLowerCase()"
                )

                if tag == "input":
                    item.fill(str(amount))
                    return
        except Exception:
            pass

    # Find visible numeric/text inputs and use the most likely amount field.
    inputs = page.locator(
        "input[type='number'], "
        "input[inputmode='decimal'], "
        "input[inputmode='numeric'], "
        "input[type='text']"
    )

    for i in range(inputs.count()):
        field = inputs.nth(i)

        try:
            if not field.is_visible():
                continue

            placeholder = (
                field.get_attribute("placeholder")
                or ""
            )
            name = (
                field.get_attribute("name")
                or ""
            )
            aria = (
                field.get_attribute("aria-label")
                or ""
            )

            metadata = " ".join(
                [
                    placeholder,
                    name,
                    aria,
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
                return
        except Exception:
            continue

    # Last fallback: visible input nearest the word "receives".
    receives = page.get_by_text(
        re.compile(
            r"receives",
            re.I,
        )
    )

    for i in range(receives.count()):
        label = receives.nth(i)

        try:
            if not label.is_visible():
                continue

            container = label.locator("xpath=..")

            for _ in range(6):
                inputs = container.locator("input")

                for j in range(inputs.count()):
                    candidate = inputs.nth(j)

                    if candidate.is_visible():
                        candidate.fill(
                            str(amount)
                        )
                        return

                container = container.locator(
                    "xpath=.."
                )
        except Exception:
            continue

    raise RuntimeError(
        "Could not locate the destination amount field."
    )


def select_payment_country(page, country: str):
    print(
        "Selecting payment country:",
        country,
    )

    # Try a labelled field first.
    labelled = page.get_by_label(
        re.compile(
            r"country|region|payment.*from",
            re.I,
        )
    )

    for i in range(labelled.count()):
        field = labelled.nth(i)

        try:
            if not field.is_visible():
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

                return
        except Exception:
            continue

    # Search visible comboboxes for a country control.
    combos = page.get_by_role(
        "combobox"
    )

    for i in range(combos.count()):
        field = combos.nth(i)

        try:
            if not field.is_visible():
                continue

            field.click()
            page.wait_for_timeout(400)

            # Try typing into focused/inner input.
            try:
                active = page.locator(":focus")
                if active.evaluate(
                    "el => el.tagName.toLowerCase()"
                ) == "input":
                    active.fill(country)
            except Exception:
                pass

            page.wait_for_timeout(500)

            try:
                choose_from_open_dropdown(
                    page,
                    country,
                )
                return
            except Exception:
                page.keyboard.press(
                    "Escape"
                )
        except Exception:
            continue

    raise RuntimeError(
        f'Could not select payment country "{country}".'
    )


def extract_offline_bank_transfer_quote(page) -> float:
    label = page.get_by_text(
        re.compile(
            r"Offline bank transfer",
            re.I,
        )
    )

    visible_label = None

    for i in range(label.count()):
        candidate = label.nth(i)

        try:
            if candidate.is_visible():
                visible_label = candidate
                break
        except Exception:
            pass

    if visible_label is None:
        raise RuntimeError(
            "Offline bank transfer payment method was not found."
        )

    node = visible_label

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
    config: QuoteConfig = USD_5000,
    headless=True,
):
    """
    Phase V3.1.

    Reads the displayed quote only.
    It does NOT submit/create a payment and does NOT enter personal details.
    """

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

    fetched_at = now_ist()

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

            # The payment form is JS-rendered.
            page.wait_for_timeout(
                3000
            )

            page.get_by_text(
                re.compile(
                    r"Make a Payment",
                    re.I,
                )
            ).first.wait_for(
                state="visible",
                timeout=30000,
            )

            # --------------------------------------------------
            # STEP 1: institution country
            # --------------------------------------------------
            select_landing_dropdown(
                page,
                index=0,
                value=config.institution_country,
                description="institution country",
            )

            page.wait_for_timeout(
                1000
            )

            # Institution list can reload after country selection.
            page.wait_for_timeout(
                1000
            )

            # --------------------------------------------------
            # STEP 2: institution
            # --------------------------------------------------
            select_landing_dropdown(
                page,
                index=1,
                value=config.institution,
                description="institution",
            )

            page.wait_for_timeout(
                700
            )

            # Save a checkpoint screenshot before continuing.
            try:
                page.screenshot(
                    path=str(
                        DEBUG_DIR
                        / "flywire_checkpoint_institution.png"
                    ),
                    full_page=True,
                )
            except Exception:
                pass

            # --------------------------------------------------
            # STEP 3: Continue
            # --------------------------------------------------
            click_text(
                page,
                "Continue",
            )

            page.wait_for_timeout(
                2200
            )

            # --------------------------------------------------
            # STEP 4: destination amount
            # --------------------------------------------------
            fill_amount(
                page,
                config.amount,
            )

            # --------------------------------------------------
            # STEP 5: payer/payment country = India
            # --------------------------------------------------
            select_payment_country(
                page,
                config.payment_country,
            )

            page.wait_for_timeout(
                700
            )

            try:
                click_text(
                    page,
                    "Next",
                )
            except Exception:
                click_text(
                    page,
                    "Continue",
                )

            page.wait_for_timeout(
                2200
            )

            # --------------------------------------------------
            # STEP 6: Full Loan Financing
            # --------------------------------------------------
            click_text(
                page,
                "Full Loan Financing",
            )

            page.wait_for_timeout(
                1000
            )

            # --------------------------------------------------
            # STEP 7: Bank
            # --------------------------------------------------
            click_text(
                page,
                "Bank",
            )

            page.wait_for_timeout(
                1000
            )

            # --------------------------------------------------
            # STEP 8: SBI loan
            # --------------------------------------------------
            click_text(
                page,
                "I have taken a loan from SBI",
            )

            page.wait_for_timeout(
                700
            )

            try:
                click_text(
                    page,
                    "Continue",
                )
            except Exception:
                pass

            page.wait_for_timeout(
                2200
            )

            # --------------------------------------------------
            # STEP 9: read quote only
            # --------------------------------------------------
            inr_quote = (
                extract_offline_bank_transfer_quote(
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
                    fetched_at.isoformat(),

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
                "FLYWIRE QUOTE CAPTURED"
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
                fetched_at.isoformat(),
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
