"""Local tagging shell: a two-pane page -- HEROZ's colorful interactive replay on the
left, a frame/decision identifier + blunder-tagging pane on the right.

The right pane indexes frames the SAME way the colorful viewer does -- step ``X / total``
(the film frame number). An "Analyze as" selector picks which seat is *us*: it flips the
colorful viewer's perspective and auto-labels each saved blunder as own/peer (with the right
agent) from the frame's acting seat -- so blunders for BOTH players are taggable. HEROZ is
cross-origin so its step can't be read; the step box is the bridge.

A **Scope** selector says what the tag is *about* (ADR-0049): this decision or the whole turn. You
always tag from a real Decision -- the **Anchor** -- but off decision scope the record is keyed by
the Scope's subject, ``correct`` is optional, and the server embeds the Span of covered Decisions.
See ADR-0014 / ADR-0015 / ADR-0049.
"""
from __future__ import annotations

import json
import math
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .batch import load_game
from .categories import CATEGORIES
from .correction import SOURCES
from .seats import detect_seat
from .service import frames_payload, list_corrections, record_correction
from .store import delete_correction

STATE: dict = {}  # set by serve(): replays (paths), current, cache, our_team, agent, source, ...


def _game() -> dict:
    """The current Replay's loaded context (lazy + cached): replay, live trace, own-seat, build id."""
    idx = STATE["current"]
    cache = STATE["cache"]
    if idx not in cache:
        cache[idx] = load_game(STATE["replays"][idx])
    return cache[idx]


def _own_seat(game: dict) -> int | None:
    """Default 'Analyze as' seat: the log-derived own-seat, else team-name detection."""
    seat = game.get("live_seat")
    return seat if seat is not None else detect_seat(game["replay"], STATE.get("our_team"))


def _games_payload() -> dict:
    game = _game()
    info = game["replay"].get("info") or {}
    return {"count": len(STATE["replays"]), "current": STATE["current"],
            "episode_id": info.get("EpisodeId"), "own_seat": _own_seat(game)}


def _turn_plan_from_form(form: dict) -> dict | None:
    """None on a decision tag or an empty note, so the field stays sparse and never rides on a
    non-turn-plan Correction."""
    if form.get("scope") != "turn":
        return None
    intended = str(form.get("intended_line", ""))
    end_board = str(form.get("expected_end_board", ""))
    counterfactual = form.get("counterfactual")
    if not (intended.strip() or end_board.strip() or counterfactual):
        return None
    plan = {"intended_line": intended, "expected_end_board": end_board}
    if counterfactual:
        plan["counterfactual"] = counterfactual
    return plan


def _counterfactual_response(session_id: str, recorder) -> dict:
    view = recorder.view()
    payload = recorder.payload() if view["status"] == "complete" else None
    recorded = [{"block": step["block"], "label": step["label"]} for step in recorder.steps]
    return {"ok": True, "session": session_id, **view, "recorded_steps": recorded,
            "counterfactual": payload}


def _json_body(payload) -> bytes:
    def normalize(value):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        return value

    return json.dumps(normalize(payload), allow_nan=False).encode("utf-8")


