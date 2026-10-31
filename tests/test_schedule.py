from datetime import datetime, timedelta, timezone

from groundops.passes import Pass
from groundops.schedule import plan_contacts

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def mk(sat, start_min, end_min):
    return Pass(sat, "GS", T0 + timedelta(minutes=start_min), T0 + timedelta(minutes=end_min),
                T0 + timedelta(minutes=(start_min + end_min) / 2), 30.0, 0.0, 180.0)


def test_two_smaller_contacts_beat_one_blocking_contact():
    # greedy by priority would take BIG and lose both others (3 < 2 + 2)
    passes = [mk("BIG", 0, 10), mk("A", 0, 4), mk("B", 6, 10)]
    plan = plan_contacts(passes, {"BIG": 3, "A": 2, "B": 2}, turnaround_s=60)
    assert [p.satellite for p in plan.contacts] == ["A", "B"]
    assert plan.priority_total == 4
    assert [(p.satellite, why) for p, why in plan.dropped] == [
        ("BIG", "conflicts with a higher-value contact")]


def test_turnaround_time_is_respected():
    passes = [mk("A", 0, 5), mk("B", 6, 10)]
    tight = plan_contacts(passes, {"A": 1, "B": 1}, turnaround_s=120)
    assert len(tight.contacts) == 1
    loose = plan_contacts(passes, {"A": 1, "B": 1}, turnaround_s=30)
    assert len(loose.contacts) == 2
    for a, b in zip(loose.contacts, loose.contacts[1:]):
        assert (b.aos - a.los).total_seconds() >= 30


def test_equal_priority_prefers_more_contact_time():
    passes = [mk("A", 0, 3), mk("B", 1, 9)]
    plan = plan_contacts(passes, {"A": 1, "B": 1}, turnaround_s=0)
    assert [p.satellite for p in plan.contacts] == ["B"]


def test_short_and_unprioritised_passes_are_reported_not_silently_lost():
    passes = [mk("A", 0, 1), mk("X", 5, 10), mk("A", 20, 25)]
    plan = plan_contacts(passes, {"A": 1}, min_duration_s=120)
    reasons = {(p.satellite, p.aos): why for p, why in plan.dropped}
    assert reasons[("A", T0)] == "shorter than 120 s"
    assert reasons[("X", T0 + timedelta(minutes=5))] == "no priority assigned"
    assert [p.satellite for p in plan.contacts] == ["A"]


def test_every_pass_ends_up_scheduled_or_explained():
    passes = [mk("A", i * 3, i * 3 + 4) for i in range(12)]
    plan = plan_contacts(passes, {"A": 1}, turnaround_s=60)
    assert len(plan.contacts) + len(plan.dropped) == len(passes)
    for a, b in zip(plan.contacts, plan.contacts[1:]):
        assert (b.aos - a.los).total_seconds() >= 60
