from datetime import datetime, timedelta, timezone

import pytest

from groundops import cli
from groundops.anomalies import CLOSED, ESCALATED, INVESTIGATING, AnomalyError, AnomalyLog

T0 = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)


def test_lifecycle_is_replayed_from_the_log(tmp_path):
    path = tmp_path / "log.jsonl"
    log = AnomalyLog(path)
    a = log.open("Battery undervoltage in eclipse", "major", T0, "telemetry", "ops1", T0)
    log.move(a.id, INVESTIGATING, "ops1", T0 + timedelta(minutes=5))
    log.move(a.id, CLOSED, "ops1", T0 + timedelta(hours=2),
             root_cause="heater duty cycle left at test value",
             corrective_action="restored nominal heater table, added to pass checklist")

    again = AnomalyLog(path)
    b = again.items[a.id]
    assert b.state == CLOSED
    assert b.root_cause.startswith("heater")
    assert [h.get("to") for h in b.history] == [None, INVESTIGATING, CLOSED]
    assert again.open_items() == []


def test_closing_needs_root_cause_and_corrective_action(tmp_path):
    log = AnomalyLog(tmp_path / "log.jsonl")
    a = log.open("Lost lock", "minor", T0, "ground station", "ops1", T0)
    with pytest.raises(AnomalyError, match="root cause"):
        log.move(a.id, CLOSED, "ops1", T0, root_cause="weather")


def test_critical_must_be_escalated_before_closing(tmp_path):
    log = AnomalyLog(tmp_path / "log.jsonl")
    a = log.open("Safe mode entry", "critical", T0, "telemetry", "ops1", T0)
    with pytest.raises(AnomalyError, match="escalated"):
        log.move(a.id, CLOSED, "ops1", T0, root_cause="x", corrective_action="y")
    with pytest.raises(AnomalyError, match="who"):
        log.move(a.id, ESCALATED, "ops1", T0)
    log.move(a.id, ESCALATED, "ops1", T0, escalated_to="flight dynamics on-call")
    log.move(a.id, CLOSED, "lead", T0, root_cause="x", corrective_action="y")
    assert log.items[a.id].state == CLOSED


def test_invalid_transition_and_reopen_without_reason(tmp_path):
    log = AnomalyLog(tmp_path / "log.jsonl")
    a = log.open("Clock drift", "minor", T0, "ground station", "ops1", T0)
    log.move(a.id, CLOSED, "ops1", T0, root_cause="NTP", corrective_action="fixed")
    with pytest.raises(AnomalyError, match="cannot go"):
        log.move(a.id, ESCALATED, "ops1", T0, escalated_to="x")
    with pytest.raises(AnomalyError, match="note"):
        log.move(a.id, INVESTIGATING, "ops1", T0)
    log.move(a.id, INVESTIGATING, "ops1", T0, note="drift came back after reboot")
    assert [x.id for x in log.open_items()] == [a.id]


def test_open_items_put_the_most_severe_first(tmp_path):
    log = AnomalyLog(tmp_path / "log.jsonl")
    log.open("minor thing", "minor", T0, "s", "ops", T0)
    log.open("critical thing", "critical", T0 + timedelta(hours=1), "s", "ops", T0)
    assert [a.severity for a in log.open_items()] == ["critical", "minor"]


def test_report_end_to_end(tmp_path, capsys):
    data = tmp_path / "data"
    assert cli.main(["sample", "--dir", str(data)]) == 0
    log = AnomalyLog(data / "anomalies.jsonl")
    log.open("Battery undervoltage during eclipse", "major", T0, "telemetry", "ops1", T0)
    out = tmp_path / "report.md"
    assert cli.main(["report", "--tle", str(data / "demo.tle"), "--limits", str(data / "limits.csv"),
                     "--telemetry", str(data / "telemetry.csv"),
                     "--anomalies", str(data / "anomalies.jsonl"), "--out", str(out)]) == 0
    text = out.read_text()
    assert "# Shift handover: Helsinki (demo)" in text
    assert "ANOM-0001 (major, OPEN)" in text
    assert "conflicts with a higher-value contact" in text
    assert "battery_voltage" in text and "no samples for" in text
