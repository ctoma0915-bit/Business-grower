"""Offline true-colour basemap: Sentinel-2 L2A (10 m) mosaic from a single cloud-free summer pass.

Scans the public `sentinel-cogs` bucket (Element 84 / AWS Open Data) for the MGRS tiles over the
county, picks the date with the lowest combined cloud cover where every tile is available,
and mosaics the TCI (true colour) COGs onto the 10 m EPSG:3844 AOI grid.
"""
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
from shapely.geometry import shape

from common import RASTER, WORK, aoi_path, run, warp_to_aoi

BUCKET = "https://sentinel-cogs.s3.us-west-2.amazonaws.com"
PREFIX = "sentinel-s2-l2a-cogs/35/T"
SQUARES = ["KL", "KM", "LL", "LM", "LK", "ML", "MM", "MK", "NL", "NM"]
MONTHS = [(2025, m) for m in (7, 8, 9, 6)] + [(2024, m) for m in (7, 8, 9, 6)]
MAX_CLOUD = 3.0  # % per tile


def ls(prefix: str) -> list[str]:
    url = f"{BUCKET}/?list-type=2&prefix={prefix}&delimiter=/"
    return re.findall(r"<Prefix>([^<]+)</Prefix>", urllib.request.urlopen(url).read().decode())[1:]


def item(prefix: str) -> dict:
    sid = prefix.rstrip("/").rsplit("/", 1)[1]
    return json.loads(urllib.request.urlopen(f"{BUCKET}/{prefix}{sid}.json").read())


def main() -> None:
    aoi = gpd.read_file(aoi_path()).to_crs(4326).geometry.iloc[0]

    # Which MGRS squares touch the county?
    needed = []
    for sq in SQUARES:
        months = ls(f"{PREFIX}/{sq}/2025/8/")
        if not months:
            continue
        geom = shape(item(months[0])["geometry"])
        if geom.intersects(aoi) and geom.intersection(aoi).area > 0.002 * aoi.area:
            needed.append(sq)
    print("MGRS tiles:", needed)

    cache = WORK / "s2_items.json"
    cands = json.loads(cache.read_text()) if cache.exists() else {}
    for year, month in MONTHS:
        key = f"{year}-{month}"
        if key not in cands:
            prefixes = [p for sq in needed for p in ls(f"{PREFIX}/{sq}/{year}/{month}/")]
            with ThreadPoolExecutor(16) as ex:
                items = list(ex.map(item, prefixes))
            cands[key] = [{"id": i["id"], "date": i["properties"]["datetime"][:10],
                           "tile": i["id"].split("_")[1][2:],
                           "cloud": i["properties"].get("eo:cloud_cover", 100),
                           "nodata": i["properties"].get("s2:nodata_pixel_percentage", 100),
                           "tci": i["assets"]["visual"]["href"],
                           "geometry": i["geometry"]} for i in items]
            cache.write_text(json.dumps(cands))

        # group by acquisition date; need every tile with low cloud and real coverage of the AOI
        by_date: dict[str, list] = {}
        for c in cands[key]:
            by_date.setdefault(c["date"], []).append(c)
        best = None
        for date, cs in sorted(by_date.items()):
            good = [c for c in cs if c["cloud"] <= MAX_CLOUD]
            cover = shape({"type": "GeometryCollection",
                           "geometries": [c["geometry"] for c in good]}) if good else None
            if not good or cover.buffer(0).intersection(aoi).area < 0.995 * aoi.area:
                continue
            score = sum(c["cloud"] for c in good) / len(good)
            if best is None or score < best[0]:
                best = (score, date, good)
        if best:
            break
    if not best:
        raise SystemExit("no single cloud-free pass found; relax MAX_CLOUD or add months")

    score, date, good = best
    # paint the most complete tiles last so they win in overlaps
    good.sort(key=lambda c: -c["nodata"])
    print(f"Using {date}, mean cloud {score:.2f}%:", [c["id"] for c in good])
    vrt = WORK / "s2_tci.vrt"
    srcs = [f"/vsicurl/{c['tci'].replace('s3://sentinel-cogs', BUCKET)}" for c in good]
    run(["gdalbuildvrt", "-overwrite", "-srcnodata", "0", vrt, *srcs])
    warp_to_aoi(vrt, RASTER / "imagery_sentinel2_truecolor_10m.tif", res=10,
                resampling="cubic", nodata=None,
                cog=["-of", "COG", "-co", "COMPRESS=JPEG", "-co", "QUALITY=88",
                     "-co", "BLOCKSIZE=512", "-co", "OVERVIEWS=AUTO", "-co", "BIGTIFF=IF_SAFER"],
                # alpha -> internal mask in the JPEG COG, so edges stay crisp-transparent
                extra=["-wo", "UNIFIED_SRC_NODATA=YES", "-dstalpha"])
    (WORK / "s2_used.json").write_text(json.dumps({"date": date, "items": [c["id"] for c in good],
                                                   "mean_cloud_pct": score}))


if __name__ == "__main__":
    main()
