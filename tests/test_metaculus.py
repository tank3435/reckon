from reckon.ingestion.metaculus import (
    _clamp01,
    _community_probability,
    _extract_from_latest,
    _forecaster_count,
    _is_binary,
    _stub_data,
)


# ---------------------------------------------------------------------------
# _is_binary
# ---------------------------------------------------------------------------

def test_is_binary_true():
    assert _is_binary({"question_type": "binary"})


def test_is_binary_false_for_continuous():
    assert not _is_binary({"question_type": "continuous"})


def test_is_binary_false_when_missing():
    assert not _is_binary({})


# ---------------------------------------------------------------------------
# _forecaster_count
# ---------------------------------------------------------------------------

def test_forecaster_count_current_api():
    assert _forecaster_count({"nr_forecasters": 312}) == 312


def test_forecaster_count_legacy_api():
    assert _forecaster_count({"number_of_forecasters": 450}) == 450


def test_forecaster_count_prefers_current():
    assert _forecaster_count({"nr_forecasters": 100, "number_of_forecasters": 50}) == 100


def test_forecaster_count_zero_when_absent():
    assert _forecaster_count({}) == 0


# ---------------------------------------------------------------------------
# _extract_from_latest
# ---------------------------------------------------------------------------

def test_extract_from_latest_direct_float():
    assert _extract_from_latest(0.07) == 0.07


def test_extract_from_latest_value_key():
    assert _extract_from_latest({"value": 0.15}) == 0.15


def test_extract_from_latest_q2_key():
    assert _extract_from_latest({"q2": 0.12}) == 0.12


def test_extract_from_latest_centers_array():
    assert _extract_from_latest({"centers": [0.09, 0.15, 0.22]}) == 0.09


def test_extract_from_latest_means_array():
    assert _extract_from_latest({"means": [0.06]}) == 0.06


def test_extract_from_latest_none_input():
    assert _extract_from_latest(None) is None


def test_extract_from_latest_empty_dict():
    assert _extract_from_latest({}) is None


# ---------------------------------------------------------------------------
# _community_probability — end-to-end format coverage
# ---------------------------------------------------------------------------

def test_probability_current_api_aggregations():
    q = {
        "aggregations": {
            "recency_weighted": {
                "latest": {"value": 0.07}
            }
        }
    }
    assert _community_probability(q) == 0.07


def test_probability_current_api_centers():
    q = {
        "aggregations": {
            "recency_weighted": {
                "latest": {"centers": [0.04]}
            }
        }
    }
    assert _community_probability(q) == 0.04


def test_probability_falls_back_to_unweighted():
    q = {
        "aggregations": {
            "recency_weighted": {"latest": None},
            "unweighted": {"latest": {"value": 0.11}},
        }
    }
    assert _community_probability(q) == 0.11


def test_probability_legacy_float():
    q = {"community_prediction": 0.03}
    assert _community_probability(q) == 0.03


def test_probability_legacy_nested_full():
    q = {"community_prediction": {"full": {"q2": 0.08}}}
    assert _community_probability(q) == 0.08


def test_probability_legacy_nested_direct_q2():
    q = {"community_prediction": {"q2": 0.05}}
    assert _community_probability(q) == 0.05


def test_probability_returns_none_when_absent():
    assert _community_probability({}) is None


def test_probability_clamps_above_one():
    q = {"community_prediction": 1.5}
    assert _community_probability(q) == 1.0


def test_probability_clamps_below_zero():
    q = {"community_prediction": -0.1}
    assert _community_probability(q) == 0.0


# ---------------------------------------------------------------------------
# _stub_data
# ---------------------------------------------------------------------------

def test_stub_data_returns_ten_rows():
    # 5 topics × 2 indicators (probability + forecasters)
    assert len(_stub_data()) == 10


def test_stub_data_has_correct_sources():
    assert all(r.source == "metaculus" for r in _stub_data())


def test_stub_data_probabilities_in_range():
    probs = [r.raw_value for r in _stub_data() if r.unit == "probability_%"]
    assert all(0 <= p <= 100 for p in probs)
