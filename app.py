"""
app.py — UAV Mission Risk Prediction & Real-Time Monitoring System
Ground Control Station Interface (Mission Planner style)
"""
import sys, os, time, math, json, datetime, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

from streamlit_js_eval import get_geolocation
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Arc
import io
import streamlit as st
import streamlit.components.v1 as components

from utils.config       import FEATURE_NAMES, UAV_SPECS, MISSION_TYPES
from utils.geocoding    import (geocode_place, parse_coordinates, reverse_geocode,
                                haversine_distance, get_bearing, bearing_to_compass,
                                interpolate_route, estimate_flight_time,
                                generate_nfz, check_nfz_conflicts, get_grid_reference)
from utils.weather      import get_weather, get_forecast
from utils.ml_model     import (train_model, predict_risk,
                                get_feature_contributions, generate_explanation)
from utils.deep_learning import (train_all, predict_deep_mlp, predict_lstm,
                                  predict_transformer, detect_anomaly)
from utils.alerts        import (evaluate_alerts, battery_drain_per_km,
                                  risk_color, compute_readiness,
                                  generate_sitrep, check_compliance)
from utils.terrain import (get_elevation_profile, check_terrain_clearance,
                            get_terrain_alerts, get_max_terrain_risk_summary)
from utils.rth import full_contingency_check, check_rth_feasibility
from utils.gps_resilience import simulate_gps_event, dead_reckoning_estimate, gps_risk_penalty, get_gps_alert
from utils.swarm import check_swarm_conflicts, conflict_to_alert
from utils.ui_theme import (theme_css, topbar_html, mp_header, waypoint_table_html,
                            hud_page, dials_page)
from utils.place_search import search_places, looks_like_coords, STATUS as SEARCH_STATUS
try:
    from streamlit_searchbox import st_searchbox
    SEARCH_OK = True
except Exception:
    SEARCH_OK = False
try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_OK = True
except Exception:
    FOLIUM_OK = False

# ------------------------------------------------------------
# place search box (type "ban" and get a list of places, like a maps app)
# ------------------------------------------------------------
SEARCHBOX_STYLE = {
    "searchbox": {
        "control": {"backgroundColor": "#1b1e22", "borderColor": "#464c54", "color": "#e6e8ea",
                    "minHeight": 40},
        "singleValue": {"color": "#e6e8ea"},
        "input": {"color": "#e6e8ea"},
        "placeholder": {"color": "#8a939c"},
        "menuList": {"backgroundColor": "#23262a"},
        "option": {"color": "#e6e8ea", "backgroundColor": "#23262a", "highlightColor": "#33401a"},
    },
    "dropdown": {"fill": "#9ac329"},
    "clear": {"fill": "#9aa3ad"},
}


SEARCH_RADIUS_KM = 100   # this system is built for missions up to 100 km


def _search_box_core(key, bias, radius, scope):
    def _search(q):
        centre = bias
        if key == "dst_search":       # destination suggestions are centred on the chosen source
            picked = str((st.session_state.get("src_search") or {}).get("result") or "")
            if looks_like_coords(picked):
                centre = tuple(float(v) for v in picked.split(","))
        hits = search_places(q, bias=centre, radius_km=radius)
        st.session_state[key + "_status"] = dict(SEARCH_STATUS)
        return hits

    st_searchbox(_search,
                 debounce=300,
                 placeholder="Type a city, village or area (e.g. ban...)",
                 key=key, default_use_searchterm=True,
                 rerun_scope=scope, style_overrides=SEARCHBOX_STYLE)
    _s = st.session_state.get(key + "_status") or {"query": ""}
    if _s["query"]:
        if _s["note"]:
            st.caption(_s["note"])
        elif _s["sources"] == ["offline list"]:
            st.caption(f'{_s["n"]} from the built-in offline list '
                       '(online place search not reachable from this computer)')
        else:
            st.caption(f'{_s["n"]} suggestion{"" if _s["n"] == 1 else "s"} - '
                       f'{" + ".join(_s["sources"]) or "none found"}')


if SEARCH_OK and hasattr(st, "fragment"):
    @st.fragment
    def _search_box(key, bias, radius):
        # only this box re-runs while typing, so the rest of the page stays still
        _search_box_core(key, bias, radius, "fragment")
else:
    def _search_box(key, bias, radius):
        _search_box_core(key, bias, radius, "app")


def place_box(key, bias=None, radius=None):
    """
    Returns (text, mode) for the analysis step.
    Picked suggestion -> ("lat, lon", "GPS Coordinates").
    Typed but not picked -> (typed text, "Name / Village / City").
    """
    if not SEARCH_OK:
        st.warning("Suggestion box not available. Run: python -m pip install streamlit-searchbox "
                   "(using a plain text box for now)")
        txt = st.text_input("Place", key=key + "_txt", placeholder="City, village or area")
        return txt, "Name / Village / City"
    _search_box(key, bias, radius)
    res = str((st.session_state.get(key) or {}).get("result") or "").strip()
    if looks_like_coords(res):
        return res, "GPS Coordinates"
    return res, "Name / Village / City"


def resolve_place(text):
    """Name -> (lat, lon). Uses the project geocoder first, then the suggestion search."""
    try:
        return geocode_place(text)
    except Exception:
        hits = search_places(text, limit=1)
        if hits:
            return parse_coordinates(hits[0][1])
        raise


def html_frame(html, height):
    """Embed a small HTML page. Uses st.iframe on new Streamlit, components.html on older ones."""
    if hasattr(st, "iframe"):
        st.iframe(html, height=max(int(height), 1))
    else:
        components.html(html, height=height)

st.set_page_config(page_title="UAV Ground Control Station",
                    page_icon="🛸", layout="wide",
                    initial_sidebar_state="collapsed")

# ============================================================
# THEME  (dark ground-control look, see utils/ui_theme.py)
# ============================================================
st.markdown(theme_css(), unsafe_allow_html=True)

# ============================================================
# helper functions
# ============================================================
def fig_png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    return buf.getvalue()


def metric(val, lbl, color="#1a5fb4"):
    return (f'<div class="metric"><div class="metric-val" '
            f'style="color:{color}">{val}</div>'
            f'<div class="metric-lbl">{lbl}</div></div>')


def status_html(pred):
    s = pred["risk_score"]
    cls = ("status-crit" if s >= 80 else "status-high" if s >= 60
           else "status-mod" if s >= 35 else "status-safe")
    return (f'<div class="status-banner {cls}">{pred["label"]} '
            f'&nbsp;|&nbsp; RISK: {s:.1f}% '
            f'&nbsp;|&nbsp; CONFIDENCE: {pred["confidence"]:.1f}%</div>')


def alert_line(a):
    cls = {"critical": "al-crit", "warning": "al-warn",
           "caution": "al-caut", "info": "al-caut"}.get(a.level, "al-caut")
    act = f'<br><span style="color:#888">→ {a.action}</span>' if a.action else ""
    return f'<div class="{cls}">{a.message}{act}</div>'


def draw_gauge(value, vmin, vmax, label, unit, warn=None, danger=None):
    fig, ax = plt.subplots(figsize=(2.0, 2.0), facecolor="white")
    ax.set_facecolor("white")
    ax.set_xlim(-1.2, 1.2); ax.set_ylim(-1.2, 1.2)
    ax.set_aspect("equal"); ax.axis("off")
    span = 270
    ax.add_patch(Arc((0, 0), 1.78, 1.78, angle=0, theta1=225, theta2=315,
                      color="#e0e0e0", linewidth=11))
    if warn and danger:
        g = 225 - ((warn - vmin) / (vmax - vmin)) * span
        a = 225 - ((danger - vmin) / (vmax - vmin)) * span
        ax.add_patch(Arc((0, 0), 1.78, 1.78, angle=0, theta1=g, theta2=225,
                          color="#3fa33f", linewidth=11))
        ax.add_patch(Arc((0, 0), 1.78, 1.78, angle=0, theta1=a, theta2=g,
                          color="#d69f00", linewidth=11))
        ax.add_patch(Arc((0, 0), 1.78, 1.78, angle=0, theta1=315, theta2=a,
                          color="#c23b3b", linewidth=11))
    else:
        nv = max(0, min(1, (value - vmin) / (vmax - vmin)))
        ax.add_patch(Arc((0, 0), 1.78, 1.78, angle=0,
                          theta1=225 - nv * span, theta2=225,
                          color="#1a5fb4", linewidth=11))
    norm = max(0, min(1, (value - vmin) / (vmax - vmin)))
    ang = math.radians(225 - norm * span)
    nc = ("#c23b3b" if danger and value >= danger else
          "#d69f00" if warn and value >= warn else "#333333")
    ax.annotate("", xy=(0.68*math.cos(ang), 0.68*math.sin(ang)), xytext=(0, 0),
                arrowprops=dict(arrowstyle="-|>", color=nc, lw=2.2, mutation_scale=10))
    ax.plot(0, 0, "o", color=nc, markersize=5)
    ax.text(0, -0.24, f"{value:.1f}", color=nc, fontsize=12, fontweight="bold",
            ha="center", va="center")
    ax.text(0, -0.46, unit, color="#888", fontsize=6.5, ha="center")
    ax.text(0, 0.62, label.upper(), color="#888", fontsize=6.5, ha="center")
    plt.tight_layout(pad=0)
    return fig_png(fig)


