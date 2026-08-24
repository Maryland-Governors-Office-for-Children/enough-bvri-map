# CLAUDE.md — ENOUGH × BVRI Map

## What This Is

Single-page interactive Leaflet map showing the overlap between:
- **Active ENOUGH grantee tracts** in Baltimore City (GOC)
- **Baltimore Vacants Reinvestment Initiative (BVRI)** properties — "Vacants to Value" open bid list and DHCD Impact Investment Areas

Requested by Mihir Parikh. Intentionally simple: one grantee-tract layer, one BVRI-points layer, one investment-area polygon layer (off by default).

**Live site:** https://maryland-governors-office-for-children.github.io/enough-bvri-map/
**Source repo:** https://github.com/Maryland-Governors-Office-for-Children/enough-bvri-map

## Repo Structure

```
docs/                    GitHub Pages site (index.html + data/)
  index.html             Single-page Leaflet map
  crosswalk.html         ENOUGH Crosswalk: per-layer overlap breakdown + stacking/gap view
  methodology.html       Per-layer data-source + join-method documentation
  .nojekyll
  data/
    grantee_tracts.geojson         111 active ENOUGH grantee tracts statewide
    grantees.json                  28 grantee organizations with tract counts
    grantee_geoids.json            ENOUGH grantee tract GEOIDs (statewide, legacy, kept for backwards-compat)
    bvri_vacants.geojson           1,192 Vacants to Value properties (Baltimore City, from DHCD ArcGIS)
    bvri_investment_areas.geojson  7 DHCD Impact Investment Area polygons (Baltimore City)
    nmtc_maryland.geojson          587 NMTC-eligible tracts statewide (CDFI Fund)
    oz_designated_maryland.geojson 149 designated Opportunity Zones (2018 TCJA; MD DHCD/Commerce via iMap) + rural flag
    oz2_eligible_maryland.geojson  451 OZ 2.0-eligible tracts (2020–2024 ACS; OpportunityZones.com) w/ MFI ratio + poverty
    ez_maryland.geojson            34 Maryland Enterprise Zones + Focus Areas (MD Commerce via iMap)
    just_communities_maryland.geojson  419 designated Just Communities (MD DHCD via iMap; Just Communities Act of 2024)
    crosswalk.json                 Precomputed ENOUGH × layer overlap (built by build_crosswalk.py)
scripts/
  fetch_bvri.py          Refresh BVRI data from Baltimore City DHCD ArcGIS REST
  fetch_oz2.py           Refresh OZ 2.0-eligible tracts from opportunityzones.com + rural flag on designated OZs
  fetch_ez.py            Refresh Maryland Enterprise Zones from iMap MD_IncentiveZones
  fetch_jc.py            Refresh Just Communities from iMap MD_HousingDesignatedAreas Layer 9
  build_crosswalk.py     Compute ENOUGH × layer overlap (Shapely) -> docs/data/crosswalk.json
  requirements-crosswalk.txt  Pinned shapely for build_crosswalk.py
```

## How to Refresh Data

```bash
python3 scripts/fetch_bvri.py   # re-fetches bvri_vacants.geojson + bvri_investment_areas.geojson
python3 scripts/fetch_jc.py     # re-fetches just_communities_maryland.geojson (419 tracts)
# then commit the refreshed docs/data/*.geojson
```

BVRI data source: `https://egisdata.baltimorecity.gov/egis/rest/services/Housing/DHCD_Open_Baltimore_Datasets/FeatureServer`
- Layer 7: Vacants to Value (open bid list)
- Layer 10: Impact Investment Areas

ENOUGH grantee tract data is built from the `enough-eligibility-changes` repo. To rebuild after that repo's data updates:
```bash
python3 -c "
import json
src = json.load(open('../enough-eligibility-analysis/docs/data/tracts_2026.geojson'))
geoids = set(json.load(open('docs/data/grantee_geoids.json')))
keep_props = ['GEOID20','F2024_Child_Poverty_Rate__2026_','F2024_Child_Poverty_Rate_Margin_Of_Error','SCHOOL_BND_INT_CPG_TOTAL']
feats = [{'type':'Feature','geometry':f['geometry'],'properties':{k:f['properties'].get(k) for k in keep_props}}
         for f in src['features']
         if f['properties'].get('JURSCODE') == 'BACI' and f['properties'].get('GEOID20') in geoids]
json.dump({'type':'FeatureCollection','features':feats}, open('docs/data/grantee_tracts.geojson','w'))
print(len(feats), 'grantee tracts written')
"
```

