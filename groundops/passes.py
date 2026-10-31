"""Pass prediction: when a satellite rises above and sets below a station's elevation mask."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from sgp4.api import SGP4_ERRORS

from .frames import Station, julian_date, look_angles, teme_to_ecef
from .tle import Satellite


class PropagationError(RuntimeError):
    pass


def look(sat: Satellite, station: Station, t: datetime) -> tuple[float, float, float]:
    jd = julian_date(t)
    whole = math.floor(jd)
    err, r, _ = sat.satrec.sgp4(whole, jd - whole)
    if err:
        raise PropagationError(f"{sat.name} at {t:%Y-%m-%d %H:%M:%S}Z: {SGP4_ERRORS[err]}")
    return look_angles(teme_to_ecef(r, jd), station)


def elevation(sat: Satellite, station: Station, t: datetime) -> float:
    return look(sat, station, t)[1]


@dataclass(frozen=True)
class Pass:
    satellite: str
    station: str
    aos: datetime
    los: datetime
    tca: datetime
    max_elevation: float
    aos_azimuth: float
    los_azimuth: float
    starts_before_window: bool = False
    ends_after_window: bool = False

    @property
    def duration_s(self) -> float:
        return (self.los - self.aos).total_seconds()


def _crossing(sat, station, lo: datetime, hi: datetime, mask: float, rising: bool,
              tol_s: float) -> datetime:
    """Bisect for the moment elevation crosses the mask between lo and hi."""
    while (hi - lo).total_seconds() > tol_s:
        mid = lo + (hi - lo) / 2
        above = elevation(sat, station, mid) >= mask
        if above == rising:
            hi = mid
        else:
            lo = mid
    return hi if rising else lo


def _culmination(sat, station, a: datetime, b: datetime, tol_s: float) -> datetime:
    """Golden-section search for maximum elevation; a single pass is unimodal."""
    inv_phi = (math.sqrt(5) - 1) / 2
    c = b - (b - a) * inv_phi
    d = a + (b - a) * inv_phi
    while (b - a).total_seconds() > tol_s:
        if elevation(sat, station, c) > elevation(sat, station, d):
            b = d
        else:
            a = c
        c = b - (b - a) * inv_phi
        d = a + (b - a) * inv_phi
    return a + (b - a) / 2


def find_passes(sat: Satellite, station: Station, start: datetime, end: datetime,
                min_elevation: float = 10.0, step_s: float = 30.0,
                tol_s: float = 0.1) -> list[Pass]:
    """Scan the window at `step_s` and refine each mask crossing by bisection.

    A pass shorter than the step can be missed; 30 s suits low Earth orbit at a 10 degree mask.
    """
    step = timedelta(seconds=step_s)
    passes: list[Pass] = []
    t, el = start, elevation(sat, station, start)
    aos = start if el >= min_elevation else None
    while t < end:
        t2 = min(t + step, end)
        el2 = elevation(sat, station, t2)
        if el < min_elevation <= el2:
            aos = _crossing(sat, station, t, t2, min_elevation, True, tol_s)
        elif el >= min_elevation > el2 and aos is not None:
            los = _crossing(sat, station, t, t2, min_elevation, False, tol_s)
            passes.append(_build(sat, station, aos, los, start, end))
            aos = None
        t, el = t2, el2
    if aos is not None:
        passes.append(_build(sat, station, aos, end, start, end))
    return passes


def _build(sat, station, aos, los, start, end) -> Pass:
    tca = _culmination(sat, station, aos, los, 0.5)
    return Pass(
        satellite=sat.name,
        station=station.name,
        aos=aos,
        los=los,
        tca=tca,
        max_elevation=elevation(sat, station, tca),
        aos_azimuth=look(sat, station, aos)[0],
        los_azimuth=look(sat, station, los)[0],
        starts_before_window=aos == start,
        ends_after_window=los == end,
    )


def passes_for(sats: list[Satellite], station: Station, start: datetime, end: datetime,
               min_elevation: float = 10.0) -> list[Pass]:
    out = [p for s in sats for p in find_passes(s, station, start, end, min_elevation)]
    return sorted(out, key=lambda p: p.aos)
