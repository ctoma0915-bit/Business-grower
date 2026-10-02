"""One-file QGIS package: every vector layer, every raster, the default styles and the styled
QGIS project (with the A3 layouts), all inside a single GeoPackage.

    brasov_county_qgis.gpkg
      ├─ 26 vector layers / tables  (same as the thematic GeoPackages, styles in layer_styles)
      ├─ 18 raster tables           (tiled, with overviews)
      └─ QGIS project "Brasov County"  (open it from the Browser panel, or drag the file in)

Raster encoding (GeoPackage tiles):
  * categorical / integer rasters -> 16-bit PNG "gridded coverage", lossless
  * continuous float rasters      -> 16-bit PNG with per-tile scale/offset at an explicit
                                     precision (max error = precision / 2), see PRECISION
  * upstream area                 -> Float32 TIFF tiles, lossless (values span 7 orders)
  * Sentinel-2 imagery            -> RGBA, JPEG for full tiles / PNG for edge tiles
"""
import sqlite3
import subprocess
import sys

from catalog import RASTERS, VECTORS
from common import DATA, RASTER, ROOT, run

OUT = ROOT / "brasov_county_qgis.gpkg"

# Smallest significant value for lossy float rasters (units of the layer).
PRECISION = {
    "topo_dem_25m.tif": 0.1,             # m   (DEM accuracy is metres)
    "topo_slope_deg.tif": 0.05,          # degrees
    "topo_ruggedness_tri.tif": 0.05,     # m
    "hydro_hand_m.tif": 0.05,            # m
    "hydro_twi.tif": 0.01,               # index
}
LOSSLESS_FLOAT = {"hydro_upstream_area_km2.tif"}
RGBA = {"imagery_sentinel2_truecolor_10m.tif"}
CATEGORICAL = {"topo_slope_classes.tif", "topo_landforms_geomorphons.tif",
               "hydro_flood_susceptibility.tif", "hydro_flow_dir_d8.tif",
               "water_gsw_transitions.tif", "landcover_worldcover_10m.tif"}


def descriptions() -> dict:
    """Layer descriptions/identifiers as written by 09_package.py into gpkg_contents."""
    out = {}
    for stem in {v[0] for v in VECTORS}:
        with sqlite3.connect(DATA / f"{stem}.gpkg") as con:
            for name, ident, desc in con.execute(
                    "SELECT table_name, identifier, description FROM gpkg_contents"):
                out[name] = (stem, ident, desc)
    return out


def main() -> None:
    OUT.unlink(missing_ok=True)

    # ---- vectors --------------------------------------------------------------------
    desc = descriptions()
    for stem, layer, *_ in VECTORS:
        _, ident, d = desc[layer]
        run(["ogr2ogr", "-f", "GPKG", *(["-update"] if OUT.exists() else []), OUT,
             DATA / f"{stem}.gpkg", layer, "-nln", layer,
             "-lco", f"IDENTIFIER={ident}", "-lco", f"DESCRIPTION={d}"])

    # ---- rasters --------------------------------------------------------------------
    for fname, group, title, d, src in RASTERS:
        table = fname.rsplit(".", 1)[0]
        co = ["-co", "APPEND_SUBDATASET=YES", "-co", f"RASTER_TABLE={table}",
              "-co", f"RASTER_IDENTIFIER={title}", "-co", f"RASTER_DESCRIPTION={d}"]
        if fname in RGBA:
            opts = ["-b", 1, "-b", 2, "-b", 3, "-b", "mask", "-colorinterp_4", "alpha",
                    "-co", "TILE_FORMAT=AUTO", "-co", "QUALITY=88"]
            resampling = "average"
        elif fname in LOSSLESS_FLOAT:
            opts = ["-co", "TILE_FORMAT=TIFF"]
            resampling = "nearest"
        elif fname in PRECISION:
            opts = ["-co", "TILE_FORMAT=PNG", "-co", f"PRECISION={PRECISION[fname]}"]
            resampling = "average"
        else:  # integer rasters (categorical, aspect, hillshade, surface-water %)
            dtype = "Int16" if fname == "topo_aspect_deg.tif" else "UInt16"
            opts = ["-ot", dtype, "-co", "TILE_FORMAT=PNG"]
            resampling = "nearest" if fname in CATEGORICAL else "average"
        run(["gdal_translate", "-q", "-of", "GPKG", *opts, *co, RASTER / fname, OUT])
        run(["gdaladdo", "-q", "-r", resampling, f"GPKG:{OUT}:{table}",
             2, 4, 8, 16, 32, 64])

    # ---- styled QGIS project, embedded in the GeoPackage ------------------------------
    subprocess.run([sys.executable, "10_qgis_project.py", "--single", str(OUT)], check=True)
    run(["ogrinfo", "-q", "-sql", "VACUUM", OUT])
    print(f"{OUT.name}: {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
