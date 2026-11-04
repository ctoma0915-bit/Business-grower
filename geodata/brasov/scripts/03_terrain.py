"""Topography from the Copernicus GLO-30 DEM: elevation, hillshade, slope, aspect, ruggedness,
landforms (geomorphons), planning slope classes and contour lines.

The DEM is resampled once onto a 25 m EPSG:3844 grid that covers the whole hydrology window;
every later raster (terrain + hydrology) is cut from that same grid, so all cells line up.
"""
import math
import urllib.request

import geopandas as gpd
import numpy as np
import rasterio
from scipy.ndimage import gaussian_filter

from common import (COG_BYTE_CAT, COG_INT, CRS, RASTER, RAW, RES, WORK, aoi_bounds_3844,
                    aoi_path, run, stage_gpkg, warp_to_aoi)

DEM_URL = "https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif"
TILES = [f"Copernicus_DSM_COG_10_N{lat}_00_E{lon:03d}_00_DEM" for lat in (45, 46) for lon in (24, 25, 26)]

# Lossy-but-bounded LERC compression: max absolute error per cell, in the layer's units.
def cog_lerc(max_err: float) -> list[str]:
    return ["-of", "COG", "-co", "COMPRESS=LERC_ZSTD", "-co", f"MAX_Z_ERROR={max_err}",
            "-co", "BLOCKSIZE=512", "-co", "OVERVIEWS=AUTO", "-co", "RESAMPLING=AVERAGE"]


def snap(b, s=RES, pad=0.0):
    minx, miny, maxx, maxy = b
    return (math.floor((minx - pad) / s) * s, math.floor((miny - pad) / s) * s,
            math.ceil((maxx + pad) / s) * s, math.ceil((maxy + pad) / s) * s)


def download() -> list:
    out = []
    for n in TILES:
        dst = RAW / "dem" / f"{n}.tif"
        dst.parent.mkdir(exist_ok=True)
        if not dst.exists():
            urllib.request.urlretrieve(DEM_URL.format(n=n), dst)
        out.append(dst)
    return out


