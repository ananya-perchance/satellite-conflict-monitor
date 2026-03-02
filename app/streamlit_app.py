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

# AI Integration (Mock implementation for now, can be replaced with OpenAI/Gemini API)
def analyze_change_with_ai(change_pct, change_pixels):
    """Analyze the satellite change results using a heuristic AI approach."""
    if change_pct < 5:
        return "Minimal change detected. The region appears stable with no significant new construction or destruction."
    elif 5 <= change_pct < 20:
        return f"Moderate activity detected. Approximately {change_pct}% of the area shows changes, possibly new small-scale structures, road clearings, or seasonal vegetation shifts."
    else:
        return f"Significant landscape transformation detected! {change_pct}% of the area has changed. This is highly indicative of large-scale construction, land clearing, or significant structural changes."

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

def km_to_deg(km):
    return km / 111.0

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
    url = image.getThumbURL({
        "region": region,
        "dimensions": size,
        "format": "png",
        "min": 0, "max": 3000,
        "bands": ["B4"]
    })
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
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
    change_pct = round(change_pixels / mask.size * 100, 2)
    return before_n, after_n, diff, mask, change_pixels, change_pct

# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Satellite Conflict Monitor", page_icon="satellite", layout="wide")
st.title("Satellite Conflict Monitor")

# Sidebar
with st.sidebar:
    st.header("1. Pick Location")
    # Default coordinates
    if 'lat' not in st.session_state: st.session_state.lat = 33.3457
    if 'lon' not in st.session_state: st.session_state.lon = 75.9557
    
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=10)
    m.add_child(folium.LatLngPopup())
    map_data = st_folium(m, height=300, width=300)
    
    if map_data and map_data.get("last_clicked"):
        st.session_state.lat = map_data["last_clicked"]["lat"]
        st.session_state.lon = map_data["last_clicked"]["lng"]
        st.success(f"Selected: {st.session_state.lat:.4f}, {st.session_state.lon:.4f}")

    lat = st.number_input("Latitude", value=st.session_state.lat, format="%.4f")
    lon = st.number_input("Longitude", value=st.session_state.lon, format="%.4f")
    size_km = st.slider("Box size (km)", 5, 100, 20)
    
    st.header("2. Analysis Parameters")
    days_back = st.slider("Look-back (days)", 30, 730, 365)
    threshold = st.slider("Threshold", 5, 60, 25)
    run_btn = st.button("Run AI Analysis", type="primary", use_container_width=True)

if run_btn:
    with st.spinner("Analyzing imagery..."):
        try:
            init_ee()
            aoi = get_bbox(lat, lon, size_km)
            before_img, after_img, date_range = get_before_after_images(aoi, days_back=days_back)
            before_arr = ee_image_to_array(before_img, aoi)
            after_arr = ee_image_to_array(after_img, aoi)
            b, a, d, m, pixels, pct = detect_change(before_arr, after_arr, threshold=threshold)
            
            # AI Insight
            ai_commentary = analyze_change_with_ai(pct, pixels)
            st.info(f"🤖 **AI Analysis:** {ai_commentary}")
            
            # Metrics
            c1, c2, c3 = st.columns(3)
            c1.metric("Change Area", f"{pct}%")
            c2.metric("Changed Pixels", pixels)
            c3.metric("Date Range", date_range)
            
            # Visuals
            v1, v2, v3, v4 = st.columns(4)
            v1.image(b, caption="Before", use_column_width=True)
            v2.image(a, caption="After", use_column_width=True)
            v3.image(d, caption="Difference", use_column_width=True)
            v4.image(m, caption="Detected Changes", use_column_width=True)
            
        except Exception as e:
            st.error(f"Error: {e}")
else:
    st.info("Click on the map or enter coordinates, then click **Run AI Analysis**.")
