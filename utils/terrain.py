"""
terrain.py - Terrain Elevation Awareness for UAV Mission System

Fetches REAL ground elevation data (Open-Elevation API) at every waypoint.
Uses POST (avoids URL length limits on long routes), retries on failure,
longer timeout, and NEVER silently pretends fake data is real - the
caller always knows whether data is LIVE or SIMULATED.
"""

import requests
import random
import time


def get_elevation_profile(waypoints: list, max_retries: int = 3) -> tuple:
    """
    waypoints: list of (lat, lon) tuples
    Returns: (elevations, source) where source is "LIVE" or "SIMULATED"
    """
    url = "https://api.open-elevation.com/api/v1/lookup"
    payload = {
        "locations": [{"latitude": lat, "longitude": lon} for lat, lon in waypoints]
    }

    last_error = None
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, timeout=20)
            response.raise_for_status()
            data = response.json()
            elevations = [round(r["elevation"], 1) for r in data["results"]]
            if len(elevations) != len(waypoints):
                raise ValueError(
                    f"API returned {len(elevations)} elevations for "
                    f"{len(waypoints)} waypoints - mismatched response"
                )
            return elevations, "LIVE"
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(1.5 * (attempt + 1))

    print(f"[terrain.py] Elevation API failed after {max_retries} attempts: {last_error}")
    return _simulate_elevation_profile(waypoints), "SIMULATED"


def _simulate_elevation_profile(waypoints: list) -> list:
    """
    Fallback ONLY - used when the real API is genuinely unreachable.
    Clearly labeled SIMULATED by get_elevation_profile() above.
    """
    seed = int(abs(waypoints[0][0] * 1000) + abs(waypoints[0][1] * 1000)) % 99999
    rng = random.Random(seed)

    base = rng.uniform(100, 800)
    elevations = [base]
    for _ in range(len(waypoints) - 1):
        step = rng.uniform(-40, 40)
        base = max(0, base + step)
        elevations.append(round(base, 1))
    return elevations


def check_terrain_clearance(waypoints: list, elevations: list,
                             planned_altitude_m: float,
                             min_safe_clearance_m: float = 30.0) -> list:
    if not elevations:
        return []

    start_elevation = elevations[0]
    results = []

    for i, (wp, ground_elev) in enumerate(zip(waypoints, elevations)):
        drone_absolute_alt = start_elevation + planned_altitude_m
        clearance = drone_absolute_alt - ground_elev
        is_risk = clearance < min_safe_clearance_m
        is_collision = clearance < 0

        results.append({
            "waypoint_index": i,
            "lat": wp[0], "lon": wp[1],
            "ground_elevation_m": ground_elev,
            "drone_altitude_m": round(drone_absolute_alt, 1),
            "clearance_m": round(clearance, 1),
            "is_risk": is_risk,
            "is_collision": is_collision,
            "recommended_altitude_m": (
                round(planned_altitude_m + (min_safe_clearance_m - clearance), 0)
                if is_risk else planned_altitude_m
            ),
        })

    return results


def get_terrain_alerts(clearance_data: list) -> list:
    alerts = []
    for c in clearance_data:
        if c["is_collision"]:
            alerts.append({
                "level": "critical",
                "message": (
                    f"TERRAIN COLLISION — WP{c['waypoint_index']+1:02d}: "
                    f"Ground {c['ground_elevation_m']:.0f}m, drone at "
                    f"{c['drone_altitude_m']:.0f}m — NEGATIVE CLEARANCE"
                ),
                "action": f"Increase altitude to {c['recommended_altitude_m']:.0f}m minimum",
            })
        elif c["is_risk"]:
            alerts.append({
                "level": "warning",
                "message": (
                    f"LOW TERRAIN CLEARANCE — WP{c['waypoint_index']+1:02d}: "
                    f"Only {c['clearance_m']:.0f}m above ground"
                ),
                "action": f"Recommend increasing altitude to {c['recommended_altitude_m']:.0f}m",
            })
    return alerts


def get_max_terrain_risk_summary(clearance_data: list) -> dict:
    if not clearance_data:
        return {"min_clearance": None, "collision_count": 0,
                "risk_count": 0, "worst_waypoint": None}

    min_c = min(clearance_data, key=lambda x: x["clearance_m"])
    return {
        "min_clearance": min_c["clearance_m"],
        "collision_count": sum(1 for c in clearance_data if c["is_collision"]),
        "risk_count": sum(1 for c in clearance_data if c["is_risk"]),
        "worst_waypoint": min_c["waypoint_index"],
    }