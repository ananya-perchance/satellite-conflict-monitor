# backend/gee_fetch.py
# Google Earth Engine fetch logic.
# Used by the Streamlit app to get Sentinel-2 composites for any AOI.

import ee
from datetime import datetime, timedelta
import sys
import os

# Add parent dir to path so config.py is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CLOUD_THRESHOLD


def initialize_ee():
    """Initialize Earth Engine for standalone script use."""
    try:
        ee.Initialize()
    except Exception:
        ee.Authenticate()
        ee.Initialize()


def km_to_deg(km):
    """Rough conversion of km to degrees (works at mid-latitudes)."""
    return km / 111.0


def get_bbox(lat, lon, size_km):
    """Return an ee.Geometry.Rectangle for a given center + size."""
    d = km_to_deg(size_km) / 2
    return ee.Geometry.Rectangle([lon - d, lat - d, lon + d, lat + d])


def get_s2_collection(aoi, start_str, end_str, cloud_pct=None):
    """Return a filtered Sentinel-2 ImageCollection."""
    if cloud_pct is None:
        cloud_pct = CLOUD_THRESHOLD
    return (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start_str, end_str)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_pct))
    )


def get_before_after_composites(lat, lon, size_km, days_back=365, cloud_pct=None):
    """Main function: returns before/after ee.Image composites and date range string.

    Args:
        lat (float): Center latitude.
        lon (float): Center longitude.
        size_km (float): Side length of bounding box in km.
        days_back (int): How many days of history to use.
        cloud_pct (int): Max cloud cover % filter.

    Returns:
        tuple: (before_image, after_image, aoi, date_range_str)
    """
    if cloud_pct is None:
        cloud_pct = CLOUD_THRESHOLD

    aoi = get_bbox(lat, lon, size_km)

    end   = datetime.utcnow()
    start = end - timedelta(days=days_back)

    start_str = start.strftime("%Y-%m-%d")
    end_str   = end.strftime("%Y-%m-%d")

    col = get_s2_collection(aoi, start_str, end_str, cloud_pct)

    # "Before": median of oldest 20 scenes in the window
    before = col.limit(20).median().clip(aoi)

    # "After": median of the 5 most recent scenes
    after = col.sort("system:time_start", False).limit(5).median().clip(aoi)

    date_range = f"{start_str} to {end_str}"
    return before, after, aoi, date_range


if __name__ == "__main__":
    # Quick sanity test
    initialize_ee()
    before, after, aoi, dr = get_before_after_composites(
        lat=31.5, lon=78.5, size_km=20
    )
    print(f"Date range: {dr}")
    print(f"Before bands: {before.bandNames().getInfo()}")
    print(f"After  bands: {after.bandNames().getInfo()}")
    print("gee_fetch.py OK")
