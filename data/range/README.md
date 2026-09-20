# Longleaf pine natural range (Little)

Natural range of longleaf pine (*Pinus palustris*) from Elbert L. Little Jr.'s *Atlas of United States Trees*
(Critchfield & Little 1966 for the pines). Public domain: works prepared by US federal employees, not subject to copyright (17 U.S.C. 105).

| File | What it is |
|---|---|
| `pinupalu.geojson` | 38 polygons, no holes. Straight copy from the mirror below. **This is what the web map should read.** |
| `pinupalu.kml` | Same geometry, generated from the GeoJSON for viewing in Google Earth/QGIS. |

- **Source:** https://github.com/wpetry/USTreeAtlas (`geojson/pinupalu.geojson`, `shp/pinupalu/`). The original USGS
  server was taken down in 2017; that repo mirrors the 27 Jan 2017 Internet Archive snapshot.
- **CRS:** NAD27 (EPSG:4267). The GeoJSON and KML keep those coordinates unchanged, and treating them as WGS84 shifts
  points by well under ~100 m in the Southeast, which doesn't matter at this scale.
- **Caveat:** USGS withdrew these maps citing digitization errors; they're a coarse, 1970s-era generalization. Fine
  for a range mask, not for anything parcel-level.
- The original shapefile (`.shp/.shx/.dbf`, no `.prj` in the mirror) was deleted since the GeoJSON is identical geometry;
  re-download from the mirror if ever needed.
- `../surface/mask.npz` (the map mask: which 0.05 degree grid cells fall inside these polygons) was generated once from
  `pinupalu.geojson` by a point-in-polygon test. The range is fixed, so there is no script for it in the repo; the
  last version is in git history (`scripts/build_mask.py`, up to commit 48f60cb).
