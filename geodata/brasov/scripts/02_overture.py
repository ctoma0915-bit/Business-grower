"""Vector base map from Overture Maps (OpenStreetMap + other open sources), clipped to the AOI.

Reads GeoParquet straight from the public S3 bucket with bbox predicate push-down, so only the
row groups covering Brașov are downloaded.

Layers written to brasov_county.gpkg:
  transport_roads, transport_rail (cut where bridges / tunnels start and end),
  transport_structure_pieces (bridge / tunnel pieces before clipping, for 3D profiles), buildings, water_lines, water_areas, water_points,
  landuse, protected_areas, land_natural_areas, land_natural_lines, topo_peaks, infrastructure_points,
  infrastructure_lines, infrastructure_areas, settlements, places_poi
"""
import json
import os
import sys
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.fs as pafs
import shapely
import shapely.ops

from common import COUNTY_BBOX_WGS84, CRS, WORK, aoi_path, stage_gpkg

RELEASE = os.environ.get("OVERTURE_RELEASE", "2026-09-23.1")
BASE = f"overturemaps-us-west-2/release/{RELEASE}"

fs = pafs.S3FileSystem(anonymous=True, region="us-west-2",
                       proxy_options=os.environ.get("HTTPS_PROXY") or None)
AOI = gpd.read_file(aoi_path()).geometry.iloc[0]
STAGE = stage_gpkg("overture")


def bbox_filter():
    xmin, ymin, xmax, ymax = COUNTY_BBOX_WGS84
    return ((pc.field("bbox", "xmin") <= xmax) & (pc.field("bbox", "xmax") >= xmin)
            & (pc.field("bbox", "ymin") <= ymax) & (pc.field("bbox", "ymax") >= ymin))


def read(theme: str, typ: str, columns: dict) -> gpd.GeoDataFrame:
    """Read one Overture type for the county bbox, reproject to EPSG:3844 and clip to the AOI."""
    cache = WORK / f"overture_{theme}_{typ}.parquet"
    if cache.exists():
        gdf = gpd.read_parquet(cache)
    else:
        t0 = time.time()
        dataset = ds.dataset(f"{BASE}/theme={theme}/type={typ}", filesystem=fs, format="parquet")
        cols = {"id": pc.field("id"), **columns, "geometry": pc.field("geometry")}
        table = dataset.to_table(filter=bbox_filter(), columns=cols)
        df = table.to_pandas()
        geom = shapely.from_wkb(df.pop("geometry").to_numpy())
        gdf = gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326").to_crs(CRS)
        gdf = gdf[gdf.intersects(AOI)]
        gdf.to_parquet(cache)
        print(f"  {theme}/{typ}: {len(gdf)} features in {time.time() - t0:.0f}s", flush=True)
    return gdf


def first_value(rules) -> str | None:
    """Overture 'rules' lists ([{value, between}, ...]) -> first value."""
    if rules is None or len(rules) == 0:
        return None
    v = rules[0].get("value")
    return None if v is None else str(v)


def as_text(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (list, tuple, np.ndarray)):
        return ";".join(str(x) for x in v) if len(v) else None
    return str(v)


