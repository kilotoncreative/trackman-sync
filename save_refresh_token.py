#!/usr/bin/env python3
"""Save a rotated Trackman refresh token back to the repo's Actions secret.

Needs GH_SECRETS_PAT: a fine-grained token limited to this repo with
"Secrets: Read and write" permission.
"""
import base64
import os
import sys
from pathlib import Path

import requests
from nacl import encoding, public

path = Path(os.environ.get("NEW_REFRESH_TOKEN_FILE", ".new_refresh_token"))
if not path.exists():
    print("Refresh token unchanged.")
    sys.exit(0)

repo = os.environ["GITHUB_REPOSITORY"]
headers = {
    "Authorization": f"Bearer {os.environ['GH_SECRETS_PAT']}",
    "Accept": "application/vnd.github+json",
}
api = f"https://api.github.com/repos/{repo}/actions/secrets"

key = requests.get(f"{api}/public-key", headers=headers, timeout=30)
key.raise_for_status()
k = key.json()
box = public.SealedBox(public.PublicKey(k["key"].encode(), encoding.Base64Encoder()))
encrypted = base64.b64encode(box.encrypt(path.read_text().strip().encode())).decode()

r = requests.put(f"{api}/TRACKMAN_REFRESH_TOKEN", headers=headers, timeout=30,
                 json={"encrypted_value": encrypted, "key_id": k["key_id"]})
r.raise_for_status()
path.unlink()
print("Saved rotated refresh token.")
