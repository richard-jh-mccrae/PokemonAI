"""Local tagging shell: a two-pane page -- HEROZ's colorful interactive replay on the
left, a frame/decision identifier + blunder-tagging pane on the right.

The right pane indexes frames the SAME way the colorful viewer does -- step ``X / total``
(the film frame number). An "Analyze as" selector picks which seat is *us*: it flips the
colorful viewer's perspective and auto-labels each saved blunder as own/peer (with the right
agent) from the frame's acting seat -- so blunders for BOTH players are taggable. HEROZ is
cross-origin so its step can't be read; the step box is the bridge. See ADR-0014 / ADR-0015.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .categories import CATEGORIES
from .correction import SOURCES
from .service import frames_payload, list_corrections, record_correction
from .store import delete_correction

STATE: dict = {}  # set by serve(): replay, our_team, agent, source, submission_id, store_path, viewer_dir


def _json(handler: BaseHTTPRequestHandler, payload, code: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_html(handler: BaseHTTPRequestHandler, text: str, code: int = 200) -> None:
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
            return _send_html(self, _SHELL_HTML)
        if self.path.startswith("/replay.json"):
            return _json(self, STATE["replay"])
        if self.path.startswith("/frames.json"):
            return _json(self, frames_payload(STATE["replay"], STATE.get("our_team")))
        if self.path.startswith("/corrections.json"):
            return _json(self, list_corrections(STATE["replay"], STATE["store_path"]))
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
                return _send_html(self, index.read_text(encoding="utf-8"))
            return _send_html(self, _VIEWER_PLACEHOLDER)
        return _send_html(self, "<h1>404</h1>", 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        form = json.loads(self.rfile.read(length) or b"{}")
        if self.path.startswith("/delete"):
            removed = delete_correction(str(form.get("id", "")), STATE["store_path"])
            return _json(self, {"ok": True, "removed": removed})
        if not self.path.startswith("/correction"):
            return _json(self, {"error": "not found"}, 404)
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
        return _json(self, {"ok": True, "id": corr.id, "category": corr.category, "seat": corr.seat,
                            "source": corr.source, "correct_label": corr.correct_label})


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
<b>Offline plain board not vendored.</b>
<p>Build it once: <code>python tools/train/blunder/viewer/build.py</code></p></body>"""


