#!/usr/bin/env python3
"""Post-build sanity checks on everything in docs/data/.

Why this exists: on 2026-09-24 the live site published
"-1,130 properties left the vacancy list and stayed off it" because a rollup was
summed over 199 census tracts instead of the 46 ENOUGH ones. Nothing in the
pipeline objected — the number was impossible, not merely wrong, and it shipped.
fetch_vacants.py now asserts its own invariants, but seven other build scripts had
none and build_crosswalk.py feeds every headline figure on two pages.

This runs cheap structural checks that would have caught that class of error:
impossible counts, subsets larger than their supersets, percentages outside
0-100, empty layers, and figures that disagree between files. It is intended to
run after any fetch/build and before any push.

Usage:
    python3 scripts/validate_outputs.py          # check, exit 1 on failure
    python3 scripts/validate_outputs.py -q       # only print failures
"""

import json
import sys
from pathlib import Path

DATA = Path(__file__).parent.parent / "docs" / "data"

# layer file -> (minimum plausible feature count, geometry type expected)
LAYERS = {
    "grantee_tracts.geojson": (100, "Polygon"),
    "bvri_vacants.geojson": (500, "Point"),
    "bvri_investment_areas.geojson": (5, "Polygon"),
    "nmtc_maryland.geojson": (400, "Polygon"),
    "oz_designated_maryland.geojson": (140, "Polygon"),
    "oz2_eligible_maryland.geojson": (400, "Polygon"),
    "ez_maryland.geojson": (20, "Polygon"),
    "just_communities_maryland.geojson": (400, "Polygon"),
    "vacant_buildings_baltimore.geojson": (8000, "Point"),
    "vacant_lots_baltimore.geojson": (12000, "Point"),
    "vacancy_reductions_baltimore.geojson": (3000, "Point"),
    "vacancy_change_tracts.geojson": (150, "Polygon"),
}

fails, notes = [], []


def fail(msg):
    fails.append(msg)


def load(name):
    path = DATA / name
    if not path.exists():
        fail(f"{name}: missing")
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        fail(f"{name}: unreadable ({exc})")
        return None


def check_layers():
    for name, (minimum, geom) in LAYERS.items():
        d = load(name)
        if not d:
            continue
        feats = d.get("features")
        if not isinstance(feats, list):
            fail(f"{name}: no features array")
            continue
        if len(feats) < minimum:
            fail(f"{name}: {len(feats)} features, expected at least {minimum}")
        missing = sum(1 for f in feats if not f.get("geometry"))
        if missing:
            fail(f"{name}: {missing} features have no geometry")
        types = {(f.get("geometry") or {}).get("type") for f in feats[:400]}
        if not any(geom in (t or "") for t in types):
            fail(f"{name}: expected {geom} geometry, saw {types}")
        notes.append(f"{name}: {len(feats)} features")


def check_crosswalk():
    d = load("crosswalk.json")
    if not d:
        return
    T = d["totals"]
    for key, layer in d["layers"].items():
        o_t, t_t = layer["tracts_overlapping"], layer["total_tracts"]
        o_c, t_c = layer["communities_overlapping"], layer["total_communities"]
        if o_t > t_t:
            fail(f"crosswalk {key}: {o_t} overlapping > {t_t} total tracts")
        if o_c > t_c:
            fail(f"crosswalk {key}: {o_c} communities > {t_c} total")
        if o_t < 0 or o_c < 0:
            fail(f"crosswalk {key}: negative count")
        # a layer claiming overlap must name the communities it overlaps
        if o_c and not layer.get("breakdown"):
            fail(f"crosswalk {key}: {o_c} communities but empty breakdown")
        if len(layer.get("geoids", [])) != o_t:
            fail(f"crosswalk {key}: geoid list ({len(layer.get('geoids', []))}) "
                 f"disagrees with tracts_overlapping ({o_t})")
    s = d["stacking"]
    hist_total = sum(s["histogram"].values())
    if hist_total != T["tracts"]:
        fail(f"crosswalk stacking: histogram sums to {hist_total}, "
             f"expected {T['tracts']} tracts")
    bc = T.get("baltimore_city", {})
    if bc and bc["tracts"] > T["tracts"]:
        fail("crosswalk: Baltimore City tracts exceed statewide total")
    notes.append(f"crosswalk.json: {len(d['layers'])} layers, "
                 f"{T['tracts']} tracts, {T['communities']} communities")


