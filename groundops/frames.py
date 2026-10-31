"""Coordinate conversions from the SGP4 output frame to a ground station's view.

Simplifications, stated so nobody mistakes this for flight dynamics software: UT1 is
taken as UTC and polar motion is ignored. Both are well under the accuracy of a TLE.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

WGS84_A_KM = 6378.137
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)


def julian_date(t: datetime) -> float:
    return t.timestamp() / 86400.0 + 2440587.5


def gmst_rad(jd_ut1: float) -> float:
    """Greenwich mean sidereal time, IAU 1982 model."""
    c = (jd_ut1 - 2451545.0) / 36525.0
    seconds = (67310.54841 + (876600.0 * 3600 + 8640184.812866) * c
               + 0.093104 * c * c - 6.2e-6 * c ** 3)
    return math.radians((seconds % 86400.0) / 240.0)


def teme_to_ecef(r_teme: tuple[float, float, float], jd_ut1: float) -> tuple[float, float, float]:
    g = gmst_rad(jd_ut1)
    x, y, z = r_teme
    return (math.cos(g) * x + math.sin(g) * y,
            -math.sin(g) * x + math.cos(g) * y,
            z)


@dataclass(frozen=True)
class Station:
    name: str
    lat_deg: float
    lon_deg: float
    alt_km: float = 0.0

    def ecef(self) -> tuple[float, float, float]:
        return geodetic_to_ecef(self.lat_deg, self.lon_deg, self.alt_km)


def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_km: float) -> tuple[float, float, float]:
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    n = WGS84_A_KM / math.sqrt(1 - WGS84_E2 * math.sin(lat) ** 2)
    return ((n + alt_km) * math.cos(lat) * math.cos(lon),
            (n + alt_km) * math.cos(lat) * math.sin(lon),
            (n * (1 - WGS84_E2) + alt_km) * math.sin(lat))


def look_angles(sat_ecef: tuple[float, float, float], station: Station) -> tuple[float, float, float]:
    """Azimuth and elevation in degrees and slant range in km, from the station to the satellite."""
    sx, sy, sz = station.ecef()
    dx, dy, dz = sat_ecef[0] - sx, sat_ecef[1] - sy, sat_ecef[2] - sz
    lat, lon = math.radians(station.lat_deg), math.radians(station.lon_deg)
    east = -math.sin(lon) * dx + math.cos(lon) * dy
    north = (-math.sin(lat) * math.cos(lon) * dx - math.sin(lat) * math.sin(lon) * dy
             + math.cos(lat) * dz)
    up = (math.cos(lat) * math.cos(lon) * dx + math.cos(lat) * math.sin(lon) * dy
          + math.sin(lat) * dz)
    az = math.degrees(math.atan2(east, north)) % 360.0
    el = math.degrees(math.atan2(up, math.hypot(east, north)))
    return az, el, math.sqrt(dx * dx + dy * dy + dz * dz)
