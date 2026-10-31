"""Deterministic demo data.

The ISS element set is the widely published 2008 example. The DEMO satellites are fictional:
the same orbit shifted in node and phase so that their passes compete for one antenna.
The telemetry is synthetic housekeeping data with a few planted problems.
"""

from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .tle import with_checksum

ISS = ("ISS (ZARYA)",
       "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927",
       "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537")

DEMO_START = datetime(2008, 9, 20, 12, 0, tzinfo=timezone.utc)


def _variant(name: str, catalog: int, raan_shift: float, anomaly_shift: float):
    l1 = ISS[1][:2] + f"{catalog:05d}" + ISS[1][7:]
    raan = (float(ISS[2][17:25]) + raan_shift) % 360
    anomaly = (float(ISS[2][43:51]) + anomaly_shift) % 360
    l2 = ISS[2][:2] + f"{catalog:05d}" + ISS[2][7:17] + f"{raan:8.4f}" + ISS[2][25:43] \
        + f"{anomaly:8.4f}" + ISS[2][51:]
    return name, with_checksum(l1), with_checksum(l2)


def write_tles(path: Path) -> None:
    sets = [ISS, _variant("DEMO-A", 90001, 2.0, 8.0), _variant("DEMO-B", 90002, -6.0, 300.0)]
    path.write_text("".join(f"{n}\n{a}\n{b}\n" for n, a, b in sets))


def write_telemetry(path: Path, hours: int = 6, period_s: int = 10, seed: int = 7) -> None:
    rng = random.Random(seed)
    rows = []
    n = hours * 3600 // period_s
    for i in range(n):
        t = DEMO_START + timedelta(seconds=i * period_s)
        orbit_phase = 2 * math.pi * (i * period_s) / (91.5 * 60)
        sunlit = math.sin(orbit_phase) > -0.3
        battery_v = 7.9 + (0.25 if sunlit else -0.35) + rng.gauss(0, 0.02)
        battery_t = 12 + 6 * math.sin(orbit_phase) + rng.gauss(0, 0.3)
        obc_t = 31 + rng.gauss(0, 0.4)
        if i == 300:
            obc_t = 58.0                      # one corrupted sample: should not alarm
        if 1500 <= i < 1530:
            battery_v -= 0.6                  # five-minute undervoltage: should alarm
        if 1200 <= i < 1260:
            continue                          # ten-minute dropout of every parameter
        rows += [(t, "battery_voltage", round(battery_v, 3)),
                 (t, "battery_temp", round(battery_t, 2)),
                 (t, "obc_temp", round(obc_t, 2))]
        if i == 2000:
            rows.append((t, "rw_speed", 4100.0))  # parameter with no limit definition
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time", "parameter", "value"])
        w.writerows((t.isoformat().replace("+00:00", "Z"), p, v) for t, p, v in rows)


LIMITS = """parameter,red_low,yellow_low,yellow_high,red_high,persistence,units
battery_voltage,7.0,7.4,8.4,8.6,3, V
battery_temp,-5,0,30,40,3, C
obc_temp,-20,-10,50,60,3, C
"""


def write_all(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    write_tles(directory / "demo.tle")
    write_telemetry(directory / "telemetry.csv")
    (directory / "limits.csv").write_text(LIMITS)
