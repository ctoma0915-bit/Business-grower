"""Tree canopy height at 5 m from Meta / WRI's global 1 m canopy height map (Tolan et al. 2024,
CHM v6, AWS Open Data `dataforgood-fb-data`, CC BY 4.0).

The ~1 m source is aggregated per ~5 m cell by majority rule, which keeps canopy edges crisp and
heights honest (a plain average would halve the height of a half-covered cell):
  * cover  = share of the cell's source pixels with canopy >= 2 m
  * height = mean height of those canopy pixels if cover >= 50 %, else 0 (no canopy)
Aggregation runs in the source grid (6x6 pixels of 1.194 m Web Mercator = ~5.0 m on the ground
at 45.7 N), then the result is placed on the 5 m Stereo 70 grid by nearest neighbour.

Output: raster/canopy_height_5m.vrt -> four COG quadrants canopy_height_5m_{nw,ne,sw,se}.tif
(split so each file stays far below GitHub's 100 MB limit). Values are metres, 255 = outside AOI.
"""
import json
import urllib.request
from concurrent.futures import ProcessPoolExecutor

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.windows import Window, from_bounds

from common import CRS, RASTER, RAW, WORK, aoi_bounds_3844, aoi_path, run

BASE = "https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/alsgedi_global_v6_float"
RES = 5          # output cell (m)
AGG = 6          # source pixels per side aggregated into one ~5 m cell
CANOPY_M = 2     # minimum height counted as tree canopy
NODATA = 255

D = RAW / "chm"


def download() -> list:
    D.mkdir(parents=True, exist_ok=True)
    idx = D / "tiles.geojson"
    if not idx.exists():
        urllib.request.urlretrieve(f"{BASE}/tiles.geojson", idx)
    tiles = gpd.read_file(idx)
    aoi = gpd.read_file(aoi_path()).to_crs(tiles.crs).geometry.iloc[0]
    paths = []
    for key in tiles[tiles.intersects(aoi)].tile:
        dst = D / f"{key}.tif"
        if not dst.exists():
            urllib.request.urlretrieve(f"{BASE}/chm/{key}.tif", dst)
        paths.append(dst)
    return paths


def aggregate_tile(path):
    """Majority-rule 6x6 aggregation in the source grid (EPSG:3857, 1.194 m). At ~45.7 N a
    6-pixel block is ~5.0 m on the ground. Streams the strip-organised tile top to bottom."""
    out_path = WORK / "chm_agg" / path.name
    if out_path.exists():
        return out_path
    out_path.parent.mkdir(exist_ok=True)
    f = AGG
    with rasterio.open(path) as src:
        ow, oh = src.width // f, src.height // f
        out = np.zeros((oh, ow), "uint8")
        band = 512 * f
        for r0 in range(0, oh * f, band):
            nrows = min(band, oh * f - r0)
            h = src.read(1, window=Window(0, r0, ow * f, nrows))
            h = h.reshape(nrows // f, f, ow, f)
            canopy = h >= CANOPY_M
            n = canopy.sum(axis=(1, 3), dtype="uint16")
            tot = (h * canopy).sum(axis=(1, 3), dtype="uint32")
            mean_h = np.where(n > 0, tot / np.maximum(n, 1), 0)
            blk = np.where(n * 2 >= f * f, np.clip(np.rint(mean_h), 1, 254), 0)
            out[r0 // f:(r0 + nrows) // f] = blk.astype("uint8")
        prof = dict(driver="GTiff", width=ow, height=oh, count=1, dtype="uint8", crs=src.crs,
                    transform=src.transform * src.transform.scale(f), tiled=True,
                    compress="zstd")
    with rasterio.open(out_path, "w", **prof) as dst:
        dst.write(out, 1)
    return out_path


def main() -> None:
    tiles = download()
    with ProcessPoolExecutor(4) as ex:
        agg = list(ex.map(aggregate_tile, tiles))
    agg_vrt = WORK / "chm_agg.vrt"
    run(["gdalbuildvrt", "-overwrite", agg_vrt, *agg])

    minx, miny, maxx, maxy = aoi_bounds_3844()
    full = WORK / "canopy_5m_full.tif"
    # nearest: values are already 5 m aggregates; 255 marks cells outside the county + 1 km
    run(["gdalwarp", "-overwrite", "-t_srs", CRS, "-tr", RES, RES, "-te", minx, miny, maxx, maxy,
         "-r", "near", "-cutline", aoi_path(), "-dstnodata", NODATA, "-multi",
         "-wo", "NUM_THREADS=ALL_CPUS", "-co", "COMPRESS=ZSTD", "-co", "TILED=YES",
         "-co", "BIGTIFF=YES", agg_vrt, full])
    with rasterio.open(full) as src:
        width, height = src.width, src.height

    # Four quadrant COGs + a VRT that QGIS opens as one layer.
    half_w, half_h = width // 2, height // 2
    quads = {"nw": (0, 0, half_w, half_h), "ne": (half_w, 0, width - half_w, half_h),
             "sw": (0, half_h, half_w, height - half_h),
             "se": (half_w, half_h, width - half_w, height - half_h)}
    parts = []
    for name, (xo, yo, xs, ys) in quads.items():
        p = RASTER / f"canopy_height_5m_{name}.tif"
        run(["gdal_translate", "-q", "-srcwin", xo, yo, xs, ys, "-of", "COG",
             "-co", "COMPRESS=ZSTD", "-co", "PREDICTOR=2", "-co", "LEVEL=19",
             "-co", "BLOCKSIZE=512", "-co", "OVERVIEWS=AUTO", "-co", "RESAMPLING=AVERAGE",
             full, p])
        parts.append(p.name)
    run(["gdalbuildvrt", "-overwrite", RASTER / "canopy_height_5m.vrt", *parts],
        cwd=RASTER)

    # Acquisition dates of the source imagery over the county (for the documentation).
    with rasterio.open(f"/vsicurl/{BASE}/CHM_acquisition_date.tif") as src:
        b = gpd.read_file(aoi_path()).to_crs(src.crs).total_bounds
        win = from_bounds(*b, transform=src.transform).round_offsets()
        d = src.read(1, window=win.round_lengths())
        d = d[np.isfinite(d) & (d > 0)]
    info = {"min": float(d.min()), "max": float(d.max()), "median": float(np.median(d))}
    (WORK / "canopy_dates.json").write_text(json.dumps(info))
    print("source acquisition dates:", info)


if __name__ == "__main__":
    main()
