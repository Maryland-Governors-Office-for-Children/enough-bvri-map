#!/usr/bin/env python3
"""Build docs/data/crosswalk.json — the ENOUGH × other-layer crosswalk.

For each non-grantee map layer, compute how many ENOUGH communities (grantee
organizations) and how many ENOUGH grantee tracts overlap that layer, plus a
per-grantee breakdown. Answers questions like "how many ENOUGH communities are
in an Enterprise Zone?" — and, inversely, which grantee tracts sit in *no* other
statewide investment program (where ENOUGH is the only lever).

Join method per layer:
  - NMTC  : exact GEOID match (grantee tracts and NMTC are both 2020-vintage tracts)
  - OZ    : geometric intersection (OZ polygons are 2010-vintage tracts)
  - EZ    : geometric intersection (irregular economic-development polygons)
  - DHCD  : geometric intersection (neighborhood polygons, Baltimore City only)
  - BVRI  : point-in-polygon (BVRI properties are points, Baltimore City only)

Geometric overlaps use a minimum-overlap-area threshold (MIN_OVERLAP_FRAC): a
tract counts as overlapping a polygon layer only if at least that fraction of
the tract's area falls inside it. This discards boundary slivers. The 5% value
is validated against the exact-GEOID join for Opportunity Zones — at 5% the
geometric method reproduces the exact-GEOID count (38), so it is not tuned to a
target so much as confirmed by an independent method.

Usage:
  python scripts/build_crosswalk.py           # rebuild docs/data/crosswalk.json
  python scripts/build_crosswalk.py --check    # verify committed JSON is fresh
                                               #   (exit 1 if source data drifted)

Requires shapely (not on system Python under PEP 668). Reproducible venv:
    python3 -m venv .venv-geo
    .venv-geo/bin/pip install -r scripts/requirements-crosswalk.txt
    .venv-geo/bin/python scripts/build_crosswalk.py
"""

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict

from shapely.geometry import shape, Point
from shapely.prepared import prep
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "docs", "data")

# A grantee tract counts as overlapping a polygon layer only if at least this
# fraction of the tract's area falls inside the layer. Filters boundary slivers.
MIN_OVERLAP_FRAC = 0.05

# Input files that feed the crosswalk. Hashed into the output so a --check run
# can detect when the committed crosswalk.json has gone stale vs. its sources.
SOURCE_FILES = [
    "grantee_tracts.geojson",
    "grantees.json",
    "nmtc_maryland.geojson",
    "oz_designated_maryland.geojson",
    "ez_maryland.geojson",
    "bvri_investment_areas.geojson",
    "bvri_vacants.geojson",
]

# The three statewide incentive layers, used for the "stacking" analysis. BVRI
# and DHCD are Baltimore-City-only, so they're excluded from the statewide
# gap count (a rural grantee tract can't be faulted for lacking a Baltimore
# vacant-property program).
STATEWIDE_LAYERS = ["nmtc", "oz", "ez"]


def load(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)


def source_hash():
    h = hashlib.sha256()
    for name in SOURCE_FILES:
        with open(os.path.join(DATA, name), "rb") as f:
            h.update(hashlib.sha256(f.read()).digest())
    return h.hexdigest()


