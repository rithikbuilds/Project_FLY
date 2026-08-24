def verify_rate_table(text):

    lower = text.lower()

    required_headers = [
        "currency",
        "ttsell",
        "bill sell",
        "ttbuy",
    ]

    for header in required_headers:

        if header not in lower:

            raise RuntimeError(
                "Bank of Baroda expected header not found: "
                + header
            )

    print(
        "BOB Currency / TTSell / TTBuy headers verified."
    )
