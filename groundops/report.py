"""Shift handover report in Markdown."""

from __future__ import annotations

from datetime import datetime

from .anomalies import Anomaly
from .limits import Event
from .passes import Pass
from .schedule import Plan


def _t(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%SZ")


def shift_report(station: str, start: datetime, end: datetime, passes: list[Pass], plan: Plan,
                 events: list[Event], open_anomalies: list[Anomaly],
                 tle_warnings: list[str]) -> str:
    out = [f"# Shift handover: {station}", "",
           f"Window {_t(start)} to {_t(end)}", ""]

    out += ["## Needs attention", ""]
    attention = list(tle_warnings)
    attention += [f"{e.parameter} is {e.current} since {_t(e.time)} ({e.detail})"
                  for e in _latest_limit_states(events) if e.current != "NOMINAL"]
    attention += [f"{e.parameter}: {e.detail}" for e in events if e.kind == "STALE"]
    attention += [f"{a.id} ({a.severity}, {a.state}): {a.title}" for a in open_anomalies]
    out += [f"- {line}" for line in attention] or ["- Nothing outstanding."]
    out.append("")

    out += ["## Contact plan", "",
            f"{len(plan.contacts)} contacts scheduled, {len(plan.dropped)} passes not used.", "",
            "| Satellite | AOS | LOS | Max el | Duration |",
            "|---|---|---|---|---|"]
    out += [f"| {p.satellite} | {_t(p.aos)} | {_t(p.los)} | {p.max_elevation:.1f} | "
            f"{p.duration_s / 60:.1f} min |" for p in plan.contacts]
    if plan.dropped:
        out += ["", "Not scheduled:", ""]
        out += [f"- {p.satellite} {_t(p.aos)}: {why}" for p, why in plan.dropped]
    out.append("")

    out += ["## Telemetry events", ""]
    limit_events = [e for e in events if e.kind in ("LIMIT", "UNKNOWN")]
    if limit_events:
        out += ["| Time | Parameter | Change | Detail |", "|---|---|---|---|"]
        out += [f"| {_t(e.time)} | {e.parameter} | "
                f"{f'{e.previous} to {e.current}' if e.kind == 'LIMIT' else 'unknown parameter'} | "
                f"{e.detail} |" for e in limit_events]
    else:
        out.append("No limit transitions.")
    out.append("")

    out += ["## All predicted passes", "",
            "| Satellite | AOS | TCA | LOS | Max el | AOS az | LOS az |",
            "|---|---|---|---|---|---|---|"]
    out += [f"| {p.satellite} | {_t(p.aos)} | {_t(p.tca)} | {_t(p.los)} | {p.max_elevation:.1f} | "
            f"{p.aos_azimuth:.0f} | {p.los_azimuth:.0f} |" for p in passes]
    out.append("")
    return "\n".join(out)


def _latest_limit_states(events: list[Event]) -> list[Event]:
    latest: dict[str, Event] = {}
    for e in events:
        if e.kind == "LIMIT":
            latest[e.parameter] = e
    return sorted(latest.values(), key=lambda e: e.parameter)