def main() -> None:
    tiles = download()
    vrt = WORK / "dem_wgs84.vrt"
    run(["gdalbuildvrt", "-overwrite", vrt, *tiles])

    # 1. Hydrology-window DEM (also the master grid).
    hb = snap(gpd.read_file(WORK / "hydro_extent.gpkg").total_bounds)
    dem_hydro = WORK / "dem_hydro.tif"
    run(["gdalwarp", "-overwrite", "-t_srs", CRS, "-tr", RES, RES, "-te", *hb, "-r", "bilinear",
         "-ot", "Float32", "-dstnodata", -9999, "-multi", "-wo", "NUM_THREADS=ALL_CPUS",
         "-co", "COMPRESS=DEFLATE", "-co", "TILED=YES", "-co", "BIGTIFF=YES", vrt, dem_hydro])

    # 2. AOI window + 2 km margin for edge-free derivatives.
    mb = snap(aoi_bounds_3844(), pad=2000)
    dem_m = WORK / "dem_margin.tif"
    run(["gdal_translate", "-projwin", mb[0], mb[3], mb[2], mb[1], "-co", "COMPRESS=DEFLATE",
         "-co", "TILED=YES", dem_hydro, dem_m])

    warp_to_aoi(dem_m, RASTER / "topo_dem_25m.tif", resampling="near", cog=cog_lerc(0.01),
                nodata=-9999)

    # 3. Classic gdaldem derivatives.
    hs, slope, slope_p, aspect, tri = (WORK / f"{k}.tif" for k in
                                       ("hillshade", "slope", "slope_pct", "aspect", "tri"))
    run(["gdaldem", "hillshade", "-multidirectional", "-z", "1.5", "-compute_edges", dem_m, hs])
    run(["gdaldem", "slope", "-compute_edges", dem_m, slope])
    run(["gdaldem", "slope", "-p", "-compute_edges", dem_m, slope_p])
    run(["gdaldem", "aspect", "-zero_for_flat", "-compute_edges", dem_m, aspect])
    run(["gdaldem", "TRI", "-alg", "Riley", "-compute_edges", dem_m, tri])

    warp_to_aoi(hs, RASTER / "topo_hillshade.tif", resampling="near", cog=COG_INT, nodata=0)
    warp_to_aoi(slope, RASTER / "topo_slope_deg.tif", resampling="near", cog=cog_lerc(0.05),
                nodata=-9999)
    warp_to_aoi(aspect, RASTER / "topo_aspect_deg.tif", resampling="near", cog=COG_INT,
                nodata=-9999, extra=["-ot", "Int16"])
    warp_to_aoi(tri, RASTER / "topo_ruggedness_tri.tif", resampling="near", cog=cog_lerc(0.05),
                nodata=-9999)

    # 4. Planning slope classes (percent): 1 <2, 2 2-5, 3 5-10, 4 10-15, 5 15-25, 6 25-35,
    #    7 35-50, 8 >=50.
    with rasterio.open(slope_p) as src:
        sp = src.read(1)
        prof = src.profile
        nd = src.nodata
    cls = np.digitize(sp, [2, 5, 10, 15, 25, 35, 50]).astype("uint8") + 1
    cls[(sp == nd) | ~np.isfinite(sp)] = 0
    prof.update(dtype="uint8", nodata=0, compress="zstd")
    slope_cls = WORK / "slope_classes.tif"
    with rasterio.open(slope_cls, "w", **prof) as dst:
        dst.write(cls, 1)
    warp_to_aoi(slope_cls, RASTER / "topo_slope_classes.tif", resampling="near", cog=COG_BYTE_CAT,
                nodata=0)

    # 5. Geomorphons landform classification (Jasiewicz & Stepinski 2013), 10 classes.
    geom = WORK / "geomorphons.tif"
    run(["whitebox_tools", "-r=Geomorphons", f"--dem={dem_m}", f"--output={geom}",
         "--search=40", "--threshold=1.0", "--fdist=0", "--skip=0", "--forms"])
    warp_to_aoi(geom, RASTER / "topo_landforms_geomorphons.tif", resampling="near",
                cog=COG_BYTE_CAT, nodata=0, extra=["-ot", "Byte"])

    # 6. Contours from a lightly smoothed DEM (sigma = 1 cell) for clean cartographic lines.
    with rasterio.open(dem_m) as src:
        z = src.read(1)
        prof = src.profile
    valid = z != -9999
    zs = gaussian_filter(np.where(valid, z, np.nanmean(z[valid])), sigma=1.0)
    zs[~valid] = -9999
    smooth = WORK / "dem_smooth.tif"
    with rasterio.open(smooth, "w", **prof) as dst:
        dst.write(zs.astype("float32"), 1)
    raw_ct = WORK / "contours_raw.gpkg"
    raw_ct.unlink(missing_ok=True)
    run(["gdal_contour", "-a", "elev_m", "-i", 10, "-snodata", -9999, "-nln", "contours",
         smooth, raw_ct])
    ct = gpd.read_file(raw_ct)
    aoi = gpd.read_file(aoi_path()).geometry.iloc[0]
    ct = ct[ct.intersects(aoi)]
    ct["geometry"] = ct.geometry.simplify(2.0).intersection(aoi)
    ct = ct[~ct.is_empty]
    ct = ct.explode(index_parts=False)
    ct = ct[ct.geom_type == "LineString"]
    ct["elev_m"] = ct["elev_m"].round().astype(int)
    ct["kind"] = np.where(ct.elev_m % 100 == 0, "index_100m",
                          np.where(ct.elev_m % 50 == 0, "intermediate_50m", "regular_10m"))
    ct = ct[["elev_m", "kind", "geometry"]].reset_index(drop=True)
    ct.to_file(stage_gpkg("terrain"), layer="topo_contours_10m", driver="GPKG")
    print("contours:", len(ct))


if __name__ == "__main__":
    main()
