"""Robust page loading for the scout and the recorder.

Real apps are slow or messy: a web font or a CDN that never answers, analytics scripts,
Shiny apps that take their time to connect. Nothing here may hang the film:
  * third-party requests (other hosts than the app) get `THIRD_PARTY_TIMEOUT` seconds, then fail
  * known trackers / chat widgets are blocked outright (they never appear in a product film)
  * navigation waits for the DOM, not for every resource; 'load' is awaited softly
  * a failed navigation is retried once
  * for server-backed apps we wait until they are connected and idle (generously, with progress)
"""
import re, time, urllib.parse

THIRD_PARTY_TIMEOUT = 8.0
BLOCK = re.compile(r"google-analytics\.com|googletagmanager\.com|doubleclick\.net|facebook\.net|connect\.facebook|hotjar\.com|segment\.(io|com)|"
                   r"intercom(cdn)?\.(io|com)|crisp\.chat|drift\.com|hubspot\.com|hs-scripts|clarity\.ms|mixpanel\.com|amplitude\.com|sentry\.io|"
                   r"plausible\.io|matomo|cloudflareinsights|newrelic|nr-data|fullstory|tawk\.to|zendesk|livechatinc|optimizely", re.I)


def harden(ctx, start_url, log=print):
    """install request handling on a browser context"""
    host = (urllib.parse.urlparse(start_url).hostname or "").lower()
    local = {host, "127.0.0.1", "localhost", "[::1]"}

    def handler(route):
        req = route.request
        u = urllib.parse.urlparse(req.url)
        if u.scheme in ("data", "blob", "file") or (u.hostname or "").lower() in local:
            return route.continue_()
        if BLOCK.search(req.url):
            return route.abort()
        try:
            resp = route.fetch(timeout=THIRD_PARTY_TIMEOUT * 1000)
            return route.fulfill(response=resp)
        except Exception:  # noqa: BLE001  (slow or unreachable: the page carries on without it)
            try: route.abort()
            except Exception: pass  # noqa: BLE001
    try:
        ctx.route("**/*", handler)
    except Exception as e:  # noqa: BLE001
        log("  (request handling unavailable: %s)" % str(e)[:80])


SHINY_READY_JS = """() => {
  const d = document.documentElement;
  if (document.readyState === 'loading') return 'parsing';
  if (window.Shiny && window.Shiny.shinyapp) {
    if (!(window.Shiny.shinyapp.isConnected && window.Shiny.shinyapp.isConnected())) return 'connecting';
    if (d.classList.contains('shiny-busy') || document.querySelector('.recalculating, .shiny-output-busy')) return 'computing';
  }
  if (document.querySelector('[data-testid="stApp"]') && document.querySelector('[data-testid="stStatusWidget"] [data-testid="stStatusWidgetRunningIcon"], .stSpinner')) return 'computing';
  return '';
}"""


def open_page(page, url, log=print, timeout=90, settle=None):
    """navigate robustly; returns True when the page is usable (it may still be fetching extras)"""
    last = None
    for attempt in (1, 2):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            last = None; break
        except Exception as e:  # noqa: BLE001
            last = e
            if page.url and not page.url.startswith("about:"):
                log("  the page is slow to load (%s); carrying on" % str(e).splitlines()[0][:90]); last = None; break
            log("  navigation failed (%s); retrying" % str(e).splitlines()[0][:90]); time.sleep(2)
    if last is not None:
        raise last
    try: page.wait_for_load_state("load", timeout=10000)
    except Exception: log("  some page resources are still loading; carrying on")  # noqa: BLE001
    return True


def wait_ready(page, log=print, max_s=180, quiet_s=0.8, progress=None, clock=None):
    """wait until a server-backed app is connected and idle. `clock(ms)` advances a fake clock (recorder)."""
    t0 = time.time(); quiet = None; last_state = None; said = 0
    while time.time() - t0 < max_s:
        try: st = page.evaluate(SHINY_READY_JS)
        except Exception: st = 'loading'  # noqa: BLE001
        if st:
            quiet = None
            if st != last_state or time.time() - said > 10:
                msg = {"parsing": "page loading", "connecting": "waiting for the app to connect", "computing": "the app is computing",
                       "loading": "page loading"}.get(st, st)
                if progress: progress("%s (%.0fs)" % (msg, time.time() - t0))
                said = time.time(); last_state = st
        else:
            if quiet is None: quiet = time.time()
            if time.time() - quiet >= quiet_s: return True
        if clock: clock(100)
        time.sleep(0.1)
    log("  the app was still busy after %.0fs; carrying on" % max_s)
    return False
