"""OPTIONAL: ISRIC SoilGrids 2.0 (250 m) soil property rasters, to complement the 1 km HWSD units.

Not part of the default run: files.isric.org was not reachable from the environment that built
this export, so these rasters are not in data/. Run it from any machine with normal internet:

    python 05b_soilgrids_optional.py

Writes raster/soil_sg_<property>_<depth>.tif (EPSG:3844, 250 m, masked to the AOI) and
raster/soil_sg_wrb_most_probable.tif. Values keep SoilGrids' integer "mapped units":
  clay/sand/silt g/kg (/10 -> %), soc dg/kg (/10 -> g/kg), phh2o pH*10, bdod cg/cm3 (/100 ->
  g/cm3), cfvo cm3/dm3 (/10 -> vol %), cec mmol(c)/kg, nitrogen cg/kg.
Licence: CC BY 4.0, ISRIC - World Soil Information.
"""
from common import COG_BYTE_CAT, COG_INT, RASTER, warp_to_aoi

BASE = "https://files.isric.org/soilgrids/latest/data"
PROPS = ["clay", "sand", "silt", "soc", "phh2o", "bdod", "cfvo", "cec", "nitrogen"]
DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm"]


def main() -> None:
    for prop in PROPS:
        for depth in DEPTHS:
            src = f"/vsicurl/{BASE}/{prop}/{prop}_{depth}_mean.vrt"
            warp_to_aoi(src, RASTER / f"soil_sg_{prop}_{depth.replace('-', '_')}.tif", res=250,
                        resampling="bilinear", cog=COG_INT, nodata=-32768,
                        extra=["-ot", "Int16"])
    warp_to_aoi(f"/vsicurl/{BASE}/wrb/MostProbable.vrt", RASTER / "soil_sg_wrb_most_probable.tif",
                res=250, resampling="near", cog=COG_BYTE_CAT, nodata=255, extra=["-ot", "Byte"])


if __name__ == "__main__":
    main()
