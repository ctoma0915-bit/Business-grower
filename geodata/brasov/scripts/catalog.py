"""Single source of truth for every published layer: file, title, description, source, licence.
Used by 09_package.py (GeoPackage descriptions + LAYERS.md) and 10_qgis_project.py (groups)."""

SRC = {
    "gb": ("geoBoundaries gbOpen ROU (ADM1: World Bank; ADM2: ANCPI cadastre)", "CC BY 4.0"),
    "ov": ("Overture Maps Foundation, release {overture} (OpenStreetMap + Microsoft/Google ML "
           "buildings)", "ODbL 1.0 (© OpenStreetMap contributors, Overture Maps)"),
    "ovp": ("Overture Maps Foundation places, release {overture}", "CDLA-Permissive-2.0"),
    "dem": ("Copernicus DEM GLO-30 (DLR/Airbus, ESA)", "Copernicus DEM licence (free, attribution)"),
    "demd": ("Derived from Copernicus DEM GLO-30 (this pipeline: GDAL / WhiteboxTools)",
             "Copernicus DEM licence (free, attribution)"),
    "hwsd": ("FAO & IIASA Harmonized World Soil Database v2.0 (ESDB-based in Romania)",
             "FAO/IIASA terms (CC BY-NC-SA 3.0 IGO) - check before commercial use"),
    "gsw": ("EC JRC Global Surface Water v1.4, 1984-2021 (Pekel et al. 2016)",
            "Free, attribution required"),
    "wc": ("ESA WorldCover 10 m 2021 v200", "CC BY 4.0"),
    "chm": ("Meta & WRI High Resolution Canopy Height Maps (Tolan et al. 2024), ~1 m source",
            "CC BY 4.0"),
    "s2": ("Copernicus Sentinel-2 L2A, {s2date} (AWS sentinel-cogs)",
           "Copernicus open licence (contains modified Copernicus Sentinel data)"),
}

