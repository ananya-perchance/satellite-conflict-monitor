# How to Export Before/After Images for an AOI (Manual Method)

The Streamlit app fetches imagery live and does NOT need this process.
This guide is only needed if you want to download raw GeoTIFF files for offline processing
using `process_change.py` directly.

---

## Step 1: Get coordinates for your region

1. Go to [Google Maps](https://maps.google.com) or [Google Earth Web](https://earth.google.com/web)
2. Navigate to your region of interest
3. Right-click to get exact lat/lon
4. Note the approximate size of your area in km

---

## Step 2: Export images from Earth Engine Code Editor

1. Go to https://code.earthengine.google.com
2. Paste the following JavaScript:

```javascript
// Replace these with your actual coordinates
var lon_min = 78.0,
    lat_min = 31.0,
    lon_max = 79.0,
    lat_max = 32.0;

var bounds = ee.Geometry.Rectangle([lon_min, lat_min, lon_max, lat_max]);

// Date range for "before" composite
var before_start = '2024-01-01';
var before_end   = '2024-06-30';

// Date range for "after" composite
var after_start  = '2025-01-01';
var after_end    = '2025-06-30';

var col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(bounds)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20));

var before = col.filterDate(before_start, before_end).median().clip(bounds);
var after  = col.filterDate(after_start,  after_end ).median().clip(bounds);

// Visualize (optional)
Map.centerObject(bounds, 12);
Map.addLayer(before, {bands:['B4','B3','B2'], min:0, max:3000}, 'Before');
Map.addLayer(after,  {bands:['B4','B3','B2'], min:0, max:3000}, 'After');

// Export Band B4 only (grayscale for change detection)
Export.image.toDrive({
  image: before.select('B4'),
  description: 'my_aoi_before',
  folder: 'conflict_monitor',
  region: bounds,
  scale: 10,
  maxPixels: 1e9
});

Export.image.toDrive({
  image: after.select('B4'),
  description: 'my_aoi_after',
  folder: 'conflict_monitor',
  region: bounds,
  scale: 10,
  maxPixels: 1e9
});
```

3. Click **Run**
4. Go to the **Tasks** tab (top right)
5. Click **Run** next to each export task
6. Wait for tasks to complete (5-15 minutes)

---

## Step 3: Download the files

1. Go to [Google Drive](https://drive.google.com)
2. Find the folder `conflict_monitor`
3. Download:
   - `my_aoi_before.tif`
   - `my_aoi_after.tif`
4. Place them in your local `data/raw/` folder:
   ```
   data/raw/my_aoi_before.tif
   data/raw/my_aoi_after.tif
   ```

---

## Step 4: Run offline change detection

```bash
python backend/process_change.py \
  data/raw/my_aoi_before.tif \
  data/raw/my_aoi_after.tif \
  data/processed/my_aoi
```

Output files in `data/processed/my_aoi/`:
- `before_thumb.png`
- `after_thumb.png`
- `diff_thumb.png`
- `change_mask_thumb.png`
- `meta.json` (stats)

---

## Notes

- `scale: 10` means 10 metres per pixel (native Sentinel-2 resolution for B4)
- Exporting large areas takes longer; start with a small box (20-50 km)
- Cloud cover > 20% will produce noisy results; adjust the filter if needed
- The `maxPixels: 1e9` limit handles most region sizes up to ~100km x 100km
