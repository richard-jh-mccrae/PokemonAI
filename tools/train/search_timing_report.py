"""Deterministic self-contained HTML view of a Search Timing Run."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path


def _number(value, *, scale=1.0, digits=2, suffix="") -> str:
    if value is None:
        return "—"
    return f"{float(value) * scale:.{digits}f}{suffix}"


def _row(result: dict) -> str:
    timing = result.get("timing") or {}
    metrics = result.get("metrics") or {}
    work = metrics.get("work") or {}
    phase = metrics.get("timing") or {}
    transport = metrics.get("transport") or {}
    root_source = result.get("root_source") or {}
    deck_match = (None if "deck_matches_current" not in root_source
                  else "exact" if root_source["deck_matches_current"]
                  else f"{root_source.get('deck_overlap_cards', '—')}/60")
    cells = (
        result.get("root_id"), result.get("agent"), result.get("frame_class"),
        result.get("method"), result.get("backend"), result.get("semantic_gate"),
        result.get("decision_gate"), result.get("value_gate"),
        (result.get("profile") or {}).get("timing_gate"),
        (result.get("tree_evidence") or {}).get("timing_gate"),
        root_source.get("observation_bytes"),
        root_source.get("runtime_deck"),
        deck_match,
        _number(timing.get("median_seconds"), scale=1000, suffix=" ms"),
        _number(timing.get("p95_seconds"), scale=1000, suffix=" ms"),
        _number(timing.get("first_seconds"), scale=1000, suffix=" ms"),
        _number(timing.get("repeat_median_seconds"), scale=1000, suffix=" ms"),
        _number(timing.get("simulations_per_second"), digits=1),
        metrics.get("simulations"), work.get("transitions"), work.get("evaluations"),
        work.get("chances"), _number(phase.get("prior_seconds"), scale=1000, suffix=" ms"),
        _number(phase.get("search_seconds"), scale=1000, suffix=" ms"),
        _number(phase.get("overhead_seconds"), scale=1000, suffix=" ms"),
        _number(transport.get("startup_seconds"), scale=1000, suffix=" ms"),
        transport.get("request_messages"), transport.get("response_messages"),
        (transport.get("request_bytes") or 0) + (transport.get("response_bytes") or 0),
        metrics.get("tree_nodes"), metrics.get("cache_entries"), metrics.get("stop_reason"),
    )
    return "<tr>" + "".join(f"<td>{escape(str(value if value is not None else '—'))}</td>"
                              for value in cells) + "</tr>"


def render_report(document: dict) -> str:
    if document.get("schema") != "search-timing-run" or document.get("schema_version") != 1:
        raise ValueError("unsupported Search Timing Run schema")
    if not isinstance(document.get("results"), list):
        raise ValueError("Search Timing Run results must be a list")
    source = document["source"]
    rows = "\n".join(_row(result) for result in document.get("results", ()))
    wire = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    wire = wire.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    dirty = "dirty" if source.get("dirty") else "clean"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(document['title'])}</title>
<style>
:root{{--ink:#172033;--muted:#687189;--line:#dfe3eb;--paper:#f7f8fb;--card:#fff;--accent:#3157d5;--hot:#d946ef}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:14px/1.45 system-ui,sans-serif}}
header,main{{max-width:1600px;margin:auto;padding:20px}}header{{background:#14213d;color:white;max-width:none}}
h1{{margin:0 0 8px;font-size:24px}}h2{{margin:26px 0 10px;font-size:18px}}.meta{{display:flex;gap:18px;flex-wrap:wrap;color:#d9e2ff}}
.panel{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;box-shadow:0 2px 8px #1c274015}}
.table-wrap{{overflow:auto}}table{{border-collapse:collapse;width:100%;white-space:nowrap}}th,td{{padding:7px 9px;border-bottom:1px solid var(--line);text-align:right}}
th{{position:sticky;top:0;background:#edf1fa;font-size:12px}}th:nth-child(-n+13),td:nth-child(-n+13){{text-align:left}}
.tree-grid{{display:grid;grid-template-columns:minmax(520px,2fr) minmax(320px,1fr);gap:12px}}select{{max-width:100%;padding:7px}}.graph-scroll{{height:560px;overflow:auto;background:#fbfcff;border:1px solid var(--line)}}
#tree{{display:block}}.edge{{stroke:#a7afbf}}.node rect{{fill:white;stroke:#71809e;stroke-width:1.5;rx:7}}.node.hot rect{{stroke:var(--hot);stroke-width:3}}.node.transposed rect{{fill:#f5f0ff}}.node text{{font-size:11px;pointer-events:none}}.node{{cursor:pointer}}
.facts{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6fa;padding:9px;border-radius:6px;max-height:240px;overflow:auto}}
.empty{{color:var(--muted);padding:30px;text-align:center}}@media(max-width:900px){{.tree-grid{{grid-template-columns:1fr}}.graph-scroll{{height:430px}}}}
</style></head><body>
<header><h1>{escape(document['title'])}</h1><div class="meta">
<span>{escape(document['generated_at'])} ({escape(document['timezone'])})</span>
<span>{escape(source.get('branch') or 'detached')}</span><span>{escape(source['commit'])}</span><span>{dirty}</span>
<span>suite {escape(document['suite']['name'])}</span></div></header><main>
<h2>Timing summary</h2><div class="panel table-wrap"><table><thead><tr>
<th>Root</th><th>Deck</th><th>Frame class</th><th>Method</th><th>Backend</th><th>Comparable</th><th>Decision gate</th><th>Value gate</th><th>Profile gate</th><th>Tree gate</th>
<th>Input bytes</th><th>Runtime deck</th><th>Current deck</th><th>Median</th><th>P95</th><th>First</th><th>Repeat median</th><th>Sim/s</th><th>Sim</th><th>Transitions</th>
<th>Evaluations</th><th>Chance</th><th>Prior</th><th>Search</th><th>Overhead</th><th>Worker startup</th><th>IPC requests</th><th>IPC responses</th><th>IPC bytes</th>
<th>Tree nodes</th><th>Cache</th><th>Stop</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>Tree traversal</h2><div class="panel"><select id="tree-select"></select><div class="tree-grid">
<div class="graph-scroll"><svg id="tree" role="img" aria-label="PUCT search graph"></svg></div><section id="details" class="empty">Select a captured node.</section>
</div></div>
<h2>Profiles</h2><div class="panel" id="profiles"></div>
</main><script>const RUN = {wire};
const ns='http://www.w3.org/2000/svg', select=document.querySelector('#tree-select'), svg=document.querySelector('#tree'), details=document.querySelector('#details');
const treeRows=RUN.results.filter(row=>row.tree); const cards=RUN.cards||{{}};
function el(name,attrs={{}}){{const x=document.createElementNS(ns,name);Object.entries(attrs).forEach(([k,v])=>x.setAttribute(k,v));return x}}
function unpack(v){{if(Array.isArray(v))return v.map(unpack);if(!v||typeof v!=='object')return v;if(v.$tuple)return v.$tuple.map(unpack);if(v.$frozenset)return v.$frozenset.map(unpack);if(v.$bytes)return v.$bytes;if(v.$type)return Object.assign({{_type:v.$type}},Object.fromEntries(Object.entries(v.fields).map(([k,x])=>[k,unpack(x)])));return Object.fromEntries(Object.entries(v).map(([k,x])=>[k,unpack(x)]))}}
function card(c){{if(!c)return '—';const id=c.card_id??c;return `${{cards[id]||'Card'}} #${{id}}`}}
function body(b){{return b?`${{card(b.card)}} · ${{b.hp}}/${{b.max_hp}} HP · E[${{(b.energies||[]).join(',')}}]`:'—'}}
function side(s){{if(!s)return '—';const hand=s.hand?((s.hand.bag?.cards||[]).map(card).join(', ')||`${{s.hand.count??s.hand_count}} hidden`):'—';return `Active: ${{body(s.active)}}\nBench: ${{(s.bench||[]).map(body).join('\\n       ')||'—'}}\nHand: ${{hand}}\nDeck: ${{s.deck_count}} · Prizes: ${{s.prize_count}}\nDiscard: ${{(s.discard?.cards||[]).map(card).join(', ')||'—'}}`}}
function actionName(e){{if(e.kind==='chance')return `chance slot ${{e.chance_slot}} · p=${{e.probability}}`;const a=e.action||{{}};return `${{a.kind||'action'}}${{a.parts?.length?' '+a.parts.join('/') : ''}} [${{(e.selection||[]).join(',')}}]`}}
function show(row,node){{const graph=row.tree,out=graph.edges.filter(e=>e.source_node_id===node.node_id),obs=unpack(JSON.parse(node.observation).payload),valuation=node.valuation||{{}};details.className='';details.innerHTML=`<h3>Node ${{node.node_id}} · ${{node.kind}}</h3><div class="facts"><pre>${{escapeHtml(side(obs.me))}}</pre><pre>${{escapeHtml(side(obs.them))}}</pre></div><h3>Turn / allowances</h3><pre>${{escapeHtml(JSON.stringify(obs.turn||{{}},null,2))}}</pre><h3>Available decisions</h3>${{actionTable(out)}}<h3>Ledger valuation</h3><p>Total ${{valuation.total??'—'}} · ${{valuation.status||'—'}}</p>${{componentTable(valuation.components||[])}}<h3>Search budget</h3><pre>${{escapeHtml(JSON.stringify({{node_reaches:node.visits,outgoing_visits:node.outgoing_visits,node_selections:node.selections,tree_pass:row.tree_evidence?.metrics,timing_gate:row.tree_evidence?.timing_gate}},null,2))}}</pre><h3>Raw legal observation</h3><pre>${{escapeHtml(JSON.stringify(obs,null,2))}}</pre>`}}
function escapeHtml(x){{return String(x).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
function actionTable(edges){{if(!edges.length)return '<p>Boundary. No outgoing action.</p>';return `<div class="table-wrap"><table><tr><th>Action</th><th>Prior</th><th>Visits</th><th>Q</th><th>Target</th><th>Exclusion</th></tr>${{edges.map(e=>`<tr><td>${{escapeHtml(actionName(e))}}</td><td>${{e.prior??'—'}}</td><td>${{e.visits}}</td><td>${{e.visits?e.value_sum/e.visits:'—'}}</td><td>${{e.target_node_id??'—'}}</td><td>${{escapeHtml(e.exclusion||'')}}</td></tr>`).join('')}}</table></div>`}}
function componentTable(parts){{if(!parts.length)return '<p>No components.</p>';return `<div class="table-wrap"><table><tr><th>Feature</th><th>Activation</th><th>Coefficient</th><th>Value</th></tr>${{parts.map(p=>`<tr><td>${{escapeHtml(p.key)}}</td><td>${{p.activation}}</td><td>${{p.coefficient}}</td><td>${{p.value}}</td></tr>`).join('')}}</table></div>`}}
function draw(index){{svg.replaceChildren();if(index<0)return;const row=treeRows[index],g=row.tree,nodes=g.nodes,depths={{}},incoming={{}};g.edges.forEach(e=>{{if(e.target_node_id!=null)incoming[e.target_node_id]=(incoming[e.target_node_id]||0)+1}});nodes.forEach(n=>(depths[n.depth??0]??=[]).push(n));const width=Math.max(800,(Math.max(...Object.keys(depths).map(Number))+1)*230),height=Math.max(540,...Object.values(depths).map(x=>x.length*105+50));svg.setAttribute('viewBox',`0 0 ${{width}} ${{height}}`);svg.style.width=`${{width}}px`;svg.style.height=`${{height}}px`;const pos={{}};Object.entries(depths).forEach(([d,list])=>list.forEach((n,i)=>pos[n.node_id]=[35+Number(d)*230,35+i*105]));g.edges.forEach(e=>{{if(e.target_node_id==null)return;const a=pos[e.source_node_id],b=pos[e.target_node_id],line=el('line',{{x1:a[0]+160,y1:a[1]+28,x2:b[0],y2:b[1]+28,class:'edge','stroke-width':1+Math.log2(1+e.visits),opacity:e.visits?1:.35}});svg.append(line)}});nodes.forEach(n=>{{const [x,y]=pos[n.node_id],classes=['node'];if(n.visits===Math.max(...nodes.map(x=>x.visits)))classes.push('hot');if((incoming[n.node_id]||0)>1)classes.push('transposed');const group=el('g',{{class:classes.join(' '),transform:`translate(${{x}} ${{y}})`}});group.append(el('rect',{{width:160,height:58}}));const t=el('text',{{x:8,y:17}});[`#${{n.node_id}} ${{n.kind}}`,`visits ${{n.visits}} · value ${{n.valuation?.total??'—'}}`,`depth ${{n.depth??'—'}} · in ${{incoming[n.node_id]||0}}`].forEach((line,i)=>{{const s=el('tspan',{{x:8,dy:i?16:0}});s.textContent=line;t.append(s)}});group.append(t);group.onclick=()=>show(row,n);svg.append(group)}});show(row,nodes.find(n=>n.node_id===g.root_node_id)||nodes[0])}}
treeRows.forEach((row,i)=>{{const o=document.createElement('option');o.value=i;o.textContent=`${{row.root_id}} · ${{row.method}} · ${{row.backend}}`;select.append(o)}});select.onchange=()=>draw(Number(select.value));if(treeRows.length)draw(0);else{{select.hidden=true;document.querySelector('.graph-scroll').innerHTML='<div class="empty">No tree pass in this run.</div>'}}
function profileRows(rows,kind){{if(!rows?.length)return '<p>None captured.</p>';const memory=kind==='allocation';return `<div class="table-wrap"><table><tr><th>File:line</th><th>${{memory?'Count':'Function'}}</th><th>${{memory?'Bytes':'Calls'}}</th><th>${{memory?'':'Own ms'}}</th><th>${{memory?'':'Cumulative ms'}}</th></tr>${{rows.slice(0,15).map(x=>`<tr><td>${{escapeHtml(x.file)}}:${{x.line}}</td><td>${{escapeHtml(memory?x.count:x.function)}}</td><td>${{memory?x.size_bytes:x.calls}}</td><td>${{memory?'':(x.total_seconds*1000).toFixed(2)}}</td><td>${{memory?'':(x.cumulative_seconds*1000).toFixed(2)}}</td></tr>`).join('')}}</table></div>`}}
function profileView(row){{const p=row.profile,workerLinks=p.workers.pstats.map((x,i)=>`<a href="${{escapeHtml(x)}}">worker ${{i+1}} pstats</a>`).join(' · ');return `<h3>${{escapeHtml(row.root_id)}} · ${{escapeHtml(row.method)}} · ${{escapeHtml(row.backend)}}</h3><p>timing gate ${{escapeHtml(p.timing_gate)}} · ${{p.elapsed_seconds==null?'failed':(p.elapsed_seconds*1000).toFixed(2)+' ms profiled'}} · peak ${{p.memory.peak_bytes.toLocaleString()}} bytes · <a href="${{escapeHtml(p.parent.pstats)}}">parent pstats</a>${{workerLinks?' · '+workerLinks:''}}</p><h4>Parent CPU</h4>${{profileRows(p.parent.top_functions,'cpu')}}<h4>Worker CPU</h4>${{profileRows(p.workers.top_functions,'cpu')}}<h4>Live allocations</h4>${{profileRows(p.memory.top_allocations,'allocation')}}`}}
document.querySelector('#profiles').innerHTML=RUN.results.filter(r=>r.profile).map(profileView).join('')||'<p>No profile pass in this run.</p>';
</script></body></html>"""


def write_report(run_path: Path, output: Path | None = None) -> Path:
    run_path = Path(run_path)
    document = json.loads(run_path.read_text(encoding="utf-8"))
    target = Path(output) if output is not None else run_path.with_name("report.html")
    target.write_text(render_report(document), encoding="utf-8", newline="\n")
    return target


__all__ = ("render_report", "write_report")
