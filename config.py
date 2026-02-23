# config.py
# Global configuration: Areas of Interest and thresholds

AOIS = {
    "ladakh_base_1": {
        "name": "Ladakh Forward Base",
        "bounds": [78.0, 31.0, 79.0, 32.0],
        "description": "Indian Army base region near the LAC with China."
    },
    "spratly_reef": {
        "name": "Spratly Island Reef",
        "bounds": [111.9, 10.8, 114.5, 11.5],
        "description": "Disputed reef in the South China Sea with artificial island building."
    }
}

# % cloud cover allowed in Sentinel-2 imagery
CLOUD_THRESHOLD = 20

# Pixel difference threshold for change detection
CHANGE_THRESHOLD = 25
