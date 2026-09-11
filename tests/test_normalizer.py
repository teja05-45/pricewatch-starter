from pricewatch.agents.normalizer import parse_money, detect_currency


def test_usd_plain():
    assert parse_money("$596.85") == (59685, "USD")


def test_usd_thousands():
    assert parse_money("$1,299.00") == (129900, "USD")


def test_european_comma_decimal():
    assert parse_money("720,92 €") == (72092, "EUR")
    assert parse_money("937,20 €") == (93720, "EUR")
    assert parse_money("1.299,00 €") == (129900, "EUR")


def test_european_space_thousands():
    assert parse_money("1 299,50 €") == (129950, "EUR")


def test_zero_decimal_jpy():
    assert parse_money("¥1,500") == (1500, "JPY")
    assert parse_money("1500 JPY") == (1500, "JPY")


def test_currency_detection():
    assert detect_currency("£45.99") == "GBP"
    assert detect_currency("₹1,499.00") == "INR"
    assert detect_currency("450 SEK") == "SEK"
    assert detect_currency("NOK 200,00") == "NOK"
    assert detect_currency("CHF 50.00") == "CHF"


def test_no_number():
    assert parse_money("Price unavailable", "USD") == (None, "USD")
    assert parse_money(None, "EUR") == (None, "EUR")


def test_malformed_prices():
    assert parse_money("Price on request", "USD") == (None, "USD")
    assert parse_money("", "USD") == (None, "USD")


def test_spaced_dollar_decimals():
    assert parse_money("$ 125 . 51", "USD") == (12551, "USD")
    assert parse_money("$ 1,420 . 14", "USD") == (142014, "USD")
    assert parse_money("$ 264 . 76", "USD") == (26476, "USD")


def test_comma_spaced_decimal():
    assert parse_money("$ 1,506 . 12", "USD") == (150612, "USD")
    assert parse_money("1,420.14", "USD") == (142014, "USD")


