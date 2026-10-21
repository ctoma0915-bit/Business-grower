"""3D infrastructure for the relief sections (14_3d_sections.py): bridges, tunnels, power lines,
cable cars / ski lifts and dams, placed on the same surface as the terrain mesh.

  bridges     turquoise deck at the modelled deck height (topo_structures Z, never below the mesh
              surface), grey piers every ~30 m down to the valley floor where the deck is high
  tunnels     magenta tube inside the ground (the viewer shows it through the terrain), dark
              portal arches where the tunnel meets the surface
  power       towers at the line's vertices (OSM nodes = pylons), cross-arms, sagging conductors
  aerialways  supports and stations, cables (two strands for gondolas / chair lifts)
  dams        crest wall along the dam line

Every part carries a feature index (vertex attribute _FEATURE_ID) into the layer's feature list
(node extras), so the viewer can name what is under the pointer.
World coordinates are Stereo 70 metres (E, N, z); `Layer.export` converts to glTF axes
(X = E - west, Y = z, Z = north - N).
"""
import numpy as np
from shapely.geometry import box

from structures import (DECK_CLEARANCE, DECK_THICKNESS, Surface, as_lines, chainage, clip_3d,
                        floor_under)

# material name -> (sRGB hex, emissive share, double sided)
MATERIALS = {
    "bridge_deck": ("#00bfcf", 0.35, True),
    "bridge_pier": ("#6e6e6e", 0.0, True),
    "bridge_marker": ("#00bfcf", 1.0, False),
    "tunnel_tube": ("#d22fd2", 0.45, True),
    "tunnel_line": ("#d22fd2", 1.0, False),
    "tunnel_portal": ("#2e2e33", 0.0, True),
    "tunnel_marker": ("#d22fd2", 1.0, False),
    "power_cable": ("#7a3cff", 0.5, False),
    "power_tower": ("#5c5c5c", 0.0, False),
    "aerial_cable": ("#1a8cff", 0.6, False),
    "aerial_tower": ("#1d2b45", 0.0, False),
    "aerial_station": ("#1d4f8f", 0.1, True),
    "dam": ("#a3acb6", 0.05, True),
}

LAYERS = {   # key -> (label for the legend, swatch material)
    "bridges": ("Bridges & viaducts", "bridge_deck"),
    "tunnels": ("Tunnels (seen through the ground)", "tunnel_tube"),
    "power": ("Power lines", "power_cable"),
    "aerialways": ("Cable cars & ski lifts", "aerial_cable"),
    "dams": ("Dams", "dam"),
}

POWER_HEIGHT = {"power_line": 32.0, "minor_line": 12.0}
AERIAL_HEIGHT = {"cable_car": 18.0, "gondola": 14.0, "mixed_lift": 12.0, "chair_lift": 10.0,
                 "platter": 5.0, "drag_lift": 5.0, "t-bar": 5.0, "j-bar": 5.0, "rope_tow": 2.0,
                 "magic_carpet": 1.0, "zip_line": 12.0}
AERIAL_LABEL = {"cable_car": "Cable car", "gondola": "Gondola", "mixed_lift": "Gondola / chair lift",
                "chair_lift": "Chair lift", "platter": "Platter lift", "drag_lift": "Drag lift",
                "t-bar": "T-bar lift", "j-bar": "J-bar lift", "rope_tow": "Rope tow",
                "zip_line": "Zip line"}
STATIONS = {"cable_car", "gondola", "mixed_lift", "chair_lift"}
# passages under buildings and short underpasses are tagged as tunnels too; they stay in the 2D
# data but would only clutter the 3D view
MINOR_PASSAGE = {"footway", "path", "steps", "pedestrian", "cycleway", "service", "living_street",
                 "bridleway"}
MAJOR = {"motorway", "trunk", "primary"}


def srgb_to_linear(hexcol: str):
    c = np.array([int(hexcol[i:i + 2], 16) / 255 for i in (1, 3, 5)])
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).round(4).tolist()


