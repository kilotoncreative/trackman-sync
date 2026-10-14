"""Log in to the Trackman portal in a headless browser and capture the
headers the portal itself sends to api.trackmangolf.com/graphql.

The portal keeps its token in memory, so we let it log in normally and
read the Authorization header off its own GraphQL traffic (the same trick
TrackPull uses). The browser session (cookies) is saved to AUTH_STATE so
later runs usually skip the password and email code entirely.

Login steps are matched loosely because Trackman's form markup can change.
On any failure a screenshot and page HTML are written to debug/.
"""
import email
import imaplib
import os
import re
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

PORTAL_URL = "https://portal.trackmangolf.com/player/activities"
AUTH_STATE = Path(os.environ.get("AUTH_STATE", ".auth/state.json"))
DEBUG_DIR = Path("debug")

EMAIL_SEL = ("input[type=email], input[name='Username' i], input[name*='email' i], "
             "input[id*='email' i], input[autocomplete=username]")
PASSWORD_SEL = "input[type=password]"
CODE_SEL = ("input[autocomplete=one-time-code], input[name*='code' i], input[id*='code' i], "
            "input[name*='otp' i], input[inputmode=numeric]")
SUBMIT_SEL = ("button[type=submit], input[type=submit], button:has-text('Continue'), "
              "button:has-text('Next'), button:has-text('Log in'), button:has-text('Sign in'), "
              "button:has-text('Verify')")
FORWARD_HEADERS = ("authorization", "accept", "content-type")


class LoginError(Exception):
    pass


def _host(url):
    return urlparse(url).hostname or ""


def _on_portal(page):
    return _host(page.url) == "portal.trackmangolf.com"


def _on_login(page):
    return _host(page.url) == "login.trackmangolf.com"


def _forwardable(name):
    n = name.lower()
    return n in FORWARD_HEADERS or n.startswith(("x-", "tm-", "apollographql-")) or "trackman" in n


