#!/usr/bin/env python3
"""
Fetch Maryland's official 2026 Opportunity Zones eligibility from the
Maryland Department of Commerce / state portal ArcGIS service.

Source service:
  https://services.arcgis.com/njFNhDsUCentVYJW/arcgis/rest/services/
    Maryland_Official_Eligible_Opportunity_Zones_Census_Tracts_2026/FeatureServer/0

Owned by: BRAD.WOLTERS@maryland.gov_maryland (Maryland portal)
Backing data: EIG (Economic Innovation Group) eligibility map, ACS 2020-2024
Vintage: CY 2026 (preliminary, pending federal guidance)

Filters to oz_elig='OZ Eligible' to keep the file tight (~451 tracts).
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent.parent / "docs" / "data" / "oz_maryland.geojson"

BASE = ("https://services.arcgis.com/njFNhDsUCentVYJW/arcgis/rest/services/"
        "Maryland_Official_Eligible_Opportunity_Zones_Census_Tracts_2026/FeatureServer/0/query")

FIELDS = [
    "GEOID", "NAME", "oz_elig", "pov_rte", "mfi_rat",
    "rural_g", "rrl_trs", "STATE_N", "COUNTY_", "msa",
]


def fetch_eligible():
    all_features = []
    offset = 0
    page_size = 1000
    while True:
        params = urllib.parse.urlencode({
            "where": "oz_elig='OZ Eligible'",
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
    s = str(v).strip().rstrip("%")
    try:
        return float(s)
    except ValueError:
        return None


def main():
    print("Fetching Opportunity Zones eligible tracts for Maryland...")
    features = fetch_eligible()
    print(f"  Got {len(features)} OZ-eligible tracts")

    out_features = []
    rural_counts = {"Rural": 0, "Non-rural": 0, "Other": 0}
    for f in features:
        p = f.get("properties", {})
        rural = (p.get("rural_g") or "").strip()
        if rural == "Rural":
            rural_counts["Rural"] += 1
        elif rural == "Non-rural":
            rural_counts["Non-rural"] += 1
        else:
            rural_counts["Other"] += 1
        out_features.append({
            "type": "Feature",
            "geometry": f.get("geometry"),
            "properties": {
                "GEOID": p.get("GEOID"),
                "NAME": p.get("NAME"),
                "county": p.get("COUNTY_"),
                "state": p.get("STATE_N"),
                "msa": p.get("msa"),
                "oz_elig": p.get("oz_elig"),
                "rural": rural or None,
                "rural_targeted": p.get("rrl_trs"),
                "poverty_rate": to_float(p.get("pov_rte")),
                "mfi_ratio": to_float(p.get("mfi_rat")),
            },
        })

    out = {"type": "FeatureCollection", "features": out_features}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh)

    print(f"\nWrote {OUT}")
    print(f"  Total: {len(out_features)} OZ-eligible tracts")
    for k, n in rural_counts.items():
        print(f"  {k}: {n}")


if __name__ == "__main__":
    main()
