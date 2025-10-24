# 🌊 EcoRouteAI — Intelligent Maritime Route Optimization and Risk Analysis

**EcoRouteAI** is an AI-assisted ( Manual for now ) maritime route optimization and safety platform that integrates environmental, weather, and risk data (e.g., pirate attack zones) to provide the safest and most eco-efficient routes for ocean navigation.


## 🌍 Overview

EcoRouteAI enables ships, researchers, and logistics planners to make data-driven routing decisions that balance **safety**, **distance efficiency**, and **environmental sustainability**.

Using real-world data (pirate attacks, weather, geospatial coordinates), it calculates the most efficient maritime route while avoiding risky or hazardous zones.



## 🧠 Key Features

- **🗺️ Smart Route Planning** — Calculates optimal routes between ports using the `searoute` library and geographic data.
- **⚠️ Risk Assessment** — Integrates historical pirate attack data to identify and avoid high-risk regions.
- **☁️ Weather Integration** — Uses weather APIs to assess current and forecasted sea conditions.
- **🌱 Eco-Efficiency Metrics** — Evaluates route efficiency based on distance and environmental impact.
- **🧭 Interactive Map Interface** — Built with `Streamlit` + `Folium` for real-time visualization and user interaction.
- **🔍 Fuzzy Port Matching** — Supports flexible input search using `RapidFuzz` string matching.
- **📊 Modular Design** — Each function (routing, risk, weather, utils) is modular and reusable.



## 🏗️ System Architecture


User Interface (Streamlit)
        │
        ▼
Routing Engine ─────► Risk Analyzer ─────► Weather Provider
        │                    │                     │
        ▼                    ▼                     ▼
     Searoute API      Pirate Attacks CSV     Weather APIs
        │
        ▼
GeoJSON Route + Risk Score + Weather Summary


⚙️ Each module in EcoRouteAI is designed to handle a distinct aspect of the route optimization process while remaining interconnected for seamless data flow.


## 📂 Project Structure

```
EcoRouteAI/
│
├── app.py                # Main Streamlit app interface
├── routing.py            # Route generation using Searoute & Shapely
├── risk.py               # Pirate risk computation module
├── weather_providers.py  # Weather data integration
├── data_sources.py       # External data connectors
├── utils.py              # Helper & geospatial utilities
├── portswitch.py         # Port selection and validation logic
├── pirate_attacks.csv    # Dataset of historical pirate attacks
├── requirements.txt      # Dependencies
└── README.md             # Documentation
```

---

## 🧩 Tech Stack

| Category | Technologies Used |
|-----------|------------------|
| **Frontend/UI** | Streamlit, Folium, Streamlit-Folium |
| **Backend Logic** | Python, Pandas, Shapely, SeRoute |
| **Data Processing** | RapidFuzz, GeoJSON, CSV |
| **Visualization** | Folium Maps, Shapely Geometry |
| **Deployment** | Streamlit Cloud |
| **Version Control** | GitHub |

---

## ⚙️ Installation & Setup

### 🧾 1. Clone the Repository
```bash
git clone https://github.com/dindi00/sea_route_optimize.git
cd EcoRouteAI
```

### 📦 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 🧭 3. Run Locally
```bash
streamlit run app.py
```

Then open the provided local URL (e.g., `http://localhost:8501`) in your browser.

---

## ☁️ Deployment on Streamlit Cloud

1. Go to [Streamlit Cloud](https://share.streamlit.io/).  
2. Click **"New App"** → connect your GitHub repo → choose **branch: main** and **file: app.py**.  
3. Click **Deploy**.  
4. Done! Your app will be live and accessible via a public URL.

---

## 🧭 Usage Guide

1. Enter your **departure port** and **destination port**.  
2. The system will:
   - Compute an optimal route via `Searoute`.
   - Check for **risk zones** from `pirate_attacks.csv`.
   - Retrieve **current weather conditions** from weather providers.
3. View the result on an **interactive Folium map** showing:
   - Green path = safe & optimal  
   - Red zones = high-risk (pirate) areas  
   - Weather icons = key forecast indicators


## 📈 Sample Visualization

🌍 Route Map Example
-------------------------------------
Origin: Singapore
Destination: Port Said
Optimal Distance: 9,845 km
Risk Level: Low
Weather: Moderate Wind, Clear
-------------------------------------


## 🧮 Core Logic Breakdown

| Module | Purpose | Key Functions |
|---------|----------|----------------|
| **routing.py** | Route generation using `Searoute` & `Shapely` | `calculate_route()`, `plot_route()` |
| **risk.py** | Pirate risk scoring from CSV data | `compute_risk_score()`, `get_risk_zones()` |
| **weather_providers.py** | Weather data fetching | `get_weather_forecast()`, `fetch_conditions()` |
| **data_sources.py** | Source management for external data | `load_data()`, `update_sources()` |
| **utils.py** | Utility helpers (distance, coordinate ops) | `haversine_distance()`, `normalize_coords()` |
| **portswitch.py** | Port validation & fuzzy matching | `match_port()`, `resolve_input()` |



## 🔬 Data Sources

- **Pirate Attacks Dataset:** Historical maritime incident data (`pirate_attacks.csv`)
- **Weather Data:** External weather API (e.g., Open-Meteo or similar providers) - Project is using OpenWeatherAPI
- **Ports Database:** Built-in list for port matching and coordinate lookup



## 📜 License

This project is licensed under the [MIT License](LICENSE).



## 🧑‍💻 Contributors

Meet the amazing team behind **EcoRouteAI** 🌊  

| 👤 Name | 💼 Role | ✉️ Contact |
|:--------|:---------|:-----------|
| 🪶 **Aizuddin** | 🧠 Full Stack Developer | — |
| 🎨 **Qastalani** | 💻 Front-End Developer & 🎤 Pitcher | — |
| 🔬 **Ahmad Fauzi** | 📚 Researcher | — |

*Together, we build sustainable intelligence for the seas.*



## 🌱 Future Enhancements

- Integration with live **marine vessel tracking APIs**  
- Real-time **CO₂ footprint estimation**  
- Machine learning for **route risk prediction**  
- Enhanced **UI animations and dynamic overlays**
- AI automation **Implement AI to automate process**



## 💡 Citation

If you use EcoRouteAI in your research or project, please cite:

Dindi. (2025). EcoRouteAI: Maritime Route Optimization and Risk Analysis.

© 2025 BorneoTechies. Built with Amazing team using Streamlit and Python.
