"""Bridges, tunnels and other built structures in 3D: classification, widths and height
profiles on a terrain surface. Used by 12_topo_layers.py (topo_structures layer, profiles on
the 25 m DEM) and 14_3d_sections.py (meshes, profiles on the 3D mesh surface itself).

Heights (OSM/Overture carry no deck or tunnel levels, so they are modelled):
  bridge  deck runs straight between the two abutments (ground at the ends) and is lifted to
          stay at least DECK_CLEARANCE above the ground under it
  tunnel  roadway runs on an even grade between the two portals and is pushed down so the
          tube keeps TUNNEL_COVER of ground above its crown; the required depth ramps up from
          0 at a portal over the first TUNNEL_RAMP m
"""
import numpy as np
from shapely.geometry import LineString, MultiLineString, Point

DECK_CLEARANCE = 1.5     # m, deck underside above the ground beneath it (short bridges)
DECK_THICKNESS = 1.6     # m
TUNNEL_COVER = 6.0       # m of ground above the tube crown, reached TUNNEL_RAMP m inside
TUNNEL_RAMP = 40.0
SAMPLE = 10.0            # m between profile samples

# carriageway / deck width (m) by Overture class
ROAD_WIDTH = {"motorway": 24, "trunk": 13, "primary": 11, "secondary": 9, "tertiary": 8,
              "residential": 7, "unclassified": 6, "living_street": 6, "service": 5,
              "track": 4, "pedestrian": 5, "cycleway": 3, "footway": 3, "path": 2.5,
              "steps": 2.5, "bridleway": 2.5, "unknown": 6}
RAIL_WIDTH = 6.5         # single track bed with walkways (double track: two features)


def _flags(v) -> str:
    return v if isinstance(v, str) else ""          # missing flags arrive as None or NaN


def rail_status(cls: str, flags: str | None) -> str | None:
    """in use / under construction / disused; None = proposed (not built: not drawn)."""
    f = _flags(flags)
    if "is_under_construction" in f:
        return "under construction"
    if "is_abandoned" in f or "is_disused" in f:
        return "disused"
    if cls == "unknown":
        return None
    return "in use"


def road_status(flags: str | None) -> str:
    return "under construction" if "is_under_construction" in _flags(flags) else "in use"


def structure_kind(flags: str | None) -> str | None:
    f = _flags(flags)
    if "is_indoor" in f:                  # passages inside buildings / car parks
        return None
    if "is_tunnel" in f:
        return "tunnel"
    if "is_bridge" in f:
        return "bridge"
    return None


def width_for(mode: str, cls: str, width_m) -> float:
    if mode == "rail":
        return RAIL_WIDTH
    try:
        w = float(width_m)
        if 2 <= w <= 40:
            return w
    except (TypeError, ValueError):
        pass
    return float(ROAD_WIDTH.get(cls, 6))


def structures_from(pieces):
    """Bridges and tunnels from the split transport pieces (subtype road/rail): one feature per
    physical structure - pieces that join end to end (same kind, mode and status) are merged,
    attributes come from the longest piece."""
    import geopandas as gpd
    from shapely.ops import linemerge, unary_union
    d = pieces.copy()
    is_rail = d["subtype"] == "rail"
    flags = d["rail_flags"].where(is_rail, d["road_flags"])
    d["structure"] = flags.map(structure_kind)
    d["mode"] = np.where(is_rail, "rail", "road")
    d["status"] = [rail_status(c, f) if r else road_status(f)
                   for r, c, f in zip(is_rail, d["class"], flags)]
    d = d[d["structure"].notna() & d["status"].notna()]
    d = d.explode(index_parts=False).reset_index(drop=True)
    d["width_m"] = [width_for(m, c, w) for m, c, w in zip(d["mode"], d["class"], d["width_m"])]
    rows = []
    for key, grp in d.groupby(["structure", "mode", "status"]):
        union = unary_union(list(grp.geometry))
        merged = linemerge(union) if isinstance(union, MultiLineString) else union
        sidx = grp.sindex
        for line in as_lines(merged):
            near = grp.iloc[sidx.query(line.buffer(0.5), predicate="intersects")]
            near = near[near.geometry.within(line.buffer(0.5))]
            if near.empty:
                continue
            best = near.loc[near.length.idxmax()]
            rows.append({"structure": key[0], "mode": key[1], "status": key[2],
                         "class": best["class"], "name": best["name"], "ref": best["ref"],
                         "width_m": float(near["width_m"].max()),
                         "overture_id": best["overture_id"], "geometry": line})
    out = gpd.GeoDataFrame(rows, crs=pieces.crs)
    return out[out.length >= 3].reset_index(drop=True)


