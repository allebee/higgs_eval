"""Single-file HTML trace viewer.

Goals (per task.md): a human finds a failing step in under 30 seconds.

* Left pane: case list; regressions sort to top, flaky flagged.
* Right pane: message timeline; failed assertions pinned and highlighted.
* Filter box + URL hash deep-link: `#case=foo` opens directly.

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
 :root {{ --pass:#1a7f37; --fail:#cf222e; --flaky:#bf8700; --bg:#f6f8fa; --mono:ui-monospace,Menlo,Consolas,monospace; }}
 * {{ box-sizing:border-box; }} body {{ font:13px/1.45 system-ui,sans-serif; margin:0; color:#1f2328; background:#fff; }}
 header {{ padding:10px 16px; border-bottom:1px solid #d0d7de; background:var(--bg); position:sticky; top:0; z-index:2; display:flex; gap:16px; align-items:center; flex-wrap:wrap;}}
 header h1 {{ font-size:15px; margin:0; }}
 .stat {{ display:inline-flex; flex-direction:column; min-width:72px; }}
 .stat b {{ font-size:14px; }}
 .stat span {{ color:#656d76; font-size:11px; }}
 #layout {{ display:grid; grid-template-columns:340px 1fr; height:calc(100vh - 60px); }}
 #left {{ border-right:1px solid #d0d7de; overflow-y:auto; }}
 #left input {{ width:100%; padding:8px; border:0; border-bottom:1px solid #d0d7de; outline:0; font:13px system-ui; }}
 .caserow {{ padding:8px 12px; border-bottom:1px solid #eaeef2; cursor:pointer; display:flex; gap:8px; align-items:center; }}
 .caserow:hover, .caserow.active {{ background:var(--bg); }}
 .pill {{ font-size:10px; font-weight:700; padding:2px 6px; border-radius:10px; color:#fff; }}
 .pill.pass {{ background:var(--pass); }} .pill.fail {{ background:var(--fail); }} .pill.flaky {{ background:var(--flaky); }}
 .regtag {{ font-size:10px; color:#cf222e; font-weight:700; margin-left:auto; }}
 #right {{ overflow-y:auto; padding:16px 24px; }}
 h2 {{ font-size:16px; margin:0 0 4px; }} .muted {{ color:#656d76; font-size:12px; }}
 details {{ border:1px solid #d0d7de; border-radius:6px; margin:8px 0; background:#fff; }}
 details > summary {{ padding:8px 12px; cursor:pointer; font-weight:600; list-style:none; }}
 details[open] > summary {{ border-bottom:1px solid #eaeef2; }}
 pre {{ background:var(--bg); padding:8px; border-radius:4px; overflow-x:auto; margin:0; font-family:var(--mono); font-size:12px; white-space:pre-wrap; word-break:break-word; max-height:360px; }}
 .role-user {{ border-left:3px solid #0969da; padding-left:8px; }}
 .role-assistant {{ border-left:3px solid #8250df; padding-left:8px; }}
 .role-tool {{ border-left:3px solid #656d76; padding-left:8px; }}
 .msg {{ margin:8px 0; }}
 .verdict {{ margin:4px 0; padding:6px 8px; border-radius:4px; background:#f6f8fa; }}
 .verdict.fail {{ background:#ffebe9; border-left:3px solid var(--fail); }}
 .verdict.pass {{ background:#dafbe1; border-left:3px solid var(--pass); }}
 .tc {{ font-family:var(--mono); font-size:11px; color:#0550ae; }}
 .hash {{ font-family:var(--mono); color:#656d76; font-size:11px; }}
</style></head>
<body>
<header>
  <h1>DRL Eval — {title}</h1>
  <div class="stat"><b>{pass_rate}</b><span>pass rate (95% CI: {ci_lo}–{ci_hi})</span></div>
  <div class="stat"><b>{passed}/{total}</b><span>runs</span></div>
  <div class="stat"><b>${cost}</b><span>cost</span></div>
  <div class="stat"><b>{p50}ms</b><span>p50</span></div>
  <div class="stat"><b>{p95}ms</b><span>p95</span></div>
  <div class="stat"><b>{flaky}</b><span>flaky</span></div>
  <div class="stat" style="color:#cf222e;"><b>{regressions}</b><span>regressions</span></div>
  <div class="muted">agent={agent_model} · judge={judge_model}</div>
</header>
<div id="layout">
  <div id="left">
    <input id="filter" placeholder="filter cases…">
    <div id="caselist"></div>
  </div>
  <div id="right"><p class="muted">Select a case on the left.</p></div>
</div>
<script id="DATA" type="application/json">{data_json}</script>
<script>
const DATA = JSON.parse(document.getElementById('DATA').textContent);
const list = document.getElementById('caselist');
const right = document.getElementById('right');
const filter = document.getElementById('filter');
const regressions = new Set(DATA.diff?.regressions || []);

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

function select(id) {{
  document.querySelectorAll('.caserow').forEach(r => r.classList.toggle('active', r.dataset.id===id));
  const c = DATA.cases.find(x => x.case_id === id);
  if (!c) return;
  history.replaceState(null, '', '#case=' + encodeURIComponent(id));
  const run = c.runs[0];
  const verdicts = (run.verdicts || []).map(v => `
    <div class="verdict ${{v.passed?'pass':'fail'}}">
      <b>${{v.passed?'✓':'✗'}} ${{esc(v.metric)}}</b> <span class="muted">[${{v.kind}}]</span>
      <div>${{esc(v.rationale)}}</div>
      ${{v.evidence?.length? '<pre>'+esc((v.evidence||[]).join('\n'))+'</pre>':''}}
    </div>`).join('');
  const trace = (run.trace_messages || []).map(m => renderMsg(m)).join('');
  right.innerHTML = `
    <h2>${{esc(c.case_id)}}</h2>
    <p class="muted">runs ${{c.runs.filter(r=>r.passed).length}}/${{c.runs.length}} passed
      · stopped=${{esc(run.stopped_reason||'?')}}
      · ${{run.wall_time_ms||0}}ms · $${{(run.cost_usd||0).toFixed(4)}}
      · <span class="hash">hash=${{esc(run.trace_hash||'')}}</span></p>
    <h3>Verdicts</h3>
    ${{verdicts || '<p class="muted">no verdicts</p>'}}
    <h3>Trace</h3>
    ${{trace || '<p class="muted">no trace data (error run?)</p>'}}
  `;
}}

function renderMsg(m) {{
  const role = m.role || 'assistant';
  if (role === 'system' || role === 'user') {{
    return `<details class="msg role-${{role}}"><summary>${{role.toUpperCase()}}</summary><pre>${{esc(typeof m.content==='string'?m.content:JSON.stringify(m.content,null,2))}}</pre></details>`;
  }}
  if (role === 'assistant') {{
    const tcs = (m.tool_calls||[]).map(tc => `<div class="tc">→ ${{esc(tc.name)}}(${{esc(JSON.stringify(tc.args))}})</div>`).join('');
    return `<details open class="msg role-assistant"><summary>ASSISTANT <span class="muted">(${{m.latency_ms||0}}ms)</span></summary>
      ${{m.text?'<pre>'+esc(m.text)+'</pre>':''}}
      ${{tcs}}
    </details>`;
  }}
  if (role === 'tool') {{
    const content = typeof m.content === 'string' ? m.content : JSON.stringify(m.content, null, 2);
    return `<details class="msg role-tool"><summary>TOOL: ${{esc(m.name||'?')}} <span class="muted">(${{m.latency_ms||0}}ms)</span></summary><pre>${{esc(content)}}</pre></details>`;
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
