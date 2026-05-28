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
  .nojekyll
  data/
    grantee_tracts.geojson         111 active ENOUGH grantee tracts statewide
    grantees.json                  28 grantee organizations with tract counts
    grantee_geoids.json            ENOUGH grantee tract GEOIDs (statewide, legacy, kept for backwards-compat)
    bvri_vacants.geojson           1,192 Vacants to Value properties (Baltimore City, from DHCD ArcGIS)
    bvri_investment_areas.geojson  7 DHCD Impact Investment Area polygons (Baltimore City)
    nmtc_maryland.geojson          587 NMTC-eligible tracts statewide (CDFI Fund)
    oz_maryland.geojson            451 Opportunity Zones 2026 eligible tracts (MD Commerce / EIG)
scripts/
  fetch_bvri.py          Refresh BVRI data from Baltimore City DHCD ArcGIS REST
```

## How to Refresh Data

```bash
python3 scripts/fetch_bvri.py   # re-fetches bvri_vacants.geojson + bvri_investment_areas.geojson
# then commit docs/data/bvri_vacants.geojson
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

## Deploy

Push to `main` → GitHub Pages auto-deploys from `docs/`.

## Key Numbers (as of May 2026)

- 28 active ENOUGH grantees, 111 grantee tracts statewide (40 in Baltimore City)
- 1,192 BVRI Vacants to Value properties (Baltimore City only)
- 7 DHCD Impact Investment Areas (Baltimore City only)
- 587 NMTC-eligible tracts statewide (350 Severe Distress, 237 Distressed)
- 451 Opportunity Zones 2026 eligible tracts statewide (383 Non-rural, 68 Rural)
