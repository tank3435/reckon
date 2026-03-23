from datetime import datetime, timezone

from reckon.ingestion.acled import (
    EVENT_TYPES,
    KEY_REGIONS,
    _date_range,
    _make,
    _stub_data,
)


def test_date_range_span():
    start, end = _date_range()
    from datetime import date
    d_start = date.fromisoformat(start)
    d_end = date.fromisoformat(end)
    assert (d_end - d_start).days == 90


def test_date_range_end_is_today():
    from datetime import date
    _, end = _date_range()
    assert date.fromisoformat(end) == date.today()


def test_make_fields():
    now = datetime.now(timezone.utc)
    ind = _make("acled_battles", 450, now)
    assert ind.source == "acled"
    assert ind.source_id == "acled:acled_battles"
    assert ind.raw_value == 450.0
    assert ind.unit == "count"
    assert ind.tier == "military"


def test_stub_data_count():
    # 6 event types + total_events + total_fatalities + 4 regions = 12
    assert len(_stub_data()) == 12


def test_stub_data_source():
    assert all(r.source == "acled" for r in _stub_data())


def test_stub_data_stable_source_ids():
    ids = [r.source_id for r in _stub_data()]
    assert len(ids) == len(set(ids)), "source_id values must be unique for upsert to work"


def test_stub_data_covers_all_event_types():
    names = {r.name for r in _stub_data()}
    for indicator_name in EVENT_TYPES.values():
        assert indicator_name in names


def test_stub_data_covers_all_regions():
    names = {r.name for r in _stub_data()}
    for indicator_name in KEY_REGIONS.values():
        assert indicator_name in names


def test_stub_data_non_negative_values():
    assert all(r.raw_value >= 0 for r in _stub_data())
