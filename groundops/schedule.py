"""Contact planning for a single antenna.

Passes of different satellites overlap, and the antenna needs time to slew and reconfigure
between contacts. Picking the highest-priority pass first is not optimal (one long
high-priority pass can block two others worth more together), so this solves the weighted
interval scheduling problem exactly: maximise total priority, then total contact time.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import timedelta

from .passes import Pass


@dataclass
class Plan:
    contacts: list[Pass] = field(default_factory=list)
    dropped: list[tuple[Pass, str]] = field(default_factory=list)
    priority_total: int = 0
    contact_seconds: float = 0.0


def plan_contacts(passes: list[Pass], priorities: dict[str, int], turnaround_s: float = 120.0,
                  min_duration_s: float = 120.0) -> Plan:
    plan = Plan()
    candidates = []
    for p in passes:
        if p.satellite not in priorities:
            plan.dropped.append((p, "no priority assigned"))
        elif p.duration_s < min_duration_s:
            plan.dropped.append((p, f"shorter than {min_duration_s:.0f} s"))
        else:
            candidates.append(p)

    candidates.sort(key=lambda p: p.los)
    gap = timedelta(seconds=turnaround_s)
    ends = [p.los + gap for p in candidates]
    # previous[i]: how many candidates finish (plus turnaround) before candidate i starts
    previous = [bisect_right(ends, p.aos) for p in candidates]

    def value_if_taken(i: int) -> tuple[int, float]:
        p = candidates[i - 1]
        before = best[previous[i - 1]]
        return before[0] + priorities[p.satellite], before[1] + p.duration_s

    best: list[tuple[int, float]] = [(0, 0.0)]
    for i in range(1, len(candidates) + 1):
        best.append(max(best[i - 1], value_if_taken(i)))

    chosen = []
    i = len(candidates)
    while i > 0:
        if value_if_taken(i) == best[i]:
            chosen.append(candidates[i - 1])
            i = previous[i - 1]
        else:
            i -= 1

    chosen_ids = {id(p) for p in chosen}
    plan.contacts = sorted(chosen, key=lambda p: p.aos)
    plan.dropped += [(p, "conflicts with a higher-value contact")
                     for p in candidates if id(p) not in chosen_ids]
    plan.dropped.sort(key=lambda d: d[0].aos)
    plan.priority_total, plan.contact_seconds = best[-1]
    return plan
