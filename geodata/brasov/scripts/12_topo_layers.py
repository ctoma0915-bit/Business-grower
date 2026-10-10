"""Extra layers for the topographic map series and the 3D sections.

  topo_sheet_index_50k   20 x 15 km sheets (1:50,000 on A2) on a round Stereo 70 km grid;
                         also the footprint of each 3D section. Named after the main locality.
  topo_streams_unmapped  DEM-derived channels with no mapped (OSM) waterway within 30 m - the
                         rest of the drainage network, drawn dashed on the topographic map
  topo_spot_heights      DEM summits (highest cell within ~1 km, >= 40 m local relief) that
                         are not already a named peak, with elevation
  topo_peaks_labelled    named peaks / saddles with an elevation label (OSM `ele` tag, or the
                         DEM value where OSM has none)
"""
import math

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage as ndi
from shapely.geometry import box

from common import CRS, RASTER, stage_gpkg

SHEET_W, SHEET_H = 20000, 15000      # metres; 400 x 300 mm at 1:50,000
GRID_X0, GRID_Y1 = 470000, 525000    # sheet grid origin (west edge, north edge)
OUT = stage_gpkg("topo")
RANK = {"city": 0, "town": 1, "village": 2, "hamlet": 3}


def sheet_index() -> gpd.GeoDataFrame:
    county = gpd.read_file(stage_gpkg("boundaries"), layer="admin_county").geometry.iloc[0]
    sett = gpd.read_file(stage_gpkg("overture"), layer="settlements")
    sett = sett[sett["class"].isin(RANK)].copy()
    sett["rank"] = sett["class"].map(RANK)
    # size proxy: buildings within 1 km of the settlement point
    bld = gpd.read_file(stage_gpkg("overture"), layer="buildings", columns=[])
    bpts = gpd.GeoDataFrame(geometry=bld.representative_point(), crs=CRS)
    ring = gpd.GeoDataFrame({"sid": sett.index}, geometry=sett.buffer(1000), crs=CRS)
    sett["n_bld"] = sett.index.map(gpd.sjoin(bpts, ring, predicate="within").groupby("sid").size()
                                   ).fillna(0)
    # commune/town seats share the UAT's name; prefer them as the sheet's main locality
    uat = gpd.read_file(stage_gpkg("boundaries"), layer="admin_uat")
    sett["seat"] = sett["name"].isin(set(uat["name"]))
    # seats ranked by their whole UAT's building count
    nb = gpd.sjoin(bpts, uat[["name", "geometry"]], predicate="within").groupby("name").size()
    sett.loc[sett.seat, "n_bld"] = sett.loc[sett.seat, "name"].map(nb).fillna(
        sett.loc[sett.seat, "n_bld"])
    sett = sett[~sett["name"].str.contains("vacanță|vacanta", case=False, na=False)]
    peaks = gpd.read_file(stage_gpkg("overture"), layer="topo_peaks")
    peaks = peaks[(peaks["class"] == "peak") & peaks["name"].notna()]
    minx, miny, maxx, maxy = county.bounds
    ncols = math.ceil((maxx - GRID_X0) / SHEET_W)
    nrows = math.ceil((GRID_Y1 - miny) / SHEET_H)
    rows = []
    for r in range(nrows):
        for c in range(ncols):
            x0, y1 = GRID_X0 + c * SHEET_W, GRID_Y1 - r * SHEET_H
            g = box(x0, y1 - SHEET_H, x0 + SHEET_W, y1)
            inside = g.intersection(county)
            if inside.area < 0.005 * g.area:     # skip sheets with a sliver of county only
                continue
            s_in = sett[sett.within(g) & sett.within(county)]
            p_in = peaks[peaks.within(g) & peaks.within(county)]
            if len(s_in):
                name = s_in.sort_values(["rank", "seat", "n_bld"],
                                        ascending=[True, False, False]).iloc[0]["name"]
            elif len(p_in):   # mountain sheet: name it after its highest named peak
                name = p_in.sort_values("elevation", ascending=False, na_position="last"
                                        ).iloc[0]["name"]
            else:
                name = "(mountain area)"
            rows.append({"sheet": f"BV50-{chr(65 + r)}{c + 1}", "row": chr(65 + r),
                         "col": c + 1, "name": name,
                         "county_share_pct": round(100 * inside.area / g.area, 1),
                         "xmin": x0, "ymin": y1 - SHEET_H, "xmax": x0 + SHEET_W, "ymax": y1,
                         "geometry": g})
    idx = gpd.GeoDataFrame(rows, crs=CRS)
    # neighbours for the margin diagram: sheet ids in the 8 directions ('' = none)
    ids = {(r["row"], r["col"]): r["sheet"] for r in rows}
    for dname, dr, dc in (("n", -1, 0), ("s", 1, 0), ("w", 0, -1), ("e", 0, 1)):
        idx[f"adj_{dname}"] = [ids.get((chr(ord(r) + dr), c + dc), "") for r, c in
                               zip(idx["row"], idx["col"])]
    idx["page"] = range(1, len(idx) + 1)
    return idx


