"""Reading two-line element sets and checking them before use."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sgp4.api import Satrec


class TLEError(ValueError):
    pass


def checksum(line: str) -> int:
    """Modulo-10 checksum over the first 68 columns: digits count as themselves, '-' as 1."""
    total = 0
    for ch in line[:68]:
        if ch.isdigit():
            total += int(ch)
        elif ch == "-":
            total += 1
    return total % 10


def with_checksum(line: str) -> str:
    """Return the first 68 columns of `line` with a correct checksum digit appended."""
    body = line[:68].ljust(68)
    return body + str(checksum(body))


def validate_line(line: str, number: int) -> None:
    if len(line) != 69:
        raise TLEError(f"line {number} has {len(line)} characters, expected 69")
    if line[0] != str(number):
        raise TLEError(f"line {number} starts with {line[0]!r}")
    if not line[68].isdigit() or checksum(line) != int(line[68]):
        raise TLEError(f"line {number} checksum mismatch")


@dataclass
class Satellite:
    name: str
    line1: str
    line2: str
    satrec: Satrec

    @property
    def catalog_number(self) -> str:
        return self.line1[2:7].strip()

    @property
    def epoch(self) -> datetime:
        jd = self.satrec.jdsatepoch + self.satrec.jdsatepochF
        return datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=jd - 2451545.0)

    def age_days(self, at: datetime) -> float:
        return (at - self.epoch).total_seconds() / 86400.0


def parse(name: str, line1: str, line2: str) -> Satellite:
    line1, line2 = line1.rstrip(), line2.rstrip()
    validate_line(line1, 1)
    validate_line(line2, 2)
    if line1[2:7] != line2[2:7]:
        raise TLEError(f"{name}: catalog numbers differ between lines")
    return Satellite(name.strip(), line1, line2, Satrec.twoline2rv(line1, line2))


def load(path: str | Path) -> list[Satellite]:
    """Load a three-line TLE file (name line, then line 1 and line 2)."""
    lines = [ln.rstrip("\n") for ln in Path(path).read_text().splitlines() if ln.strip()]
    if len(lines) % 3:
        raise TLEError(f"{path}: expected groups of three lines, got {len(lines)} lines")
    return [parse(lines[i], lines[i + 1], lines[i + 2]) for i in range(0, len(lines), 3)]


def age_warnings(sats: list[Satellite], at: datetime, max_age_days: float = 3.0) -> list[str]:
    """Element sets lose accuracy quickly; flag any that are too far from the planning time."""
    out = []
    for sat in sats:
        age = sat.age_days(at)
        if abs(age) > max_age_days:
            out.append(f"{sat.name}: elements are {age:+.1f} days from the planning time "
                       f"(epoch {sat.epoch:%Y-%m-%d %H:%M}Z), refresh before relying on pass times")
    return out
