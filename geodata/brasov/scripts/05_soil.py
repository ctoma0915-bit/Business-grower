"""Soil from the FAO/IIASA Harmonized World Soil Database v2.0 (HWSD v2, 30 arc-second ≈ 1 km).

In Romania HWSD v2 is built from the European Soil Database (ESDB) — the same source used for
EU soil maps. Each soil mapping unit (SMU) is a mix of soil components; full component x depth
data (7 layers, 0-200 cm) is kept in the `soil_hwsd_layers` table, and the polygons carry the
dominant component's properties plus a planning-oriented hydrologic soil group.

Outputs (stage gpkg "soil"):
  soil_hwsd_units      polygons, one per SMU patch (dominant soil + topsoil/subsoil properties)
  soil_hwsd_components table, every soil component of every SMU in the county
  soil_hwsd_layers     table, every component x depth layer (D1..D7) with all lab properties
"""
import io
import subprocess
import urllib.request
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import rasterio
import shapely
from rasterio.features import shapes
from rasterio.windows import from_bounds

from common import COUNTY_BBOX_WGS84, CRS, RAW, aoi_path, stage_gpkg

HWSD = "https://s3.eu-west-1.amazonaws.com/data.gaezdev.aws.fao.org/HWSD"
D = RAW / "hwsd"

# USDA texture -> NRCS hydrologic soil group (NEH 630 ch.7, texture-based approximation)
HSG_BY_TEXTURE = {"Sand": "A", "Loamy sand": "A", "Sandy loam": "A", "Silt loam": "B",
                  "Loam": "B", "Silt": "B", "Sandy clay loam": "C", "Clay loam": "D",
                  "Silty clay loam": "D", "Sandy clay": "D", "Silty clay": "D",
                  "Clay (light)": "D", "Clay (heavy)": "D"}


def ensure_downloads() -> None:
    D.mkdir(parents=True, exist_ok=True)
    for z, member in (("HWSD2_RASTER.zip", "HWSD2.bil"), ("HWSD2_DB.zip", "HWSD2.mdb")):
        if not (D / member).exists():
            data = urllib.request.urlopen(f"{HWSD}/{z}").read()
            zipfile.ZipFile(io.BytesIO(data)).extractall(D)


def mdb(table: str) -> pd.DataFrame:
    out = subprocess.run(["mdb-export", str(D / "HWSD2.mdb"), table], check=True,
                         capture_output=True, text=True).stdout
    return pd.read_csv(io.StringIO(out), low_memory=False)


def lookup(table: str, key: str = "CODE", val: str = "VALUE") -> dict:
    df = mdb(table)
    df[val] = df[val].astype(str).str.strip()
    return df.drop_duplicates(key).set_index(key)[val].to_dict()


