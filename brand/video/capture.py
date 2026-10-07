"""Phone-size screenshots of the real app (headless Chrome, CDP), from the video demo server.
Run with a Python that has websocket-client:  ~/quotebot/.venv/bin/python brand/video/capture.py"""
import base64
import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket

OUT = Path(__file__).parent / "shots"
OUT.mkdir(exist_ok=True)
BASE = "http://127.0.0.1:8510"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

prof = tempfile.mkdtemp()
proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=9334", f"--user-data-dir={prof}",
                         "--hide-scrollbars", "--disable-gpu", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(60):
    try:
        page = next(t for t in json.load(urllib.request.urlopen("http://127.0.0.1:9334/json")) if t["type"] == "page")
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
    r = cdp("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
    return r.get("result", {}).get("value")


def wait_for(expr, secs=90):
    for _ in range(int(secs * 4)):
        if js(expr):
            return True
        time.sleep(0.25)
    raise RuntimeError("timed out: " + expr)


def shot(name, wait=0.8):
    time.sleep(wait)
    (OUT / f"{name}.png").write_bytes(base64.b64decode(cdp("Page.captureScreenshot", format="png")["data"]))
    print("shot", name)


def go(hash_, wait=1.2):
    js(f"location.hash = '{hash_}'")
    time.sleep(wait)
    js("window.scrollTo(0,0)")


cdp("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=3, mobile=True)
cdp("Emulation.setUserAgentOverride", userAgent="Mozilla/5.0 (iPhone; CPU iPhone OS 26_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.6 Mobile/15E148 Safari/604.1")
cdp("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "light"}])
cdp("Page.enable"); cdp("Runtime.enable")
cdp("Page.navigate", url=f"{BASE}/app.html"); time.sleep(2)
js("""(async () => {
  const t = (await (await fetch('/api/login', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({email:'demo@example.com', password:'demo-pass-1'})})).json()).token;
  localStorage.setItem('ss-token', t);
  const me = await (await fetch('/api/me', {headers:{'X-Token': t}})).json();
  localStorage.setItem('ss-site', me.sites[0].id); location.hash = '#board'; location.reload(); })()""")
time.sleep(3)
wait_for("!!document.querySelector('.tile')")

# keep a copy of the file on the device first, as a real phone does (else the board asks for it)
go("#file", 2.0)
js("document.querySelector('[data-act=offline-save]').click()")
time.sleep(6)

# 1. the site board
go("#board", 2.0)
shot("1_board")

# 2. say the day: recording
go("#task", 1.2)
js("""(() => { const m = document.querySelector('.mic'); m.classList.add('rec');
  document.getElementById('timer').textContent = 'Recording 0:18 · tap to finish';
  document.querySelector('#view p.center').innerHTML = '“Sipho and Lwazi do brickwork on the east wall from the scaffold. Johan digs the sewer trench with the TLB, about 1.4 metres deep, Thabo helps him…”'; })()""")
shot("2_record")

# 3. the task sheet the AI writes from the voice note (typed here, same AI)
js("""(() => { document.querySelector('#view details').open = true;
  document.getElementById('t-text').value = 'Sipho and Lwazi do brickwork on the east wall of the first floor from the scaffold. Johan digs the sewer trench on the north boundary with the TLB, about 1.4 metres deep, and Thabo helps him with the pipes.';
  document.querySelector('[data-act=task-text]').click(); })()""")
wait_for("document.querySelector('h1') && document.querySelector('h1').textContent.includes(\"Check today\")", 120)
js("document.querySelectorAll('#view .note.warn').forEach((n) => n.style.display = 'none'); window.scrollTo(0,0)")
shot("3_task", 1.5)

# 4. the workers sign on the phone
js("document.querySelector('[data-act=task-to-sign]').click()")
time.sleep(1.5)
js("""(async () => { const d = await IDB.get(draftKey('task'));
  const sig = {image: 'data:image/png;base64,', name: 'x', signed_at: new Date().toISOString()};
  S.data.workers.filter((w) => d.tasks.some((t) => t.worker_ids.includes(w.id))).slice(0, 2).forEach((w) => d.signatures[w.id] = sig);
  await saveDraft('task', d); route(); })()""")
time.sleep(1.5)
js("window.scrollTo(0,0); const b = document.querySelector('[data-act=task-sign]'); b && b.click();")
time.sleep(2.0)
js("""(() => { const c = document.querySelector('.modal canvas'); if (!c) return; const x = c.getContext('2d');
  x.setTransform(1, 0, 0, 1, 0, 0); const w = c.width, h = c.height;
  x.lineWidth = Math.max(4, w / 120); x.lineCap = 'round'; x.lineJoin = 'round'; x.strokeStyle = '#122433'; x.beginPath();
  for (let i = 0; i <= 90; i++) { const t = i / 90, px = w * (0.1 + 0.75 * t),
    py = h * (0.5 + 0.2 * Math.sin(t * 19) * (1.1 - t) - 0.1 * Math.sin(t * 3.1)); i ? x.lineTo(px, py) : x.moveTo(px, py); }
  x.stroke(); x.beginPath(); x.moveTo(w * 0.18, h * 0.78); x.quadraticCurveTo(w * 0.5, h * 0.7, w * 0.88, h * 0.74); x.stroke();
  const hint = document.querySelector('.modal .hint'); if (hint) hint.style.display = 'none'; })()""")
shot("4_sign", 1.0)
js("document.querySelector('.modal [data-x=cancel]') && document.querySelector('.modal [data-x=cancel]').click()")

# 5. toolbox talk in the workers' language
go("#talk", 1.5)
js("document.getElementById('tk-lang').value = 'zu'; document.querySelector('[data-act=talk-ai]').click()")
wait_for("!!document.querySelector('.talk-text')", 150)
js("window.scrollTo(0,0)")
shot("5_talk", 1.5)

# 6. an incident from a voice note
js("(async () => { await dropDraft('task'); await dropDraft('talk'); })()")
go("#incident", 1.5)
js("""(() => { document.querySelector('#view details').open = true;
  document.getElementById('inc-text').value = 'This is Piet, site supervisor. Today at about 10:20 on the north boundary trench, a section of the trench wall gave way while Thabo was laying pipe. Soil came down to his knees. We dug him out by hand within two minutes. He has a bruised left leg, no other injury. The first aider checked him and we took him to the clinic for a check-up. We stopped all trench work, barricaded the trench and called the excavation supervisor to shore the walls.';
  document.querySelector('[data-act=inc-text]').click(); })()""")
wait_for("document.querySelector('h1') && document.querySelector('h1').textContent.includes('Incident report')", 150)
js("document.querySelectorAll('#view .note.warn').forEach((n) => n.style.display = 'none'); window.scrollTo(0,0)")
shot("6_incident", 1.5)

# 7. the H&S plan, drafted by the app and approved
js("(async () => { await dropDraft('incident'); })()")
go("#hsplan", 2.5)
shot("7_plan", 1.0)

# 8. the safety file, always ready
go("#file", 2.5)
shot("8_file", 1.0)

ws.close()
proc.terminate()
