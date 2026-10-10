"""3D topographic sections: one terrain block (GLB) per 1:50,000 sheet, plus a county overview.

For each sheet of topo_sheet_index_50k (same 20 x 15 km footprints as the 2D map series):
  maps/3d/sections/<sheet>.glb            terrain mesh (50 m grid, true scale, no exaggeration)
                                          draped with the topographic map (4096 x 3072 px,
                                          ~4.9 m/px), with side walls and a base like a relief
                                          model; areas outside the county in grey shaded relief
  maps/3d/sections/<sheet>_satellite.jpg  Sentinel-2 drape for the same footprint (viewer toggle)
  maps/3d/sections/BV-overview.glb        whole county, 200 m grid
  maps/3d/index.json                      catalogue used by the viewer (origin, bounds, heights)

glTF details: Y up, X = easting - west edge, Z = north edge - northing (north = -Z), metres.
Positions are int16 with KHR_mesh_quantization (Y stored in decimetres, node scale 0.1); the
node's `extras` carry the Stereo 70 (EPSG:3844) origin so coordinates can be recovered.
"""
import io
import json
import struct
import sys

import geopandas as gpd
import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.windows import from_bounds
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor
from qgis.core import (QgsApplication, QgsContrastEnhancement, QgsMapRendererParallelJob,
                       QgsMapSettings, QgsMultiBandColorRenderer, QgsProject, QgsRasterLayer,
                       QgsRectangle)

from common import DATA, RASTER, ROOT, WORK, aoi_path, run

OUT = ROOT / "maps" / "3d"
SEC = OUT / "sections"
SEC.mkdir(parents=True, exist_ok=True)
DEM = WORK / "dem_hydro.tif"           # unmasked DEM covering every sheet rectangle
STEP, OV_STEP = 50, 200                # mesh spacing (m): sheets / overview
TEX, SAT = (4096, 3072), (2048, 1536)  # texture sizes for a 20 x 15 km sheet
DPI = 220                              # label size in the texture (~1:42,000 equivalent)
BASE_BELOW = 150                       # block base: this many metres below the lowest point
Y_SCALE = 0.1                          # stored Y unit = decimetre
WALL_RGB = (0.56, 0.47, 0.38)
OUTSIDE_RGB = np.array([231, 228, 220], "float32")

app = QgsApplication([], False)
app.initQgis()


# ---------------------------------------------------------------- textures
def outside_relief() -> QgsRasterLayer:
    """RGBA raster: warm grey shaded relief outside the county AOI, transparent inside."""
    out = WORK / "outside_relief_rgba.tif"
    if not out.exists():
        hs = WORK / "hydro_hillshade_outside.tif"
        run(["gdaldem", "hillshade", "-multidirectional", "-z", "1.3", "-compute_edges", DEM, hs])
        with rasterio.open(hs) as src:
            h = src.read(1).astype("float32")
            prof = src.profile
            tr = src.transform
        aoi = gpd.read_file(aoi_path()).geometry.iloc[0]
        inside = rasterize([(aoi, 1)], out_shape=h.shape, transform=tr, dtype="uint8") == 1
        shade = 0.55 + 0.45 * (h / 255.0)
        rgb = (OUTSIDE_RGB[:, None, None] * shade[None]).clip(0, 255).astype("uint8")
        alpha = np.where(inside, 0, 255).astype("uint8")
        prof.update(count=4, dtype="uint8", nodata=None, compress="deflate", tiled=True,
                    blockxsize=256, blockysize=256,
                    photometric="RGB")
        with rasterio.open(out, "w", **prof) as dst:
            dst.write(np.concatenate([rgb, alpha[None]]))
            dst.colorinterp = [rasterio.enums.ColorInterp.red, rasterio.enums.ColorInterp.green,
                               rasterio.enums.ColorInterp.blue, rasterio.enums.ColorInterp.alpha]
    lyr = QgsRasterLayer(str(out), "outside relief")
    r = QgsMultiBandColorRenderer(lyr.dataProvider(), 1, 2, 3)
    r.setAlphaBand(4)
    lyr.setRenderer(r)
    return lyr