def annotate(title, text):
    """Emit a GitHub Actions error annotation (readable via the API, unlike logs)."""
    text = str(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::error title={title}::{text[:3500]}", flush=True)


def _describe(page):
    """Short text description of the current page, without any typed values."""
    fields = page.evaluate("""() => [...document.querySelectorAll('input,button,select,a[role=button]')]
      .filter(e => e.offsetParent !== null)
      .map(e => [e.tagName.toLowerCase(), e.type||'', e.name||'', e.id||'',
                 e.getAttribute('autocomplete')||'', e.getAttribute('inputmode')||'',
                 (e.innerText||e.value&&e.type==='submit'&&e.value||'').trim().slice(0,40)].join('|'))
      .slice(0, 40)""")
    body = page.inner_text("body")[:1200]
    return f"URL: {page.url}\nTitle: {page.title()}\nVisible controls:\n" + "\n".join(fields) + f"\n\nPage text:\n{body}"


def _dump(page, tag):
    DEBUG_DIR.mkdir(exist_ok=True)
    try:
        page.screenshot(path=str(DEBUG_DIR / f"{tag}.png"), full_page=True)
        (DEBUG_DIR / f"{tag}.html").write_text(page.content())
        (DEBUG_DIR / f"{tag}.url.txt").write_text(page.url)
        annotate("Login page state", _describe(page))
    except Exception as e:  # noqa: BLE001
        print(f"debug dump failed: {e}")


def _visible(page, selector, timeout=4000):
    try:
        loc = page.locator(selector).first
        loc.wait_for(state="visible", timeout=timeout)
        return loc
    except PWTimeout:
        return None


def _submit(page, field):
    btn = page.locator(SUBMIT_SEL).first
    if btn.count() and btn.is_visible():
        btn.click()
    else:
        field.press("Enter")


def fetch_email_code(since_epoch, timeout=180):
    """Poll the mailbox for the newest Trackman login code sent after since_epoch."""
    user = os.environ.get("IMAP_USER") or os.environ["TRACKMAN_EMAIL"]
    password = os.environ["IMAP_PASSWORD"]
    host = os.environ.get("IMAP_HOST", "imap.gmail.com")
    sender = os.environ.get("CODE_SENDER", "trackman")
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(10)
        with imaplib.IMAP4_SSL(host) as m:
            m.login(user, password)
            m.select("INBOX", readonly=True)
            _, ids = m.search(None, f'(FROM "{sender}" SINCE {time.strftime("%d-%b-%Y", time.gmtime(since_epoch - 86400))})')
            for num in reversed(ids[0].split()[-10:]):
                _, msg_data = m.fetch(num, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                try:
                    sent = parsedate_to_datetime(msg["Date"]).timestamp()
                except (TypeError, ValueError):
                    continue
                if sent < since_epoch - 60:
                    continue
                code = _find_code(msg)
                if code:
                    return code
    raise LoginError("No Trackman login code arrived by email within 3 minutes.")


def _find_code(msg):
    texts = []
    for part in msg.walk():
        if part.get_content_maintype() == "text":
            payload = part.get_payload(decode=True) or b""
            texts.append(payload.decode(part.get_content_charset() or "utf-8", "ignore"))
    text = re.sub(r"<[^>]+>", " ", " ".join(texts))
    text = re.sub(r"&[a-z]+;|#[0-9a-fA-F]{3,6}\b", " ", text)
    for pattern in (r"\b(\d{6})\b", r"\b(\d{4,8})\b"):
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return None


def _do_login(page):
    print("Logging in to Trackman...")
    email_field = _visible(page, EMAIL_SEL, 15000)
    if not email_field:
        raise LoginError("Could not find the email field on the login page.")
    email_field.fill(os.environ["TRACKMAN_EMAIL"])

    pw = _visible(page, PASSWORD_SEL, 1500)
    if not pw:  # email and password on separate steps
        _submit(page, email_field)
        pw = _visible(page, PASSWORD_SEL, 10000)
    if pw:
        pw.fill(os.environ["TRACKMAN_PASSWORD"])
        code_requested_at = time.time()
        _submit(page, pw)
    else:
        code_requested_at = time.time()  # passwordless: email step sends the code

    # Either we land back on the portal, or a code prompt appears.
    error_sel = ".validation-summary-errors, .field-validation-error, .alert-danger, [role=alert]"
    for _ in range(30):
        page.wait_for_timeout(1000)
        if _on_portal(page):
            return
        code_field = _visible(page, CODE_SEL, 1000)
        if code_field:
            print("Waiting for the emailed login code...")
            code = fetch_email_code(code_requested_at)
            boxes = page.locator(CODE_SEL)
            if boxes.count() >= len(code):  # one box per digit
                boxes.first.click()
                page.keyboard.type(code, delay=80)
            else:
                code_field.fill(code)
            remember = page.locator("input[type=checkbox]").first
            if remember.count() and remember.is_visible() and not remember.is_checked():
                remember.check()
            _submit(page, code_field)
            page.wait_for_url(lambda u: _host(u) == "portal.trackmangolf.com", timeout=30000)
            return
        err = page.locator(error_sel).first
        if err.count() and err.is_visible() and err.inner_text().strip():
            raise LoginError(f"Trackman login error: {err.inner_text().strip()[:200]}")
    raise LoginError("Login did not complete (no code prompt and no redirect).")


def get_graphql_headers():
    """Return the headers the logged-in portal uses for its GraphQL calls."""
    captured = {}

    def on_request(req):
        if req.url.startswith("https://api.trackmangolf.com/graphql"):
            hdrs = {k: v for k, v in req.headers.items() if _forwardable(k)}
            if any(k.lower() == "authorization" for k in hdrs):
                captured.update(hdrs)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            storage_state=str(AUTH_STATE) if AUTH_STATE.exists() else None,
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"),
        )
        page = ctx.new_page()
        page.on("request", on_request)
        try:
            page.goto(PORTAL_URL, wait_until="domcontentloaded")
            for i in range(20):  # up to ~20s for either a token or a login page
                if captured:
                    break
                if i == 8 and not _on_login(page):
                    # Portal may show a landing page with a login button instead of redirecting.
                    link = page.locator("a:has-text('Log in'), button:has-text('Log in'), "
                                        "a:has-text('Sign in'), button:has-text('Sign in')").first
                    if link.count() and link.is_visible():
                        link.click()
                        page.wait_for_timeout(2000)
                if _on_login(page):
                    _do_login(page)
                    if urlparse(page.url).path != "/player/activities":
                        page.goto(PORTAL_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(1000)
            if not captured:
                page.reload(wait_until="networkidle")
            if not captured:
                raise LoginError("Logged in but never saw the portal's GraphQL token.")
            AUTH_STATE.parent.mkdir(parents=True, exist_ok=True)
            ctx.storage_state(path=str(AUTH_STATE))
        except Exception:
            _dump(page, "login_failure")
            raise
        finally:
            browser.close()
    print("Got portal session.")
    return captured
