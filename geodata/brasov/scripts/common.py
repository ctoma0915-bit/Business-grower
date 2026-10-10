"""Shared paths, constants and helpers for the Brașov County geodata pipeline."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = Path(os.environ.get("BRASOV_RAW", ROOT / "_raw"))     # downloaded source data (not committed)
WORK = Path(os.environ.get("BRASOV_WORK", ROOT / "_work"))  # intermediates (not committed)
DATA = ROOT / "data"
RASTER = DATA / "raster"
GPKG = DATA / "brasov_county.gpkg"

for p in (RAW, WORK, DATA, RASTER):
    p.mkdir(parents=True, exist_ok=True)

# Romanian national projected CRS (Stereo 70), used for every output.
CRS = "EPSG:3844"
# Terrain/hydrology grid resolution in metres (Copernicus GLO-30 is ~31 m N-S, ~22 m E-W here).
RES = 25

# Clip area = county boundary buffered by this many metres, so edge features keep context.
AOI_BUFFER_M = 1000

# Hydrology is computed on a wider window that contains the whole upstream Olt catchment
# (Harghita + Covasna), otherwise flow accumulation along the Olt would be truncated.
HYDRO_BBOX_WGS84 = (24.45, 45.25, 26.65, 46.98)  # minx, miny, maxx, maxy

# WGS84 bbox for downloads that only need the county (county bounds + ~3 km).
COUNTY_BBOX_WGS84 = (24.60, 45.35, 26.15, 46.22)

# Cloud Optimized GeoTIFF creation options.
COG_FLOAT = ["-of", "COG", "-co", "COMPRESS=ZSTD", "-co", "PREDICTOR=3", "-co", "LEVEL=15",
             "-co", "BLOCKSIZE=512", "-co", "OVERVIEWS=AUTO", "-co", "BIGTIFF=IF_SAFER"]
COG_INT = ["-of", "COG", "-co", "COMPRESS=ZSTD", "-co", "PREDICTOR=2", "-co", "LEVEL=15",
           "-co", "BLOCKSIZE=512", "-co", "OVERVIEWS=AUTO", "-co", "BIGTIFF=IF_SAFER"]
COG_BYTE_CAT = COG_INT + ["-co", "RESAMPLING=MODE"]


def run(cmd: list[str], **kw) -> None:
    """Run a command, echoing it, and fail loudly."""
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def stage_gpkg(step: str) -> Path:
    """Per-step GeoPackage; 09_package.py merges all of them into GPKG."""
    return WORK / f"stage_{step}.gpkg"


def aoi_path() -> Path:
    return WORK / "aoi.gpkg"


def aoi_bounds_3844() -> tuple[float, float, float, float]:
    """AOI bounds snapped outward to the RES grid."""
    import geopandas as gpd
    import math

    minx, miny, maxx, maxy = gpd.read_file(aoi_path()).total_bounds
    s = RES
    return (math.floor(minx / s) * s, math.floor(miny / s) * s,
            math.ceil(maxx / s) * s, math.ceil(maxy / s) * s)


def warp_to_aoi(src: Path | str, dst: Path, *, res: float = RES, resampling: str = "bilinear",
                cog: list[str] = COG_FLOAT, nodata: float | None = None,
                cutline: bool = True, extra: list[str] | None = None) -> Path:
    """Reproject a raster to EPSG:3844 on the AOI grid, masked to the AOI polygon, as a COG."""
    minx, miny, maxx, maxy = aoi_bounds_3844()
    tmp = dst.with_suffix(".tmp.tif")
    cmd = ["gdalwarp", "-overwrite", "-t_srs", CRS, "-tr", res, res,
           "-te", minx, miny, maxx, maxy, "-r", resampling, "-multi", "-wo", "NUM_THREADS=ALL_CPUS",
           "-co", "COMPRESS=ZSTD", "-co", "TILED=YES", "-co", "BIGTIFF=IF_SAFER"]
    if cutline:
        cmd += ["-cutline", aoi_path()]
    if nodata is not None:
        cmd += ["-dstnodata", nodata]
    cmd += (extra or []) + [src, tmp]
    run(cmd)
    run(["gdal_translate", *cog, tmp, dst])
    tmp.unlink()
    return dst
