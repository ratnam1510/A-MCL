"""
HTML Share Page Generator for A/MCL.

Aesthetic: "Warm Darkroom" — Fraunces variable serif display + Azeret Mono body.
Warm near-black (#0C0A08), cream text (#E8E0D0), terracotta accent (#C4654A).
Left-aligned asymmetric layout. Ruled-paper lines + corner glow + film grain.
"""

from __future__ import annotations

import html
import re
from datetime import datetime


def _escape(text: str) -> str:
    """HTML-escape and render markdown constructs into styled HTML."""
    escaped = html.escape(text)
    escaped = re.sub(
        r'```(\w*)\n(.*?)```',
        r'<pre class="codeblk" data-lang="\1">\2</pre>',
        escaped, flags=re.DOTALL,
    )
    escaped = re.sub(r'`([^`]+)`', r'<code class="ilc">\1</code>', escaped)
    escaped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
    escaped = re.sub(
        r'^(#{1,4})\s+(.+)$',
        lambda m: f'<span class="mdh mdh{len(m.group(1))}">{m.group(2)}</span>',
        escaped, flags=re.MULTILINE,
    )
    escaped = re.sub(
        r'^[\-\*]\s+(.+)$', r'<span class="mdb">\1</span>',
        escaped, flags=re.MULTILINE,
    )
    return escaped


PALETTE = {
    "antigravity": "#D4AA44",
    "cursor":      "#4FBE9E",
    "opencode":    "#D87A50",
    "claude":      "#BE8858",
    "amp":         "#9878D0",
    "roo-cline":   "#D462A0",
    "windsurf":    "#5A96D8",
    "copilot":     "#5AC8A2",
}
DFL_COLOR = "#887E70"


def _ac(name: str) -> str:
    return PALETTE.get(name, DFL_COLOR)


