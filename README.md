# trackman-sync

Gets your Trackman practice sessions, shot by shot, into this repo from your iPhone. After a range session: open the portal in Safari, tap Share → **Sync Trackman**. About 10 seconds.

## How it works

1. The **Sync Trackman** shortcut runs `shortcut/sync_trackman.js` inside your logged-in portal.trackmangolf.com page. It uses the portal's own login (nothing stored, no password) to read your recent activities from Trackman's GraphQL API.
2. The shortcut uploads the result to `data/inbox/` in this repo.
3. A GitHub Action (`process_inbox.py`) turns each upload into:
   - `data/all_shots.csv`: every shot, one row each
   - `data/sessions/<date>_<type>_<id>.csv` and `.json`: one file per session

Speeds are in mph and distances in yards (columns end in `_mph` / `_yd`). Angles and spin are as Trackman reports them. Covered: range sessions, Virtual Range, Shot Analysis, Combine, Find My Distance, Map My Bag, Virtual Golf. Course rounds are skipped. Re-syncing the same days is harmless.

Why not fully automatic: Trackman's password login is behind a CAPTCHA, and its PIN login is for pairing with bays. Running inside your own logged-in Safari tab avoids both.

## One-time setup (iPhone)

### 1. GitHub token
github.com → Settings → Developer settings → **Fine-grained tokens** → Generate new token:
- Repository access: only `trackman-sync`
- Permissions: **Contents: Read and write**
- Copy the token.

### 2. Turn on "Run JavaScript on Webpage"
Settings app → Apps → Shortcuts → Advanced → turn on **Allow Running Scripts**.

### 3. Build the shortcut
Shortcuts app → **+** → name it **Sync Trackman**. Tap the (i) info button → turn on **Show in Share Sheet** → set it to receive **Safari web pages** only.

Add these actions in order:

1. **Run JavaScript on Webpage**: input is *Shortcut Input*. Delete the sample code and paste the full contents of `shortcut/sync_trackman.js`. (Open the file on github.com, tap **Raw**, select all, copy.)
2. **Get Dictionary from Input** (input: *JavaScript Result*).
3. **Get Dictionary Value** → key `error` from *Dictionary*.
4. **If** *Dictionary Value* **has any value**:
   - **Show Alert**: `Trackman sync failed: ` + *Dictionary Value*
   - **Stop This Shortcut**
   - **End If**
5. **Base64 Encode** *JavaScript Result* (tap the action to set **Line Breaks: None**).
6. **Format Date**: *Current Date*, custom format `yyyyMMdd-HHmmss`.
7. **Get Contents of URL**:
   - URL: `https://api.github.com/repos/kilotoncreative/trackman-sync/contents/data/inbox/` + *Formatted Date* + `.json`
   - Method: **PUT**
   - Headers: `Authorization` = `Bearer <your token>`, `Accept` = `application/vnd.github+json`
   - Request Body: **JSON** with two text fields: `message` = `Trackman upload`, `content` = *Base64 Encoded*
8. **Get Dictionary Value** → key `count` from the *Dictionary* in step 2.
9. **Show Notification**: `Uploaded ` + *Dictionary Value* + ` Trackman sessions`.

## Using it

- Log in at **portal.trackmangolf.com** in Safari (once; Safari remembers you).
- After practice: open the portal → Share → **Sync Trackman**. It pulls the last 30 days.
- First time only: edit `var DAYS = 30;` at the top of the script to `3650`, run it once for a full backfill, then set it back.
- Ask Claude to read `data/all_shots.csv` or a session file.

If the alert says sync failed, send Claude the message. It includes what the script saw.

## Notes

- Unofficial access to your own data, using your own logged-in browser session. Personal use.
- GraphQL queries adapted from [TrackPull](https://github.com/criticalberne/TrackPull) (MIT).
