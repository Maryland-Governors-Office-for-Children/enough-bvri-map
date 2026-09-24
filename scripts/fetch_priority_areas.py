#!/usr/bin/env python3
"""
Fetch Baltimore City DHCD's vacancy-reduction priority geographies.

These are the areas DHCD's own Vacants Reinvestment Council dashboard filters its
Vacants Reduction page by — i.e. where the City has said it is concentrating
vacant-property work. Putting them beside the ENOUGH grantee tracts answers a
question GOC cannot otherwise answer: **is the City's own targeting reaching
ENOUGH neighborhoods, and which ENOUGH tracts sit in no priority area at all?**
The second half of that is the useful half — it is a concrete list to take to DHCD
rather than a general complaint.

Sources (Baltimore City DHCD, dmxFocusAreas):
  .../Housing/dmxFocusAreas/MapServer/1   "Other Vacancy Reduction Priority
                                           Geographies" — 25 named areas
  .../Housing/dmxFocusAreas/MapServer/2   "Major Redevelopment" — 6 named areas
Layer 0 of the same service is Impact Investment Areas, already on the map as
bvri_investment_areas.geojson, so it is not re-fetched here.

The service publishes in a projected CRS (areas are in square feet), so outSR=4326
is requested explicitly.

Writes docs/data/priority_areas_baltimore.geojson with `name` and `category`.
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent.parent / "docs" / "data" / "priority_areas_baltimore.geojson"
BASE = ("https://egisdata.baltimorecity.gov/egis/rest/services/Housing/"
        "dmxFocusAreas/MapServer")
LAYERS = [(1, "Vacancy Reduction Priority Geography"),
          (2, "Major Redevelopment")]


def fetch(layer):
    params = urllib.parse.urlencode({
        "where": "1=1", "outFields": "Name", "returnGeometry": "true",
        "outSR": "4326", "f": "geojson", "resultRecordCount": 1000,
    })
    with urllib.request.urlopen(f"{BASE}/{layer}/query?{params}", timeout=90) as r:
        return json.loads(r.read()).get("features", [])


def round_coords(obj, nd=5):
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(c), nd) for c in obj]
        return [round_coords(o, nd) for o in obj]
    return obj


def main():
    feats = []
    for layer, category in LAYERS:
        got = fetch(layer)
        print(f"  Layer {layer} ({category}): {len(got)} areas")
        for f in got:
            geom = f.get("geometry")
            if not geom:
                continue
            name = (f.get("properties") or {}).get("Name")
            feats.append({
                "type": "Feature",
                "geometry": dict(geom, coordinates=round_coords(geom["coordinates"])),
                "properties": {"name": name, "category": category},
            })
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    print(f"\nWrote {OUT}")
    print(f"  {len(feats)} priority areas: "
          + ", ".join(sorted(f["properties"]["name"] or "?" for f in feats)[:8]) + " ...")


if __name__ == "__main__":
    main()
