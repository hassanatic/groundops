"""Command line entry point: groundops {sample,passes,plan,check,report}."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import limits, sample, tle
from .anomalies import AnomalyLog
from .frames import Station
from .passes import passes_for
from .report import shift_report
from .schedule import plan_contacts

STATIONS = {
    "helsinki": Station("Helsinki (demo)", 60.1699, 24.9384, 0.03),
    "oulu": Station("Oulu (demo)", 65.0121, 25.4651, 0.02),
}


def _time(s: str) -> datetime:
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _priorities(s: str) -> dict[str, int]:
    out = {}
    for part in filter(None, s.split(",")):
        name, _, value = part.rpartition("=")
        out[name.strip()] = int(value)
    return out


def _window(args):
    start = _time(args.start)
    return start, start + timedelta(hours=args.hours)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="groundops")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sample", help="write the demo TLEs, limits and telemetry")
    s.add_argument("--dir", default="data")

    for name in ("passes", "plan", "report"):
        p = sub.add_parser(name)
        p.add_argument("--tle", default="data/demo.tle")
        p.add_argument("--station", choices=sorted(STATIONS), default="helsinki")
        p.add_argument("--start", default=sample.DEMO_START.isoformat())
        p.add_argument("--hours", type=float, default=24)
        p.add_argument("--min-el", type=float, default=10.0)
        if name != "passes":
            p.add_argument("--priorities", default="ISS (ZARYA)=3,DEMO-A=2,DEMO-B=1")
            p.add_argument("--turnaround", type=float, default=120)
        if name == "report":
            p.add_argument("--limits", default="data/limits.csv")
            p.add_argument("--telemetry", default="data/telemetry.csv")
            p.add_argument("--period", type=float, default=10)
            p.add_argument("--anomalies", default="data/anomalies.jsonl")
            p.add_argument("--out")

    c = sub.add_parser("check", help="check telemetry against limits")
    c.add_argument("--limits", default="data/limits.csv")
    c.add_argument("--telemetry", default="data/telemetry.csv")
    c.add_argument("--period", type=float, default=10)

    args = ap.parse_args(argv)

    if args.cmd == "sample":
        sample.write_all(Path(args.dir))
        print(f"wrote demo data to {args.dir}/")
        return 0

    if args.cmd == "check":
        events = limits.check(limits.load_samples(args.telemetry), limits.load_limits(args.limits),
                              args.period)
        for e in events:
            print(f"{e.time:%Y-%m-%d %H:%M:%S}Z  {e.kind:7} {e.parameter:16} "
                  f"{e.previous or '':8} -> {e.current or '':8} {e.detail}")
        return 1 if any(e.current == limits.RED for e in events) else 0

    sats = tle.load(args.tle)
    station = STATIONS[args.station]
    start, end = _window(args)
    warnings = tle.age_warnings(sats, start)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    passes = passes_for(sats, station, start, end, args.min_el)

    if args.cmd == "passes":
        for p in passes:
            print(f"{p.satellite:12} AOS {p.aos:%m-%d %H:%M:%S}  LOS {p.los:%H:%M:%S}  "
                  f"max {p.max_elevation:5.1f} deg  az {p.aos_azimuth:5.1f} -> {p.los_azimuth:5.1f}  "
                  f"{p.duration_s / 60:4.1f} min")
        return 0

    plan = plan_contacts(passes, _priorities(args.priorities), args.turnaround)
    if args.cmd == "plan":
        for p in plan.contacts:
            print(f"CONTACT  {p.satellite:12} {p.aos:%m-%d %H:%M:%S} - {p.los:%H:%M:%S}")
        for p, why in plan.dropped:
            print(f"dropped  {p.satellite:12} {p.aos:%m-%d %H:%M:%S}  {why}")
        print(f"total priority {plan.priority_total}, contact time {plan.contact_seconds / 60:.1f} min")
        return 0

    events = limits.check(limits.load_samples(args.telemetry), limits.load_limits(args.limits),
                          args.period)
    log = AnomalyLog(args.anomalies)
    text = shift_report(station.name, start, end, passes, plan, events, log.open_items(), warnings)
    if args.out:
        Path(args.out).write_text(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
