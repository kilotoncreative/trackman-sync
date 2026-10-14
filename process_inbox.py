#!/usr/bin/env python3
"""Turn uploads from the "Sync Trackman" iOS Shortcut into CSV files.

Each upload is a JSON file in data/inbox/ written by shortcut/sync_trackman.js:
  {"ok": true, "activities": [{"id", "time", "type", "node": {...}}, ...]}

For each activity this writes data/sessions/<date>_<type>_<id>.csv and .json,
then rebuilds data/all_shots.csv from every session file. Uploads that
overlap earlier ones are fine: sessions are keyed by activity id.
"""
import csv
import json
import re
from pathlib import Path

DATA = Path("data")
INBOX, SESSIONS = DATA / "inbox", DATA / "sessions"
ALL_SHOTS = DATA / "all_shots.csv"

# The API returns speeds in m/s and distances in meters.
MS_TO_MPH, M_TO_YD = 2.2369363, 1.0936133
SPEED_FIELDS = {"clubSpeed", "ballSpeed"}
DISTANCE_FIELDS = {"carry", "total", "carrySide", "totalSide", "maxHeight"}


def extract_shots(node):
    strokes = [(s.get("club"), s) for s in node.get("strokes") or []]
    for g in node.get("strokeGroups") or []:
        strokes += [(s.get("club") or g.get("club") or g.get("name"), s) for s in g.get("strokes") or []]
    return [(club, s) for club, s in strokes if s and s.get("measurement")]


def _conv(v, factor):
    return round(v * factor, 2) if isinstance(v, (int, float)) else v


def to_rows(act, shots):
    rows = []
    for n, (club, s) in enumerate(shots, 1):
        row = {
            "activity_id": act["id"], "activity_time": act.get("time"), "activity_type": act.get("type"),
            "shot": n, "club": club or "Unknown", "shot_time": s.get("time"),
            "target_distance_yd": _conv(s.get("targetDistance"), M_TO_YD),
        }
        for k, v in s["measurement"].items():
            if k in SPEED_FIELDS:
                row[f"{k}_mph"] = _conv(v, MS_TO_MPH)
            elif k in DISTANCE_FIELDS:
                row[f"{k}_yd"] = _conv(v, M_TO_YD)
            else:
                row[k] = v
        rows.append(row)
    return rows


def write_csv(path, rows):
    fields = []
    for r in rows:
        fields += [k for k in r if k not in fields]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def session_stem(act):
    stem = f"{(act.get('time') or 'unknown')[:10]}_{act.get('type')}_{act['id'][-8:]}"
    return re.sub(r"[^A-Za-z0-9_-]", "_", stem)


def main():
    SESSIONS.mkdir(parents=True, exist_ok=True)
    uploads = sorted(INBOX.glob("*.json")) if INBOX.exists() else []
    added = updated = 0
    for upload in uploads:
        payload = json.loads(upload.read_text())
        if not payload.get("ok"):
            print(f"{upload.name}: upload reported an error: {payload.get('error')}")
            upload.unlink()
            continue
        for act in payload.get("activities", []):
            shots = extract_shots(act.get("node") or {})
            if not shots:
                continue
            stem = session_stem(act)
            csv_path = SESSIONS / f"{stem}.csv"
            if csv_path.exists():
                with csv_path.open(newline="") as f:
                    if sum(1 for _ in csv.reader(f)) - 1 >= len(shots):
                        continue  # already have this session in full
                updated += 1
            else:
                added += 1
            (SESSIONS / f"{stem}.json").write_text(json.dumps(act["node"], indent=1))
            write_csv(csv_path, to_rows(act, shots))
        upload.unlink()

    # Rebuild the combined file from every session, oldest first.
    rows = []
    for path in sorted(SESSIONS.glob("*.csv")):
        with path.open(newline="") as f:
            rows += list(csv.DictReader(f))
    if rows:
        write_csv(ALL_SHOTS, rows)
    print(f"{len(uploads)} uploads: {added} new sessions, {updated} updated, {len(rows)} shots total.")


if __name__ == "__main__":
    main()