# (gpkg file stem, layer, stage step, title, description, source key)
VECTORS = [
    ("brasov_admin", "admin_county", "boundaries", "County boundary",
     "Județul Brașov outline = dissolve of the 58 official ANCPI UAT polygons.", "gb"),
    ("brasov_admin", "admin_uat", "boundaries", "UATs (municipalities, towns, communes)",
     "58 administrative-territorial units with rank and a planning statistics block "
     "(elevation, slope, land cover, flood susceptibility, soil, buildings, roads).", "gb"),
    ("brasov_admin", "admin_counties_context", "boundaries", "Neighbouring counties",
     "Brașov and its 8 neighbouring counties, for map context.", "gb"),
    ("brasov_admin", "settlements", "overture", "Settlements (points)",
     "Cities, towns, villages and hamlets with names (and population where known).", "ov"),

    ("brasov_topography", "topo_contours_10m", "terrain", "Contours 10 m",
     "Contour lines every 10 m (kind: regular_10m / intermediate_50m / index_100m), from a "
     "lightly smoothed 25 m DEM. Heights are EGM2008 geoid (DSM - includes canopy/buildings).",
     "demd"),
    ("brasov_topography", "topo_peaks", "overture", "Peaks, saddles, caves, cliffs",
     "Named terrain points from OpenStreetMap, with elevation where tagged.", "ov"),
    ("brasov_topography", "land_natural_areas", "overture", "Natural land cover areas (OSM)",
     "Forest, grassland, scrub, wetland, rock, scree polygons mapped in OpenStreetMap.", "ov"),
    ("brasov_topography", "land_natural_lines", "overture", "Natural lines (OSM)",
     "Ridges, cliffs and other linear natural features.", "ov"),

    ("brasov_water", "hydro_streams", "hydrology", "Stream network (DEM-derived)",
     "D8 channels with >= 1 km2 upstream area, routed on a DEM with the mapped OSM waterways "
     "burned in (95 % of mapped river length within 25 m). Strahler & Shreve order, upstream "
     "area at the segment outlet, mean gradient. Upstream area is complete (whole Olt basin).",
     "demd"),
    ("brasov_water", "hydro_subbasins", "hydrology", "Sub-catchments",
     "One catchment per stream link of the >= 10 km2 network (planning-scale catchments).",
     "demd"),
    ("brasov_water", "hydro_drainage_basins", "hydrology", "Major drainage basins",
     "Basins draining out of the modelling window (Olt, Prahova, Buzău, Dâmbovița, ...).",
     "demd"),
    ("brasov_water", "water_lines", "overture", "Rivers, streams, canals, ditches (OSM)",
     "Mapped watercourses with names and class (river/stream/canal/drain/ditch).", "ov"),
    ("brasov_water", "water_areas", "overture", "Lakes, reservoirs, ponds, riverbanks (OSM)",
     "Mapped water bodies.", "ov"),
    ("brasov_water", "water_points", "overture", "Springs and water points (OSM)",
     "Springs, wells, water taps and similar point features.", "ov"),

    ("brasov_soil", "soil_hwsd_units", "soil", "Soil mapping units (HWSD v2)",
     "~1 km soil units: dominant WRB 2022 soil, all components, drainage, rootable depth, "
     "AWC, topsoil (0-20 cm) and subsoil (20-100 cm) texture, OC, pH, CEC, bulk density, "
     "CaCO3, plus a texture/drainage-based NRCS hydrologic soil group (A-D).", "hwsd"),
    ("brasov_soil", "soil_hwsd_components", "soil", "Soil components (table)",
     "Every soil component of every mapping unit with its share (%).", "hwsd"),
    ("brasov_soil", "soil_hwsd_layers", "soil", "Soil horizons D1-D7 (table)",
     "Full lab-property profile 0-200 cm for every component (join on hwsd2_smu_id).", "hwsd"),

    ("brasov_landuse_infrastructure", "landuse", "overture", "Land use (OSM)",
     "Residential, industrial, farmland, meadow, orchard, parks, cemeteries, quarries, ...",
     "ov"),
    ("brasov_landuse_infrastructure", "protected_areas", "overture",
     "Protected areas & well protection zones (OSM)",
     "Nature reserves/parks and drinking-water well protection zones mapped in OSM. NOT a "
     "complete Natura 2000 / ANANP inventory.", "ov"),
    ("brasov_landuse_infrastructure", "transport_roads", "overture", "Roads",
     "Road segments with class, name, national/European route refs (DN/DJ/E), surface, "
     "speed limit, level (bridges/tunnels).", "ov"),
    ("brasov_landuse_infrastructure", "transport_rail", "overture", "Railways", "Rail segments.",
     "ov"),
    ("brasov_landuse_infrastructure", "infrastructure_lines", "overture",
     "Linear infrastructure", "Power lines, bridges, dams, pipelines, aerialways, fences.", "ov"),
    ("brasov_landuse_infrastructure", "infrastructure_points", "overture",
     "Point infrastructure", "Power towers, transformers, hydrants, stops, crossings, ...", "ov"),
    ("brasov_landuse_infrastructure", "infrastructure_areas", "overture",
     "Infrastructure areas", "Substations, power plants, parking, storage tanks, dams, ...", "ov"),
    ("brasov_landuse_infrastructure", "places_poi", "overture", "Points of interest",
     "Businesses, public services, schools, health, tourism (confidence >= 0.5).", "ovp"),

    ("brasov_buildings", "buildings", "overture", "Building footprints",
     "All building footprints (OSM + Microsoft ML) with class, height/floors where known.",
     "ov"),
]