After refreshing ANY source layer (grantee tracts or any incentive layer), rebuild the
crosswalk so `crosswalk.json` stays in sync (the map + crosswalk page both read it):
```bash
python3 -m venv .venv-geo && .venv-geo/bin/pip install -r scripts/requirements-crosswalk.txt
.venv-geo/bin/python scripts/build_crosswalk.py          # rebuild docs/data/crosswalk.json
.venv-geo/bin/python scripts/build_crosswalk.py --check   # verify JSON matches source data
```
`build_crosswalk.py` stamps a `source_hash` into the JSON; `--check` fails (exit 1) if the
committed `crosswalk.json` is stale vs. the source geojson. Run it before any external share.

## Deploy

Push to `main` → GitHub Pages auto-deploys from `docs/`.

## Key Numbers (as of May 2026)

- 28 active ENOUGH grantees, 111 grantee tracts statewide (40 in Baltimore City)
- 1,192 BVRI Vacants to Value properties (Baltimore City only)
- 7 DHCD Impact Investment Areas (Baltimore City only)
- 587 NMTC-eligible tracts statewide (350 Severe Distress, 237 Distressed)
- 149 designated Opportunity Zones statewide (2018 TCJA, in effect through 2028; 47 rural)
- 451 OZ 2.0-eligible tracts statewide (2020–2024 ACS via opportunityzones.com; MD may nominate up to 113, effective 2027).
  **92** grantee tracts (26/28 communities) are OZ 2.0-eligible — exact-GEOID join
- 419 designated **Just Communities** statewide (Just Communities Act of 2024, HB 241/SB 308; MD DHCD via iMap
  `MD_HousingDesignatedAreas` Layer 9). **81** grantee tracts (26/28 communities) are Just Communities — exact-GEOID
  join. DHCD Methodology **v1.0** (2025-04-23): 4 of 14 legislated criteria had no data; qualifying score ≥13.5 is an
  administrative cutoff, not statutory; results clipped to Priority Funding Areas. A v2.0 will move both counts.
  **Careful with `redlining`:** it is only ever `true` (184) or `null` (235) — never `false`. HOLC mapped only a few
  Maryland cities, so `null` means "no HOLC map here", NOT "not redlined". Never report the complement as un-redlined.
- 32 Maryland Enterprise Zones + 2 Focus Areas statewide; **86** grantee tracts touch an Enterprise Zone
  (any-overlap; headline). A stricter ≥5%-area test gives **71** (footnoted on the crosswalk page — the
  15-tract gap is boundary slivers). EZ uses any-overlap because it has no tract-based ground truth to
  validate a threshold against; OZ keeps 5% because that reproduces its exact-GEOID count. Map reads both
  from `crosswalk.json`.

### ENOUGH Crosswalk overlap (from `crosswalk.json`)
- NMTC: 28/28 communities, 102/111 tracts (86 Severe Distress, 16 Distressed) — every community is NMTC-eligible
- Opportunity Zones (designated): 20/28 communities, 38/111 tracts (≥5% area)
- OZ 2.0-eligible: 26/28 communities, 92/111 tracts (exact GEOID; 20% of the 451-tract eligible pool)
- Enterprise Zones: 21/28 communities, 86/111 tracts (any overlap; 71 at ≥5% area)
- Just Communities: 26/28 communities, 81/111 tracts (exact GEOID; 19% of the 419 statewide). The 30
  non-designated grantee tracts cluster in Prince George's (10) + Anne Arundel (7); Caroline Human Services
  Council and One Annapolis have zero. Excluded from the stacking histogram (funding priority, not a tax credit)
- BVRI Vacants: 10/28 communities, 33/111 tracts (565 of 1,192 properties inside a grantee tract)
- DHCD Impact Areas: 6/28 communities, 21/111 tracts
- Stacking (statewide NMTC/OZ/EZ, EZ any-overlap): 6 tracts in zero program, 15 in one, 59 in two,
  31 in all three; all 28 communities are in at least one
