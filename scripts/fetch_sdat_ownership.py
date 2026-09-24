#!/usr/bin/env python3
"""
Join Maryland SDAT parcel data to the Baltimore vacancy layers, to answer the one
question the vacancy datasets cannot: **what happened to the property?**

A vacant-building notice closing tells you a notice closed. It does not tell you
whether the house became a home. SDAT carries an owner-occupancy indicator, the
owner's mailing address, and the last transfer date and price, so for properties
that left the vacancy list we can ask whether they are now owner-occupied, held by
an out-of-area owner, or simply sitting.

Source (Maryland Department of Planning / SDAT, via MD iMap):
  https://mdgeodata.md.gov/imap/rest/services/PlanningCadastre/MD_PropertyData/MapServer/0
    "Parcel Points" — 237,260 records for Baltimore City; 114 fields.

Restricted to the 46 ENOUGH grantee tracts in Baltimore City via CT2020 (the
service carries a 2020 census-tract field, so no spatial join is needed), which
cuts the fetch to about 54,600 parcels.

Join key: SDAT ACCTID ends in "<block> <lot>", the same form as DHCD's BLOCKLOT
(e.g. "1256 001"), so the tail of ACCTID joins property-for-property to the
vacancy layers.

Fields used:
  OOI       owner-occupancy indicator — H = owner-occupied (homeowner),
            N = not owner-occupied, D = partial/other
  HOMQLCOD  homestead (principal-residence) credit qualification
  OWNCITY / OWNSTATE   owner's mailing address, for absentee ownership
  TRADATE / CONSIDR1   last transfer date and consideration (sale price)
  DESCLU    land-use description
  YEARBLT   year built

Writes docs/data/vacancy_ownership_sdat.json.
"""

import json
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "docs" / "data"
SDAT = ("https://mdgeodata.md.gov/imap/rest/services/PlanningCadastre/"
        "MD_PropertyData/MapServer/0/query")
FIELDS = ["ACCTID", "CT2020", "OOI", "HOMQLCOD", "OWNCITY", "OWNSTATE",
          "TRADATE", "CONSIDR1", "DESCLU", "YEARBLT"]
OOI_LABEL = {"H": "owner-occupied", "N": "not owner-occupied", "D": "partial/other"}


def blocklot(acctid):
    """SDAT ACCTID tail is '<block> <lot>', matching DHCD BLOCKLOT."""
    if not acctid:
        return None
    tail = acctid[-8:]
    return tail.strip() if " " in tail else None


def fetch(where):
    out, offset = [], 0
    while True:
        q = urllib.parse.urlencode({
            "where": where, "outFields": ",".join(FIELDS),
            "returnGeometry": "false", "f": "json",
            "resultRecordCount": 2000, "resultOffset": offset,
        })
        with urllib.request.urlopen(f"{SDAT}?{q}", timeout=180) as r:
            batch = json.loads(r.read()).get("features", [])
        out.extend(batch)
        print(f"    {len(out)} ...", end="\r")
        if len(batch) < 2000:
            break
        offset += 2000
    print(f"    {len(out)} parcels")
    return out


