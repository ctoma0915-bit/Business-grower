#!/usr/bin/env bash
# Rebuild the whole Brașov County export from the original open-data sources.
# Requires the conda environment in environment.yml (GDAL, QGIS, WhiteboxTools, mdbtools).
set -euo pipefail
cd "$(dirname "$0")"
export GDAL_HTTP_MULTIRANGE=YES GDAL_HTTP_MAX_RETRY=5
# Only for steps that read remote rasters: it also hides sidecar files (e.g. HWSD .hdr).
REMOTE="env GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR"
export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen}

python 01_boundaries.py      # county, 58 UATs, AOI, hydrology window
python 02_overture.py        # roads, rail, buildings, water, land use, infrastructure, POIs
python 03_terrain.py         # DEM, hillshade, slope, aspect, TRI, geomorphons, contours
python 04_hydrology.py       # flow routing, streams, catchments, HAND, TWI, flood classes
python 05_soil.py            # HWSD v2 soil units + full horizon tables
# python 05b_soilgrids_optional.py   # SoilGrids 250 m (needs access to files.isric.org)
$REMOTE python 06_water_landcover.py # JRC surface water history, ESA WorldCover
$REMOTE python 07_imagery.py # Sentinel-2 cloud-free true-colour mosaic
python 08_canopy.py          # 5 m tree canopy height from the ~1 m Meta/WRI model (5 GB download)
python 09_package.py         # thematic GeoPackages, UAT statistics, LAYERS.md
python 10_qgis_project.py    # QGIS project, default styles, A3 layouts, previews
python 11_single_gpkg.py     # one-file package: everything + project in brasov_county_qgis.gpkg
