# trackman-sync

Pulls your Trackman practice sessions, shot by shot, into this repo every night. Set up and run entirely from an iPhone.

## How it works

- A headless browser on GitHub Actions logs into portal.trackmangolf.com like you do. When Trackman emails a login code, it reads the code from your inbox.
- It captures the token the portal uses, then asks Trackman's GraphQL API for activities it hasn't seen yet.
- The browser session is saved between runs, so most nights skip the password and code entirely.
- Output lands in `data/`:
  - `data/all_shots.csv`: every shot, one row each
  - `data/sessions/<date>_<type>_<id>.csv` and `.json`: one file per session
- Speeds are in mph and distances in yards (columns end in `_mph` / `_yd`). Angles and spin are as Trackman reports them.
- Covered: range sessions, Virtual Range, Shot Analysis, Combine, Find My Distance, Map My Bag, Virtual Golf. Course rounds are skipped for now.

## One-time setup (iPhone)

### 1. Create a Gmail app password
This lets the sync read the login code Trackman emails you.
1. Google Account → Security → turn on 2-Step Verification if it isn't already.
2. Go to myaccount.google.com/apppasswords, create one named `trackman-sync`, and copy the 16-character password.

The app password can read your whole inbox. The script only reads messages from Trackman, and the password lives as an encrypted GitHub secret. For tighter isolation, forward Trackman emails to a separate Gmail account and use that one instead.

### 2. Add repo secrets
Repo → Settings → Secrets and variables → Actions → New repository secret:

| Name | Value |
|---|---|
| `TRACKMAN_EMAIL` | your Trackman login email |
| `TRACKMAN_PASSWORD` | your Trackman password |
| `IMAP_USER` | the Gmail address that receives Trackman codes |
| `IMAP_PASSWORD` | the app password from step 1 |

### 3. First run
Actions → **Trackman sync** → Run workflow, with **Re-download every activity** checked. This backfills your history.

## Daily use

- **Automatic:** runs nightly at about 10pm Eastern.
- **On demand:** the iOS Shortcut below.
- **Analysis:** ask Claude to read `data/all_shots.csv` or a session file.
- **Failures:** GitHub emails you. Login failures attach screenshots under the run's **Artifacts** (`login-debug`). Ask Claude to look at the failed run.

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