def compute():
    grantee_tracts = load("grantee_tracts.geojson")
    grantees = load("grantees.json")["grantees"]
    nmtc = load("nmtc_maryland.geojson")
    oz = load("oz_designated_maryland.geojson")
    ez = load("ez_maryland.geojson")
    dhcd = load("bvri_investment_areas.geojson")
    bvri = load("bvri_vacants.geojson")

    # --- tract -> grantee(s) map (grantees.json is the source of truth; a few
    # tracts are shared by two grantees, so a tract can map to >1 grantee) ---
    tract_grantees = defaultdict(list)
    grantee_total_tracts = {}
    for g in grantees:
        grantee_total_tracts[g["name"]] = g["tract_count"]
        for t in g["tracts"]:
            tract_grantees[t].append(g["name"])

    # --- build grantee tract geometries keyed by GEOID ---
    tracts = {}  # geoid -> {geom, area, grantees:[...], county}
    for f in grantee_tracts["features"]:
        geoid = f["properties"]["GEOID20"]
        geom = shape(f["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        tracts[geoid] = {
            "geom": geom,
            "area": geom.area,
            "grantees": tract_grantees.get(geoid, [f["properties"].get("grantee_name")]),
            "jurscode": f["properties"].get("JURSCODE"),
        }

    all_geoids = set(tracts)
    total_tracts = len(all_geoids)
    total_grantees = len(grantees)
    shared_tracts = sum(1 for t in tracts.values() if len(t["grantees"]) > 1)

    def summarize(hit_geoids, label):
        """Roll a set of overlapping grantee-tract GEOIDs up to tract count,
        community count, and a per-grantee breakdown. NB: a tract shared by two
        grantees is attributed to both, so per-grantee tract counts can sum to
        more than tracts_overlapping (see shared_tracts)."""
        per_grantee = defaultdict(int)
        for geoid in hit_geoids:
            for gname in tracts[geoid]["grantees"]:
                per_grantee[gname] += 1
        breakdown = sorted(
            ({"grantee": k, "tracts": v,
              "grantee_total_tracts": grantee_total_tracts.get(k, v)}
             for k, v in per_grantee.items()),
            key=lambda r: (-r["tracts"], r["grantee"]),
        )
        return {
            "label": label,
            "tracts_overlapping": len(hit_geoids),
            "total_tracts": total_tracts,
            "communities_overlapping": len(per_grantee),
            "total_communities": total_grantees,
            "geoids": sorted(hit_geoids),
            "breakdown": breakdown,
        }

    results = {}

    # --- NMTC: exact GEOID match, split by distress tier ---
    nmtc_class = {str(f["properties"]["FIPS"]): f["properties"].get("nmtc_class")
                  for f in nmtc["features"]}
    nmtc_hits = all_geoids & set(nmtc_class)
    res = summarize(nmtc_hits, "NMTC-Eligible Tracts")
    tiers = defaultdict(int)
    for geoid in nmtc_hits:
        tiers[nmtc_class.get(geoid) or "Eligible"] += 1
    res["tiers"] = dict(tiers)
    res["join"] = "exact GEOID match (2020 tracts)"
    results["nmtc"] = res

    # --- helper: geometric intersection with area-fraction threshold ---
    # min_frac=0 counts any overlap (tract touches the layer at all); a positive
    # value requires that fraction of the tract's area to fall inside the layer.
    def polygon_layer_hits(features, filt=None, min_frac=MIN_OVERLAP_FRAC):
        polys = []
        for f in features:
            if filt and not filt(f):
                continue
            if not f.get("geometry"):
                continue
            g = shape(f["geometry"])
            if not g.is_valid:
                g = g.buffer(0)
            polys.append(g)
        merged = unary_union(polys)
        if not merged.is_valid:
            merged = merged.buffer(0)
        pmerged = prep(merged)
        hits = set()
        for geoid, t in tracts.items():
            if not pmerged.intersects(t["geom"]):
                continue
            if min_frac <= 0:
                hits.add(geoid)
                continue
            try:
                inter = merged.intersection(t["geom"]).area
            except Exception:
                inter = merged.intersection(t["geom"], grid_size=1e-9).area
            if t["area"] > 0 and inter / t["area"] >= min_frac:
                hits.add(geoid)
        return hits

    oz_hits = polygon_layer_hits(oz["features"])
    results["oz"] = summarize(oz_hits, "Designated Opportunity Zones")
    results["oz"]["join"] = f"geometric overlap ≥{int(MIN_OVERLAP_FRAC*100)}% of tract area"

    # Enterprise Zones: headline counts any overlap (a tract that touches a zone),
    # matching the state's Enterprise Zone lookup framing. We also compute the
    # stricter ≥5%-area count and expose it as a footnote figure.
    ez_filt = lambda f: not f["properties"].get("focus_area")
    ez_hits = polygon_layer_hits(ez["features"], filt=ez_filt, min_frac=0)
    ez_hits_5pct = polygon_layer_hits(ez["features"], filt=ez_filt, min_frac=MIN_OVERLAP_FRAC)
    results["ez"] = summarize(ez_hits, "Maryland Enterprise Zones")
    results["ez"]["join"] = "any geometric overlap (tract touches a zone)"
    results["ez"]["strict_5pct_tracts"] = len(ez_hits_5pct)
    results["ez"]["strict_5pct_communities"] = len(set(
        gn for geoid in ez_hits_5pct for gn in tracts[geoid]["grantees"]))

    dhcd_hits = polygon_layer_hits(dhcd["features"])
    results["dhcd"] = summarize(dhcd_hits, "DHCD Impact Investment Areas")
    results["dhcd"]["join"] = f"geometric overlap ≥{int(MIN_OVERLAP_FRAC*100)}% of tract area (Baltimore City only)"

    # --- BVRI Vacants to Value: point-in-polygon ---
    prepared_tracts = [(geoid, prep(t["geom"])) for geoid, t in tracts.items()]
    bvri_hits = set()          # grantee tract geoids containing >=1 BVRI point
    bvri_points_in = 0         # total BVRI points inside any grantee tract (unique)
    tract_bvri_pts = defaultdict(int)   # geoid -> point count
    for f in bvri["features"]:
        geom = f.get("geometry")
        if not geom or geom.get("type") != "Point":
            continue
        pt = Point(geom["coordinates"])
        for geoid, pg in prepared_tracts:
            if pg.contains(pt):
                bvri_hits.add(geoid)
                bvri_points_in += 1
                tract_bvri_pts[geoid] += 1
                break
    res = summarize(bvri_hits, "BVRI Vacants to Value")
    res["properties_total"] = sum(
        1 for f in bvri["features"] if (f.get("geometry") or {}).get("type") == "Point")
    res["properties_in_grantee_tracts"] = bvri_points_in
    res["join"] = "point-in-polygon (Baltimore City only)"
    # per-grantee BVRI property counts, from each grantee's own tracts
    for row in res["breakdown"]:
        gname = row["grantee"]
        row["properties"] = sum(
            tract_bvri_pts.get(geoid, 0)
            for geoid in bvri_hits if gname in tracts[geoid]["grantees"])
    results["bvri"] = res

    # --- Stacking / gap analysis across the three STATEWIDE layers ---
    layer_hitsets = {"nmtc": nmtc_hits, "oz": oz_hits, "ez": ez_hits}
    tract_layer_count = {}
    for geoid in all_geoids:
        tract_layer_count[geoid] = sum(
            1 for k in STATEWIDE_LAYERS if geoid in layer_hitsets[k])
    hist = defaultdict(int)
    for c in tract_layer_count.values():
        hist[c] += 1
    # tracts in zero statewide program — where ENOUGH is the only lever
    zero_geoids = sorted(g for g, c in tract_layer_count.items() if c == 0)
    zero_by_grantee = defaultdict(int)
    for g in zero_geoids:
        for gname in tracts[g]["grantees"]:
            zero_by_grantee[gname] += 1
    # communities with *no* statewide-program overlap on any tract
    covered_communities = set()
    for k in STATEWIDE_LAYERS:
        for geoid in layer_hitsets[k]:
            covered_communities.update(tracts[geoid]["grantees"])
    all_communities = set(grantee_total_tracts)
    stacking = {
        "layers_considered": STATEWIDE_LAYERS,
        "histogram": {str(i): hist.get(i, 0) for i in range(len(STATEWIDE_LAYERS) + 1)},
        "tracts_in_zero": len(zero_geoids),
        "zero_geoids": zero_geoids,
        "zero_by_grantee": sorted(
            ({"grantee": k, "tracts": v,
              "grantee_total_tracts": grantee_total_tracts.get(k, v)}
             for k, v in zero_by_grantee.items()),
            key=lambda r: (-r["tracts"], r["grantee"])),
        "communities_in_at_least_one": len(covered_communities),
        "communities_in_none": sorted(all_communities - covered_communities),
    }

    return {
        "generated_note": "Built by scripts/build_crosswalk.py — do not edit by hand.",
        "source_hash": source_hash(),
        "totals": {"communities": total_grantees, "tracts": total_tracts,
                   "shared_tracts": shared_tracts},
        "min_overlap_frac": MIN_OVERLAP_FRAC,
        "layers": results,
        "stacking": stacking,
    }


def print_summary(out):
    T = out["totals"]
    print(f"ENOUGH: {T['communities']} communities, {T['tracts']} tracts "
          f"({T['shared_tracts']} shared by two grantees)\n")
    for key in ["bvri", "dhcd", "nmtc", "oz", "ez"]:
        r = out["layers"][key]
        print(f"{r['label']}:")
        print(f"  {r['communities_overlapping']}/{T['communities']} communities, "
              f"{r['tracts_overlapping']}/{T['tracts']} tracts overlap")
        if "tiers" in r:
            print(f"  tiers: {r['tiers']}")
        if "properties_in_grantee_tracts" in r:
            print(f"  BVRI properties in grantee tracts: "
                  f"{r['properties_in_grantee_tracts']}/{r['properties_total']}")
        print()
    s = out["stacking"]
    print("Stacking across statewide layers (NMTC / OZ / EZ):")
    print(f"  tracts by # of programs: {s['histogram']}")
    print(f"  grantee tracts in ZERO statewide program: {s['tracts_in_zero']}")
    print(f"  communities in none: {len(s['communities_in_none'])}\n")


def main():
    ap = argparse.ArgumentParser(description="Build the ENOUGH crosswalk data.")
    ap.add_argument("--check", action="store_true",
                    help="verify committed crosswalk.json is fresh vs. source data; "
                         "exit 1 if stale. Does not write.")
    args = ap.parse_args()

    outpath = os.path.join(DATA, "crosswalk.json")

    if args.check:
        if not os.path.exists(outpath):
            print("FAIL: crosswalk.json does not exist — run without --check.")
            sys.exit(1)
        committed = json.load(open(outpath))
        cur = source_hash()
        old = committed.get("source_hash")
        if old == cur:
            print("OK: crosswalk.json is in sync with its source data.")
            sys.exit(0)
        print("STALE: source data has changed since crosswalk.json was built.")
        print(f"  committed source_hash: {old}")
        print(f"  current  source_hash: {cur}")
        print("  -> rerun: python scripts/build_crosswalk.py")
        sys.exit(1)

    out = compute()
    with open(outpath, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {outpath}\n")
    print_summary(out)


if __name__ == "__main__":
    main()