# (file, group, title, description, source key)
RASTERS = [
    ("imagery_sentinel2_truecolor_10m.tif", "Imagery", "Sentinel-2 true colour 10 m",
     "Single-pass cloud-free mosaic (offline basemap).", "s2"),
    ("topo_dem_25m.tif", "Topography", "Elevation (DEM) 25 m",
     "Metres above EGM2008 geoid. Surface model: includes forest canopy and buildings.", "dem"),
    ("topo_hillshade.tif", "Topography", "Hillshade", "Multidirectional hillshade.", "demd"),
    ("topo_slope_deg.tif", "Topography", "Slope (degrees)", "Slope in degrees.", "demd"),
    ("topo_slope_classes.tif", "Topography", "Slope classes (planning)",
     "1 <2%, 2 2-5%, 3 5-10%, 4 10-15%, 5 15-25%, 6 25-35%, 7 35-50%, 8 >=50%.", "demd"),
    ("topo_aspect_deg.tif", "Topography", "Aspect (degrees)",
     "Downslope direction, 0 = north, clockwise; 0 also for flat cells.", "demd"),
    ("topo_ruggedness_tri.tif", "Topography", "Terrain ruggedness index",
     "Riley TRI (m).", "demd"),
    ("topo_landforms_geomorphons.tif", "Topography", "Landforms (geomorphons)",
     "1 flat, 2 peak, 3 ridge, 4 shoulder, 5 spur, 6 slope, 7 hollow, 8 footslope, 9 valley, "
     "10 pit.", "demd"),
    ("hydro_flood_susceptibility.tif", "Water", "Flood susceptibility (HAND classes)",
     "Height above nearest drainage: 1 <1 m very high, 2 1-3 m high, 3 3-5 m moderate, "
     "4 5-10 m low, 5 >=10 m very low. Screening proxy, not an official flood map.", "demd"),
    ("hydro_hand_m.tif", "Water", "Height above nearest drainage (m)",
     "Vertical distance to the stream cell each cell drains to.", "demd"),
    ("hydro_twi.tif", "Water", "Topographic wetness index",
     "ln(a / tan b) from D-infinity specific catchment area; high = wet/saturation-prone.",
     "demd"),
    ("hydro_upstream_area_km2.tif", "Water", "Upstream (contributing) area km2",
     "D8 flow accumulation expressed in km2.", "demd"),
    ("hydro_flow_dir_d8.tif", "Water", "Flow direction D8 (ESRI codes)",
     "1 E, 2 SE, 4 S, 8 SW, 16 W, 32 NW, 64 N, 128 NE; 0 = no downslope neighbour.", "demd"),
    ("water_gsw_occurrence.tif", "Water", "Surface water occurrence 1984-2021 (%)",
     "Share of valid satellite observations with water; never-water cells are nodata.", "gsw"),
    ("water_gsw_recurrence.tif", "Water", "Surface water recurrence (%)",
     "How often water returns from year to year.", "gsw"),
    ("water_gsw_seasonality.tif", "Water", "Surface water seasonality 2021 (months)",
     "Number of months with water in 2021.", "gsw"),
    ("water_gsw_transitions.tif", "Water", "Surface water change 1984-2021",
     "1 permanent, 2 new permanent, 3 lost permanent, 4 seasonal, 5 new seasonal, 6 lost "
     "seasonal, 7 seasonal->permanent, 8 permanent->seasonal, 9 ephemeral permanent, "
     "10 ephemeral seasonal.", "gsw"),
    ("canopy_height_5m.vrt", "Land cover", "Tree canopy height 5 m",
     "Mean height (m) of tree canopy >= 2 m in each 5 m cell where canopy covers >= 50 % of it; "
     "0 = no canopy. From a ~1 m canopy height model of Maxar imagery (c. 2010-2020). "
     "VRT over 4 COG quadrants (canopy_height_5m_{nw,ne,sw,se}.tif).", "chm"),
    ("landcover_worldcover_10m.tif", "Land cover", "Land cover 10 m (ESA WorldCover 2021)",
     "10 trees, 20 shrubland, 30 grassland, 40 cropland, 50 built-up, 60 bare/sparse, "
     "70 snow/ice, 80 water, 90 herbaceous wetland, 100 moss/lichen.", "wc"),
]
