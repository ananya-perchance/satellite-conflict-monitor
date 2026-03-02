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

# Detailed AI Analysis with heuristic pattern recognition
def analyze_change_with_ai(change_pct, change_pixels, size_km, threshold):
    """
    Detailed analysis of landscape changes.
    Recognizes patterns based on change density and area size.
    """
    total_area_km2 = float(size_km)**2
    changed_area_km2 = (float(change_pct) / 100.0) * total_area_km2
    
    analysis = [f"***Area Overview:** Analyzed a {size_km}×{size_km} km region ({total_area_km2} km²)."]
    
    if change_pct < 2:
        analysis.append("✅ **Stability:** The region is highly stable. No visible structural changes.")
    elif change_pct < 5:
        analysis.append("⚠️ **Low Change:** Minor changes detected, possibly seasonal vegetation or natural erosion.")
    elif change_pct < 15:
        analysis.append("🔶 **Moderate Change:** Noticeable changes. Could be infrastructure development or agricultural activity.")
    elif change_pct < 30:
        analysis.append("🔴 **Significant Change:** Major alterations detected. Potential military build-up or large-scale construction.")
    else:
        analysis.append("🚨 **Critical Change:** Extensive modifications across the region. High priority for investigation.")
    
    # Detailed breakdowns
    analysis.append(f"\n**Change Statistics:**")
    analysis.append(f"- Changed Area: {changed_area_km2:.2f} km²")
    analysis.append(f"- Percentage Changed: {change_pct:.2f}%")
    analysis.append(f"- Changed Pixels: {change_pixels:,}")
    
    # Pattern interpretation
    if change_pct > 10:
        if changed_area_km2 > 50:
            analysis.append("\n📊 **Pattern Analysis:** Large-scale development. Likely involves:")
            analysis.append("  - Military base expansion")
            analysis.append("  - Infrastructure projects (roads, airstrips)")
            analysis.append("  - Mining or resource extraction")
        elif changed_area_km2 > 10:
            analysis.append("\n📊 **Pattern Analysis:** Medium-scale activity. Possible scenarios:")
            analysis.append("  - New building construction")
            analysis.append("  - Agricultural expansion")
            analysis.append("  - Border fortifications")
        else:
            analysis.append("\n📊 **Pattern Analysis:** Localized changes. Could indicate:")
            analysis.append("  - Small outpost or checkpoint construction")
            analysis.append("  - Vegetation clearing")
            analysis.append("  - Minor infrastructure updates")
    
    # Recommendations
    if change_pct > 15:
        analysis.append("\n💡 **Recommendations:**")
        analysis.append("  - Conduct follow-up analysis with higher resolution imagery")
        analysis.append("  - Compare with historical trends for confirmation")
        analysis.append("  - Monitor region continuously for further developments")
    
    return "\n".join(analysis)

# Initialize Earth Engine
try:
    credentials = ee.ServiceAccountCredentials(
        email=st.secrets["ee_service_account"]["client_email"],
        key_data=st.secrets["ee_service_account"]["ee_private_key"]    )
    ee.Initialize(credentials)
except Exception as e:
    st.error(f"Failed to initialize Earth Engine: {e}")
    sys.exit(1)

st.title("🛰️ Satellite Conflict Monitor")
st.write("Detect landscape changes using Sentinel-2 satellite imagery")

# Add tabs for different input methods
tab1, tab2 = st.tabs(["📍 Coordinates", "🗺️ Map Picker"])

with tab1:
    st.subheader("Enter Location Coordinates")
    col1, col2 = st.columns(2)
    with col1:
        lat = st.number_input("Latitude", value=34.0, min_value=-90.0, max_value=90.0, format="%.4f")
    with col2:
        lon = st.number_input("Longitude", value=74.0, min_value=-180.0, max_value=180.0, format="%.4f")
    
    # Location search
    st.write("**Or search for a location:**")
    location_search = st.text_input("Enter place name (e.g., 'Kashmir, India' or 'Doklam')")
    if location_search:
        try:
            # Use Nominatim API for geocoding
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
            else:
                st.error("Geocoding service unavailable. Please use coordinates.")
        except Exception as e:
            st.error(f"Error searching location: {e}")

