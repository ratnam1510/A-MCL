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
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}

:root{
  --bg:#0C0A08;
  --s1:#161210;
  --s2:#1E1A16;
  --s3:#272220;
  --bdr:rgba(232,224,208,0.07);
  --bdr-h:rgba(232,224,208,0.13);
  --tx:#E8E0D0;
  --tx2:#A69E90;
  --tx3:#6D655A;
  --tx4:#3A3530;
  --tx5:#252220;
  --accent:#C4654A;
  --accent-dim:rgba(196,101,74,0.09);
  --accent-bdr:rgba(196,101,74,0.25);
  --ease:cubic-bezier(0.4,0,0.2,1);
  --spring:cubic-bezier(0.34,1.56,0.64,1);
  --display:'Fraunces','Georgia',serif;
  --body:'Azeret Mono','Menlo','Consolas',monospace;
}

html{scroll-behavior:smooth}

body{
  background:var(--bg);color:var(--tx);
  font-family:var(--body);font-size:13px;font-weight:400;line-height:1.7;
  -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;
  overflow-x:hidden;
}

::selection{background:rgba(196,101,74,0.2);color:#fff}

/* Film grain */
body::after{
  content:'';position:fixed;inset:0;
  background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E") repeat;
  pointer-events:none;z-index:9999;mix-blend-mode:overlay;opacity:0.032;
}

/* Ruled-paper lines */
body::before{
  content:'';position:fixed;inset:0;
  background-image:repeating-linear-gradient(0deg,transparent,transparent 55px,rgba(232,224,208,0.018) 55px,rgba(232,224,208,0.018) 56px);
  pointer-events:none;z-index:0;
}

/* Corner glow */
.glow{
  position:fixed;top:-15%;left:-10%;width:65%;height:55%;
  background:radial-gradient(ellipse at center,rgba(196,101,74,0.06) 0%,transparent 60%);
  filter:blur(80px);pointer-events:none;mix-blend-mode:screen;z-index:0;
}

@keyframes fadeUp{
  from{opacity:0;transform:translateY(20px)}
  to{opacity:1;transform:translateY(0)}
}
@keyframes shimmer{
  0%{background-position:-200% center}
  100%{background-position:200% center}
}
@keyframes barIn{to{width:var(--w)}}
@keyframes enter{
  from{opacity:0;transform:translateY(16px)}
  to{opacity:1;transform:translateY(0)}
}

/* ── Layout ── */
.wrap{
  max-width:720px;width:100%;margin:0 auto;
  padding:80px 48px 96px;position:relative;z-index:1;
}

/* ── Nav ── */
.nav{
  display:flex;align-items:center;justify-content:space-between;
  margin-bottom:72px;animation:enter .5s var(--ease) both;
}
.nav-brand{
  font-family:var(--display);font-weight:700;font-size:18px;
  font-style:italic;color:var(--tx);letter-spacing:-0.04em;
}
.nav-meta{font-size:11px;color:var(--tx5);letter-spacing:0.05em}

/* ── Hero ── */
.hero{margin-bottom:56px;animation:enter .65s var(--ease) .04s both}
.hero-badge{
  display:inline-flex;align-items:center;gap:8px;margin-bottom:36px;
}
.hero-badge-dot{
  width:6px;height:6px;border-radius:50%;background:var(--accent);
  box-shadow:0 0 10px rgba(196,101,74,0.6);
}
.hero-badge span{font-size:10px;color:var(--tx3);font-weight:500;letter-spacing:0.1em;text-transform:uppercase}
.hero h1{
  font-family:var(--display);font-weight:900;
  font-size:clamp(3rem,7.5vw,6rem);
  letter-spacing:-0.04em;line-height:0.9;margin-bottom:24px;
}
.hero-l1{display:block;color:var(--tx)}
.hero-l2{display:block;color:var(--accent);font-style:italic}
.hero-l3{display:block;color:rgba(232,224,208,0.14);font-style:italic}
.hero p{font-size:14px;color:var(--tx3);line-height:1.8;max-width:440px}

/* ── Grand metrics ── */
.grand{
  display:inline-flex;align-items:center;
  background:var(--s1);border:1px solid var(--bdr);
  border-radius:12px;overflow:hidden;
  margin-top:36px;margin-bottom:52px;
  animation:enter .65s var(--ease) .1s both;
}
.gm{text-align:center;padding:18px 28px}
.gm-v{
  font-family:var(--display);font-size:1.8rem;font-weight:800;
  font-style:italic;letter-spacing:-0.04em;
  background:linear-gradient(135deg,var(--accent),#D4AA44);
  background-size:200% auto;
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  line-height:1;margin-bottom:4px;animation:shimmer 5s linear infinite;
}
.gm-l{font-size:9px;color:var(--tx5);text-transform:uppercase;letter-spacing:0.2em;font-weight:500}
.gm-div{width:1px;background:var(--bdr);align-self:stretch}

/* ── Project selector ── */
.proj-sel{
  display:flex;gap:6px;flex-wrap:wrap;
  margin-bottom:48px;animation:enter .65s var(--ease) .15s both;
}
.ps-btn{
  padding:7px 16px;background:var(--s1);border:1px solid var(--bdr);
  border-radius:100px;cursor:pointer;display:inline-flex;align-items:center;gap:8px;
  transition:all 0.2s var(--ease);color:var(--tx4);
  font-family:var(--body);font-size:11px;font-weight:500;
}
.ps-btn:hover{background:var(--s2);border-color:var(--bdr-h);color:var(--tx2);transform:translateY(-1px)}
.ps-btn.active{background:var(--accent-dim);border-color:var(--accent-bdr);color:var(--tx)}
.ps-count{font-size:9px;color:var(--tx5);background:rgba(232,224,208,0.03);padding:2px 6px;border-radius:100px}

/* ── Project panel ── */
.proj-panel{animation:enter .45s var(--ease) both;width:100%}
.proj-header{margin-bottom:48px}
.proj-name{
  font-family:var(--display);font-weight:800;font-style:italic;
  font-size:clamp(1.8rem,4vw,2.8rem);letter-spacing:-0.04em;
  color:var(--tx);line-height:1;margin-bottom:8px;
}
.proj-path{font-size:11px;color:var(--tx5);margin-bottom:24px}
.proj-metrics{
  display:inline-flex;align-items:center;
  background:var(--s1);border:1px solid var(--bdr);
  border-radius:10px;overflow:hidden;
}
.pm{text-align:center;padding:14px 22px}
.pm-v{
  font-family:var(--display);font-size:1.4rem;font-weight:800;
  font-style:italic;letter-spacing:-0.04em;color:var(--tx);
  display:block;margin-bottom:2px;
}
.pm-l{font-size:8px;color:var(--tx5);text-transform:uppercase;letter-spacing:0.2em;font-weight:500;display:block}
.pm-div{width:1px;background:var(--bdr);align-self:stretch}

/* ── Section ── */
.sec{margin-bottom:48px;animation:enter .5s var(--ease) both;overflow:hidden}
.sec-hd{
  display:flex;align-items:center;gap:14px;
  margin-bottom:22px;padding-bottom:14px;
  border-bottom:1px solid var(--bdr);
}
.sec-icon{font-size:14px;flex-shrink:0}
.sec-tt{font-family:var(--display);font-size:1rem;font-weight:700;font-style:italic;letter-spacing:-0.02em;color:var(--tx)}
.sec-sub{font-size:10px;color:var(--tx5);margin-top:2px}

/* ── Agent bars ── */
.bar{
  display:flex;flex-direction:column;gap:7px;
  margin-bottom:5px;padding:13px 16px;
  background:var(--s1);border:1px solid var(--bdr);border-radius:10px;
  animation:enter .4s var(--ease) both;animation-delay:var(--d);
  transition:border-color 0.2s var(--ease);
}
.bar:hover{border-color:var(--bdr-h)}
.bar-top{display:flex;align-items:center;gap:9px}
.bar-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.bar-name{font-size:11px;font-weight:500;color:var(--tx2);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar-nums{display:flex;align-items:baseline;gap:6px;flex-shrink:0}
.bar-ct{font-size:12px;font-weight:600;color:var(--tx)}
.bar-pct{font-size:9px;color:var(--tx5)}
.bar-track{height:2px;background:rgba(232,224,208,0.04);border-radius:1px;position:relative;overflow:hidden}
.bar-fill{
  position:absolute;top:0;left:0;bottom:0;border-radius:1px;
  width:0;animation:barIn 1.5s var(--spring) forwards;
  animation-delay:calc(var(--d) + .3s);
}

/* ── Messages ── */
.thread{display:flex;flex-direction:column;gap:3px;width:100%;min-width:0}
.msg{display:flex;gap:12px;animation:enter .3s var(--ease) both;animation-delay:var(--d);min-width:0}
.msg-rail{display:flex;flex-direction:column;align-items:center;width:28px;flex-shrink:0;padding-top:4px}
.msg-av{
  width:24px;height:24px;border-radius:6px;
  display:flex;align-items:center;justify-content:center;
  font-size:9px;font-weight:600;color:#fff;flex-shrink:0;
}
.msg-line{flex:1;width:1px;margin:4px 0;background:rgba(232,224,208,0.04)}
.msg-card{
  flex:1;min-width:0;overflow:hidden;
  background:var(--s1);border:1px solid var(--bdr);
  border-radius:10px;padding:14px 18px;
  transition:border-color 0.2s var(--ease);
}
.msg-card:hover{border-color:var(--bdr-h)}
.msg-a .msg-card{border-left:2px solid var(--ac,rgba(196,101,74,0.3))}
.msg-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:7px}
.msg-who{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:0.14em}
.msg-ts{font-size:9px;color:var(--tx5)}
.msg-txt{
  font-size:12px;color:var(--tx3);white-space:pre-wrap;
  overflow-wrap:anywhere;word-break:break-word;line-height:1.7;
}
.msg-txt strong{color:var(--tx);font-weight:600}
.msg-txt .mdh{display:block;font-family:var(--display);font-weight:700;font-style:italic;color:var(--tx);margin:14px 0 6px;letter-spacing:-0.02em}
.msg-txt .mdh1{font-size:1.1rem}
.msg-txt .mdh2{font-size:1rem}
.msg-txt .mdh3{font-size:0.9rem;color:var(--tx2)}
.msg-txt .mdb{display:block;padding-left:16px;position:relative}
.msg-txt .mdb::before{content:'';position:absolute;left:5px;top:.75em;width:3px;height:3px;border-radius:50%;background:var(--tx5)}

/* ── Code ── */
.codeblk{
  background:var(--bg);border:1px solid var(--bdr);border-radius:8px;
  padding:14px 18px;font-size:11px;line-height:1.7;overflow-x:auto;margin:10px 0;
  color:var(--tx2);position:relative;
}
.codeblk::before{content:attr(data-lang);position:absolute;top:6px;right:12px;font-size:8px;color:var(--tx5);text-transform:uppercase;letter-spacing:0.12em;font-weight:600}
.ilc{background:var(--accent-dim);border:1px solid var(--accent-bdr);border-radius:3px;padding:1px 5px;font-size:.82em;color:var(--accent)}

/* ── Decisions ── */
.dec{
  background:var(--s1);border:1px solid var(--bdr);border-radius:10px;
  margin-bottom:5px;overflow:hidden;
  animation:enter .4s var(--ease) both;animation-delay:var(--d);
  transition:all 0.2s var(--ease);
}
.dec:hover{border-color:var(--bdr-h)}
.dec[open]{border-color:var(--accent-bdr);box-shadow:0 6px 24px rgba(0,0,0,0.25)}
.dec-sum{
  display:flex;align-items:flex-start;gap:12px;padding:14px 16px;
  cursor:pointer;list-style:none;user-select:none;transition:background 0.2s;
}
.dec-sum::-webkit-details-marker{display:none}
.dec-sum:hover{background:rgba(232,224,208,0.01)}
.dec-chev{color:var(--tx5);flex-shrink:0;transition:transform .25s var(--ease);margin-top:3px}
.dec[open] .dec-chev{transform:rotate(90deg);color:var(--accent)}
.dec-q{flex:1;font-size:12px;font-weight:500;line-height:1.5;color:var(--tx)}
.dec-tag{font-size:9px;text-transform:uppercase;letter-spacing:0.1em;padding:2px 7px;border-radius:100px;background:rgba(232,224,208,0.03);flex-shrink:0;font-weight:500}
.dec-body{padding:0 16px 16px 40px;border-top:1px solid rgba(232,224,208,0.04);padding-top:14px;display:flex;flex-direction:column;gap:12px}
.dec-lab{display:block;font-size:8px;color:var(--tx5);text-transform:uppercase;letter-spacing:0.2em;font-weight:600;margin-bottom:4px}
.dec-ans{font-size:12px;color:var(--tx);line-height:1.7}
.dec-reason{font-size:11px;color:var(--tx3);line-height:1.7;padding-left:12px;border-left:2px solid var(--accent-bdr)}
.dec-alts{font-size:11px;color:var(--tx3)}
.dec-alts ul{list-style:none;margin-top:6px;display:flex;flex-direction:column;gap:3px}
.dec-alts li{padding:7px 12px;background:var(--s2);border-radius:6px;border:1px solid var(--bdr);transition:background 0.2s}
.dec-alts li:hover{background:var(--s3)}

/* ── Files ── */
.fl{
  display:flex;align-items:flex-start;gap:12px;padding:11px 14px;
  background:var(--s1);border:1px solid var(--bdr);border-radius:10px;
  margin-bottom:3px;animation:enter .3s var(--ease) both;animation-delay:var(--d);
  transition:all 0.2s var(--ease);
}
.fl:hover{background:var(--s2);border-color:var(--bdr-h);transform:translateX(3px)}
.fl-pip{width:2px;min-height:32px;border-radius:1px;flex-shrink:0;align-self:stretch}
.fl-info{flex:1;min-width:0}
.fl-dir{font-size:10px;color:var(--tx5)}
.fl-base{font-size:11px;color:var(--tx);font-weight:500}
.fl-meta{display:flex;align-items:center;gap:8px;margin-top:3px}
.fl-act{font-size:8px;text-transform:uppercase;letter-spacing:0.1em;font-weight:600}
.fl-sm{font-size:10px;color:var(--tx5);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* ── Preferences ── */
.pf{
  display:flex;align-items:flex-start;gap:16px;padding:11px 14px;
  background:var(--s1);border:1px solid var(--bdr);border-radius:10px;
  margin-bottom:3px;transition:all 0.2s var(--ease);
}
.pf:hover{background:var(--s2);border-color:var(--bdr-h)}
.pf-k{font-size:11px;font-weight:600;color:var(--tx);min-width:110px;flex-shrink:0}
.pf-v{font-size:11px;color:var(--tx3);line-height:1.6}

/* ── Footer ── */
.foot{
  margin-top:56px;padding-top:28px;
  border-top:1px solid var(--bdr);
  display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;
}
.foot-brand{font-family:var(--display);font-size:14px;font-weight:600;font-style:italic;color:var(--tx5);letter-spacing:-0.03em}
.foot-links{display:flex;align-items:center;gap:18px}
.foot-links a{font-size:10px;color:var(--tx4);text-decoration:none;transition:color 0.2s var(--ease);letter-spacing:0.05em}
.foot-links a:hover{color:var(--tx2)}

::-webkit-scrollbar{width:3px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(232,224,208,0.08);border-radius:2px}
::-webkit-scrollbar-thumb:hover{background:rgba(232,224,208,0.14)}

@media(max-width:768px){
  .wrap{padding:56px 24px 72px}
  .hero h1{font-size:clamp(2.6rem,8vw,3.8rem)}
  .grand{flex-wrap:wrap}.gm-div{display:none}
  .proj-metrics{flex-wrap:wrap}.pm-div{display:none}
  .proj-sel{gap:5px}
  .msg-card{padding:12px 14px}
}
@media(max-width:480px){
  .wrap{padding:44px 18px 56px}
  .fl{flex-direction:column;gap:6px}.fl-pip{width:100%;height:2px;min-height:0}
  .pf{flex-direction:column;gap:3px}.pf-k{min-width:0}
  .nav-meta{display:none}.pm{padding:12px 16px}
}
'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>amcl \u2014 shared context</title>
<meta name="description" content="A/MCL \u2014 shared context for AI coding agents.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght,SOFT,WONK@0,9..144,200..900,0..100,0..1;1,9..144,200..900,0..100,0..1&family=Azeret+Mono:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>

<div class="glow" aria-hidden="true"></div>

<div class="wrap">

  <div class="nav">
    <span class="nav-brand">a:mcl</span>
    <span class="nav-meta">{now}</span>
  </div>

  <div class="hero">
    <div class="hero-badge">
      <span class="hero-badge-dot"></span>
      <span>A/MCL Secure Share</span>
    </div>
    <h1>
      <span class="hero-l1">Shared</span>
      <span class="hero-l2">context\u2014</span>
      <span class="hero-l3">every agent.</span>
    </h1>
    <p>Every decision, conversation, and file change \u2014 exported and shared.</p>
  </div>

  <div class="grand">
    <div class="gm"><div class="gm-v">{total_projects}</div><div class="gm-l">Projects</div></div>
    <div class="gm-div"></div>
    <div class="gm"><div class="gm-v">{grand_msgs}</div><div class="gm-l">Messages</div></div>
    <div class="gm-div"></div>
    <div class="gm"><div class="gm-v">{grand_decs}</div><div class="gm-l">Decisions</div></div>
    <div class="gm-div"></div>
    <div class="gm"><div class="gm-v">{grand_files}</div><div class="gm-l">Files</div></div>
  </div>

  <div class="proj-sel">
    {selector_buttons}
  </div>

  <div id="project-panels">
    {project_panels}
  </div>

  {prefs_html}

  <footer class="foot">
    <span class="foot-brand">a:mcl</span>
    <div class="foot-links">
      <a href="https://pypi.org/project/amcl-server/" target="_blank" rel="noopener">amcl-server</a>
      <a href="https://github.com/ratnam1510/A-MCL" target="_blank" rel="noopener">GitHub</a>
    </div>
  </footer>

</div>

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
    panel.style.animation = 'enter 0.4s cubic-bezier(0.4,0,0.2,1) both';
  }}
  var btns = document.querySelectorAll('.ps-btn');
  if (btns[idx]) btns[idx].classList.add('active');
}}
</script>

</body>
</html>'''
