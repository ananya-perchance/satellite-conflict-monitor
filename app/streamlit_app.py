# app/streamlit_app.py
import streamlit as st
import ee
import numpy as np
import cv2
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
import requests
import sys
import os
from streamlit_folium import st_folium
import folium
import google.generativeai as genai

# Configure Gemini AI
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"Gemini configuration error: {e}")

def get_ai_analysis(change_pct, change_area, location_name, context="geopolitical/military"):
    prompt = f"""
    Analyze the following satellite imagery change detection data for {location_name}:
    - Area Analyzed: {location_name}
    - Percentage of Change: {change_pct:.2f}%
    - Total Changed Area: {change_area:.2f} km2
    
    Context: {context}
    
    Please provide a concise analysis of what these changes might represent (e.g., new construction, vegetation changes, infrastructure development) and any potential significance in a {context} context. Be objective and mention that this is an AI-assisted analysis.
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI Analysis failed: {e}"

def mask_s2_clouds(image):
    """Masks clouds in a Sentinel-2 image using the SCL band."""
    scl = image.select('SCL')
    # SCL classes: 3 (Cloud Shadows), 8 (Cloud Medium Probability), 9 (Cloud High Probability), 10 (Cirrus)
    mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
    return image.updateMask(mask)

# Initialize Earth Engine
try:
    credentials = ee.ServiceAccountCredentials(
        email=st.secrets["ee_service_account"]["client_email"],
        key_data=st.secrets["ee_service_account"]["ee_private_key"]
    )
    ee.Initialize(credentials)
except Exception as e:
    st.error(f"Failed to initialize Earth Engine: {e}")
    sys.exit(1)

st.title("Satellite Conflict Monitor")
st.write("Detect landscape changes using Sentinel-2 satellite imagery")

# Default coordinates
lat = 34.0
lon = 74.0

# Add tabs for different input methods
tab1, tab2 = st.tabs(["Coordinates", "Map Picker"])
with tab1:
    st.subheader("Enter Location Coordinates")
    col1, col2 = st.columns(2)
    with col1:
        lat = st.number_input("Latitude", value=34.0, min_value=-90.0, max_value=90.0, format="%.4f")
    with col2:
        lon = st.number_input("Longitude", value=74.0, min_value=-180.0, max_value=180.0, format="%.4f")

    st.write("**Or search for a location:**")
    location_search = st.text_input("Enter place name (e.g., 'Kashmir, India' or 'Doklam')")
    if location_search:
        try:
            geocode_url = f"https://nominatim.openstreetmap.org/search?q={location_search}&format=json&limit=1"
            response = requests.get(geocode_url, headers={"User-Agent": "SatelliteConflictMonitor/1.0"})
            if response.status_code == 200:
                results = response.json()
                if results:
                    lat = float(results[0]["lat"])
                    lon = float(results[0]["lon"])
                    st.success(f"Found: {results[0].get('display_name', location_search)} at ({lat:.4f}, {lon:.4f})")
                else:
                    st.warning("Location not found. Please try a different search term.")
        except Exception as e:
            st.error(f"Error searching location: {e}")

with tab2:
    st.subheader("Select Location on Map")
    m = folium.Map(location=[lat, lon], zoom_start=6)
    folium.Marker([lat, lon], popup="Selected Location", draggable=True).add_to(m)
    map_data = st_folium(m, width=700, height=500)
    if map_data and map_data.get("last_clicked"):
        lat = map_data["last_clicked"]["lat"]
        lon = map_data["last_clicked"]["lng"]

# Parameters
st.subheader("Analysis Parameters")
col3, col4, col5 = st.columns(3)
with col3:
    size_km = st.slider("Area Size (km)", min_value=5, max_value=50, value=20)
with col4:
    months_back = st.slider("Months Back", min_value=1, max_value=24, value=6)
with col5:
    threshold = st.slider("Sensitivity", min_value=0.05, max_value=0.5, value=0.15, step=0.01)

if st.button("Analyze Changes"):
    with st.spinner("Processing satellite imagery..."):
        try:
            point = ee.Geometry.Point([lon, lat])
            region = point.buffer(size_km * 1000 / 2).bounds()
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=months_back * 30)
            
            # Using Sentinel-2 Surface Reflectance
            collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
                .filterBounds(region) \
                .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')) \
                .map(mask_s2_clouds)
            
            if collection.size().getInfo() < 2:
                st.error("Not enough cloud-free images available.")
            else:
                recent = collection.sort('system:time_start', False).first()
                old = collection.sort('system:time_start').first()
                
                # Use NDVI for more robust change detection (vegetation/construction)
                def get_ndvi(img):
                    return img.normalizedDifference(['B8', 'B4']).rename('NDVI')
                
                recent_ndvi = get_ndvi(recent)
                old_ndvi = get_ndvi(old)
                
                # Detect change in NDVI
                diff = recent_ndvi.subtract(old_ndvi).abs()
                change_mask = diff.gt(threshold)
                
                # Stats
                stats = change_mask.reduceRegion(
                    reducer=ee.Reducer.sum(),
                    geometry=region,
                    scale=10,
                    maxPixels=1e9
                ).getInfo()
                
                change_pixels = stats.get('NDVI', 0)
                total_pixels = region.area(maxError=1).divide(100).getInfo()
                change_pct = (change_pixels / total_pixels) * 100 if total_pixels > 0 else 0
                total_area_km2 = float(size_km)**2
                changed_area_km2 = (change_pct / 100.0) * total_area_km2
                
                st.success("Analysis Complete!")
                
                col_a, col_b = st.columns(2)
                with col_a:
                    st.subheader("Older Image (RGB)")
                    old_url = old.select(['B4', 'B3', 'B2']).visualize(min=0, max=3000).getThumbURL({
                        'region': region, 'dimensions': 512, 'format': 'png'
                    })
                    st.image(old_url)
                    st.caption(f"Date: {datetime.fromtimestamp(old.get('system:time_start').getInfo()/1000).strftime('%Y-%m-%d')}")
                
                with col_b:
                    st.subheader("Recent Image (RGB)")
                    recent_url = recent.select(['B4', 'B3', 'B2']).visualize(min=0, max=3000).getThumbURL({
                        'region': region, 'dimensions': 512, 'format': 'png'
                    })
                    st.image(recent_url)
                    st.caption(f"Date: {datetime.fromtimestamp(recent.get('system:time_start').getInfo()/1000).strftime('%Y-%m-%d')}")
                
                st.subheader("Detected Changes (NDVI Difference)")
                change_viz_url = change_mask.visualize(min=0, max=1, palette=['black', 'red']).getThumbURL({
                    'region': region, 'dimensions': 512, 'format': 'png'
                })
                st.image(change_viz_url)
                
                st.subheader("AI Contextual Analysis")
                loc_name = location_search if location_search else f"Coordinates ({lat}, {lon})"
                with st.spinner("Generating AI Analysis..."):
                    ai_report = get_ai_analysis(change_pct, changed_area_km2, loc_name)
                    st.markdown(ai_report)
                    
        except Exception as e:
            st.error(f"Error: {e}")
            st.exception(e)
