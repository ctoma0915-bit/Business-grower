"""DEM-derived hydrology with WhiteboxTools on the wide hydrology window (whole upstream Olt basin).

Outputs (clipped to the AOI):
  raster: hydro_flow_dir_d8.tif (ESRI D8 codes), hydro_upstream_area_km2.tif,
          hydro_hand_m.tif (height above nearest drainage), hydro_twi.tif (topographic wetness),
          hydro_flood_susceptibility.tif (HAND classes)
  vector: hydro_streams (Strahler/Shreve order, upstream area), hydro_subbasins (>=10 km2 links),
          hydro_basins_outlets (major drainage systems leaving the window)
"""
import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import shapes
import shapely

from common import COG_BYTE_CAT, COG_INT, CRS, RASTER, RES, WORK, aoi_path, run, stage_gpkg, warp_to_aoi

STREAM_KM2 = 1.0      # channel initiation threshold for the stream network & HAND
SUBBASIN_KM2 = 10.0   # stream links used to delineate planning sub-catchments
CELL_KM2 = RES * RES / 1e6

W = WORK / "hydro"
W.mkdir(exist_ok=True)


def wbt(tool: str, **kw) -> None:
    run(["whitebox_tools", f"-r={tool}", f"--wd={W}", "-v=false",
         *[f"--{k}={v}" if v is not True else f"--{k}" for k, v in kw.items()]])


def cog_lerc(max_err):
    return ["-of", "COG", "-co", "COMPRESS=LERC_ZSTD", "-co", f"MAX_Z_ERROR={max_err}",
            "-co", "BLOCKSIZE=512", "-co", "OVERVIEWS=AUTO"]


