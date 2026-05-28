# CLAUDE.md — ENOUGH × BVRI Map

## What This Is

Single-page interactive Leaflet map showing the overlap between:
- **ENOUGH Act** eligible census tracts in Baltimore City (GOC)
- **Baltimore Vacants Reinvestment Initiative (BVRI)** properties — specifically the "Vacants to Value" open bid list and DHCD Impact Investment Areas

Requested by Mihir Parikh. Goal: let GOC and BVRI partners see where their work intersects, and pull rough counts.

**Live site:** https://maryland-governors-office-for-children.github.io/enough-bvri-map/
**Source repo:** https://github.com/Maryland-Governors-Office-for-Children/enough-bvri-map

## Repo Structure

```
docs/                    GitHub Pages site (index.html + data/)
  index.html             Single-page Leaflet map
  .nojekyll
  data/
    tracts_baltimore.geojson     199 Baltimore City tracts (slimmed from statewide)
    grantee_geoids.json          ENOUGH grantee tract GEOIDs (copied from eligibility repo)
    bvri_vacants.geojson         1,192 Vacants to Value properties (from DHCD ArcGIS)
    bvri_investment_areas.geojson  7 DHCD Impact Investment Area polygons
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

ENOUGH tract data is copied from `enough-eligibility-changes` repo. Re-copy if that repo's data is refreshed:
```bash
cp ../enough-eligibility-analysis/docs/data/tracts_2026.geojson /tmp/ && \
python3 -c "
import json
g = json.load(open('/tmp/tracts_2026.geojson'))
keep = ['GEOID20','JURSCODE','Eligibility_Status','Qualifying_Criteria1_CPR_30',
        'Qualifying_Criteria2_CPR_30MOE','F2024_Child_Poverty_Rate__2026_',
        'F2024_Child_Poverty_Rate_Margin_Of_Error','SCHOOL_BND_INT_CPG_TOTAL','SCHOOL_NAME']
feats = [{'type':'Feature','geometry':f['geometry'],'properties':{k:f['properties'].get(k) for k in keep}}
         for f in g['features'] if f['properties'].get('JURSCODE') == 'BACI']
json.dump({'type':'FeatureCollection','features':feats}, open('docs/data/tracts_baltimore.geojson','w'))
print(len(feats), 'tracts written')
"
```

## Deploy

Push to `main` → GitHub Pages auto-deploys from `docs/`.

## Key Numbers (as of May 2026)

- 199 Baltimore City census tracts
- 85 ENOUGH eligible (both tests pass)
- 43 active grantee tracts
- 1,192 BVRI Vacants to Value properties
- 7 DHCD Impact Investment Areas
