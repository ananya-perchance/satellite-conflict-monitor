# app/streamlit_app.py
# Full dynamic Satellite Conflict Monitor
# User picks any lat/lon + box size, app fetches imagery and detects changes live.

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

# ---------------------------------------------------------------------------
# Earth Engine helpers
# ---------------------------------------------------------------------------

def init_ee():
    """Initialize Earth Engine. Uses interactive auth locally.
    On Streamlit Cloud, store service account JSON in st.secrets."""
    try:
        # Try service account first (production)
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
    """Rough lat/lon degree conversion for mid-latitudes."""
    return km / 111.0


def get_bbox(lat, lon, size_km):
    """Build an Earth Engine bounding-box rectangle."""
    d = km_to_deg(size_km) / 2
    return ee.Geometry.Rectangle([lon - d, lat - d, lon + d, lat + d])


def get_before_after_images(aoi, days_back=365, cloud_pct=20):
    """Return two Sentinel-2 median composites: before and after."""
    end = datetime.utcnow()
    start = end - timedelta(days=days_back)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start_str, end_str)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_pct))
    )

    # Older half of the collection = "before"
    before = col.limit(20).median().clip(aoi)
    # Most recent images = "after"
    after = col.sort("system:time_start", False).limit(5).median().clip(aoi)

    return before, after, f"{start_str} to {end_str}"


def ee_image_to_array(image, region, size=512):
    """Download a small PNG thumbnail from Earth Engine and return as numpy array."""
    url = image.getThumbURL({
        "region": region,
        "dimensions": size,
        "format": "png",
        "min": 0,
        "max": 3000,
        "bands": ["B4"]   # Red band - shows surface well
    })
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    img = Image.open(BytesIO(resp.content)).convert("L")  # grayscale
    return np.array(img)


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

def detect_change(before_arr, after_arr, threshold=25):
    """Compute change mask between two grayscale arrays.
    Returns: before_norm, after_norm, diff, mask, change_pixels, change_pct"""
    before_n = cv2.normalize(before_arr, None, 0, 255, cv2.NORM_MINMAX).astype("uint8")
    after_n  = cv2.normalize(after_arr, None, 0, 255, cv2.NORM_MINMAX).astype("uint8")

    diff = cv2.absdiff(after_n, before_n)

    _, mask = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)

    # Morphological cleanup: remove tiny noise blobs
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    change_pixels = int(np.sum(mask == 255))
    total_pixels  = mask.size
    change_pct    = round(change_pixels / total_pixels * 100, 2)

    return before_n, after_n, diff, mask, change_pixels, change_pct


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Satellite Conflict Monitor",
    page_icon="satellite",
    layout="wide"
)

st.title("Satellite Conflict Monitor")
st.markdown(
    "Select **any location on Earth** by entering coordinates and area size. "
    "The app fetches live Sentinel-2 imagery and automatically detects infrastructure changes."
)

# Sidebar controls
with st.sidebar:
    st.header("Region Selection")
    lat      = st.number_input("Latitude",  value=31.5,  min_value=-90.0,  max_value=90.0,  format="%.4f")
    lon      = st.number_input("Longitude", value=78.5,  min_value=-180.0, max_value=180.0, format="%.4f")
    size_km  = st.slider("Box size (km)",   min_value=5,   max_value=100, value=20)

    st.header("Parameters")
    days_back  = st.slider("Look-back period (days)", min_value=30, max_value=730, value=365)
    threshold  = st.slider("Change threshold (0-60)", min_value=5,  max_value=60,  value=25)
    cloud_pct  = st.slider("Max cloud cover (%)",     min_value=5,  max_value=50,  value=20)

    run_btn = st.button("Run Analysis", type="primary", use_container_width=True)

    st.markdown("---")
    st.caption(
        "Data: Sentinel-2 via Google Earth Engine.\n"
        "Change detection: OpenCV absolute difference + morphological cleanup."
    )

# Main analysis
if run_btn:
    with st.spinner("Step 1/3 Initializing Earth Engine and fetching imagery..."):
        try:
            init_ee()
            aoi = get_bbox(lat, lon, size_km)
            before_img, after_img, date_range = get_before_after_images(
                aoi, days_back=days_back, cloud_pct=cloud_pct
            )
            before_arr = ee_image_to_array(before_img, aoi, size=512)
            after_arr  = ee_image_to_array(after_img,  aoi, size=512)
        except Exception as e:
            st.error(f"Earth Engine error: {e}")
            st.info(
                "Make sure you have authenticated Earth Engine.\n"
                "Run `import ee; ee.Authenticate(); ee.Initialize()` in a terminal first."
            )
            st.stop()

    with st.spinner("Step 2/3 Computing change mask..."):
        b, a, d, m, change_pixels, change_pct = detect_change(
            before_arr, after_arr, threshold=threshold
        )

    # Metrics
    st.subheader("Results")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Changed Pixels",  change_pixels)
    col2.metric("Changed Area %",  f"{change_pct}%")
    col3.metric("Box Size",        f"{size_km} km")
    col4.metric("Date Range",      date_range)

    # Images
    st.subheader("Visual Comparison")
    c1, c2, c3, c4 = st.columns(4)
    c1.image(b, caption="Before (Band B4)",      use_container_width=True)
    c2.image(a, caption="After (Band B4)",       use_container_width=True)
    c3.image(d, caption="Difference",            use_container_width=True)
    c4.image(m, caption="Detected Changes",      use_container_width=True)

    st.markdown(
        f"**Center:** lat={lat}, lon={lon} | "
        f"**Box:** {size_km} km | "
        f"**Threshold:** {threshold} | "
        f"**Cloud filter:** {cloud_pct}%"
    )

    # Interpretation guide
    with st.expander("How to interpret the results"):
        st.markdown(
            """
- **Before / After**: Median composites of Sentinel-2 Band B4 (red band). Brighter = more reflective surface.
- **Difference**: Absolute pixel-wise difference. Bright areas = pixels that changed significantly.
- **Detected Changes**: Binary mask after thresholding + noise removal. White blobs = meaningful changes.
- A high *Changed Area %* in a conflict zone often indicates new construction, clearing, or destruction.
- Use a **smaller threshold** to catch subtle changes; increase it to reduce false positives from cloud artifacts.
            """
        )
else:
    st.info("Set your coordinates in the sidebar and click **Run Analysis** to start.")
