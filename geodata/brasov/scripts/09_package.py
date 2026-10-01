"""Assemble the deliverable: thematic GeoPackages (with layer descriptions), a per-UAT planning
statistics block on admin_uat, and data/LAYERS.md (generated catalogue)."""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask

from catalog import RASTERS, SRC, VECTORS
from common import CRS, DATA, RASTER, RES, WORK, run, stage_gpkg


def fmt_src(key: str) -> tuple[str, str]:
    ctx = {"overture": json.loads((WORK / "overture_release.json").read_text())["release"],
           "s2date": json.loads((WORK / "s2_used.json").read_text())["date"]
           if (WORK / "s2_used.json").exists() else "n/a"}
    name, lic = SRC[key]
    return name.format(**ctx), lic


def zonal(uat: gpd.GeoDataFrame) -> pd.DataFrame:
    """Planning statistics per UAT from the published rasters and vectors."""
    rows = []
    r = {k: rasterio.open(RASTER / f) for k, f in {
        "dem": "topo_dem_25m.tif", "slope": "topo_slope_deg.tif",
        "scls": "topo_slope_classes.tif", "flood": "hydro_flood_susceptibility.tif",
        "wc": "landcover_worldcover_10m.tif"}.items()}

    def vals(key, geom):
        a, _ = mask(r[key], [geom], crop=True, filled=False)
        a = a[0]
        return a.compressed()

    for g in uat.geometry:
        dem, slope, scls, flood, wc = (vals(k, g) for k in ("dem", "slope", "scls", "flood", "wc"))
        n_wc = max(len(wc), 1)
        rows.append({
            "elev_min_m": round(float(dem.min()), 1), "elev_mean_m": round(float(dem.mean()), 1),
            "elev_max_m": round(float(dem.max()), 1),
            "slope_mean_deg": round(float(slope.mean()), 2),
            "pct_slope_lt5": round(100 * np.isin(scls, [1, 2]).mean(), 1),
            "pct_slope_5_15": round(100 * np.isin(scls, [3, 4]).mean(), 1),
            "pct_slope_15_25": round(100 * (scls == 5).mean(), 1),
            "pct_slope_gt25": round(100 * np.isin(scls, [6, 7, 8]).mean(), 1),
            "pct_flood_very_high_high": round(100 * np.isin(flood, [1, 2]).mean(), 1),
            "pct_forest": round(100 * (wc == 10).sum() / n_wc, 1),
            "pct_grassland": round(100 * (wc == 30).sum() / n_wc, 1),
            "pct_cropland": round(100 * (wc == 40).sum() / n_wc, 1),
            "pct_built_up": round(100 * (wc == 50).sum() / n_wc, 1),
            "pct_water": round(100 * (wc == 80).sum() / n_wc, 1),
        })
    for v in r.values():
        v.close()
    return pd.DataFrame(rows, index=uat.index)