def _json(handler: BaseHTTPRequestHandler, payload, code: int = 200) -> None:
    body = _json_body(payload)
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
            return _json(self, _game()["replay"])
        if self.path.startswith("/frames.json"):
            game = _game()
            return _json(self, frames_payload(game["replay"], STATE.get("our_team"),
                                              game.get("live_records"), game.get("live_seat"),
                                              game.get("live_records_by_seat")))
        if self.path.startswith("/corrections.json"):
            return _json(self, list_corrections(_game()["replay"], STATE["store_path"]))
        if self.path.startswith("/games.json"):
            return _json(self, _games_payload())
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
        if self.path.startswith("/game"):                 # switch which Replay we tag
            idx = max(0, min(len(STATE["replays"]) - 1, int(form.get("i", 0))))
            STATE["current"] = idx
            STATE["counterfactuals"].clear()
            return _json(self, {"ok": True, **_games_payload()})
        if self.path == "/counterfactual/start":
            try:
                from .counterfactual import CounterfactualRecorder
                recorder = CounterfactualRecorder.from_replay(
                    _game()["replay"], frame=int(form["frame"]), rng_seed=0)
                recorder.choose([int(i) for i in form["correct"]])
                session_id = uuid.uuid4().hex
                STATE["counterfactuals"][session_id] = recorder
                return _json(self, _counterfactual_response(session_id, recorder))
            except Exception as exc:  # cgpy must refuse unsupported paths without killing the shell
                return _json(self, {"error": str(exc)}, 400)
        if self.path == "/counterfactual/step":
            try:
                session_id = str(form["session"])
                recorder = STATE["counterfactuals"][session_id]
                recorder.choose([int(i) for i in form["choice"]])
                return _json(self, _counterfactual_response(session_id, recorder))
            except Exception as exc:
                return _json(self, {"error": str(exc)}, 400)
        if self.path == "/counterfactual/undo":
            try:
                session_id = str(form["session"])
                recorder = STATE["counterfactuals"][session_id]
                recorder.undo()
                return _json(self, _counterfactual_response(session_id, recorder))
            except Exception as exc:
                return _json(self, {"error": str(exc)}, 400)
        if self.path == "/counterfactual/cancel":
            removed = STATE["counterfactuals"].pop(str(form.get("session", "")), None)
            return _json(self, {"ok": True, "removed": removed is not None})
        if not self.path.startswith("/correction"):
            return _json(self, {"error": "not found"}, 404)
        game = _game()
        # Agent on saved tag: form value wins (own -> CLI --agent via META.agent; peer -> opponent
        # label), else auto-fill from THIS replay's build folder, else CLI default.
        agent = form.get("agent") or game.get("agent") or STATE.get("agent", "")
        try:
            corr = record_correction(
                game["replay"],
                frame=int(form["frame"]),
                correct=[int(i) for i in form["correct"]],
                category=form["category"],
                rationale=form.get("rationale", ""),
                source=form.get("source", STATE.get("source", "own")),
                agent=agent,
                store_path=STATE["store_path"],
                submission_id=form.get("submission_id", STATE.get("submission_id")),
                agent_version=STATE.get("agent_version") or game.get("agent_version"),
                agent_build=game.get("agent_build"),
                built_at=game.get("built_at"),
                live_records=game.get("live_records"),
                live_records_by_seat=game.get("live_records_by_seat"),
                replace_id=form.get("editing_id") or None,
                attribution=form.get("attribution") or None,
                posture_mismatch=bool(form.get("posture_mismatch", False)),  # opp Read wrong (ADR-0041)
                scope=form.get("scope", "decision"),   # decision | turn (ADR-0049); the Span
                turn_plan=_turn_plan_from_form(form),   # the human's ideal-line note
            )                                          # is assembled server-side from the Anchor
        except (KeyError, ValueError) as exc:
            return _json(self, {"error": str(exc)}, 400)
        return _json(self, {"ok": True, "id": corr.id, "category": corr.category, "seat": corr.seat,
                            "source": corr.source, "correct_label": corr.correct_label,
                            "scope": corr.scope, "subject": corr.subject})


def init_state(replays, *, store_path, agent="", source="own", our_team=None,
               submission_id=None, agent_version=None, viewer_dir=""):
    """Populate the server STATE for a batch of Replay paths (testable without starting HTTP)."""
    STATE.clear()
    STATE.update(replays=[str(p) for p in replays], current=0, cache={},
                 counterfactuals={},
                 store_path=str(store_path), agent=agent, source=source, our_team=our_team,
                 submission_id=submission_id, agent_version=agent_version, viewer_dir=str(viewer_dir))


