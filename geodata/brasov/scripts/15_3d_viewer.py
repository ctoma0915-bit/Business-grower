"""3D viewer for the relief sections + preview renders.

  maps/3d/viewer.html     offline viewer (three.js + proj4 vendored in maps/3d/lib). Browsers block
                          local file loading, so serve the folder:  python -m http.server -d maps/3d
                          then open http://localhost:8000/viewer.html
  maps/3d/index.json      enriched with the county outline and grid bounds for the index map
  docs/3d/<sheet>.jpg     oblique render of every section (headless Chromium, same viewer code)
  docs/3d_sections.jpg    contact sheet of all sections
  _work/artifact/         the same viewer with CDN imports, for publishing as a web page. Web
                          hosts may not serve .glb, so there each block is rebuilt in the browser
                          from <sheet>_height.png (lossless, the GLB's own decimetre heights) and
                          <sheet>_topo.jpg (the GLB's own texture), both extracted from the GLB

Libraries: three.js 0.170.0 and proj4 2.15.0 (npm). Pass --no-shots to skip the renders,
--only=ID,ID to re-render some of them.
"""
import functools
import http.server
import json
import shutil
import socketserver
import struct
import subprocess
import sys
import threading
from pathlib import Path

import geopandas as gpd
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from common import DATA, ROOT, WORK, stage_gpkg

OUT = ROOT / "maps" / "3d"
LIB = OUT / "lib"
DOCS3D = ROOT / "docs" / "3d"
TEMPLATE = Path(__file__).with_name("viewer_template.html")
THREE_VER, PROJ4_VER = "0.170.0", "2.15.0"
NODE_MODULES = Path(sys.argv[sys.argv.index("--node-modules") + 1]) if "--node-modules" in sys.argv \
    else WORK / "node" / "node_modules"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

IMPORTMAP = """<script type="importmap">
{{"imports": {{"three": "{three}", "three/addons/": "{addons}"}}}}
</script>"""


def vendor_libs() -> None:
    """Copy the exact library files the viewer imports (offline use)."""
    if not (NODE_MODULES / "three").exists():
        subprocess.run(["npm", "install", "--prefix", str(NODE_MODULES.parent), "--silent",
                        f"three@{THREE_VER}", f"proj4@{PROJ4_VER}"], check=True)
    jsm = NODE_MODULES / "three" / "examples" / "jsm"
    files = {LIB / "three.module.min.js": NODE_MODULES / "three/build/three.module.min.js",
             LIB / "addons/loaders/GLTFLoader.js": jsm / "loaders/GLTFLoader.js",
             LIB / "addons/controls/OrbitControls.js": jsm / "controls/OrbitControls.js",
             LIB / "addons/utils/BufferGeometryUtils.js": jsm / "utils/BufferGeometryUtils.js",
             LIB / "proj4.js": NODE_MODULES / "proj4/dist/proj4.js"}
    for dst, src in files.items():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    (LIB / "LICENSES.txt").write_text(
        f"three.js {THREE_VER} - MIT License, Copyright 2010-2024 three.js authors\n"
        f"proj4js {PROJ4_VER} - MIT License, Copyright 2014 Mike Adair, Richard Greenwood, "
        "Didier Richard, Stephen Irons, Olivier Terral, Calvin Metcalf\n")


def enrich_index() -> dict:
    idx = json.loads((OUT / "index.json").read_text())
    county = gpd.read_file(stage_gpkg("boundaries"), layer="admin_county").geometry.iloc[0]
    outline = county.simplify(250)
    outline = max(outline.geoms, key=lambda g: g.area) if outline.geom_type == "MultiPolygon" \
        else outline
    idx["county_outline"] = [[round(x), round(y)] for x, y in outline.exterior.coords]
    sheets = gpd.read_file(DATA / "brasov_topographic.gpkg", layer="topo_sheet_index_50k")
    idx["grid_bounds"] = [float(v) for v in sheets.total_bounds]
    (OUT / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1))
    return idx


def write_viewers() -> Path:
    body = TEMPLATE.read_text()
    head_end = body.index("{{IMPORTMAP}}") + len("{{IMPORTMAP}}")
    local_head = (body[:head_end]
                  .replace("{{PROJ4}}", '<script src="lib/proj4.js"></script>')
                  .replace("{{IMPORTMAP}}", IMPORTMAP.format(three="./lib/three.module.min.js",
                                                             addons="./lib/addons/")))
    local = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
             '<meta name="viewport" content="width=device-width, initial-scale=1, '
             'viewport-fit=cover">\n<style>[hidden]{display:none!important}body{margin:0}</style>\n'
             + local_head + "\n</head>\n<body>\n" + body[head_end:] + "\n</body>\n</html>\n")
    (OUT / "viewer.html").write_text(local)
    cdn = f"https://cdn.jsdelivr.net/npm/three@{THREE_VER}"
    art = (body.replace("{{PROJ4}}", f'<script src="https://cdn.jsdelivr.net/npm/proj4@{PROJ4_VER}'
                                     '/dist/proj4.js"></script>')
           .replace("{{IMPORTMAP}}", IMPORTMAP.format(three=f"{cdn}/build/three.module.min.js",
                                                      addons=f"{cdn}/examples/jsm/")))
    adir = WORK / "artifact"
    adir.mkdir(exist_ok=True)
    (adir / "brasov-3d-relief.html").write_text(art)
    return adir / "brasov-3d-relief.html"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def read_glb(path: Path):
    raw = path.read_bytes()
    jlen = struct.unpack_from("<I", raw, 12)[0]
    gltf = json.loads(raw[20:20 + jlen])
    return gltf, raw[20 + jlen + 8:]