def _build_project_html(proj: dict, idx: int) -> str:
    project_name = proj["name"]
    project_path = proj["path"]
    messages = proj["messages"]
    decisions = proj["decisions"]
    file_changes = proj["file_changes"]
    agent_stats = proj["agent_stats"]

    n_msg = len(messages)
    n_dec = len(decisions)
    n_fil = len(file_changes)
    n_agt = len(agent_stats)
    total_am = sum(s.get("count", 0) for s in agent_stats)

    # ── Agent bars ──
    mx = max((s["count"] for s in agent_stats), default=1)
    bars = ""
    for ix, s in enumerate(agent_stats):
        ag = s["agent"]
        ct = s["count"]
        pct = int((ct / mx) * 100)
        shr = int((ct / total_am) * 100) if total_am else 0
        c = _ac(ag)
        bars += f'''
        <div class="bar" style="--d:{0.08 * ix:.2f}s">
          <div class="bar-top">
            <span class="bar-dot" style="background:{c}"></span>
            <span class="bar-name">{html.escape(ag)}</span>
            <span class="bar-nums">
              <span class="bar-ct">{ct}</span>
              <span class="bar-pct">{shr}%</span>
            </span>
          </div>
          <div class="bar-track">
            <div class="bar-fill" style="--w:{pct}%;background:{c}"></div>
          </div>
        </div>'''

    # ── Messages ──
    msgs = ""
    for i, m in enumerate(messages):
        role = m.get("role", "user")
        ag = m.get("agent", "")
        cont = _escape(m.get("content", ""))
        ts = m.get("timestamp", "")
        usr = role == "user"
        lbl = "You" if usr else (ag or "Assistant")
        c = "#504840" if usr else _ac(ag)
        av = lbl[0].upper()
        tsd = html.escape(ts[:16]) if ts else ""
        side = "msg-u" if usr else "msg-a"

        msgs += f'''
        <div class="msg {side}" style="--d:{min(0.012 * i, 1.0):.3f}s;--ac:{c}">
          <div class="msg-rail">
            <div class="msg-av" style="background:{c}">{av}</div>
            <div class="msg-line"></div>
          </div>
          <div class="msg-card">
            <div class="msg-top">
              <span class="msg-who" style="color:{c}">{html.escape(lbl)}</span>
              <span class="msg-ts">{tsd}</span>
            </div>
            <div class="msg-txt">{cont}</div>
          </div>
        </div>'''

    # ── Decisions ──
    decs = ""
    for i, d in enumerate(decisions):
        q = html.escape(d.get("question", ""))
        a = _escape(d.get("answer", ""))
        rn = _escape(d.get("reasoning", ""))
        dag = html.escape(d.get("agent", ""))
        c = _ac(d.get("agent", ""))
        alts = d.get("alternatives", "")
        if isinstance(alts, str) and alts:
            try:
                import json as _j
                alts = _j.loads(alts)
            except Exception:
                alts = []
        if not isinstance(alts, list):
            alts = []

        rn_html = (
            f'<div class="dec-reason"><span class="dec-lab">Reasoning</span>{rn}</div>'
            if rn else ""
        )
        alt_html = ""
        if alts:
            lis = "".join(f'<li>{html.escape(str(x))}</li>' for x in alts)
            alt_html = (
                f'<div class="dec-alts"><span class="dec-lab">Alternatives</span>'
                f'<ul>{lis}</ul></div>'
            )

        decs += f'''
        <details class="dec" style="--d:{0.06 * i:.2f}s">
          <summary class="dec-sum">
            <svg class="dec-chev" width="10" height="10" viewBox="0 0 10 10">
              <path d="M3 1L7 5L3 9" stroke="currentColor" stroke-width="1.4"
                    fill="none" stroke-linecap="round"/>
            </svg>
            <span class="dec-q">{q}</span>
            <span class="dec-tag" style="color:{c}">{dag}</span>
          </summary>
          <div class="dec-body">
            <div class="dec-ans"><span class="dec-lab">Decision</span>{a}</div>
            {rn_html}
            {alt_html}
          </div>
        </details>'''

    # ── Files ──
    acol = {"created": "#4FBE9E", "modified": "#D4AA44", "deleted": "#C4654A"}
    fls = ""
    for i, fc in enumerate(file_changes):
        fp = html.escape(fc.get("file_path", fc.get("file", "")))
        act = fc.get("action", "modified")
        sm = html.escape(fc.get("summary", ""))
        col = acol.get(act, "#887E70")
        base = fp.rsplit("/", 1)[-1] if "/" in fp else fp
        dirp = fp.rsplit("/", 1)[0] + "/" if "/" in fp else ""

        fls += f'''
        <div class="fl" style="--d:{0.025 * i:.3f}s">
          <div class="fl-pip" style="background:{col}"></div>
          <div class="fl-info">
            <span class="fl-dir">{dirp}</span><span class="fl-base">{base}</span>
            <div class="fl-meta">
              <span class="fl-act" style="color:{col}">{act}</span>
              {f'<span class="fl-sm">{sm}</span>' if sm else ''}
            </div>
          </div>
        </div>'''

    # ── Sections ──
    def _sec(ic: str, title: str, sub: str, body: str) -> str:
        return f'''
      <section class="sec">
        <div class="sec-hd">
          <span class="sec-icon">{ic}</span>
          <div>
            <h2 class="sec-tt">{title}</h2>
            <p class="sec-sub">{sub}</p>
          </div>
        </div>
        {body}
      </section>'''

    sec_stats = _sec(
        "\U0001F3C6", "Agent Leaderboard",
        f"{n_agt} agents \u00b7 {total_am} messages",
        bars,
    ) if agent_stats else ""

    sec_chat = _sec(
        "\U0001F4AC", "Conversation",
        f"{n_msg} messages \u2014 complete timeline",
        f'<div class="thread">{msgs}</div>',
    ) if msgs else ""

    sec_decs = _sec(
        "\U0001F9E0", "Design Decisions",
        f"{n_dec} decisions with reasoning",
        decs,
    ) if decs else ""

    sec_files = _sec(
        "\U0001F4C1", "File Changes",
        f"{n_fil} files touched",
        fls,
    ) if fls else ""

    display = "block" if idx == 0 else "none"

    return f'''
    <div class="proj-panel" id="proj-{idx}" style="display:{display}">
      <div class="proj-header">
        <h2 class="proj-name">{html.escape(project_name)}</h2>
        <p class="proj-path">{html.escape(project_path)}</p>
        <div class="proj-metrics">
          <div class="pm"><span class="pm-v">{n_msg}</span><span class="pm-l">Messages</span></div>
          <div class="pm-div"></div>
          <div class="pm"><span class="pm-v">{n_dec}</span><span class="pm-l">Decisions</span></div>
          <div class="pm-div"></div>
          <div class="pm"><span class="pm-v">{n_fil}</span><span class="pm-l">Files</span></div>
          <div class="pm-div"></div>
          <div class="pm"><span class="pm-v">{n_agt}</span><span class="pm-l">Agents</span></div>
        </div>
      </div>
      {sec_stats}
      {sec_chat}
      {sec_decs}
      {sec_files}
    </div>'''