def check_vacants():
    d = load("vacants_enough.json")
    if not d:
        return
    T, C = d["enough_totals"], d["citywide"]
    if T["vacant_buildings"] > C["vacant_buildings"]:
        fail("vacants: ENOUGH buildings exceed citywide")
    if T["vacant_lots"] > C["vacant_lots"]:
        fail("vacants: ENOUGH lots exceed citywide")
    for label, blk in (("enough", T), ("citywide", C)):
        if blk["cycled_properties"] > blk["gross_resolved"]:
            fail(f"vacants {label}: cycled > gross_resolved")
        if blk["gross_resolved"] - blk["cycled_properties"] < 0:
            fail(f"vacants {label}: durable count negative")
    RC = d["reduction_comparison"]
    if (RC["enough"]["tracts_with_vacancy"] + RC["rest_of_city"]["tracts_with_vacancy"]
            != RC["all_city"]["tracts_with_vacancy"]):
        fail("vacants: ENOUGH + rest != all_city tracts")
    for grp in ("enough", "rest_of_city", "all_city"):
        r = RC[grp]
        if r["tracts_reduced"] > r["tracts_with_vacancy"]:
            fail(f"vacants {grp}: reduced > total tracts")
        if r["pct_tracts_reduced"] is not None and not 0 <= r["pct_tracts_reduced"] <= 100:
            fail(f"vacants {grp}: pct outside 0-100")
    if "significance" in RC:
        fail("vacants: a p-value is present; ENOUGH tracts are purposively "
             "selected, so no inferential claim should be published")
    for r in d["by_grantee"]:
        if r["vacant_buildings"] > r["baseline_buildings"] + r["new_issued"]:
            fail(f"vacants {r['grantee']}: now exceeds baseline + new issued")
    # the map layer and the rollup must agree on how many points are in ENOUGH
    lyr = load("vacant_buildings_baltimore.geojson")
    if lyr:
        in_e = sum(1 for f in lyr["features"] if f["properties"].get("in_enough") == 1)
        if in_e != T["vacant_buildings"]:
            fail(f"vacants: layer has {in_e} in-ENOUGH points but rollup says "
                 f"{T['vacant_buildings']}")
        no_addr = sum(1 for f in lyr["features"] if not f["properties"].get("address"))
        if no_addr > len(lyr["features"]) * 0.2:
            fail(f"vacant buildings: {no_addr} points missing an address "
                 f"(field probably absent from outFields)")
    notes.append(f"vacants_enough.json: ENOUGH {T['vacant_buildings']} buildings + "
                 f"{T['vacant_lots']} lots; durable "
                 f"{T['gross_resolved'] - T['cycled_properties']}")


def check_sdat():
    d = load("vacancy_ownership_sdat.json")
    if not d:
        return
    for key in ("all_enough_parcels", "currently_vacant", "durably_resolved"):
        b = d[key]
        for pct in ("pct_owner_occupied", "pct_owner_outside_maryland",
                    "pct_sold_since_fy25"):
            if not 0 <= b[pct] <= 100:
                fail(f"sdat {key}: {pct} outside 0-100")
        if sum(b["owner_occupancy"].values()) != b["parcels"]:
            fail(f"sdat {key}: owner_occupancy buckets do not sum to parcels")
    notes.append(f"vacancy_ownership_sdat.json: resolved "
                 f"{d['durably_resolved']['pct_owner_occupied']}% owner-occupied vs "
                 f"{d['all_enough_parcels']['pct_owner_occupied']}% baseline")


def main():
    quiet = "-q" in sys.argv
    check_layers()
    check_crosswalk()
    check_vacants()
    check_sdat()
    if not quiet:
        for n in notes:
            print(f"  ok  {n}")
    if fails:
        print(f"\nFAILED {len(fails)} check(s):", file=sys.stderr)
        for f in fails:
            print(f"  ✗ {f}", file=sys.stderr)
        sys.exit(1)
    print(f"\nAll checks passed ({len(notes)} artifacts).")


if __name__ == "__main__":
    main()