def glb_height_and_texture(path: Path, step: float):
    """Terrain heights (dm, grid) and the JPEG drape, read back from a section GLB."""
    gltf, binbuf = read_glb(path)
    node = gltf["nodes"][0]
    xy = node["scale"][0]
    pts = []
    for prim in gltf["meshes"][0]["primitives"]:
        if prim["material"] != 0:
            continue
        acc = gltf["accessors"][prim["attributes"]["POSITION"]]
        bv = gltf["bufferViews"][acc["bufferView"]]
        a = np.frombuffer(binbuf, "int16", acc["count"] * 4, bv["byteOffset"]).reshape(-1, 4)
        pts.append(a[:, :3])
    pts = np.concatenate(pts).astype("int64")
    col = np.round(pts[:, 0] * xy / step).astype(int)
    row = np.round(pts[:, 2] * xy / step).astype(int)
    grid = np.full((row.max() + 1, col.max() + 1), -1, "int64")
    grid[row, col] = pts[:, 1]
    assert (grid >= 0).all() and grid.max() < 65536
    bv = gltf["bufferViews"][gltf["images"][0]["bufferView"]]
    jpeg = binbuf[bv["byteOffset"]:bv["byteOffset"] + bv["byteLength"]]
    return grid, jpeg


def web_package(idx: dict) -> None:
    """Heights + drapes for the web viewer (see module docstring)."""
    adir = WORK / "artifact"
    sec = adir / "sections"
    shutil.rmtree(sec, ignore_errors=True)
    sec.mkdir(parents=True)
    web = json.loads(json.dumps(idx))
    for e in [web["overview"]] + web["sections"]:
        grid, jpeg = glb_height_and_texture(OUT / e.pop("glb"), e["mesh_step_m"])
        rgb = np.zeros(grid.shape + (3,), "uint8")
        rgb[..., 0], rgb[..., 1] = grid >> 8, grid & 255
        h = sec / f"{e['sheet']}_height.png"
        Image.fromarray(rgb, "RGB").save(h, optimize=True)
        t = sec / f"{e['sheet']}_topo.jpg"
        t.write_bytes(jpeg)
        files = [h, t]
        if "satellite" in e:
            shutil.copyfile(OUT / e["satellite"], adir / e["satellite"])
        e.update(height=f"sections/{h.name}", topo=f"sections/{t.name}",
                 web_bytes=sum(f.stat().st_size for f in files))
        e["web_mb"] = round(e["web_bytes"] / 1e6, 2)
    (adir / "index.json").write_text(json.dumps(web, ensure_ascii=False, indent=1))
    total = sum(f.stat().st_size for f in sec.iterdir())
    print(f"web package: {len(list(sec.iterdir()))} files, {total / 1e6:.0f} MB")


def serve(directory: Path):
    handler = functools.partial(QuietHandler, directory=str(directory))
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def shots(idx: dict) -> None:
    from playwright.sync_api import sync_playwright
    DOCS3D.mkdir(parents=True, exist_ok=True)
    srv, port = serve(OUT)
    items = [(s["sheet"], s["name"]) for s in idx["sections"]] + [("BV-overview", "Whole county")]
    only = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--only=")), None)
    if only:
        items = [it for it in items if it[0] in only]
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--use-gl=angle",
                                                             "--use-angle=swiftshader",
                                                             "--enable-unsafe-swiftshader"])
        page = b.new_page(viewport={"width": 1600, "height": 1000})
        for sid, name in items:
            for tex in ("topo",) + (("sat",) if sid in ("BV50-E4", "BV50-F3") else ()):
                # the county is 3x wider than deep: look at it square-on from the south
                view = "az=0&el=42&dist=1.12&exag=1.5" if sid == "BV-overview" else \
                    "az=-20&el=30&exag=1"
                page.goto(f"http://127.0.0.1:{port}/viewer.html?s={sid}&shot=1&tex={tex}&{view}")
                page.wait_for_function("window.__ready === true", timeout=180000)
                page.wait_for_timeout(1500 if tex == "sat" else 300)
                fn = DOCS3D / f"{sid}{'_satellite' if tex == 'sat' else ''}.jpg"
                page.screenshot(path=str(fn), type="jpeg", quality=88)
                print("  shot", fn.name, flush=True)
        b.close()
    srv.shutdown()
    # contact sheet in sheet-grid order
    sheets = [s for s in idx["sections"]]
    rows = sorted({s["sheet"][5] for s in sheets})
    cols = sorted({int(s["sheet"][6:]) for s in sheets})
    tw, th = 400, 250
    sheet_img = Image.new("RGB", (len(cols) * tw, len(rows) * th), (240, 242, 238))
    draw = ImageDraw.Draw(sheet_img)
    font = ImageFont.load_default(size=18)
    for s in sheets:
        r, c = rows.index(s["sheet"][5]), cols.index(int(s["sheet"][6:]))
        im = Image.open(DOCS3D / f"{s['sheet']}.jpg").convert("RGB")
        im.thumbnail((tw, th))
        x, y = c * tw + (tw - im.width) // 2, r * th + (th - im.height) // 2
        sheet_img.paste(im, (x, y))
        draw.text((c * tw + 10, r * th + 8), f"{s['sheet']}  {s['name']}", fill=(30, 36, 32),
                  font=font)
    sheet_img.save(ROOT / "docs" / "3d_sections.jpg", quality=88, optimize=True)


def main() -> None:
    vendor_libs()
    idx = enrich_index()
    art = write_viewers()
    print("viewer:", OUT / "viewer.html", "| web page:", art)
    web_package(idx)
    if "--no-shots" not in sys.argv:
        shots(idx)


if __name__ == "__main__":
    main()