def generate_share_html(
    projects: list[dict],
    preferences: dict[str, str],
) -> str:
    """Generate a self-contained HTML share page."""

    now = datetime.now().strftime("%b %d, %Y")
    total_projects = len(projects)
    grand_msgs = sum(len(p["messages"]) for p in projects)
    grand_decs = sum(len(p["decisions"]) for p in projects)
    grand_files = sum(len(p["file_changes"]) for p in projects)

    project_panels = ""
    for i, proj in enumerate(projects):
        project_panels += _build_project_html(proj, i)

    selector_buttons = ""
    for i, proj in enumerate(projects):
        n = html.escape(proj["name"])
        mc = len(proj["messages"])
        active = " active" if i == 0 else ""
        selector_buttons += f'''
        <button class="ps-btn{active}" data-idx="{i}" onclick="switchProject({i})">
          <span class="ps-name">{n}</span>
          <span class="ps-count">{mc}</span>
        </button>'''

    IC_GEAR = "\u2699\uFE0F"
    prefs_html = ""
    if preferences:
        prf = ""
        for cat, val in preferences.items():
            prf += f'''
              <div class="pf">
                <span class="pf-k">{html.escape(cat)}</span>
                <span class="pf-v">{html.escape(val)}</span>
              </div>'''
        prefs_html = f'''
    <section class="sec">
      <div class="sec-hd">
        <span class="sec-icon">{IC_GEAR}</span>
        <div>
          <h2 class="sec-tt">Global Preferences</h2>
          <p class="sec-sub">Shared across all agents</p>
        </div>
      </div>
      {prf}
    </section>'''

    CSS = r'''
@import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght,SOFT,WONK@0,9..144,200..900,0..100,0..1;1,9..144,200..900,0..100,0..1&family=Azeret+Mono:wght@300;400;500;600&display=swap');

/* Preflight — matches Tailwind v4 preflight from the home page exactly */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;border:0 solid}
html{
  line-height:1.5;
  -webkit-text-size-adjust:100%;
  -moz-tab-size:4;tab-size:4;
  font-feature-settings:normal;
  font-variation-settings:normal;
  -webkit-tap-highlight-color:transparent;
  scroll-behavior:smooth;
}
h1,h2,h3,h4,h5,h6{font-size:inherit;font-weight:inherit}
a{color:inherit;text-decoration:inherit}
code,pre{font-family:'Azeret Mono','Menlo',monospace}
button{font-family:inherit;font-size:100%;background:transparent;cursor:pointer}
img,svg{display:block;vertical-align:middle}
summary{display:list-item;cursor:pointer}

body{
  background:#0C0A08;color:#E8E0D0;
  font-family:'Azeret Mono','Menlo',monospace;
  font-size:13px;font-weight:400;line-height:1.7;
  -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;
  overflow-x:hidden;
}
::selection{background:rgba(196,101,74,0.2);color:#fff}

/* Film grain — identical to globals.css */
body::after{
  content:'';position:fixed;inset:0;
  background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E") repeat;
  pointer-events:none;z-index:9999;mix-blend-mode:overlay;opacity:0.032;
}
/* Ruled-paper lines — identical to globals.css */
body::before{
  content:'';position:fixed;inset:0;
  background-image:repeating-linear-gradient(0deg,transparent,transparent 55px,rgba(232,224,208,0.018) 55px,rgba(232,224,208,0.018) 56px);
  pointer-events:none;z-index:0;
}

@keyframes fadeUp{
  from{opacity:0;transform:translateY(24px)}
  to{opacity:1;transform:translateY(0)}
}
@keyframes barIn{to{width:var(--w)}}

/* ── Content components ── */

.proj-sel{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:48px}
.ps-btn{
  padding:8px 18px;background:#161210;border:1px solid rgba(232,224,208,0.07);
  border-radius:100px;cursor:pointer;display:inline-flex;align-items:center;gap:10px;
  transition:all 0.2s cubic-bezier(0.4,0,0.2,1);color:#6D655A;
  font-family:'Azeret Mono','Menlo',monospace;font-size:11px;font-weight:500;
}
.ps-btn:hover{background:#1E1A16;border-color:rgba(232,224,208,0.13);color:#A69E90;transform:translateY(-1px)}
.ps-btn.active{background:rgba(196,101,74,0.09);border-color:rgba(196,101,74,0.25);color:#E8E0D0}
.ps-count{font-size:9px;color:#6D655A;background:rgba(232,224,208,0.05);padding:2px 7px;border-radius:100px}

.proj-panel{width:100%;max-width:1100px}
.proj-header{margin-bottom:48px}
.proj-name{font-family:'Fraunces',Georgia,serif;font-weight:800;font-style:italic;font-size:clamp(2rem,5vw,3.5rem);letter-spacing:-0.04em;color:#E8E0D0;line-height:1;margin-bottom:8px}
.proj-path{font-size:12px;color:#6D655A;margin-bottom:24px}
.proj-metrics{display:inline-flex;align-items:center;background:#161210;border:1px solid rgba(232,224,208,0.07);border-radius:10px;overflow:hidden}
.pm{text-align:center;padding:14px 22px}
.pm-v{font-family:'Fraunces',Georgia,serif;font-size:1.4rem;font-weight:800;font-style:italic;letter-spacing:-0.04em;color:#E8E0D0;display:block;margin-bottom:2px}
.pm-l{font-size:9px;color:#6D655A;text-transform:uppercase;letter-spacing:0.2em;font-weight:500;display:block}
.pm-div{width:1px;background:rgba(232,224,208,0.07);align-self:stretch}

.sec{margin-bottom:48px;overflow:hidden}
.sec-hd{display:flex;align-items:center;gap:14px;margin-bottom:22px;padding-bottom:14px;border-bottom:1px solid rgba(232,224,208,0.07)}
.sec-icon{font-size:14px;flex-shrink:0}
.sec-tt{font-family:'Fraunces',Georgia,serif;font-size:1rem;font-weight:700;font-style:italic;letter-spacing:-0.02em;color:#E8E0D0}
.sec-sub{font-size:11px;color:#6D655A;margin-top:2px}

.bar{display:flex;flex-direction:column;gap:7px;margin-bottom:5px;padding:13px 16px;background:#161210;border:1px solid rgba(232,224,208,0.07);border-radius:10px;transition:border-color 0.2s}
.bar:hover{border-color:rgba(232,224,208,0.13)}
.bar-top{display:flex;align-items:center;gap:9px}
.bar-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.bar-name{font-size:12px;font-weight:500;color:#A69E90;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar-nums{display:flex;align-items:baseline;gap:6px;flex-shrink:0}
.bar-ct{font-size:13px;font-weight:600;color:#E8E0D0}
.bar-pct{font-size:10px;color:#6D655A}
.bar-track{height:2px;background:rgba(232,224,208,0.04);border-radius:1px;position:relative;overflow:hidden}
.bar-fill{position:absolute;top:0;left:0;bottom:0;border-radius:1px;width:0;animation:barIn 1.5s cubic-bezier(0.34,1.56,0.64,1) forwards;animation-delay:calc(var(--d,0s) + .3s)}

.thread{display:flex;flex-direction:column;gap:3px;width:100%;min-width:0}
.msg{display:flex;gap:12px;min-width:0}
.msg-rail{display:flex;flex-direction:column;align-items:center;width:28px;flex-shrink:0;padding-top:4px}
.msg-av{width:24px;height:24px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:600;color:#fff;flex-shrink:0}
.msg-line{flex:1;width:1px;margin:4px 0;background:rgba(232,224,208,0.04)}
.msg-card{flex:1;min-width:0;overflow:hidden;background:#161210;border:1px solid rgba(232,224,208,0.07);border-radius:10px;padding:14px 18px;transition:border-color 0.2s}
.msg-card:hover{border-color:rgba(232,224,208,0.13)}
.msg-a .msg-card{border-left:2px solid var(--ac,rgba(196,101,74,0.3))}
.msg-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:7px}
.msg-who{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.14em}
.msg-ts{font-size:10px;color:#6D655A}
.msg-txt{font-size:13px;color:#A69E90;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;line-height:1.7}
.msg-txt strong{color:#E8E0D0;font-weight:600}
.msg-txt .mdh{display:block;font-family:'Fraunces',Georgia,serif;font-weight:700;font-style:italic;color:#E8E0D0;margin:14px 0 6px;letter-spacing:-0.02em}
.msg-txt .mdh1{font-size:1.1rem}.msg-txt .mdh2{font-size:1rem}.msg-txt .mdh3{font-size:0.9rem;color:#A69E90}
.msg-txt .mdb{display:block;padding-left:16px;position:relative}
.msg-txt .mdb::before{content:'';position:absolute;left:5px;top:.75em;width:3px;height:3px;border-radius:50%;background:#6D655A}

.codeblk{background:#0C0A08;border:1px solid rgba(232,224,208,0.07);border-radius:8px;padding:14px 18px;font-size:11px;line-height:1.7;overflow-x:auto;margin:10px 0;color:#A69E90;position:relative}
.codeblk::before{content:attr(data-lang);position:absolute;top:6px;right:12px;font-size:9px;color:#6D655A;text-transform:uppercase;letter-spacing:0.12em;font-weight:600}
.ilc{background:rgba(196,101,74,0.09);border:1px solid rgba(196,101,74,0.25);border-radius:3px;padding:1px 5px;font-size:.82em;color:#C4654A}

.dec{background:#161210;border:1px solid rgba(232,224,208,0.07);border-radius:10px;margin-bottom:5px;overflow:hidden;transition:all 0.2s}
.dec:hover{border-color:rgba(232,224,208,0.13)}
.dec[open]{border-color:rgba(196,101,74,0.25);box-shadow:0 6px 24px rgba(0,0,0,0.25)}
.dec-sum{display:flex;align-items:flex-start;gap:12px;padding:14px 16px;cursor:pointer;list-style:none;user-select:none;transition:background 0.2s}
.dec-sum::-webkit-details-marker{display:none}
.dec-sum:hover{background:rgba(232,224,208,0.01)}
.dec-chev{color:#3A3530;flex-shrink:0;transition:transform .25s;margin-top:3px}
.dec[open] .dec-chev{transform:rotate(90deg);color:#C4654A}
.dec-q{flex:1;font-size:13px;font-weight:500;line-height:1.5;color:#E8E0D0}
.dec-tag{font-size:9px;text-transform:uppercase;letter-spacing:0.1em;padding:2px 7px;border-radius:100px;background:rgba(232,224,208,0.03);flex-shrink:0;font-weight:500}
.dec-body{padding:0 16px 16px 40px;border-top:1px solid rgba(232,224,208,0.04);padding-top:14px;display:flex;flex-direction:column;gap:12px}
.dec-lab{display:block;font-size:9px;color:#6D655A;text-transform:uppercase;letter-spacing:0.2em;font-weight:600;margin-bottom:4px}
.dec-ans{font-size:13px;color:#E8E0D0;line-height:1.7}
.dec-reason{font-size:13px;color:#A69E90;line-height:1.7;padding-left:12px;border-left:2px solid rgba(196,101,74,0.25)}
.dec-alts{font-size:13px;color:#A69E90}
.dec-alts ul{list-style:none;margin-top:6px;display:flex;flex-direction:column;gap:3px}
.dec-alts li{padding:7px 12px;background:#1E1A16;border-radius:6px;border:1px solid rgba(232,224,208,0.07);transition:background 0.2s}
.dec-alts li:hover{background:#272220}

.fl{display:flex;align-items:flex-start;gap:12px;padding:11px 14px;background:#161210;border:1px solid rgba(232,224,208,0.07);border-radius:10px;margin-bottom:3px;transition:all 0.2s}
.fl:hover{background:#1E1A16;border-color:rgba(232,224,208,0.13);transform:translateX(3px)}
.fl-pip{width:2px;min-height:32px;border-radius:1px;flex-shrink:0;align-self:stretch}
.fl-info{flex:1;min-width:0}
.fl-dir{font-size:11px;color:#6D655A}
.fl-base{font-size:12px;color:#E8E0D0;font-weight:500}
.fl-meta{display:flex;align-items:center;gap:8px;margin-top:3px}
.fl-act{font-size:9px;text-transform:uppercase;letter-spacing:0.1em;font-weight:600}
.fl-sm{font-size:11px;color:#6D655A;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

.pf{display:flex;align-items:flex-start;gap:16px;padding:11px 14px;background:#161210;border:1px solid rgba(232,224,208,0.07);border-radius:10px;margin-bottom:3px;transition:all 0.2s}
.pf:hover{background:#1E1A16;border-color:rgba(232,224,208,0.13)}
.pf-k{font-size:12px;font-weight:600;color:#E8E0D0;min-width:110px;flex-shrink:0}
.pf-v{font-size:12px;color:#A69E90;line-height:1.6}

::-webkit-scrollbar{width:3px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(232,224,208,0.08);border-radius:2px}
::-webkit-scrollbar-thumb:hover{background:rgba(232,224,208,0.14)}

@media(max-width:768px){
  .hero-grid{grid-template-columns:1fr!important;gap:32px!important}
  .proj-metrics{flex-wrap:wrap}.pm-div{display:none}
  .proj-sel{gap:5px}
  .msg-card{padding:12px 14px}
}
@media(max-width:480px){
  .fl{flex-direction:column;gap:6px}.fl-pip{width:100%;height:2px;min-height:0}
  .pf{flex-direction:column;gap:3px}.pf-k{min-width:0}
  .pm{padding:12px 16px}
}
'''

    # Inline styles copied VERBATIM from page.tsx
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>amcl \u2014 shared context</title>
<meta name="description" content="A/MCL \u2014 shared context for AI coding agents.">
<style>{CSS}</style>
</head>
<body>

