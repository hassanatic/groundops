# groundops

Small tools for the routine side of ground segment operations: when will the satellites be
overhead, which of those passes should the antenna take, is the housekeeping telemetry inside
its limits, what anomalies are still open, and what does the next shift need to know.

I wrote it to learn how mission operations support work fits together. It is a practice
project, not flight software.

## What it does

| Module | Job |
|---|---|
| `tle.py` | Reads two-line element sets, checks line length, line numbers, catalog numbers and checksums, and warns when elements are too old for the planning window. |
| `frames.py` | Converts SGP4 output (TEME) to Earth-fixed coordinates using Greenwich mean sidereal time, and from there to azimuth, elevation and range for a station on the WGS84 ellipsoid. |
| `passes.py` | Scans a time window, finds each rise above and set below the elevation mask, refines AOS and LOS by bisection to 0.1 s, and finds the culmination with a golden-section search. |
| `schedule.py` | Plans contacts for one antenna. Passes overlap and the antenna needs turnaround time, so it solves weighted interval scheduling exactly (most total priority, then most contact time) rather than greedily. Every pass ends up either scheduled or listed with the reason it was not. |
| `limits.py` | Checks telemetry against yellow and red bands. A change of state is only reported after N consecutive samples agree, in both directions, so a single bad sample does not alarm and a value sitting on a limit does not flap. Gaps in the data are reported as stale, and parameters without a limit definition are reported once. |
| `anomalies.py` | An append-only anomaly log (JSON lines). Open, investigating, escalated, closed. Closing needs a root cause and a corrective action, a critical anomaly has to be escalated before it can be closed, and reopening needs a reason. State is rebuilt by replaying the log. |
| `report.py` | A Markdown shift handover: what needs attention, the contact plan, telemetry transitions and all predicted passes. |

## Try it

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
groundops sample --dir data      # demo element sets, limits and telemetry
groundops passes --hours 24
groundops plan --hours 24
groundops check                  # exits 1 if anything is red
groundops report --hours 24
pytest -q
```

The demo uses the widely published ISS element set from September 2008, so the default window
is 20-21 September 2008. `DEMO-A` and `DEMO-B` are fictional satellites made from the same
orbit with a shifted node and phase, so that their passes compete for one antenna. The
telemetry is synthetic, with a one-sample glitch that should be ignored, a ten-minute dropout
and a five-minute undervoltage that should both be caught.

## How it is checked

- 33 tests, run on Python 3.11 and 3.12 in GitHub Actions.
- Sidereal time is checked against the published value at J2000, and the geodetic conversion
  and look angles against cases with known answers.
- Pass times are compared with [Skyfield](https://rhodesmill.org/skyfield/), which does the
  full frame reduction this package skips. For the demo window AOS, culmination and LOS agree
  to within a second and maximum elevation to within 0.05 degrees.

## Limits

- UT1 is taken as UTC and polar motion is ignored. Both are far below the accuracy of a TLE.
- The pass scan steps every 30 s, so a pass that clips the mask for less than that can be missed.
- One antenna, no slew model beyond a fixed turnaround time, no link budget.
- Telemetry comes from CSV files, not a live feed.

## Licence

MIT