with tab2:
    st.subheader("Select Location on Map")
    st.write("Click on the map to select coordinates, or drag the marker.")
    
    # Create a folium map centered on current coordinates
    m = folium.Map(location=[lat if 'lat' in locals() else 34.0, lon if 'lon' in locals() else 74.0], zoom_start=6)
    
    # Add a draggable marker
    folium.Marker(
        [lat if 'lat' in locals() else 34.0, lon if 'lon' in locals() else 74.0],
        popup="Drag me!",
        draggable=True
    ).add_to(m)
    
    # Display map and get click data
    map_data = st_folium(m, width=700, height=500)
    
    # Update coordinates if map was clicked or marker dragged
    if map_data and map_data.get("last_clicked"):
        lat = map_data["last_clicked"]["lat"]
        lon = map_data["last_clicked"]["lng"]
        st.success(f"Selected coordinates: ({lat:.4f}, {lon:.4f})")

# Parameters
st.subheader("Analysis Parameters")
col3, col4, col5 = st.columns(3)
with col3:
    size_km = st.slider("Area Size (km)", min_value=5, max_value=50, value=20, 
                        help="Size of the square area to analyze")
with col4:
    months_back = st.slider("Months Back", min_value=1, max_value=24, value=6,
                           help="How far back to compare imagery")
with col5:
    threshold = st.slider("Sensitivity", min_value=10, max_value=100, value=30,
                         help="Lower = more sensitive to changes")

if st.button("Analyze Changes"):
    with st.spinner("Processing satellite imagery..."):
        try:
            # Define region
            point = ee.Geometry.Point([lon, lat])
            region = point.buffer(size_km * 1000 / 2).bounds()
            
            # Date ranges
            end_date = datetime.now()
            start_date = end_date - timedelta(days=months_back*30)
            
            # Get Sentinel-2 images
            collection = ee.ImageCollection('COPERNICUS/S2_SR') \
                .filterBounds(point) \
                .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')) \
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
            
            if collection.size().getInfo() < 2:
                st.error("Not enough cloud-free images available for this location and time period.")
            else:
                # Get recent and old images
                recent = collection.sort('system:time_start', False).first()
                old = collection.sort('system:time_start').first()
                
                # Select RGB bands
                recent_rgb = recent.select(['B4', 'B3', 'B2'])
                old_rgb = old.select(['B4', 'B3', 'B2'])
                
                # Compute change
                diff = recent_rgb.subtract(old_rgb).abs().reduce(ee.Reducer.sum())
                change_mask = diff.gt(threshold)
                
                # Get change statistics
                stats = change_mask.reduceRegion(
                    reducer=ee.Reducer.sum(),
                    geometry=region,
                    scale=10,
                    maxPixels=1e9
                ).getInfo()
                
                change_pixels = stats.get('sum', 0)
                total_pixels = region.area().divide(100).getInfo()
                change_pct = (change_pixels / total_pixels) * 100 if total_pixels > 0 else 0
                
                # Display results
                st.success("Analysis Complete!")
                
                col_a, col_b = st.columns(2)
                
                with col_a:
                    st.subheader("📅 Older Image")
                    old_url = old_rgb.visualize(min=0, max=3000).getThumbURL({
                        'region': region,
                        'dimensions': 512,
                        'format': 'png'
                    })
                    old_img = Image.open(BytesIO(requests.get(old_url).content))
                    st.image(old_img, use_container_width=True)
                    old_date = datetime.fromtimestamp(old.get('system:time_start').getInfo()/1000)
                    st.caption(f"Date: {old_date.strftime('%Y-%m-%d')}")
                
                with col_b:
                    st.subheader("🆕 Recent Image")
                    recent_url = recent_rgb.visualize(min=0, max=3000).getThumbURL({
                        'region': region,
                        'dimensions': 512,
                        'format': 'png'
                    })
                    recent_img = Image.open(BytesIO(requests.get(recent_url).content))
                    st.image(recent_img, use_container_width=True)
                    recent_date = datetime.fromtimestamp(recent.get('system:time_start').getInfo()/1000)
                    st.caption(f"Date: {recent_date.strftime('%Y-%m-%d')}")
                
                # Change visualization
                st.subheader("🔍 Detected Changes")
                change_url = change_mask.visualize(min=0, max=1, palette=['black', 'red']).getThumbURL({
                    'region': region,
                    'dimensions': 512,
                    'format': 'png'
                })
                change_img = Image.open(BytesIO(requests.get(change_url).content))
                st.image(change_img, use_container_width=True)
                st.caption(f"Red areas indicate changes (Threshold: {threshold})")
                
                # AI Analysis with detailed insights
                st.subheader("🤖 AI Analysis")
                ai_analysis = analyze_change_with_ai(change_pct, change_pixels, size_km, threshold)
                st.info(ai_analysis)
                
        except Exception as e:
            st.error(f"Error during analysis: {e}")
            st.exception(e)
