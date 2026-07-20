#!/usr/bin/env python3
"""
Fetch Maryland's DESIGNATED Opportunity Zones from the Maryland iMap
MD_IncentiveZones ArcGIS service (MD DHCD / MD Dept. of Commerce data).

Source service:
  https://mdgeodata.md.gov/imap/rest/services/BusinessEconomy/MD_IncentiveZones/FeatureServer/14
    Layer 14 — Opportunity Zones (149 designated census tracts statewide)

These are the Opportunity Zones designated under the 2017 Tax Cuts and Jobs Act
(IRS Notice 2018-48): Maryland nominated 149 low-income 2010 census tracts, which
the U.S. Treasury approved. The designation runs for a decade (in effect through
2028). This is distinct from the preliminary OZ 2.0 *eligible* tracts — this layer
is the officially designated zones only.

Backing tract boundaries: 2010 U.S. Census tracts.

Writes docs/data/oz_designated_maryland.geojson.
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent.parent / "docs" / "data" / "oz_designated_maryland.geojson"

BASE = ("https://mdgeodata.md.gov/imap/rest/services/BusinessEconomy/"
        "MD_IncentiveZones/FeatureServer/14/query")

FIELDS = ["CT_2010", "COUNTY_N", "Selected_T", "MHI"]


def fetch_designated():
    all_features = []
    offset = 0
    page_size = 500
    while True:
        params = urllib.parse.urlencode({
            "where": "1=1",
            "outFields": ",".join(FIELDS),
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultRecordCount": page_size,
            "resultOffset": offset,
        })
        url = f"{BASE}?{params}"
        print(f"  Fetching offset={offset}...")
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())
        batch = data.get("features", [])
        all_features.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return all_features


def to_float(v):
    if v is None:
        return None
    try:
        return float(str(v).strip())
    except ValueError:
        return None


def main():
    print("Fetching DESIGNATED Opportunity Zones for Maryland...")
    features = fetch_designated()
    print(f"  Got {len(features)} designated OZ tracts")

    out_features = []
    for f in features:
        p = f.get("properties", {})
        out_features.append({
            "type": "Feature",
            "geometry": f.get("geometry"),
            "properties": {
                "GEOID": p.get("CT_2010"),
                "county": p.get("COUNTY_N"),
                "designated": p.get("Selected_T"),
                "mhi": to_float(p.get("MHI")),
            },
        })

    out = {"type": "FeatureCollection", "features": out_features}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh)

    print(f"\nWrote {OUT}")
    print(f"  Total: {len(out_features)} designated Opportunity Zones")


if __name__ == "__main__":
    main()
