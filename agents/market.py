import requests
from datetime import datetime
from zoneinfo import ZoneInfo


# ==========================================================
# CONFIGURATION
# ==========================================================

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


# Primary source
PRIMARY_URL = (
    "https://open.er-api.com/v6/latest/USD"
)


# Fallback source
FALLBACK_URL = (
    "https://api.frankfurter.app/latest"
)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/129 Safari/537.36"
    ),
    "Accept": "application/json",
}


# ==========================================================
# TIME
# ==========================================================

def now_ist():
    return datetime.now(IST)


# ==========================================================
# PRIMARY SOURCE
# OPEN EXCHANGE RATE API
# ==========================================================

def fetch_primary():

    print()
    print(
        "Market Agent: trying primary reference source"
    )

    print(
        PRIMARY_URL
    )


    response = requests.get(
        PRIMARY_URL,
        headers=HEADERS,
        timeout=30
    )


    response.raise_for_status()


    data = response.json()


    if data.get("result") != "success":

        raise RuntimeError(
            "Primary market-rate source "
            "did not return success."
        )


    rates = data.get(
        "rates",
        {}
    )


    if "INR" not in rates:

        raise RuntimeError(
            "INR missing from primary "
            "market-rate response."
        )


    usd_inr = float(
        rates["INR"]
    )


    result = {}


    for currency in CURRENCIES:


        if currency == "USD":

            result[currency] = (
                usd_inr
            )

            continue


        currency_per_usd = (
            rates.get(
                currency
            )
        )


        if not currency_per_usd:

            print(
                "Market primary missing:",
                currency
            )

            continue


        # API base = USD
        #
        # Example:
        # 1 USD = X CAD
        # 1 USD = Y INR
        #
        # Therefore:
        #
        # 1 CAD = Y / X INR

        currency_inr = (
            usd_inr
            /
            float(
                currency_per_usd
            )
        )


        result[currency] = (
            currency_inr
        )


    timestamp = (
        data.get(
            "time_last_update_utc"
        )
    )


    return {
        "source":
            "Open Exchange Rates Reference",

        "source_url":
            PRIMARY_URL,

        "source_timestamp":
            timestamp,

        "fetched_at":
            now_ist().isoformat(),

        "rates":
            result,
    }


# ==========================================================
# FALLBACK
# FRANKFURTER
# ==========================================================

def fetch_fallback():

    print()
    print(
        "Market Agent: trying fallback source"
    )


    result = {}


    for currency in CURRENCIES:


        url = (
            FALLBACK_URL
            + "?from="
            + currency
            + "&to=INR"
        )


        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )


        response.raise_for_status()


        data = response.json()


        rates = data.get(
            "rates",
            {}
        )


        rate = rates.get(
            "INR"
        )


        if rate is None:

            print(
                "Market fallback missing:",
                currency
            )

            continue


        result[currency] = float(
            rate
        )


    if not result:

        raise RuntimeError(
            "Fallback market-rate source "
            "returned no rates."
        )


    return {
        "source":
            "Frankfurter Reference Rate",

        "source_url":
            FALLBACK_URL,

        "source_timestamp":
            None,

        "fetched_at":
            now_ist().isoformat(),

        "rates":
            result,
    }


# ==========================================================
# VALIDATION
# ==========================================================

def validate_rates(rates):

    ranges = {

        "USD":
            (70, 130),

        "CAD":
            (40, 100),

        "AUD":
            (40, 100),

        "GBP":
            (90, 180),

        "EUR":
            (80, 160),

        "SGD":
            (45, 110),

        "AED":
            (15, 40),

        "NZD":
            (30, 90),

    }


    valid = {}


    for currency, rate in rates.items():


        if currency not in ranges:

            continue


        low, high = (
            ranges[currency]
        )


        if (
            low
            <= rate
            <= high
        ):


            valid[currency] = (
                round(
                    float(rate),
                    4
                )
            )


        else:


            print(
                "Market Agent rejected:",
                currency,
                rate
            )


    return valid


# ==========================================================
# MAIN AGENT
# ==========================================================

def collect():

    print()

    print(
        "=============================="
    )

    print(
        "MARKET RATE AGENT"
    )

    print(
        "=============================="
    )


    try:


        result = (
            fetch_primary()
        )


        print(
            "Primary market source worked."
        )


    except Exception as error:


        print(
            "Primary market source failed:"
        )


        print(
            str(error)
        )


        result = (
            fetch_fallback()
        )


        print(
            "Fallback market source worked."
        )


    valid_rates = (
        validate_rates(
            result["rates"]
        )
    )


    if not valid_rates:


        raise RuntimeError(
            "Market Agent returned "
            "no valid INR reference rates."
        )


    result[
        "rates"
    ] = valid_rates


    print()

    print(
        "Reference market rates:"
    )


    for currency in CURRENCIES:


        if currency not in valid_rates:

            continue


        print(
            currency,
            valid_rates[
                currency
            ]
        )


    print(
        "Market Agent completed:",
        len(valid_rates),
        "rates"
    )


    return result
