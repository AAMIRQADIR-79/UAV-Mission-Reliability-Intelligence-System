<div align="center">

# AI-Driven UAV Mission Reliability Intelligence System

**Pre-flight and in-flight risk intelligence for small delivery drones**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B?logo=streamlit&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-Deep%20Learning-EE4C2C?logo=pytorch&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-Ensemble-F7931E?logo=scikitlearn&logoColor=white)
![Status](https://img.shields.io/badge/Status-Research%20Prototype-informational)
![Paper](https://img.shields.io/badge/Paper-Accepted%20at%20ICAIN%202026-success)

*Department of Computer Science and Engineering, Sai Vidya Institute of Technology, Bengaluru*

</div>

---

## Table of Contents

1. [Overview](#overview)
2. [Key Features](#key-features)
3. [Operating Scope](#operating-scope)
4. [System Architecture](#system-architecture)
5. [Models](#models)
6. [Results](#results)
7. [Screenshots](#screenshots)
8. [Getting Started](#getting-started)
9. [Usage](#usage)
10. [Project Structure](#project-structure)
11. [Testing and Validation](#testing-and-validation)
12. [Limitations](#limitations)
13. [Roadmap](#roadmap)
14. [Publication](#publication)
15. [Team](#team)
16. [License](#license)
17. [Acknowledgements](#acknowledgements)

---

## Overview

Delivery drones fail for reasons that are often predictable: a battery that drains faster than planned, strong wind along part of the route, a restricted airspace, or terrain that rises above the planned altitude. Most ground-control software shows the operator what the drone is doing *now*, but does not estimate *before take-off* how likely a planned mission is to run into trouble.

This project is a ground-control dashboard that closes that gap. Given a source and a destination, it builds the route, pulls live weather and terrain data for every waypoint, checks the mission against operating rules, and produces a **risk score with an explanation** of what is driving it. A tree-based ensemble and four deep learning models score each mission from different angles, and a set of safety modules cover return-to-home, GPS loss and multi-drone conflicts.

> **Note on data:** the models are trained on a physics-informed **synthetic** dataset, because real delivery-mission failure data is not publicly available. See [Limitations](#limitations).

---

## Key Features

| Area | What it does |
|---|---|
| **Route planning** | Place search with nearby-first suggestions (typo tolerant), or GPS coordinates; Haversine distance, bearing and evenly spaced waypoints |
| **Per-waypoint live data** | Weather fetched at every waypoint (OpenWeatherMap) rather than one reading for the whole route |
| **Risk prediction** | Ensemble classifier plus four deep learning models; Low / Medium / High risk with feature importance |
| **Waypoint-level insight** | BiLSTM attention heatmap and Transformer per-waypoint risk show *where* along the route the danger is |
| **Anomaly detection** | Autoencoder trained on safe missions only; flags unusual missions that the rules did not anticipate |
| **Scope guard** | Flags missions beyond 100 km or 400 m, or without enough battery for the round trip plus reserve, instead of scoring them |
| **Terrain awareness** | Compares planned altitude against real ground elevation at each waypoint and advises a corrected altitude |
| **Return-to-home** | Checks battery for the return leg and selects a reachable emergency landing zone |
| **GPS-loss fallback** | Dead reckoning with a growing uncertainty radius when GPS drops out |
| **Multi-drone check** | Flags a conflict only when two drones are close in both distance and time |
| **Compliance** | DGCA altitude limits and no-fly zone checks |
| **Mission report** | Downloadable summary of the mission and its risk assessment |
| **Operator UI** | Dark, Mission Planner-style interface with map, HUD, instrument dials and waypoint table |

---

## Operating Scope

The system is intentionally restricted to the use case it is designed for:

| Parameter | Limit |
|---|---|
| Vehicle class | Small delivery drones |
| Maximum mission distance | **100 km** |
| Maximum altitude | **400 m** |
| Battery reserve | 20 % kept in reserve |

Missions outside these limits are reported as out of scope instead of being given a misleading score.

---

## System Architecture

```
 Source (A) ──┐
              ├─► Route builder ─► Waypoints ─┬─► Weather (per waypoint)
 Destination (B)┘   (Haversine, bearing)      ├─► Terrain elevation
                                              ├─► Rule checks (scope, DGCA, no-fly zones)
                                              └─► Battery drain estimate
                                                         │
                                                         ▼
                                             Feature engineering (10 inputs)
                                                         │
                         ┌───────────────┬───────────────┼───────────────┬───────────────┐
                         ▼               ▼               ▼               ▼               ▼
                   Tree ensemble   Residual MLP    BiLSTM + Attn    Transformer     Autoencoder
                         └───────────────┴───────────────┼───────────────┴───────────────┘
                                                         ▼
                              Risk level, per-waypoint risk, anomaly flag, alerts
                                                         │
                       Return-to-home · GPS-loss estimate · Multi-drone conflicts
                                                         ▼
                                              Streamlit ground-control dashboard
```

**The ten model inputs:** distance, battery level, wind speed, payload, signal strength, temperature, altitude, humidity, estimated flight time and battery drain rate.

---

## Models

| Model | Role | Input | Output |
|---|---|---|---|
| **Tree ensemble** (Random Forest 300 + Gradient Boosting 200 + Extra Trees 250, soft voting 3:2:2) | Fast, explainable primary score | Mission features | Risk class, feature importance |
| **Residual MLP** | Independent second opinion | Mission features | Risk class |
| **BiLSTM with Attention** | Locate the risky part of the route | Waypoint sequence | Risk, attention weights per waypoint |
| **Waypoint Transformer** | Capture risks that come from combinations of distant waypoints | Waypoint sequence | Per-waypoint risk |
| **Telemetry Autoencoder** (10-16-8-4-8-16-10) | Flag unusual missions without labels | Mission features | Reconstruction error, anomaly flag |

<<<<<<< HEAD
Architecture diagrams are available in [`assets/architectures/`](assets/architectures/).
=======
Architecture diagrams are available in [`docs/architectures/`](docs/architectures/).
>>>>>>> bc112206aac8e5be481eddd6506375408703e75f

---

## Results

Evaluated on a stratified 20 % held-out split of the synthetic dataset (8,000 missions, 3 % label noise).

| Model | Accuracy | AUC-ROC | Parameters |
|---|---|---|---|
<<<<<<< HEAD
| Ensemble (RF + GBM + ET) | 93.25 % | 94.84 % | n/a |
| Residual MLP | 90.56 % | n/a | 550,273 |
| BiLSTM + Attention | 95.00 % | n/a | 142,530 |
| **Waypoint Transformer** | **99.08 %** | n/a | 152,769 |
=======
| Ensemble (RF + GBM + ET) | 93.50 % | 94.87 % | n/a |
| Residual MLP | 90.56 % | n/a | 550,273 |
| BiLSTM + Attention | 95.33 % | n/a | 142,530 |
| **Waypoint Transformer** | **98.94 %** | n/a | 152,769 |
>>>>>>> bc112206aac8e5be481eddd6506375408703e75f
| Autoencoder | unsupervised | n/a | 702 |

> **How to read these numbers.** Labels come from rules based on documented drone operating limits, so these figures show how well each model learned and generalised those rules. They are **not** an estimate of accuracy on real flights. Validation on real flight data is listed in the [Roadmap](#roadmap).

---

## Screenshots

<<<<<<< HEAD
<!-- Replace these with your own screenshots, saved in assets/images/ -->

| Flight Plan | Flight Data |
|---|---|
| ![Flight plan](assets/images/flight_plan.png) | ![Flight data](assets/images/flight_data.png) |

| Deep Learning | Terrain and RTH |
|---|---|
| ![Deep learning](assets/images/deep_learning.png) | ![Terrain and RTH](assets/images/terrain_rth.png) |
=======
<!-- Replace these with your own screenshots, saved in docs/images/ -->

| Flight Plan | Flight Data |
|---|---|
| ![Flight plan](docs/images/flight_plan.png) | ![Flight data](docs/images/flight_data.png) |

| Deep Learning | Terrain and RTH |
|---|---|
| ![Deep learning](docs/images/deep_learning.png) | ![Terrain and RTH](docs/images/terrain_rth.png) |
>>>>>>> bc112206aac8e5be481eddd6506375408703e75f

---

## Getting Started

### Prerequisites

- Python 3.10 or newer
- An [OpenWeatherMap](https://openweathermap.org/api) API key (free tier is enough). Without a key the app falls back to simulated weather and labels it as such.
- Internet access for place search, weather and elevation lookups

### Installation

```bash
# 1. Clone the repository
<<<<<<< HEAD
git clone https://github.com/AAMIRQADIR-79/UAV-Mission-Reliability-Intelligence-System.git
cd UAV-Mission-Reliability-Intelligence-System
=======
git clone https://github.com/<your-username>/<repository-name>.git
cd <repository-name>
>>>>>>> bc112206aac8e5be481eddd6506375408703e75f

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
pip install torch streamlit-searchbox streamlit-js-eval
```

### Run

```bash
python -m streamlit run app.py
```

The app opens at `http://localhost:8501`. On first launch the models are trained and cached to `models/`; later launches load them from disk.

> If the models fail to load after changing the code, delete the contents of `models/` so they retrain.

---

## Usage

1. **Flight Plan:** enter a source and destination by name, or let the app use your current location as the source. Suggestions appear as you type, nearest first.
2. Set the mission parameters: payload, altitude, battery and drone profile.
3. Enter your OpenWeatherMap key, then run the analysis.
4. Review the result across the tabs:

| Tab | Content |
|---|---|
| Flight Plan | Route, waypoints and mission parameters |
| Flight Data | HUD, instrument dials, risk level, alerts |
| Weather | Per-waypoint conditions |
| NFZ Status | No-fly zone check |
| AI Analysis | Ensemble risk score and feature importance |
| Simulation | Step-by-step mission playback |
| Deep Learning | Attention heatmap, per-waypoint risk, anomaly score |
| Report | Downloadable mission report |
| Terrain and RTH | Terrain clearance and return-to-home feasibility |
| Swarm | Multi-drone conflict check |

Flight data is currently **simulated**. The dashboard labels this as `LINK: SIMULATED` until a real flight controller is connected.

---

## Project Structure

```
.
├── app.py                    # Streamlit application
├── requirements.txt
<<<<<<< HEAD
├── test_alerts.py            # Alert rule tests
├── .streamlit/               # Streamlit theme and settings
├── models/                   # Cached trained models (generated on first run)
├── exports/                  # Generated mission reports
├── assets/
│   ├── images/               # README screenshots
│   └── architectures/        # Model architecture diagrams
└── utils/
    ├── config.py             # Features, drone specs, mission types
    ├── geocoding.py          # Place and coordinate handling
    ├── place_search.py       # Nearby-first, typo-tolerant place suggestions
    ├── weather.py            # OpenWeatherMap client with simulated fallback
    ├── terrain.py            # Elevation profile and terrain clearance
    ├── scope_check.py        # 100 km / 400 m / battery scope guard
    ├── ml_model.py           # Tree ensemble training and prediction
    ├── deep_learning.py      # MLP, BiLSTM, Transformer, Autoencoder
    ├── alerts.py             # Alert rules and battery drain estimate
    ├── rth.py                # Return-to-home and emergency landing
    ├── gps_resilience.py     # GPS-loss simulation and dead reckoning
    ├── swarm.py              # Multi-drone conflict detection
    ├── data_generator.py     # Synthetic mission dataset generator
    └── ui_theme.py           # Mission Planner-style theme, HUD, dials
=======
├── models/                   # Cached trained models (generated on first run)
├── utils/
│   ├── config.py             # Features, drone specs, mission types
│   ├── geocoding.py          # Place and coordinate handling
│   ├── place_search.py       # Nearby-first, typo-tolerant place suggestions
│   ├── weather.py            # OpenWeatherMap client with simulated fallback
│   ├── terrain.py            # Elevation profile and terrain clearance
│   ├── scope_check.py        # 100 km / 400 m / battery scope guard
│   ├── ml_model.py           # Tree ensemble training and prediction
│   ├── deep_learning.py      # MLP, BiLSTM, Transformer, Autoencoder
│   ├── alerts.py             # Alert rules and battery drain estimate
│   ├── rth.py                # Return-to-home and emergency landing
│   ├── gps_resilience.py     # GPS-loss simulation and dead reckoning
│   ├── swarm.py              # Multi-drone conflict detection
│   ├── visualizations.py     # Charts
│   └── ui_theme.py           # Mission Planner-style theme, HUD, dials
├── docs/
│   ├── architectures/        # Model architecture diagrams
│   └── images/               # README screenshots
└── tests/                    # Rule-check test cases
>>>>>>> bc112206aac8e5be481eddd6506375408703e75f
```

> Adjust this tree to match your repository before publishing.

---

## Testing and Validation

The rule-based safety modules are verified against cases with known answers:

| ID | Case | Expected result |
|---|---|---|
| TC1 | Mission at 450 m | Flagged as above the 400 m limit |
| TC2 | Route of 120 km | Flagged as out of scope |
| TC3 | Two points 1° of latitude apart | Haversine returns about 111.2 km |
| TC4 | 60 km round trip with 50 % battery | Infeasible, risk forced to 99 % |
| TC5 | Srinagar to Gulmarg at flat altitude | Terrain collision flagged, altitude advised |
| TC6 | Low battery far from home | Diversion to a reachable landing zone |
| TC7 | Three drones, one near-crossing | Conflict caught, clear route ignored |

The machine learning models are evaluated separately, as described under [Results](#results).

---

## Limitations

This is a research prototype, and its limits are stated openly:

- **Synthetic training data.** Labels are rule-generated. Accuracy figures measure agreement with those rules, not real-world failure prediction.
- **No live drone yet.** Telemetry in the dashboard is simulated. Battery drain uses a physics-informed estimate rather than measured values.
- **Straight-line routes.** Routes do not follow roads, corridors or published airspace structure.
- **Waypoint-level checks.** Multi-drone conflicts and terrain clearance are evaluated at waypoints, not along the continuous path.
- **Simple GPS-loss model.** The uncertainty growth is a simplified drift model, not a full inertial navigation solution.
- **Models are trained once.** They do not update themselves from new flights; retraining is a deliberate offline step.

---

## Roadmap

- [ ] Connect a flight controller over MAVLink (start with ArduPilot or PX4 SITL, then a physical Pixhawk drone), read-only first
- [ ] Log real flights and outcomes, then retrain and validate on real data
- [ ] Validate the battery model against public data (for example the CMU Matrice 100 dataset)
- [ ] Test the autoencoder on public fault datasets (for example ALFA) and flight logs
- [ ] Adaptive battery-drain estimation during flight
- [ ] Report precision, recall and F1 alongside accuracy and AUC
- [ ] Airspace- and terrain-aware routing instead of straight lines
- [ ] Continuous-path conflict and terrain checks

---

## Publication

> **AI Driven UAV Mission Reliability System**
> Accepted at **ICAIN 2026**, International Conference on Artificial Intelligence and Networking (Elsevier).

If you use this work, please cite it:

```bibtex
@inproceedings{uav_mission_reliability_2026,
  title     = {AI Driven UAV Mission Reliability System},
  author    = {Sofi, Aamir Qadir and Tiwari, Abhay and Dheeraj, H. R. and Joshi, Karthik B.},
  booktitle = {International Conference on Artificial Intelligence and Networking (ICAIN)},
  year      = {2026}
}
```

*Update the citation with the final proceedings details once published.*

---

## Team

| Name | USN |
|---|---|
| **Aamir Qadir Sofi** | 1VA23CS002 |
| Abhay Tiwari | 1VA23CS004 |
| H. R. Dheeraj Gudimani | 1VA23CS055 |
| Karthik B. Joshi | 1VA23CS075 |

**Guide:** Dr. Shantakumar B Patil, Professor and Dean R&D, Dept. of CSE
**Co-Guide:** Prof. Arathi B N, Assistant Professor, Dept. of CSE

Sai Vidya Institute of Technology, Rajanukunte, Bengaluru, Karnataka, India.

---

## License

Released under the **MIT License** (replace this if your institution requires a different one). See [`LICENSE`](LICENSE) for details.

---

## Acknowledgements

- Sai Vidya Institute of Technology, Department of CSE, for guidance and resources
- [OpenWeatherMap](https://openweathermap.org/) for weather data
- [OpenStreetMap](https://www.openstreetmap.org/), [Photon](https://photon.komoot.io/) and [Open-Meteo](https://open-meteo.com/) for place search
- [Streamlit](https://streamlit.io/), [PyTorch](https://pytorch.org/), [scikit-learn](https://scikit-learn.org/) and [Folium](https://python-visualization.github.io/folium/)
- DGCA Drone Rules, 2021, as the reference for operating limits

> This software is a research and decision-support prototype. It is not certified for operational flight and must not be used as the sole basis for flight safety decisions.