class Layer:
    """Triangles, line segments and points per material, plus the feature list."""

    def __init__(self, key: str):
        self.key = key
        self.features: list[dict] = []
        self.tris: dict[str, list] = {}     # material -> [pos, nrm, idx, fid] lists
        self.lines: dict[str, list] = {}    # material -> [pos pairs, fid]
        self.points: dict[str, list] = {}

    def feature(self, props: dict) -> int:
        self.features.append({k: v for k, v in props.items() if v is not None and v == v})
        return len(self.features) - 1

    # -- primitives (world coordinates)
    def mesh(self, mat, pos, nrm, idx, fid):
        t = self.tris.setdefault(mat, [[], [], [], [], 0])
        t[0].append(pos), t[1].append(nrm), t[2].append(idx + t[4]), t[3].append(np.full(len(pos), fid))
        t[4] += len(pos)

    def segments(self, mat, pts_a, pts_b, fid):
        seg = np.empty((len(pts_a) * 2, 3))
        seg[0::2], seg[1::2] = pts_a, pts_b
        ln = self.lines.setdefault(mat, [[], []])
        ln[0].append(seg), ln[1].append(np.full(len(seg), fid))

    def polyline(self, mat, pts, fid):
        if len(pts) >= 2:
            self.segments(mat, pts[:-1], pts[1:], fid)

    def point(self, mat, p, fid):
        pt = self.points.setdefault(mat, [[], []])
        pt[0].append(np.asarray(p, "float64")[None]), pt[1].append(np.array([fid]))

    def empty(self) -> bool:
        return not (self.tris or self.lines or self.points)

    def export(self, x0: float, y1: float) -> dict:
        """glTF-ready arrays: positions float32 in glTF axes, normals, uint32 indices."""
        def axes(p):
            return np.column_stack([p[:, 0] - x0, p[:, 2], y1 - p[:, 1]]).astype("float32")

        def naxes(n):
            return np.column_stack([n[:, 0], n[:, 2], -n[:, 1]]).astype("float32")

        prims = []
        for mat, (pos, nrm, idx, fid, _) in self.tris.items():
            prims.append({"mode": 4, "material": mat, "pos": axes(np.concatenate(pos)),
                          "nrm": naxes(np.concatenate(nrm)), "idx": np.concatenate(idx).astype("uint32"),
                          "fid": np.concatenate(fid).astype("float32")})
        for mat, (pos, fid) in self.lines.items():
            prims.append({"mode": 1, "material": mat, "pos": axes(np.concatenate(pos)), "nrm": None,
                          "idx": None, "fid": np.concatenate(fid).astype("float32")})
        for mat, (pos, fid) in self.points.items():
            prims.append({"mode": 0, "material": mat, "pos": axes(np.concatenate(pos)), "nrm": None,
                          "idx": None, "fid": np.concatenate(fid).astype("float32")})
        label, swatch = LAYERS[self.key]
        return {"name": f"infra:{self.key}", "prims": prims,
                "extras": {"layer": self.key, "label": label, "swatch": MATERIALS[swatch][0],
                           "count": len(self.features), "features": self.features}}


# ---------------------------------------------------------------- geometry helpers
def directions(xy: np.ndarray):
    """Unit direction and left-hand normal at each vertex of a 2D polyline."""
    d = np.gradient(xy, axis=0) if len(xy) > 1 else np.array([[1.0, 0.0]])
    d /= np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9)[:, None]
    return d, np.column_stack([-d[:, 1], d[:, 0]])


def sweep_box(layer, mat, xy, top, bottom, width, fid):
    """Closed box swept along a polyline: top/bottom heights per vertex, constant width."""
    n_pts = len(xy)
    d, n = directions(xy)
    h = width / 2
    L = np.column_stack([xy + n * h])
    R = np.column_stack([xy - n * h])
    corners = {"lt": np.column_stack([L, top]), "rt": np.column_stack([R, top]),
               "lb": np.column_stack([L, bottom]), "rb": np.column_stack([R, bottom])}
    up = np.tile([0, 0, 1.0], (n_pts, 1))
    side_n = np.column_stack([n, np.zeros(n_pts)])
    faces = [("lt", "rt", up), ("rb", "lb", -up), ("lb", "lt", side_n), ("rt", "rb", -side_n)]
    pos, nrm, idx = [], [], []
    k = 0
    for a, b, fn in faces:
        strip = np.empty((n_pts * 2, 3))
        strip[0::2], strip[1::2] = corners[a], corners[b]
        pos.append(strip)
        nrm.append(np.repeat(fn, 2, axis=0))
        i = np.arange(n_pts - 1) * 2 + k
        idx.append(np.column_stack([i, i + 1, i + 2, i + 2, i + 1, i + 3]).ravel())
        k += n_pts * 2
    for end, sign in ((0, -1), (-1, 1)):          # end caps
        cap = np.array([corners["lt"][end], corners["rt"][end], corners["lb"][end],
                        corners["rb"][end]])
        pos.append(cap)
        nrm.append(np.tile(np.append(d[end] * sign, 0), (4, 1)))
        idx.append(np.array([0, 1, 2, 2, 1, 3]) + k)
        k += 4
    layer.mesh(mat, np.concatenate(pos), np.concatenate(nrm), np.concatenate(idx), fid)