def unmapped_streams() -> gpd.GeoDataFrame:
    st = gpd.read_file(stage_gpkg("hydrology"), layer="hydro_streams")
    wl = gpd.read_file(stage_gpkg("overture"), layer="water_lines")
    wa = gpd.read_file(stage_gpkg("overture"), layer="water_areas")
    mapped = pd.concat([wl.geometry.buffer(30), wa.geometry.buffer(15)]).union_all()
    out = st.copy()
    out["geometry"] = out.geometry.difference(mapped)
    out = out[~out.is_empty].explode(index_parts=False)
    out = out[out.geom_type == "LineString"]
    out = out[out.length >= 150].copy()          # drop slivers left between mapped reaches
    out["length_m"] = out.length.round(1)
    return out[["strahler", "upstream_km2", "length_m", "geometry"]].reset_index(drop=True)


def spot_heights(peaks: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    with rasterio.open(RASTER / "topo_dem_25m.tif") as src:
        z = src.read(1, masked=True).filled(np.nan).astype("float64")
        tr = src.transform
    zz = np.where(np.isnan(z), -1e9, z)
    win = 41                                       # ~1 km window on the 25 m grid
    is_max = (zz == ndi.maximum_filter(zz, size=win)) & ~np.isnan(z)
    zmin = ndi.minimum_filter(np.where(np.isnan(z), 1e9, z), size=win)
    relief = np.where(is_max, z - zmin, 0)
    rr, cc = np.nonzero(is_max & (relief >= 40))
    xs, ys = rasterio.transform.xy(tr, rr, cc)
    pts = gpd.GeoDataFrame({"elev_m": np.round(z[rr, cc]).astype(int),
                            "relief_m": np.round(relief[rr, cc]).astype(int)},
                           geometry=gpd.points_from_xy(xs, ys), crs=CRS)
    named = peaks[peaks["class"].isin(["peak", "saddle", "volcano", "hill"])]
    if len(named):
        near = gpd.sjoin_nearest(pts, named[["geometry"]], max_distance=400, how="left")
        pts = pts.loc[near[near["index_right"].isna()].index.unique()]
    pts["source"] = "DEM (Copernicus GLO-30, DSM)"
    return pts.reset_index(drop=True)


def labelled_peaks() -> gpd.GeoDataFrame:
    pk = gpd.read_file(stage_gpkg("overture"), layer="topo_peaks")
    with rasterio.open(RASTER / "topo_dem_25m.tif") as src:
        dem_z = np.array([v[0] for v in src.sample([(p.x, p.y) for p in pk.geometry])])
        nd = src.nodata
    pk["dem_elev_m"] = np.where(dem_z == nd, np.nan, np.round(dem_z))
    pk["elev_label"] = pk["elevation"].where(pk["elevation"].notna(), pk["dem_elev_m"])
    pk["elev_source"] = np.where(pk["elevation"].notna(), "OSM", "DEM")
    return pk


def main() -> None:
    OUT.unlink(missing_ok=True)
    idx = sheet_index()
    idx.to_file(OUT, layer="topo_sheet_index_50k", driver="GPKG")
    print(f"sheets: {len(idx)}")
    print(idx[["sheet", "name", "county_share_pct"]].to_string(index=False))
    us = unmapped_streams()
    us.to_file(OUT, layer="topo_streams_unmapped", driver="GPKG")
    print(f"unmapped stream pieces: {len(us)}, {us.length_m.sum() / 1000:.0f} km")
    pk = labelled_peaks()
    pk.to_file(OUT, layer="topo_peaks_labelled", driver="GPKG")
    sh = spot_heights(pk)
    sh.to_file(OUT, layer="topo_spot_heights", driver="GPKG")
    print(f"spot heights: {len(sh)}; peaks labelled: {pk.elev_label.notna().sum()}/{len(pk)}")


if __name__ == "__main__":
    main()
