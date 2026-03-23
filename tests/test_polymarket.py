from reckon.ingestion.polymarket import _filter_markets, _is_yes_no, _yes_price

GOOD_MARKET = {
    "conditionId": "0xabc",
    "active": True,
    "closed": False,
    "outcomes": ["Yes", "No"],
    "outcomePrices": ["0.07", "0.93"],
    "liquidity": 50000,
}


def test_yes_price_extracts_yes_outcome():
    assert _yes_price(GOOD_MARKET) == 0.07


def test_yes_price_handles_reversed_order():
    market = {**GOOD_MARKET, "outcomes": ["No", "Yes"], "outcomePrices": ["0.93", "0.07"]}
    assert _yes_price(market) == 0.07


def test_yes_price_returns_none_on_bad_data():
    assert _yes_price({"outcomes": [], "outcomePrices": []}) is None


def test_is_yes_no_case_insensitive():
    assert _is_yes_no(["YES", "no"])
    assert _is_yes_no(["Yes", "No"])
    assert not _is_yes_no(["Candidate A", "Candidate B"])


def test_filter_markets_excludes_closed():
    closed = {**GOOD_MARKET, "closed": True}
    assert _filter_markets([closed], set()) == []


def test_filter_markets_excludes_low_liquidity():
    thin = {**GOOD_MARKET, "liquidity": 10}
    assert _filter_markets([thin], set()) == []


def test_filter_markets_excludes_non_binary():
    multi = {**GOOD_MARKET, "outcomes": ["A", "B", "C"], "outcomePrices": ["0.3", "0.3", "0.4"]}
    assert _filter_markets([multi], set()) == []


def test_filter_markets_excludes_seen():
    seen = {"0xabc"}
    assert _filter_markets([GOOD_MARKET], seen) == []


def test_filter_markets_passes_valid():
    result = _filter_markets([GOOD_MARKET], set())
    assert len(result) == 1
    assert result[0]["conditionId"] == "0xabc"
