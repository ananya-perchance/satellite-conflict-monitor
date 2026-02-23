# Satellite Conflict Monitor

Automated detection of infrastructure changes in conflict zones using free Sentinel-2 satellite imagery, OpenCV, and Streamlit.

## Features
- Select **any region on Earth** by entering coordinates + box size
- No manual image downloads — imagery fetched live from Google Earth Engine
- Before / After satellite thumbnails side by side
- Automatically computed change mask using OpenCV
- Key stats: changed pixels, % area changed
- Clean Streamlit UI deployable anywhere

## Folder Structure
```
satellite-conflict-monitor/
├─ app/
│  └─ streamlit_app.py       # Public-facing Streamlit web app
├─ backend/
│  ├─ gee_fetch.py           # Google Earth Engine fetch logic
│  ├─ process_change.py      # OpenCV change detection pipeline
│  └─ refresh_aoi_example.md # Manual GEE export guide
├─ config.py                 # AOI definitions and thresholds
├─ requirements.txt
├─ .gitignore
└─ README.md
```

## Getting Started

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Authenticate Google Earth Engine (one-time)
```python
import ee
ee.Authenticate()
ee.Initialize()
```

### 3. Run the web app
```bash
streamlit run app/streamlit_app.py
```

### 4. Use the app
- Enter latitude, longitude, and box size (km)
- Adjust look-back period and change threshold
- Click **Run Analysis**
- View before/after images and the detected change mask

## Deployment (Streamlit Cloud)
1. Push this repo to GitHub
2. Go to https://share.streamlit.io
3. Connect your GitHub account
4. Select this repo and set main file to `app/streamlit_app.py`
5. Deploy — you get a public URL instantly

## How it works
1. **Data:** Google Earth Engine fetches Sentinel-2 imagery for your selected region
2. **Processing:** Two median composites (before/after) are built and downloaded as PNGs
3. **Detection:** OpenCV computes pixel-wise absolute difference, applies threshold + morphological cleanup
4. **Display:** Streamlit shows all outputs with key metrics

## Tech Stack
- Python, Streamlit, Google Earth Engine API
- OpenCV, NumPy, Pillow, Rasterio
- Folium (maps), Streamlit-Folium

## Use Cases
- Monitor border infrastructure changes
- Track deforestation or urban expansion
- Detect new military installations
- OSINT (Open Source Intelligence) research
