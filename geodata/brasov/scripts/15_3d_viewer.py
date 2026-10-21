"""3D viewer for the relief sections + preview renders.

  maps/3d/viewer.html     offline viewer (three.js + proj4 vendored in maps/3d/lib). Browsers block
                          local file loading, so serve the folder:  python -m http.server -d maps/3d
                          then open http://localhost:8000/viewer.html
  maps/3d/index.json      enriched with the county outline and grid bounds for the index map
  docs/3d/<sheet>.jpg     oblique render of every section (headless Chromium, same viewer code)
  docs/3d_sections.jpg    contact sheet of all sections
  docs/3d/detail_*.jpg    close-ups of the infrastructure (bridges, tunnels, lifts)
  _work/artifact/         the same viewer with CDN imports, for publishing as a web page. Web
                          hosts may not serve .glb, so there each block is rebuilt in the browser
                          from <sheet>_height.png (lossless, the GLB's own decimetre heights) and
                          <sheet>_topo.jpg (the GLB's own texture) and <sheet>_infra.json (the
                          GLB's infrastructure meshes, base64 arrays), all extracted from the GLB.
                          Its download links point at the GLBs on GitHub, pinned to the last
                          commit that changed maps/3d/sections (commit new models first)

Libraries: three.js 0.170.0 and proj4 2.15.0 (npm). Pass --no-shots to skip the renders,
--only=ID,ID to re-render some of them.
"""
import base64
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
from infra3d import MATERIALS

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


def glb_infra(path: Path) -> dict | None:
    """Infrastructure nodes of a section GLB as JSON-ready base64 arrays."""
    gltf, binbuf = read_glb(path)

    def arr(acc_i, dtype):
        acc = gltf["accessors"][acc_i]
        bv = gltf["bufferViews"][acc["bufferView"]]
        n = acc["count"] * {"SCALAR": 1, "VEC2": 2, "VEC3": 3}[acc["type"]]
        a = np.frombuffer(binbuf, dtype, n, bv["byteOffset"])
        return base64.b64encode(a.tobytes()).decode()

    layers = []
    for node in gltf["nodes"]:
        ex = node.get("extras", {})
        if "layer" not in ex:
            continue
        prims = []
        for prim in gltf["meshes"][node["mesh"]]["primitives"]:
            mat = gltf["materials"][prim["material"]]["name"]
            hexc, emissive, double = MATERIALS[mat]
            at = prim["attributes"]
            prims.append({"mode": prim.get("mode", 4), "material": mat, "color": hexc,
                          "emissive": emissive, "double": double,
                          "pos": arr(at["POSITION"], "float32"),
                          "nrm": arr(at["NORMAL"], "float32") if "NORMAL" in at else None,
                          "fid": arr(at["_FEATURE_ID"], "float32"),
                          "idx": arr(prim["indices"], "uint32") if "indices" in prim else None})
        layers.append({**ex, "prims": prims})
    return {"layers": layers} if layers else None


def github_links() -> tuple[str, str]:
    """(raw-file URL prefix, folder URL) of maps/3d/sections on GitHub at the last commit that
    changed it."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=OUT, capture_output=True, text=True,
                              check=True).stdout.strip()
    repo = git("remote", "get-url", "origin").split("github.com/", 1)[1].removesuffix(".git")
    rel = (OUT / "sections").relative_to(git("rev-parse", "--show-toplevel")).as_posix()
    sha = git("log", "-1", "--format=%H", "--", "sections")
    if git("status", "--porcelain", "--", "sections"):
        print("  note: uncommitted models - download links point to the last committed ones")
    return (f"https://github.com/{repo}/raw/{sha}/{rel}",
            f"https://github.com/{repo}/tree/{sha}/{rel}")


def web_package(idx: dict) -> None:
    """Heights + drapes for the web viewer (see module docstring)."""
    adir = WORK / "artifact"
    sec = adir / "sections"
    shutil.rmtree(sec, ignore_errors=True)
    sec.mkdir(parents=True)
    web = json.loads(json.dumps(idx))
    raw, web["download_all"] = github_links()
    for e in [web["overview"]] + web["sections"]:
        e["download"] = f"{raw}/{e['sheet']}.glb"
        grid, jpeg = glb_height_and_texture(OUT / e.pop("glb"), e["mesh_step_m"])
        rgb = np.zeros(grid.shape + (3,), "uint8")
        rgb[..., 0], rgb[..., 1] = grid >> 8, grid & 255
        h = sec / f"{e['sheet']}_height.png"
        Image.fromarray(rgb, "RGB").save(h, optimize=True)
        t = sec / f"{e['sheet']}_topo.jpg"
        t.write_bytes(jpeg)
        files = [h, t]
        infra = glb_infra(OUT / f"sections/{e['sheet']}.glb")
        if infra:
            j = sec / f"{e['sheet']}_infra.json"
            j.write_text(json.dumps(infra, ensure_ascii=False, separators=(",", ":")))
            files.append(j)
            e["infra_json"] = f"sections/{j.name}"
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


# close-ups: (file, query) - cx/cz aim at a point as fractions of the block, cy its elevation
DETAILS = [
    ("detail_predeal_tunnels", "s=BV50-F4&cx=0.875&cz=0.24&cy=1000&dist=0.11&az=25&el=42"),
    ("detail_predeal_dn1_viaduct", "s=BV50-F4&cx=0.714&cz=0.464&cy=1000&dist=0.035&az=-50&el=28"),
    ("detail_poiana_brasov_lifts", "s=BV50-E4&cx=0.675&cz=0.78&cy=1250&dist=0.16&az=-35&el=32"),
    ("detail_brasov_tampa", "s=BV50-E4&cx=0.83&cz=0.33&cy=700&dist=0.09&az=-20&el=38"),
]


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
        if not only:
            for fn, q in DETAILS:
                page.goto(f"http://127.0.0.1:{port}/viewer.html?{q}&shot=1&tex=topo")
                page.wait_for_function("window.__ready === true", timeout=180000)
                page.wait_for_timeout(300)
                page.screenshot(path=str(DOCS3D / f"{fn}.jpg"), type="jpeg", quality=88)
                print("  shot", fn, flush=True)
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