def serve(replays, *, store_path, agent="", source="own", our_team=None,
          submission_id=None, agent_version=None, viewer_dir="", host="127.0.0.1", port=8077):
    """Blocking; returns the bound port. Each Replay's telemetry (ADR-0019) loads lazily per game."""
    init_state(replays, store_path=store_path, agent=agent, source=source, our_team=our_team,
               submission_id=submission_id, agent_version=agent_version, viewer_dir=viewer_dir)
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
 #right{width:400px;padding:14px;overflow:auto;font-size:12px}
 #ids{font-size:12px;color:#555;background:#f6f6f6;padding:6px 8px;border-radius:5px}
 #nav{display:flex;gap:6px;align-items:center;margin:12px 0}
 #nav input{width:64px} #pick{flex:1}
 .now{background:#f2f6fc;padding:10px;border-radius:6px;margin-bottom:6px}
 .now .big{font-size:18px;font-weight:700}
 .timing{font-size:15px;margin:4px 0}.timing b{font-variant-numeric:tabular-nums}
 label{display:block;margin:10px 0 3px;font-weight:600} select,textarea,input{width:100%;font:13px system-ui}
 textarea{height:200px;resize:vertical} #correct{height:120px} #cfchoice{height:100px}
 button{padding:6px 10px;cursor:pointer} #save{margin-top:12px;padding:8px 14px;font-weight:600}
 #msg{margin-top:8px} .ko{color:#b00} .ok{color:#070} #log{margin-top:6px;color:#555;font-size:12px}
 :disabled{opacity:.5}
 .item{border:1px solid #e4e4e4;border-radius:5px;padding:6px 8px;margin:5px 0;font-size:12px;background:#fafafa}
 .item .x{color:#b00;cursor:pointer;float:right;font-weight:700;margin-left:8px}
 .item .ed{color:#06c;cursor:pointer;float:right} .item i{color:#666}
 .crit{display:flex;align-items:center;gap:6px;color:#c00;font-weight:700;margin:12px 0 0}
 .crit input{width:auto;margin:0}
 .live{margin-top:6px;font-size:12px;color:#333;background:#eef4ee;padding:6px 8px;border-radius:5px}
 .live .verd{font-weight:700} .live .warn{color:#a50;font-weight:400}
 .posture{margin-top:5px;font-size:12px;color:#334;background:#eef1f8;padding:6px 8px;border-radius:5px}
 .posture .alt{color:#777} .posture .off{color:#999}
 .pmark{display:flex;align-items:center;gap:6px;color:#4457b8;font-weight:700;margin:8px 0 0}
 .pmark input{width:auto;margin:0} .pmark .h{color:#888;font-weight:400;font-size:12px}
 .scopehint{color:#777;margin-top:3px} .item .sc{color:#4a6}
</style></head><body>
<div id="left">
 <div id="vbar">
  <button id="reload">🎨 colorful</button><button id="tab">↗ new tab</button>
  <button id="plain">plain board</button>
  <span id="gnav" style="display:flex;gap:4px;align-items:center;margin-left:8px;border-left:1px solid #ddd;padding-left:8px">
   <button id="gprev">◀</button><b id="gpos">1/1</b>
   <span style="color:#888">ep <span id="gep">?</span></span><button id="gnext">▶</button>
  </span>
  <span class="hint">board follows the selected step</span>
 </div>
 <iframe id="viewer" name="viewer" src="/viewer/"></iframe>
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
 <label class="pmark" title="Flags the agent's opponent Read/Posture as wrong at this decision. /blunder-buster ties it to the believed archetype's Matchup Brief / recognition, not a generic weight."><input type="checkbox" id="posture_wrong"> Opponent read was wrong<span class="h">— tie this blunder to the matchup (archetype above)</span></label>
 <label>Scope — what this tag is about (ADR-0049)</label><select id="scope"></select>
 <div class="scopehint" id="scopehint"></div>
 <label>Category (the blunder identifier)</label><select id="category"></select>
 <label id="correctlab">Correct move(s) — the better legal option</label><select id="correct" multiple></select>
 <label>Source</label><select id="source"></select>
 <label>Attribution (optional)</label><input id="attribution" placeholder="hypothesis:&lt;id&gt; / missing_hypothesis / tactical / value / scouting">
 <label class="crit" title="blunder-buster resolves CRITICAL blunders first, one at a time, and never leaves one unfixed"><input type="checkbox" id="critical"> Critical</label>
 <label>Rationale — state the <b>general rule</b>, not just this instance</label><textarea id="rationale" placeholder="The rule the agent should learn (e.g. 'snipe the highest-threat benched attacker with energy'), then the intended line. This becomes the when() the Tuner authors."></textarea>
 <div id="turnplan" style="display:none">
  <label>Intended line — your ideal decision sequence</label>
  <textarea id="intended_line" style="height:70px" placeholder="e.g. retreat Cinderace → attach {F} to Solrock → KO the Active"></textarea>
  <label>Expected end-board — what the line sets up (the leaf's target)</label>
  <textarea id="expected_end_board" style="height:55px" placeholder="e.g. Mega Lucario active with 2 {F}, boost line armed for next turn"></textarea>
  <div class="live" id="cfbox">
   <b>Executable ideal turn</b> — cgpy forks from the alternate anchor and proves safe reordering.
   <div style="margin-top:6px"><button id="cfstart">Start from correct move</button>
    <button id="cfundo" disabled>Undo</button><button id="cfcancel" disabled>Reset</button></div>
   <div id="cfstatus" class="scopehint">not recorded</div>
   <select id="cfchoice" multiple style="display:none"></select>
   <button id="cfapply" style="display:none;margin-top:5px">Apply selected step</button>
   <div id="cfsteps"></div>
  </div>
  <div class="scopehint" id="firedhint"></div>
 </div>
 <button id="save">Save blunder ▸ ship</button>
 <div id="msg"></div><div id="log"></div>
 <h3 style="margin:16px 0 4px">Logged blunders — this replay (<span id="count">0</span>)</h3>
 <div id="list"></div>
</div>
<script>
let FR=[],META={},i=0,replayObj=null,viewerReplayObj=null,saved=0,total=0,teamNames=[],editingId=null,LIST=[];
let CFSESSION=null,CFPAYLOAD=null;
let plainReady=false,plainLoaded=false;
const $=id=>document.getElementById(id);
const FORM=['scope','category','correct','source','attribution','critical','posture_wrong','rationale','save'];
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
// The CRITICAL marker lives IN the rationale (case-sensitive word-boundary token, mirrors
// train.blunder.correction.is_critical). The checkbox is a bidirectional toggle of that token,
// so downstream (proposals/dashboard/blunder-buster) needs no change.
const CRIT_RE=/\\bCRITICAL\\b/;
const applyCritical=(t,on)=>{const s=t.replace(/\\bCRITICAL\\b[:：]?\\s*/g,'').replace(/^\\s+/,''); return on?('CRITICAL: '+s):s;};
const syncCrit=()=>{$('critical').checked=CRIT_RE.test($('rationale').value);};
const analyzeVal=()=>$('analyze').value;
const viewSeat=()=>{const v=analyzeVal(); return v==='both'?0:+v;};
const isOwn=seat=>{const v=analyzeVal(); return v==='both'||+v===seat;};
const pname=s=>(teamNames&&teamNames[s])||('Player '+s);

function openColorful(target){
  if(!replayObj) return;
  const r=viewerReplayObj||replayObj, vl=r.steps[0][0].visualize, seat=viewSeat();
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
function normalizeViewerReplay(replay){
  const copy=JSON.parse(JSON.stringify(replay));
  const frames=copy?.steps?.[0]?.[0]?.visualize||[];
  for(const frame of frames){
    const current=frame.current||{};
    current.stadium=Array.isArray(current.stadium)?current.stadium:[];
    for(const player of current.players||[]){
      for(const area of ['active','bench','discard','prize'])
        player[area]=Array.isArray(player[area])?player[area]:[];
      if(!Array.isArray(player.hand))
        player.hand=Array.from({length:Number(player.handCount)||0},()=>({name:'Hidden'}));
      for(const card of [...player.active,...player.bench,...player.hand,...player.discard,...current.stadium]){
        if(!card) continue;
        if(card.name==null) card.name='Hidden';
        if(!Array.isArray(card.energies)) card.energies=[];
      }
    }
  }
  return copy;
}
function postPlain(){
  if(!plainReady||!viewerReplayObj) return;
  const payload=plainLoaded?{step:i}:{
    replay:viewerReplayObj, agents:teamNames.map(name=>({name})), step:i, parentHandlesUi:true};
  $('viewer').contentWindow.postMessage(payload,location.origin);
  plainLoaded=true;
}
function openPlain(force=false){
  plainLoaded=false;
  if(new URL($('viewer').src,location.href).pathname!=='/viewer/'){
    plainReady=false; $('viewer').src='/viewer/';
  }else if(force){
    plainReady=false; $('viewer').contentWindow.location.reload();
  }else if(plainReady) postPlain();
}
function watchPlainControls(){
  const doc=$('viewer').contentDocument;
  if(!doc||doc.documentElement.dataset.shellWatching) return;
  doc.documentElement.dataset.shellWatching='1';
  const tidy=()=>{
    const seen=new Set();
    for(const button of doc.querySelectorAll('button')){
      const key=button.textContent+'|'+button.style.left+'|'+button.style.top;
      if(seen.has(key)) button.remove(); else seen.add(key);
    }
  };
  new MutationObserver(tidy).observe(doc.documentElement,{childList:true,subtree:true});
  tidy();
}
window.addEventListener('message',event=>{
  if(event.source===$('viewer').contentWindow&&event.data&&event.data.ready){
    plainReady=true; watchPlainControls(); postPlain();
  }
});
// A scoped tag (turn, ADR-0049) shares its Anchor step with the Decision tags inside it, so
// the row states what it is ABOUT; a prescription-free one has no "→ correct" line to show.
const scopeTag=it=>it.scope==='turn'?`turn ${it.subject} (${it.span_len} decisions)`
  :'';
const turnGrade=it=>{
  const grade=it.turn_plan&&it.turn_plan.grade, first=grade&&grade.first_divergence;
  if(!grade) return '';
  return ` · <b class="sc">grade ${esc(grade.status)}${first?` @ f${first.frame}`:''}</b>`;
};
async function refreshList(){
  LIST=await (await fetch('/corrections.json')).json();
  $('count').textContent=LIST.length;
  $('list').innerHTML=LIST.map((it,k)=>
    `<div class="item"><span class="x" onclick="removeItem(${k})">✕</span>`+
    `<span class="ed" onclick="editItem(${k})">edit</span>`+
    `<b>step ${it.step}</b> · T${it.turn} · seat ${it.seat} · ${esc(it.category)} · ${esc(it.source)}`+
    (it.decision_seconds!=null?` · ${it.decision_seconds.toFixed(3)}s`:'')+
    (it.scope!=='decision'?` · <b class="sc">${esc(scopeTag(it))}</b>`:'')+
    turnGrade(it)+
    (CRIT_RE.test(it.rationale||'')?' · <b style="color:#c00">⚠ CRITICAL</b>':'')+
    (it.posture_mismatch?' · <b style="color:#4457b8">🔮 read wrong</b>':'')+
    (it.correct.length?`<br>→ ${esc(it.correct_label||('opt '+it.correct.join(',')))}`:'')+
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
  $('posture_wrong').checked=!!it.posture_mismatch;   // after gotoStep→show() reset it
  $('intended_line').value=(it.turn_plan&&it.turn_plan.intended_line)||'';
  $('expected_end_board').value=(it.turn_plan&&it.turn_plan.expected_end_board)||'';
  resetCF(false);
  if(it.turn_plan&&it.turn_plan.counterfactual){
    CFPAYLOAD=it.turn_plan.counterfactual; renderStoredCF(CFPAYLOAD);}
  $('scope').value=it.scope||'decision'; applyScope();
  syncCrit();
  [...$('correct').options].forEach(o=>o.selected=it.correct.includes(+o.value));
  editingId=it.id; $('msg').className=''; $('msg').textContent='editing — Save to replace'; $('right').scrollTop=0;
}
// The Scope selector. `correct` is mandatory at decision scope and OPTIONAL at turn scope (giving it
// asserts THIS Anchor is the first divergent Decision). Identity follows the scope's subject, not
// the frame.
function fillScope(f){
  const keep=$('scope').value||'decision';             // sticky while stepping frames
  $('scope').innerHTML='';
  $('scope').add(new Option('this decision','decision'));
  $('scope').add(new Option('turn '+f.turn+' (this seat)','turn'));
  $('scope').value=keep;
  if(!$('scope').value) $('scope').value='decision';
  applyScope();
}
function applyScope(){
  const s=$('scope').value, sel=$('correct'), optional=FR[i].min_count===0;
  sel.disabled=!FR[i].taggable;
  // At decision scope on an OPTIONAL select, selecting nothing is itself the ruling — a decline.
  // Say so, or the affordance exists and no human knows it is there.
  $('correctlab').innerHTML=s==='decision'?(optional
      ?'Correct move(s) — the better legal option, or <i>none</i> to rule a <b>decline</b>'
      :'Correct move(s) — the better legal option')
    :'Correct move(s) — <i>optional</i>: the first divergent option at this anchor';
  $('scopehint').textContent=s==='decision'?''
    :'keyed by the turn, not this frame — every decision of the turn travels with the tag';
  $('turnplan').style.display=(s==='turn')?'block':'none';   // the human's ideal-line note
  if(s==='turn') updateFired();
}
async function postCF(path,body){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  return r.json();
}
function resetCF(cancel=true){
  if(cancel&&CFSESSION) postCF('/counterfactual/cancel',{session:CFSESSION});
  CFSESSION=null; CFPAYLOAD=null;
  $('cfstatus').textContent='not recorded'; $('cfstatus').className='scopehint';
  $('cfchoice').style.display='none'; $('cfapply').style.display='none';
  $('cfchoice').innerHTML=''; $('cfsteps').innerHTML='';
  $('cfundo').disabled=true; $('cfcancel').disabled=true;
}
function renderStoredCF(proof){
  const rel=proof.adjacent_relations||[], commutes=rel.filter(x=>x.status==='commutes').length;
  $('cfstatus').className='ok';
  $('cfstatus').textContent=`complete · ${proof.steps.length} menu steps · ${commutes} safe swap(s)`+
    ((proof.randomness||[]).length?` · sampled randomness ${(proof.randomness||[]).length}×`:'');
  $('cfsteps').innerHTML=proof.steps.map((s,k)=>`<div>${k+1}. ${esc(s.label||'?')}</div>`).join('')+
    rel.map(x=>`<div><b>${esc(x.status)}</b>: ${esc(x.left)} ↔ ${esc(x.right)}</div>`).join('');
  $('cfcancel').disabled=false;
}
function renderCF(j){
  if(!j.ok){$('cfstatus').className='ko';$('cfstatus').textContent=j.error||'cgpy refused';return;}
  CFSESSION=j.session; CFPAYLOAD=j.counterfactual||null;
  $('cfundo').disabled=!j.step_count;
  $('cfsteps').innerHTML=(j.recorded_steps||[]).map((s,k)=>
    `<div>${k+1}. ${esc(s.label)} <span class="scopehint">block ${s.block}</span></div>`).join('');
  if(CFPAYLOAD){renderStoredCF(CFPAYLOAD);$('cfchoice').style.display='none';$('cfapply').style.display='none';return;}
  $('cfstatus').className='scopehint';
  $('cfstatus').textContent=`recording · choose ${j.min_count}..${j.max_count} option(s)`;
  $('cfchoice').innerHTML=''; (j.options||[]).forEach(o=>$('cfchoice').add(new Option(o.label,o.position)));
  $('cfchoice').style.display='block'; $('cfapply').style.display='inline-block'; $('cfcancel').disabled=false;
}
$('cfstart').onclick=async()=>{
  const correct=[...$('correct').selectedOptions].map(o=>+o.value);
  if($('scope').value!=='turn'||!correct.length){
    $('cfstatus').className='ko';$('cfstatus').textContent='select a turn-scope correct anchor first';return;}
  resetCF(); $('cfstatus').textContent='starting cgpy…';
  renderCF(await postCF('/counterfactual/start',{frame:FR[i].frame,correct}));
};
$('cfapply').onclick=async()=>{
  const choice=[...$('cfchoice').selectedOptions].map(o=>+o.value);
  renderCF(await postCF('/counterfactual/step',{session:CFSESSION,choice}));
};
$('cfundo').onclick=async()=>renderCF(await postCF('/counterfactual/undo',{session:CFSESSION}));
$('cfcancel').onclick=()=>resetCF();
// Show which rule(s) the human's `correct` pick currently fires (from the live @T trace's opts.fired),
// so `leans_on_rule` is DERIVED, never typed — blunder-buster reads the same `fired` at consume time.
function updateFired(){
  const f=FR[i], sel=[...$('correct').selectedOptions].map(o=>+o.value);
  if(!f||!f.live||!f.live.opts||!sel.length){$('firedhint').textContent='';return;}
  const rules=new Set();
  sel.forEach(idx=>{const o=f.live.opts.find(x=>x.i===idx);(o&&o.fired||[]).forEach(fr=>rules.add(fr[0]));});
  $('firedhint').innerHTML=rules.size
    ?('your pick currently fires: <b>'+[...rules].map(esc).join(', ')+'</b> — the rule(s) it may lean on')
    :'your pick fires no scored rule in the live trace';
}
async function boot(){
  META=await (await fetch('/meta.json')).json();
  META.categories.forEach(c=>$('category').add(new Option(c,c)));
  META.sources.forEach(s=>$('source').add(new Option(s,s)));
  $('critical').onchange=()=>{$('rationale').value=applyCritical($('rationale').value,$('critical').checked);};
  $('rationale').oninput=syncCrit;
  $('scope').onchange=applyScope;
  $('correct').onchange=()=>{updateFired();if(CFSESSION||CFPAYLOAD)resetCF();};
  $('analyze').onchange=()=>{fillPick(); show(i);};
  $('gprev').onclick=()=>switchGame(-1); $('gnext').onclick=()=>switchGame(1);
  loadGame();
}
async function loadGame(){
  const g=await (await fetch('/games.json')).json();
  $('gpos').textContent=(g.current+1)+'/'+g.count; $('gep').textContent=g.episode_id??'?';
  $('gprev').disabled=g.current<=0; $('gnext').disabled=g.current>=g.count-1;
  const p=await (await fetch('/frames.json')).json();
  FR=p.frames; total=p.total; teamNames=p.team_names||[];
  replayObj=await (await fetch('/replay.json')).json();
  viewerReplayObj=normalizeViewerReplay(replayObj);
  const seat=(g.own_seat!=null?g.own_seat:(p.seat!=null?p.seat:0));
  $('ids').innerHTML=`ep <b>${p.episode_id??'?'}</b> · sub <b>${META.submission_id??'—'}</b> · own seat <b>${g.own_seat??p.seat??'(none)'}</b>`;
  $('analyze').innerHTML='';
  $('analyze').add(new Option(`P0 — ${pname(0)}`,'0'));
  $('analyze').add(new Option(`P1 — ${pname(1)}`,'1'));
  $('analyze').add(new Option('both (self-play) — all own','both'));
  $('analyze').value=String(seat);
  $('step').max=total; $('oftotal').textContent='/'+total;
  fillPick();
  editingId=null;
  openPlain(); show(0); refreshList();
}
async function switchGame(d){
  const g=await (await fetch('/games.json')).json();
  const j=g.current+d; if(j<0||j>=g.count) return;
  await fetch('/game',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({i:j})});
  loadGame();
}
function show(n){
  if(FR.length) resetCF();
  i=Math.max(0,Math.min(FR.length-1,n)); const f=FR[i], own=isOwn(f.seat);
  $('pick').value=i; $('step').value=f.step; $('source').value=own?'own':'peer';
  let h=`<div class="big">Step ${f.step}/${total} &nbsp;·&nbsp; Turn ${f.turn}</div>`+
    `<div>decision by <b>${pname(f.seat)}</b> (seat ${f.seat}) → saves as <b>${own?'own':'peer'}</b></div>`+
    `<div><b>${f.context||'(no decision here)'}</b>${f.type?' ('+f.type+')':''}</div>`;
  if(f.taggable) h+=`<div class="timing">decision time: <b>${f.decision_seconds==null?'unavailable':f.decision_seconds.toFixed(3)+'s'}</b></div>`;
  if(f.lethal_proof_seconds!=null) h+=`<div class="timing">Lethal solver: <b>${f.lethal_proof_seconds.toFixed(3)}s</b></div>`;
  if(f.search_timing){
    const S=f.search_timing, sec=x=>Number(x).toFixed(1)+'s';
    const focus=S.strategy_focus_position==null?'not focused':`${S.strategy_focus_position} of ${S.strategy_focus_count}`;
    h+=`<div class="live"><b>Bellman search timing</b>`+
      `<div>Total search: <b>${sec(S.total_seconds)}</b></div>`+
      `<div>Final sequence first found: <b>${sec(S.first_found_seconds)}</b></div>`+
      `<div>Final sequence stabilized: <b>${sec(S.stabilized_seconds)}</b></div>`+
      `<div>Strategy wave: <b>${esc(S.strategy_wave||'unavailable')}</b></div>`+
      `<div>Strategy focus position: <b>${focus}</b></div>`+
      `<div>Remaining search after answer: <b>${sec(S.remaining_seconds)}</b></div></div>`;
  }
  if(f.selected_label) h+=`<div>engine selected: <b>${f.selected_label}</b></div>`;
  if(f.live){
    // The shipped agent's @T record for this decision (ADR-0019): how it ACTUALLY decided. A
    // non-null lethal/planned verdict means that layer short-circuited scoring (ADR-0030/0031) —
    // shown so the rationale can target the right layer (planner/solver code, not weights).
    const L=f.live, arr=a=>'['+((a||[]).join(','))+']';
    h+=`<div class="live">live @T: chose ${arr(L.chosen)} · margin ${L.margin??'?'}`+
      (L.lethal?`<div class="verd">&#127919; LETHAL ${esc(L.lethal.kind||'')} &rarr; ${arr(L.lethal.step)} — ${esc(L.lethal.why||'')}</div>`:'')+
      (L.planned?`<div class="verd">&#129517; PLANNED ${esc(L.planned.goal||'')} &rarr; ${arr(L.planned.step)} — ${esc(L.planned.why||'')}</div>`:'')+
      ((L.lethal||L.planned)?`<div class="warn">solver/planner drove this pick — scores didn't; fix = planner.py (win rung vs heuristic rungs), not weights</div>`:'')+
      // Decide()-only reorder (ADR-0019): `chosen` is NOT argmax(score) by design, so a held-back
      // turn-ender or a greedy grab isn't a scoring bug — flag it so a blunder tag targets sequencing.
      ((L.reordered||L.grabbed)?`<div class="warn">${L.grabbed?'greedy multi-pick — chosen SET came from dynamic gap-scoring, not top-N static score':'attack-last resequenced the menu — a higher-score turn-ender was held (see ·deferred·); chosen is NOT argmax(score)'}</div>`:'')+
      `</div>`;
  }
  if(f.live&&f.live.posture){
    // The Scouting Posture the shipped agent held at this decision (ADR-0041): who it thought it
    // faced (top-k archetype candidates + posterior), the applied confidence γ, and the matched
    // Matchup Brief. This is the context for the "opponent read was wrong" checkbox below.
    const P=f.live.posture, c=P.cands||[];
    const top=c[0]?`${esc(c[0][0])} <span class="off">p=${c[0][1]}</span>`:'<span class="off">unrecognized</span>';
    const alt=c.slice(1,3).map(x=>`${esc(x[0])} ${x[1]}`).join(', ');
    h+=`<div class="posture">&#128302; agent read: <b>${top}</b> &nbsp;·&nbsp; &gamma;=${P.gamma??'?'}`+
      (P.brief?` · brief <b>${esc(P.brief)}</b>`:` · <span class="off">no brief</span>`)+
      (P.fav!=null?` · fav ${P.fav}`:'')+
      (alt?`<div class="alt">also weighed: ${alt}</div>`:'')+`</div>`;
  }
  if(f.live&&f.live.gamble){
    // The gamble rung's full working (ADR-0039/0019): every number behind the (non-)gamble, so a
    // shuffle-in / Ultra-Ball-fetch blunder tag can target the real defect (outs undercounted?
    // det baseline wrong? a stand-down gate too eager?). Sparse: present only when the rung ran.
    const G=f.live.gamble;
    if(!G.considered){
      h+=`<details class="live"><summary>&#127922; gamble: stood down — ${esc(G.why||'?')}</summary>`+
        `<div class="alt">the rung was reached but declined before pricing; if the human line here `+
        `was a refresh/dig, this gate is the thing to correct</div></details>`;
    }else{
      const cls=(G.classes||[]).map(c=>
        `<div>· ${esc(c.label)} — <b>${c.copies}</b> outs (cards ${esc((c.sought||[]).join(', '))}) `+
        `worth ${c.value}</div>`).join('');
      const ev=(G.evals||[]).map(e=>
        `<div>· opt ${e.i} (cid ${e.cid}, draw ${e.draws}): P=${e.p} &rarr; EV ${e.ev} for ${esc(e.label)}</div>`).join('');
      h+=`<details class="live"><summary>&#127922; gamble: priced — `+
        (G.best?`<b>fired</b> opt ${G.best[0]} EV ${G.best[1]}`:`<b>declined</b> (no EV beat the held line)`)+
        ` · det ${G.det} · pool ${G.pool}${G.burst?` · burst ${G.burst}`:''}</summary>`+
        (cls?`<div class="alt">outcome classes (cards sought):</div>`+cls:'')+
        (ev?`<div class="alt">per-option pricing:</div>`+ev:'')+`</details>`;
    }
  }
  $('now').innerHTML=h;
  const sel=$('correct'); sel.innerHTML=''; f.options.forEach(op=>sel.add(new Option(op.label,op.pos)));
  FORM.forEach(id=>$(id).disabled=!f.taggable);
  $('posture_wrong').checked=false;    // fresh frame -> unflagged (editItem re-checks it after)
  $('msg').className=''; $('msg').textContent=f.taggable?'':'(not a taggable frame — step to a decision)';
  fillScope(f);                        // anchor must be a Decision, whatever the scope
  syncCrit();
  postPlain();
}
function pickOption(f,k){
  // Our-agent decisions stand out: ▶ marker + bold (bold on <option> is browser-dependent, the
  // marker is the reliable cue). Show the turn, then the decision taken — easier to eyeball.
  const own=isOwn(f.seat), act=f.selected_label||f.context||'—';
  const timing=f.decision_seconds==null?'':` · ${f.decision_seconds.toFixed(3)}s`;
  const o=new Option(`${f.step}/${total} · T${f.turn}${timing} · ${own?'▶ ':''}${act}${f.taggable?'':' (—)'}`,k);
  if(own) o.style.fontWeight='bold';
  return o;
}
function fillPick(){
  const cur=$('pick').value; $('pick').innerHTML='';
  FR.forEach((f,k)=>$('pick').add(pickOption(f,k)));
  if(cur!=='') $('pick').value=cur;
}
function gotoStep(s){const k=FR.findIndex(f=>f.step==s); if(k>=0)show(k);}
$('prev').onclick=()=>show(i-1); $('next').onclick=()=>show(i+1);
$('pick').onchange=e=>show(+e.target.value);
$('step').onchange=e=>gotoStep(+e.target.value);
$('reload').onclick=()=>openColorful('viewer'); $('tab').onclick=()=>openColorful('_blank');
$('plain').onclick=()=>openPlain(true);
$('save').onclick=async()=>{
  const f=FR[i], scope=$('scope').value, own=isOwn(f.seat);
  const correct=[...$('correct').selectedOptions].map(o=>+o.value);
  // An empty `correct` at decision scope is a DECLINE — "take none of these" — and is a real ruling
  // wherever the select is OPTIONAL (Issue #229). It is refused everywhere else, including where
  // `min_count` is unknown, which is exactly what `build_correction` does with the same number: the
  // pane must never offer a save the validator will reject, nor block one it would accept.
  if(scope==='decision'&&!correct.length&&f.min_count!==0){
    $('msg').className='ko';$('msg').textContent='pick the correct move(s)';return;}
  const rationale=applyCritical($('rationale').value,$('critical').checked);   // checkbox owns the CRITICAL token
  const body={frame:f.frame,correct,category:$('category').value,rationale,
    scope:$('scope').value,                        // what the tag is about (ADR-0049)
    intended_line:$('intended_line').value, expected_end_board:$('expected_end_board').value,  // Phase-3 note
    counterfactual:CFPAYLOAD,
    source:$('source').value, agent: own?META.agent:pname(f.seat),
    submission_id: own?META.submission_id:null, attribution:$('attribution').value,
    posture_mismatch:$('posture_wrong').checked,   // opponent Read flagged wrong (ADR-0041)
    editing_id: editingId||''};   // edit flow: lets the server allow replacing this same tag
  const r=await fetch('/correction',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const j=await r.json(); $('msg').className=j.ok?'ok':'ko';
  if(j.ok){
    if(editingId){await fetch('/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:editingId})}); editingId=null;}
    saved++; $('msg').textContent=`saved: ${pname(f.seat)} · ${j.source} · ${j.scope}`+
      (j.subject!=null?` ${j.subject}`:'')+` · ${j.category}`+(j.correct_label?` → ${j.correct_label}`:'');
    $('log').textContent=`${saved} blunder(s) shipped this session`; $('rationale').value='';
    $('intended_line').value=''; $('expected_end_board').value=''; $('firedhint').textContent=''; resetCF();
    syncCrit(); refreshList();
  } else $('msg').textContent='error: '+j.error;
};
boot();
</script></body></html>"""
