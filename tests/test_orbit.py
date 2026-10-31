import math
from datetime import datetime, timedelta, timezone

import pytest

from groundops import sample, tle
from groundops.frames import Station, geodetic_to_ecef, gmst_rad, look_angles
from groundops.passes import elevation, find_passes

HELSINKI = Station("Helsinki", 60.1699, 24.9384, 0.03)
START = sample.DEMO_START


@pytest.fixture(scope="module")
def iss():
    return tle.parse(*sample.ISS)


def test_checksum_accepts_published_lines_and_rejects_a_changed_digit():
    for line in sample.ISS[1:]:
        assert tle.checksum(line) == int(line[68])
    broken = sample.ISS[2][:20] + "9" + sample.ISS[2][21:]
    with pytest.raises(tle.TLEError, match="checksum"):
        tle.parse("X", sample.ISS[1], broken)


def test_mismatched_catalog_numbers_are_rejected():
    other = tle.with_checksum(sample.ISS[2][:2] + "99999" + sample.ISS[2][7:])
    with pytest.raises(tle.TLEError, match="catalog"):
        tle.parse("X", sample.ISS[1], other)


def test_epoch_is_decoded_from_the_element_set(iss):
    assert iss.epoch.strftime("%Y-%m-%d %H:%M") == "2008-09-20 12:25"


def test_old_elements_are_flagged(iss):
    assert tle.age_warnings([iss], START) == []
    warnings = tle.age_warnings([iss], START + timedelta(days=10))
    assert len(warnings) == 1 and "refresh" in warnings[0]


def test_gmst_at_j2000_matches_the_published_value():
    assert math.degrees(gmst_rad(2451545.0)) == pytest.approx(280.46061837, abs=1e-6)


def test_geodetic_conversion_on_the_axes():
    assert geodetic_to_ecef(0, 0, 0) == pytest.approx((6378.137, 0, 0))
    x, y, z = geodetic_to_ecef(90, 0, 0)
    assert z == pytest.approx(6356.752, abs=1e-3)


def test_a_point_straight_above_the_station_is_at_90_degrees():
    above = geodetic_to_ecef(HELSINKI.lat_deg, HELSINKI.lon_deg, 500)
    _, el, rng = look_angles(above, HELSINKI)
    assert el == pytest.approx(90, abs=1e-6)
    assert rng == pytest.approx(500 - HELSINKI.alt_km, abs=1e-6)


@pytest.fixture(scope="module")
def iss_passes(iss):
    return find_passes(iss, HELSINKI, START, START + timedelta(hours=24), min_elevation=10)


def test_passes_are_found_and_ordered(iss_passes):
    assert len(iss_passes) >= 1
    for a, b in zip(iss_passes, iss_passes[1:]):
        assert a.los < b.aos


def test_aos_and_los_sit_on_the_mask(iss, iss_passes):
    for p in iss_passes:
        assert elevation(iss, HELSINKI, p.aos) == pytest.approx(10, abs=0.05)
        assert elevation(iss, HELSINKI, p.los) == pytest.approx(10, abs=0.05)


def test_culmination_is_the_highest_point_of_the_pass(iss, iss_passes):
    for p in iss_passes:
        assert p.aos < p.tca < p.los
        samples = [elevation(iss, HELSINKI, p.aos + timedelta(seconds=s))
                   for s in range(0, int(p.duration_s), 5)]
        assert p.max_elevation >= max(samples) - 0.01


def test_pass_geometry_is_plausible_for_this_orbit(iss_passes):
    # 51.6 degree inclination seen from 60 N: low passes, a few minutes long
    for p in iss_passes:
        assert 10 < p.max_elevation < 25
        assert 60 < p.duration_s < 12 * 60


def test_a_pass_in_progress_at_the_window_start_is_marked(iss, iss_passes):
    p = iss_passes[0]
    mid = p.aos + (p.los - p.aos) / 2
    cut = find_passes(iss, HELSINKI, mid, mid + timedelta(hours=1))
    assert cut[0].starts_before_window and cut[0].aos == mid
    assert cut[0].los == pytest.approx(p.los, abs=timedelta(seconds=1))