def block(layer, mat, centre_xy, direction, length, width, z0, z1, fid):
    """Upright box (piers, portal pillars, stations) oriented along `direction`."""
    c = np.asarray(centre_xy, "float64")
    d = np.asarray(direction, "float64") / max(np.hypot(*direction), 1e-9)
    xy = np.array([c - d * length / 2, c + d * length / 2])
    sweep_box(layer, mat, xy, np.array([z1, z1]), np.array([z0, z0]), width, fid)


def tube(layer, mat, xy, zc, radius, fid, sides=10):
    d, n = directions(xy)
    a = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    ring_n = (np.cos(a)[None, :, None] * np.column_stack([n, np.zeros(len(xy))])[:, None, :]
              + np.sin(a)[None, :, None] * np.array([0, 0, 1.0])[None, None, :])
    centre = np.column_stack([xy, zc])[:, None, :]
    pos = (centre + ring_n * radius).reshape(-1, 3)
    i, j = np.meshgrid(np.arange(len(xy) - 1), np.arange(sides), indexing="ij")
    a0, a1 = i * sides + j, i * sides + (j + 1) % sides
    b0, b1 = a0 + sides, a1 + sides
    idx = np.stack([a0, b0, a1, a1, b0, b1], axis=-1).ravel()
    layer.mesh(mat, pos, ring_n.reshape(-1, 3), idx, fid)


def resample(xyz: np.ndarray, spacing: float) -> np.ndarray:
    """Resample a 3D polyline every `spacing` m (Z interpolated along the 2D chainage). Fine
    spacings keep the original vertices (exact bends); coarse ones (overview) do not."""
    s = chainage(xyz[:, :2])
    if s[-1] == 0:
        return xyz
    n = max(2, int(np.ceil(s[-1] / spacing)) + 1)
    t = np.linspace(0, s[-1], n)
    if spacing < 30:
        t = np.unique(np.concatenate([t, s]))
    return np.column_stack([np.interp(t, s, xyz[:, 0]), np.interp(t, s, xyz[:, 1]),
                            np.interp(t, s, xyz[:, 2])])


def inside(xy, rect):
    return ((xy[:, 0] >= rect[0]) & (xy[:, 0] <= rect[2]) & (xy[:, 1] >= rect[1])
            & (xy[:, 1] <= rect[3]))


# ---------------------------------------------------------------- layers
def bridges(st, rect, surf: Surface, min_len=0.0, spacing=8.0, piers=True):
    lay = Layer("bridges")
    area = box(*rect)
    for r in st.itertuples():
        if r.structure != "bridge" or r.length_m < min_len:
            continue
        for part in clip_3d(r.geometry, area):
            xyz = resample(np.asarray(part.coords), spacing)
            xy = xyz[:, :2]
            g = surf(xy[:, 0], xy[:, 1])
            top = np.maximum(xyz[:, 2], g + DECK_CLEARANCE + DECK_THICKNESS)
            w = max(float(r.width_m), 3.5)
            fid = lay.feature({"kind": "Bridge" if r.length_m < 150 else "Viaduct",
                               "name": r.name, "ref": r.ref, "mode": r.mode, "class": r.cls,
                               "status": r.status, "length_m": r.full_length_m,
                               "clearance_m": r.max_clearance_m})
            sweep_box(lay, "bridge_deck", xy, top, top - DECK_THICKNESS, w, fid)
            s = chainage(xy)
            if piers and s[-1] > 24:
                floor = floor_under(xy, surf, float(np.clip(0.4 * r.full_length_m, 12, 45)))
                d, _ = directions(xy)
                for sp in np.arange(15, s[-1] - 9, 30.0):
                    k = int(np.searchsorted(s, sp))
                    bottom = np.interp(sp, s, top) - DECK_THICKNESS
                    base = np.interp(sp, s, floor)
                    if bottom - base > 3:
                        c = [np.interp(sp, s, xy[:, 0]), np.interp(sp, s, xy[:, 1])]
                        block(lay, "bridge_pier", c, d[min(k, len(d) - 1)],
                              3.0 if r.mode == "rail" else 2.2, w * 0.7, base - 1, bottom, fid)
            if r.full_length_m >= 20 or r.cls in MAJOR:
                m = len(xy) // 2
                lay.point("bridge_marker", [xy[m, 0], xy[m, 1], top[m] + 2], fid)
    return lay


