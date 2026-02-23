# backend/process_change.py
# OpenCV-based change detection pipeline.
# Takes before/after numpy arrays and returns change stats + mask.

import cv2
import numpy as np
import rasterio
from pathlib import Path
import json
import sys
import os
from io import BytesIO
import requests
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CHANGE_THRESHOLD


def normalize_array(arr):
    """Normalize a float32 array to uint8 (0-255)."""
    return cv2.normalize(arr, None, 0, 255, cv2.NORM_MINMAX).astype("uint8")


def compute_diff(before_uint8, after_uint8):
    """Compute absolute pixel difference between two uint8 arrays."""
    return cv2.absdiff(after_uint8, before_uint8)


def threshold_mask(diff, threshold=None):
    """Apply binary threshold and morphological cleanup to diff image."""
    if threshold is None:
        threshold = CHANGE_THRESHOLD
    _, mask = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def count_changes(mask):
    """Return (change_pixels, total_pixels, change_pct)."""
    change_pixels = int(np.sum(mask == 255))
    total_pixels  = mask.size
    change_pct    = round(change_pixels / total_pixels * 100, 2)
    return change_pixels, total_pixels, change_pct


def process_arrays(before_arr, after_arr, threshold=None):
    """End-to-end pipeline from raw float arrays to stats.

    Args:
        before_arr: numpy float array of before image
        after_arr:  numpy float array of after image
        threshold:  int pixel diff threshold (default: from config)

    Returns:
        dict with keys: before_n, after_n, diff, mask,
                        change_pixels, total_pixels, change_pct
    """
    before_n = normalize_array(before_arr.astype("float32"))
    after_n  = normalize_array(after_arr.astype("float32"))
    diff     = compute_diff(before_n, after_n)
    mask     = threshold_mask(diff, threshold)
    change_pixels, total_pixels, change_pct = count_changes(mask)

    return {
        "before_n":      before_n,
        "after_n":       after_n,
        "diff":          diff,
        "mask":          mask,
        "change_pixels": change_pixels,
        "total_pixels":  total_pixels,
        "change_pct":    change_pct
    }


def process_tif_files(before_path, after_path, out_dir, threshold=None):
    """Process two GeoTIFF files and save output PNGs + meta.json to out_dir.

    Args:
        before_path (str): Path to before .tif
        after_path  (str): Path to after  .tif
        out_dir     (str): Directory to save outputs
        threshold   (int): Pixel change threshold

    Returns:
        dict: metadata with stats
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with rasterio.open(before_path) as src:
        before_arr = src.read(1).astype("float32")
    with rasterio.open(after_path) as src:
        after_arr  = src.read(1).astype("float32")

    result = process_arrays(before_arr, after_arr, threshold)

    # Save 512x512 thumbnails
    size = (512, 512)
    cv2.imwrite(str(out_dir / "before_thumb.png"),      cv2.resize(result["before_n"], size))
    cv2.imwrite(str(out_dir / "after_thumb.png"),       cv2.resize(result["after_n"],  size))
    cv2.imwrite(str(out_dir / "diff_thumb.png"),        cv2.resize(result["diff"],     size))
    cv2.imwrite(str(out_dir / "change_mask_thumb.png"), cv2.resize(result["mask"],     size))

    meta = {
        "change_pixels": result["change_pixels"],
        "total_pixels":  result["total_pixels"],
        "change_pct":    result["change_pct"]
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run change detection on two GeoTIFF files.")
    parser.add_argument("before",  help="Path to before .tif")
    parser.add_argument("after",   help="Path to after  .tif")
    parser.add_argument("out_dir", help="Output directory for PNGs + meta.json")
    parser.add_argument("--threshold", type=int, default=None)
    args = parser.parse_args()

    meta = process_tif_files(args.before, args.after, args.out_dir, args.threshold)
    print(f"Change pixels : {meta['change_pixels']}")
    print(f"Change area % : {meta['change_pct']}%")
    print(f"Outputs saved : {args.out_dir}")