def main() -> None:
    files = {}
    for stem, layer, step, title, desc, src in VECTORS:
        dst = DATA / f"{stem}.gpkg"
        if stem not in files:
            dst.unlink(missing_ok=True)
            files[stem] = dst
        if layer == "admin_uat":
            continue  # written below with statistics
        name, lic = fmt_src(src)
        run(["ogr2ogr", "-f", "GPKG", *(["-update"] if dst.exists() else []), dst,
             stage_gpkg(step), layer, "-nln", layer,
             "-lco", f"IDENTIFIER={title}", "-lco", f"DESCRIPTION={desc} Source: {name}. "
             f"Licence: {lic}."])

    # ---- UAT planning statistics --------------------------------------------------------
    uat = gpd.read_file(stage_gpkg("boundaries"), layer="admin_uat")
    uat = pd.concat([uat, zonal(uat)], axis=1)

    soil = gpd.read_file(stage_gpkg("soil"), layer="soil_hwsd_units")
    inter = gpd.overlay(uat[["name", "geometry"]], soil[["dominant_wrb", "hydrologic_soil_group",
                                                         "geometry"]], how="intersection")
    inter["a"] = inter.area
    dom_soil = inter.sort_values("a").groupby("name").last()
    uat["dominant_soil_wrb"] = uat.name.map(dom_soil.dominant_wrb)
    hsg = inter.groupby(["name", "hydrologic_soil_group"]).a.sum().unstack(fill_value=0)
    uat["pct_soil_hsg_d"] = uat.name.map((100 * hsg.get("D", 0) / hsg.sum(axis=1)).round(1))

    b = gpd.read_file(stage_gpkg("overture"), layer="buildings", columns=["footprint_m2"])
    bj = gpd.sjoin(gpd.GeoDataFrame(b.drop(columns="geometry"),
                                    geometry=b.representative_point(), crs=CRS),
                   uat[["name", "geometry"]], predicate="within")
    uat["n_buildings"] = uat.name.map(bj.groupby("name").size()).fillna(0).astype(int)
    uat["building_footprint_ha"] = uat.name.map(
        (bj.groupby("name").footprint_m2.sum() / 1e4).round(2)).fillna(0)

    roads = gpd.read_file(stage_gpkg("overture"), layer="transport_roads", columns=["class"])
    roads = roads[~roads["class"].isin(["footway", "path", "steps", "cycleway", "bridleway",
                                        "pedestrian", "track"])]
    rj = gpd.overlay(roads[["class", "geometry"]], uat[["name", "geometry"]], how="intersection",
                     keep_geom_type=True)
    rj["len"] = rj.length
    uat["road_km"] = uat.name.map((rj.groupby("name")["len"].sum() / 1000).round(1)).fillna(0)
    st = gpd.read_file(stage_gpkg("hydrology"), layer="hydro_streams")
    sj = gpd.overlay(st[["geometry"]], uat[["name", "geometry"]], how="intersection",
                     keep_geom_type=True)
    sj["len"] = sj.length
    uat["stream_density_km_km2"] = (uat.name.map(sj.groupby("name")["len"].sum() / 1000)
                                    / uat.area_km2).round(3)

    title, desc, src = [(t, d, s) for f, l, _, t, d, s in VECTORS if l == "admin_uat"][0]
    name, lic = fmt_src(src)
    uat.to_file(files["brasov_admin"], layer="admin_uat", driver="GPKG", engine="pyogrio",
                layer_options={"IDENTIFIER": title,
                               "DESCRIPTION": f"{desc} Source: {name}. Licence: {lic}."})
    uat.drop(columns="geometry").to_csv(DATA / "uat_planning_statistics.csv", index=False,
                                         encoding="utf-8-sig")  # BOM: Excel shows diacritics
    print(uat.drop(columns="geometry").head(5).T.to_string())

    # ---- catalogue -----------------------------------------------------------------------
    lines = ["# Layer catalogue - Brașov County geodata", "",
             f"All layers are in **{CRS} (Stereo 70)**. Rasters share one {RES} m grid "
             "(10 m for land cover and imagery) and are Cloud Optimized GeoTIFFs.", "",
             "## Vector layers (GeoPackage)", "",
             "| File | Layer | Features | Description | Source | Licence |",
             "|---|---|---:|---|---|---|"]
    import pyogrio
    for stem, layer, step, title, desc, src in VECTORS:
        n = pyogrio.read_info(DATA / f"{stem}.gpkg", layer=layer)["features"]
        name, lic = fmt_src(src)
        lines.append(f"| `{stem}.gpkg` | `{layer}` | {n:,} | **{title}.** {desc} | {name} | {lic} |")
    lines += ["", "## Raster layers (`raster/`)", "",
              "| File | Resolution | Type | Description | Source | Licence |",
              "|---|---|---|---|---|---|"]
    for f, group, title, desc, src in RASTERS:
        with rasterio.open(RASTER / f) as ds:
            res = f"{ds.res[0]:g} m"
            typ = f"{ds.count}x {ds.dtypes[0]}"
        name, lic = fmt_src(src)
        lines.append(f"| `raster/{f}` | {res} | {typ} | **{title}.** {desc} | {name} | {lic} |")
    lines += ["", "## UAT planning statistics", "",
              "`admin_uat` (and `uat_planning_statistics.csv`) carry, per UAT: elevation "
              "min/mean/max, mean slope, % area by slope band (<5, 5-15, 15-25, >25 %), % area "
              "with very high/high flood susceptibility (HAND < 3 m), % forest / grassland / "
              "cropland / built-up / water (WorldCover), dominant soil and % hydrologic soil "
              "group D, building count and footprint, road length (excl. paths/tracks) and "
              "DEM stream density.", ""]
    (DATA / "LAYERS.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
