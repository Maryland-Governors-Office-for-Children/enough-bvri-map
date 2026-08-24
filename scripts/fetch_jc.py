#!/usr/bin/env python3
"""
Fetch Maryland's designated Just Communities from the Maryland iMap
MD_HousingDesignatedAreas ArcGIS service (MD DHCD data).

Source service:
  https://mdgeodata.md.gov/imap/rest/services/BusinessEconomy/MD_HousingDesignatedAreas/FeatureServer/9
    Layer 9 — Just Communities (419 designated census tracts statewide)

Just Communities were created by the **Just Communities Act of 2024**
(Maryland HB 241 / SB 308). MD DHCD's Division of Just Communities, working with
the Eastern Shore Regional GIS Cooperative (ESRGC), scored every Maryland census
tract against the legislatively mandated criteria — Priority Funding Area status,
homeownership, property-value and vacancy trends, history of redlining, state
imprisonment rate, Superfund proximity, lead-paint exposure, and adult asthma
rates — and designated the tracts scoring >= 13.5 on the resulting Just
Communities Index. That threshold cut 1,439 candidate tracts down to 419.
Designation targets State funding and investment to historically disinvested
areas. (Methodology Report v1.0, 2025-04-23.)

Backing tract boundaries: 2020 U.S. Census tracts — so these join to the ENOUGH
grantee tracts on an exact GEOID match (no geometric threshold needed).

Note: this is the same 419-tract layer published in DHCD's public Just
Communities Viewer (the ArcGIS Experience app). A narrower internal
"Refined Just Communities Designations" layer (398 tracts, a strict subset)
also exists in ArcGIS Online, but 419 is the count the State publishes as
designated, so that is what this script pulls.

Writes docs/data/just_communities_maryland.geojson.
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent.parent / "docs" / "data" / "just_communities_maryland.geojson"

BASE = ("https://mdgeodata.md.gov/imap/rest/services/BusinessEconomy/"
        "MD_HousingDesignatedAreas/FeatureServer/9/query")

FIELDS = [
    "GEOID", "NAMELSAD", "County",
    "RECAP", "HistoryOfRedlining",
    "VacantHousingUnitsPer", "OwnerOccupiedHousingUnits",
    "SevereHouseBurdentRenters", "SevereHouseBurdenHomeowners",
    "LeadPaintExposurePer", "SuperfundProximityPerc",
    "AsthmaRate", "ImprisonmentRate",
]


def fetch_just_communities():
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
        with urllib.request.urlopen(url, timeout=60) as r:
            data = json.loads(r.read())
        batch = data.get("features", [])
        all_features.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return all_features


def to_float(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).strip())
    except ValueError:
        return None


def round_coords(obj, ndigits=5):
    """Round coordinate precision in place. The iMap service returns ~14 decimal
    places (sub-nanometer); 5 decimals is ~1 m, far finer than tract boundaries
    need, and roughly halves the geojson the browser has to download."""
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(c), ndigits) for c in obj]
        return [round_coords(o, ndigits) for o in obj]
    return obj


def yes_no(v):
    """Normalize the Yes / No / 'No Data Available' string fields to a bool or None."""
    if v is None:
        return None
    s = str(v).strip().lower()
    if s == "yes":
        return True
    if s == "no":
        return False
    return None


def main():
    print("Fetching designated Just Communities for Maryland...")
    features = fetch_just_communities()
    print(f"  Got {len(features)} Just Communities tracts")

    out_features = []
    for f in features:
        p = f.get("properties", {})
        geom = f.get("geometry")
        if geom and geom.get("coordinates") is not None:
            geom = dict(geom, coordinates=round_coords(geom["coordinates"]))
        out_features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "GEOID": p.get("GEOID"),
                "tract_name": p.get("NAMELSAD"),
                "county": p.get("County"),
                # Designation-criteria indicators, kept for the map popup.
                "recap": yes_no(p.get("RECAP")),
                "redlining": yes_no(p.get("HistoryOfRedlining")),
                "vacant_housing_pct": to_float(p.get("VacantHousingUnitsPer")),
                "owner_occupied_pct": to_float(p.get("OwnerOccupiedHousingUnits")),
                "cost_burden_renters_pct": to_float(p.get("SevereHouseBurdentRenters")),
                "cost_burden_owners_pct": to_float(p.get("SevereHouseBurdenHomeowners")),
                "lead_paint_index": to_float(p.get("LeadPaintExposurePer")),
                "superfund_proximity_pctile": to_float(p.get("SuperfundProximityPerc")),
                "asthma_pctile": to_float(p.get("AsthmaRate")),
                "imprisonment_rate": to_float(p.get("ImprisonmentRate")),
            },
        })

    out = {"type": "FeatureCollection", "features": out_features}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh)

    n_recap = sum(1 for f in out_features if f["properties"]["recap"])
    n_red = sum(1 for f in out_features if f["properties"]["redlining"])
    print(f"\nWrote {OUT}")
    print(f"  Total: {len(out_features)} designated Just Communities")
    print(f"  R/ECAP: {n_recap} | History of redlining: {n_red}")


if __name__ == "__main__":
    main()
