"""Local tagging shell: a stdlib-HTTP parent page that embeds the official cabt
viewer (iframe) and drives a side-panel for authoring Corrections.

Thin wrapper over ``service.py`` (the tested glue). No third-party deps. The shell
owns timeline navigation, so it always knows which Decision is being tagged; it
feeds the replay to the viewer via ``postMessage`` (ADR-0014).
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .categories import CATEGORIES
from .correction import SOURCES
from .service import decisions_payload, record_correction

STATE: dict = {}  # set by serve(): replay, our_team, agent, source, submission_id, store_path, viewer_dir


def _json(handler: BaseHTTPRequestHandler, payload, code: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _html(handler: BaseHTTPRequestHandler, text: str, code: int = 200) -> None:
    body = text.encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return _html(self, _SHELL_HTML)
        if self.path.startswith("/replay.json"):
            return _json(self, STATE["replay"])
        if self.path.startswith("/decisions.json"):
            return _json(self, decisions_payload(STATE["replay"], STATE.get("our_team")))
        if self.path.startswith("/meta.json"):
            return _json(self, {
                "categories": list(CATEGORIES),
                "sources": list(SOURCES),
                "agent": STATE.get("agent"),
                "source": STATE.get("source", "own"),
                "submission_id": STATE.get("submission_id"),
            })
        if self.path in ("/viewer/", "/viewer/index.html"):
            index = Path(STATE.get("viewer_dir", "")) / "index.html"
            if index.exists():
                return _html(self, index.read_text(encoding="utf-8"))
            return _html(self, _VIEWER_PLACEHOLDER)
        return _html(self, "<h1>404</h1>", 404)

    def do_POST(self):
        if not self.path.startswith("/correction"):
            return _json(self, {"error": "not found"}, 404)
        length = int(self.headers.get("Content-Length", 0))
        form = json.loads(self.rfile.read(length) or b"{}")
        try:
            corr = record_correction(
                STATE["replay"],
                frame=int(form["frame"]),
                correct=[int(i) for i in form["correct"]],
                category=form["category"],
                rationale=form.get("rationale", ""),
                source=form.get("source", STATE.get("source", "own")),
                agent=form.get("agent", STATE.get("agent", "")),
                store_path=STATE["store_path"],
                submission_id=form.get("submission_id", STATE.get("submission_id")),
                agent_version=form.get("agent_version", STATE.get("agent_version")),
                attribution=form.get("attribution") or None,
            )
        except (KeyError, ValueError) as exc:
            return _json(self, {"error": str(exc)}, 400)
        return _json(self, {"ok": True, "category": corr.category,
                            "correct_label": corr.correct_label})


def serve(replay: dict, *, store_path, agent="", source="own", our_team=None,
          submission_id=None, agent_version=None, viewer_dir="", host="127.0.0.1", port=8077):
    """Start the shell server (blocking). Returns the bound port."""
    STATE.update(replay=replay, store_path=str(store_path), agent=agent, source=source,
                 our_team=our_team, submission_id=submission_id, agent_version=agent_version,
                 viewer_dir=str(viewer_dir))
    httpd = ThreadingHTTPServer((host, port), _Handler)
    print(f"blunder_correction shell -> http://{host}:{httpd.server_address[1]}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return httpd.server_address[1]


_VIEWER_PLACEHOLDER = """<!doctype html><meta charset='utf-8'>
<body style="font:14px system-ui;padding:16px;color:#555">
<b>Official cabt viewer not vendored yet.</b>
<p>Build it once: <code>python tools/train/blunder/viewer/build.py</code><br>
Tagging still works from the panel on the right.</p></body>"""


_SHELL_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>blunder_correction</title>
<style>
 body{font:14px system-ui,sans-serif;margin:0;display:flex;height:100vh;color:#1a1a1a}
 #left{flex:1;border-right:1px solid #ddd;display:flex;flex-direction:column}
 #bar{padding:8px;border-bottom:1px solid #eee;display:flex;gap:6px;align-items:center}
 iframe{flex:1;border:0;width:100%}
 #panel{width:380px;padding:14px;overflow:auto}
 label{display:block;margin:10px 0 3px;font-weight:600}
 select,textarea,input{width:100%;box-sizing:border-box;font:13px system-ui}
 textarea{height:80px} .now{background:#f2f6fc;padding:8px;border-radius:5px}
 button{padding:6px 12px;margin-top:12px;cursor:pointer} #msg{margin-top:8px}
 .ko{color:#b00} .ok{color:#070}
</style></head><body>
<div id="left">
 <div id="bar">
  <button id="prev">◀ prev</button><button id="play">play ▶</button><button id="next">next ▶</button>
  <input id="scrub" type="range" min="0" value="0" style="flex:1">
  <span id="pos"></span>
 </div>
 <iframe id="viewer" src="/viewer/"></iframe>
</div>
<div id="panel">
 <h3>Tag a blunder</h3>
 <div class="now" id="now"></div>
 <label>Category</label><select id="category"></select>
 <label>Correct move(s) — the better legal option</label><select id="correct" multiple size="6"></select>
 <label>Source</label><select id="source"></select>
 <label>Attribution (optional)</label><input id="attribution" placeholder="hypothesis:&lt;id&gt; / missing_hypothesis / tactical / value / scouting">
 <label>Rationale</label><textarea id="rationale" placeholder="Why it's a blunder + the intended line"></textarea>
 <button id="save">Save Correction</button>
 <div id="msg"></div>
</div>
<script>
let D=[], META={}, i=0, timer=null, replayObj=null;
const $=id=>document.getElementById(id);
function postReplay(){
  const f=$('viewer');
  if(f&&f.contentWindow&&replayObj)
    f.contentWindow.postMessage({replay:replayObj,
      agents:((replayObj.info&&replayObj.info.TeamNames)||[]).map(n=>({name:n}))},'*');
}
async function boot(){
  META=await (await fetch('/meta.json')).json();
  D=(await (await fetch('/decisions.json')).json()).decisions;
  replayObj=await (await fetch('/replay.json')).json();
  $('viewer').addEventListener('load',postReplay);
  postReplay();                 // in case the iframe already loaded
  $('scrub').max=D.length-1;
  META.categories.forEach(c=>$('category').add(new Option(c,c)));
  META.sources.forEach(s=>$('source').add(new Option(s,s)));
  $('source').value=META.source||'own';
  show();
}
function show(){
  const d=D[i]; if(!d)return;
  $('pos').textContent=(i+1)+'/'+D.length;
  $('scrub').value=i;
  $('now').innerHTML=`frame ${d.frame} · turn ${d.turn} · seat ${d.seat} · <b>${d.context}</b><br>chosen: `+
     d.chosen.map(p=>d.options[p]?.label).join(', ');
  const sel=$('correct'); sel.innerHTML='';
  d.options.forEach(o=>{const op=new Option(o.label,o.pos); if(d.chosen.includes(o.pos))op.textContent+='  (chosen)'; sel.add(op);});
}
function go(n){i=Math.max(0,Math.min(D.length-1,n));show();}
$('prev').onclick=()=>go(i-1); $('next').onclick=()=>go(i+1);
$('scrub').oninput=e=>go(+e.target.value);
$('play').onclick=()=>{ if(timer){clearInterval(timer);timer=null;$('play').textContent='play ▶';}
  else{$('play').textContent='pause ⏸';timer=setInterval(()=>{if(i>=D.length-1){clearInterval(timer);timer=null;$('play').textContent='play ▶';}else go(i+1);},900);} };
$('save').onclick=async()=>{
  const d=D[i];
  const correct=[...$('correct').selectedOptions].map(o=>+o.value);
  const body={frame:d.frame,correct,category:$('category').value,rationale:$('rationale').value,
    source:$('source').value,agent:META.agent,submission_id:META.submission_id,attribution:$('attribution').value};
  const r=await fetch('/correction',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const j=await r.json();
  $('msg').className=j.ok?'ok':'ko';
  $('msg').textContent=j.ok?('Saved: '+j.category+' → '+j.correct_label):('Error: '+j.error);
};
boot();
</script></body></html>"""