def draw_telemetry(tlog):
    if len(tlog) < 2:
        return b""
    steps = [t["step"] for t in tlog]
    batt  = [t["battery"] for t in tlog]
    wind  = [t["wind"] for t in tlog]
    risk  = [t["risk_score"] for t in tlog]
    sig   = [t["signal"] for t in tlog]
    fig, axes = plt.subplots(2, 2, figsize=(9, 4.2), facecolor="white")
    for ax, data, title, col, w, d in [
        (axes[0][0], batt, "Battery (%)", "#3fa33f", 25, 15),
        (axes[0][1], wind, "Wind (m/s)",  "#1a5fb4", 10, 15),
        (axes[1][0], risk, "Risk (%)",    "#d9752c", 35, 60),
        (axes[1][1], sig,  "Signal (%)",  "#7a4fbf", 35, 20),
    ]:
        ax.set_facecolor("#fafafa")
        ax.plot(steps, data, color=col, lw=2, marker="o", markersize=3)
        ax.fill_between(steps, data, alpha=0.1, color=col)
        ax.axhline(w, color="#d69f00", lw=0.8, ls="--", alpha=0.7)
        ax.axhline(d, color="#c23b3b", lw=0.8, ls="--", alpha=0.7)
        ax.set_title(title, fontsize=9)
        ax.grid(alpha=0.3)
        for sp in ax.spines.values():
            sp.set_color("#ccc")
    plt.tight_layout()
    return fig_png(fig)


def draw_fi(fi_dict):
    lmap = {"distance_km":"Distance","battery_pct":"Battery","wind_speed_mps":"Wind Speed",
            "payload_kg":"Payload","signal_strength_pct":"Signal","temperature_c":"Temperature",
            "altitude_m":"Altitude","humidity_pct":"Humidity","flight_time_min":"Flight Time",
            "battery_drain_rate":"Drain Rate"}
    if not fi_dict:
        return b""
    items = sorted(fi_dict.items(), key=lambda x: x[1])
    labels = [lmap.get(k, k) for k, _ in items]
    vals = [v for _, v in items]
    colors = ["#c23b3b" if v > 0.2 else "#d69f00" if v > 0.1 else "#1a5fb4" for v in vals]
    fig, ax = plt.subplots(figsize=(5, 3.3), facecolor="white")
    ax.set_facecolor("#fafafa")
    bars = ax.barh(labels, vals, color=colors, height=0.55, edgecolor="#ccc")
    for bar, val in zip(bars, vals):
        ax.text(val + 0.004, bar.get_y() + bar.get_height()/2, f"{val:.3f}",
                va="center", fontsize=8)
    ax.set_title("Feature Importance (Random Forest)", fontsize=10)
    ax.grid(axis="x", alpha=0.3)
    for sp in ax.spines.values():
        sp.set_color("#ccc")
    plt.tight_layout()
    return fig_png(fig)


def draw_attn(weights):
    fig, ax = plt.subplots(figsize=(8, 1.5), facecolor="white")
    data = np.array(weights).reshape(1, -1)
    im = ax.imshow(data, cmap="YlOrRd", aspect="auto", vmin=0)
    for i, w in enumerate(weights):
        ax.text(i, 0, f"{w:.3f}", ha="center", va="center", fontsize=8,
                color="black" if w < np.mean(weights)*1.3 else "white")
    ax.set_xticks(range(len(weights)))
    ax.set_xticklabels([f"WP{i+1}" for i in range(len(weights))], fontsize=7.5)
    ax.set_yticks([])
    ax.set_title("LSTM Attention Weights — Waypoint Criticality", fontsize=9.5)
    plt.colorbar(im, ax=ax, fraction=0.02, pad=0.01)
    plt.tight_layout()
    return fig_png(fig)


def draw_wp_risk(per_wp, worst):
    fig, ax = plt.subplots(figsize=(8, 2.6), facecolor="white")
    ax.set_facecolor("#fafafa")
    colors = ["#c23b3b" if r >= 60 else "#d69f00" if r >= 35 else "#3fa33f" for r in per_wp]
    bars = ax.bar(range(1, len(per_wp)+1), per_wp, color=colors, edgecolor="#999")
    if worst < len(bars):
        bars[worst].set_edgecolor("black"); bars[worst].set_linewidth(2)
    ax.axhline(60, color="#c23b3b", lw=0.8, ls="--", alpha=0.7)
    ax.axhline(35, color="#d69f00", lw=0.8, ls="--", alpha=0.7)
    ax.set_title("Transformer — Per-Waypoint Risk (Parallel Computation)", fontsize=9.5)
    ax.set_ylim(0, 105)
    ax.grid(axis="y", alpha=0.3)
    for sp in ax.spines.values():
        sp.set_color("#ccc")
    plt.tight_layout()
    return fig_png(fig)


def draw_curves(history, title):
    epochs = list(range(1, len(history["loss"])+1))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7, 2.6), facecolor="white")
    a1.set_facecolor("#fafafa")
    a1.plot(epochs, history["loss"], color="#d9752c", lw=2)
    a1.fill_between(epochs, history["loss"], alpha=0.1, color="#d9752c")
    a1.set_title("Training Loss", fontsize=9)
    a1.grid(alpha=0.3)
    if "val_acc" in history:
        a2.set_facecolor("#fafafa")
        a2.plot(epochs, [x*100 for x in history["val_acc"]], color="#3fa33f", lw=2)
        a2.set_title("Validation Accuracy (%)", fontsize=9)
        a2.grid(alpha=0.3)
    fig.suptitle(title, fontsize=9.5)
    plt.tight_layout()
    return fig_png(fig)


