"""
place_search.py - search-as-you-type place lookup, like the search box in a maps app.

What it does
  * Suggests towns, villages and areas as you type ("ban" -> Bengaluru, Bannerghatta ...)
  * Puts places NEAR you first and shows how far each one is
  * Can hide anything farther than 100 km (this system is built for short delivery flights)
  * Forgives spelling mistakes ("yelhanka", "Banglore", "hebal")
  * Asks its sources at the same time, so it answers in about one round trip

Sources: Photon (OpenStreetMap, built for typing-as-you-search), Open-Meteo geocoding,
and a short built-in list so the box still works with no internet.
"""
import difflib
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait

import requests

_PHOTON = "https://photon.komoot.io/api/"
_METEO = "https://geocoding-api.open-meteo.com/v1/search"
_TIMEOUT = 2.0          # seconds; a slow source is simply skipped
_DOWN_FOR = 45          # after a failure, skip that source for this many seconds
_MIN_ONLINE = 3         # letters needed before asking the internet (2 letters use the offline list)
_CACHE_SECONDS = 600
_HEADERS = {"User-Agent": "UAV-Mission-Reliability-Student-Project/1.0"}

# one shared connection pool: no new handshake on every key press
_SESSION = requests.Session()
_SESSION.headers.update(_HEADERS)
_SESSION.mount("https://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=8))
_POOL = ThreadPoolExecutor(max_workers=8)

_FIXES = {
    "banglore": "bangalore", "bangalor": "bangalore", "bengalore": "bengaluru",
    "bangaluru": "bengaluru", "mumbay": "mumbai", "dilli": "delhi", "calcutta": "kolkata",
    "madras": "chennai", "poona": "pune", "mysuru": "mysore", "trivandrum": "thiruvananthapuram",
}

# (label, lat, lon, extra search words)  - offline fallback only
_BUILTIN = [
    ("Bengaluru, Karnataka, India", 12.9716, 77.5946, "bangalore banglore"),
    ("Yelahanka, Bengaluru, Karnataka, India", 13.1007, 77.5963, "bangalore"),
    ("Hebbal, Bengaluru, Karnataka, India", 13.0358, 77.5970, "bangalore"),
    ("Bannerghatta, Bengaluru, Karnataka, India", 12.8000, 77.5770, "bannerughatta"),
    ("Banashankari, Bengaluru, Karnataka, India", 12.9255, 77.5468, ""),
    ("Devanahalli, Karnataka, India", 13.2437, 77.7126, ""),
    ("Doddaballapura, Karnataka, India", 13.2957, 77.5378, "doddaballapur"),
    ("Kolar, Karnataka, India", 13.1367, 78.1292, ""),
    ("Mysuru, Karnataka, India", 12.2958, 76.6394, "mysore"),
    ("Banswara, Rajasthan, India", 23.5461, 74.4350, ""),
    ("Banda, Uttar Pradesh, India", 25.4800, 80.3360, ""),
    ("Mumbai, Maharashtra, India", 19.0760, 72.8777, "bombay"),
    ("Pune, Maharashtra, India", 18.5204, 73.8567, "poona"),
    ("Delhi, India", 28.6139, 77.2090, "new delhi"),
    ("Hyderabad, Telangana, India", 17.3850, 78.4867, ""),
    ("Chennai, Tamil Nadu, India", 13.0827, 80.2707, "madras"),
    ("Srinagar, Jammu and Kashmir, India", 34.0837, 74.7973, ""),
    ("Gulmarg, Jammu and Kashmir, India", 34.0484, 74.3805, ""),
]

_COORD_RE = re.compile(r"^\s*-?\d{1,3}(\.\d+)?\s*,\s*-?\d{1,3}(\.\d+)?\s*$")

# every place the app has shown so far; lets us fix a typo against names we already know
_SEEN = {}

_DOWN = {}      # source name -> time until which we skip it
_CACHE = {}     # (query, bias, radius) -> (time, results, sources)

# what the last search did, so the app can show it under the box
STATUS = {"query": "", "sources": [], "n": 0, "note": ""}


def looks_like_coords(text):
    """True for text such as '12.9716, 77.5946'."""
    return bool(text) and bool(_COORD_RE.match(str(text)))


def km_between(a, b):
    """Great-circle distance in km between (lat, lon) pairs."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _fix_spelling(q):
    return "".join(_FIXES.get(w.lower(), w) for w in re.split(r"(\W+)", q))


def _join(*parts):
    seen, out = set(), []
    for p in parts:
        p = (p or "").strip()
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return ", ".join(out)


def _bbox(bias, radius_km):
    lat, lon = bias
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.2))
    return f"{lon - dlon:.4f},{lat - dlat:.4f},{lon + dlon:.4f},{lat + dlat:.4f}"


def _from_photon(q, limit, bias, radius_km):
    params = {"q": q, "limit": limit, "lang": "en"}
    if bias:
        params.update({"lat": bias[0], "lon": bias[1]})
        if radius_km:
            params["bbox"] = _bbox(bias, radius_km)
    r = _SESSION.get(_PHOTON, params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    hits = []
    for f in r.json().get("features", []):
        p = f.get("properties", {})
        lon, lat = f["geometry"]["coordinates"][:2]
        name = p.get("name") or p.get("street")
        if not name:
            continue
        label = _join(name, p.get("district") or p.get("locality"), p.get("city"),
                      p.get("county") if not p.get("city") else None,
                      p.get("state"), p.get("country"))
        hits.append((label, lat, lon))
    return hits


def _from_meteo(q, limit):
    r = _SESSION.get(_METEO, params={"name": q, "count": limit, "language": "en", "format": "json"},
                     timeout=_TIMEOUT)
    r.raise_for_status()
    return [(_join(p.get("name"), p.get("admin2"), p.get("admin1"), p.get("country")),
             p["latitude"], p["longitude"]) for p in (r.json().get("results") or [])]


def _from_builtin(q):
    ql = q.lower().strip()
    out = []
    for label, lat, lon, extra in _BUILTIN:
        words = (label.lower() + " " + extra).replace(",", " ").split()
        if any(w.startswith(ql) for w in words):
            out.append((label, lat, lon))
    return out


def _fuzzy_known(q):
    """Fix a typo against names we already know (built-in list + everything shown before)."""
    pool = {l: (la, lo) for l, la, lo, _ in _BUILTIN}
    pool.update({l: v for l, v in _SEEN.items()})
    names = {l.split(",")[0].lower(): l for l in pool}
    close = difflib.get_close_matches(q.lower().split(",")[0].strip(), list(names), n=4, cutoff=0.72)
    return [(names[c], *pool[names[c]]) for c in close]


def _variants(q):
    """Extra queries tried at the same time, to catch typos near the end of the word."""
    first = q.split(",")[0].strip()
    vs = []
    if "," in q and len(first) >= 3:
        vs.append(first)
    if len(first) >= 5:
        vs.append(first[:-1])
    if len(first) >= 7:
        vs.append(first[:-2])
    return vs


def _relevance(q, label):
    ql = q.lower().split(",")[0].strip()
    name = label.split(",")[0].lower()
    if name.startswith(ql):
        return 1.0
    if ql in name:
        return 0.85
    r = max(difflib.SequenceMatcher(None, ql, name[:len(ql) + 1]).ratio(),
            difflib.SequenceMatcher(None, ql, name).ratio())
    return r * 0.9


def _alive(name):
    return time.time() >= _DOWN.get(name, 0)


def _search_cached(q, limit, bias, radius_km):
    key = (q, limit, bias, radius_km)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _CACHE_SECONDS:
        return hit[1], hit[2]

    used, raw, online_ok = [], [], False
    if len(q) >= _MIN_ONLINE:
        jobs = {}
        if _alive("Photon"):
            jobs["Photon"] = _POOL.submit(_from_photon, q, limit * 2, bias, radius_km)
        if _alive("Open-Meteo"):
            jobs["Open-Meteo"] = _POOL.submit(_from_meteo, q, limit)
        variant_jobs = ([_POOL.submit(_from_photon, v, limit, bias, radius_km) for v in _variants(q)]
                        if "Photon" in jobs else [])
        if jobs:
            wait(list(jobs.values()) + variant_jobs, timeout=_TIMEOUT + 0.5)
        for name, fut in jobs.items():
            if fut.done() and not fut.exception():
                _DOWN.pop(name, None)
                online_ok = True
                got = fut.result()
                if got:
                    raw += got
                    used.append(name)
            else:
                _DOWN[name] = time.time() + _DOWN_FOR     # skip a failing source for a while
        for fut in variant_jobs:
            if fut.done() and not fut.exception() and fut.result():
                raw += fut.result()
                if "Photon" not in used:
                    used.append("Photon")

    if len(raw) < 3:
        got = _from_builtin(q) or _fuzzy_known(q)
        if got:
            raw += got
            used.append("offline list")

    scored, seen_xy, seen_label = [], set(), set()
    for label, lat, lon in raw:
        _SEEN[label] = (lat, lon)
        xy = (round(lat, 3), round(lon, 3))
        if xy in seen_xy or label in seen_label:
            continue
        seen_xy.add(xy)
        seen_label.add(label)
        d = km_between(bias, (lat, lon)) if bias else None
        if radius_km and d is not None and d > radius_km:
            continue
        rel = _relevance(q, label)
        if rel < 0.5:
            continue
        score = rel - (0.35 * min(d, 150) / 150 if d is not None else 0)
        scored.append((score, label, lat, lon, d))
    scored.sort(key=lambda t: -t[0])

    out = []
    for score, label, lat, lon, d in scored[:limit]:
        shown = f"{label}  -  {d:.0f} km away" if d is not None else label
        out.append((shown, f"{lat:.6f}, {lon:.6f}"))
    if online_ok:                      # never keep an offline-only answer around
        _CACHE[key] = (time.time(), out, used)
    return out, used


def search_places(query, bias=None, radius_km=None, limit=7):
    """
    [(label, "lat, lon"), ...] for what has been typed so far.
      bias       (lat, lon) of the person: nearer places rank higher and show their distance
      radius_km  hide places farther than this (use None to search everywhere)
    """
    q = (query or "").strip()
    if len(q) < 2:
        return []
    if looks_like_coords(q):
        return [(f"Use coordinates {q}", q)]
    b = (round(bias[0], 2), round(bias[1], 2)) if bias else None
    out, used = _search_cached(_fix_spelling(q), limit, b, radius_km if b else None)
    note = ""
    if not out and radius_km and b:
        note = f"nothing within {radius_km:.0f} km matches '{q}'. Untick the 100 km box to search everywhere."
    STATUS.update({"query": q, "sources": used, "n": len(out), "note": note})
    return out
