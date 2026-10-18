"""
ui_theme.py - Ground-control look for the dashboard.

Dark charcoal screen, lime panel headers, icon toolbar, satellite map,
waypoint table and instrument panel (horizon + dials).
Icons are our own simple line drawings.
"""
import base64
import math

# ---------------------------------------------------------------- colours
BG       = "#16181b"
PANEL    = "#23262a"
PANEL_HI = "#2c3035"
LINE     = "#3a3f45"
TEXT     = "#e6e8ea"
MUTED    = "#9aa3ad"
LIME     = "#9ac329"
LIME_HI  = "#b4e04a"
GOOD     = "#8bd44a"
WARN     = "#f5b83d"
BAD      = "#ff6b5e"
INFO     = "#5aa9ff"

# ---------------------------------------------------------------- tab icons
_ICON_PATHS = [
    # 1 flight plan: globe with pin
    "<circle cx='12' cy='12' r='9'/><path d='M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18'/>",
    # 2 flight data: dial with needle
    "<path d='M4 17a8 8 0 1 1 16 0'/><path d='M12 17l4-6'/><circle cx='12' cy='17' r='1.2'/><path d='M4 20h16'/>",
    # 3 weather: cloud
    "<path d='M7 18h10a4 4 0 0 0 .5-7.97A6 6 0 0 0 6 11a3.5 3.5 0 0 0 1 7z'/>",
    # 4 no-fly zone: circle with bar
    "<circle cx='12' cy='12' r='9'/><path d='M5.6 5.6l12.8 12.8'/>",
    # 5 AI analysis: chip
    "<rect x='7' y='7' width='10' height='10' rx='1'/><path d='M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4'/>",
    # 6 simulation: monitor with play
    "<rect x='3' y='4' width='18' height='12' rx='1'/><path d='M10 8l5 2-5 2z'/><path d='M8 20h8M12 16v4'/>",
    # 7 deep learning: network
    "<circle cx='5' cy='6' r='2'/><circle cx='5' cy='18' r='2'/><circle cx='12' cy='12' r='2'/><circle cx='19' cy='8' r='2'/><circle cx='19' cy='16' r='2'/><path d='M7 6l3.5 5M7 18l3.5-5M14 11l3.5-2M14 13l3.5 2'/>",
    # 8 report: page with lines
    "<path d='M7 3h8l4 4v14H7z'/><path d='M15 3v4h4M10 12h6M10 15h6M10 18h4'/>",
    # 9 terrain: mountains
    "<path d='M3 19l6-10 4 6 3-4 5 8z'/>",
    # 10 swarm: three drones
    "<circle cx='12' cy='6' r='2'/><circle cx='6' cy='17' r='2'/><circle cx='18' cy='17' r='2'/><path d='M12 8v3M8 15.5l3-4M16 15.5l-3-4'/>",
]


def _icon_uri(path_xml, colour):
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
           f"stroke='{colour}' stroke-width='1.6' stroke-linecap='round' "
           f"stroke-linejoin='round'>{path_xml}</svg>")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def _icon_css():
    rules = []
    for i, p in enumerate(_ICON_PATHS, 1):
        rules.append(
            f'.stTabs [role="tablist"] > [role="tab"]:nth-child({i})::before'
            f'{{background-image:url("{_icon_uri(p, "#c9d1d6")}");}}')
        rules.append(
            f'.stTabs [role="tablist"] > [role="tab"][aria-selected="true"]:nth-child({i})::before'
            f'{{background-image:url("{_icon_uri(p, LIME_HI)}");}}')
    return "\n".join(rules)