def tunnels(st, rect, surf: Surface, min_len=0.0, spacing=10.0, sides=10):
    lay = Layer("tunnels")
    area = box(*rect)
    for r in st.itertuples():
        if r.structure != "tunnel" or r.length_m < min_len:
            continue
        if r.cls in MINOR_PASSAGE and r.full_length_m < 40:
            continue
        notable = r.mode == "rail" or r.cls in MAJOR or r.full_length_m >= 100
        radius = float(np.clip(r.width_m / 2 + 1, 4, 8))
        for part in clip_3d(r.geometry, area):
            xyz = resample(np.asarray(part.coords), spacing)
            xy = xyz[:, :2]
            g = surf(xy[:, 0], xy[:, 1])
            s = chainage(xy)
            inner = np.minimum(s, s[-1] - s) > 40
            floor = np.where(inner, np.minimum(xyz[:, 2], g - 2 * radius - 2), xyz[:, 2])
            zc = floor + radius * 0.9
            fid = lay.feature({"kind": "Tunnel", "name": r.name, "ref": r.ref, "mode": r.mode,
                               "status": r.status, "length_m": r.full_length_m,
                               "cover_m": r.max_cover_m})
            tube(lay, "tunnel_tube", xy, zc, radius, fid, sides)
            lay.polyline("tunnel_line", np.column_stack([xy, zc]), fid)
            d, n = directions(xy)
            for end, out in ((0, -1), (-1, 1)):
                if abs(floor[end] - g[end]) > 10:         # cut by the sheet edge, not a portal
                    continue
                c, nn = xy[end], n[end]
                w2 = radius + 1.2
                for side in (-1, 1):                       # pillars + lintel
                    block(lay, "tunnel_portal", c + nn * side * w2, d[end], 1.6, 1.6,
                          floor[end] - 1, floor[end] + 2 * radius, fid)
                block(lay, "tunnel_portal", c, d[end], 1.6, 2 * w2 + 1.6,
                      floor[end] + 2 * radius - 0.5, floor[end] + 2 * radius + 1.5, fid)
                if notable:
                    lay.point("tunnel_marker", [c[0], c[1], floor[end] + 2 * radius + 4], fid)
    return lay


def _span_points(a, b, za, zb, surf, sag_ratio, max_sag, clearance, spacing=25.0):
    span = float(np.hypot(*(b - a)))
    n = max(2, int(np.ceil(span / spacing)) + 1)
    t = np.linspace(0, 1, n)[:, None]
    xy = a + (b - a) * t
    sag = min(sag_ratio * span, max_sag)
    z = za + (zb - za) * t[:, 0] - 4 * sag * t[:, 0] * (1 - t[:, 0])
    z = np.maximum(z, surf(xy[:, 0], xy[:, 1]) + clearance)
    return np.column_stack([xy, z])


def _emit_inside(lay, mat, pts, rect, fid):
    keep = inside(pts[:, :2], rect)
    pair = keep[:-1] & keep[1:]
    if pair.any():
        lay.segments(mat, pts[:-1][pair], pts[1:][pair], fid)


