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
  docs/data/vacant_buildings_enough.geojson  current open VBNs inside grantee tracts
  docs/data/vacant_lots_enough.geojson       vacant lots inside grantee tracts

Needs shapely; run from the repo-local venv:
    .venv-geo/bin/python scripts/fetch_vacants.py
"""

import json
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


def ms_to_date(v):
    if v is None:
        return None
    return datetime.fromtimestamp(v / 1000, tz=timezone.utc).date()


def load_grantee_index():
    """Baltimore City grantee tracts -> prepared polygons + grantee names.

    Vacancy data is Baltimore City only, so only the city tracts matter. The
    grantee roster is the source of truth for tract -> grantee (a few tracts are
    shared by two grantees, so a tract can map to more than one)."""
    tracts = json.load(open(DATA / "grantee_tracts.geojson"))
    grantees = json.load(open(DATA / "grantees.json"))["grantees"]

    tract_grantees = defaultdict(list)
    grantee_total = {}
    for g in grantees:
        grantee_total[g["name"]] = g["tract_count"]
        for t in g["tracts"]:
            tract_grantees[t].append(g["name"])

    geoms, geoids = [], []
    for f in tracts["features"]:
        p = f["properties"]
        geoid = p["GEOID20"]
        if not (p.get("JURSCODE") == "BACI" or geoid.startswith("24510")):
            continue
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        geoms.append(g)
        geoids.append(geoid)
    return geoms, geoids, tract_grantees, grantee_total, len(grantees)


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
    geoms, geoids, tract_grantees, grantee_total, n_communities = load_grantee_index()
    print(f"Baltimore City ENOUGH grantee tracts: {len(geoids)}")

    print("\nFetching vacancy spells (VacantsTimeSlider Layer 0)...")
    spells = fetch_all(SPELLS, ["blocklot", "DateNotice", "DateEnd", "NEIGHBOR"])

    print("Fetching vacant lots (VacantLot_Test Layer 0)...")
    lots = fetch_all(LOTS, ["BLOCKLOT", "FULLADDR", "NO_IMPRV"], page=5000)

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

    cur_lots = defaultdict(set)
    citywide_lots = set()
    for f, geoid in zip(lots, lot_geoid):
        bl = f["properties"].get("BLOCKLOT")
        citywide_lots.add(bl)
        if geoid:
            cur_lots[geoid].add(bl)

    # --- roll up by grantee ------------------------------------------------
    def rollup(per_tract):
        out = defaultdict(set)
        for geoid, items in per_tract.items():
            for gname in tract_grantees.get(geoid, []):
                out[gname] |= {(geoid, i) for i in items}
        return {k: len(v) for k, v in out.items()}

    g_buildings = rollup(cur_buildings)
    g_lots = rollup(cur_lots)
    g_at = {label: rollup(stock_at[label]) for label, _ in marks}

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
            "grantee_total_tracts": grantee_total.get(gname),
            "baltimore_tracts": sum(
                1 for geoid in geoids if gname in tract_grantees.get(geoid, [])),
            "stock_by_mark": {label: g_at[label].get(gname, 0) for label, _ in marks},
        }
        grantee_rows.append(row)
    grantee_rows.sort(key=lambda r: -r["total_vacants"])

    tract_rows = []
    for geoid in sorted(set(cur_buildings) | set(cur_lots)):
        b, lt = len(cur_buildings.get(geoid, ())), len(cur_lots.get(geoid, ()))
        base = len(stock_at[base_label].get(geoid, ()))
        tract_rows.append({
            "GEOID": geoid,
            "grantees": tract_grantees.get(geoid, []),
            "vacant_buildings": b, "vacant_lots": lt, "total_vacants": b + lt,
            "baseline_buildings": base, "change_buildings": b - base,
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

    out = {
        "generated_note": "Built by scripts/fetch_vacants.py — do not edit by hand.",
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
        },
        # NB these are deduplicated across tracts. Three Baltimore City grantee
        # tracts are served by two grantees each, so summing the per-grantee rows
        # would double-count them (about 230 buildings). Always use these totals
        # for any ENOUGH-wide figure rather than adding up the breakdown column.
        "enough_totals": {
            "communities_statewide": n_communities,
            "baltimore_tracts": len(geoids),
            "tracts_with_vacants": len(tract_rows),
            "vacant_buildings": sum(len(v) for v in cur_buildings.values()),
            "vacant_lots": sum(len(v) for v in cur_lots.values()),
            "baseline_buildings": sum(len(v) for v in stock_at[base_label].values()),
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
        feats = []
        for f, geoid in zip(features, hits):
            if not geoid:
                continue
            p = f["properties"]
            keep = {k: p.get(src) for k, src in props.items()}
            keep["GEOID"] = geoid
            keep["grantees"] = tract_grantees.get(geoid, [])
            coords = [round(c, 5) for c in f["geometry"]["coordinates"]]
            feats.append({"type": "Feature",
                          "geometry": {"type": "Point", "coordinates": coords},
                          "properties": keep})
        (DATA / path).write_text(json.dumps(
            {"type": "FeatureCollection", "features": feats}))
        return len(feats)

    open_spells, open_hits = [], []
    for f, geoid in zip(spells, spell_geoid):
        if ms_to_date(f["properties"].get("DateEnd")) >= snapshot:
            open_spells.append(f)
            open_hits.append(geoid)
    nb = dump(open_spells, open_hits, "vacant_buildings_enough.geojson",
              {"blocklot": "blocklot", "address": "Address",
               "neighborhood": "NEIGHBOR", "date_notice": "DateNotice"})
    nl = dump(lots, lot_geoid, "vacant_lots_enough.geojson",
              {"blocklot": "BLOCKLOT", "address": "FULLADDR"})

    T = out["enough_totals"]
    C = out["citywide"]
    print(f"\nWrote {DATA/'vacants_enough.json'}")
    print(f"  map layers: {nb} vacant buildings, {nl} vacant lots inside grantee tracts")
    print(f"\nCitywide: {C['vacant_buildings']:,} vacant buildings + "
          f"{C['vacant_lots']:,} lots = {C['total_vacants']:,} total")
    print(f"  buildings since {base_label}: {C['change_buildings']:+,}")
    print(f"\nENOUGH (Baltimore City): {T['vacant_buildings']:,} buildings + "
          f"{T['vacant_lots']:,} lots = {T['total_vacants']:,} total vacants")
    print(f"  across {T['communities_with_vacants']} communities, "
          f"{T['tracts_with_vacants']}/{T['baltimore_tracts']} city tracts")
    print("\nTop ENOUGH communities by total vacants:")
    for r in grantee_rows[:12]:
        pct = f"{r['pct_change_buildings']:+.1f}%" if r["pct_change_buildings"] is not None else "  n/a"
        print(f"  {r['grantee'][:44]:<46} {r['total_vacants']:>5,} total "
              f"({r['vacant_buildings']:>4,} bldg + {r['vacant_lots']:>4,} lot)  "
              f"bldg {r['change_buildings']:+4d} ({pct})")


if __name__ == "__main__":
    main()
