#!/usr/bin/env python3
"""Pull new Trackman activities (shot-level data) into CSV and JSON.

Auth: exchanges a stored refresh token for an access token at Trackman's
login server, then queries the same GraphQL API the web portal uses.
Trackman may rotate the refresh token on every use; the new one is written
to NEW_REFRESH_TOKEN_FILE so the workflow can save it back as a secret.

GraphQL queries adapted from TrackPull (MIT, (c) 2026 criticalberne).
Personal use only. This is unofficial access to your own data.
"""
import csv
import json
import os
import sys
import time
from pathlib import Path

import requests

TOKEN_URL = "https://login.trackmangolf.com/connect/token"
GRAPHQL_URL = "https://api.trackmangolf.com/graphql"
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
STATE_FILE = DATA_DIR / "state.json"
ALL_SHOTS = DATA_DIR / "all_shots.csv"
NEW_REFRESH_TOKEN_FILE = Path(os.environ.get("NEW_REFRESH_TOKEN_FILE", ".new_refresh_token"))
PAGE_SIZE = 100

# Activity types that carry shot data.
SHOT_TYPES = {
    "SessionActivity", "VirtualRangeSessionActivity", "ShotAnalysisSessionActivity",
    "CombineTestActivity", "RangeFindMyDistanceActivity", "MapMyBagActivity",
    "MapMyBagSessionActivity", "BagMappingActivity", "VirtualGolfActivity",
    "VirtualGolfSessionActivity", "CoursePlayActivity", "CourseSessionActivity",
}

LIST_QUERY = """
query GetPlayerActivities($skip: Int!, $take: Int!) {
  me {
    activities(skip: $skip, take: $take) {
      totalCount
      pageInfo { hasNextPage }
      items { id time kind __typename }
    }
  }
}"""

MEASURE = """clubSpeed ballSpeed smashFactor attackAngle clubPath faceAngle
  faceToPath swingDirection swingPlane dynamicLoft spinRate spinAxis spinLoft
  launchAngle launchDirection carry total carrySide totalSide
  maxHeight landingAngle hangTime"""
STROKE = f"club time targetDistance measurement {{ {MEASURE} }}"
PRO_BALL = """club time targetDistance
  measurement(measurementType: PRO_BALL_MEASUREMENT) {
    ballSpeed ballSpin spinAxis carry carrySide total totalSide
    landingAngle launchAngle launchDirection maxHeight }"""


def flat_query(t, strokes=STROKE):
    return f"""query FetchActivityById($id: ID!) {{ node(id: $id) {{ __typename
      ... on {t} {{ id time strokes {{ {strokes} }} }} }} }}"""


def grouped_query(t, strokes=STROKE):
    return f"""query FetchActivityById($id: ID!) {{ node(id: $id) {{ __typename
      ... on {t} {{ id time strokeGroups {{ club name strokes {{ {strokes} }} }} }} }} }}"""


def detail_queries(t):
    """Candidate queries for one activity type, tried in order until one returns shots."""
    qs = [flat_query(t), grouped_query(t)]
    if t in ("RangeFindMyDistanceActivity", "MapMyBagActivity", "MapMyBagSessionActivity"):
        qs += [flat_query(t, PRO_BALL), grouped_query(t, PRO_BALL)]
    return qs


# Unit conversion. The API returns speeds in m/s and distances in meters.
MS_TO_MPH = 2.2369363
M_TO_YD = 1.0936133
SPEED_FIELDS = {"clubSpeed", "ballSpeed"}
DISTANCE_FIELDS = {"carry", "total", "carrySide", "totalSide", "maxHeight"}


def get_access_token(client_id, refresh_token):
    r = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }, timeout=30)
    if r.status_code != 200:
        sys.exit(f"Token refresh failed (HTTP {r.status_code}): {r.text[:300]}\n"
                 "Re-run the token bookmarklet and update TRACKMAN_REFRESH_TOKEN.")
    tok = r.json()
    new_rt = tok.get("refresh_token")
    if new_rt and new_rt != refresh_token:
        NEW_REFRESH_TOKEN_FILE.write_text(new_rt)
    return tok["access_token"]


def gql(session, query, variables):
    for attempt in range(3):
        r = session.post(GRAPHQL_URL, json={"query": query, "variables": variables}, timeout=60)
        if r.status_code in (429, 502, 503, 504):
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        body = r.json()
        return body.get("data"), body.get("errors")
    r.raise_for_status()