def power(lines, rect, surf: Surface, classes=("power_line", "minor_line"), spacing=25.0):
    lay = Layer("power")
    sel = lines[lines["cls"].isin(classes)]
    for r in sel.itertuples():
        H = float(r.height) if r.height == r.height and r.height else POWER_HEIGHT[r.cls]
        fid = lay.feature({"kind": "High-voltage power line" if r.cls == "power_line"
                           else "Power line (minor)", "name": r.name, "tower_height_m": H})
        for ln in as_lines(r.geometry):
            v = np.asarray(ln.coords)[:, :2]
            base = surf(v[:, 0], v[:, 1])
            d, n = directions(v)
            arm = 6.0 if r.cls == "power_line" else 0.0
            wires = (-arm, arm) if arm else (0.0,)
            ins = inside(v, rect)
            for k in np.nonzero(ins)[0]:                   # towers
                lay.segments("power_tower", [[*v[k], base[k] - 1]], [[*v[k], base[k] + H]], fid)
                if arm:
                    lay.segments("power_tower", [[*(v[k] - n[k] * arm), base[k] + H - 3]],
                                 [[*(v[k] + n[k] * arm), base[k] + H - 3]], fid)
            for k in range(len(v) - 1):                    # conductors
                if not (ins[k] or ins[k + 1]):
                    continue
                for o in wires:
                    a, b = v[k] + n[k] * o, v[k + 1] + n[k + 1] * o
                    pts = _span_points(a, b, base[k] + H - 3.5, base[k + 1] + H - 3.5, surf,
                                       0.03, 25.0, 7.0, spacing)
                    _emit_inside(lay, "power_cable", pts, rect, fid)
    return lay


def aerialways(lines, rect, surf: Surface):
    lay = Layer("aerialways")
    sel = lines[lines["subtype"] == "aerialway"]
    for r in sel.itertuples():
        cls = r.cls
        H = AERIAL_HEIGHT.get(cls, 8.0)
        fid = lay.feature({"kind": AERIAL_LABEL.get(cls, "Aerialway"), "name": r.name})
        for ln in as_lines(r.geometry):
            v = np.asarray(ln.coords)[:, :2]
            base = surf(v[:, 0], v[:, 1])
            d, n = directions(v)
            ins = inside(v, rect)
            off = (-3.0, 3.0) if cls in STATIONS else (0.0,)
            for k in np.nonzero(ins)[0]:
                if cls in STATIONS and k in (0, len(v) - 1):
                    block(lay, "aerial_station", v[k], d[k], 14, 10, base[k] - 1, base[k] + H * 0.6,
                          fid)
                else:
                    lay.segments("aerial_tower", [[*v[k], base[k] - 1]], [[*v[k], base[k] + H]],
                                 fid)
            for k in range(len(v) - 1):
                if not (ins[k] or ins[k + 1]):
                    continue
                for o in off:
                    a, b = v[k] + n[k] * o, v[k + 1] + n[k + 1] * o
                    pts = _span_points(a, b, base[k] + H - 0.5, base[k + 1] + H - 0.5, surf,
                                       0.015, 15.0, 2.0 if cls in STATIONS else 0.8)
                    _emit_inside(lay, "aerial_cable", pts, rect, fid)
    return lay


def dams(lines, rect, surf: Surface):
    lay = Layer("dams")
    area = box(*rect)
    sel = lines[lines["cls"] == "dam"]
    for r in sel.itertuples():
        fid = lay.feature({"kind": "Dam", "name": r.name})
        for part in as_lines(r.geometry.intersection(area)):
            xyz = resample(np.column_stack([np.asarray(part.coords)[:, :2],
                                            np.zeros(len(part.coords))]), 8.0)
            xy = xyz[:, :2]
            g = surf(xy[:, 0], xy[:, 1])
            crest = float(np.median(g)) + 2.0
            sweep_box(lay, "dam", xy, np.full(len(xy), crest), np.minimum(g - 3, crest - 2), 8.0,
                      fid)
    return lay


def build_all(structures_gdf, infra_lines, rect, surf: Surface, overview=False) -> list[dict]:
    """All infrastructure layers for one section, exported to glTF axes."""
    pad = 600
    big = (rect[0] - pad, rect[1] - pad, rect[2] + pad, rect[3] + pad)
    st = structures_gdf.cx[big[0]:big[2], big[1]:big[3]].rename(columns={"class": "cls"})
    il = infra_lines.cx[big[0]:big[2], big[1]:big[3]].rename(columns={"class": "cls"})
    if overview:     # county scale (200 m mesh): bigger structures, coarser sampling, no piers
        layers = [bridges(st, rect, surf, 25, spacing=40, piers=False),
                  tunnels(st, rect, surf, 30, spacing=50, sides=6),
                  power(il, rect, surf, ("power_line",), spacing=100)]
    else:
        layers = [bridges(st, rect, surf), tunnels(st, rect, surf), power(il, rect, surf)]
    layers += [aerialways(il, rect, surf), dams(il, rect, surf)]
    return [lay.export(rect[0], rect[3]) for lay in layers if not lay.empty()]
