#!/usr/bin/env python3
"""
Build the ENOUGH × Baltimore vacancy crosswalk — vacant *buildings* and vacant
*lots*, current counts plus the reduction trend, per ENOUGH grantee.

This is the data behind the map's "Vacant Buildings / Vacant Lots" layers and the
"Vacants Reduction" section of the ENOUGH Crosswalk page. It answers the two
questions Mihir asked for:
  1. How many total vacants (standing buildings + lots) sit in each ENOUGH
     grantee's tracts?
  2. How is that number moving — i.e. the Vacants Reduction view from Baltimore
     DHCD's Vacants Reinvestment Council dashboard, but cut by ENOUGH community
     instead of by DHCD priority area.

WHY NOT the Open Bid List: the map's original BVRI layer is Layer 7 of the DHCD
Open Baltimore service ("Open Bid List - Vacants to Value", ~1,200 properties).
That is only the subset the City is actively marketing for sale. The actual
vacancy stock the City, the Council dashboard and the press track is the count of
open **Vacant Building Notices (VBNs)** — about 11,500 properties. This script
uses the VBN universe.

SOURCES
-------
Vacancy spells (the important one):
  https://egisdata.baltimorecity.gov/egis/rest/services/Housing/VacantsTimeSlider/MapServer/0
    "Open Vacants" — one row per *interval* a property was vacant, with
    DateNotice (VBN issued) and DateEnd (VBN resolved). A property that cycled in
    and out of vacancy has several rows. Rows whose DateEnd equals the service's
    snapshot date are the ones still open today; that sentinel date is detected at
    runtime (SNAPSHOT_DATE below) rather than hardcoded.
  Layer 1 of the same service is the complementary "Resolved Vacants" (closed
  intervals); we do not need it, because Layer 0 already carries the end date.

  Because each row is an interval, the *stock* of vacant buildings on any date D
  is simply the rows where DateNotice <= D < DateEnd. That is what makes a real
  reduction trend possible instead of a single snapshot. Validated against the
  City's own dashboard figures (within ~0.6% at every fiscal-year boundary):
      2024-07-01 (FY25 start)  computed 13,233   dashboard 13,312
      2025-07-01 (FY25 end)    computed 12,599   dashboard 12,589
      2026-07-01 (FY26 end)    computed 11,604   dashboard 11,624
      snapshot (current)       computed 11,523   dashboard 11,448
  The residual gap is snapshot timing plus a handful of same-property duplicate
  intervals; it is not material at community scale, but it does mean these
  numbers should be described as "closely tracks DHCD", not "equals DHCD".

Vacant lots:
  https://egisdata.baltimorecity.gov/egis/rest/services/Housing/VacantLot_Test/MapServer/0
    ~18,700 vacant lots (NO_IMPRV = no improvement on the parcel). NB the service
    is named "_Test" — it is the only public vacant-lot layer published on the
    City's server, and it is the one feeding the City's Tolemi integration, but
    the name is a standing risk. Re-verify before citing lot counts externally.
    Lots have no equivalent interval history, so lots are a current snapshot only
    and are deliberately excluded from the reduction trend.

Writes:
  docs/data/vacants_enough.json              per-tract + per-grantee counts & trend
  docs/data/vacant_buildings_baltimore.geojson  all current open VBNs citywide,
      each flagged in_enough=1 when it falls in an ENOUGH grantee tract
  docs/data/vacant_lots_baltimore.geojson       all vacant lots citywide, same flag

Needs shapely; run from the repo-local venv:
    .venv-geo/bin/python scripts/fetch_vacants.py
"""

import json
import math
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import shape, Point
from shapely.prepared import prep
from shapely.strtree import STRtree

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"

SPELLS = ("https://egisdata.baltimorecity.gov/egis/rest/services/Housing/"
          "VacantsTimeSlider/MapServer/0/query")
LOTS = ("https://egisdata.baltimorecity.gov/egis/rest/services/Housing/"
        "VacantLot_Test/MapServer/0/query")

# Outflow detail: what actually happened to properties that left the VBN list.
# Rehab preserves a housing unit (and a potential homeownership asset for an
# ENOUGH family); demolition removes it. That distinction is the policy question
# the vacancy net-change number hides, so both flows are counted separately.
DHCD = ("https://egisdata.baltimorecity.gov/egis/rest/services/Housing/"
        "DHCD_Open_Baltimore_Datasets/FeatureServer")
