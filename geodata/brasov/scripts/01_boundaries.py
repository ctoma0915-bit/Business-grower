"""Administrative boundaries: Brașov County, its 58 UATs (communes/towns), neighbours, AOI.

Source: geoBoundaries gbOpen ROU ADM1 (World Bank) and ADM2 (ANCPI cadastre), CC BY 4.0.
The county outline is the dissolve of the official ANCPI UAT polygons.
"""
import urllib.request

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from common import AOI_BUFFER_M, CRS, HYDRO_BBOX_WGS84, RAW, WORK, aoi_path, stage_gpkg

GB = "https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/main/releaseData/gbOpen/ROU"

# Official names (with diacritics) and UAT rank for the 58 administrative units of Brașov County.
UAT_NAMES = {
    "APATA": "Apața", "AUGUSTIN": "Augustin", "BECLEAN": "Beclean", "BOD": "Bod", "BRAN": "Bran",
    "BRASOV": "Brașov", "BUDILA": "Budila", "BUNESTI": "Bunești", "CATA": "Cața", "CINCU": "Cincu",
    "CODLEA": "Codlea", "COMANA": "Comana", "CRISTIAN": "Cristian", "CRIZBAV": "Crizbav",
    "DRAGUS": "Drăguș", "DUMBRAVITA": "Dumbrăvița", "FAGARAS": "Făgăraș", "FELDIOARA": "Feldioara",
    "FUNDATA": "Fundata", "GHIMBAV": "Ghimbav", "HALCHIU": "Hălchiu", "HARMAN": "Hărman",
    "HARSENI": "Hârseni", "HOGHIZ": "Hoghiz", "HOLBAV": "Holbav", "HOMOROD": "Homorod",
    "JIBERT": "Jibert", "LISA": "Lisa", "MAIERUS": "Măieruș", "MANDRA": "Mândra", "MOIECIU": "Moieciu",
    "ORMENIS": "Ormeniș", "PARAU": "Părău", "POIANA MARULUI": "Poiana Mărului", "PREDEAL": "Predeal",
    "PREJMER": "Prejmer", "RACOS": "Racoș", "RASNOV": "Râșnov", "RECEA": "Recea", "RUPEA": "Rupea",
    "SACELE": "Săcele", "SAMBATA DE SUS": "Sâmbăta de Sus", "SANPETRU": "Sânpetru",
    "SERCAIA": "Șercaia", "SINCA": "Șinca", "SINCA NOUA": "Șinca Nouă", "SOARS": "Șoarș",
    "TARLUNGENI": "Tărlungeni", "TELIU": "Teliu", "TICUSU": "Ticuș", "UCEA": "Ucea", "UNGRA": "Ungra",
    "VAMA BUZAULUI": "Vama Buzăului", "VICTORIA": "Victoria", "VISTEA": "Viștea", "VOILA": "Voila",
    "VULCAN": "Vulcan", "ZARNESTI": "Zărnești",
}
COUNTY_NAMES = {"ARGES": "Argeș", "BRASOV": "Brașov", "BUZAU": "Buzău", "COVASNA": "Covasna",
                "DAMBOVITA": "Dâmbovița", "HARGHITA": "Harghita", "MURES": "Mureș",
                "PRAHOVA": "Prahova", "SIBIU": "Sibiu"}
MUNICIPII = {"BRASOV", "CODLEA", "FAGARAS", "SACELE"}
ORASE = {"GHIMBAV", "PREDEAL", "RASNOV", "RUPEA", "VICTORIA", "ZARNESTI"}


STAGE = stage_gpkg("boundaries")


def fetch(level: str) -> gpd.GeoDataFrame:
    dst = RAW / f"gb_ROU_{level}.geojson"
    if not dst.exists():
        urllib.request.urlretrieve(f"{GB}/{level}/geoBoundaries-ROU-{level}.geojson", dst)
    return gpd.read_file(dst)


def main() -> None:
    adm1 = fetch("ADM1").to_crs(CRS)
    adm2 = fetch("ADM2").to_crs(CRS)

    county_gb = adm1[adm1.shapeISO == "RO-BV"]
    pts = adm2.copy()
    pts["geometry"] = adm2.representative_point()
    inside = gpd.sjoin(pts, county_gb[["geometry"]], predicate="within").index
    uat = adm2.loc[inside].dissolve(by="shapeName", as_index=False)
    assert len(uat) == 58, f"expected 58 UATs, got {len(uat)}"

    uat["name"] = uat.shapeName.map(UAT_NAMES)
    uat["rank"] = uat.shapeName.map(
        lambda n: "municipiu" if n in MUNICIPII else "oraș" if n in ORASE else "comună")
    uat["area_km2"] = (uat.area / 1e6).round(3)
    uat = uat[["name", "rank", "area_km2", "shapeID", "geometry"]].rename(columns={"shapeID": "gb_id"})
    uat = uat.sort_values("name").reset_index(drop=True)

    county = gpd.GeoDataFrame(
        {"name": ["Județul Brașov"], "iso": ["RO-BV"], "n_uat": [58],
         "area_km2": [round(uat.area_km2.sum(), 2)]},
        geometry=[uat.union_all().buffer(0)], crs=CRS)

    neighbours = adm1[adm1.intersects(county.geometry.iloc[0].buffer(5000))]
    neighbours = neighbours[["shapeName", "shapeISO", "geometry"]].rename(
        columns={"shapeName": "name", "shapeISO": "iso"})
    neighbours["name"] = neighbours["name"].map(COUNTY_NAMES).fillna(neighbours["name"])

    aoi = county.copy()
    aoi["geometry"] = county.buffer(AOI_BUFFER_M)
    aoi[["geometry"]].to_file(aoi_path(), layer="aoi")

    hydro = gpd.GeoDataFrame(geometry=[box(*HYDRO_BBOX_WGS84)], crs="EPSG:4326").to_crs(CRS)
    hydro.to_file(WORK / "hydro_extent.gpkg", layer="hydro_extent")

    county.to_file(STAGE, layer="admin_county", driver="GPKG")
    uat.to_file(STAGE, layer="admin_uat", driver="GPKG")
    neighbours.to_file(STAGE, layer="admin_counties_context", driver="GPKG")
    print(county[["name", "area_km2"]].to_string(index=False))
    print(pd.Series(uat["rank"]).value_counts().to_string())


if __name__ == "__main__":
    main()
