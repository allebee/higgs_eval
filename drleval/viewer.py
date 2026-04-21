"""Single-file HTML trace viewer — Higgsfield-inspired dark theme.

Goals (per task.md): a human finds a failing step in under 30 seconds.

* Left pane: case list; regressions sort to top, flaky flagged.
* Right pane: message timeline; failed assertions pinned and highlighted.
* Filter box + URL hash deep-link: `#case=foo` opens directly.
* Message-level diff: when a previous-run trace is available for the same
  case, toggle a diff view that highlights added/removed/changed messages.

Zero JS framework. Data is embedded as JSON.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>DRL Eval — {title}</title>
<style>
 :root {{
   /* Higgsfield-inspired dark palette: near-black surfaces with magenta+violet accents. */
   --bg:#0a0a0b;
   --surface:#141417;
   --surface-2:#1c1c22;
   --border:#2a2a33;
   --text:#f5f5f7;
   --text-dim:#a1a1aa;
   --text-faint:#71717a;
   --accent:#ff2d7a;        /* hot magenta */
   --accent-2:#b829ff;      /* violet */
   --accent-gradient:linear-gradient(135deg,#ff2d7a 0%,#b829ff 100%);
   --pass:#10b981;
   --fail:#ff2d7a;
   --flaky:#f59e0b;
   --info:#60a5fa;
   --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
   --glow: 0 0 24px -8px #ff2d7a99;
 }}
 * {{ box-sizing:border-box; }}
 html,body {{ background:var(--bg); }}
 body {{ font:13px/1.5 -apple-system,"SF Pro Text",Inter,system-ui,sans-serif; margin:0; color:var(--text); }}
 ::-webkit-scrollbar {{ width:10px; height:10px; }}
 ::-webkit-scrollbar-track {{ background:var(--bg); }}
 ::-webkit-scrollbar-thumb {{ background:var(--border); border-radius:6px; }}
 ::-webkit-scrollbar-thumb:hover {{ background:#3a3a44; }}

 header {{
   padding:14px 20px; border-bottom:1px solid var(--border);
   background:linear-gradient(180deg, rgba(255,45,122,0.06) 0%, transparent 60%), var(--surface);
   position:sticky; top:0; z-index:2;
   display:flex; gap:20px; align-items:center; flex-wrap:wrap;
 }}
 header h1 {{
   font-size:15px; margin:0; font-weight:700; letter-spacing:-0.01em;
   background:var(--accent-gradient); -webkit-background-clip:text;
   background-clip:text; color:transparent;
 }}
 .brand-dot {{ display:inline-block; width:8px; height:8px; border-radius:50%;
   background:var(--accent-gradient); box-shadow:var(--glow); margin-right:8px; vertical-align:middle;
 }}
 .stat {{ display:inline-flex; flex-direction:column; min-width:72px; }}
 .stat b {{ font-size:15px; font-weight:600; color:var(--text); font-variant-numeric:tabular-nums; }}
 .stat span {{ color:var(--text-faint); font-size:10.5px; text-transform:uppercase; letter-spacing:0.06em; }}
 .stat.regressions b {{ color:var(--fail); }}

 #layout {{ display:grid; grid-template-columns:340px 1fr; height:calc(100vh - 62px); }}
 #left {{ border-right:1px solid var(--border); overflow-y:auto; background:var(--surface); }}
 #filter {{
   width:100%; padding:10px 12px; border:0; border-bottom:1px solid var(--border);
   background:var(--surface-2); color:var(--text); outline:0; font:13px system-ui;
 }}
 #filter::placeholder {{ color:var(--text-faint); }}
 #filter:focus {{ border-bottom-color:var(--accent); box-shadow:inset 0 -1px 0 var(--accent); }}

 .caserow {{
   padding:10px 14px; border-bottom:1px solid var(--border);
   cursor:pointer; display:flex; gap:8px; align-items:center;
   transition:background 120ms ease;
 }}
 .caserow:hover {{ background:var(--surface-2); }}
 .caserow.active {{ background:linear-gradient(90deg, rgba(255,45,122,0.12) 0%, rgba(184,41,255,0.06) 100%);
                    border-left:2px solid var(--accent); padding-left:12px; }}

 .pill {{
   font-size:9.5px; font-weight:700; padding:3px 7px; border-radius:999px; color:#fff;
   letter-spacing:0.04em; text-transform:uppercase;
 }}
 .pill.pass {{ background:var(--pass); box-shadow:0 0 12px -4px var(--pass); }}
 .pill.fail {{ background:var(--accent-gradient); box-shadow:var(--glow); }}
 .pill.flaky {{ background:var(--flaky); color:#111; }}
 .regtag {{ font-size:9.5px; color:var(--fail); font-weight:700; margin-left:auto; letter-spacing:0.05em; }}

 #right {{ overflow-y:auto; padding:20px 28px; background:var(--bg); }}
 h2 {{ font-size:17px; margin:0 0 6px; font-weight:700; letter-spacing:-0.01em; }}
 h3 {{ font-size:11.5px; margin:22px 0 10px; font-weight:600; color:var(--text-dim);
       text-transform:uppercase; letter-spacing:0.08em; }}
 .muted {{ color:var(--text-faint); font-size:12px; }}
 .hash {{ font-family:var(--mono); color:var(--text-faint); font-size:11px; }}

 details {{
   border:1px solid var(--border); border-radius:8px; margin:8px 0; background:var(--surface);
   overflow:hidden;
 }}
 details > summary {{
   padding:10px 14px; cursor:pointer; font-weight:600; list-style:none;
   display:flex; gap:10px; align-items:center;
 }}
 details > summary::-webkit-details-marker {{ display:none; }}
 details[open] > summary {{ border-bottom:1px solid var(--border); }}
 pre {{
   background:#0a0a0d; padding:10px 14px; overflow-x:auto; margin:0;
   font-family:var(--mono); font-size:12px; line-height:1.55;
   white-space:pre-wrap; word-break:break-word; max-height:400px;
   color:#e8e8ec;
 }}
 .role-user > summary {{ border-left:3px solid var(--info); }}
 .role-assistant > summary {{ border-left:3px solid var(--accent-2); }}
 .role-tool > summary {{ border-left:3px solid var(--text-faint); }}

 .verdict {{
   margin:6px 0; padding:10px 14px; border-radius:6px;
   background:var(--surface-2); border-left:3px solid var(--border);
 }}
 .verdict.fail {{
   background:linear-gradient(90deg, rgba(255,45,122,0.16) 0%, rgba(255,45,122,0.04) 100%);
   border-left-color:var(--fail);
 }}
 .verdict.pass {{
   background:rgba(16,185,129,0.08); border-left-color:var(--pass);
 }}
 .verdict b {{ font-weight:600; }}
 .verdict .rat {{ color:var(--text-dim); font-size:12.5px; margin-top:3px; }}
 .tc {{ font-family:var(--mono); font-size:11.5px; color:var(--accent); padding:4px 14px; }}
 .tc .name {{ color:var(--accent-2); font-weight:600; }}
 .latency {{ color:var(--text-faint); font-size:11px; font-family:var(--mono); margin-left:auto; }}

 .actions {{ display:flex; gap:8px; margin:12px 0 0; }}
 .btn {{
   background:var(--surface-2); color:var(--text); border:1px solid var(--border);
   padding:6px 12px; border-radius:6px; font-size:12px; cursor:pointer;
   transition:all 120ms ease; font-family:inherit;
 }}
 .btn:hover {{ border-color:var(--accent); color:var(--accent); }}
 .btn.active {{ background:var(--accent-gradient); border-color:transparent; color:#fff; }}

 .diff-added {{ background:rgba(16,185,129,0.12); border-left:3px solid var(--pass); }}
 .diff-removed {{ background:rgba(255,45,122,0.10); border-left:3px solid var(--fail); opacity:0.75; }}
 .diff-changed > summary {{ border-left:3px solid var(--flaky) !important; }}
 .diff-label {{
   display:inline-block; padding:1px 6px; border-radius:3px;
   font-size:9px; font-weight:700; text-transform:uppercase; letter-spacing:0.05em;
   margin-right:6px;
 }}
 .diff-label.added {{ background:var(--pass); color:#fff; }}
 .diff-label.removed {{ background:var(--fail); color:#fff; }}
 .diff-label.changed {{ background:var(--flaky); color:#111; }}

 .empty {{ padding:28px; text-align:center; color:var(--text-faint); }}
</style></head>
<body>
<header>
  <h1><span class="brand-dot"></span>DRL Eval · <span style="color:var(--text-faint);font-weight:500;">{title}</span></h1>
  <div class="stat"><b>{pass_rate}</b><span>pass rate · CI {ci_lo}–{ci_hi}</span></div>
  <div class="stat"><b>{passed}/{total}</b><span>runs</span></div>
  <div class="stat"><b>${cost}</b><span>cost</span></div>
  <div class="stat"><b>{p50}ms</b><span>p50</span></div>
  <div class="stat"><b>{p95}ms</b><span>p95</span></div>
  <div class="stat"><b>{flaky}</b><span>flaky</span></div>
  <div class="stat regressions"><b>{regressions}</b><span>regressions</span></div>
  <div class="muted" style="margin-left:auto;">agent={agent_model} · judge={judge_model}</div>
</header>
<div id="layout">
  <div id="left">
    <input id="filter" placeholder="filter cases…">
    <div id="caselist"></div>
  </div>
  <div id="right"><div class="empty">Select a case on the left.</div></div>
</div>
<script id="DATA" type="application/json">{data_json}</script>
<script>
const DATA = JSON.parse(document.getElementById('DATA').textContent);
const list = document.getElementById('caselist');
const right = document.getElementById('right');
const filter = document.getElementById('filter');
const regressions = new Set(DATA.diff?.regressions || []);
const prevByCase = DATA.prev_trace_messages || {{}}; // case_id -> [msgs]
let diffMode = false;

function esc(s) {{ return String(s ?? '').replace(/[&<>]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c])); }}
function sortCases(cases) {{
  return cases.slice().sort((a,b) => {{
    const ra = regressions.has(a.case_id) ? 0 : 1;
    const rb = regressions.has(b.case_id) ? 0 : 1;
    if (ra !== rb) return ra - rb;
    const pa = passRate(a), pb = passRate(b);
    if (pa !== pb) return pa - pb;
    return a.case_id.localeCompare(b.case_id);
  }});
}}
function passRate(c) {{ const p = c.runs.filter(r=>r.passed).length; return c.runs.length? p/c.runs.length:0; }}
function status(c) {{
  const pr = passRate(c);
  if (c.runs.length>1 && pr>0 && pr<1) return 'flaky';
  return pr===1 ? 'pass' : 'fail';
}}

function renderList(q='') {{
  list.innerHTML = '';
  const filtered = sortCases(DATA.cases).filter(c => !q || c.case_id.toLowerCase().includes(q.toLowerCase()));
  for (const c of filtered) {{
    const row = document.createElement('div');
    row.className = 'caserow'; row.dataset.id = c.case_id;
    const st = status(c);
    row.innerHTML = `<span class="pill ${{st}}">${{st.toUpperCase()}}</span>
      <span>${{esc(c.case_id)}}</span>
      <span class="muted">${{c.runs.filter(r=>r.passed).length}}/${{c.runs.length}}</span>
      ${{regressions.has(c.case_id)?'<span class="regtag">REGRESSION</span>':''}}`;
    row.onclick = () => select(c.case_id);
    list.appendChild(row);
  }}
}}

function msgKey(m) {{
  // Identity for diff: role + tool name + args (assistant) / content-hash (tool/user).
  if (!m) return '';
  if (m.role === 'assistant') {{
    const tcs = (m.tool_calls||[]).map(tc => tc.name + ':' + JSON.stringify(tc.args||{{}})).join('|');
    return 'a:' + (m.text||'').slice(0,80) + '|' + tcs;
  }}
  if (m.role === 'tool') {{
    return 't:' + (m.name||'') + ':' + (typeof m.content==='string' ? m.content.slice(0,120) : JSON.stringify(m.content).slice(0,120));
  }}
  return (m.role||'?') + ':' + (typeof m.content==='string' ? m.content.slice(0,80) : '');
}}

function diffMessages(prev, cur) {{
  // LCS-ish: for each cur msg, mark added if its key isn't in prev; removed for prev msgs absent in cur.
  const prevKeys = new Set(prev.map(msgKey));
  const curKeys = new Set(cur.map(msgKey));
  const out = [];
  // interleave by position; this keeps reading order intuitive.
  const maxLen = Math.max(prev.length, cur.length);
  for (let i=0; i<maxLen; i++) {{
    const p = prev[i], c = cur[i];
    const pk = p ? msgKey(p) : null;
    const ck = c ? msgKey(c) : null;
    if (p && !c) out.push({{m:p, tag:'removed'}});
    else if (c && !p) out.push({{m:c, tag:'added'}});
    else if (pk === ck) out.push({{m:c, tag:'same'}});
    else {{
      // position differs; emit as changed pair
      if (!curKeys.has(pk)) out.push({{m:p, tag:'removed'}});
      if (!prevKeys.has(ck)) out.push({{m:c, tag:'added'}});
      else out.push({{m:c, tag:'same'}});
    }}
  }}
  return out;
}}

function select(id) {{
  document.querySelectorAll('.caserow').forEach(r => r.classList.toggle('active', r.dataset.id===id));
  const c = DATA.cases.find(x => x.case_id === id);
  if (!c) return;
  history.replaceState(null, '', '#case=' + encodeURIComponent(id));
  const run = c.runs[0];
  const verdicts = (run.verdicts || []).map(v => `
    <div class="verdict ${{v.passed?'pass':'fail'}}">
      <b>${{v.passed?'✓':'✗'}} ${{esc(v.metric)}}</b> <span class="muted">[${{v.kind}}]</span>
      <div class="rat">${{esc(v.rationale)}}</div>
      ${{v.evidence?.length? '<pre style="margin-top:6px;">'+esc((v.evidence||[]).join('\n'))+'</pre>':''}}
    </div>`).join('');

  const curMsgs = run.trace_messages || [];
  const prevMsgs = prevByCase[id] || [];
  const canDiff = prevMsgs.length > 0;

  let traceHtml;
  if (diffMode && canDiff) {{
    const diffed = diffMessages(prevMsgs, curMsgs);
    traceHtml = diffed.map(d => renderMsg(d.m, d.tag)).join('');
  }} else {{
    traceHtml = curMsgs.map(m => renderMsg(m, null)).join('');
  }}

  const diffBtn = canDiff
    ? `<button class="btn ${{diffMode?'active':''}}" onclick="toggleDiff('${{id}}')">${{diffMode?'✓ ':'± '}}diff vs previous</button>`
    : '<span class="muted" style="padding:6px 0;">(no previous run to diff)</span>';

  right.innerHTML = `
    <h2>${{esc(c.case_id)}}</h2>
    <p class="muted">runs ${{c.runs.filter(r=>r.passed).length}}/${{c.runs.length}} passed
      · stopped=${{esc(run.stopped_reason||'?')}}
      · ${{run.wall_time_ms||0}}ms · $${{(run.cost_usd||0).toFixed(4)}}
      · <span class="hash">hash=${{esc(run.trace_hash||'')}}</span></p>
    <h3>Verdicts</h3>
    ${{verdicts || '<p class="muted">no verdicts</p>'}}
    <div class="actions">
      <h3 style="margin:0; padding-top:6px;">Trace</h3>
      <div style="margin-left:auto;">${{diffBtn}}</div>
    </div>
    ${{traceHtml || '<p class="muted" style="margin-top:10px;">no trace data (error run?)</p>'}}
  `;
}}

function toggleDiff(id) {{ diffMode = !diffMode; select(id); }}

function renderMsg(m, tag) {{
  const role = m.role || 'assistant';
  const diffClass = tag && tag !== 'same' ? ('diff-' + tag) : '';
  const label = tag && tag !== 'same' ? `<span class="diff-label ${{tag}}">${{tag}}</span>` : '';
  if (role === 'system' || role === 'user') {{
    return `<details class="msg role-${{role}} ${{diffClass}}"><summary>${{label}}${{role.toUpperCase()}}</summary><pre>${{esc(typeof m.content==='string'?m.content:JSON.stringify(m.content,null,2))}}</pre></details>`;
  }}
  if (role === 'assistant') {{
    const tcs = (m.tool_calls||[]).map(tc => `<div class="tc">→ <span class="name">${{esc(tc.name)}}</span>(${{esc(JSON.stringify(tc.args))}})</div>`).join('');
    return `<details open class="msg role-assistant ${{diffClass}}">
      <summary>${{label}}ASSISTANT<span class="latency">${{m.latency_ms||0}}ms</span></summary>
      ${{m.text?'<pre>'+esc(m.text)+'</pre>':''}}
      ${{tcs}}
    </details>`;
  }}
  if (role === 'tool') {{
    const content = typeof m.content === 'string' ? m.content : JSON.stringify(m.content, null, 2);
    return `<details class="msg role-tool ${{diffClass}}">
      <summary>${{label}}TOOL: <span style="color:var(--accent-2);">${{esc(m.name||'?')}}</span><span class="latency">${{m.latency_ms||0}}ms</span></summary>
      <pre>${{esc(content)}}</pre>
    </details>`;
  }}
  return `<pre>${{esc(JSON.stringify(m))}}</pre>`;
}}

filter.oninput = () => renderList(filter.value);
renderList();
const hash = decodeURIComponent((location.hash.match(/case=([^&]+)/)||[])[1]||'');
if (hash) select(hash);
else if (DATA.cases[0]) select(sortCases(DATA.cases)[0].case_id);
</script>
</body></html>
"""


