"""Visual layer for the Streamlit app: theme CSS, the animated hero, and small HTML fragments."""
from html import escape

HAZARD_NAMES = {
    "fire_smoke": "Fire or smoke",
    "zone_entry": "Restricted-zone entry",
    "removed_object": "Object removed",
    "abandoned_object": "Object left behind",
}
PROFILE_NAMES = {"unmanned_tower": "Unmanned tower", "staffed_hub": "Staffed hub"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@500;600;700&display=swap');

:root {
  --ink: #0E1726; --panel: #15223A; --panel-2: #1A2945; --line: #263754;
  --text: #E6ECF5; --muted: #8A9AB5; --amber: #F2B33D; --red: #E5484D;
  --orange: #F08C3A; --teal: #3CCB9A; --grid: rgba(138,154,181,.16);
}
html, body, .stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp li {
  font-family: 'IBM Plex Sans', system-ui, sans-serif;
}
.stApp h1, .stApp h2, .stApp h3, .lv-display { font-family: 'IBM Plex Sans Condensed', 'IBM Plex Sans', sans-serif; letter-spacing: -.01em; }
.stApp { background: var(--ink); }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
.block-container { padding-top: 1.6rem; max-width: 1240px; }

/* ---------- hero: mast camera sweeping light over a 3D grid ---------- */
.lv-hero {
  position: relative; height: 290px; border: 1px solid var(--line); border-radius: 16px; overflow: hidden;
  background: radial-gradient(120% 150% at 82% 0%, #1D2F4E 0%, var(--ink) 62%);
  margin-bottom: 1.4rem;
}
.lv-stage { position: absolute; inset: 0; perspective: 640px; perspective-origin: 70% 20%; }
.lv-plane {
  position: absolute; left: -30%; right: -30%; bottom: -10%; height: 150%;
  transform-origin: 50% 100%; transform: rotateX(70deg);
  background-image: linear-gradient(var(--grid) 1px, transparent 1px), linear-gradient(90deg, var(--grid) 1px, transparent 1px);
  background-size: 46px 46px;
  -webkit-mask-image: linear-gradient(to top, #000 25%, transparent 80%); mask-image: linear-gradient(to top, #000 25%, transparent 80%);
  animation: lv-tilt 1.5s cubic-bezier(.2,.7,.2,1) both, lv-drift 22s linear 1.5s infinite;
}
.lv-mast {
  position: absolute; right: 18%; top: 26%; bottom: 0; width: 18px; transform: translateX(50%);
  background:
    linear-gradient(90deg, transparent 0 2px, #3A4E72 2px 4px, transparent 4px 14px, #3A4E72 14px 16px, transparent 16px),
    repeating-linear-gradient(135deg, transparent 0 13px, rgba(58,78,114,.8) 13px 14px),
    repeating-linear-gradient(45deg, transparent 0 13px, rgba(58,78,114,.8) 13px 14px);
  -webkit-mask-image: linear-gradient(to bottom, #000 60%, transparent); mask-image: linear-gradient(to bottom, #000 60%, transparent);
}
.lv-beacon {
  position: absolute; right: 18%; top: calc(26% - 10px); width: 7px; height: 7px; border-radius: 50%;
  transform: translateX(50%); background: var(--red); box-shadow: 0 0 12px 3px rgba(229,72,77,.55);
  animation: lv-blink 2.6s steps(1) infinite;
}
.lv-cam {
  position: absolute; right: calc(18% - 2px); top: calc(26% + 6px); width: 22px; height: 11px; border-radius: 3px;
  background: #C9D3E3; transform: translateX(50%) rotate(14deg);
}
.lv-beam {
  position: absolute; right: 18%; top: calc(26% + 12px); width: 900px; height: 520px;
  transform: translateX(50%) rotate(0deg); transform-origin: 50% 0;
  background: conic-gradient(from 160deg at 50% 0%, transparent 0deg, rgba(242,179,61,.05) 6deg, rgba(242,179,61,.30) 20deg, rgba(242,179,61,.05) 34deg, transparent 40deg);
  filter: blur(1.5px); mix-blend-mode: screen;
  animation: lv-sweep 2.8s cubic-bezier(.45,0,.2,1) .4s both, lv-idle 11s ease-in-out 3.2s infinite alternate;
}
.lv-copy { position: relative; z-index: 2; padding: 2.1rem 2.4rem; max-width: 640px; }
.lv-copy h1 { font-size: 3.1rem; line-height: 1; margin: 0 0 .7rem 0; padding: 0; color: var(--text); font-weight: 700; }
.lv-copy p { color: var(--muted); font-size: 1.05rem; line-height: 1.5; margin: 0 0 1.5rem 0; max-width: 34em; }
.lv-stats { display: flex; flex-wrap: wrap; gap: 0; }
.lv-stat { padding: 0 1.4rem; border-left: 1px solid var(--line); }
.lv-stat:first-child { padding-left: 0; border-left: 0; }
.lv-stat b { display: block; font-family: 'IBM Plex Sans Condensed', sans-serif; font-size: 1.55rem; font-weight: 600; color: var(--text); }
.lv-stat span { color: var(--muted); font-size: .85rem; }
.lv-stat.amber b { color: var(--amber); }

@keyframes lv-tilt { from { transform: rotateX(86deg) translateY(60px); opacity: 0; } to { transform: rotateX(70deg); opacity: 1; } }
@keyframes lv-drift { to { background-position: 0 46px; } }
@keyframes lv-sweep { 0% { transform: translateX(50%) rotate(-58deg); opacity: 0; } 25% { opacity: 1; } 100% { transform: translateX(50%) rotate(0deg); opacity: 1; } }
@keyframes lv-idle { from { transform: translateX(50%) rotate(0deg); } to { transform: translateX(50%) rotate(-22deg); } }
@keyframes lv-blink { 0%, 70% { opacity: 1; } 71%, 100% { opacity: .15; } }
@media (prefers-reduced-motion: reduce) {
  .lv-plane, .lv-beam, .lv-beacon { animation: none !important; }
}
@media (max-width: 760px) {
  .lv-hero { height: auto; } .lv-copy { padding: 1.5rem; } .lv-copy h1 { font-size: 2.3rem; }
  .lv-mast, .lv-cam, .lv-beacon, .lv-beam { right: 8%; opacity: .5; }
  .lv-stat { padding: .4rem 1rem .4rem 0; border-left: 0; }
}

/* ---------- tabs ---------- */
.stTabs [data-baseweb="tab-list"] { gap: .25rem; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] { padding: .55rem 1rem; color: var(--muted); font-weight: 500; }
.stTabs [aria-selected="true"] { color: var(--text); }
.stTabs [data-baseweb="tab-highlight"] { background: var(--amber); height: 2px; }
.stTabs [data-baseweb="tab-panel"] { padding-top: 1.3rem; }

/* ---------- inputs & buttons ---------- */
.stTextInput input { background: var(--panel); border: 1px solid var(--line); font-size: 1.05rem; padding: .8rem 1rem; }
.stTextInput input:focus { border-color: var(--amber); box-shadow: 0 0 0 3px rgba(242,179,61,.18); }
.stButton button { border-radius: 8px; font-weight: 500; transition: transform .12s ease, background .12s ease; }
.stButton button:active { transform: scale(.97); }
.stButton button:focus-visible { outline: 2px solid var(--amber); outline-offset: 2px; }

/* ---------- content fragments ---------- */
.lv-parse { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 1px; background: var(--line);
  border: 1px solid var(--line); border-radius: 10px; overflow: hidden; margin: .6rem 0 1.2rem; }
.lv-parse > div { background: var(--panel); padding: .7rem .9rem; }
.lv-parse small { color: var(--muted); display: block; font-size: .78rem; margin-bottom: .2rem; }
.lv-parse code { background: transparent; color: var(--amber); padding: 0; font-size: .95rem;
  font-family: 'IBM Plex Sans', sans-serif; font-weight: 500; }
@media (max-width: 760px) { .lv-parse { grid-template-columns: 1fr; } }

.lv-rank { display: flex; align-items: baseline; justify-content: space-between; margin: .2rem 0 .4rem; }
.lv-rank b { font-family: 'IBM Plex Sans Condensed', sans-serif; font-size: 1.15rem; }
.lv-rank span { color: var(--muted); font-size: .8rem; }
.lv-meta { display: grid; grid-template-columns: auto 1fr; gap: .15rem .8rem; margin: .5rem 0; font-size: .85rem; }
.lv-meta dt { color: var(--muted); } .lv-meta dd { margin: 0; color: var(--text); }
.lv-chips { display: flex; flex-wrap: wrap; gap: .35rem; margin: .4rem 0 .2rem; }
.lv-chip { font-size: .78rem; padding: .18rem .55rem; border-radius: 999px; background: rgba(242,179,61,.12);
  color: var(--amber); border: 1px solid rgba(242,179,61,.35); }
.lv-chip.quiet { background: transparent; color: var(--muted); border-color: var(--line); }
.lv-judge { border-left: 3px solid var(--amber); background: rgba(242,179,61,.07); padding: .6rem .8rem;
  border-radius: 0 8px 8px 0; font-size: .88rem; margin: .5rem 0; }
.lv-judge b { color: var(--amber); }

.lv-sev { display: inline-flex; align-items: center; gap: .5rem; font-family: 'IBM Plex Sans Condensed', sans-serif;
  font-size: 1.35rem; font-weight: 600; margin-bottom: .3rem; }
.lv-sev::before { content: ""; width: 4px; height: 1.3rem; border-radius: 2px; background: currentColor; }
.lv-sev.critical { color: var(--red); } .lv-sev.high { color: var(--orange); }
.lv-sev.medium { color: var(--amber); } .lv-sev.low { color: var(--muted); }
.lv-sev.confirmed { color: var(--teal); }

.lv-kpis { display: flex; flex-wrap: wrap; border: 1px solid var(--line); border-radius: 12px; background: var(--panel);
  margin-bottom: 1.4rem; overflow: hidden; }
.lv-kpi { flex: 1 1 180px; padding: 1rem 1.2rem; border-left: 1px solid var(--line); }
.lv-kpi:first-child { border-left: 0; }
.lv-kpi b { display: block; font-family: 'IBM Plex Sans Condensed', sans-serif; font-size: 2rem; font-weight: 600; }
.lv-kpi span { color: var(--muted); font-size: .85rem; }
.lv-kpi.amber b { color: var(--amber); }
.lv-note { color: var(--muted); font-size: .88rem; max-width: 70ch; }
[data-testid="stVerticalBlockBorderWrapper"] { border-color: var(--line) !important; border-radius: 12px; background: rgba(21,34,58,.55); }
[data-testid="stImage"] img { border-radius: 10px; }
</style>
"""


def hero(clips, pending, frame_pct):
    return f"""
<div class="lv-hero">
  <div class="lv-stage" aria-hidden="true">
    <div class="lv-plane"></div><div class="lv-beam"></div><div class="lv-mast"></div>
    <div class="lv-cam"></div><div class="lv-beacon"></div>
  </div>
  <div class="lv-copy">
    <h1 class="lv-display">Lumen Vision</h1>
    <p>Ask your tower-site footage a question and get the clips back. Every alert waits for a person to confirm it before anyone is notified.</p>
    <div class="lv-stats">
      <div class="lv-stat"><b>{clips}</b><span>clips indexed</span></div>
      <div class="lv-stat"><b>{pending}</b><span>alerts awaiting review</span></div>
      <div class="lv-stat amber"><b>{frame_pct}%</b><span>of frames needed the VLM</span></div>
    </div>
  </div>
</div>"""


def parse_box(filters, residue, hazards):
    def fmt_filters(f):
        if not f:
            return "none"
        parts = []
        for k, v in f.items():
            if k == "hours":
                parts.append({"night": "night (19:00–06:00)", "day": "day (06:00–19:00)",
                              "after": f"after {v[1]:02d}:00", "before": f"before {v[2]:02d}:00"}[v[0]])
            elif k == "profile":
                parts.append(PROFILE_NAMES.get(v, v))
            else:
                parts.append(f"{k} {v}")
        return ", ".join(parts)
    hz = ", ".join(HAZARD_NAMES[h] for h in hazards) or "none"
    return (f'<div class="lv-parse"><div><small>Exact filters</small><code>{escape(fmt_filters(filters))}</code></div>'
            f'<div><small>Matched by meaning</small><code>{escape(residue)}</code></div>'
            f'<div><small>Hazard boost</small><code>{escape(hz)}</code></div></div>')


def meta(camera, site, recorded):
    return (f'<dl class="lv-meta"><dt>Camera</dt><dd>{escape(camera)}</dd><dt>Site</dt><dd>{escape(site)}</dd>'
            f'<dt>Recorded</dt><dd>{escape(recorded)}</dd></dl>')


def chips(hazards, tags=None):
    out = [f'<span class="lv-chip">{escape(HAZARD_NAMES.get(h["type"], h["type"]))} {h["final_conf"]:.2f}</span>'
           for h in hazards]
    if not out and tags:
        out = [f'<span class="lv-chip quiet">{escape(t.strip())}</span>' for t in tags.split(",")[:5] if t.strip()]
    return f'<div class="lv-chips">{"".join(out)}</div>' if out else ""


def judgement(claim, rationale):
    why = f'<br><span style="color:var(--muted)">{escape(rationale)}</span>' if rationale else ""
    return f'<div class="lv-judge"><b>Needs human judgement:</b> {escape(claim)}{why}</div>'


def severity(sev):
    return f'<div class="lv-sev {escape(sev)}">{escape(sev.capitalize())}</div>'


def kpis(items):
    cells = "".join(f'<div class="lv-kpi{" amber" if hi else ""}"><b>{escape(str(v))}</b><span>{escape(label)}</span></div>'
                    for v, label, hi in items)
    return f'<div class="lv-kpis">{cells}</div>'
