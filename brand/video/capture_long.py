"""Full-length phone screenshots (1080 px wide) for AI video tools to scroll on a phone screen.
Same demo server as capture.py.  ~/quotebot/.venv/bin/python brand/video/capture_long.py"""
import base64
import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket

OUT = Path(__file__).parent / "long"
OUT.mkdir(exist_ok=True)
BASE = "http://127.0.0.1:8510"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CSS_W, PX_W = 390, 1080
SCALE = PX_W / CSS_W

prof = tempfile.mkdtemp()
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=9335", f"--user-data-dir={prof}",
                         "--hide-scrollbars", "--disable-gpu", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(60):
    try:
        page = next(t for t in json.load(urllib.request.urlopen("http://127.0.0.1:9335/json")) if t["type"] == "page")
        break
    except Exception:
        time.sleep(0.25)
ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=120, suppress_origin=True)
_id = 0


def cdp(method, **params):
    global _id
    _id += 1
    ws.send(json.dumps({"id": _id, "method": method, "params": params}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == _id:
            return msg.get("result", {})


def js(expr):
    return cdp("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True).get("result", {}).get("value")


def wait_for(expr, secs=120):
    for _ in range(int(secs * 4)):
        if js(expr):
            return
        time.sleep(0.25)
    raise RuntimeError("timed out: " + expr)


# Fixed and sticky parts would float in the middle of a scrolling image: put them in the flow.
FLAT = """(() => { const st = document.createElement('style'); st.id = 'flat';
  st.textContent = `nav.bottom, .fab, #toast { display: none !important; }
    header, .action-bar, .actionbar, [class*=action-bar] { position: static !important; }
    body { padding-bottom: 24px !important; } main { padding-bottom: 24px !important; }`;
  document.getElementById('flat') || document.head.appendChild(st); })()"""


def long_shot(name):
    js(FLAT)
    time.sleep(0.6)
    js("window.scrollTo(0,0)")
    h = js("Math.ceil(Math.max(document.documentElement.scrollHeight, document.body.scrollHeight))")
    cdp("Emulation.setDeviceMetricsOverride", width=CSS_W, height=h, deviceScaleFactor=SCALE, mobile=True)
    time.sleep(1.0)
    data = cdp("Page.captureScreenshot", format="png", captureBeyondViewport=True)["data"]
    (OUT / f"{name}.png").write_bytes(base64.b64decode(data))
    cdp("Emulation.setDeviceMetricsOverride", width=CSS_W, height=844, deviceScaleFactor=SCALE, mobile=True)
    print("long shot", name, f"{PX_W}x{round(h * SCALE)}")


def go(hash_, wait=1.5):
    js(f"location.hash = '{hash_}'")
    time.sleep(wait)


cdp("Emulation.setDeviceMetricsOverride", width=CSS_W, height=844, deviceScaleFactor=SCALE, mobile=True)
cdp("Emulation.setUserAgentOverride", userAgent="Mozilla/5.0 (iPhone; CPU iPhone OS 26_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.6 Mobile/15E148 Safari/604.1")
cdp("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "light"}])
cdp("Page.enable"); cdp("Runtime.enable")
cdp("Page.navigate", url=f"{BASE}/app.html"); time.sleep(2)
js("""(async () => {
  const t = (await (await fetch('/api/login', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({email:'demo@example.com', password:'demo-pass-1'})})).json()).token;
  localStorage.setItem('ss-token', t);
  const me = await (await fetch('/api/me', {headers:{'X-Token': t}})).json();
  localStorage.setItem('ss-site', me.sites[0].id); location.hash = '#file'; location.reload(); })()""")
time.sleep(3)
wait_for("!!document.querySelector('[data-act=offline-save]')")
js("document.querySelector('[data-act=offline-save]').click()")   # the device copy, so the board has no artefact
time.sleep(6)

# 1. the site board, top to bottom: every tile green, amber or red
go("#board", 2.5)
wait_for("!!document.querySelector('.tile')")
long_shot("1_site-board")

# 2. the task sheet the AI writes from one voice note
go("#task", 1.5)
js("""(() => { document.querySelector('#view details').open = true;
  document.getElementById('t-text').value = 'Sipho and Lwazi do brickwork on the east wall of the first floor from the scaffold. Johan digs the sewer trench on the north boundary with the TLB, about 1.4 metres deep, and Thabo helps him with the pipes.';
  document.querySelector('[data-act=task-text]').click(); })()""")
wait_for("document.querySelector('h1') && document.querySelector('h1').textContent.includes(\"Check today\")")
js("document.querySelectorAll('#view .note.warn').forEach((n) => n.style.display = 'none'); document.querySelectorAll('#view details').forEach((d) => d.open = true)")
long_shot("2_task-sheet")

# 3. the incident report the AI writes from one voice note
js("(async () => { await dropDraft('task'); })()")
go("#incident", 1.5)
js("""(() => { document.querySelector('#view details').open = true;
  document.getElementById('inc-text').value = 'This is Piet, site supervisor. Today at about 10:20 on the north boundary trench, a section of the trench wall gave way while Thabo was laying pipe. Soil came down to his knees. We dug him out by hand within two minutes. He has a bruised left leg, no other injury. The first aider checked him and we took him to the clinic for a check-up. We stopped all trench work, barricaded the trench and called the excavation supervisor to shore the walls.';
  document.querySelector('[data-act=inc-text]').click(); })()""")
wait_for("document.querySelector('h1') && document.querySelector('h1').textContent.includes('Incident report')")
js("document.querySelectorAll('#view .note.warn').forEach((n) => n.style.display = 'none'); document.querySelectorAll('#view details').forEach((d) => d.open = true)")
long_shot("3_incident-report")
js("(async () => { await dropDraft('incident'); })()")

# 4. the safety file
go("#file", 2.5)
long_shot("4_safety-file")

ws.close()
proc.terminate()