_SHELL_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>blunder_correction</title>
<style>
 *{box-sizing:border-box} body{font:14px system-ui,sans-serif;margin:0;display:flex;height:100vh;color:#1a1a1a}
 #left{flex:1;display:flex;flex-direction:column;min-width:0;border-right:1px solid #ddd}
 #vbar{padding:6px 8px;border-bottom:1px solid #eee;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
 #vbar .hint{color:#888;font-size:12px;margin-left:auto}
 iframe{flex:1;border:0;width:100%;background:#111}
 #right{width:400px;padding:14px;overflow:auto}
 #ids{font-size:12px;color:#555;background:#f6f6f6;padding:6px 8px;border-radius:5px}
 #nav{display:flex;gap:6px;align-items:center;margin:12px 0}
 #nav input{width:64px} #pick{flex:1}
 .now{background:#f2f6fc;padding:10px;border-radius:6px;margin-bottom:6px}
 .now .big{font-size:18px;font-weight:700}
 label{display:block;margin:10px 0 3px;font-weight:600} select,textarea,input{width:100%;font:13px system-ui}
 textarea{height:78px} #correct{height:120px}
 button{padding:6px 10px;cursor:pointer} #save{margin-top:12px;padding:8px 14px;font-weight:600}
 #msg{margin-top:8px} .ko{color:#b00} .ok{color:#070} #log{margin-top:6px;color:#555;font-size:12px}
 :disabled{opacity:.5}
 .item{border:1px solid #e4e4e4;border-radius:5px;padding:6px 8px;margin:5px 0;font-size:12px;background:#fafafa}
 .item .x{color:#b00;cursor:pointer;float:right;font-weight:700;margin-left:8px}
 .item .ed{color:#06c;cursor:pointer;float:right} .item i{color:#666}
</style></head><body>
<div id="left">
 <div id="vbar">
  <button id="reload">🎨 colorful</button><button id="tab">↗ new tab</button>
  <button id="plain">plain board</button>
  <span class="hint">read the step X/N from the viewer → type it on the right →</span>
 </div>
 <iframe id="viewer" name="viewer" src="about:blank"></iframe>
</div>
<div id="right">
 <div id="ids"></div>
 <label>Analyze as — which player is "us" (flips viewer + own/peer)</label>
 <select id="analyze"></select>
 <div id="nav">
  <button id="prev">◀</button>
  <label style="margin:0;font-weight:600">Step</label><input id="step" type="number" min="1"><span id="oftotal"></span>
  <select id="pick"></select>
  <button id="next">▶</button>
 </div>
 <div class="now" id="now"></div>
 <label>Category (the blunder identifier)</label><select id="category"></select>
 <label>Correct move(s) — the better legal option</label><select id="correct" multiple></select>
 <label>Source</label><select id="source"></select>
 <label>Attribution (optional)</label><input id="attribution" placeholder="hypothesis:&lt;id&gt; / missing_hypothesis / tactical / value / scouting">
 <label>Rationale</label><textarea id="rationale" placeholder="Why it's a blunder + the intended line"></textarea>
 <button id="save">Save blunder ▸ ship</button>
 <div id="msg"></div><div id="log"></div>
 <h3 style="margin:16px 0 4px">Logged blunders — this replay (<span id="count">0</span>)</h3>
 <div id="list"></div>
</div>
<script>
let FR=[],META={},i=0,replayObj=null,saved=0,total=0,teamNames=[],editingId=null,LIST=[];
const $=id=>document.getElementById(id);
const FORM=['category','correct','source','attribution','rationale','save'];
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const analyzeVal=()=>$('analyze').value;
const viewSeat=()=>{const v=analyzeVal(); return v==='both'?0:+v;};
const isOwn=seat=>{const v=analyzeVal(); return v==='both'||+v===seat;};
const pname=s=>(teamNames&&teamNames[s])||('Player '+s);

function openColorful(target){
  if(!replayObj) return;
  const r=replayObj, vl=r.steps[0][0].visualize, seat=viewSeat();
  for(let a=0;a<vl.length;a++)for(let j=0;j<2;j++){
    try{vl[a].current.players[j].ramainingTime=r.steps[a][j].observation.remainingOverageTime;}catch(e){}}
  vl[0].ps=(r.info&&r.info.TeamNames)||['0','1'];
  const epi=r.info&&r.info.EpisodeId;
  const f=document.createElement('form');
  f.method='POST'; f.target=target;
  f.action='https://ptcgvis.heroz.jp/Visualizer/Replay/'+(epi==null?seat:(epi+'/'+seat));
  const inp=document.createElement('input'); inp.type='hidden'; inp.name='json'; inp.value=JSON.stringify(vl);
  f.appendChild(inp); document.body.appendChild(f); f.submit(); f.remove();
}
async function refreshList(){
  LIST=await (await fetch('/corrections.json')).json();
  $('count').textContent=LIST.length;
  $('list').innerHTML=LIST.map((it,k)=>
    `<div class="item"><span class="x" onclick="removeItem(${k})">✕</span>`+
    `<span class="ed" onclick="editItem(${k})">edit</span>`+
    `<b>step ${it.step}</b> · T${it.turn} · seat ${it.seat} · ${esc(it.category)} · ${esc(it.source)}<br>`+
    `→ ${esc(it.correct_label||('opt '+it.correct.join(',')))}`+
    (it.rationale?`<br><i>${esc(it.rationale)}</i>`:'')+`</div>`).join('');
}
async function removeItem(k){
  const it=LIST[k]; if(!it) return;
  await fetch('/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:it.id})});
  if(editingId===it.id) editingId=null;
  refreshList();
}
function editItem(k){
  const it=LIST[k]; if(!it) return;
  gotoStep(it.step);
  $('category').value=it.category; $('rationale').value=it.rationale||''; $('source').value=it.source;
  [...$('correct').options].forEach(o=>o.selected=it.correct.includes(+o.value));
  editingId=it.id; $('msg').className=''; $('msg').textContent='editing — Save to replace'; $('right').scrollTop=0;
}
async function boot(){
  META=await (await fetch('/meta.json')).json();
  const p=await (await fetch('/frames.json')).json();
  FR=p.frames; total=p.total; teamNames=p.team_names||[];
  replayObj=await (await fetch('/replay.json')).json();
  $('ids').innerHTML=`ep <b>${p.episode_id??'?'}</b> · sub <b>${META.submission_id??'—'}</b> · detected seat <b>${p.seat??'(none)'}</b>`;
  $('analyze').add(new Option(`P0 — ${pname(0)}`,'0'));
  $('analyze').add(new Option(`P1 — ${pname(1)}`,'1'));
  $('analyze').add(new Option('both (self-play) — all own','both'));
  $('analyze').value=(p.seat==null?'0':String(p.seat));
  $('analyze').onchange=()=>{openColorful('viewer'); show(i);};
  $('step').max=total; $('oftotal').textContent='/'+total;
  META.categories.forEach(c=>$('category').add(new Option(c,c)));
  META.sources.forEach(s=>$('source').add(new Option(s,s)));
  FR.forEach((f,k)=>$('pick').add(new Option(`${f.step}/${total} · T${f.turn} · ${f.context||'—'}${f.taggable?'':' (—)'}`,k)));
  openColorful('viewer');
  show(0);
  refreshList();
}
function show(n){
  i=Math.max(0,Math.min(FR.length-1,n)); const f=FR[i], own=isOwn(f.seat);
  $('pick').value=i; $('step').value=f.step; $('source').value=own?'own':'peer';
  let h=`<div class="big">Step ${f.step}/${total} &nbsp;·&nbsp; Turn ${f.turn}</div>`+
    `<div>decision by <b>${pname(f.seat)}</b> (seat ${f.seat}) → saves as <b>${own?'own':'peer'}</b></div>`+
    `<div><b>${f.context||'(no decision here)'}</b>${f.type?' ('+f.type+')':''}</div>`;
  if(f.selected_label) h+=`<div>engine selected: <b>${f.selected_label}</b></div>`;
  $('now').innerHTML=h;
  const sel=$('correct'); sel.innerHTML=''; f.options.forEach(op=>sel.add(new Option(op.label,op.pos)));
  FORM.forEach(id=>$(id).disabled=!f.taggable);
  $('msg').className=''; $('msg').textContent=f.taggable?'':'(not a taggable frame — step to a decision)';
}
function gotoStep(s){const k=FR.findIndex(f=>f.step==s); if(k>=0)show(k);}
$('prev').onclick=()=>show(i-1); $('next').onclick=()=>show(i+1);
$('pick').onchange=e=>show(+e.target.value);
$('step').onchange=e=>gotoStep(+e.target.value);
$('reload').onclick=()=>openColorful('viewer'); $('tab').onclick=()=>openColorful('_blank');
$('plain').onclick=()=>{$('viewer').src='/viewer/';};
$('save').onclick=async()=>{
  const f=FR[i], correct=[...$('correct').selectedOptions].map(o=>+o.value), own=isOwn(f.seat);
  if(!correct.length){$('msg').className='ko';$('msg').textContent='pick the correct move(s)';return;}
  const body={frame:f.frame,correct,category:$('category').value,rationale:$('rationale').value,
    source:$('source').value, agent: own?META.agent:pname(f.seat),
    submission_id: own?META.submission_id:null, attribution:$('attribution').value};
  const r=await fetch('/correction',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const j=await r.json(); $('msg').className=j.ok?'ok':'ko';
  if(j.ok){
    if(editingId){await fetch('/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:editingId})}); editingId=null;}
    saved++; $('msg').textContent=`saved: ${pname(f.seat)} · ${j.source} · ${j.category} → ${j.correct_label}`;
    $('log').textContent=`${saved} blunder(s) shipped this session`; $('rationale').value=''; refreshList();
  } else $('msg').textContent='error: '+j.error;
};
boot();
</script></body></html>"""
