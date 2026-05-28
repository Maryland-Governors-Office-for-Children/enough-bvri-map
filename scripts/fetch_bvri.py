#!/usr/bin/env python3
"""
Fetch BVRI-related data from Baltimore City DHCD ArcGIS REST services.
Outputs docs/data/bvri_vacants.geojson and docs/data/bvri_investment_areas.geojson.

Run: uv run python scripts/fetch_bvri.py
"""

import json
import urllib.request
import urllib.parse
from pathlib import Path

OUT_DIR = Path(__file__).parent.parent / "docs" / "data"

BASE = "https://egisdata.baltimorecity.gov/egis/rest/services/Housing/DHCD_Open_Baltimore_Datasets/FeatureServer"

def fetch_layer(layer_id, fields, label, page_size=1000):
    all_features = []
    offset = 0
    while True:
        params = urllib.parse.urlencode({
            "where": "1=1",
            "returnGeometry": "true",
            "outFields": ",".join(fields),
            "f": "geojson",
            "resultRecordCount": page_size,
            "resultOffset": offset,
        })
        url = f"{BASE}/{layer_id}/query?{params}"
        print(f"  Fetching {label} offset={offset}...")
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())
        batch = data.get("features", [])
        all_features.extend(batch)
        if len(batch) < page_size or not data.get("exceededTransferLimit"):
            break
        offset += page_size
    print(f"  Total: {len(all_features)} features")
    return {"type": "FeatureCollection", "features": all_features}

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Layer 7: Vacants to Value (open bid list — core BVRI properties)
    vacants = fetch_layer(
        layer_id=7,
        fields=["Address", "Status", "Neighborhood", "BlockLot", "HousingMarketTypology2017"],
        label="Vacants to Value",
    )
    out_path = OUT_DIR / "bvri_vacants.geojson"
    with open(out_path, "w") as f:
        json.dump(vacants, f)
    print(f"  Written to {out_path}")

    # Layer 10: Impact Investment Areas (neighborhood polygons)
    investment_areas = fetch_layer(
        layer_id=10,
        fields=["Name", "OBJECTID"],
        label="Impact Investment Areas",
    )
    out_path = OUT_DIR / "bvri_investment_areas.geojson"
    with open(out_path, "w") as f:
        json.dump(investment_areas, f)
    print(f"  Written to {out_path}")

    print("\nDone. Commit docs/data/bvri_vacants.geojson and docs/data/bvri_investment_areas.geojson.")

if __name__ == "__main__":
    main()