<!-- Glow — copied from page.tsx -->
<div aria-hidden="true" style="position:fixed;top:-20%;left:-12%;width:70%;height:60%;background:radial-gradient(ellipse at center, rgba(196,101,74,0.07) 0%, transparent 55%);filter:blur(90px);pointer-events:none;mix-blend-mode:screen"></div>

<!-- main — copied from page.tsx -->
<main style="min-height:100vh;display:flex;flex-direction:column;position:relative">

  <!-- Nav — copied from page.tsx -->
  <nav style="width:100%;padding:36px clamp(32px, 5vw, 80px);display:flex;align-items:center;justify-content:space-between;position:relative;z-index:2;animation:fadeUp 0.5s cubic-bezier(0.4,0,0.2,1) both">
    <span style="font-family:'Fraunces', Georgia, serif;font-weight:700;font-size:20px;font-style:italic;color:#E8E0D0;letter-spacing:-0.04em">a:mcl</span>
    <a href="https://pypi.org/project/amcl-server/" target="_blank" rel="noreferrer" style="font-size:12px;font-weight:500;color:#3A3530;text-decoration:none;letter-spacing:0.06em">PyPI</a>
  </nav>

  <!-- Hero — copied from page.tsx -->
  <section style="flex:1;display:flex;flex-direction:column;justify-content:center;padding:clamp(40px, 8vh, 100px) clamp(32px, 5vw, 80px);position:relative;z-index:1">
    <h1 style="font-family:'Fraunces', Georgia, serif;font-weight:900;font-size:clamp(4.5rem, 12vw, 12rem);letter-spacing:-0.04em;line-height:0.88;margin-bottom:clamp(36px, 5vh, 64px);animation:fadeUp 0.8s cubic-bezier(0.4,0,0.2,1) 0.06s both;max-width:1200px">
      <span style="display:block;color:#E8E0D0">Shared</span>
      <span style="display:block;color:#C4654A;font-style:italic">context\u2014</span>
      <span style="display:block;color:rgba(232,224,208,0.12);font-style:italic">every agent.</span>
    </h1>

    <!-- Two-column grid — copied from page.tsx -->
    <div class="hero-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:clamp(32px, 4vw, 80px);max-width:1100px;align-items:start">
      <p style="font-size:15px;font-weight:400;color:#6D655A;line-height:1.85;max-width:480px;animation:fadeUp 0.7s cubic-bezier(0.4,0,0.2,1) 0.12s both">
        Every decision, conversation, and file change \u2014 exported {now}.
      </p>

      <!-- Metrics — styled like CmdRow from page.tsx -->
      <div style="display:flex;flex-direction:column;gap:2px">
        <div style="display:flex;align-items:center;gap:20px;padding:18px 24px;border-left:2px solid #3A3530;animation:fadeUp 0.7s cubic-bezier(0.4,0,0.2,1) 0.18s both">
          <div style="flex:1">
            <p style="font-size:9px;text-transform:uppercase;letter-spacing:0.24em;color:#3A3530;font-weight:500;margin-bottom:8px">Overview</p>
            <code style="font-size:15px;color:#E8E0D0;letter-spacing:-0.01em"><span style="color:#6D655A">{total_projects}</span> projects \u00b7 <span style="color:#6D655A">{grand_msgs}</span> messages</code>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:20px;padding:18px 24px;border-left:2px solid #3A3530;animation:fadeUp 0.7s cubic-bezier(0.4,0,0.2,1) 0.22s both">
          <div style="flex:1">
            <p style="font-size:9px;text-transform:uppercase;letter-spacing:0.24em;color:#3A3530;font-weight:500;margin-bottom:8px">Details</p>
            <code style="font-size:15px;color:#E8E0D0;letter-spacing:-0.01em"><span style="color:#6D655A">{grand_decs}</span> decisions \u00b7 <span style="color:#6D655A">{grand_files}</span> files</code>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Content sections -->
  <section style="padding:clamp(48px, 6vh, 80px) clamp(32px, 5vw, 80px);position:relative;z-index:1">
    <div class="proj-sel">
      {selector_buttons}
    </div>
    <div id="project-panels">
      {project_panels}
    </div>
    {prefs_html}
  </section>

  <!-- Footer — copied from page.tsx -->
  <footer style="padding:32px clamp(32px, 5vw, 80px) 48px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;border-top:1px solid rgba(232,224,208,0.04);position:relative;z-index:1">
    <span style="font-family:'Fraunces', Georgia, serif;font-size:16px;font-weight:600;font-style:italic;color:#252220;letter-spacing:-0.03em">a:mcl</span>
    <span style="font-size:11px;color:#252220;letter-spacing:0.06em">amcl-server \u00b7 jpdz.app</span>
  </footer>

</main>

<script>
function switchProject(idx) {{
  document.querySelectorAll('.proj-panel').forEach(function(el) {{
    el.style.display = 'none';
  }});
  document.querySelectorAll('.ps-btn').forEach(function(el) {{
    el.classList.remove('active');
  }});
  var panel = document.getElementById('proj-' + idx);
  if (panel) {{
    panel.style.display = 'block';
    panel.style.animation = 'none';
    panel.offsetHeight;
    panel.style.animation = 'fadeUp 0.4s cubic-bezier(0.4,0,0.2,1) both';
  }}
  var btns = document.querySelectorAll('.ps-btn');
  if (btns[idx]) btns[idx].classList.add('active');
}}
</script>

</body>
</html>'''
