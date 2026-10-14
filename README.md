# trackman-sync

Pulls your Trackman practice sessions, shot by shot, into this repo every night. Everything is set up and run from an iPhone.

## How it works

- `trackman_sync.py` signs in with a saved refresh token, asks Trackman's portal API (`api.trackmangolf.com/graphql`) for activities it hasn't seen, and saves each one.
- Output lands in `data/`:
  - `data/all_shots.csv`: every shot, one row each
  - `data/sessions/<date>_<type>_<id>.csv` and `.json`: one file per session
- Speeds are converted to mph and distances to yards (column names end in `_mph` / `_yd`). Angles and spin are as Trackman reports them.
- Trackman may issue a new refresh token on every sign-in. `save_refresh_token.py` writes it back to the repo secret, so you only grab a token once.
- Practice types covered: range sessions, Virtual Range, Shot Analysis, Combine, Find My Distance, Map My Bag, Virtual Golf. Course play rounds are skipped for now.

## One-time setup (about 10 minutes, all on iPhone)

### 1. Add the files to the repo
Commit these files to `kilotoncreative/trackman-sync` on `main`.

### 2. Get your Trackman token with a bookmarklet
1. In Safari, bookmark any page. Edit the bookmark: name it **Get Trackman token** and replace the address with the full contents of `bookmarklet.txt`.
2. Log in at **portal.trackmangolf.com** (enter the email code as usual).
3. Tap the address bar, type `Get Trackman`, and tap the bookmark.
4. Two boxes appear. Copy each value: first the client ID, then the refresh token.

If it says "No refresh token found," send Claude the list of storage keys it shows. The portal is storing the login differently and the script needs a small change.

### 3. Create a GitHub token for secret updates
github.com → Settings → Developer settings → Fine-grained tokens → Generate:
- Repository access: only `trackman-sync`
- Permissions: **Secrets: Read and write**, **Actions: Read and write**
- Expiration: up to 1 year

### 4. Add three repo secrets
Repo → Settings → Secrets and variables → Actions → New repository secret:

| Name | Value |
|---|---|
| `TRACKMAN_CLIENT_ID` | from the bookmarklet, box 1 |
| `TRACKMAN_REFRESH_TOKEN` | from the bookmarklet, box 2 |
| `GH_SECRETS_PAT` | the token from step 3 |

### 5. First run
Repo → Actions → **Trackman sync** → Run workflow, with **Re-download every activity** checked. This backfills your history.

## Daily use

- **Automatic:** runs nightly at about 10pm Eastern.
- **On demand:** the iOS Shortcut below.
- **Analysis:** ask Claude to read `data/all_shots.csv` or a specific session file.
- **Failures:** GitHub emails you when a run fails. "Token refresh failed" means the refresh token expired. Repeat step 2 and update `TRACKMAN_REFRESH_TOKEN`.

## iOS Shortcut: "Sync Trackman"

Shortcuts app → + → add these actions:

1. **Text**: `https://api.github.com/repos/kilotoncreative/trackman-sync/actions/workflows/sync.yml/dispatches`
2. **Get Contents of URL** (pass the Text as URL)
   - Method: **POST**
   - Headers:
     - `Authorization`: `Bearer <your token from step 3>`
     - `Accept`: `application/vnd.github+json`
   - Request Body: **JSON**, one field: `ref` = `main`
3. **Show Notification**: `Trackman sync started`

Optional: Shortcuts → Automation → **Leave** (your range's location) → run Sync Trackman. Data syncs on the drive home. Sessions can take a few minutes to upload to Trackman, and empty ones are retried automatically for 3 days.

## Notes

- Unofficial access to your own data. Personal use, low volume (one request per second, one run per night).
- GraphQL queries adapted from [TrackPull](https://github.com/criticalberne/TrackPull) (MIT).