# ---------------------------------------------------------------- CSS
_BASE_CSS = f"""
html, body, [class*="css"] {{ font-family:"Segoe UI", Arial, sans-serif; }}
.stApp {{ background:{BG}; color:{TEXT}; }}
#MainMenu, footer, header {{ visibility:hidden; }}
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], [data-testid="collapsedControl"],
[data-testid="stSidebar"] {{ display:none !important; }}
.stApp > header {{ background:transparent !important; height:0 !important; }}
.block-container {{ padding:0.5rem 1.1rem 1.2rem 1.1rem !important; max-width:100% !important; }}

/* ---------- top bar ---------- */
.topbar {{ background:#0e1012; border-bottom:2px solid {LIME}; padding:8px 14px;
  display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; }}
.topbar-left {{ display:flex; align-items:center; gap:10px; }}
.topbar-title {{ font-size:15px; font-weight:700; color:{TEXT} !important; letter-spacing:1.2px; }}
.topbar-title span {{ color:{LIME_HI} !important; }}
.topbar-right {{ display:flex; align-items:center; gap:14px; }}
.pill {{ border-radius:3px; padding:3px 10px; font-size:11px; font-weight:700; letter-spacing:.6px;
  font-family:Consolas,monospace; border:1px solid; }}
.pill-sim  {{ color:{WARN}; border-color:{WARN}; background:#2e2610; }}
.pill-msn  {{ color:{LIME_HI}; border-color:{LIME}; background:#1d2610; }}
.pill-none {{ color:{MUTED}; border-color:{LINE}; background:{PANEL}; }}
#live-clock {{ color:{LIME_HI} !important; }}
#live-date  {{ color:{MUTED} !important; }}

/* ---------- toolbar-style tabs (role selectors work on old and new Streamlit) ---------- */
.stTabs [role="tablist"] {{ background:#0e1012; gap:0; border-bottom:2px solid {LIME};
  padding:0; flex-wrap:wrap; }}
.stTabs [data-baseweb="tab-border"] {{ background:transparent !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background:{LIME} !important; height:3px; }}
.stTabs [role="tablist"] > [role="tab"] {{
  background:transparent; border:none; border-right:1px solid #1d2024; border-bottom:3px solid transparent;
  border-radius:0; height:auto; min-width:84px; padding:8px 12px 6px 12px; margin:0;
  display:flex; flex-direction:column; align-items:center; gap:3px; cursor:pointer; }}
.stTabs [role="tablist"] > [role="tab"]::before {{
  content:""; display:block; width:30px; height:30px; background-size:contain;
  background-repeat:no-repeat; background-position:center; }}
.stTabs [role="tablist"] > [role="tab"] p {{
  color:#c9d1d6 !important; font-size:10.5px; font-weight:700; letter-spacing:.5px;
  text-transform:uppercase; margin:0; white-space:nowrap; }}
.stTabs [role="tablist"] > [role="tab"]:hover {{ background:#1a1d21; }}
.stTabs [role="tablist"] > [role="tab"][aria-selected="true"] {{ background:{PANEL_HI}; border-bottom-color:{LIME}; }}
.stTabs [role="tablist"] > [role="tab"][aria-selected="true"] p {{ color:{LIME_HI} !important; }}
.stTabs [role="tabpanel"] {{ padding-top:10px; }}

/* ---------- panels ---------- */
div[data-testid="stVerticalBlockBorderWrapper"] {{ background:{PANEL}; border:1px solid {LINE} !important;
  border-radius:3px; }}
.mp-hdr {{ background:{LIME}; color:#16200a !important; font-weight:700; font-size:12px; letter-spacing:.8px;
  text-transform:uppercase; padding:4px 10px; border-radius:2px; margin:0 0 8px 0; }}
.mp-hdr * {{ color:#16200a !important; }}
.gcard-hdr, .action-hdr, .wp-header {{ background:{LIME}; color:#16200a !important; font-weight:700;
  font-size:12px; letter-spacing:.8px; text-transform:uppercase; padding:4px 10px; border-radius:2px;
  margin:12px 0 8px 0; }}
.gcard {{ background:{PANEL}; border:1px solid {LINE}; border-radius:3px; padding:10px 12px;
  margin-bottom:8px; color:{TEXT}; font-size:13px; line-height:1.6; }}
.gcard span {{ filter:brightness(1.45); }}
.metric {{ background:{PANEL}; border:1px solid {LINE}; border-top:2px solid {LIME}; border-radius:3px;
  padding:8px; text-align:center; }}
.metric-val {{ font-size:18px; font-weight:700; font-family:Consolas,monospace; filter:brightness(1.5) saturate(1.1); }}
.metric-lbl {{ font-size:10px; color:{MUTED}; text-transform:uppercase; letter-spacing:.6px; }}
.geo-line {{ font-family:Consolas,monospace; font-size:12px; color:{INFO}; background:#101a26;
  border:1px solid #23405f; padding:5px 8px; border-radius:3px; margin-bottom:6px; }}
.sitrep {{ background:#101214; border:1px solid {LINE}; border-radius:3px; padding:10px;
  font-family:Consolas,monospace; font-size:12px; color:#b9e3a0; line-height:1.7; white-space:pre-wrap; }}

.status-banner {{ border-radius:3px; padding:9px 16px; font-size:14px; font-weight:700; text-align:center;
  letter-spacing:1.2px; border:1px solid; }}
.status-safe {{ background:#14291a; border-color:#4fbf5f; color:#9be8a4; }}
.status-mod  {{ background:#2d2610; border-color:{WARN}; color:#ffd98a; }}
.status-high {{ background:#33200f; border-color:#e8883a; color:#ffc08a; }}
.status-crit {{ background:#331515; border-color:{BAD}; color:#ffb3ae; }}

.al-crit, .al-warn, .al-caut, .al-ok {{ padding:6px 10px; margin:3px 0; font-size:12px; border-radius:2px;
  border-left:4px solid; }}
.al-crit {{ background:#331515; border-color:{BAD};  color:#ffb3ae; }}
.al-warn {{ background:#2d2610; border-color:{WARN}; color:#ffd98a; }}
.al-caut {{ background:#132638; border-color:#3b8fdc; color:#a8d4ff; }}
.al-ok   {{ background:#14291a; border-color:#4fbf5f; color:#b5ecb8; }}

/* ---------- buttons / inputs ---------- */
.stButton > button {{ background:{PANEL_HI}; border:1px solid #4a5058; color:{TEXT}; font-weight:700;
  font-size:12px; letter-spacing:.5px; border-radius:3px; }}
.stButton > button:hover {{ border-color:{LIME}; color:{LIME_HI}; }}
.stButton > button[kind="primary"] {{ background:{LIME}; border-color:{LIME}; color:#16200a; }}
.stButton > button[kind="primary"]:hover {{ background:{LIME_HI}; color:#16200a; }}
.stButton > button:disabled {{ opacity:.45; }}
.stTextInput input, .stNumberInput input, div[data-baseweb="select"] > div {{
  background:#1b1e22 !important; color:{TEXT} !important; border-color:#464c54 !important; }}
.stSlider [role="slider"] {{ background-color:{LIME} !important; }}

/* ---------- waypoint table ---------- */
.mp-wrap {{ border:1px solid {LINE}; border-radius:3px; overflow:hidden; background:{PANEL}; }}
.mp-scroll {{ max-height:230px; overflow:auto; }}
table.mp-table {{ width:100%; border-collapse:collapse; font-family:Consolas,monospace; font-size:12px; }}
table.mp-table th {{ position:sticky; top:0; background:#34393f; color:{TEXT}; text-align:left; font-weight:700;
  padding:5px 8px; border-bottom:1px solid #4a5058; white-space:nowrap; }}
table.mp-table td {{ color:{TEXT}; padding:4px 8px; border-bottom:1px solid #2f3338; white-space:nowrap; }}
table.mp-table tr:nth-child(even) td {{ background:#272a2f; }}
table.mp-table tr.sel td {{ background:#1f5fae; color:#fff; }}
table.mp-table td.cmd {{ color:{LIME_HI}; }}
table.mp-table tr.sel td.cmd {{ color:#fff; }}

/* map overlay text and iframe */
iframe {{ border:1px solid {LINE}; border-radius:3px; }}
"""


