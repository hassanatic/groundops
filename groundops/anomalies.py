"""An append-only anomaly log.

Every change is a JSON line, so the history of an anomaly (who escalated it, when, and what
the root cause turned out to be) is never overwritten. The current state is rebuilt by
replaying the events.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

OPEN, INVESTIGATING, ESCALATED, CLOSED = "OPEN", "INVESTIGATING", "ESCALATED", "CLOSED"
SEVERITIES = ("minor", "major", "critical")

ALLOWED = {
    OPEN: {INVESTIGATING, ESCALATED, CLOSED},
    INVESTIGATING: {ESCALATED, CLOSED},
    ESCALATED: {INVESTIGATING, CLOSED},
    CLOSED: {INVESTIGATING},  # reopened when the fix did not hold
}


class AnomalyError(ValueError):
    pass


@dataclass
class Anomaly:
    id: str
    title: str
    severity: str
    detected_at: datetime
    source: str
    state: str = OPEN
    escalated_to: str | None = None
    root_cause: str | None = None
    corrective_action: str | None = None
    history: list[dict] = field(default_factory=list)


def _ts(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


class AnomalyLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.items: dict[str, Anomaly] = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    self._apply(json.loads(line))

    def _apply(self, ev: dict) -> None:
        if ev["type"] == "opened":
            a = Anomaly(ev["id"], ev["title"], ev["severity"],
                        datetime.fromisoformat(ev["detected_at"].replace("Z", "+00:00")),
                        ev["source"])
            self.items[a.id] = a
        else:
            a = self.items[ev["id"]]
            a.state = ev["to"]
            for key in ("escalated_to", "root_cause", "corrective_action"):
                if ev.get(key):
                    setattr(a, key, ev[key])
        self.items[ev["id"]].history.append(ev)

    def _write(self, ev: dict) -> None:
        self._apply(ev)
        with self.path.open("a") as fh:
            fh.write(json.dumps(ev) + "\n")

    def open(self, title: str, severity: str, detected_at: datetime, source: str,
             by: str, at: datetime) -> Anomaly:
        if severity not in SEVERITIES:
            raise AnomalyError(f"severity must be one of {SEVERITIES}")
        new_id = f"ANOM-{len(self.items) + 1:04d}"
        self._write({"type": "opened", "id": new_id, "title": title, "severity": severity,
                     "detected_at": _ts(detected_at), "source": source, "by": by, "at": _ts(at)})
        return self.items[new_id]

    def move(self, anomaly_id: str, to: str, by: str, at: datetime, note: str = "",
             escalated_to: str | None = None, root_cause: str | None = None,
             corrective_action: str | None = None) -> Anomaly:
        a = self.items.get(anomaly_id)
        if a is None:
            raise AnomalyError(f"unknown anomaly {anomaly_id}")
        if to not in ALLOWED[a.state]:
            raise AnomalyError(f"{anomaly_id}: cannot go from {a.state} to {to}")
        if to == ESCALATED and not escalated_to:
            raise AnomalyError(f"{anomaly_id}: say who it is escalated to")
        if to == CLOSED:
            if not (root_cause and corrective_action):
                raise AnomalyError(f"{anomaly_id}: closing needs a root cause and a corrective action")
            if a.severity == "critical" and a.escalated_to is None and escalated_to is None:
                raise AnomalyError(f"{anomaly_id}: a critical anomaly must be escalated before closing")
        if to == INVESTIGATING and a.state == CLOSED and not note:
            raise AnomalyError(f"{anomaly_id}: reopening needs a note saying why")
        self._write({"type": "moved", "id": anomaly_id, "from": a.state, "to": to, "by": by,
                     "at": _ts(at), "note": note, "escalated_to": escalated_to,
                     "root_cause": root_cause, "corrective_action": corrective_action})
        return a

    def open_items(self) -> list[Anomaly]:
        return sorted((a for a in self.items.values() if a.state != CLOSED),
                      key=lambda a: (SEVERITIES.index(a.severity) * -1, a.detected_at))