def render_html(
    report: dict[str, Any],
    *,
    diff: dict[str, Any] | None,
    trace_messages_by_run: dict[tuple[str, int], list[dict[str, Any]]],
    prev_trace_messages_by_case: dict[str, list[dict[str, Any]]] | None = None,
    out_path: Path,
) -> Path:
    # Embed a subset of the trace (messages) inline so the HTML is self-contained.
    cases_out = []
    for c in report["cases"]:
        runs_out = []
        for r in c["runs"]:
            tm = trace_messages_by_run.get((c["case_id"], r["run_index"]), [])
            runs_out.append({**r, "trace_messages": tm})
        cases_out.append({**c, "runs": runs_out})

    agg = report.get("aggregate", {})
    payload = {
        "cases": cases_out,
        "diff": diff or {},
        "prev_trace_messages": prev_trace_messages_by_case or {},
    }
    ci = agg.get("pass_rate_ci95", [0.0, 0.0])
    html_str = HTML_TEMPLATE.format(
        title=html.escape(report.get("run_id", "")[:8]),
        pass_rate=f"{agg.get('pass_rate', 0)*100:.0f}%",
        ci_lo=f"{ci[0]*100:.0f}%",
        ci_hi=f"{ci[1]*100:.0f}%",
        passed=agg.get("passed_runs", 0),
        total=agg.get("total_runs", 0),
        cost=f"{agg.get('total_cost_usd', 0):.4f}",
        p50=agg.get("p50_latency_ms", 0),
        p95=agg.get("p95_latency_ms", 0),
        flaky=agg.get("cases_flaky", 0),
        regressions=len((diff or {}).get("regressions", []) or []),
        agent_model=html.escape(report.get("agent_model", "")),
        judge_model=html.escape(report.get("judge_model", "")),
        # JSON is embedded inside a <script type="application/json">; escape </script.
        data_json=json.dumps(payload, default=str).replace("</", "<\\/"),
    )
    out_path.write_text(html_str)
    return out_path
