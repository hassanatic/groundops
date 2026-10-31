"""Compare pass times with Skyfield, which does the full frame reduction this package skips."""

from datetime import timedelta

import pytest

from groundops import sample, tle
from groundops.cli import STATIONS
from groundops.passes import find_passes

skyfield = pytest.importorskip("skyfield.api")


def test_pass_times_agree_with_skyfield_to_a_second():
    ts = skyfield.load.timescale(builtin=True)
    station = STATIONS["helsinki"]
    where = skyfield.wgs84.latlon(station.lat_deg, station.lon_deg, elevation_m=station.alt_km * 1000)
    start, end = sample.DEMO_START, sample.DEMO_START + timedelta(hours=24)

    for name, l1, l2 in [sample.ISS]:
        sat = skyfield.EarthSatellite(l1, l2, name, ts)
        times, kinds = sat.find_events(where, ts.from_datetime(start), ts.from_datetime(end),
                                       altitude_degrees=10.0)
        theirs = [t.utc_datetime() for t in times]
        ours = find_passes(tle.parse(name, l1, l2), station, start, end, min_elevation=10.0)

        assert len(theirs) == 3 * len(ours)
        for i, p in enumerate(ours):
            for mine, ref in zip((p.aos, p.tca, p.los), theirs[3 * i:3 * i + 3]):
                assert abs((mine - ref).total_seconds()) < 2.0
            alt, _, _ = (sat - where).at(ts.from_datetime(p.tca)).altaz()
            assert p.max_elevation == pytest.approx(alt.degrees, abs=0.05)