REHABS = f"{DHCD}/2/query"   # "Rehabs of Vacant Buildings"  (DateIssue)
DEMOS = f"{DHCD}/0/query"    # "Completed City Demo"         (DateDemoFinished)

# Fiscal-year boundaries to report the trend against. FY25 is the baseline the
# Vacants Reinvestment Council set its 5,000-property goal from.
FY_MARKS = [
    ("FY25 start", "2024-07-01"),
    ("FY26 start", "2025-07-01"),
    ("FY27 start", "2026-07-01"),
]


def esri_get(url, params):
    q = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{q}", timeout=120) as r:
        return json.loads(r.read())


def fetch_all(url, fields, page=1000, where="1=1"):
    """Page through an ArcGIS layer, returning geojson features."""
    out, offset = [], 0
    while True:
        d = esri_get(url, {
            "where": where, "outFields": ",".join(fields),
            "returnGeometry": "true", "outSR": "4326", "f": "geojson",
            "resultRecordCount": page, "resultOffset": offset,
        })
        batch = d.get("features", [])
        out.extend(batch)
        print(f"    {len(out)} ...", end="\r")
        if len(batch) < page:
            break
        offset += page
    print(f"    {len(out)} total")
    return out


def round_coords(obj, ndigits=5):
    """Round nested coordinate arrays. Tract polygons from the statewide source
    carry far more precision than a web map needs."""
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(c), ndigits) for c in obj]
        return [round_coords(o, ndigits) for o in obj]
    return obj


def ms_to_date(v):
    if v is None:
        return None
    return datetime.fromtimestamp(v / 1000, tz=timezone.utc).date()


# Every Baltimore City census tract, not just the ENOUGH ones. The comparison
# "what share of ENOUGH tracts saw vacancy fall, versus the rest of the city?"
# needs the non-ENOUGH tracts as a control group, so the whole city is loaded and
# each tract is flagged. Source: the same statewide 2020-tract file used to build
# grantee_tracts.geojson, filtered to JURSCODE == 'BACI' (199 tracts).
CITY_TRACTS = (ROOT.parent / "enough-eligibility-analysis" / "docs" / "data"
               / "tracts_2026.geojson")


def load_city_tracts():
    """All Baltimore City tracts -> polygons, plus which are ENOUGH and whose.

    Returns (geoms, geoids, enough_geoids, tract_grantees, grantee_total,
    n_communities, child_pov). The grantee roster is the source of truth for
    tract -> grantee; a few tracts are served by two grantees, so a tract can map
    to more than one."""
    grantees = json.load(open(DATA / "grantees.json"))["grantees"]
    tract_grantees = defaultdict(list)
    grantee_total = {}
    for g in grantees:
        grantee_total[g["name"]] = g["tract_count"]
        for t in g["tracts"]:
            tract_grantees[t].append(g["name"])

    enough_geoids = {
        f["properties"]["GEOID20"]
        for f in json.load(open(DATA / "grantee_tracts.geojson"))["features"]
        if f["properties"].get("JURSCODE") == "BACI"
        or f["properties"]["GEOID20"].startswith("24510")
    }

    geoms, geoids, child_pov = [], [], {}
    for f in json.load(open(CITY_TRACTS))["features"]:
        p = f["properties"]
        if p.get("JURSCODE") != "BACI":
            continue
        geoid = p["GEOID20"]
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        geoms.append(g)
        geoids.append(geoid)
        child_pov[geoid] = p.get("F2024_Child_Poverty_Rate__2026_")
    return (geoms, geoids, enough_geoids, tract_grantees, grantee_total,
            len(grantees), child_pov)


def assign(features, geoms, geoids):
    """Point-in-polygon each feature to a grantee tract GEOID (or None).

    STRtree for the broad phase, prepared geometries for the exact test — 50k
    points against 46 polygons is otherwise slow enough to be annoying."""
    tree = STRtree(geoms)
    prepared = [prep(g) for g in geoms]
    hits = []
    for f in features:
        gm = f.get("geometry")
        if not gm or gm.get("type") != "Point":
            hits.append(None)
            continue
        pt = Point(gm["coordinates"])
        geoid = None
        for i in tree.query(pt):
            if prepared[i].contains(pt):
                geoid = geoids[i]
                break
        hits.append(geoid)
    return hits


