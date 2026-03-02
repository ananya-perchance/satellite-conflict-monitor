# app/streamlit_app.py
import streamlit as st
import ee
import numpy as np
import cv2
from datetime import datetime, timedelta
import requests
from io import BytesIO
from PIL import Image
import sys
import os
from streamlit_folium import st_folium
import folium

# Detailed AI Analysis with heuristic pattern recognition
def analyze_change_with_ai(change_pct, change_pixels, size_km, threshold):
    """
    Detailed analysis of landscape changes.
    Recognizes patterns based on change density and area size.
    """
    total_area_km2 = float(size_km)**2
    changed_area_km2 = (float(change_pct) / 100.0) * total_area_km2
    
    analysis = [f"**Area Overview:** Analyzed a {size_km}x{size_km} km region ({total_area_km2} km²)."]
    
    if change_pct < 2:
        analysis.append("✅ **Stability:** The region is highly stable. No visible structural changes.")
    elif 2 <= change_pct < 8:
        analysis.append("🔍 **Minor Activity:** Detected small-scale anomalies. This usually corresponds to vehicle tracks, minor land clearing, or seasonal vegetation drying.")
    elif 8 <= change_pct < 25:
        analysis.append(f"🚧 **Construction/Activity:** Significant changes detected over {changed_area_km2:.2f} km². This pattern is typical for new infrastructure, road development, or large encampments.")
    else:
        analysis.append(f"🚨 **Major Transformation:** Extreme change detected ({change_pct}%). This suggests large-scale earth-moving, major building construction, or significant surface disturbance (e.g., forest fire or heavy military activity).")

    if threshold < 15:
        analysis.append("_Note: Sensitivity is set very high; some 'changes' may be due to lighting or cloud artifacts._")
        
    return 

".join(analysis)

def search_location(query):
    """Simple geocoding using Nominatim (no API key required)."""
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1"
        headers = {"User-Agent": "SatelliteConflictMonitor/1.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"]), data[0]["display_name"]
    except Exception:
        pass
    return None

# ---------------------------------------------------------------------------
# Earth Engine helpers
# ---------------------------------------------------------------------------
def init_ee():
    try:
        if "ee_service_account" in st.secrets:
            credentials = ee.ServiceAccountCredentials(
                st.secrets["ee_service_account"]["client_email"],
                key_data=st.secrets["ee_service_account"]["private_key"]
            )
            ee.Initialize(credentials)
        else:
            ee.Initialize()
    except Exception:
        ee.Authenticate()
        ee.Initialize()

def km_to_deg(km): return km / 111.0

def get_bbox(lat, lon, size_km):
    d = km_to_deg(size_km) / 2
    return ee.Geometry.Rectangle([lon - d, lat - d, lon + d, lat + d])

def get_before_after_images(aoi, days_back=365, cloud_pct=20):
    end = datetime.utcnow()
    start = end - timedelta(days=days_back)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
           .filterBounds(aoi)
           .filterDate(start_str, end_str)
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_pct)))
    before = col.limit(20).median().clip(aoi)
    after = col.sort("system:time_start", False).limit(5).median().clip(aoi)
    return before, after, f"{start_str} to {end_str}"

def ee_image_to_array(image, region, size=512):
    url = image.getThumbURL({"region": region, "dimensions": size, "format": "png", "min": 0, "max": 3000, "bands": ["B4"]})
    resp = requests.get(url, timeout=60)
    img = Image.open(BytesIO(resp.content)).convert("L")
    return np.array(img)

def detect_change(before_arr, after_arr, threshold=25):
    before_n = cv2.normalize(before_arr, None, 0, 255, cv2.NORM_MINMAX).astype("uint8")
    after_n = cv2.normalize(after_arr, None, 0, 255, cv2.NORM_MINMAX).astype("uint8")
    diff = cv2.absdiff(after_n, before_n)
    _, mask = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    change_pixels = int(np.sum(mask == 255))
    return before_n, after_n, diff, mask, change_pixels, round(change_pixels / mask.size * 100, 2)

# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Satellite Conflict Monitor", page_icon="satellite", layout="wide")
st.title("🛰️ Satellite Conflict Monitor")

if 'lat' not in st.session_state: st.session_state.lat = 33.3457
if 'lon' not in st.session_state: st.session_state.lon = 75.9557

with st.sidebar:
    st.header("1. Find Location")
    search_query = st.text_input("Search for a place (e.g., 'Gaza', 'Taipei')")
    if search_query:
        result = search_location(search_query)
        if result:
            st.session_state.lat, st.session_state.lon, name = result
            st.success(f"Found: {name}")
        else:
            st.warning("Location not found.")

    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=12)
    m.add_child(folium.LatLngPopup())
    map_data = st_folium(m, height=250, width=300, key="map")
    
    if map_data and map_data.get("last_clicked"):
        st.session_state.lat = map_data["last_clicked"]["lat"]
        st.session_state.lon = map_data["last_clicked"]["lng"]

    lat = st.number_input("Latitude", value=st.session_state.lat, format="%.4f")
    lon = st.number_input("Longitude", value=st.session_state.lon, format="%.4f")
    size_km = st.slider("Analysis Box (km)", 5, 50, 15)
    
    st.header("2. Settings")
    threshold = st.slider("Sensitivity Threshold", 5, 60, 25)
    run_btn = st.button("🚀 Run Detailed AI Analysis", type="primary", use_container_width=True)

if run_btn:
    with st.spinner("🔍 Accessing Sentinel-2 archives and computing changes..."):
        try:
            init_ee()
            aoi = get_bbox(lat, lon, size_km)
            before_img, after_img, date_range = get_before_after_images(aoi)
            before_arr = ee_image_to_array(before_img, aoi)
            after_arr = ee_image_to_array(after_img, aoi)
            b, a, d, m, pixels, pct = detect_change(before_arr, after_arr, threshold=threshold)
            
            st.subheader("🤖 Detailed AI Analysis")
            st.info(analyze_change_with_ai(pct, pixels, size_km, threshold))
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Changed Area", f"{pct}%")
            col2.metric("Changed Pixels", f"{pixels:,}")
            col3.metric("Observation Span", date_range)
            
            v1, v2, v3, v4 = st.columns(4)
            v1.image(b, caption="Baseline (Before)", use_column_width=True)
            v2.image(a, caption="Current (After)", use_column_width=True)
            v3.image(d, caption="Difference Map", use_column_width=True)
            v4.image(m, caption="Verified Changes", use_column_width=True)
        except Exception as e:
            st.error(f"Analysis failed: {e}")
else:
    st.info("Search for a place, click on the map, or enter coordinates to begin monitoring.")