def clip(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Clip to AOI; keep only geometries that are still valid & non-empty after clipping."""
    if gdf.empty:
        return gdf
    out = gdf.copy()
    need = ~out.within(AOI)
    out.loc[need, "geometry"] = out.loc[need, "geometry"].intersection(AOI)
    out = out[~out.is_empty & out.geometry.notna()]
    return out


def split_geom(gdf, kind):
    gt = gdf.geom_type
    if kind == "point":
        return gdf[gt.isin(["Point", "MultiPoint"])]
    if kind == "line":
        return gdf[gt.isin(["LineString", "MultiLineString"])]
    return gdf[gt.isin(["Polygon", "MultiPolygon"])]


def promote(gdf: gpd.GeoDataFrame, kind: str) -> gpd.GeoDataFrame:
    """Make geometry types homogeneous (multi) so GIS clients get one geometry type per layer."""
    if gdf.empty:
        return gdf
    gdf = gdf.copy()
    if kind == "line":
        gdf["geometry"] = [g if g.geom_type == "MultiLineString" else shapely.MultiLineString([g])
                           for g in gdf.geometry]
    elif kind == "area":
        gdf["geometry"] = [g if g.geom_type == "MultiPolygon" else shapely.MultiPolygon([g])
                           for g in gdf.geometry]
    return gdf


def write(gdf: gpd.GeoDataFrame, layer: str, kind: str | None = None) -> None:
    if kind:
        gdf = promote(split_geom(gdf, kind), kind)
    gdf = gdf.reset_index(drop=True)
    gdf.to_file(STAGE, layer=layer, driver="GPKG", engine="pyogrio")
    print(f"  -> {layer}: {len(gdf)}", flush=True)


NAME = {"name": pc.field("names", "primary")}
RANGED = ("road_flags", "rail_flags", "level_rules")


def _covers(rule, t: float) -> bool:
    b = rule.get("between")
    return b is None or (b[0] <= t <= b[1])


def split_at_rules(seg: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Cut segments where a flag or level applies to only part of them ('between' = fractions
    of the segment length), so that a bridge or tunnel covers exactly its own piece. Each piece
    keeps the rules that hold at its midpoint, without the range."""
    rows, geoms = [], []
    for row, geom in zip(seg.drop(columns="geometry").to_dict("records"), seg.geometry):
        cuts = {0.0, 1.0}
        for col in RANGED:
            for rule in row[col] if row[col] is not None else []:
                if rule.get("between") is not None:
                    cuts.update(float(np.clip(v, 0, 1)) for v in rule["between"])
        cuts = sorted(cuts)
        if len(cuts) == 2:
            rows.append(row)
            geoms.append(geom)
            continue
        for a, b in zip(cuts[:-1], cuts[1:]):
            if b - a < 1e-6:
                continue
            piece = dict(row)
            mid = (a + b) / 2
            for col in RANGED:
                if row[col] is not None:
                    kept = [{**r, "between": None} for r in row[col] if _covers(r, mid)]
                    piece[col] = kept or None
            rows.append(piece)
            geoms.append(shapely.ops.substring(geom, a, b, normalized=True))
    out = gpd.GeoDataFrame(rows, geometry=geoms, crs=seg.crs)
    return out[out.geom_type.isin(["LineString", "MultiLineString"]) & (out.length > 0)]


def roads_and_rail():
    seg = read("transportation", "segment", {
        **NAME, "subtype": pc.field("subtype"), "class": pc.field("class"),
        "subclass": pc.field("subclass"), "road_surface": pc.field("road_surface"),
        "speed_limits": pc.field("speed_limits"), "routes": pc.field("routes"),
        "level_rules": pc.field("level_rules"), "rail_flags": pc.field("rail_flags"),
        "road_flags": pc.field("road_flags"), "width_rules": pc.field("width_rules"),
    })
    seg = split_at_rules(seg)

    def route_refs(r):
        if r is None or len(r) == 0:
            return None
        refs = sorted({x.get("ref") for x in r if x.get("ref")})
        return ";".join(refs) or None

    def max_speed(r):
        if r is None or len(r) == 0:
            return None
        ms = r[0].get("max_speed")
        return None if ms is None else ms.get("value")

    def flags(r):
        if r is None or len(r) == 0:
            return None
        vals = sorted({v for x in r if x.get("values") is not None for v in x["values"]})
        return ";".join(vals) or None

    out = pd.DataFrame({
        "overture_id": seg["id"], "name": seg["name"], "class": seg["class"],
        "subclass": seg["subclass"], "ref": seg["routes"].map(route_refs),
        "surface": seg["road_surface"].map(first_value),
        "max_speed_kmh": seg["speed_limits"].map(max_speed),
        "level": seg["level_rules"].map(first_value),
        "width_m": seg["width_rules"].map(first_value),
        "subtype": seg["subtype"],
        "road_flags": seg["road_flags"].map(flags), "rail_flags": seg["rail_flags"].map(flags),
    })
    out = gpd.GeoDataFrame(out, geometry=seg.geometry.values, crs=CRS)
    # bridge / tunnel pieces before clipping: 3D profiles need both real ends (a tunnel cut at
    # the county edge would otherwise get a "portal" inside the mountain)
    fl = out["road_flags"].fillna("") + out["rail_flags"].fillna("")
    write(out[fl.str.contains("is_bridge|is_tunnel")], "transport_structure_pieces", "line")
    out = clip(out)
    out["length_m"] = out.length.round(1)
    write(out[out.subtype == "road"].drop(columns=["subtype", "rail_flags"]), "transport_roads", "line")
    write(out[out.subtype == "rail"].drop(columns=["subtype", "road_flags", "surface",
                                                   "max_speed_kmh"]), "transport_rail", "line")


def buildings():
    b = read("buildings", "building", {
        **NAME, "subtype": pc.field("subtype"), "class": pc.field("class"),
        "height": pc.field("height"), "num_floors": pc.field("num_floors"),
        "roof_shape": pc.field("roof_shape"), "is_underground": pc.field("is_underground"),
        "sources": pc.field("sources"),
    })
    b = clip(b)
    b["source"] = b.pop("sources").map(
        lambda s: ";".join(sorted({x["dataset"] for x in s})) if s is not None and len(s) else None)
    b = b.rename(columns={"id": "overture_id"})
    b["footprint_m2"] = b.area.round(1)
    write(b, "buildings", "area")


def water():
    w = read("base", "water", {
        **NAME, "subtype": pc.field("subtype"), "class": pc.field("class"),
        "is_intermittent": pc.field("is_intermittent"), "is_salt": pc.field("is_salt"),
        "level": pc.field("level"), "wikidata": pc.field("wikidata"),
    })
    w = clip(w).rename(columns={"id": "overture_id"})
    lines = split_geom(w, "line").copy()
    lines["length_m"] = lines.length.round(1)
    areas = split_geom(w, "area").copy()
    areas["area_m2"] = areas.area.round(1)
    write(lines, "water_lines", "line")
    write(areas, "water_areas", "area")
    write(split_geom(w, "point"), "water_points", "point")


def land_and_landuse():
    lu = read("base", "land_use", {
        **NAME, "subtype": pc.field("subtype"), "class": pc.field("class"),
        "surface": pc.field("surface"), "elevation": pc.field("elevation"),
    })
    lu = clip(lu).rename(columns={"id": "overture_id"})
    lu_a = split_geom(lu, "area").copy()
    lu_a["area_m2"] = lu_a.area.round(1)
    write(lu_a[lu_a.subtype != "protected"], "landuse", "area")
    write(lu_a[lu_a.subtype == "protected"], "protected_areas", "area")

    ln = read("base", "land", {
        **NAME, "subtype": pc.field("subtype"), "class": pc.field("class"),
        "surface": pc.field("surface"), "elevation": pc.field("elevation"),
        "wikidata": pc.field("wikidata"),
    })
    ln = clip(ln).rename(columns={"id": "overture_id"})
    pts = split_geom(ln, "point")
    write(pts[pts["class"].isin(["peak", "saddle", "volcano", "hill", "cave_entrance", "cliff",
                                 "rock", "stone", "spring", "valley", "ridge", "mountain_range"])
              | pts["elevation"].notna()], "topo_peaks", "point")
    write(ln, "land_natural_lines", "line")
    areas = split_geom(ln, "area").copy()
    areas["area_m2"] = areas.area.round(1)
    write(areas, "land_natural_areas", "area")


def infrastructure():
    inf = read("base", "infrastructure", {
        **NAME, "subtype": pc.field("subtype"), "class": pc.field("class"),
        "height": pc.field("height"), "surface": pc.field("surface"),
    })
    inf = clip(inf).rename(columns={"id": "overture_id"})
    write(inf, "infrastructure_points", "point")
    write(inf, "infrastructure_lines", "line")
    write(inf, "infrastructure_areas", "area")


def settlements():
    d = read("divisions", "division", {
        **NAME, "subtype": pc.field("subtype"), "class": pc.field("class"),
        "population": pc.field("population"), "wikidata": pc.field("wikidata"),
        "country": pc.field("country"),
    })
    d = clip(d).rename(columns={"id": "overture_id"})
    d = d[d.subtype.isin(["locality", "localadmin", "neighborhood", "microhood", "macrohood"])]
    write(d.drop(columns=["country"]), "settlements", "point")


def places():
    p = read("places", "place", {
        **NAME, "category": pc.field("basic_category"),
        "taxonomy": pc.field("taxonomy", "primary"),
        "confidence": pc.field("confidence"), "addresses": pc.field("addresses"),
        "operating_status": pc.field("operating_status"),
    })
    p = clip(p).rename(columns={"id": "overture_id"})
    p["address"] = p.pop("addresses").map(
        lambda a: a[0].get("freeform") if a is not None and len(a) else None)
    p = p[p.confidence.fillna(0) >= 0.5]
    write(p, "places_poi", "point")


STEPS = {"roads": roads_and_rail, "buildings": buildings, "water": water,
         "land": land_and_landuse, "infrastructure": infrastructure,
         "settlements": settlements, "places": places}

if __name__ == "__main__":
    for name in (sys.argv[1:] or STEPS):
        print(f"[overture] {name}", flush=True)
        STEPS[name]()
    (WORK / "overture_release.json").write_text(json.dumps({"release": RELEASE}))