def main() -> None:
    dem = WORK / "dem_hydro.tif"
    # 1. Hydrological conditioning: least-cost breaching (handles bridges/dams in the DSM),
    #    then fill whatever remains.
    wbt("BreachDepressionsLeastCost", dem=dem, output="dem_breach.tif", dist=200, fill=True)
    wbt("FillDepressions", dem="dem_breach.tif", output="dem_cond.tif", fix_flats=True)

    # 2. D8 routing.
    wbt("D8Pointer", dem="dem_cond.tif", output="d8.tif")
    wbt("D8Pointer", dem="dem_cond.tif", output="d8_esri.tif", esri_pntr=True)
    wbt("D8FlowAccumulation", i="d8.tif", output="acc_cells.tif", out_type="cells", pntr=True)

    # 3. Streams.
    wbt("ExtractStreams", flow_accum="acc_cells.tif", output="streams.tif",
        threshold=int(STREAM_KM2 / CELL_KM2))
    wbt("StrahlerStreamOrder", d8_pntr="d8.tif", streams="streams.tif", output="strahler.tif")
    wbt("ShreveStreamMagnitude", d8_pntr="d8.tif", streams="streams.tif", output="shreve.tif")
    wbt("RasterStreamsToVector", streams="strahler.tif", d8_pntr="d8.tif", output="streams.shp")

    # 4. HAND + flood susceptibility classes.
    wbt("ElevationAboveStream", dem="dem_cond.tif", streams="streams.tif", output="hand.tif")

    # 5. Topographic wetness index from D-infinity specific contributing area.
    wbt("DInfFlowAccumulation", i="dem_cond.tif", output="sca.tif", out_type="sca")
    wbt("Slope", dem="dem_cond.tif", output="slope_cond.tif", units="degrees")
    wbt("WetnessIndex", sca="sca.tif", slope="slope_cond.tif", output="twi.tif")

    # 6. Planning sub-catchments: one per stream link of the >=10 km2 network.
    wbt("ExtractStreams", flow_accum="acc_cells.tif", output="streams10.tif",
        threshold=int(SUBBASIN_KM2 / CELL_KM2))
    wbt("Subbasins", d8_pntr="d8.tif", streams="streams10.tif", output="subbasins.tif")
    wbt("Basins", d8_pntr="d8.tif", output="basins.tif")

    # ---- rasters to the AOI grid -------------------------------------------------------
    with rasterio.open(W / "acc_cells.tif") as src:
        prof = src.profile
        acc = src.read(1).astype("float32")
        acc_nd = src.nodata
    up = np.where(acc == acc_nd, -9999, acc * CELL_KM2).astype("float32")
    prof.update(dtype="float32", nodata=-9999, compress="deflate")
    with rasterio.open(W / "upstream_km2.tif", "w", **prof) as dst:
        dst.write(up, 1)

    with rasterio.open(W / "hand.tif") as src:
        hand = src.read(1)
        hprof = src.profile
        hnd = src.nodata
    # 1 very high (<1 m), 2 high (1-3), 3 moderate (3-5), 4 low (5-10), 5 very low (>=10)
    fs = (np.digitize(hand, [1, 3, 5, 10]) + 1).astype("uint8")
    fs[hand == hnd] = 0
    hprof.update(dtype="uint8", nodata=0, compress="deflate")
    with rasterio.open(W / "flood_susc.tif", "w", **hprof) as dst:
        dst.write(fs, 1)

    # nodata 255: 0 is a valid ESRI code (no downslope neighbour) and must not be remapped.
    warp_to_aoi(W / "d8_esri.tif", RASTER / "hydro_flow_dir_d8.tif", resampling="near",
                cog=COG_BYTE_CAT, nodata=255, extra=["-ot", "Byte"])
    warp_to_aoi(W / "upstream_km2.tif", RASTER / "hydro_upstream_area_km2.tif", resampling="near",
                cog=cog_lerc(0.0001), nodata=-9999)
    warp_to_aoi(W / "hand.tif", RASTER / "hydro_hand_m.tif", resampling="near", cog=cog_lerc(0.05),
                nodata=-9999, extra=["-ot", "Float32"])
    warp_to_aoi(W / "twi.tif", RASTER / "hydro_twi.tif", resampling="near", cog=cog_lerc(0.02),
                nodata=-9999, extra=["-ot", "Float32"])
    warp_to_aoi(W / "flood_susc.tif", RASTER / "hydro_flood_susceptibility.tif",
                resampling="near", cog=COG_BYTE_CAT, nodata=0)

    # ---- vectors -----------------------------------------------------------------------
    aoi = gpd.read_file(aoi_path()).geometry.iloc[0]
    out = stage_gpkg("hydrology")

    st = gpd.read_file(W / "streams.shp").set_crs(CRS, allow_override=True)
    st = st[st.intersects(aoi)].copy()
    st = st.rename(columns={"STRM_VAL": "strahler"})
    # Each vector link ends ON the downstream confluence cell (so the network connects), and
    # that cell already carries the receiving river's flow. Upstream area and Shreve magnitude
    # are therefore sampled one vertex upstream of the outlet; the drop uses the outlet itself.
    with rasterio.open(W / "upstream_km2.tif") as a, rasterio.open(W / "shreve.tif") as sh, \
            rasterio.open(W / "dem_cond.tif") as z:
        lines = []
        for g in st.geometry:
            line = g if g.geom_type == "LineString" else shapely.line_merge(g)
            lines.append(np.asarray(line.coords if line.geom_type == "LineString"
                                    else line.geoms[0].coords))
        acc_first = np.array([v[0] for v in a.sample([c[0] for c in lines])])
        acc_last = np.array([v[0] for v in a.sample([c[-1] for c in lines])])
        down_is_last = acc_last >= acc_first
        outlet = [c[-1] if d else c[0] for c, d in zip(lines, down_is_last)]
        inlet = [c[0] if d else c[-1] for c, d in zip(lines, down_is_last)]
        above_outlet = [c[-2] if d else c[1] for c, d in zip(lines, down_is_last)]
        st["upstream_km2"] = np.round([v[0] for v in a.sample(above_outlet)], 3)
        st["shreve"] = [int(v[0]) for v in sh.sample(above_outlet)]
        z_in = np.array([v[0] for v in z.sample(inlet)])
        z_out = np.array([v[0] for v in z.sample(outlet)])
    st["drop_m"] = np.round(np.maximum(z_in - z_out, 0), 1)
    st["gradient_pct"] = np.round(100 * st["drop_m"] / st.length.clip(lower=RES), 2)
    st["geometry"] = st.geometry.intersection(aoi)
    st = st[~st.is_empty].explode(index_parts=False)
    st = st[st.geom_type == "LineString"].copy()
    st["length_m"] = st.length.round(1)
    st = st[["strahler", "shreve", "upstream_km2", "gradient_pct", "length_m",
             "geometry"]].reset_index(drop=True)
    st.to_file(out, layer="hydro_streams", driver="GPKG")
    print("streams:", len(st), "max upstream km2:", st.upstream_km2.max())

    def polygonize(path, field):
        with rasterio.open(path) as src:
            arr = src.read(1)
            nd = src.nodata
            mask = arr != nd
            geoms = [(shapely.geometry.shape(g), int(v))
                     for g, v in shapes(arr.astype("int32"), mask=mask, transform=src.transform)]
        gdf = gpd.GeoDataFrame({field: [v for _, v in geoms]},
                               geometry=[g for g, _ in geoms], crs=CRS)
        return gdf.dissolve(by=field, as_index=False)

    sb = polygonize(W / "subbasins.tif", "subbasin_id")
    sb = sb[sb.intersects(aoi)].copy()
    sb["area_km2"] = (sb.area / 1e6).round(3)
    sb["share_in_aoi"] = (sb.intersection(aoi).area / sb.area).round(3)
    sb["geometry"] = sb.geometry.simplify(RES / 2)
    sb.to_file(out, layer="hydro_subbasins", driver="GPKG")
    print("subbasins:", len(sb))

    bs = polygonize(W / "basins.tif", "basin_id")
    bs["area_km2"] = (bs.area / 1e6).round(1)
    bs = bs[bs.intersects(aoi) & (bs.area_km2 >= 5)].copy()
    bs["area_in_aoi_km2"] = (bs.intersection(aoi).area / 1e6).round(1)
    bs = bs[bs.area_in_aoi_km2 >= 1].copy()
    bs["geometry"] = bs.geometry.simplify(RES)
    bs.to_file(out, layer="hydro_drainage_basins", driver="GPKG")
    print("basins:", len(bs))
    print(bs.sort_values("area_in_aoi_km2", ascending=False)[["basin_id", "area_km2",
                                                              "area_in_aoi_km2"]].head(10))


if __name__ == "__main__":
    main()