def build_map(src, dst, wps, nfz_list, nfz_conf, tlog=None, info=None, height_px=520):
    """Satellite map, yellow route, numbered waypoint badges, home marker, NFZ circles."""
    m = folium.Map(location=[(src[0]+dst[0])/2, (src[1]+dst[1])/2], zoom_start=12,
                   tiles=None, control_scale=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Imagery (c) Esri, Maxar, Earthstar Geographics", name="Satellite", max_zoom=19).add_to(m)
    folium.TileLayer("OpenStreetMap", name="Street map").add_to(m)

    pts = [[w[0], w[1]] for w in wps]
    if len(pts) >= 2:
        folium.PolyLine(pts, color="#ffe000", weight=3, opacity=0.95).add_to(m)

    for i, wp in enumerate(wps):
        rs = tlog[i]["risk_score"] if tlog and i < len(tlog) else 0
        pin = "#3fa33f" if rs < 35 else "#d69f00" if rs < 60 else "#c23b3b"
        badge = ('<div style="position:relative;width:34px;height:40px">'
                 f'<div style="position:absolute;left:11px;top:14px;width:12px;height:12px;border-radius:50%;'
                 f'background:{pin};border:2px solid #fff;box-shadow:0 0 3px #000"></div>'
                 f'<div style="position:absolute;left:0;top:-4px;min-width:34px;text-align:center;'
                 f'background:#e8eef7;border:1px solid #6b7a90;border-radius:9px;color:#1c2a3a;'
                 f'font:700 11px Segoe UI,Arial;padding:1px 0">{i+1}</div></div>')
        folium.Marker([wp[0], wp[1]], icon=folium.DivIcon(html=badge, icon_size=(34, 40), icon_anchor=(17, 26)),
                      popup=folium.Popup(
                          f"<b>WP{i+1:02d}</b><br>LAT {wp[0]:.5f}<br>LON {wp[1]:.5f}<br>"
                          f"GRID {get_grid_reference(wp[0], wp[1])}"
                          f"{'<br>RISK ' + str(rs) + '%' if tlog else ''}", max_width=180)).add_to(m)

    for nfz in nfz_list:
        col = ("#ff5a4d" if nfz["severity"] == "prohibited" else
               "#f5b83d" if nfz["severity"] == "restricted" else "#5aa9ff")
        folium.Circle([nfz["lat"], nfz["lon"]], radius=nfz["radius_km"]*1000, color=col, fill=True,
                      fill_color=col, fill_opacity=0.18, weight=2, dash_array="8 4",
                      popup=folium.Popup(f"<b>{nfz['id']}</b><br>{nfz['name']}<br>"
                                         f"SEV {nfz['severity'].upper()}", max_width=170)).add_to(m)

    if tlog:
        lw = tlog[-1].get("position", dst)
        folium.Marker([lw[0], lw[1]], popup="UAV current position",
                      icon=folium.Icon(color="blue", icon="plane", prefix="fa")).add_to(m)

    home = ('<div style="background:#e8eef7;border:1px solid #6b7a90;border-radius:9px;color:#1c2a3a;'
            'font:700 11px Segoe UI,Arial;padding:1px 9px;white-space:nowrap;display:inline-block">Home</div>')
    folium.Marker([src[0], src[1]], popup="HOME / SOURCE",
                  icon=folium.DivIcon(html=home, icon_size=(60, 22), icon_anchor=(30, -8))).add_to(m)
    folium.CircleMarker([src[0], src[1]], radius=6, color="#fff", weight=2, fill=True,
                        fill_color="#3fa33f", fill_opacity=1).add_to(m)
    if (dst[0], dst[1]) != (src[0], src[1]):
        folium.Marker([dst[0], dst[1]], popup="DESTINATION",
                      icon=folium.Icon(color="darkred", icon="flag-checkered", prefix="fa")).add_to(m)

    if info:
        box = ('<div style="position:absolute;top:10px;left:56px;z-index:9999;background:rgba(14,16,18,.82);'
               'color:#e6e8ea;font:12px Consolas,monospace;padding:6px 10px;border-left:3px solid #9ac329;'
               'line-height:1.5">' + "<br>".join(info) + "</div>")
        m.get_root().html.add_child(folium.Element(box))

    if len(pts) >= 2:
        m.fit_bounds([[min(p[0] for p in pts), min(p[1] for p in pts)],
                      [max(p[0] for p in pts), max(p[1] for p in pts)]], padding=(40, 40))
    folium.LayerControl(position="topright", collapsed=True).add_to(m)
    return m

# ============================================================
# session state
# ============================================================
DEFAULTS = dict(
    ml_model=None, ml_scaler=None, ml_meta=None, dl_models=None,
    analysis_done=False, sim_done=False, sim_running=False,
    src_coords=None, dst_coords=None, waypoints=None,
    weather_src=None, weather_dst=None, forecast=None,
    nfz_list=None, nfz_conflicts=None, distance_km=None,
    features=None, prediction=None, contribs=None,
    alerts=None, readiness=None, sitrep=None,
    telemetry_log=[], mission_id=None, mission_start=None,
    dl_preds=None, anomaly=None, src_name="", dst_name="",
    bearing=0, compass="N", ft_est=None, compliance=None,
    explanation="",
)
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


@st.cache_resource(show_spinner=False)
def load_ml():
    return train_model()


@st.cache_resource(show_spinner=False)
def load_dl():
    return train_all(force_retrain=False)


if st.session_state.ml_model is None:
    with st.spinner("Loading AI models..."):
        m, sc, meta = load_ml()
        st.session_state.ml_model = m
        st.session_state.ml_scaler = sc
        st.session_state.ml_meta = meta

if st.session_state.dl_models is None:
    with st.spinner("Loading deep learning models..."):
        st.session_state.dl_models = load_dl()

now = datetime.datetime.now()
ml_acc = st.session_state.ml_meta.get("accuracy", "-")

# ============================================================
# TOP BAR  (title, link status, live clock)
# ============================================================
st.markdown(topbar_html(st.session_state.mission_id, st.session_state.analysis_done),
            unsafe_allow_html=True)

html_frame("""
<script>
function updateClock(){
  var now = new Date();
  var timeStr = now.toLocaleTimeString('en-GB');
  var dateStr = now.toLocaleDateString('en-GB', {day:'2-digit', month:'short', year:'numeric'});
  var clockEl = window.parent.document.getElementById('live-clock');
  var dateEl = window.parent.document.getElementById('live-date');
  if (clockEl) clockEl.innerText = timeStr;
  if (dateEl) dateEl.innerText = dateStr;
}
updateClock();
setInterval(updateClock, 1000);
</script>
""", 0)

# ============================================================
# TABS  (icons are drawn by the theme CSS)
# ============================================================
tabs = st.tabs(["FLIGHT PLAN", "FLIGHT DATA", "WEATHER", "NFZ STATUS",
                "AI ANALYSIS", "SIMULATION", "DEEP LEARNING", "REPORT",
                "TERRAIN & RTH", "SWARM"])

# ------------------------------------------------------------
# TAB 0 - FLIGHT PLAN  (map + action panel + waypoint table)
# ------------------------------------------------------------
with tabs[0]:
    map_col, action_col = st.columns([3.2, 1.1], gap="small")

    with action_col:
        with st.container(border=True):
            st.markdown(mp_header("Mission parameters"), unsafe_allow_html=True)

            near_only = st.checkbox(f"Only suggest places within {SEARCH_RADIUS_KM} km of me",
                                    value=True, key="near_only")
            _radius = SEARCH_RADIUS_KM if near_only else None

            st.markdown("**Source (auto-detected via GPS)**")
            location = get_geolocation()
            _bias = None
            if location and "coords" in location:
                _bias = (location["coords"]["latitude"], location["coords"]["longitude"])

            if location and "coords" in location:
                auto_lat = location["coords"]["latitude"]
                auto_lon = location["coords"]["longitude"]
                accuracy = location["coords"].get("accuracy", 0)

                src_input = f"{auto_lat}, {auto_lon}"
                src_mode = "GPS Coordinates"

                st.success(f"Location locked: {auto_lat:.5f}, {auto_lon:.5f} "
                           f"(+/-{accuracy:.0f} m)")

                use_manual_src = st.checkbox("Override with manual source instead")
                if use_manual_src:
                    st.markdown("Manual source")
                    src_input, src_mode = place_box("src_search", _bias, _radius)
            else:
                st.warning("Waiting for GPS permission. Click 'Allow' in your "
                           "browser's location popup.")
                st.markdown("Source")
                src_input, src_mode = place_box("src_search", _bias, _radius)

            st.markdown("**Destination**")
            dst_mode = st.radio("Destination input mode",
                                ["Name / Village / City", "GPS Coordinates"],
                                label_visibility="collapsed", key="dst_mode_radio")
            if dst_mode == "Name / Village / City":
                # destination suggestions are centred on the source (picked place or GPS fix)
                _home_xy = _bias
                if looks_like_coords(str(src_input)):
                    _la, _lo = [float(v) for v in str(src_input).split(",")]
                    _home_xy = (_la, _lo)
                dst_input, dst_mode = place_box("dst_search", _home_xy, _radius)
            else:
                dst_input = st.text_input("Destination (lat, lon)", value="34.0493, 74.3800")

            mission_type = st.selectbox("Mission type", MISSION_TYPES)
            n_wps = st.slider("Waypoints", 6, 20, 12)

            battery  = st.slider("Battery (%)", 10, 100, 85)
            payload  = st.slider("Payload (kg)", 0.0, 5.0, 1.5, step=0.1)
            signal   = st.slider("Signal (%)", 10, 100, 78)
            altitude = st.slider("Altitude (m)", 20, 400, 120, step=10)

            analyse_btn  = st.button("ANALYSE MISSION", type="primary",
                                      use_container_width=True)
            simulate_btn = st.button("RUN SIMULATION", type="primary",
                                      use_container_width=True,
                                      disabled=not st.session_state.analysis_done)
            if st.button("ABORT / RTH", use_container_width=True):
                st.error("ABORT ISSUED - RETURN TO HOME ACTIVE")

        if st.session_state.analysis_done:
            _s = st.session_state.src_coords
            _d = st.session_state.dst_coords
            st.markdown(
                f'<div class="geo-line">HOME {_s[0]:.5f}, {_s[1]:.5f}</div>'
                f'<div class="geo-line">DEST {_d[0]:.5f}, {_d[1]:.5f}</div>',
                unsafe_allow_html=True)

    with map_col:
        if FOLIUM_OK:
            if st.session_state.analysis_done:
                _wps = st.session_state.waypoints
                _src = st.session_state.src_coords
                _dst = st.session_state.dst_coords
                _info = [f"Distance: {st.session_state.distance_km:.2f} km",
                         f"Bearing: {st.session_state.bearing:.0f} deg {st.session_state.compass}",
                         f"Waypoints: {len(_wps)}   NFZ zones: {len(st.session_state.nfz_list)}"]
                fmap = build_map(_src, _dst, _wps, st.session_state.nfz_list,
                                 st.session_state.nfz_conflicts,
                                 st.session_state.telemetry_log or None, info=_info)
            else:
                # before analysis: show the home position (GPS fix if we have one) at street level
                if location and "coords" in location:
                    _home = (location["coords"]["latitude"], location["coords"]["longitude"])
                    _txt = "Home = your GPS position"
                else:
                    _home = (12.9716, 77.5946)
                    _txt = "Waiting for GPS (showing default area)"
                fmap = build_map(_home, _home, [], [], [], None,
                                 info=[_txt, "Enter a destination and press ANALYSE MISSION"])
                fmap.location = list(_home)
                fmap.options["zoom"] = 13
            st_folium(fmap, width=None, height=520, returned_objects=[], key="plan_map")
        else:
            st.info("Map library not installed. Run: pip install folium streamlit-folium")

        if st.session_state.analysis_done:
            _wps = st.session_state.waypoints
            _feats = st.session_state.features
            _rows = []
            for i, wp in enumerate(_wps):
                frac = i / max(len(_wps)-1, 1)
                bt = max(0, _feats["battery_pct"] - frac*_feats["battery_pct"]*0.65)
                sect = ("ALPHA" if frac < 0.25 else "BRAVO" if frac < 0.5
                        else "CHARLIE" if frac < 0.75 else "DELTA")
                if i == 0:
                    seg_km, az = 0.0, 0
                else:
                    p = _wps[i-1]
                    seg_km = haversine_distance(p[0], p[1], wp[0], wp[1])
                    az = get_bearing(p[0], p[1], wp[0], wp[1])
                _rows.append({"#": i+1, "Command": "TAKEOFF" if i == 0 else "WAYPOINT",
                              "Lat": f"{wp[0]:.6f}", "Long": f"{wp[1]:.6f}", "Alt (m)": altitude,
                              "Dist (km)": f"{seg_km:.2f}", "AZ": f"{az:.0f}",
                              "Battery %": f"{bt:.1f}", "Sector": sect,
                              "Grid ref": get_grid_reference(wp[0], wp[1])})
            st.markdown(waypoint_table_html(
                _rows, ["#", "Command", "Lat", "Long", "Alt (m)", "Dist (km)", "AZ",
                        "Battery %", "Sector", "Grid ref"]), unsafe_allow_html=True)


# ============================================================
# ANALYSIS HANDLER
# ============================================================
if analyse_btn:
    if not str(src_input).strip() or not str(dst_input).strip():
        st.error("Please type a source and a destination, then pick one of the suggestions.")
        st.stop()
    st.session_state.analysis_done = False
    st.session_state.sim_done = False
    st.session_state.telemetry_log = []
    st.session_state.mission_id = f"MSN-{now.strftime('%H%M%S')}"
    st.session_state.mission_start = time.time()

    prog = st.progress(0, text="Resolving locations...")
    try:
        if src_mode == "Name / Village / City":
            slat, slon = resolve_place(src_input)
        else:
            slat, slon = parse_coordinates(src_input)

        if dst_mode == "Name / Village / City":
            dlat, dlon = resolve_place(dst_input)
        else:
            dlat, dlon = parse_coordinates(dst_input)

        sname = reverse_geocode(slat, slon)
        dname = reverse_geocode(dlat, dlon)
        st.session_state.src_coords = (slat, slon)
        st.session_state.dst_coords = (dlat, dlon)
        st.session_state.src_name = sname
        st.session_state.dst_name = dname
        prog.progress(15, text="Calculating route...")

        dist = haversine_distance(slat, slon, dlat, dlon)
        wps = interpolate_route(slat, slon, dlat, dlon, n_wps)
        bear = get_bearing(slat, slon, dlat, dlon)
        comp = bearing_to_compass(bear)
        ft = estimate_flight_time(dist, payload, 0)
        st.session_state.distance_km = dist
        st.session_state.waypoints = wps
        st.session_state.bearing = bear
        st.session_state.compass = comp
        st.session_state.ft_est = ft
        prog.progress(25, text="Fetching live weather...")

        w_src = get_weather(slat, slon)
        w_dst = get_weather(dlat, dlon)
        fcast = get_forecast(slat, slon)
        st.session_state.weather_src = w_src
        st.session_state.weather_dst = w_dst
        st.session_state.forecast = fcast
        prog.progress(40, text="Scanning no-fly zones...")

        nfz_list = generate_nfz(slat, slon, dlat, dlon)
        nfz_conf = check_nfz_conflicts(wps, nfz_list)
        st.session_state.nfz_list = nfz_list
        st.session_state.nfz_conflicts = nfz_conf
        prog.progress(55, text="Running AI risk assessment...")

        avg_wind = (w_src["wind_speed"] + w_dst["wind_speed"]) / 2
        avg_temp = (w_src["temperature"] + w_dst["temperature"]) / 2
        drain = battery_drain_per_km(payload, avg_wind, altitude, avg_temp)
        feats = dict(distance_km=dist, battery_pct=float(battery),
                     wind_speed_mps=avg_wind, payload_kg=float(payload),
                     signal_strength_pct=float(signal), temperature_c=avg_temp,
                     altitude_m=float(altitude), humidity_pct=float(w_src["humidity"]),
                     flight_time_min=ft["flight_time_min"], battery_drain_rate=drain)
        st.session_state.features = feats

        pred = predict_risk(st.session_state.ml_model, st.session_state.ml_scaler, feats)
        contribs = get_feature_contributions(st.session_state.ml_model,
                                              st.session_state.ml_scaler, feats)
        expl = generate_explanation(pred, feats, contribs)
        st.session_state.prediction = pred
        st.session_state.contribs = contribs
        st.session_state.explanation = expl
        prog.progress(70, text="Running deep learning suite...")

        dl = st.session_state.dl_models
        bt, sg = float(battery), float(signal)
        wpf = []
        for wp in wps:
            bt = max(0, bt - drain*(dist/max(len(wps)-1, 1)))
            sg = max(10, sg - 1.5)
            wpf.append({**feats, "battery_pct": bt, "signal_strength_pct": sg})

        dl_mlp = predict_deep_mlp(dl["deep_mlp"]["model"], dl["deep_mlp"]["scaler"], feats)
        dl_lstm = predict_lstm(dl["lstm"]["model"], dl["lstm"]["scaler"], wpf)
        dl_tf = predict_transformer(dl["transformer"]["model"],
                                     dl["transformer"]["scaler"], wpf)
        anom = detect_anomaly(dl["autoencoder"]["model"], dl["autoencoder"]["scaler"],
                               dl["autoencoder"]["threshold"], feats)
        st.session_state.dl_preds = {"mlp": dl_mlp, "lstm": dl_lstm, "transformer": dl_tf}
        st.session_state.anomaly = anom
        prog.progress(85, text="Evaluating alerts...")

        alrts = evaluate_alerts(float(battery), avg_wind, float(signal), float(payload),
                                 dist, avg_temp, pred["risk_score"], float(altitude),
                                 float(w_src["humidity"]))
        ready = compute_readiness(pred["risk_score"], alrts, len(nfz_conf),
                                   w_src["uav_weather_risk"]["composite"])
        comp_check = check_compliance(feats)
        sitrep = generate_sitrep(mission_id=st.session_state.mission_id, source=sname,
                                  destination=dname, distance_km=dist, bearing=bear,
                                  compass=comp, risk_score=pred["risk_score"],
                                  risk_level_s=pred["level"], alerts=alrts,
                                  nfz_conflicts=nfz_conf, weather=w_src, readiness=ready)

        st.session_state.alerts = alrts
        st.session_state.readiness = ready
        st.session_state.sitrep = sitrep
        st.session_state.compliance = comp_check
        st.session_state.analysis_done = True
        prog.progress(100, text="Analysis complete!")
        st.rerun()

    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

# ============================================================
# REMAINING TABS  (only populated once analysis is done)
# ============================================================
if st.session_state.analysis_done:
    pred = st.session_state.prediction
    feats = st.session_state.features
    alrts = st.session_state.alerts
    ready = st.session_state.readiness
    w_src = st.session_state.weather_src
    w_dst = st.session_state.weather_dst
    dist_km = st.session_state.distance_km
    wps = st.session_state.waypoints
    nfz_list = st.session_state.nfz_list
    nfz_conf = st.session_state.nfz_conflicts
    dl_preds = st.session_state.dl_preds
    anom = st.session_state.anomaly
    src = st.session_state.src_coords
    dst = st.session_state.dst_coords
    tlog = st.session_state.telemetry_log
    ft = st.session_state.ft_est
    dl = st.session_state.dl_models

    with tabs[1]:
        # ---- instrument row: horizon display (left) + live map (right) ----
        _speed_ms = (dist_km / max(ft["flight_time_min"], 0.1)) * 1000.0 / 60.0
        _armed = bool(st.session_state.sim_running or tlog)
        h_col, m_col = st.columns([1, 1.25], gap="small")
        with h_col:
            html_frame(
                hud_page(heading_deg=st.session_state.bearing, altitude_m=feats["altitude_m"],
                         speed_ms=_speed_ms, battery_pct=feats["battery_pct"],
                         signal_pct=feats["signal_strength_pct"], armed=_armed,
                         mode="AUTO" if _armed else "STANDBY", simulated=True,
                         risk_pct=pred["risk_score"], alt_limit=400),
                440)
        with m_col:
            if FOLIUM_OK:
                _info = [f"Distance: {dist_km:.2f} km",
                         f"Bearing: {st.session_state.bearing:.0f} deg {st.session_state.compass}"]
                st_folium(build_map(src, dst, wps, nfz_list, nfz_conf, tlog or None, info=_info),
                          width=None, height=440, returned_objects=[], key="flight_data_map")

        # ---- dials ----
        html_frame(dials_page([
            dict(value=_speed_ms, vmin=0, vmax=30, label="Speed", unit="m/s"),
            dict(value=feats["altitude_m"], vmin=0, vmax=400, label="Altitude", unit="m AGL",
                 good_below=300, bad_above=380),
            dict(value=feats["battery_pct"], vmin=0, vmax=100, label="Battery", unit="%",
                 low_is_bad=True, low_warn=35, low_bad=20),
            dict(value=feats["signal_strength_pct"], vmin=0, vmax=100, label="Link", unit="%",
                 low_is_bad=True, low_warn=35, low_bad=20),
            dict(value=feats["wind_speed_mps"], vmin=0, vmax=25, label="Wind", unit="m/s",
                 good_below=8, bad_above=15, fmt="{:.1f}"),
            dict(value=pred["risk_score"], vmin=0, vmax=100, label="Risk", unit="%",
                 good_below=35, bad_above=60),
        ]), 170)

        st.markdown(status_html(pred), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        entries = [
            (f"{dist_km:.1f} km", "Distance", "#1a5fb4"),
            (f"{feats['battery_pct']:.0f}%", "Battery",
             "#3fa33f" if feats["battery_pct"] > 40 else "#c23b3b"),
            (f"{feats['wind_speed_mps']:.1f} m/s", "Wind",
             "#d69f00" if feats["wind_speed_mps"] > 8 else "#3fa33f"),
            (f"{feats['payload_kg']:.1f} kg", "Payload", "#c9d1d6"),
            (f"{feats['signal_strength_pct']:.0f}%", "Signal",
             "#c23b3b" if feats["signal_strength_pct"] < 35 else "#1a5fb4"),
            (f"{ft['flight_time_min']:.0f} min", "ETA", "#1a5fb4"),
        ]
        for col, (val, lbl, hx) in zip([c1, c2, c3, c4, c5, c6], entries):
            with col:
                st.markdown(metric(val, lbl, hx), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        gc1, gc2 = st.columns(2)
        with gc1:
            st.markdown('<div class="gcard-hdr">SOURCE WEATHER - '
                        f'{st.session_state.src_name[:35]}</div>', unsafe_allow_html=True)
            uav_c = "#c23b3b" if w_src["uav_weather_risk"]["composite"] > 40 else "#3fa33f"
            st.markdown(
                f'<div class="gcard">'
                f'Temp: {w_src["temperature"]}C | '
                f'Wind: {w_src["wind_speed"]} m/s {w_src["wind_compass"]} | '
                f'Gust: {w_src["wind_gust"]} m/s<br>'
                f'Humidity: {w_src["humidity"]}% | '
                f'Visibility: {w_src["visibility_km"]} km<br>'
                f'Condition: {w_src["description"]} | '
                f'Beaufort F{w_src["beaufort_force"]}<br>'
                f'<span style="color:{uav_c}">UAV Risk: '
                f'{w_src["uav_weather_risk"]["composite"]:.0f}%</span>'
                f'<div style="font-size:10px;color:#999;margin-top:4px">'
                f'{w_src["source"]} - {w_src["fetch_time"]}</div></div>',
                unsafe_allow_html=True)
        with gc2:
            st.markdown('<div class="gcard-hdr">DESTINATION WEATHER - '
                        f'{st.session_state.dst_name[:35]}</div>', unsafe_allow_html=True)
            uav_c2 = "#c23b3b" if w_dst["uav_weather_risk"]["composite"] > 40 else "#3fa33f"
            st.markdown(
                f'<div class="gcard">'
                f'Temp: {w_dst["temperature"]}C | '
                f'Wind: {w_dst["wind_speed"]} m/s {w_dst["wind_compass"]} | '
                f'Gust: {w_dst["wind_gust"]} m/s<br>'
                f'Humidity: {w_dst["humidity"]}% | '
                f'Visibility: {w_dst["visibility_km"]} km<br>'
                f'Condition: {w_dst["description"]} | '
                f'Beaufort F{w_dst["beaufort_force"]}<br>'
                f'<span style="color:{uav_c2}">UAV Risk: '
                f'{w_dst["uav_weather_risk"]["composite"]:.0f}%</span>'
                f'<div style="font-size:10px;color:#999;margin-top:4px">'
                f'{w_dst["source"]} - {w_dst["fetch_time"]}</div></div>',
                unsafe_allow_html=True)

        st.markdown('<div class="gcard-hdr">PRE-FLIGHT ALERTS</div>', unsafe_allow_html=True)
        if alrts:
            for a in alrts:
                st.markdown(alert_line(a), unsafe_allow_html=True)
        else:
            st.markdown('<div class="al-ok">All systems nominal - cleared for launch</div>',
                        unsafe_allow_html=True)

        st.markdown('<div class="gcard-hdr">SITUATION REPORT</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="sitrep">{st.session_state.sitrep}</div>',
                    unsafe_allow_html=True)

    with tabs[2]:
        st.markdown('<div class="gcard-hdr">UAV WEATHER GAUGES</div>', unsafe_allow_html=True)
        wg1, wg2, wg3, wg4 = st.columns(4)
        for col, (v, mn, mx, lbl, unit, w, d) in zip([wg1, wg2, wg3, wg4], [
            (w_src["temperature"], -5, 45, "Temp", "C", 35, 40),
            (w_src["wind_speed"], 0, 25, "Wind", "m/s", 8, 15),
            (w_src["humidity"], 0, 100, "Humidity", "%", 70, 90),
            (w_src["visibility_km"], 0, 15, "Visibility", "km", 5, 3),
        ]):
            with col:
                st.image(draw_gauge(v, mn, mx, lbl, unit, w, d), use_container_width=True)

        st.markdown('<div class="gcard-hdr">48-HOUR FORECAST</div>', unsafe_allow_html=True)
        fcast = st.session_state.forecast
        if fcast:
            df_fc = pd.DataFrame(fcast[:16])
            df_fc.columns = [c.title() for c in df_fc.columns]
            st.dataframe(df_fc, use_container_width=True, hide_index=True)

    with tabs[3]:
        n1, n2, n3, n4 = st.columns(4)
        prohibited = sum(1 for n in nfz_list if n["severity"] == "prohibited")
        for col, (v, lbl, hx) in zip([n1, n2, n3, n4], [
            (len(nfz_list), "Total NFZ", "#d69f00"),
            (len(nfz_conf), "Conflicts", "#c23b3b" if nfz_conf else "#3fa33f"),
            (prohibited, "Prohibited", "#c23b3b"),
            (sum(1 for n in nfz_list if n["severity"] == "restricted"),
             "Restricted", "#d69f00"),
        ]):
            with col:
                st.markdown(metric(str(v), lbl, hx), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        for nfz in nfz_list:
            conflict = any(c["nfz_id"] == nfz["id"] for c in nfz_conf)
            st.markdown(
                f'<div class="gcard">'
                f'<b>{nfz["id"]} - {nfz["name"]}</b> '
                f'({nfz["severity"].upper()})<br>'
                f'Lat: {nfz["lat"]} | Lon: {nfz["lon"]} | '
                f'Radius: {nfz["radius_km"]} km'
                f'{"<div class=al-crit>Route conflict - reroute required</div>" if conflict else ""}'
                f'</div>', unsafe_allow_html=True)
        if not nfz_conf:
            st.markdown('<div class="al-ok">No route conflicts - all waypoints clear</div>',
                        unsafe_allow_html=True)

        st.markdown('<div class="gcard-hdr">DGCA COMPLIANCE</div>', unsafe_allow_html=True)
        cc = st.session_state.compliance
        if cc:
            for c in cc:
                cls = "al-crit" if c["severity"] == "violation" else "al-warn"
                st.markdown(f'<div class="{cls}">{c["rule"]}: {c["desc"]}</div>',
                            unsafe_allow_html=True)
        else:
            st.markdown('<div class="al-ok">No regulatory violations</div>',
                        unsafe_allow_html=True)

    with tabs[4]:
        a1, a2 = st.columns([1, 2])
        with a1:
            st.image(draw_gauge(pred["risk_score"], 0, 100, "Risk", "%", 35, 60),
                     use_container_width=True)
            st.progress(pred["safe_score"]/100, text=f"Safe {pred['safe_score']}%")
            st.progress(pred["risk_score"]/100, text=f"Risk {pred['risk_score']}%")
        with a2:
            fi = draw_fi(st.session_state.ml_meta.get("feature_importance", {}))
            if fi:
                st.image(fi, use_container_width=True)

        st.markdown('<div class="gcard-hdr">AI EXPLANATION</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="gcard">'
                    f'{st.session_state.explanation.replace(chr(10), "<br>")}</div>',
                    unsafe_allow_html=True)

        e1, e2, e3 = st.columns(3)
        for col, (nm, spec, wt) in zip([e1, e2, e3], [
            ("Random Forest", "n=300, depth=15", "37.5%"),
            ("Gradient Boosting", "n=200, lr=0.05", "28.6%"),
            ("Extra Trees", "n=250, depth=14", "33.9%"),
        ]):
            with col:
                st.markdown(metric(wt, nm), unsafe_allow_html=True)

    with tabs[5]:
        if simulate_btn and not st.session_state.sim_running:
            st.session_state.sim_running = True
            st.session_state.sim_done = False
            st.session_state.telemetry_log = []

        if st.session_state.sim_running:
            prg = st.progress(0, text="Starting simulation...")
            status_ph = st.empty()
            chart_ph = st.empty()
            alert_ph = st.empty()

            drain = feats["battery_drain_rate"]
            seg_dist = dist_km / max(len(wps)-1, 1)
            cur_b, cur_s = feats["battery_pct"], feats["signal_strength_pct"]

            for i, wp in enumerate(wps):
                cur_b = max(0, cur_b - drain*seg_dist)
                cur_s = max(10, cur_s - 1.5)
                wx = get_weather(wp[0], wp[1])
                sf = {**feats, "battery_pct": cur_b, "signal_strength_pct": cur_s,
                      "wind_speed_mps": wx["wind_speed"], "temperature_c": wx["temperature"],
                      "humidity_pct": wx["humidity"]}
                sp = predict_risk(st.session_state.ml_model, st.session_state.ml_scaler, sf)
                entry = {"step": i+1, "position": wp, "battery": round(cur_b, 1),
                         "wind": wx["wind_speed"], "signal": round(cur_s, 1),
                         "temperature": wx["temperature"], "risk_score": sp["risk_score"],
                         "level": sp["level"], "weather": wx["description"],
                         "lat": wp[0], "lon": wp[1]}
                st.session_state.telemetry_log.append(entry)

                pct = int((i+1)/len(wps)*100)
                prg.progress(pct, text=f"Waypoint {i+1}/{len(wps)}")
                status_ph.markdown(
                    f'<div class="gcard">'
                    f'<b>WP {i+1:02d}/{len(wps):02d}</b> - {sp["label"]}<br>'
                    f'Battery: {cur_b:.1f}% | Wind: {wx["wind_speed"]} m/s | '
                    f'Temp: {wx["temperature"]}C | Signal: {cur_s:.0f}% | '
                    f'Risk: {sp["risk_score"]:.1f}%</div>', unsafe_allow_html=True)

                step_al = evaluate_alerts(cur_b, wx["wind_speed"], cur_s,
                                           feats["payload_kg"], dist_km,
                                           wx["temperature"], sp["risk_score"])
                with alert_ph.container():
                    for a in step_al[:2]:
                        st.markdown(alert_line(a), unsafe_allow_html=True)

                if len(st.session_state.telemetry_log) >= 2:
                    ci = draw_telemetry(st.session_state.telemetry_log)
                    if ci:
                        chart_ph.image(ci, use_container_width=True)
                time.sleep(0.3)

            st.session_state.sim_running = False
            st.session_state.sim_done = True
            st.rerun()

        elif st.session_state.sim_done and tlog:
            st.success(f"Simulation complete - {len(tlog)} waypoints")
            fb = tlog[-1]["battery"]
            pr = max(t["risk_score"] for t in tlog)
            aw = sum(t["wind"] for t in tlog) / len(tlog)
            hr = sum(1 for t in tlog if t["risk_score"] >= 60)
            s1, s2, s3, s4 = st.columns(4)
            for col, (v, lbl, hx) in zip([s1, s2, s3, s4], [
                (f"{fb:.1f}%", "Final Battery", "#3fa33f" if fb > 25 else "#c23b3b"),
                (f"{pr:.1f}%", "Peak Risk", "#c23b3b" if pr >= 60 else "#3fa33f"),
                (f"{aw:.1f} m/s", "Avg Wind", "#d69f00"),
                (str(hr), "High Risk WPs", "#c23b3b" if hr > 0 else "#3fa33f"),
            ]):
                with col:
                    st.markdown(metric(v, lbl, hx), unsafe_allow_html=True)
            tc = draw_telemetry(tlog)
            if tc:
                st.image(tc, use_container_width=True)
            with st.expander("Full telemetry log"):
                df_tl = pd.DataFrame([{k: v for k, v in t.items() if k != "position"}
                                       for t in tlog])
                st.dataframe(df_tl, use_container_width=True)
        else:
            st.info("Press RUN SIMULATION on the Flight Plan tab to begin.")

    with tabs[6]:
        d1, d2, d3, d4 = st.columns(4)
        for col, name, meta_d, dpred, arch in [
            (d1, "Deep Residual MLP", dl["deep_mlp"]["meta"], dl_preds["mlp"],
             "10-256-[ResBlock x4]-64-1"),
            (d2, "BiLSTM + Attention", dl["lstm"]["meta"], dl_preds["lstm"],
             "BiLSTM(2L,h=64)+AttnPool"),
            (d3, "Transformer", dl["transformer"]["meta"], dl_preds["transformer"],
             "3L x 4heads x d=64"),
            (d4, "Autoencoder", dl["autoencoder"]["meta"], None,
             "10-16-8-4-8-16-10"),
        ]:
            with col:
                acc = meta_d.get("accuracy", "-")
                n = meta_d.get("n_params", 0)
                rv = (f"{dpred['risk_score']:.1f}%" if dpred else
                      f"{anom['anomaly_score']:.1f}/10")
                st.markdown(
                    f'<div class="gcard"><b>{name}</b><br>'
                    f'<span style="font-size:18px;font-weight:700">{rv}</span><br>'
                    f'<span style="font-size:10.5px;color:#777">'
                    f'Acc: {acc}% | {n:,} params<br>{arch}</span></div>',
                    unsafe_allow_html=True)

        st.markdown('<div class="gcard-hdr">LSTM ATTENTION WEIGHTS</div>',
                    unsafe_allow_html=True)
        attn = dl_preds["lstm"].get("attention_weights", [])
        if attn:
            st.image(draw_attn(attn), use_container_width=True)
            mc = dl_preds["lstm"].get("most_critical_waypoint", 0)
            st.markdown(f'<div class="al-warn">LSTM focus: Waypoint {mc+1} '
                        f'(most critical point in route)</div>', unsafe_allow_html=True)

        st.markdown('<div class="gcard-hdr">TRANSFORMER PER-WAYPOINT RISK</div>',
                    unsafe_allow_html=True)
        per_wp = dl_preds["transformer"].get("per_waypoint_risk", [])
        worst = dl_preds["transformer"].get("worst_waypoint", 0)
        if per_wp:
            st.image(draw_wp_risk(per_wp, worst), use_container_width=True)
            st.markdown(f'<div class="al-crit">Highest risk: WP{worst+1} '
                        f'({per_wp[worst]:.1f}%)</div>', unsafe_allow_html=True)

        st.markdown('<div class="gcard-hdr">AUTOENCODER ANOMALY DETECTION</div>',
                    unsafe_allow_html=True)
        ac1, ac2, ac3, ac4 = st.columns(4)
        for col, (v, lbl) in zip([ac1, ac2, ac3, ac4], [
            (f"{anom['anomaly_score']:.2f}/10", "Anomaly Score"),
            (f"{anom['reconstruction_error']:.4f}", "Recon Error"),
            (f"{anom['threshold']:.4f}", "Threshold"),
            ("Anomaly" if anom["is_anomaly"] else "Normal", "Verdict"),
        ]):
            with col:
                st.markdown(metric(v, lbl), unsafe_allow_html=True)
        cls = "al-crit" if anom["is_anomaly"] else "al-ok"
        st.markdown(f'<div class="{cls}">{anom["message"]}</div>', unsafe_allow_html=True)

        st.markdown('<div class="gcard-hdr">TRAINING CURVES</div>', unsafe_allow_html=True)
        tc1, tc2 = st.columns(2)
        for col, (key, title) in zip([tc1, tc2], [
            ("deep_mlp", "Deep Residual MLP"), ("lstm", "Bidirectional LSTM")]):
            with col:
                hist = dl[key]["meta"].get("history", {})
                if hist:
                    st.image(draw_curves(hist, title), use_container_width=True)

    with tabs[7]:
        elapsed = time.time() - (st.session_state.mission_start or time.time())
        summ = {
            "Mission ID": st.session_state.mission_id,
            "Timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "Source": st.session_state.src_name,
            "Destination": st.session_state.dst_name,
            "Distance": f"{dist_km:.1f} km",
            "Bearing": f"{st.session_state.bearing:.0f} deg {st.session_state.compass}",
            "AI Risk": f"{pred['risk_score']:.1f}% - {pred['level']}",
            "ML Accuracy": f"{ml_acc}%",
            "Readiness": f"{ready['readiness_score']:.0f}/100",
            "Verdict": ready["verdict"],
            "NFZ Conflicts": len(nfz_conf),
            "Weather Source": w_src["source"],
            "Mission Type": mission_type,
            "Elapsed": f"{elapsed:.0f}s",
        }
        if st.session_state.sim_done and tlog:
            summ["Final Battery"] = f"{tlog[-1]['battery']:.1f}%"
            summ["Peak Risk"] = f"{max(t['risk_score'] for t in tlog):.1f}%"

        st.dataframe(pd.DataFrame([(k, str(v)) for k, v in summ.items()], columns=["Parameter", "Value"]),
                     use_container_width=True, hide_index=True)

        e1, e2, e3 = st.columns(3)
        if tlog:
            csv_b = pd.DataFrame([{k: v for k, v in t.items() if k != "position"}
                                   for t in tlog]).to_csv(index=False).encode()
            with e1:
                st.download_button("Download Telemetry CSV", csv_b,
                                   f"{st.session_state.mission_id}_telemetry.csv",
                                   "text/csv", use_container_width=True)
        mj = json.dumps({"mission": summ, "features": feats, "prediction": pred,
                         "weather_src": w_src, "nfz": nfz_list,
                         "telemetry": [{k: v for k, v in t.items() if k != "position"}
                                       for t in tlog],
                         "sitrep": st.session_state.sitrep}, indent=2, default=str)
        with e2:
            st.download_button("Download Mission JSON", mj.encode(),
                               f"{st.session_state.mission_id}_mission.json",
                               "application/json", use_container_width=True)
        with e3:
            st.download_button("Download SITREP TXT", st.session_state.sitrep.encode(),
                               f"{st.session_state.mission_id}_sitrep.txt",
                               "text/plain", use_container_width=True)

        st.markdown('<div class="gcard-hdr">MODEL PERFORMANCE</div>', unsafe_allow_html=True)
        ml_m = st.session_state.ml_meta
        p1, p2, p3, p4 = st.columns(4)
        for col, (v, lbl) in zip([p1, p2, p3, p4], [
            (f"{ml_m['accuracy']:.1f}%", "ML Accuracy"),
            (f"{ml_m['auc_roc']:.1f}%", "AUC-ROC"),
            (f"{ml_m['f1_score']:.1f}%", "F1 Score"),
            (f"{ml_m['n_samples']:,}", "Train Samples"),
        ]):
            with col:
                st.markdown(metric(v, lbl), unsafe_allow_html=True)

    # -------------------- TAB 8: TERRAIN & RTH --------------------
    with tabs[8]:
        st.markdown('<div class="gcard-hdr">TERRAIN ELEVATION PROFILE</div>',
                    unsafe_allow_html=True)

        elevations, terrain_source = get_elevation_profile(wps)
        clearance_data = check_terrain_clearance(wps, elevations, altitude)
        terrain_alerts = get_terrain_alerts(clearance_data)
        terrain_summary = get_max_terrain_risk_summary(clearance_data)

        if terrain_source == "LIVE":
            st.markdown(
            '<div class="al-ok">✅ LIVE elevation data (Open-Elevation API) '
            '— terrain results below are real.</div>',
            unsafe_allow_html=True)
        else:
            st.markdown(
                '<div class="al-crit">⚠️ Elevation API unreachable — showing '
                'SIMULATED terrain (NOT real data). Do not trust the collision '
                'results below for actual flight planning. Check your internet '
                'connection and re-run analysis.</div>',
                unsafe_allow_html=True)

        tc1, tc2, tc3, tc4 = st.columns(4)
        for col, (v, lbl, hx) in zip([tc1, tc2, tc3, tc4], [
            (f"{terrain_summary['min_clearance']:.0f} m" if terrain_summary['min_clearance'] is not None else "N/A",
             "Min Clearance", "#c23b3b" if (terrain_summary['min_clearance'] or 999) < 30 else "#3fa33f"),
            (str(terrain_summary['collision_count']), "Collisions",
             "#c23b3b" if terrain_summary['collision_count'] > 0 else "#3fa33f"),
            (str(terrain_summary['risk_count']), "Low Clearance WPs",
             "#d69f00" if terrain_summary['risk_count'] > 0 else "#3fa33f"),
            (f"WP{(terrain_summary['worst_waypoint'] or 0)+1}", "Worst Point", "#444"),
        ]):
            with col:
                st.markdown(metric(v, lbl, hx), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        fig, ax = plt.subplots(figsize=(9, 3), facecolor="white")
        ax.set_facecolor("#fafafa")
        wp_indices = list(range(1, len(wps)+1))
        ground_line = elevations
        drone_line = [elevations[0] + altitude] * len(wps)
        ax.fill_between(wp_indices, ground_line, color="#8a6d3b", alpha=0.4, label="Terrain")
        ax.plot(wp_indices, drone_line, color="#1a5fb4", lw=2.5, label="Drone Altitude")
        for c in clearance_data:
            if c["is_collision"]:
                ax.scatter([c["waypoint_index"]+1], [c["drone_altitude_m"]],
                          color="red", s=100, zorder=5, marker="x")
        ax.set_xlabel("Waypoint")
        ax.set_ylabel("Elevation (m)")
        ax.legend()
        ax.grid(alpha=0.3)
        for sp in ax.spines.values():
            sp.set_color("#ccc")
        st.pyplot(fig)
        plt.close(fig)

        if terrain_alerts:
            for a in terrain_alerts:
                cls = "al-crit" if a["level"] == "critical" else "al-warn"
                st.markdown(f'<div class="{cls}">{a["message"]}<br>'
                           f'<span style="color:#888">→ {a["action"]}</span></div>',
                           unsafe_allow_html=True)
        else:
            st.markdown('<div class="al-ok">Terrain clearance safe at all waypoints</div>',
                        unsafe_allow_html=True)

        st.markdown('<div class="gcard-hdr">INTELLIGENT RETURN-TO-HOME</div>',
                    unsafe_allow_html=True)

        mid_idx = len(wps) // 2
        current_pos = wps[mid_idx]
        current_batt_for_rth = max(10, feats["battery_pct"] - mid_idx * 3)

        contingency = full_contingency_check(
            current_pos[0], current_pos[1],
            src[0], src[1], dst[0], dst[1],
            current_batt_for_rth, feats["battery_drain_rate"])

        rth = contingency["rth"]
        r1, r2, r3 = st.columns(3)
        for col, (v, lbl, hx) in zip([r1, r2, r3], [
            ("FEASIBLE" if rth["feasible"] else "NOT FEASIBLE", "RTH Status",
             "#3fa33f" if rth["feasible"] else "#c23b3b"),
            (rth["confidence"], "Confidence", "#1a5fb4"),
            (f"{rth['distance_home_km']} km", "Distance Home", "#444"),
        ]):
            with col:
                st.markdown(metric(v, lbl, hx), unsafe_allow_html=True)

        st.markdown(f'<div class="gcard">{rth["verdict"]}<br>'
                   f'Battery needed: {rth["battery_needed_pct"]}% | '
                   f'Bearing home: {rth["bearing_home"]:.0f}° {rth["compass_home"]}</div>',
                   unsafe_allow_html=True)

        if contingency["emergency"]:
            em = contingency["emergency"]
            cls = "al-ok" if em["found"] else "al-crit"
            st.markdown(f'<div class="{cls}">{em["message"]}</div>', unsafe_allow_html=True)
            if em["all_zones"]:
                df_zones = pd.DataFrame(em["all_zones"])
                st.dataframe(df_zones, use_container_width=True, hide_index=True)

        st.markdown('<div class="gcard-hdr">GPS-DENIAL RESILIENCE SIMULATION</div>',
                    unsafe_allow_html=True)
        jam_wp = st.slider("Simulate jamming starting at waypoint", 0, len(wps)-1, len(wps)-4,
                           key="jam_slider")

        gps_rows = []
        steps_without_gps = 0
        for i in range(len(wps)):
            gps_status = simulate_gps_event(i, len(wps), seed=100+i, force_jam_at=jam_wp)
            penalty = gps_risk_penalty(gps_status)
            reliable = gps_status["reliable"]
            if not reliable:
                steps_without_gps += 1
            else:
                steps_without_gps = 0
            gps_rows.append({
                "WP": i+1, "Satellites": gps_status["satellites"],
                "Quality": gps_status["quality"].upper(),
                "HDOP": gps_status["hdop"],
                "Reliable": "Yes" if reliable else "NO",
                "Risk Penalty": f"+{penalty}",
            })
        st.dataframe(pd.DataFrame(gps_rows), use_container_width=True, hide_index=True)

        gps_alerts_found = [r for r in gps_rows if r["Reliable"] == "NO"]
        if gps_alerts_found:
            st.markdown(f'<div class="al-crit">GPS unreliable for '
                       f'{len(gps_alerts_found)} waypoint(s) starting at WP{jam_wp+1} — '
                       f'system would switch to dead-reckoning navigation</div>',
                       unsafe_allow_html=True)
        else:
            st.markdown('<div class="al-ok">GPS reliable throughout entire route</div>',
                        unsafe_allow_html=True)

    # -------------------- TAB 9: SWARM --------------------
    with tabs[9]:
        st.markdown('<div class="gcard-hdr">MULTI-UAV SWARM COORDINATION</div>',
                    unsafe_allow_html=True)
        st.info("Demonstration mode: simulates 2 additional UAV missions alongside "
                "your analysed mission to test cross-drone conflict detection.")

        mid = len(wps) // 2
        offset_wps_b = []
        for i, (lat, lon) in enumerate(wps):
            if abs(i - mid) <= 2:
                blend = 1 - (abs(i - mid) / 3.0)
                offset_wps_b.append((
                    lat + 0.0015 * (1 - blend),
                    lon - 0.0012 * (1 - blend),
                ))
            else:
                offset_wps_b.append((lat + 0.02, lon - 0.015))

        offset_wps_c = [(lat - 0.08, lon + 0.06) for lat, lon in wps]

        swarm_drones = {
            "Drone-A (Primary)": {"waypoints": wps, "risk_score": pred["risk_score"]},
            "Drone-B (Escort)": {"waypoints": offset_wps_b, "risk_score": pred["risk_score"] * 1.3},
            "Drone-C (Recon)": {"waypoints": offset_wps_c, "risk_score": pred["risk_score"] * 0.7},
        }

        swarm_result = check_swarm_conflicts(swarm_drones, min_safe_separation_km=0.5)

        s1, s2, s3, s4 = st.columns(4)
        for col, (v, lbl, hx) in zip([s1, s2, s3, s4], [
            (str(swarm_result["n_drones"]), "UAVs Active", "#1a5fb4"),
            (str(swarm_result["n_conflicts"]), "Total Conflicts",
             "#c23b3b" if swarm_result["n_conflicts"] > 0 else "#3fa33f"),
            (str(swarm_result["n_critical_conflicts"]), "Critical Conflicts",
             "#c23b3b" if swarm_result["n_critical_conflicts"] > 0 else "#3fa33f"),
            (f"{swarm_result['max_individual_risk']:.1f}%", "Max Individual Risk", "#d69f00"),
        ]):
            with col:
                st.markdown(metric(v, lbl, hx), unsafe_allow_html=True)

        st.markdown(f'<div class="gcard"><b>Swarm Verdict:</b> '
                   f'{swarm_result["swarm_verdict"]}</div>', unsafe_allow_html=True)

        if FOLIUM_OK:
            cx = sum(w[0] for w in wps) / len(wps)
            cy = sum(w[1] for w in wps) / len(wps)
            swarm_map = folium.Map(location=[cx, cy], zoom_start=8, tiles="OpenStreetMap")
            colors_map = {"Drone-A (Primary)": "blue", "Drone-B (Escort)": "green",
                         "Drone-C (Recon)": "purple"}
            for name, data in swarm_drones.items():
                folium.PolyLine([[w[0], w[1]] for w in data["waypoints"]],
                               color=colors_map.get(name, "gray"), weight=3,
                               opacity=0.8, tooltip=name).add_to(swarm_map)
                folium.Marker(data["waypoints"][0],
                             icon=folium.Icon(color=colors_map.get(name, "gray"), icon="rocket", prefix="fa"),
                             popup=name).add_to(swarm_map)
            st_folium(swarm_map, width=None, height=420, returned_objects=[])

        st.markdown('<div class="gcard-hdr">CONFLICT LOG</div>', unsafe_allow_html=True)
        if swarm_result["conflicts"]:
            for c in swarm_result["conflicts"][:10]:
                alert = conflict_to_alert(c)
                cls = "al-crit" if alert["level"] == "critical" else "al-warn"
                st.markdown(f'<div class="{cls}">{alert["message"]}<br>'
                           f'<span style="color:#888">→ {alert["action"]}</span></div>',
                           unsafe_allow_html=True)
        else:
            st.markdown('<div class="al-ok">No conflicts detected between UAVs in swarm</div>',
                        unsafe_allow_html=True)

else:
    # nothing to show on the other screens until a mission has been analysed
    for _i in range(1, 10):
        with tabs[_i]:
            st.markdown('<div class="al-caut">Run ANALYSE MISSION on the FLIGHT PLAN screen first. '
                        'This screen fills in after the analysis.</div>', unsafe_allow_html=True)
