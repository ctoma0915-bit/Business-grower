"""Surface-water history (JRC Global Surface Water 1984-2021) and land cover (ESA WorldCover 2021).

  water_gsw_occurrence.tif   % of valid observations with water, 1984-2021 (0 = never -> nodata)
  water_gsw_recurrence.tif   % of years in which water returned
  water_gsw_seasonality.tif  months with water in 2021 (1-12)
  water_gsw_transitions.tif  change class 1984 -> 2021 (permanent / seasonal / new / lost ...)
  landcover_worldcover_10m.tif  ESA WorldCover v200 (2021), 11 classes, 10 m
"""
import urllib.request

from common import COG_BYTE_CAT, RASTER, RAW, warp_to_aoi

GSW = ("https://storage.googleapis.com/global-surface-water/downloads2021/{layer}/"
       "{layer}_20E_50Nv1_4_2021.tif")
WC = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
      "ESA_WorldCover_10m_2021_v200_N45E024_Map.tif")


def main() -> None:
    for layer in ("occurrence", "recurrence", "seasonality", "transitions"):
        warp_to_aoi(f"/vsicurl/{GSW.format(layer=layer)}", RASTER / f"water_gsw_{layer}.tif",
                    resampling="near", cog=COG_BYTE_CAT, nodata=0,
                    extra=["-srcnodata", "0", "-ot", "Byte"])

    wc = RAW / "wc" / WC.rsplit("/", 1)[1]
    wc.parent.mkdir(exist_ok=True)
    if not wc.exists():
        urllib.request.urlretrieve(WC, wc)
    warp_to_aoi(wc, RASTER / "landcover_worldcover_10m.tif", res=10, resampling="near",
                cog=COG_BYTE_CAT, nodata=0)


if __name__ == "__main__":
    main()
