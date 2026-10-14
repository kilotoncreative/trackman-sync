# trackman-sync

Pulls your Trackman practice sessions, shot by shot, into this repo every night. Set up and run entirely from an iPhone.

## How it works

- A headless browser on GitHub Actions opens the Trackman portal using a saved session, captures the token the portal uses, and asks Trackman's GraphQL API for activities it hasn't seen yet.
- When the saved session has expired, it uses Trackman's **Quick Login**: it emails you the PIN shown on the login page, and you enter it in the Trackman Golf app. The run waits up to 10 minutes. (Password login is blocked by a CAPTCHA, so this script doesn't use it.)
- Output lands in `data/`:
  - `data/all_shots.csv`: every shot, one row each
  - `data/sessions/<date>_<type>_<id>.csv` and `.json`: one file per session
- Speeds are in mph and distances in yards (columns end in `_mph` / `_yd`). Angles and spin are as Trackman reports them.
- Covered: range sessions, Virtual Range, Shot Analysis, Combine, Find My Distance, Map My Bag, Virtual Golf. Course rounds are skipped for now.

## One-time setup (iPhone)

### 1. Create a Gmail app password
Used to email you the PIN (and, if Trackman ever asks, to read an emailed login code).
1. Google Account → Security → turn on 2-Step Verification if needed.
2. myaccount.google.com/apppasswords → create one named `trackman-sync` → copy the 16-character password.

### 2. Add repo secrets
github.com/kilotoncreative/trackman-sync/settings/secrets/actions/new

| Name | Value |
|---|---|
| `IMAP_USER` | your Gmail address |
| `IMAP_PASSWORD` | the app password from step 1 |
| `NOTIFY_EMAIL` | optional: send PIN emails somewhere else |

`TRACKMAN_EMAIL` and `TRACKMAN_PASSWORD` are no longer used and can be deleted.

### 3. First run
Actions → Trackman sync → ⋯ → Run workflow, with **Re-download every activity** checked. Watch for the PIN email and approve it in the Trackman Golf app.

## Daily use

- **Automatic:** runs nightly at about 10pm Eastern.
- **On demand:** the iOS Shortcut below.
- **Analysis:** ask Claude to read `data/all_shots.csv` or a session file.
- **PIN emails:** only when the saved session expires. If you miss one, the run fails; approve the next one or run the shortcut.
- **Failures:** GitHub emails you. Ask Claude to look at the failed run.

## iOS Shortcut: "Sync Trackman"

First create a fine-grained GitHub token: github.com → Settings → Developer settings → Fine-grained tokens. Limit it to `trackman-sync` with **Actions: Read and write**.

Shortcuts app → + → add:

1. **Text**: `https://api.github.com/repos/kilotoncreative/trackman-sync/actions/workflows/sync.yml/dispatches`
2. **Get Contents of URL** (the Text as URL)
   - Method: **POST**
   - Headers: `Authorization` = `Bearer <your token>`, `Accept` = `application/vnd.github+json`
   - Request Body: **JSON**, one field: `ref` = `main`
3. **Show Notification**: `Trackman sync started`

Optional: Shortcuts → Automation → **Leave** (your range) → run Sync Trackman. Trackman can take a few minutes to upload a session; empty ones are retried for 3 days.

## Notes

- Unofficial access to your own data. Personal use, low volume.
- GraphQL queries adapted from [TrackPull](https://github.com/criticalberne/TrackPull) (MIT).