def main() -> None:
    ensure_downloads()
    aoi = gpd.read_file(aoi_path()).geometry.iloc[0]

    with rasterio.open(D / "HWSD2.bil") as src:
        win = from_bounds(*COUNTY_BBOX_WGS84, transform=src.transform).round_offsets().round_lengths()
        arr = src.read(1, window=win)
        tr = src.window_transform(win)
        nd = src.nodata
    polys = [(shapely.geometry.shape(g), int(v))
             for g, v in shapes(arr.astype("int32"), mask=arr != nd, transform=tr)]
    smu = gpd.GeoDataFrame({"smu_id": [v for _, v in polys]},
                           geometry=[g for g, _ in polys], crs="EPSG:4326").to_crs(CRS)
    smu = smu[smu.intersects(aoi)].copy()
    smu["geometry"] = smu.geometry.intersection(aoi)
    smu = smu.dissolve(by="smu_id", as_index=False)
    ids = sorted(smu.smu_id.unique())
    print("SMUs in AOI:", ids)

    wrb4 = lookup("D_WRB4")
    wrb2 = lookup("D_WRB2", val="Value")
    tex = lookup("D_TEXTURE_USDA")
    drain = lookup("D_DRAINAGE")
    rootd = lookup("D_ROOT_DEPTH")
    phase = lookup("D_PHASE")
    swr = lookup("D_SWR")

    layers = mdb("HWSD2_LAYERS")
    layers = layers[layers.HWSD2_SMU_ID.isin(ids)].copy()
    layers["WRB4_NAME"] = layers.WRB4.map(wrb4)
    layers["WRB2_NAME"] = layers.WRB2.map(wrb2)
    layers["TEXTURE_USDA_NAME"] = layers.TEXTURE_USDA.map(tex)
    layers["DRAINAGE_NAME"] = layers.DRAINAGE.map(drain)
    layers["ROOT_DEPTH_NAME"] = layers.ROOT_DEPTH.map(rootd)
    layers["PHASE1_NAME"] = layers.PHASE1.map(phase)
    layers["SWR_NAME"] = layers.SWR.map(swr)
    layers["ORG_CARBON"] = pd.to_numeric(layers.ORG_CARBON, errors="coerce")
    # HWSD uses -9 for "no data" (e.g. Technosols / urban units).
    for c in layers.select_dtypes("number").columns:
        layers[c] = layers[c].where(layers[c] != -9)
    for c in layers.columns:
        if layers[c].dtype == object:
            layers[c] = layers[c].where(layers[c].notna(), None)
    layers = layers.sort_values(["HWSD2_SMU_ID", "SEQUENCE", "TOPDEP"])

    comps = (layers.drop_duplicates(["HWSD2_SMU_ID", "SEQUENCE"])
             [["HWSD2_SMU_ID", "SEQUENCE", "SHARE", "WRB4", "WRB4_NAME", "WRB2_NAME", "FAO90",
               "ROOT_DEPTH_NAME", "DRAINAGE_NAME", "AWC", "PHASE1_NAME", "SWR_NAME"]])
    comp_txt = comps.groupby("HWSD2_SMU_ID").apply(
        lambda g: "; ".join(f"{r.WRB4_NAME} {r.SHARE:.0f}%" for r in g.itertuples()),
        include_groups=False)

    dom = layers[layers.SEQUENCE == 1]
    top = dom[dom.LAYER == "D1"].set_index("HWSD2_SMU_ID")
    # Subsoil: thickness-weighted mean of D2..D5 (20-100 cm).
    sub = dom[dom.LAYER.isin(["D2", "D3", "D4", "D5"])].copy()
    sub["w"] = sub.BOTDEP - sub.TOPDEP
    num = ["COARSE", "SAND", "SILT", "CLAY", "BULK", "ORG_CARBON", "PH_WATER", "TOTAL_N",
           "CEC_SOIL", "BSAT", "TCARBON_EQ"]
    for c in num:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")
    subw = sub.groupby("HWSD2_SMU_ID").apply(
        lambda g: pd.Series({c: np.average(g[c], weights=g.w) if g[c].notna().all() else np.nan
                             for c in num}), include_groups=False)

    out = smu.set_index("smu_id")
    out["dominant_wrb_code"] = top.WRB4
    out["dominant_wrb"] = top.WRB4_NAME
    out["dominant_wrb_group"] = top.WRB2_NAME
    out["dominant_fao90"] = top.FAO90
    out["dominant_share_pct"] = top.SHARE
    out["components"] = comp_txt
    out["drainage"] = top.DRAINAGE_NAME
    out["rootable_depth"] = top.ROOT_DEPTH_NAME
    out["awc_mm"] = top.AWC
    out["phase"] = top.PHASE1_NAME
    out["water_regime"] = top.SWR_NAME
    out["top_texture_usda"] = top.TEXTURE_USDA_NAME
    for c, n in [("SAND", "sand_pct"), ("SILT", "silt_pct"), ("CLAY", "clay_pct"),
                 ("COARSE", "coarse_vol_pct"), ("BULK", "bulk_density_gcm3"),
                 ("ORG_CARBON", "org_carbon_pct"), ("PH_WATER", "ph_h2o"),
                 ("TOTAL_N", "total_n_gkg"), ("CEC_SOIL", "cec_cmolkg"),
                 ("BSAT", "base_sat_pct"), ("TCARBON_EQ", "caco3_pct")]:
        out[f"top_{n}"] = pd.to_numeric(top[c], errors="coerce")
        out[f"sub_{n}"] = subw[c].round(2)

    hsg = out.top_texture_usda.map(HSG_BY_TEXTURE)
    hsg = hsg.where(~out.drainage.isin(["Poorly drained", "Very poorly drained"]), "D")
    hsg = hsg.where(~out.rootable_depth.fillna("").str.contains("Shallow|shallow"), "D")
    out["hydrologic_soil_group"] = hsg
    out = out.reset_index()
    out["area_km2"] = (out.area / 1e6).round(3)
    # Non-soil units (water, rock, urban) have no layer data.
    print(out[["smu_id", "dominant_wrb", "top_texture_usda", "hydrologic_soil_group",
               "area_km2"]].to_string())

    dst = stage_gpkg("soil")
    out.to_file(dst, layer="soil_hwsd_units", driver="GPKG")
    pyogrio.write_dataframe(comps.rename(columns=str.lower), dst, layer="soil_hwsd_components",
                            driver="GPKG")
    pyogrio.write_dataframe(layers.rename(columns=str.lower), dst, layer="soil_hwsd_layers",
                            driver="GPKG")


if __name__ == "__main__":
    main()