def theme_css():
    return "<style>\n" + _BASE_CSS + "\n" + _icon_css() + "\n</style>"


# ---------------------------------------------------------------- top bar
LOGO_SVG = (
    "<svg width='26' height='26' viewBox='0 0 24 24' fill='none' stroke='#b4e04a' stroke-width='1.6' "
    "stroke-linecap='round' stroke-linejoin='round'><circle cx='6' cy='6' r='2.5'/><circle cx='18' cy='6' r='2.5'/>"
    "<circle cx='6' cy='18' r='2.5'/><circle cx='18' cy='18' r='2.5'/><path d='M8 8l8 8M16 8l-8 8'/>"
    "<rect x='10' y='10' width='4' height='4' rx='1'/></svg>")


def topbar_html(mission_id=None, analysis_done=False):
    if analysis_done and mission_id:
        pills = (f'<span class="pill pill-sim">LINK: SIMULATED</span>'
                 f'<span class="pill pill-msn">{mission_id}</span>')
    else:
        pills = ('<span class="pill pill-sim">LINK: SIMULATED</span>'
                 '<span class="pill pill-none">NO MISSION</span>')
    return (
        '<div class="topbar">'
        f'<div class="topbar-left">{LOGO_SVG}'
        '<div class="topbar-title">UAV <span>GROUND CONTROL STATION</span></div></div>'
        '<div class="topbar-right">' + pills +
        '<div style="text-align:right;font-family:Consolas,monospace">'
        '<div id="live-clock" style="font-size:18px;font-weight:700"></div>'
        '<div id="live-date" style="font-size:10px"></div></div></div></div>')