# ---------------------------------------------------------------- surface & profiles
class Surface:
    """Terrain heights on a regular grid of nodes (row 0 = north edge), interpolated exactly
    like the 3D mesh: each cell is split into triangles NW-SW-NE and NE-SW-SE."""

    def __init__(self, z: np.ndarray, x0: float, y1: float, step: float):
        self.z, self.x0, self.y1, self.step = z, x0, y1, step

    @classmethod
    def from_raster(cls, path, window_bounds=None):
        import rasterio
        from rasterio.windows import from_bounds
        with rasterio.open(path) as src:
            win = from_bounds(*window_bounds, src.transform) if window_bounds else None
            z = src.read(1, window=win, masked=True).astype("float64").filled(np.nan)
            tr = src.window_transform(win) if win is not None else src.transform
        if np.isnan(z).any():
            z = np.where(np.isnan(z), np.nanmin(z), z)
        return cls(z, tr.c + tr.a / 2, tr.f + tr.e / 2, tr.a)   # pixel centres = nodes

    def __call__(self, x, y):
        ny, nx = self.z.shape
        u = np.clip((np.asarray(x, "float64") - self.x0) / self.step, 0, nx - 1 - 1e-9)
        v = np.clip((self.y1 - np.asarray(y, "float64")) / self.step, 0, ny - 1 - 1e-9)
        i, j = np.floor(v).astype(int), np.floor(u).astype(int)
        fu, fv = u - j, v - i
        za, zb = self.z[i, j], self.z[i, j + 1]            # NW, NE
        zc, zd = self.z[i + 1, j], self.z[i + 1, j + 1]    # SW, SE
        upper = fu + fv <= 1
        return np.where(upper, za + fu * (zb - za) + fv * (zc - za),
                        zd + (1 - fu) * (zc - zd) + (1 - fv) * (zb - zd))


def densify(line: LineString, spacing: float = SAMPLE) -> np.ndarray:
    """Vertices of the line plus points every `spacing` m (keeps bends exact)."""
    xy = np.asarray(line.coords)[:, :2]
    out = [xy[0]]
    for a, b in zip(xy[:-1], xy[1:]):
        n = max(1, int(np.ceil(np.hypot(*(b - a)) / spacing)))
        t = np.arange(1, n + 1)[:, None] / n
        out.extend(a + (b - a) * t)
    return np.asarray(out)


def chainage(xy: np.ndarray) -> np.ndarray:
    return np.concatenate([[0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])


def bridge_profile(ground: np.ndarray, s: np.ndarray) -> np.ndarray:
    """Deck top height along a bridge."""
    L = max(s[-1], 1e-6)
    straight = ground[0] + (ground[-1] - ground[0]) * s / L
    k = np.ones(3) / 3
    g = np.convolve(np.pad(ground, 1, mode="edge"), k, mode="valid") if len(ground) > 2 \
        else ground
    return np.maximum(straight, g) + DECK_CLEARANCE + DECK_THICKNESS


def tunnel_profile(ground: np.ndarray, s: np.ndarray, height: float) -> np.ndarray:
    """Roadway (floor) height along a tunnel of the given clear height."""
    L = max(s[-1], 1e-6)
    grade = ground[0] + (ground[-1] - ground[0]) * s / L
    inside = np.minimum(s, L - s)
    depth = (height + TUNNEL_COVER) * np.clip(inside / TUNNEL_RAMP, 0, 1)
    return np.minimum(grade, ground - depth)


def profile(line: LineString, kind: str, surface: Surface, height: float = 7.0):
    """(xy, s, ground, z) along a structure; z = deck top (bridge) or floor (tunnel)."""
    xy = densify(line)
    s = chainage(xy)
    ground = surface(xy[:, 0], xy[:, 1])
    z = bridge_profile(ground, s) if kind == "bridge" else tunnel_profile(ground, s, height)
    return xy, s, ground, z


def floor_under(xy: np.ndarray, surface: Surface, reach: float | None = None) -> np.ndarray:
    """Valley floor under a bridge: the lowest ground across the line within `reach` m on
    either side (default: 40 % of the bridge length, 12-45 m - a short bridge spans a narrow
    gap). The elevation model is a surface model that records the deck itself, so the ground
    straight under the line is too high."""
    if reach is None:
        reach = float(np.clip(0.4 * chainage(xy)[-1], 12, 45))
    d = np.gradient(xy, axis=0)
    n = np.column_stack([-d[:, 1], d[:, 0]])
    n /= np.maximum(np.hypot(n[:, 0], n[:, 1]), 1e-9)[:, None]
    offs = np.linspace(-reach, reach, 7)
    zz = [surface(xy[:, 0] + n[:, 0] * o, xy[:, 1] + n[:, 1] * o) for o in offs]
    return np.min(zz, axis=0)


def clip_3d(line3d: LineString, area) -> list:
    """Clip a 3D line to an area, interpolating Z at the cut points."""
    full2d = LineString(np.asarray(line3d.coords)[:, :2])
    xyz = np.asarray(line3d.coords)
    s = chainage(xyz[:, :2])
    out = []
    for part in as_lines(full2d.intersection(area)):
        pxy = np.asarray(part.coords)
        ps = np.array([full2d.project(Point(p)) for p in pxy])
        out.append(LineString(np.column_stack([pxy, np.interp(ps, s, xyz[:, 2])])))
    return out


def as_lines(geom):
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, MultiLineString):
        return list(geom.geoms)
    return [geom] if isinstance(geom, LineString) else []
