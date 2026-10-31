from datetime import datetime, timedelta, timezone

import pytest

from groundops import limits
from groundops.limits import NOMINAL, RED, YELLOW, Limit, Sample

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
VOLT = Limit("v", 7.0, 7.4, 8.4, 8.6, persistence=3, units=" V")


def series(values, param="v", period=10, start=0):
    return [Sample(T0 + timedelta(seconds=(start + i) * period), param, v)
            for i, v in enumerate(values)]


def test_bands():
    assert VOLT.classify(8.0) == NOMINAL
    assert VOLT.classify(7.2) == YELLOW
    assert VOLT.classify(8.5) == YELLOW
    assert VOLT.classify(6.9) == RED
    assert VOLT.classify(8.7) == RED


def test_limits_must_be_ordered():
    with pytest.raises(ValueError):
        Limit("bad", 7.0, 8.5, 8.4, 8.6)


def test_a_single_spike_does_not_alarm():
    events = limits.check(series([8.0, 8.0, 6.0, 8.0, 8.0]), {"v": VOLT}, 10)
    assert events == []


def test_a_sustained_excursion_alarms_at_its_first_sample_and_clears():
    values = [8.0, 6.8, 6.8, 6.8, 6.8, 8.0, 8.0, 8.0]
    events = limits.check(series(values), {"v": VOLT}, 10)
    assert [(e.previous, e.current) for e in events] == [(NOMINAL, RED), (RED, NOMINAL)]
    assert events[0].time == T0 + timedelta(seconds=10)
    assert events[0].value == 6.8


def test_value_sitting_on_a_limit_does_not_flap():
    values = [7.39, 7.41, 7.39, 7.41, 7.39, 7.41]
    assert limits.check(series(values), {"v": VOLT}, 10) == []


def test_gap_in_telemetry_is_reported_as_stale():
    samples = series([8.0, 8.0]) + series([8.0], start=10)
    events = limits.check(samples, {"v": VOLT}, 10)
    assert [e.kind for e in events] == ["STALE"]
    assert "90 s" in events[0].detail


def test_silence_up_to_now_is_stale():
    samples = series([8.0, 8.0])
    events = limits.check(samples, {"v": VOLT}, 10, now=T0 + timedelta(minutes=5))
    assert [e.kind for e in events] == ["STALE"]


def test_unknown_parameter_is_reported_once():
    samples = series([1, 2, 3], param="rw_speed")
    events = limits.check(samples, {"v": VOLT}, 10)
    assert [(e.kind, e.parameter) for e in events] == [("UNKNOWN", "rw_speed")]


def test_demo_telemetry(tmp_path):
    from groundops import sample
    sample.write_all(tmp_path)
    events = limits.check(limits.load_samples(tmp_path / "telemetry.csv"),
                          limits.load_limits(tmp_path / "limits.csv"), 10)
    kinds = [(e.kind, e.parameter, e.current) for e in events]
    # the one-sample OBC spike is filtered out, the dropout and undervoltage are caught
    assert not any(p == "obc_temp" and k == "LIMIT" for k, p, _ in kinds)
    assert ("LIMIT", "battery_voltage", RED) in kinds
    assert ("LIMIT", "battery_voltage", NOMINAL) in kinds
    assert sum(1 for k, *_ in kinds if k == "STALE") == 3
    assert ("UNKNOWN", "rw_speed", "") in kinds