def summarize(parcels, label):
    """Owner-occupancy / absentee / tenure profile for a set of parcels."""
    ooi = Counter()
    absentee = in_city = 0
    sales, years = [], []
    lu = Counter()
    for a in parcels:
        ooi[OOI_LABEL.get(a.get("OOI"), "unknown")] += 1
        st = (a.get("OWNSTATE") or "").strip().upper()
        city = (a.get("OWNCITY") or "").strip().upper()
        if st and st != "MD":
            absentee += 1
        elif city == "BALTIMORE":
            in_city += 1
        td = (a.get("TRADATE") or "").strip()
        if len(td) == 8 and td.isdigit():
            try:
                sales.append(date(int(td[:4]), int(td[4:6]) or 1, int(td[6:]) or 1))
            except ValueError:
                pass
        yb = (a.get("YEARBLT") or "").strip()
        if yb.isdigit() and 1700 < int(yb) < 2030:
            years.append(int(yb))
        if a.get("DESCLU"):
            lu[a["DESCLU"]] += 1
    n = len(parcels) or 1
    recent = sum(1 for d in sales if d >= date(2024, 7, 1))
    return {
        "label": label,
        "parcels": len(parcels),
        "owner_occupancy": dict(ooi),
        "pct_owner_occupied": round(ooi["owner-occupied"] / n * 100, 1),
        "owner_outside_maryland": absentee,
        "pct_owner_outside_maryland": round(absentee / n * 100, 1),
        "owner_in_baltimore": in_city,
        "sold_since_fy25": recent,
        "pct_sold_since_fy25": round(recent / n * 100, 1),
        "median_year_built": (sorted(years)[len(years) // 2] if years else None),
        "top_land_uses": dict(lu.most_common(5)),
    }


def main():
    tracts = json.load(open(DATA / "grantee_tracts.geojson"))
    enough = sorted({f["properties"]["GEOID20"] for f in tracts["features"]
                     if f["properties"].get("JURSCODE") == "BACI"})
    inlist = ",".join(f"'{g}'" for g in enough)
    print(f"Fetching SDAT parcels for {len(enough)} ENOUGH tracts in Baltimore City...")
    parcels = fetch(f"JURSCODE='BACI' AND CT2020 IN ({inlist})")

    by_bl = {}
    for f in parcels:
        a = f["attributes"]
        bl = blocklot(a.get("ACCTID"))
        if bl:
            by_bl[bl] = a

    # currently vacant, inside ENOUGH tracts
    vb = json.load(open(DATA / "vacant_buildings_baltimore.geojson"))
    cur = [f["properties"]["blocklot"] for f in vb["features"]
           if f["properties"].get("in_enough") == 1]
    # closures since the baseline that were durable (property not re-noticed)
    rd = json.load(open(DATA / "vacancy_reductions_baltimore.geojson"))
    durable = [f["properties"]["blocklot"] for f in rd["features"]
               if f["properties"].get("in_enough") == 1
               and f["properties"].get("durable") == 1]

    def pick(bls):
        got = [by_bl[b] for b in bls if b in by_bl]
        return got, len(bls) - len(got)

    cur_p, cur_miss = pick(cur)
    dur_p, dur_miss = pick(durable)
    all_p = [a for a in by_bl.values()]

    out = {
        "generated_note": "Built by scripts/fetch_sdat_ownership.py — do not edit by hand.",
        "source": ("MD SDAT parcel points via MD iMap "
                   "PlanningCadastre/MD_PropertyData/MapServer/0"),
        "enough_tracts": len(enough),
        "parcels_fetched": len(parcels),
        "join_note": ("Joined on the block/lot tail of SDAT ACCTID. Unmatched "
                      "properties are excluded from the profiles below rather "
                      "than assumed."),
        "all_enough_parcels": summarize(all_p, "All parcels in ENOUGH tracts"),
        "currently_vacant": dict(summarize(cur_p, "Currently vacant buildings"),
                                 unmatched=cur_miss),
        "durably_resolved": dict(summarize(dur_p, "Left the vacancy list and stayed off"),
                                 unmatched=dur_miss),
    }
    (DATA / "vacancy_ownership_sdat.json").write_text(json.dumps(out, indent=2))

    print(f"\nWrote {DATA / 'vacancy_ownership_sdat.json'}\n")
    for key in ("all_enough_parcels", "currently_vacant", "durably_resolved"):
        b = out[key]
        print(f"{b['label']} (n={b['parcels']:,}"
              + (f", {b['unmatched']} unmatched" if "unmatched" in b else "") + ")")
        print(f"   owner-occupied {b['pct_owner_occupied']}% | "
              f"owner outside MD {b['pct_owner_outside_maryland']}% | "
              f"sold since FY25 {b['pct_sold_since_fy25']}% | "
              f"median built {b['median_year_built']}")


if __name__ == "__main__":
    main()