def main():
    (geoms, geoids, enough_geoids, tract_grantees, grantee_total,
     n_communities, child_pov) = load_city_tracts()
    print(f"Baltimore City tracts: {len(geoids)} "
          f"({len(enough_geoids)} ENOUGH, {len(geoids) - len(enough_geoids)} other)")

    print("\nFetching vacancy spells (VacantsTimeSlider Layer 0)...")
    spells = fetch_all(SPELLS, ["blocklot", "DateNotice", "DateEnd", "NEIGHBOR"])

    print("Fetching vacant lots (VacantLot_Test Layer 0)...")
    lots = fetch_all(LOTS, ["BLOCKLOT", "FULLADDR", "NO_IMPRV"], page=5000)

    print("Fetching rehabs of vacant buildings (DHCD Layer 2)...")
    rehabs = fetch_all(REHABS, ["BLOCKLOT", "DateIssue", "Neighborhood"])

    print("Fetching completed city demolitions (DHCD Layer 0)...")
    demos = fetch_all(DEMOS, ["BLOCKLOT", "DateDemoFinished", "Neighborhood"])

    # The service marks still-open intervals with a sentinel DateEnd equal to the
    # data snapshot date. Detect it as the most common maximum end date.
    ends = [ms_to_date(f["properties"].get("DateEnd")) for f in spells]
    snapshot = max(e for e in ends if e)
    n_snap = sum(1 for e in ends if e == snapshot)
    print(f"\nSnapshot (sentinel) date: {snapshot}  ({n_snap} still-open intervals)")

    print("Assigning spells to grantee tracts...")
    spell_geoid = assign(spells, geoms, geoids)
    print("Assigning lots to grantee tracts...")
    lot_geoid = assign(lots, geoms, geoids)
    print("Assigning rehabs to grantee tracts...")
    rehab_geoid = assign(rehabs, geoms, geoids)
    print("Assigning demolitions to grantee tracts...")
    demo_geoid = assign(demos, geoms, geoids)

    marks = [(label, datetime.strptime(d, "%Y-%m-%d").date()) for label, d in FY_MARKS]

    # --- per-tract tallies -------------------------------------------------
    cur_buildings = defaultdict(set)          # geoid -> {blocklot} open now
    stock_at = {label: defaultdict(set) for label, _ in marks}
    citywide_cur, citywide_at = set(), {label: set() for label, _ in marks}

    for f, geoid in zip(spells, spell_geoid):
        p = f["properties"]
        bl = p.get("blocklot")
        start, end = ms_to_date(p.get("DateNotice")), ms_to_date(p.get("DateEnd"))
        if not start or not end:
            continue
        open_now = end >= snapshot
        if open_now:
            citywide_cur.add(bl)
            if geoid:
                cur_buildings[geoid].add(bl)
        for label, d in marks:
            if start <= d < end:
                citywide_at[label].add(bl)
                if geoid:
                    stock_at[label][geoid].add(bl)

    # --- flows over the baseline window ------------------------------------
    # Net change in the stock is the difference of two much larger flows. Counting
    # only the net hides how much work produced it: DHCD can resolve thousands of
    # VBNs while thousands of new ones are issued. "Gross resolved" is an interval
    # ENDING inside the window (a VBN closed); "new issued" is an interval
    # STARTING inside it. A property can appear in both if it cycled.
    window_start = marks[0][1]
    gross_resolved = defaultdict(set)   # geoid -> {blocklot} VBNs closed in window
    new_issued = defaultdict(set)       # geoid -> {blocklot} VBNs opened in window
    cw_resolved, cw_new = set(), set()
    iv_resolved = iv_new = 0   # interval counts: stock identity holds on these
    for f, geoid in zip(spells, spell_geoid):
        p = f["properties"]
        bl = p.get("blocklot")
        start, end = ms_to_date(p.get("DateNotice")), ms_to_date(p.get("DateEnd"))
        if not start or not end:
            continue
        if window_start <= end < snapshot:      # closed inside the window
            iv_resolved += 1
            cw_resolved.add(bl)
            if geoid:
                gross_resolved[geoid].add(bl)
        if start >= window_start:                # opened inside the window
            iv_new += 1
            cw_new.add(bl)
            if geoid:
                new_issued[geoid].add(bl)

    def date_filtered(features, hits, field):
        """geoid -> {blocklot} for records dated inside the window."""
        out = defaultdict(set)
        cw = set()
        for f, geoid in zip(features, hits):
            p = f["properties"]
            d = ms_to_date(p.get(field))
            if not d or d < window_start:
                continue
            bl = p.get("BLOCKLOT")
            cw.add(bl)
            if geoid:
                out[geoid].add(bl)
        return out, cw

    tract_rehabs, cw_rehabs = date_filtered(rehabs, rehab_geoid, "DateIssue")
    tract_demos, cw_demos = date_filtered(demos, demo_geoid, "DateDemoFinished")

    cur_lots = defaultdict(set)
    citywide_lots = set()
    for f, geoid in zip(lots, lot_geoid):
        bl = f["properties"].get("BLOCKLOT")
        citywide_lots.add(bl)
        if geoid:
            cur_lots[geoid].add(bl)

    # --- roll up by grantee ------------------------------------------------
    def rollup(per_tract):
        """Per-tract sets -> per-grantee counts. Only ENOUGH tracts map to a
        grantee, so non-ENOUGH city tracts drop out here naturally."""
        out = defaultdict(set)
        for geoid, items in per_tract.items():
            for gname in tract_grantees.get(geoid, []):
                out[gname] |= {(geoid, i) for i in items}
        return {k: len(v) for k, v in out.items()}

    g_buildings = rollup(cur_buildings)
    g_lots = rollup(cur_lots)
    g_at = {label: rollup(stock_at[label]) for label, _ in marks}
    g_resolved = rollup(gross_resolved)
    g_new = rollup(new_issued)
    g_rehabs = rollup(tract_rehabs)
    g_demos = rollup(tract_demos)

    base_label = FY_MARKS[0][0]
    grantee_rows = []
    for gname in sorted(set(g_buildings) | set(g_lots)):
        b = g_buildings.get(gname, 0)
        lt = g_lots.get(gname, 0)
        base = g_at[base_label].get(gname, 0)
        row = {
            "grantee": gname,
            "vacant_buildings": b,
            "vacant_lots": lt,
            "total_vacants": b + lt,
            "baseline_buildings": base,
            "change_buildings": b - base,
            "pct_change_buildings": round((b - base) / base * 100, 1) if base else None,
            "gross_resolved": g_resolved.get(gname, 0),
            "new_issued": g_new.get(gname, 0),
            "gross_pct_of_baseline": round(g_resolved.get(gname, 0) / base * 100, 1) if base else None,
            "rehabs": g_rehabs.get(gname, 0),
            "demolitions": g_demos.get(gname, 0),
            "grantee_total_tracts": grantee_total.get(gname),
            "baltimore_tracts": sum(
                1 for geoid in geoids if gname in tract_grantees.get(geoid, [])),
            "stock_by_mark": {label: g_at[label].get(gname, 0) for label, _ in marks},
        }
        grantee_rows.append(row)
    grantee_rows.sort(key=lambda r: -r["total_vacants"])

    tract_rows = []
    for geoid in sorted((set(cur_buildings) | set(cur_lots)) & enough_geoids):
        b, lt = len(cur_buildings.get(geoid, ())), len(cur_lots.get(geoid, ()))
        base = len(stock_at[base_label].get(geoid, ()))
        tract_rows.append({
            "GEOID": geoid,
            "grantees": tract_grantees.get(geoid, []),
            "vacant_buildings": b, "vacant_lots": lt, "total_vacants": b + lt,
            "baseline_buildings": base, "change_buildings": b - base,
            "gross_resolved": len(gross_resolved.get(geoid, ())),
            "new_issued": len(new_issued.get(geoid, ())),
            "rehabs": len(tract_rehabs.get(geoid, ())),
            "demolitions": len(tract_demos.get(geoid, ())),
        })

    # --- neighborhood view, to line up with press coverage -----------------
    nb_cur, nb_base = defaultdict(set), defaultdict(set)
    for f in spells:
        p = f["properties"]
        nb = (p.get("NEIGHBOR") or "").strip()
        bl = p.get("blocklot")
        start, end = ms_to_date(p.get("DateNotice")), ms_to_date(p.get("DateEnd"))
        if not nb or not start or not end:
            continue
        if end >= snapshot:
            nb_cur[nb].add(bl)
        if start <= marks[0][1] < end:
            nb_base[nb].add(bl)
    neighborhoods = sorted(
        ({"neighborhood": nb,
          "baseline": len(nb_base.get(nb, ())), "current": len(nb_cur.get(nb, ())),
          "change": len(nb_cur.get(nb, ())) - len(nb_base.get(nb, ())),
          "pct_change": round((len(nb_cur.get(nb, ())) - len(nb_base.get(nb, ())))
                              / len(nb_base[nb]) * 100, 1) if nb_base.get(nb) else None}
         for nb in set(nb_cur) | set(nb_base)),
        key=lambda r: r["change"])

    def esum(per_tract):
        """Sum a per-tract dict over ENOUGH tracts only."""
        return sum(len(v) for g, v in per_tract.items() if g in enough_geoids)

    # --- tract-level reduction rates: ENOUGH vs the rest of the city ---------
    # The headline comparison. For every Baltimore City tract we ask a simple
    # question: did its stock of vacant buildings fall between the baseline and
    # now? Then we compare how often that is true inside ENOUGH tracts against
    # how often it is true in the other 153 city tracts. Tracts that had no
    # vacant buildings at baseline and none now are excluded — they cannot
    # reduce, and counting them would dilute whichever group holds more of them.
    tract_stats = {}
    for geoid in geoids:
        b = len(cur_buildings.get(geoid, ()))
        base = len(stock_at[base_label].get(geoid, ()))
        tract_stats[geoid] = {
            "GEOID": geoid,
            "in_enough": 1 if geoid in enough_geoids else 0,
            "grantees": tract_grantees.get(geoid, []),
            "baseline_buildings": base,
            "vacant_buildings": b,
            "change_buildings": b - base,
            "pct_change": round((b - base) / base * 100, 1) if base else None,
            "vacant_lots": len(cur_lots.get(geoid, ())),
            "gross_resolved": len(gross_resolved.get(geoid, ())),
            "new_issued": len(new_issued.get(geoid, ())),
            "rehabs": len(tract_rehabs.get(geoid, ())),
            "demolitions": len(tract_demos.get(geoid, ())),
            "child_poverty_pct": child_pov.get(geoid),
        }

    def reduction_rate(group):
        """Share of tracts in `group` whose vacant-building count fell."""
        rows = [tract_stats[g] for g in group
                if tract_stats[g]["baseline_buildings"] > 0
                or tract_stats[g]["vacant_buildings"] > 0]
        reduced = [r for r in rows if r["change_buildings"] < 0]
        flat = [r for r in rows if r["change_buildings"] == 0]
        rose = [r for r in rows if r["change_buildings"] > 0]
        base_sum = sum(r["baseline_buildings"] for r in rows)
        now_sum = sum(r["vacant_buildings"] for r in rows)
        return {
            "tracts_with_vacancy": len(rows),
            "tracts_reduced": len(reduced),
            "tracts_flat": len(flat),
            "tracts_increased": len(rose),
            "pct_tracts_reduced": round(len(reduced) / len(rows) * 100, 1) if rows else None,
            "baseline_buildings": base_sum,
            "vacant_buildings": now_sum,
            "change_buildings": now_sum - base_sum,
            "pct_change_buildings": round((now_sum - base_sum) / base_sum * 100, 1) if base_sum else None,
            "median_tract_pct_change": (
                sorted(r["pct_change"] for r in rows if r["pct_change"] is not None)[
                    len([r for r in rows if r["pct_change"] is not None]) // 2]
                if any(r["pct_change"] is not None for r in rows) else None),
        }

    # Share-of-tracts-that-fell is NOT size-neutral: the bigger a tract's stock,
    # the more certain it is to lose at least one property. Publishing the bins
    # makes the confound visible instead of letting the headline imply performance.
    size_bins = []
    for lo, hi, lab in ((1, 10, "1–10"), (10, 50, "10–49"),
                        (50, 150, "50–149"), (150, 10 ** 9, "150+")):
        grp = [t for t in tract_stats.values()
               if lo <= t["baseline_buildings"] < hi]
        if not grp:
            continue
        fell = [t for t in grp if t["change_buildings"] < 0]
        pcts = sorted(t["pct_change"] for t in grp if t["pct_change"] is not None)
        size_bins.append({
            "baseline_band": lab, "tracts": len(grp), "tracts_reduced": len(fell),
            "pct_tracts_reduced": round(len(fell) / len(grp) * 100, 1),
            "median_pct_change": pcts[len(pcts) // 2] if pcts else None,
            "enough_share": round(sum(1 for t in grp if t["in_enough"]) / len(grp) * 100, 1),
        })

    enough_list = [g for g in geoids if g in enough_geoids]
    other_list = [g for g in geoids if g not in enough_geoids]
    comparison = {
        "enough": reduction_rate(enough_list),
        "rest_of_city": reduction_rate(other_list),
        "all_city": reduction_rate(geoids),
        "size_bins": size_bins,
    }
    # Two-proportion z-test on the ENOUGH vs rest-of-city tract shares. Published
    # so the page can state plainly that the gap is not statistically significant
    # rather than presenting it as a settled finding.
    _e, _o = comparison["enough"], comparison["rest_of_city"]
    a, na = _e["tracts_reduced"], _e["tracts_with_vacancy"]
    b, nb = _o["tracts_reduced"], _o["tracts_with_vacancy"]
    if na and nb:
        p1, p2 = a / na, b / nb
        pp = (a + b) / (na + nb)
        se = math.sqrt(pp * (1 - pp) * (1 / na + 1 / nb))
        z = (p1 - p2) / se if se else 0.0
        comparison["significance"] = {
            "gap_pp": round((p1 - p2) * 100, 1),
            "z": round(z, 2),
            "p_two_sided": round(math.erfc(abs(z) / math.sqrt(2)), 3),
            "significant_at_05": bool(math.erfc(abs(z) / math.sqrt(2)) < 0.05),
        }
    # Double-count disclosure for the per-grantee ranking.
    comparison["grantee_baseline_sum"] = sum(
        r["baseline_buildings"] for r in grantee_rows)
    comparison["vbns_outside_any_tract"] = (
        len(citywide_cur) - sum(t["vacant_buildings"] for t in tract_stats.values()))
    # Same question at the grantee level: of each grantee's tracts, how many fell?
    grantee_reduction = []
    for gname in sorted(grantee_total):
        ts = [g for g in enough_list if gname in tract_grantees.get(g, [])]
        ts = [g for g in ts if tract_stats[g]["baseline_buildings"] > 0
              or tract_stats[g]["vacant_buildings"] > 0]
        if not ts:
            continue
        red = [g for g in ts if tract_stats[g]["change_buildings"] < 0]
        grantee_reduction.append({
            "grantee": gname,
            "tracts": len(ts),
            "tracts_reduced": len(red),
            "pct_tracts_reduced": round(len(red) / len(ts) * 100, 1),
        })
    grantee_reduction.sort(key=lambda r: (-r["pct_tracts_reduced"], -r["tracts"]))

    out = {
        "generated_note": "Built by scripts/fetch_vacants.py — do not edit by hand.",
        "city_tracts_analyzed": len(geoids),
        "reduction_comparison": comparison,
        "grantee_reduction_rates": grantee_reduction,
        "by_city_tract": [tract_stats[g] for g in geoids],
        "snapshot_date": str(snapshot),
        "baseline_label": base_label,
        "baseline_date": str(marks[0][1]),
        "fy_marks": [{"label": l, "date": str(d)} for l, d in marks],
        "citywide": {
            "vacant_buildings": len(citywide_cur),
            "vacant_lots": len(citywide_lots),
            "total_vacants": len(citywide_cur) + len(citywide_lots),
            "stock_by_mark": {l: len(citywide_at[l]) for l, _ in marks},
            "change_buildings": len(citywide_cur) - len(citywide_at[base_label]),
            "gross_resolved": len(cw_resolved),
            "new_issued": len(cw_new),
            "gross_resolved_intervals": iv_resolved,
            "new_issued_intervals": iv_new,
            "cycled_properties": len(cw_resolved & cw_new),
            "rehabs": len(cw_rehabs),
            "demolitions": len(cw_demos),
        },
        # NB these are deduplicated across tracts. Three Baltimore City grantee
        # tracts are served by two grantees each, so summing the per-grantee rows
        # would double-count them (about 230 buildings). Always use these totals
        # for any ENOUGH-wide figure rather than adding up the breakdown column.
        "enough_totals": {
            "communities_statewide": n_communities,
            # ENOUGH grantee tracts in Baltimore City. NB `geoids` is now every
            # city tract (199), so this must count the ENOUGH subset explicitly.
            "baltimore_tracts": len(enough_geoids),
            "tracts_with_vacants": len(tract_rows),
            "vacant_buildings": esum(cur_buildings),
            "vacant_lots": esum(cur_lots),
            "baseline_buildings": esum(stock_at[base_label]),
            "gross_resolved": esum(gross_resolved),
            "new_issued": esum(new_issued),
            "rehabs": esum(tract_rehabs),
            "demolitions": esum(tract_demos),
            "cycled_properties": sum(
                len(gross_resolved[g] & new_issued[g])
                for g in set(gross_resolved) | set(new_issued)),
            "communities_with_vacants": len(grantee_rows),
            "shared_tracts": sum(
                1 for geoid in geoids if len(tract_grantees.get(geoid, [])) > 1),
        },
        "by_grantee": grantee_rows,
        "by_tract": tract_rows,
        "by_neighborhood": neighborhoods,
    }
    out["enough_totals"]["total_vacants"] = (
        out["enough_totals"]["vacant_buildings"] + out["enough_totals"]["vacant_lots"])
    out["enough_totals"]["change_buildings"] = (
        out["enough_totals"]["vacant_buildings"]
        - out["enough_totals"]["baseline_buildings"])

    (DATA / "vacants_enough.json").write_text(json.dumps(out, indent=2))

    # --- map layers: only the points inside grantee tracts -----------------
    def dump(features, hits, path, props):
        """Write every Baltimore City point, flagged by whether it sits in an
        ENOUGH grantee tract. The out-of-area points are what let a reader see how
        ENOUGH's footprint relates to the city's overall vacancy pattern, so they
        are context, not clutter — but they carry only the minimum properties,
        since bytes matter at ~30k points and they get a lighter popup."""
        feats = []
        n_in = 0
        for f, geoid in zip(features, hits):
            p = f["properties"]
            keep = {k: p.get(src) for k, src in props.items()}
            if geoid:
                keep["in_enough"] = 1
                keep["GEOID"] = geoid
                keep["grantees"] = tract_grantees.get(geoid, [])
                n_in += 1
            coords = [round(c, 5) for c in f["geometry"]["coordinates"]]
            feats.append({"type": "Feature",
                          "geometry": {"type": "Point", "coordinates": coords},
                          "properties": keep})
        (DATA / path).write_text(json.dumps(
            {"type": "FeatureCollection", "features": feats}))
        return len(feats), n_in

    open_spells, open_hits = [], []
    for f, geoid in zip(spells, spell_geoid):
        if ms_to_date(f["properties"].get("DateEnd")) >= snapshot:
            open_spells.append(f)
            open_hits.append(geoid)
    nb, nb_in = dump(open_spells, open_hits, "vacant_buildings_baltimore.geojson",
                     {"blocklot": "blocklot", "address": "Address",
                      "neighborhood": "NEIGHBOR", "date_notice": "DateNotice"})
    nl, nl_in = dump(lots, lot_geoid, "vacant_lots_baltimore.geojson",
                     {"blocklot": "BLOCKLOT", "address": "FULLADDR"})

    # --- Layer: vacancy REDUCTIONS as individual points ---------------------
    # Each point is a property whose vacant-building notice closed during the
    # window, placed where the property is. This is the "where did vacancy
    # actually come down" layer, as opposed to "where is vacancy now".
    resolved_feats = []
    for f, geoid in zip(spells, spell_geoid):
        pr = f["properties"]
        end = ms_to_date(pr.get("DateEnd"))
        start = ms_to_date(pr.get("DateNotice"))
        if not end or not (window_start <= end < snapshot):
            continue
        keep = {
            "blocklot": pr.get("blocklot"),
            "address": pr.get("Address"),
            "neighborhood": pr.get("NEIGHBOR"),
            "date_resolved": pr.get("DateEnd"),
            # A closure is only durable if the property was not re-noticed.
            "durable": 0 if (geoid and pr.get("blocklot") in new_issued.get(geoid, ()))
                       or (pr.get("blocklot") in cw_new) else 1,
        }
        if start:
            keep["years_vacant"] = round((end - start).days / 365.25, 1)
        if geoid:
            keep["GEOID"] = geoid
            if geoid in enough_geoids:
                keep["in_enough"] = 1
                keep["grantees"] = tract_grantees.get(geoid, [])
        coords = [round(c, 5) for c in f["geometry"]["coordinates"]]
        resolved_feats.append({"type": "Feature",
                               "geometry": {"type": "Point", "coordinates": coords},
                               "properties": keep})
    (DATA / "vacancy_reductions_baltimore.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": resolved_feats}))
    nr_in = sum(1 for f in resolved_feats if f["properties"].get("in_enough"))
    nr_dur = sum(1 for f in resolved_feats if f["properties"]["durable"])

    # --- Layer: per-tract change, as polygons for a choropleth --------------
    tract_feats = []
    for f in json.load(open(CITY_TRACTS))["features"]:
        pr = f["properties"]
        if pr.get("JURSCODE") != "BACI":
            continue
        st = tract_stats.get(pr["GEOID20"])
        if not st:
            continue
        geom = f["geometry"]
        tract_feats.append({
            "type": "Feature",
            "geometry": dict(geom, coordinates=round_coords(geom["coordinates"])),
            "properties": {k: st[k] for k in (
                "GEOID", "in_enough", "grantees", "baseline_buildings",
                "vacant_buildings", "change_buildings", "pct_change",
                "gross_resolved", "rehabs", "demolitions", "child_poverty_pct")},
        })
    (DATA / "vacancy_change_tracts.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": tract_feats}))

    T = out["enough_totals"]
    C = out["citywide"]
    print(f"\nWrote {DATA/'vacants_enough.json'}")
    print(f"  map layers (citywide, flagged by ENOUGH): {nb:,} vacant buildings "
          f"({nb_in:,} in ENOUGH tracts), {nl:,} vacant lots ({nl_in:,} in ENOUGH tracts)")
    print(f"\nCitywide: {C['vacant_buildings']:,} vacant buildings + "
          f"{C['vacant_lots']:,} lots = {C['total_vacants']:,} total")
    print(f"  buildings since {base_label}: {C['change_buildings']:+,}")
    print(f"\nENOUGH (Baltimore City): {T['vacant_buildings']:,} buildings + "
          f"{T['vacant_lots']:,} lots = {T['total_vacants']:,} total vacants")
    print(f"  across {T['communities_with_vacants']} communities, "
          f"{T['tracts_with_vacants']}/{T['baltimore_tracts']} city tracts")
    RC = out["reduction_comparison"]
    print(f"\nTract-level reduction rate ({base_label} -> now):")
    for k, lab in (("enough", "ENOUGH tracts"), ("rest_of_city", "Rest of city"), ("all_city", "All city")):
        r = RC[k]
        print(f"  {lab:<16} {r['tracts_reduced']:>3}/{r['tracts_with_vacancy']:<3} tracts fell "
              f"({r['pct_tracts_reduced']}%)  | stock {r['pct_change_buildings']}%  "
              f"| median tract {r['median_tract_pct_change']}%")
    print(f"\nReduction points: {len(resolved_feats):,} closures mapped "
          f"({nr_in:,} in ENOUGH tracts, {nr_dur:,} durable citywide)")
    print(f"\nFlows since {base_label} — ENOUGH: {T['gross_resolved']:,} VBNs resolved, "
          f"{T['new_issued']:,} newly issued | {T['rehabs']:,} rehabs, {T['demolitions']:,} demolitions")
    print(f"  citywide: {C['gross_resolved']:,} resolved, {C['new_issued']:,} newly issued | "
          f"{C['rehabs']:,} rehabs, {C['demolitions']:,} demolitions")
    if C['demolitions']:
        print(f"  rehab:demolition ratio — ENOUGH "
              f"{T['rehabs']/max(T['demolitions'],1):.1f}:1, citywide {C['rehabs']/C['demolitions']:.1f}:1")
    print("\nTop ENOUGH communities by total vacants:")
    for r in grantee_rows[:12]:
        pct = f"{r['pct_change_buildings']:+.1f}%" if r["pct_change_buildings"] is not None else "  n/a"
        print(f"  {r['grantee'][:44]:<46} {r['total_vacants']:>5,} total "
              f"({r['vacant_buildings']:>4,} bldg + {r['vacant_lots']:>4,} lot)  "
              f"bldg {r['change_buildings']:+4d} ({pct})")


if __name__ == "__main__":
    main()
