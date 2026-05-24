# Missing Women Rider Route Tool

Fresh mobile-first rider app. Run with `python3 -m http.server 5500` from this folder and open `http://localhost:5500`.

Noise logs and trip completion status are now saved in Supabase.

## Data Export

Export data from Supabase:

```bash
python3 export_data.py
```

This creates timestamped exports in `exports/` with manifest.json and images.

## Export to Analysis Repos

Export data to streetaqi or soundscape for analysis:

```bash
# Export pollution data to streetaqi (includes reverse geocoding)
python3 export.py --type pollution --manifest exports/export-2026-05-24/manifest.json

# Export sound data to soundscape
python3 export.py --type sound --manifest exports/export-2026-05-24/manifest.json

# Skip geocoding (faster)
python3 export.py --type pollution --manifest exports/export-2026-05-24/manifest.json --no-geocode
```

## Air Quality Analysis

Air quality analysis tools have moved to [streetaqi](https://github.com/soodoku/streetaqi):

```bash
pip install streetaqi[all]
streetaqi analyze --readings exports/pollution_logs.csv --output output/analysis
```