def mp_header(text):
    return f'<div class="mp-hdr">{text}</div>'


# ---------------------------------------------------------------- waypoint table
def waypoint_table_html(rows, columns, selected=0):
    head = "".join(f"<th>{c}</th>" for c in columns)
    body = []
    for i, r in enumerate(rows):
        cells = []
        for c in columns:
            cls = ' class="cmd"' if c == "Command" else ""
            cells.append(f"<td{cls}>{r.get(c, '')}</td>")
        body.append(f'<tr class="{"sel" if i == selected else ""}">' + "".join(cells) + "</tr>")
    return ('<div class="mp-wrap"><div class="mp-hdr" style="margin:0;border-radius:0">Waypoints</div>'
            '<div class="mp-scroll"><table class="mp-table"><thead><tr>' + head +
            "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div></div>")


# ---------------------------------------------------------------- dials (SVG)
def _polar(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.cos(a), cy - r * math.sin(a)


def _arc(cx, cy, r, d0, d1):
    x0, y0 = _polar(cx, cy, r, d0)
    x1, y1 = _polar(cx, cy, r, d1)
    large = 1 if abs(d1 - d0) > 180 else 0
    sweep = 1 if d1 < d0 else 0
    return f"M{x0:.1f},{y0:.1f} A{r},{r} 0 {large} {sweep} {x1:.1f},{y1:.1f}"


def dial_svg(value, vmin, vmax, label, unit, good_below=None, bad_above=None,
             low_is_bad=False, low_warn=None, low_bad=None, fmt="{:.0f}"):
    """
    One round instrument. Sweep runs 225 deg (min) to -45 deg (max).
    Colour bands: for normal dials, green until good_below, amber until bad_above, red after.
    For low-is-bad dials (battery, signal), red below low_bad, amber below low_warn.
    """
    cx = cy = 70
    r = 52
    span = 270.0
    frac = lambda v: max(0.0, min(1.0, (v - vmin) / (vmax - vmin)))
    ang = lambda v: 225 - frac(v) * span
    parts = [f'<path d="{_arc(cx, cy, r, 225, -45)}" stroke="#2f343a" stroke-width="9" fill="none" stroke-linecap="butt"/>']
    if low_is_bad and low_warn is not None and low_bad is not None:
        bands = [(vmin, low_bad, BAD), (low_bad, low_warn, WARN), (low_warn, vmax, GOOD)]
        needle = BAD if value < low_bad else WARN if value < low_warn else GOOD
    elif good_below is not None and bad_above is not None:
        bands = [(vmin, good_below, GOOD), (good_below, bad_above, WARN), (bad_above, vmax, BAD)]
        needle = GOOD if value < good_below else WARN if value < bad_above else BAD
    else:
        bands = [(vmin, vmax, INFO)]
        needle = TEXT
    for lo, hi, col in bands:
        if hi > lo:
            parts.append(f'<path d="{_arc(cx, cy, r, ang(lo), ang(hi))}" stroke="{col}" stroke-width="9" '
                         f'fill="none" opacity="0.85"/>')
    for k in range(0, 11):
        v = vmin + (vmax - vmin) * k / 10
        x0, y0 = _polar(cx, cy, r + 7, ang(v))
        x1, y1 = _polar(cx, cy, r + (11 if k % 5 == 0 else 9), ang(v))
        parts.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="#6b737c" stroke-width="1"/>')
    nx, ny = _polar(cx, cy, r - 6, ang(value))
    parts.append(f'<line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{needle}" stroke-width="3" stroke-linecap="round"/>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="5" fill="{needle}"/>')
    parts.append(f'<text x="{cx}" y="{cy + 30}" text-anchor="middle" fill="{needle}" font-size="17" '
                 f'font-weight="700" font-family="Consolas,monospace">{fmt.format(value)}</text>')
    parts.append(f'<text x="{cx}" y="{cy + 43}" text-anchor="middle" fill="{MUTED}" font-size="9.5" '
                 f'font-family="Segoe UI,Arial">{unit}</text>')
    parts.append(f'<text x="{cx}" y="{cy - 22}" text-anchor="middle" fill="#c9d1d6" font-size="9" '
                 f'font-weight="700" letter-spacing="1" font-family="Segoe UI,Arial">{label.upper()}</text>')
    return f'<svg viewBox="0 0 140 140" width="150" height="150">{"".join(parts)}</svg>'


def dials_page(dials):
    """dials: list of kwargs dicts for dial_svg. Returns a full HTML page for components.html."""
    cells = "".join(f'<div class="cell">{dial_svg(**d)}</div>' for d in dials)
    return (f'<!doctype html><html><body style="margin:0;background:{PANEL};">'
            '<style>.row{display:flex;flex-wrap:wrap;justify-content:space-around;gap:4px;padding:6px 4px}'
            '.cell{flex:1 1 140px;display:flex;justify-content:center}</style>'
            f'<div class="row">{cells}</div></body></html>')


# ---------------------------------------------------------------- HUD (horizon display)
def hud_page(heading_deg=0, altitude_m=0, speed_ms=0, battery_pct=0, signal_pct=0,
             pitch_deg=0, roll_deg=0, armed=False, mode="AUTO", simulated=True,
             risk_pct=None, alt_limit=400):
    """
    Horizon display with compass strip, speed and altitude tapes.
    pitch/roll default to level. With a real drone they come from its attitude data.
    """
    state = "ARMED" if armed else "DISARMED"
    state_col = GOOD if armed else BAD
    risk_txt = "" if risk_pct is None else f"RISK {risk_pct:.0f}%"
    sim_tag = ('<text x="10" y="76" fill="#f5b83d" font-size="10" font-weight="700" '
               'font-family="Consolas,monospace">SIMULATED TELEMETRY</text>') if simulated else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"></head>
<body style="margin:0;background:#0e1012;">
<svg id="hud" viewBox="0 0 520 420" width="100%" style="display:block;max-height:430px"></svg>
<script>
const P = {{hdg:{heading_deg:.1f}, alt:{altitude_m:.1f}, spd:{speed_ms:.1f}, bat:{battery_pct:.1f},
  sig:{signal_pct:.1f}, pitch:{pitch_deg:.1f}, roll:{roll_deg:.1f}, state:"{state}",
  stateCol:"{state_col}", mode:"{mode}", risk:"{risk_txt}", altLimit:{alt_limit}}};
const NS="http://www.w3.org/2000/svg";
const svg=document.getElementById("hud");
function el(tag,attrs,parent){{const e=document.createElementNS(NS,tag);
  for(const k in attrs)e.setAttribute(k,attrs[k]); (parent||svg).appendChild(e); return e;}}
function txt(s,x,y,size,fill,anchor,weight,parent){{const t=el("text",{{x:x,y:y,fill:fill,"font-size":size,
  "text-anchor":anchor||"middle","font-weight":weight||"400","font-family":"Consolas,monospace"}},parent);
  t.textContent=s;return t;}}
const W=520,H=420,cx=260,cy=215, PPD=4.2;
const defs=el("defs",{{}});
const clip=el("clipPath",{{id:"cp"}},defs); el("rect",{{x:60,y:60,width:400,height:300}},clip);
const g=el("g",{{"clip-path":"url(#cp)"}});
const rot=el("g",{{transform:"rotate("+(-P.roll)+" "+cx+" "+cy+")"}},g);
const tr=el("g",{{transform:"translate(0 "+(P.pitch*PPD)+")"}},rot);
el("rect",{{x:-400,y:-600,width:1400,height:815,fill:"#3d78b8"}},tr);
el("rect",{{x:-400,y:215,width:1400,height:900,fill:"#6f5a2e"}},tr);
el("line",{{x1:-400,y1:215,x2:1000,y2:215,stroke:"#fff","stroke-width":2}},tr);
for(let p=-30;p<=30;p+=5){{ if(p===0)continue;
  const y=215-p*PPD, w=(p%10===0)?60:30;
  el("line",{{x1:cx-w/2,y1:y,x2:cx+w/2,y2:y,stroke:"#fff","stroke-width":1.5}},tr);
  if(p%10===0){{txt(Math.abs(p),cx-w/2-12,y+4,11,"#fff","middle","400",tr);txt(Math.abs(p),cx+w/2+12,y+4,11,"#fff","middle","400",tr);}}
}}
// aircraft symbol
el("path",{{d:"M185,215 h55 l8,10 M335,215 h-55 l-8,10",stroke:"#ffd400","stroke-width":4,fill:"none"}});
el("circle",{{cx:cx,cy:cy,r:4,fill:"#ffd400"}});
// frame
el("rect",{{x:60,y:60,width:400,height:300,fill:"none",stroke:"#3a3f45","stroke-width":2}});
// compass strip
el("rect",{{x:60,y:20,width:400,height:28,fill:"#16181b",stroke:"#3a3f45"}});
const names={{0:"N",90:"E",180:"S",270:"W"}};
for(let d=-60; d<=60; d+=5){{
  const hv=((Math.round(P.hdg/5)*5+d)%360+360)%360, x=cx+(d+(Math.round(P.hdg/5)*5-P.hdg))*3.3;
  if(x<66||x>454)continue;
  el("line",{{x1:x,y1:48,x2:x,y2:(hv%10===0)?38:43,stroke:"#9aa3ad"}});
  if(hv%30===0) txt(names[hv]||hv,x,34,11,names[hv]?"#b4e04a":"#e6e8ea","middle","700");
}}
el("path",{{d:"M"+(cx-6)+",18 L"+(cx+6)+",18 L"+cx+",26 Z",fill:"#ffd400"}});
txt(Math.round(P.hdg)+"\\u00b0",cx,13,11,"#ffd400","middle","700");
// speed tape
el("rect",{{x:8,y:60,width:50,height:300,fill:"#16181bcc",stroke:"#3a3f45"}});
const sg=el("g",{{"clip-path":"url(#cps)"}}); const cps=el("clipPath",{{id:"cps"}},defs); el("rect",{{x:8,y:60,width:50,height:300}},cps);
for(let s=Math.floor(P.spd)-12;s<=Math.ceil(P.spd)+12;s++){{
  if(s<0)continue; const y=cy-(s-P.spd)*10;
  if(y<62||y>358)continue;
  el("line",{{x1:46,y1:y,x2:58,y2:y,stroke:"#9aa3ad"}},sg);
  if(s%5===0) txt(s,34,y+4,11,"#e6e8ea","middle","400",sg);
}}
el("rect",{{x:6,y:cy-12,width:48,height:24,fill:"#000",stroke:"#ffd400"}});
txt(P.spd.toFixed(1),30,cy+5,13,"#ffd400","middle","700");
txt("SPEED m/s",33,376,9,"#9aa3ad","middle","400");
// altitude tape
el("rect",{{x:462,y:60,width:50,height:300,fill:"#16181bcc",stroke:"#3a3f45"}});
const cpa=el("clipPath",{{id:"cpa"}},defs); el("rect",{{x:462,y:60,width:50,height:300}},cpa);
const ag=el("g",{{"clip-path":"url(#cpa)"}});
for(let a=Math.floor(P.alt/5)*5-60;a<=P.alt+60;a+=5){{
  const y=cy-(a-P.alt)*2.4; if(y<62||y>358||a<0)continue;
  el("line",{{x1:462,y1:y,x2:474,y2:y,stroke:"#9aa3ad"}},ag);
  if(a%20===0) txt(a,494,y+4,11,"#e6e8ea","middle","400",ag);
}}
const yl=cy-(P.altLimit-P.alt)*2.4;
if(yl>62&&yl<358) el("line",{{x1:462,y1:yl,x2:512,y2:yl,stroke:"#ff6b5e","stroke-width":2,"stroke-dasharray":"4 3"}},ag);
el("rect",{{x:466,y:cy-12,width:46,height:24,fill:"#000",stroke:"#ffd400"}});
txt(P.alt.toFixed(0),489,cy+5,13,"#ffd400","middle","700");
txt("ALT m (AGL)",487,376,9,"#9aa3ad","middle","400");
// status text
txt(P.state,cx,130,34,P.stateCol,"middle","700").setAttribute("opacity","0.9");
// bottom bar
el("rect",{{x:0,y:388,width:520,height:32,fill:"#16181b",stroke:"#3a3f45"}});
const bc=P.bat<20?"#ff6b5e":P.bat<35?"#f5b83d":"#8bd44a";
txt("BAT "+P.bat.toFixed(0)+"%",12,408,13,bc,"start","700");
const sc=P.sig<20?"#ff6b5e":P.sig<35?"#f5b83d":"#8bd44a";
txt("LINK "+P.sig.toFixed(0)+"%",150,408,13,sc,"start","700");
txt(P.risk,300,408,13,"#e6e8ea","start","700");
txt("MODE "+P.mode,430,408,12,"#9aa3ad","start","700");
</script>
{''}
</body></html>""".replace("</script>\n{''}", "</script>")