def render(layers, rect, size, dpi) -> bytes:
    ms = QgsMapSettings()
    ms.setLayers(layers)
    ms.setDestinationCrs(QgsProject.instance().crs())
    ms.setExtent(QgsRectangle(*rect))
    ms.setOutputSize(QSize(*size))
    ms.setOutputDpi(dpi)
    ms.setBackgroundColor(QColor("white"))
    job = QgsMapRendererParallelJob(ms)
    job.start()
    job.waitForFinished()
    img = job.renderedImage()
    buf = io.BytesIO()
    tmp = WORK / "_tex.png"
    img.save(str(tmp))
    Image.open(tmp).convert("RGB").save(buf, "JPEG", quality=80, optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------- mesh
def heights(rect, step):
    """Elevation (m) at mesh nodes spaced `step` m over rect (xmin, ymin, xmax, ymax)."""
    xmin, ymin, xmax, ymax = rect
    nx, ny = int(round((xmax - xmin) / step)) + 1, int(round((ymax - ymin) / step)) + 1
    with rasterio.open(DEM) as src:
        win = from_bounds(xmin - step / 2, ymin - step / 2, xmax + step / 2, ymax + step / 2,
                          src.transform)
        z = src.read(1, window=win, out_shape=(ny, nx), resampling=Resampling.average,
                     masked=True).filled(np.nan)
    if np.isnan(z).any():
        z = np.where(np.isnan(z), np.nanmin(z), z)
    return z.astype("float64")


def quant_normal(n, xy=1):
    """True unit normals -> int8, pre-compensated for the node scale S = (xy, Y_SCALE, xy):
    renderers transform normals by S^-1, so store S @ n (then normalise)."""
    m = n * np.array([xy, Y_SCALE, xy], "float64")
    m /= np.linalg.norm(m, axis=-1, keepdims=True)
    return np.round(m * 127).astype("int8")


def terrain_prims(z, step, xy=1):
    ny, nx = z.shape
    gz, gx = np.gradient(z, step)                 # rows = +Z (south), cols = +X (east)
    n = np.stack([-gx, np.ones_like(z), -gz], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    X = np.arange(nx) * step
    Z = np.arange(ny) * step
    prims = []
    rows_per = 65535 // nx - 1
    r0 = 0
    while r0 < ny - 1:
        r1 = min(r0 + rows_per, ny - 1)
        zz = z[r0:r1 + 1]
        rr, cc = np.meshgrid(np.arange(r0, r1 + 1), np.arange(nx), indexing="ij")
        pos = np.stack([X[cc] / xy, np.round(zz / Y_SCALE), Z[rr] / xy], axis=-1).reshape(-1, 3)
        uv = np.stack([cc / (nx - 1), rr / (ny - 1)], axis=-1).reshape(-1, 2)
        h, w = zz.shape
        i = np.arange((h - 1) * (w - 1))
        a = (i // (w - 1)) * w + (i % (w - 1))
        b, c, d = a + 1, a + w, a + w + 1             # a=NW b=NE c=SW d=SE
        idx = np.stack([a, c, b, b, c, d], axis=-1).reshape(-1)
        prims.append({"pos": pos.astype("int16"),
                      "nrm": quant_normal(n[r0:r1 + 1].reshape(-1, 3), xy),
                      "uv": np.round(uv * 65535).astype("uint16"),
                      "idx": idx.astype("uint16"), "material": 0})
        r0 = r1
    return prims


def wall_prim(z, step, base, xy=1):
    """Four side walls and a base plate (no texture)."""
    ny, nx = z.shape
    W, H = (nx - 1) * step, (ny - 1) * step
    pos, nrm, idx = [], [], []

    def strip(top_pts, normal, flip):
        k0 = sum(len(p) for p in pos)
        top = np.array(top_pts, "float64")
        bot = top.copy()
        bot[:, 1] = base
        v = np.empty((len(top) * 2, 3))
        v[0::2], v[1::2] = top, bot                   # top_i, bottom_i interleaved
        pos.append(v)
        nrm.append(np.repeat([normal], len(v), axis=0))
        for i in range(len(top) - 1):
            a, c, b, d = k0 + 2 * i, k0 + 2 * i + 1, k0 + 2 * i + 2, k0 + 2 * i + 3
            idx.extend([a, c, b, b, c, d] if flip else [a, b, c, b, d, c])

    xs, zs = np.arange(nx) * step, np.arange(ny) * step
    strip([(x, z[0, j], 0) for j, x in enumerate(xs)], (0, 0, -1), False)        # north
    strip([(x, z[-1, j], H) for j, x in enumerate(xs)], (0, 0, 1), True)         # south
    strip([(0, z[i, 0], zz) for i, zz in enumerate(zs)], (-1, 0, 0), True)       # west
    strip([(W, z[i, -1], zz) for i, zz in enumerate(zs)], (1, 0, 0), False)      # east
    k0 = sum(len(p) for p in pos)
    pos.append(np.array([(0, base, 0), (W, base, 0), (0, base, H), (W, base, H)], "float64"))
    nrm.append(np.repeat([(0, -1, 0)], 4, axis=0))
    idx.extend([k0, k0 + 1, k0 + 2, k0 + 1, k0 + 3, k0 + 2])
    p = np.concatenate(pos)
    p[:, 1] = np.round(p[:, 1] / Y_SCALE)
    p[:, 0] /= xy
    p[:, 2] /= xy
    return {"pos": np.round(p).astype("int16"),
            "nrm": quant_normal(np.concatenate(nrm).astype("float64"), xy),
            "uv": None, "idx": np.array(idx, "uint32"), "material": 1}


# ---------------------------------------------------------------- GLB writer
def write_glb(path, prims, jpeg, name, extras, xy=1):
    binbuf = bytearray()
    views, accessors = [], []

    def view(data: bytes, target=None, stride=None):
        while len(binbuf) % 4:
            binbuf.append(0)
        v = {"buffer": 0, "byteOffset": len(binbuf), "byteLength": len(data)}
        if target:
            v["target"] = target
        if stride:
            v["byteStride"] = stride
        binbuf.extend(data)
        views.append(v)
        return len(views) - 1

    def accessor(**kw):
        accessors.append(kw)
        return len(accessors) - 1

    gl_prims = []
    for p in prims:
        n = len(p["pos"])
        pos4 = np.zeros((n, 4), "int16")
        pos4[:, :3] = p["pos"]
        attrs = {"POSITION": accessor(bufferView=view(pos4.tobytes(), 34962, 8), componentType=5122,
                                      count=n, type="VEC3", min=p["pos"].min(0).tolist(),
                                      max=p["pos"].max(0).tolist())}
        n4 = np.zeros((n, 4), "int8")
        n4[:, :3] = p["nrm"]
        attrs["NORMAL"] = accessor(bufferView=view(n4.tobytes(), 34962, 4), componentType=5120,
                                   normalized=True, count=n, type="VEC3")
        if p["uv"] is not None:
            attrs["TEXCOORD_0"] = accessor(bufferView=view(p["uv"].tobytes(), 34962, 4),
                                           componentType=5123, normalized=True, count=n,
                                           type="VEC2")
        idx = p["idx"]
        ctype = 5123 if idx.dtype == np.uint16 else 5125
        ia = accessor(bufferView=view(idx.tobytes(), 34963), componentType=ctype,
                      count=len(idx), type="SCALAR")
        gl_prims.append({"attributes": attrs, "indices": ia, "material": p["material"]})
    img_view = view(jpeg)
    gltf = {
        "asset": {"version": "2.0", "generator": "brasov geodata pipeline (14_3d_sections.py)",
                  "copyright": "Copernicus DEM GLO-30 (DLR/Airbus); OpenStreetMap contributors / "
                               "Overture Maps (ODbL); Meta & WRI canopy (CC BY 4.0)"},
        "extensionsUsed": ["KHR_mesh_quantization"],
        "extensionsRequired": ["KHR_mesh_quantization"],
        "scene": 0, "scenes": [{"nodes": [0], "name": name}],
        "nodes": [{"mesh": 0, "name": name, "scale": [xy, Y_SCALE, xy], "extras": extras}],
        "meshes": [{"name": name, "primitives": gl_prims}],
        "materials": [
            {"name": "topographic map", "pbrMetallicRoughness": {
                "baseColorTexture": {"index": 0}, "metallicFactor": 0, "roughnessFactor": 1}},
            {"name": "block sides", "pbrMetallicRoughness": {
                "baseColorFactor": [*WALL_RGB, 1], "metallicFactor": 0, "roughnessFactor": 1}}],
        "textures": [{"sampler": 0, "source": 0}],
        "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}],
        "images": [{"bufferView": img_view, "mimeType": "image/jpeg"}],
        "accessors": accessors, "bufferViews": views,
        "buffers": [{"byteLength": len(binbuf)}],
    }
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    while len(binbuf) % 4:
        binbuf.append(0)
    total = 12 + 8 + len(js) + 8 + len(binbuf)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(binbuf), 0x004E4942) + bytes(binbuf))


# ---------------------------------------------------------------- main
def build(sid, title, rect, step, tex_size, dpi, topo_layers, sat_layers, outside, sat=True,
          xy=1):
    """xy = horizontal storage unit (m); int16 covers +-32 km at 1 m, so the overview uses 10."""
    z = heights(rect, step)
    base = float(np.floor((z.min() - BASE_BELOW) / 10) * 10)
    prims = terrain_prims(z, step, xy) + [wall_prim(z, step, base, xy)]
    jpeg = render(topo_layers + [outside], rect, tex_size, dpi)
    extras = {"sheet": sid, "name": title, "crs": "EPSG:3844",
              "origin_easting": rect[0], "origin_northing": rect[3],
              "axes": "X = easting - origin_easting, Z = origin_northing - northing, Y = "
                      "elevation (m, EGM2008, Copernicus GLO-30 DSM)",
              "mesh_step_m": step, "vertical_exaggeration": 1}
    glb = SEC / f"{sid}.glb"
    write_glb(glb, prims, jpeg, f"{sid} {title}", extras, xy)
    entry = {"sheet": sid, "name": title, "glb": f"sections/{glb.name}",
             "bounds": list(rect), "mesh_step_m": step, "base_m": base,
             "elev_min_m": round(float(z.min()), 1), "elev_max_m": round(float(z.max()), 1),
             "glb_mb": round(glb.stat().st_size / 1e6, 2)}
    if sat:
        sj = SEC / f"{sid}_satellite.jpg"
        sj.write_bytes(render(sat_layers + [outside], rect, SAT, 96))
        entry["satellite"] = f"sections/{sj.name}"
    print(f"  {sid} {title}: {entry['glb_mb']} MB, {z.min():.0f}-{z.max():.0f} m", flush=True)
    return entry


def main() -> None:
    project = QgsProject.instance()
    project.read(str(ROOT / "brasov_topographic.qgz"))
    tree = project.layerTreeRoot()
    topo = [lyr for lyr in tree.layerOrder() if tree.findLayer(lyr.id()).isVisible()
            and lyr.name() != "Sheet index 1:50,000"]
    img = QgsRasterLayer(str(RASTER / "imagery_sentinel2_truecolor_10m.tif"), "Sentinel-2")
    mb = QgsMultiBandColorRenderer(img.dataProvider(), 1, 2, 3)
    mb.setAlphaBand(4)
    for setter in (mb.setRedContrastEnhancement, mb.setGreenContrastEnhancement,
                   mb.setBlueContrastEnhancement):
        ce = QgsContrastEnhancement(img.dataProvider().dataType(1))
        ce.setContrastEnhancementAlgorithm(
            QgsContrastEnhancement.ContrastEnhancementAlgorithm.StretchToMinimumMaximum)
        ce.setMinimumValue(0)
        ce.setMaximumValue(165)
        setter(ce)
    img.setRenderer(mb)
    county_line = [lyr for lyr in topo if lyr.name() == "County boundary"]
    outside = outside_relief()

    idx = gpd.read_file(DATA / "brasov_topographic.gpkg", layer="topo_sheet_index_50k")
    only = [x.split("=", 1)[1].split(",") for x in sys.argv if x.startswith("--only=")]
    if only:   # quick test: build just these sections, skip overview and index
        for r in idx[idx.sheet.isin(only[0])].itertuples():
            build(r.sheet, r.name, (r.xmin, r.ymin, r.xmax, r.ymax), STEP, TEX, DPI, topo,
                  [img] + county_line, outside)
        return
    entries = []
    for r in idx.sort_values("page").itertuples():
        rect = (r.xmin, r.ymin, r.xmax, r.ymax)
        entries.append(build(r.sheet, r.name, rect, STEP, TEX, DPI, topo, [img] + county_line,
                             outside))
    # county overview: whole sheet grid, coarser mesh, generalised texture
    xmin, ymin, xmax, ymax = idx.total_bounds
    rect = (float(xmin), float(ymin), float(xmax), float(ymax))
    w = 4096
    h = int(round(w * (ymax - ymin) / (xmax - xmin)))
    ov = build("BV-overview", "Brașov County (overview)", rect, OV_STEP, (w, h), 150, topo,
               [img] + county_line, outside, sat=True, xy=10)
    index = {"title": "Brașov County - 3D topographic sections",
             "crs": "EPSG:3844", "vertical_exaggeration_in_files": 1,
             "overview": ov, "sections": entries,
             "notes": "Sections match the 1:50,000 sheets BV50-*. Elevations: Copernicus DEM "
                      "GLO-30 (surface model, EGM2008). Textures: topographic map of this "
                      "dataset; satellite: Sentinel-2 L2A 2025-07-26."}
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1))
    total = sum(e["glb_mb"] for e in entries) + ov["glb_mb"]
    print(f"sections: {len(entries)} + overview, {total:.0f} MB of GLB")


if __name__ == "__main__":
    main()
    app.exitQgis()
