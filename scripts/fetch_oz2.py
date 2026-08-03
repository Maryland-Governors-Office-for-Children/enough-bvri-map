#!/usr/bin/env python3
"""
Fetch Maryland's OZ 2.0 *eligible* census tracts + the rural/non-rural flag for
the already-designated (2018) Opportunity Zones from OpportunityZones.com.

Source page:
  https://opportunityzones.com/location/maryland/

That page publishes two tables this project reuses:
  1. Current OZs (Designated 2018) — 149 tracts, each flagged Rural / Non-Rural.
     The map already carries these tracts' geometry (oz_designated_maryland.geojson,
     from MD iMap); this script only *annotates* that file with the rural flag.
  2. Future OZ 2.0 Designations — 451 census tracts that meet the OZ 2.0 statutory
     median-family-income and/or poverty thresholds (per OpportunityZones.com's
     analysis of the 2020–2024 ACS, released 2026-01-29), each with an MFI ratio
     and poverty rate. Maryland may nominate up to 113 of these (25% cap); new
     designations take effect 2027-01-01. This is a *candidate/eligibility* layer,
     not a designation.

The OZ 2.0 tracts are 2020-vintage census tracts — their GEOIDs match the
statewide tract geometry used to build grantee_tracts.geojson, so we attach real
tract polygons by GEOID join (no geometry is scraped from the source page).

Statewide tract geometry source (2020 tracts, 2024 ACS attributes):
  ../enough-eligibility-analysis/docs/data/tracts_2026.geojson  (GEOID20 key)

Writes:
  docs/data/oz2_eligible_maryland.geojson      (451 eligible tracts + MFI/poverty)
  docs/data/oz_designated_maryland.geojson     (rewritten with a `rural` flag)
"""

import json
import re
import urllib.request
from pathlib import Path

PAGE = "https://opportunityzones.com/location/maryland/"
DATA = Path(__file__).parent.parent / "docs" / "data"
TRACTS_SRC = (Path(__file__).parent.parent.parent
              / "enough-eligibility-analysis" / "docs" / "data" / "tracts_2026.geojson")

OZ2_OUT = DATA / "oz2_eligible_maryland.geojson"
DESIG = DATA / "oz_designated_maryland.geojson"


def fetch_html():
    req = urllib.request.Request(PAGE, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "ignore")


def parse_tables(html):
    """Return (designated, eligible) row lists from the two page tables."""
    tables = re.findall(r"(?is)<table.*?</table>", html)

    def rows_of(t):
        out = []
        for tr in re.findall(r"(?is)<tr.*?</tr>", t):
            cells = [re.sub(r"<[^>]+>", "", c).replace("&#x27;", "'").strip()
                     for c in re.findall(r"(?is)<td[^>]*>(.*?)</td>", tr)]
            if cells:
                out.append(cells)
        return out

    designated = rows_of(tables[0])   # [County, GEOID, Type]
    eligible = rows_of(tables[1])     # [County, GEOID, MFI Ratio, Poverty]
    return designated, eligible


def load_tract_geometry():
    """GEOID20 -> geometry, from the statewide 2020-tract source."""
    src = json.load(open(TRACTS_SRC))
    return {f["properties"]["GEOID20"]: f["geometry"] for f in src["features"]}


def pct(v):
    if v in (None, "", "—"):
        return None
    try:
        return float(str(v).replace("%", "").strip())
    except ValueError:
        return None


def build_eligible(eligible, geom_by_geoid):
    feats, missing = [], []
    for county, geoid, mfi, pov in eligible:
        g = geom_by_geoid.get(geoid)
        if g is None:
            missing.append(geoid)
            continue
        feats.append({
            "type": "Feature",
            "geometry": g,
            "properties": {
                "GEOID": geoid,
                "county": county,
                "mfi_ratio": pct(mfi),      # median family income vs. area, %
                "poverty": pct(pov),        # poverty rate, %
            },
        })
    return feats, missing


def annotate_designated(designated):
    """Add a `rural` boolean to the existing designated-OZ geojson, by GEOID."""
    rural_by_geoid = {geoid: (typ.strip().lower() == "rural")
                      for county, geoid, typ in designated}
    oz = json.load(open(DESIG))
    matched = 0
    for f in oz["features"]:
        geoid = f["properties"].get("GEOID")
        if geoid in rural_by_geoid:
            f["properties"]["rural"] = rural_by_geoid[geoid]
            matched += 1
        else:
            f["properties"]["rural"] = None
    return oz, matched, len(rural_by_geoid)


def main():
    print(f"Fetching {PAGE} ...")
    html = fetch_html()
    designated, eligible = parse_tables(html)
    print(f"  parsed {len(designated)} designated rows, {len(eligible)} eligible rows")

    geom = load_tract_geometry()
    feats, missing = build_eligible(eligible, geom)
    print(f"  matched geometry for {len(feats)}/{len(eligible)} eligible tracts")
    if missing:
        print(f"  WARNING: no geometry for {len(missing)} eligible GEOIDs: {missing}")

    json.dump({"type": "FeatureCollection", "features": feats}, open(OZ2_OUT, "w"))
    print(f"Wrote {OZ2_OUT} ({len(feats)} tracts)")

    oz, matched, n = annotate_designated(designated)
    n_rural = sum(1 for f in oz["features"] if f["properties"].get("rural"))
    json.dump(oz, open(DESIG, "w"))
    print(f"Wrote {DESIG} (rural flag on {matched}/{n} designated; {n_rural} rural)")


if __name__ == "__main__":
    main()