def list_activities(session):
    out, skip = [], 0
    while True:
        data, errors = gql(session, LIST_QUERY, {"skip": skip, "take": PAGE_SIZE})
        if errors and not data:
            sys.exit(f"Activity list failed: {json.dumps(errors)[:500]}")
        page = data["me"]["activities"]
        items = page.get("items") or []
        out += items
        skip += PAGE_SIZE
        if not page.get("pageInfo", {}).get("hasNextPage") or not items:
            return out


def extract_shots(node):
    strokes = []
    for s in node.get("strokes") or []:
        strokes.append((s.get("club"), s))
    for g in node.get("strokeGroups") or []:
        for s in g.get("strokes") or []:
            strokes.append((s.get("club") or g.get("club") or g.get("name"), s))
    return [(club, s) for club, s in strokes if s.get("measurement")]


def fetch_activity(session, act):
    for q in detail_queries(act["__typename"]):
        data, _ = gql(session, q, {"id": act["id"]})
        node = (data or {}).get("node") or {}
        shots = extract_shots(node)
        if shots:
            return node, shots
    return None, []


def to_rows(act, shots):
    rows = []
    for n, (club, s) in enumerate(shots, 1):
        m = s["measurement"]
        row = {
            "activity_id": act["id"], "activity_time": act.get("time"),
            "activity_type": act["__typename"], "shot": n, "club": club or "Unknown",
            "shot_time": s.get("time"), "target_distance_yd": _conv(s.get("targetDistance"), M_TO_YD),
        }
        for k, v in m.items():
            if k in SPEED_FIELDS:
                row[f"{k}_mph"] = _conv(v, MS_TO_MPH)
            elif k in DISTANCE_FIELDS:
                row[f"{k}_yd"] = _conv(v, M_TO_YD)
            else:
                row[k] = v
        rows.append(row)
    return rows


def _age_days(ts):
    from datetime import datetime, timezone
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 86400
    except ValueError:
        return 999


def _conv(v, factor):
    return round(v * factor, 2) if isinstance(v, (int, float)) else v


def write_csv(path, rows, append=False):
    if not rows:
        return
    existing_header = []
    if append and path.exists():
        with path.open(newline="") as f:
            existing_header = next(csv.reader(f), [])
    fields = list(existing_header)
    for r in rows:
        fields += [k for k in r if k not in fields]
    if append and path.exists() and fields != existing_header:
        # New columns appeared: rewrite the file with the wider header.
        with path.open(newline="") as f:
            old = list(csv.DictReader(f))
        rows, append = old + rows, False
    mode = "a" if append and path.exists() else "w"
    with path.open(mode, newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if mode == "w":
            w.writeheader()
        w.writerows(rows)


def main():
    client_id = os.environ["TRACKMAN_CLIENT_ID"]
    refresh_token = os.environ["TRACKMAN_REFRESH_TOKEN"]
    lookback = os.environ.get("RESYNC_ALL") == "true"

    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "sessions").mkdir(exist_ok=True)
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"synced": {}}

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {get_access_token(client_id, refresh_token)}",
        "Content-Type": "application/json", "Accept": "application/json",
        "Origin": "https://portal.trackmangolf.com",
    })

    activities = [a for a in list_activities(session) if a.get("__typename") in SHOT_TYPES]
    todo = [a for a in activities if lookback or a["id"] not in state["synced"]]
    print(f"{len(activities)} shot activities found, {len(todo)} new.")

    new_rows = []
    for act in sorted(todo, key=lambda a: a.get("time") or ""):
        node, shots = fetch_activity(session, act)
        if not shots:
            # Retry empty activities for 3 days (a session may still be uploading),
            # then stop asking.
            if _age_days(act.get("time")) > 3:
                state["synced"][act["id"]] = {"time": act.get("time"), "shots": 0}
            print(f"  {act.get('time')} {act['__typename']}: no shot data")
            continue
        state["synced"][act["id"]] = {"time": act.get("time"), "shots": len(shots)}
        stem = f"{(act.get('time') or 'unknown')[:10]}_{act['__typename']}_{act['id'][-8:]}"
        stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)
        rows = to_rows(act, shots)
        (DATA_DIR / "sessions" / f"{stem}.json").write_text(json.dumps(node, indent=1))
        write_csv(DATA_DIR / "sessions" / f"{stem}.csv", rows)
        new_rows += rows
        print(f"  {act.get('time')} {act['__typename']}: {len(shots)} shots")
        time.sleep(1)  # be polite

    if not lookback:
        write_csv(ALL_SHOTS, new_rows, append=True)
    else:
        write_csv(ALL_SHOTS, new_rows)
    STATE_FILE.write_text(json.dumps(state, indent=1, sort_keys=True))

    summary = f"{len(new_rows)} new shots from {len(todo)} activities."
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text(f"### Trackman sync\n{summary}\n")


if __name__ == "__main__":
    main()
