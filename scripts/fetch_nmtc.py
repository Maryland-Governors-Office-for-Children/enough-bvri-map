#!/usr/bin/env python3
"""
Fetch NMTC eligibility data for Baltimore City from CDFI Fund's authoritative
ArcGIS feature service (NMTC_Qualified_Tracts_2020), compute the distress
classification, and write docs/data/nmtc_baltimore.geojson.

Source:
  https://services6.arcgis.com/BAJNi3EgCdtQ1BCG/arcgis/rest/services/NMTC_Qualified_Tracts_2020/FeatureServer/3
  Owner: layermanager (publicly authoritative, marked CDFI Fund as source)
  Data vintage: 2020 Census Tracts + 2016-2020 ACS

Classification (matches PolicyMap categories):
  - "Severe Distress"     — income ≤ 60% benchmark OR poverty ≥ 30% OR unemployment ratio ≥ 1.5
  - "Distressed"          — income ≤ 80% benchmark OR poverty ≥ 20%
  - "Eligible"            — qualifies for NMTC LIC but not in the above tiers
  - "Not Eligible"        — does not qualify
  - "Insufficient Data"   — missing inputs
"""

import json
import urllib.request
import urllib.parse
from pathlib import Path

OUT = Path(__file__).parent.parent / "docs" / "data" / "nmtc_maryland.geojson"

BASE = ("https://services6.arcgis.com/BAJNi3EgCdtQ1BCG/arcgis/rest/services/"
        "NMTC_Qualified_Tracts_2020/FeatureServer/3/query")

FIELDS = [
    "FIPS", "STATE_FIPS", "COUNTY_FIPS", "STCOFIPS",
    "Does_Census_Tract_Qualify_For_N",
    "Census_Tract_Poverty_Rate____20",
    "Census_Tract_Percent_of_Benchma",
    "Census_Tract_Unemployment_to_Na",
    "OMB_Metro_Non_metro_Designation",
]


def to_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def classify(props):
    qualifies = (props.get("Does_Census_Tract_Qualify_For_N") or "").upper()
    poverty = to_float(props.get("Census_Tract_Poverty_Rate____20"))
    income_pct = to_float(props.get("Census_Tract_Percent_of_Benchma"))
    unemp_ratio = to_float(props.get("Census_Tract_Unemployment_to_Na"))

    if qualifies == "NO":
        return "Not Eligible"
    if poverty is None and income_pct is None and unemp_ratio is None:
        return "Insufficient Data"

    income_pct_pct = income_pct * 100 if income_pct is not None and income_pct <= 1.5 else income_pct
    severe = (
        (income_pct_pct is not None and income_pct_pct <= 60) or
        (poverty is not None and poverty >= 30) or
        (unemp_ratio is not None and unemp_ratio >= 1.5)
    )
    if severe:
        return "Severe Distress"

    distressed = (
        (income_pct_pct is not None and income_pct_pct <= 80) or
        (poverty is not None and poverty >= 20)
    )
    if distressed:
        return "Distressed"

    if qualifies == "YES":
        return "Eligible"
    return "Not Eligible"


def fetch_maryland():
    all_features = []
    offset = 0
    page_size = 1000
    while True:
        params = urllib.parse.urlencode({
            "where": "STATE_FIPS='24'",
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


def main():
    print("Fetching NMTC tracts for Maryland (STATE_FIPS=24)...")
    features = fetch_maryland()
    print(f"  Got {len(features)} tracts")

    # Slim and classify
    out_features = []
    counts = {}
    for f in features:
        p = f.get("properties", {})
        klass = classify(p)
        counts[klass] = counts.get(klass, 0) + 1
        out_features.append({
            "type": "Feature",
            "geometry": f.get("geometry"),
            "properties": {
                "FIPS": p.get("FIPS"),
                "nmtc_class": klass,
                "qualifies": p.get("Does_Census_Tract_Qualify_For_N"),
                "poverty_pct": to_float(p.get("Census_Tract_Poverty_Rate____20")),
                "income_pct_benchmark": to_float(p.get("Census_Tract_Percent_of_Benchma")),
                "unemployment_ratio": to_float(p.get("Census_Tract_Unemployment_to_Na")),
                "metro": p.get("OMB_Metro_Non_metro_Designation"),
            },
        })

    out = {"type": "FeatureCollection", "features": out_features}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh)

    print(f"\nWrote {OUT}")
    print("Classification breakdown:")
    for k, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {n}")


if __name__ == "__main__":
    main()
