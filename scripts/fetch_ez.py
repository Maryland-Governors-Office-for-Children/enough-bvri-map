#!/usr/bin/env python3
"""
Fetch Maryland Enterprise Zones (and Enterprise Zone Focus Areas) from the
Maryland iMap MD_IncentiveZones ArcGIS service (MD Dept. of Commerce data).

Source service:
  https://mdgeodata.md.gov/imap/rest/services/BusinessEconomy/MD_IncentiveZones/FeatureServer
    Layer 4 — Enterprise Zones            (~32 statewide polygons)
    Layer 5 — Enterprise Zone Focus Areas (enhanced-credit sub-areas)

Enterprise Zones are a MD Commerce tax-incentive program: businesses locating in
a zone may qualify for real-property and income tax credits. Focus Areas are
sub-areas within a zone that carry enhanced credits.

Writes docs/data/ez_maryland.geojson with a `focus_area` flag distinguishing the
two layers, so the map can render/label them separately.
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent.parent / "docs" / "data" / "ez_maryland.geojson"

BASE = ("https://mdgeodata.md.gov/imap/rest/services/BusinessEconomy/"
        "MD_IncentiveZones/FeatureServer")

def fetch_layer(layer_id):
    all_features = []
    offset = 0
    page_size = 500
    while True:
        params = urllib.parse.urlencode({
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultRecordCount": page_size,
            "resultOffset": offset,
        })
        url = f"{BASE}/{layer_id}/query?{params}"
        print(f"  Layer {layer_id}: fetching offset={offset}...")
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())
        batch = data.get("features", [])
        all_features.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return all_features


def build(features, is_focus):
    out = []
    for f in features:
        p = f.get("properties", {})
        out.append({
            "type": "Feature",
            "geometry": f.get("geometry"),
            "properties": {
                "sitename": p.get("sitename"),
                "orgname": p.get("orgname"),
                "address": p.get("streetaddr"),
                "city": p.get("city"),
                "county": p.get("county"),
                "zip": p.get("zip"),
                "website": p.get("website"),
                "extent": p.get("extent"),
                "expiration": p.get("Expiration"),  # epoch ms (null for focus areas)
                "focus_area": is_focus,
            },
        })
    return out


def main():
    print("Fetching Maryland Enterprise Zones...")
    zones = build(fetch_layer(4), False)
    focus = build(fetch_layer(5), True)
    features = zones + focus

    out = {"type": "FeatureCollection", "features": features}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh)

    print(f"\nWrote {OUT}")
    print(f"  Enterprise Zones: {len(zones)}")
    print(f"  Focus Areas:      {len(focus)}")
    print(f"  Total features:   {len(features)}")


if __name__ == "__main__":
    main()
