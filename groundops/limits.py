"""Housekeeping telemetry limit checking.

Each parameter has yellow (caution) and red (out of limits) bands. A single noisy sample
should not page anyone, so a state change is only reported after `persistence` consecutive
samples agree; the same applies on the way back to nominal, which stops an alarm flapping
when a value sits on a limit. A parameter that stops arriving is reported as stale.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

NOMINAL, YELLOW, RED = "NOMINAL", "YELLOW", "RED"


@dataclass(frozen=True)
class Limit:
    parameter: str
    red_low: float
    yellow_low: float
    yellow_high: float
    red_high: float
    persistence: int = 1
    units: str = ""

    def __post_init__(self):
        if not self.red_low <= self.yellow_low <= self.yellow_high <= self.red_high:
            raise ValueError(f"{self.parameter}: limits must satisfy "
                             "red_low <= yellow_low <= yellow_high <= red_high")
        if self.persistence < 1:
            raise ValueError(f"{self.parameter}: persistence must be at least 1")

    def classify(self, value: float) -> str:
        if value < self.red_low or value > self.red_high:
            return RED
        if value < self.yellow_low or value > self.yellow_high:
            return YELLOW
        return NOMINAL


@dataclass(frozen=True)
class Sample:
    time: datetime
    parameter: str
    value: float


@dataclass(frozen=True)
class Event:
    time: datetime
    parameter: str
    kind: str          # "LIMIT" or "STALE" or "UNKNOWN"
    previous: str
    current: str
    value: float | None
    detail: str


def load_limits(path: str | Path) -> dict[str, Limit]:
    out = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            lim = Limit(row["parameter"], float(row["red_low"]), float(row["yellow_low"]),
                        float(row["yellow_high"]), float(row["red_high"]),
                        int(row.get("persistence") or 1), row.get("units", ""))
            out[lim.parameter] = lim
    return out


def load_samples(path: str | Path) -> list[Sample]:
    with open(path, newline="") as fh:
        return [Sample(datetime.fromisoformat(r["time"].replace("Z", "+00:00")),
                       r["parameter"], float(r["value"])) for r in csv.DictReader(fh)]


def check(samples: list[Sample], limits: dict[str, Limit], expected_period_s: float,
          stale_factor: float = 3.0, now: datetime | None = None) -> list[Event]:
    """Return state-change events in time order."""
    events: list[Event] = []
    reported: dict[str, str] = {}
    pending: dict[str, tuple[str, int, Sample]] = {}
    last_seen: dict[str, datetime] = {}
    unknown: set[str] = set()
    stale_after = expected_period_s * stale_factor

    for s in sorted(samples, key=lambda s: s.time):
        lim = limits.get(s.parameter)
        if lim is None:
            if s.parameter not in unknown:
                unknown.add(s.parameter)
                events.append(Event(s.time, s.parameter, "UNKNOWN", "", "", s.value,
                                    "no limit definition for this parameter"))
            continue

        prev_time = last_seen.get(s.parameter)
        if prev_time is not None and (s.time - prev_time).total_seconds() > stale_after:
            gap = (s.time - prev_time).total_seconds()
            events.append(Event(prev_time, s.parameter, "STALE", "", "", None,
                                f"no samples for {gap:.0f} s (expected every {expected_period_s:.0f} s)"))
        last_seen[s.parameter] = s.time

        state = lim.classify(s.value)
        current = reported.get(s.parameter, NOMINAL)
        if state == current:
            pending.pop(s.parameter, None)
            continue
        cand, count, first = pending.get(s.parameter, (state, 0, s))
        if cand != state:
            cand, count, first = state, 0, s
        count += 1
        if count >= lim.persistence:
            events.append(Event(first.time, s.parameter, "LIMIT", current, state, first.value,
                                f"{count} consecutive sample(s), first {first.value:g}{lim.units}"))
            reported[s.parameter] = state
            pending.pop(s.parameter, None)
        else:
            pending[s.parameter] = (cand, count, first)

    if now is not None:
        for param, seen in last_seen.items():
            if (now - seen).total_seconds() > stale_after:
                events.append(Event(seen, param, "STALE", "", "", None,
                                    f"nothing received since {seen:%H:%M:%S}Z"))
    return sorted(events, key=lambda e: e.time)


def current_states(events: list[Event]) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in events:
        if e.kind == "LIMIT":
            out[e.parameter] = e.current
    return out
