"""Build the ready-to-open QGIS project (brasov_county.qgz) with grouped, styled layers, an A3
print layout, optional online basemaps, and preview renders in docs/.

Styles are also saved as defaults next to the data (GeoPackage `layer_styles` table for vectors,
`<raster>.qml` side-cars for rasters), so layers look the same when added to any other project.
"""
import sys

from qgis.PyQt.QtCore import QRectF, QSize, Qt
from qgis.PyQt.QtGui import QColor, QFont, QPainter
from qgis.core import (
    Qgis, QgsApplication, QgsCategorizedSymbolRenderer, QgsColorRampShader,
    QgsContrastEnhancement, QgsCoordinateReferenceSystem, QgsFillSymbol, QgsLayerTree,
    QgsLayoutExporter, QgsLayoutItemLabel, QgsLayoutItemLegend, QgsLayoutItemMap,
    QgsLayoutItemPage, QgsLayoutItemPicture, QgsLayoutItemScaleBar, QgsLayoutPoint,
    QgsLayoutSize, QgsLineSymbol, QgsMapRendererParallelJob, QgsMapSettings, QgsMarkerSymbol,
    QgsMapLayerLegendUtils, QgsMultiBandColorRenderer, QgsPalLayerSettings, QgsPalettedRasterRenderer, QgsPrintLayout,
    QgsLegendStyle, QgsProject, QgsProperty, QgsRasterLayer, QgsRasterMinMaxOrigin,
    QgsRasterShader, QgsRectangle,
    QgsReferencedRectangle, QgsRendererCategory, QgsRuleBasedRenderer,
    QgsSingleBandGrayRenderer, QgsSingleBandPseudoColorRenderer, QgsSingleSymbolRenderer,
    QgsTextBufferSettings, QgsTextFormat, QgsUnitTypes, QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)

from catalog import RASTERS, VECTORS
from common import DATA, RASTER, ROOT

app = QgsApplication([], False)
app.initQgis()

DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)
PROJECT_FILE = ROOT / "brasov_county.qgz"

TITLES = {layer: title for _, layer, _, title, _, _ in VECTORS}
RTITLES = {f: title for f, _, title, _, _ in RASTERS}

project = QgsProject.instance()
project.clear()
project.setCrs(QgsCoordinateReferenceSystem("EPSG:3844"))
project.setTitle("Județul Brașov - geospatial base (topography, soil, water)")
project.setFilePathStorage(Qgis.FilePathType.Relative)
project.setFileName(str(PROJECT_FILE))
root = project.layerTreeRoot()


# ---------------------------------------------------------------- helpers
def qc(c: str) -> QColor:
    """'#RRGGBB' or '#RRGGBBAA' (CSS order; Qt would read 8 digits as #AARRGGBB)."""
    if len(c) == 9:
        return QColor(int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16), int(c[7:9], 16))
    return QColor(c)


def pc(c: str) -> str:
    """Colour as a QGIS symbol property string 'r,g,b,a'."""
    q = qc(c)
    return f"{q.red()},{q.green()},{q.blue()},{q.alpha()}"


def vec(stem: str, layer: str) -> QgsVectorLayer:
    lyr = QgsVectorLayer(f"{DATA / (stem + '.gpkg')}|layername={layer}", TITLES[layer], "ogr")
    assert lyr.isValid(), layer
    return lyr


def ras(fname: str) -> QgsRasterLayer:
    lyr = QgsRasterLayer(str(RASTER / fname), RTITLES[fname])
    assert lyr.isValid(), fname
    return lyr


def fill(color, outline="#00000000", width=0.0, style="solid", **kw):
    return QgsFillSymbol.createSimple({"color": pc(color), "outline_color": pc(outline),
                                       "outline_width": str(width), "style": style,
                                       "outline_width_unit": "MM", **kw})


def line(color, width, style="solid", **kw):
    return QgsLineSymbol.createSimple({"line_color": pc(color), "line_width": str(width),
                                       "line_style": style, "capstyle": "round",
                                       "joinstyle": "round", **kw})


def marker(color, size, name="circle", outline="#ffffff", **kw):
    return QgsMarkerSymbol.createSimple({"name": name, "color": pc(color), "size": str(size),
                                         "outline_color": pc(outline), "outline_width": "0.2", **kw})


def categorized(lyr, field, cats, other=None):
    items = [QgsRendererCategory(v, sym, lab) for v, sym, lab in cats]
    if other is not None:
        items.append(QgsRendererCategory(None, other, "other"))
    lyr.setRenderer(QgsCategorizedSymbolRenderer(field, items))


def rules(lyr, rule_list):
    """rule_list: (label, filter, symbol, min_scale_denominator or 0)"""
    root_rule = QgsRuleBasedRenderer.Rule(None)
    for label, flt, sym, minscale in rule_list:
        r = QgsRuleBasedRenderer.Rule(sym, 0, minscale, flt, label)
        root_rule.appendChild(r)
    lyr.setRenderer(QgsRuleBasedRenderer(root_rule))


def labels(lyr, expr, size=8, color="#222222", buffer=1.0, line_placement=False,
           size_expr=None, bold=False, minscale=0, italic=False):
    s = QgsPalLayerSettings()
    s.fieldName = expr
    s.isExpression = True
    fmt = QgsTextFormat()
    font = QFont("Sans Serif")
    font.setBold(bold)
    font.setItalic(italic)
    fmt.setFont(font)
    fmt.setSize(size)
    fmt.setColor(QColor(color))
    if buffer:
        b = QgsTextBufferSettings()
        b.setEnabled(True)
        b.setSize(buffer)
        b.setColor(QColor("#ffffff"))
        fmt.setBuffer(b)
    s.setFormat(fmt)
    if line_placement:
        s.placement = Qgis.LabelPlacement.Line
    if size_expr:
        s.dataDefinedProperties().setProperty(QgsPalLayerSettings.Property.Size,
                                              QgsProperty.fromExpression(size_expr))
    if minscale:
        s.scaleVisibility = True
        s.minimumScale = minscale
        s.maximumScale = 1
    lyr.setLabeling(QgsVectorLayerSimpleLabeling(s))
    lyr.setLabelsEnabled(True)


def ramp(lyr, stops, method="linear", vmin=None, vmax=None, clip=False):
    fn = QgsColorRampShader()
    fn.setColorRampType({"linear": Qgis.ShaderInterpolationMethod.Linear,
                         "discrete": Qgis.ShaderInterpolationMethod.Discrete,
                         "exact": Qgis.ShaderInterpolationMethod.Exact}[method])
    fn.setColorRampItemList([QgsColorRampShader.ColorRampItem(v, qc(c), lab)
                             for v, c, lab in stops])
    fn.setClip(clip)
    sh = QgsRasterShader()
    sh.setRasterShaderFunction(fn)
    r = QgsSingleBandPseudoColorRenderer(lyr.dataProvider(), 1, sh)
    r.setClassificationMin(stops[0][0] if vmin is None else vmin)
    r.setClassificationMax(stops[-1][0] if vmax is None else vmax)
    lyr.setRenderer(r)


def paletted(lyr, classes):
    lyr.setRenderer(QgsPalettedRasterRenderer(
        lyr.dataProvider(), 1,
        [QgsPalettedRasterRenderer.Class(v, qc(c), lab) for v, c, lab in classes]))


def add(group, lyr, visible=True, minscale=0):
    if minscale:
        lyr.setScaleBasedVisibility(True)
        lyr.setMinimumScale(minscale)
        lyr.setMaximumScale(1)
    project.addMapLayer(lyr, False)
    node = group.addLayer(lyr)
    node.setItemVisibilityChecked(visible)
    node.setExpanded(False)
    return lyr


def save_default_style(lyr):
    if isinstance(lyr, QgsVectorLayer):
        try:
            lyr.saveStyleToDatabaseV2("default", "brasov pipeline", True, "")
        except AttributeError:
            lyr.saveStyleToDatabase("default", "brasov pipeline", True, "")
    else:
        lyr.saveNamedStyle(str(RASTER / (lyr.source().rsplit("/", 1)[1].rsplit(".", 1)[0]
                                          + ".qml")))


# ---------------------------------------------------------------- groups (top draws on top)
g_admin = root.addGroup("Administrative")
g_infra = root.addGroup("Transport & infrastructure")
g_bld = root.addGroup("Buildings")
g_water = root.addGroup("Water & hydrology")
g_topo = root.addGroup("Topography")
g_soil = root.addGroup("Soil")
g_land = root.addGroup("Land use & land cover")
g_img = root.addGroup("Imagery")
g_web = root.addGroup("Online basemaps (need internet)")

# ---- Administrative
county = vec("brasov_admin", "admin_county")
county.setRenderer(QgsSingleSymbolRenderer(fill("#00000000", "#1a1a1a", 0.9, style="no")))
uat = vec("brasov_admin", "admin_uat")
uat.setRenderer(QgsSingleSymbolRenderer(fill("#00000000", "#4d4d4d", 0.3, style="no",
                                             outline_style="dash")))
labels(uat, '"name"', size=7.5, color="#3a3a3a", italic=True, minscale=400000)
sett = vec("brasov_admin", "settlements")
categorized(sett, "class", [
    ("city", marker("#1a1a1a", 3.2, "square"), "City"),
    ("town", marker("#1a1a1a", 2.4, "square"), "Town"),
    ("village", marker("#333333", 1.4), "Village"),
    ("hamlet", marker("#555555", 1.0), "Hamlet"),
])
labels(sett, '"name"', size=7, bold=False, minscale=0, size_expr=(
    "CASE WHEN \"class\"='city' THEN 11 WHEN \"class\"='town' THEN 9 "
    "WHEN \"class\"='village' THEN 7 ELSE 6 END"))
ctx = vec("brasov_admin", "admin_counties_context")
ctx.setRenderer(QgsSingleSymbolRenderer(fill("#00000000", "#999999", 0.5, style="no")))
labels(ctx, 'CASE WHEN "iso" <> \'RO-BV\' THEN upper("name") END', size=9, color="#8a8a8a")
for lyr, vis in ((county, True), (uat, True), (sett, True), (ctx, True)):
    add(g_admin, lyr, vis)

# ---- Transport & infrastructure
roads = vec("brasov_landuse_infrastructure", "transport_roads")
rules(roads, [
    ("Motorway", "\"class\" = 'motorway'", line("#e8336b", 1.4), 0),
    ("Trunk / DN (E)", "\"class\" = 'trunk'", line("#f07b3f", 1.1), 0),
    ("Primary", "\"class\" = 'primary'", line("#f4a442", 0.9), 0),
    ("Secondary", "\"class\" = 'secondary'", line("#e6c229", 0.7), 0),
    ("Tertiary", "\"class\" = 'tertiary'", line("#8c8c8c", 0.45), 400000),
    ("Local / residential",
     "\"class\" IN ('residential','unclassified','living_street','unknown')",
     line("#a6a6a6", 0.25), 100000),
    ("Service", "\"class\" = 'service'", line("#bdbdbd", 0.18), 50000),
    ("Track", "\"class\" = 'track'", line("#a0522d", 0.25, "dash"), 100000),
    ("Path / footway",
     "\"class\" IN ('path','footway','steps','pedestrian','cycleway','bridleway')",
     line("#7f7f7f", 0.18, "dot"), 50000),
])
labels(roads, "CASE WHEN \"class\" IN ('motorway','trunk','primary','secondary') "
              "THEN coalesce(\"ref\", \"name\") END", size=6.5, line_placement=True,
       minscale=150000)
rail = vec("brasov_landuse_infrastructure", "transport_rail")
rail.setRenderer(QgsSingleSymbolRenderer(line("#262626", 0.6, "dash")))
infl = vec("brasov_landuse_infrastructure", "infrastructure_lines")
categorized(infl, "class", [
    ("power_line", line("#7b3294", 0.45, "dash dot"), "Power line (HV)"),
    ("minor_line", line("#c2a5cf", 0.25, "dash dot"), "Power line (minor)"),
    ("pipeline", line("#5e3c99", 0.4, "dot"), "Pipeline"),
    ("dam", line("#08306b", 1.0), "Dam"),
    ("chair_lift", line("#000000", 0.3, "dash"), "Chair lift"),
    ("cable_car", line("#000000", 0.3, "dash"), "Cable car"),
    ("platter", line("#000000", 0.2, "dash"), "Ski lift"),
    ("drag_lift", line("#000000", 0.2, "dash"), "Drag lift"),
])
infp = vec("brasov_landuse_infrastructure", "infrastructure_points")
infp.setRenderer(QgsSingleSymbolRenderer(marker("#6a51a3", 1.0)))
infa = vec("brasov_landuse_infrastructure", "infrastructure_areas")
infa.setRenderer(QgsSingleSymbolRenderer(fill("#dadaeb", "#6a51a3", 0.15)))
poi = vec("brasov_landuse_infrastructure", "places_poi")
poi.setRenderer(QgsSingleSymbolRenderer(marker("#e6550d", 1.2)))
add(g_infra, roads)
add(g_infra, rail)
add(g_infra, infl)
add(g_infra, infp, False, 25000)
add(g_infra, infa, False)
add(g_infra, poi, False)

# ---- Buildings
bld = vec("brasov_buildings", "buildings")
bld.setRenderer(QgsSingleSymbolRenderer(fill("#c9a18f", "#8c6a5c", 0.1)))
add(g_bld, bld, True, 60000)

# ---- Water & hydrology
wa = vec("brasov_water", "water_areas")
wa.setRenderer(QgsSingleSymbolRenderer(fill("#a6cee3", "#1f78b4", 0.2)))
wl = vec("brasov_water", "water_lines")
rules(wl, [
    ("River", "\"class\" = 'river'", line("#1f78b4", 0.9), 0),
    ("Canal", "\"class\" = 'canal'", line("#1f78b4", 0.5), 0),
    ("Stream", "\"class\" = 'stream'", line("#4a90d9", 0.35), 400000),
    ("Drain / ditch", "\"class\" IN ('drain','ditch')", line("#6baed6", 0.2), 100000),
])
labels(wl, "CASE WHEN \"class\" IN ('river','canal') THEN \"name\" END", size=7,
       color="#1f4e79", line_placement=True, italic=True, minscale=500000)
wp = vec("brasov_water", "water_points")
wp.setRenderer(QgsSingleSymbolRenderer(marker("#2b8cbe", 1.4)))
st = vec("brasov_water", "hydro_streams")
st.setRenderer(QgsRuleBasedRenderer(QgsRuleBasedRenderer.Rule(None)))
rules(st, [(f"Strahler {o}", f"\"strahler\" = {o}", line("#2171b5", w), ms) for o, w, ms in
           [(1, 0.12, 100000), (2, 0.2, 200000), (3, 0.3, 0), (4, 0.45, 0), (5, 0.65, 0),
            (6, 0.85, 0), (7, 1.2, 0)]])
sb = vec("brasov_water", "hydro_subbasins")
sb.setRenderer(QgsSingleSymbolRenderer(fill("#00000000", "#08519c", 0.3, style="no")))
basins = vec("brasov_water", "hydro_drainage_basins")
basin_colors = ["#8dd3c7", "#ffffb3", "#bebada", "#fb8072", "#80b1d3", "#fdb462", "#b3de69",
                "#fccde5", "#d9d9d9", "#bc80bd"]
import pyogrio  # noqa: E402
bids = sorted(pyogrio.read_dataframe(DATA / "brasov_water.gpkg", layer="hydro_drainage_basins",
                                     read_geometry=False).basin_id.tolist())
categorized(basins, "basin_id", [(b, fill(basin_colors[i % 10], "#555555", 0.3),
                                  f"Basin {b}") for i, b in enumerate(bids)])
basins.setOpacity(0.6)

flood = ras("hydro_flood_susceptibility.tif")
paletted(flood, [(1, "#08306b", "Very high (HAND < 1 m)"), (2, "#2171b5", "High (1-3 m)"),
                 (3, "#6baed6", "Moderate (3-5 m)"), (4, "#c6dbef", "Low (5-10 m)"),
                 (5, "#ffffff00", "Very low (>= 10 m)")])
hand = ras("hydro_hand_m.tif")
ramp(hand, [(0, "#08306b", "0 m"), (2, "#2171b5", "2"), (5, "#6baed6", "5"),
            (10, "#c6dbef", "10"), (30, "#f7fbff", "30+ m")])
twi = ras("hydro_twi.tif")
ramp(twi, [(2, "#8c510a", "dry"), (6, "#dfc27d", ""), (9, "#f6e8c3", ""), (12, "#80cdc1", ""),
           (16, "#01665e", "wet")])
upa = ras("hydro_upstream_area_km2.tif")
ramp(upa, [(1, "#ffffff00", "< 1 km2"), (10, "#c6dbef", "1-10"), (100, "#6baed6", "10-100"),
           (1000, "#2171b5", "100-1000"), (1e9, "#08306b", "> 1000 km2")], method="discrete",
     vmin=0, vmax=12000)
fdir = ras("hydro_flow_dir_d8.tif")
paletted(fdir, [(1, "#e41a1c", "E"), (2, "#ff7f00", "SE"), (4, "#ffff33", "S"),
                (8, "#4daf4a", "SW"), (16, "#377eb8", "W"), (32, "#984ea3", "NW"),
                (64, "#a65628", "N"), (128, "#f781bf", "NE"), (0, "#000000", "no flow")])
gsw_o = ras("water_gsw_occurrence.tif")
ramp(gsw_o, [(1, "#ffcccc", "1 %"), (50, "#8080ff", "50 %"), (100, "#0000ff", "100 %")])
gsw_r = ras("water_gsw_recurrence.tif")
ramp(gsw_r, [(1, "#ff7f27", "1 %"), (50, "#99d9ea", "50 %"), (100, "#0000ff", "100 %")])
gsw_s = ras("water_gsw_seasonality.tif")
ramp(gsw_s, [(1, "#99d9ea", "1 month"), (6, "#5c9be0", ""), (12, "#0000aa", "12 months")])
gsw_t = ras("water_gsw_transitions.tif")
paletted(gsw_t, [(1, "#0000ff", "Permanent"), (2, "#22b14c", "New permanent"),
                 (3, "#d1102d", "Lost permanent"), (4, "#99d9ea", "Seasonal"),
                 (5, "#b5e61d", "New seasonal"), (6, "#e6a1aa", "Lost seasonal"),
                 (7, "#ff7f27", "Seasonal -> permanent"), (8, "#ffc90e", "Permanent -> seasonal"),
                 (9, "#7f7f7f", "Ephemeral permanent"), (10, "#c3c3c3", "Ephemeral seasonal")])
for lyr, vis, ms in ((wp, False, 50000), (wa, True, 0), (wl, True, 0), (st, False, 0),
                     (sb, False, 0), (basins, False, 0), (flood, False, 0), (hand, False, 0),
                     (twi, False, 0), (upa, False, 0), (fdir, False, 0), (gsw_o, False, 0),
                     (gsw_r, False, 0), (gsw_s, False, 0), (gsw_t, False, 0)):
    add(g_water, lyr, vis, ms)

# ---- Topography
ct = vec("brasov_topography", "topo_contours_10m")
rules(ct, [
    ("Index 100 m", "\"kind\" = 'index_100m'", line("#8c6239", 0.3), 300000),
    ("Intermediate 50 m", "\"kind\" = 'intermediate_50m'", line("#a67c52", 0.18), 100000),
    ("10 m", "\"kind\" = 'regular_10m'", line("#c8a882", 0.1), 30000),
])
labels(ct, "CASE WHEN \"kind\" = 'index_100m' THEN \"elev_m\" END", size=6, color="#8c6239",
       line_placement=True, minscale=60000)
pk = vec("brasov_topography", "topo_peaks")
categorized(pk, "class", [
    ("peak", marker("#5a3a1a", 2.0, "triangle", "#ffffff"), "Peak"),
    ("saddle", marker("#8c6239", 1.4, "diamond", "#ffffff"), "Saddle / pass"),
    ("cave_entrance", marker("#000000", 1.4, "half_square"), "Cave entrance"),
], other=marker("#8c6239", 1.0))
labels(pk, "CASE WHEN \"class\" = 'peak' AND \"name\" IS NOT NULL THEN \"name\" || "
           "coalesce('\\n' || \"elevation\" || ' m', '') END", size=6.5, color="#4d2f12",
       minscale=250000)
landn = vec("brasov_topography", "land_natural_areas")
categorized(landn, "subtype", [
    ("forest", fill("#9bc48f", "#00000000"), "Forest"),
    ("grass", fill("#d9ecb4", "#00000000"), "Grassland"),
    ("shrub", fill("#c3d69b", "#00000000"), "Scrub / heath"),
    ("wetland", fill("#b8e0d2", "#00000000"), "Wetland"),
    ("rock", fill("#d9d9d9", "#00000000"), "Rock / scree"),
])
lnl = vec("brasov_topography", "land_natural_lines")
lnl.setRenderer(QgsSingleSymbolRenderer(line("#6b4423", 0.3)))

hs = ras("topo_hillshade.tif")
g = QgsSingleBandGrayRenderer(hs.dataProvider(), 1)
ce = QgsContrastEnhancement(Qgis.DataType.Byte)
ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.ContrastEnhancementAlgorithm.StretchToMinimumMaximum)
ce.setMinimumValue(40)
ce.setMaximumValue(255)
g.setContrastEnhancement(ce)
hs.setRenderer(g)
hs.setBlendMode(QPainter.CompositionMode.CompositionMode_Multiply)
hs.setOpacity(0.7)
dem = ras("topo_dem_25m.tif")
ramp(dem, [(400, "#5e9e4f", "400 m"), (550, "#9cc47a", ""), (700, "#d6e3a0", "700 m"),
           (900, "#efe2a2", ""), (1100, "#e3c27f", "1100 m"), (1400, "#c99a62", ""),
           (1700, "#a9784e", "1700 m"), (2000, "#9c8b7e", ""), (2300, "#cfc8c2", "2300 m"),
           (2550, "#ffffff", "2550 m")])
slc = ras("topo_slope_classes.tif")
paletted(slc, [(1, "#1a9850", "< 2 %"), (2, "#66bd63", "2-5 %"), (3, "#a6d96a", "5-10 %"),
               (4, "#d9ef8b", "10-15 %"), (5, "#fee08b", "15-25 %"), (6, "#fdae61", "25-35 %"),
               (7, "#f46d43", "35-50 %"), (8, "#d73027", ">= 50 %")])
sld = ras("topo_slope_deg.tif")
ramp(sld, [(0, "#ffffcc", "0°"), (10, "#fed976", "10°"), (20, "#fd8d3c", "20°"),
           (30, "#e31a1c", "30°"), (45, "#800026", "45°+")])
asp = ras("topo_aspect_deg.tif")
ramp(asp, [(0, "#e41a1c", "N"), (90, "#ffff33", "E"), (180, "#4daf4a", "S"),
           (270, "#377eb8", "W"), (360, "#e41a1c", "N")])
tri = ras("topo_ruggedness_tri.tif")
ramp(tri, [(0, "#f7f7f7", "smooth"), (5, "#cccccc", ""), (15, "#969696", ""),
           (40, "#252525", "rugged")])
gm = ras("topo_landforms_geomorphons.tif")
paletted(gm, [(1, "#dcdcdc", "Flat"), (2, "#380000", "Peak"), (3, "#c80000", "Ridge"),
              (4, "#ff5014", "Shoulder"), (5, "#fad23c", "Spur"), (6, "#ffff3c", "Slope"),
              (7, "#b4e614", "Hollow"), (8, "#3cfa96", "Footslope"), (9, "#0000ff", "Valley"),
              (10, "#000038", "Pit")])
for lyr, vis in ((ct, True), (pk, True), (lnl, False), (landn, False), (gm, False),
                 (slc, False), (sld, False), (asp, False), (tri, False), (hs, True), (dem, True)):
    add(g_topo, lyr, vis)

# ---- Soil
soil = vec("brasov_soil", "soil_hwsd_units")
soil_colors = {
    "Dystric Cambisols": "#e0a96d", "Eutric Cambisols": "#f3c98b", "Retic Stagnosols": "#9ecae1",
    "Luvic Stagnosols": "#6baed6", "Mollic Stagnosols": "#4292c6", "Rendzic Leptosols": "#bdbdbd",
    "Umbric Leptosols": "#969696", "Gleyic Phaeozems": "#8c6d31", "Haplic Phaeozems": "#bd9e39",
    "Luvic Phaeozems": "#e7ba52", "Eutric Fluvisols": "#7fcdbb", "Haplic Luvisols": "#d6616b",
    "Entic Podzols": "#a55194", "Albic Podzols": "#ce6dbd", "Calcaric Regosols": "#f7f4a3",
    "Technosols": "#636363",
}
present = pyogrio.read_dataframe(DATA / "brasov_soil.gpkg", layer="soil_hwsd_units",
                                 read_geometry=False).dominant_wrb.dropna().unique()
categorized(soil, "dominant_wrb", [(n, fill(soil_colors.get(n, "#cccccc"), "#555555", 0.2), n)
                                   for n in sorted(present)])
soil.setOpacity(0.85)
hsg = vec("brasov_soil", "soil_hwsd_units")
hsg.setName("Hydrologic soil group (A-D)")
categorized(hsg, "hydrologic_soil_group", [
    ("A", fill("#a1d99b", "#555555", 0.2), "A - high infiltration"),
    ("B", fill("#fed976", "#555555", 0.2), "B - moderate"),
    ("C", fill("#fd8d3c", "#555555", 0.2), "C - slow"),
    ("D", fill("#bd0026", "#555555", 0.2), "D - very slow / shallow / wet"),
], other=fill("#d9d9d9", "#555555", 0.2))
hsg.setOpacity(0.8)
add(g_soil, soil, False)
add(g_soil, hsg, False)

# ---- Land use & land cover
prot = vec("brasov_landuse_infrastructure", "protected_areas")
rules(prot, [
    ("Nature reserve / park", "\"class\" <> 'protected'",
     fill("#1a9850", "#1a9850", 0.6, style="b_diagonal"), 0),
    ("Protection zone (e.g. water wells)", "\"class\" = 'protected'",
     fill("#3182bd", "#3182bd", 0.3, style="f_diagonal"), 0),
])
lu = vec("brasov_landuse_infrastructure", "landuse")
categorized(lu, "subtype", [
    ("residential", fill("#e8c4b8"), "Residential"), ("developed", fill("#c9b3d6"), "Industrial / commercial"),
    ("agriculture", fill("#f4efc1"), "Agriculture"), ("horticulture", fill("#d4e8a5"), "Horticulture / orchards"),
    ("managed", fill("#cfe8b5"), "Managed grass"), ("park", fill("#b5e3a5"), "Parks"),
    ("recreation", fill("#a8dcc4"), "Recreation / sport"), ("cemetery", fill("#aac9a8"), "Cemetery"),
    ("education", fill("#f2dda3"), "Education"), ("military", fill("#f2a7a7"), "Military"),
    ("resource_extraction", fill("#c8b29a"), "Quarry"), ("construction", fill("#d9d0c1"), "Construction"),
    ("pedestrian", fill("#e0e0e0"), "Pedestrian"),
], other=fill("#eeeeee"))
wc = ras("landcover_worldcover_10m.tif")
paletted(wc, [(10, "#006400", "Tree cover"), (20, "#ffbb22", "Shrubland"),
              (30, "#ffff4c", "Grassland"), (40, "#f096ff", "Cropland"),
              (50, "#fa0000", "Built-up"), (60, "#b4b4b4", "Bare / sparse vegetation"),
              (70, "#f0f0f0", "Snow and ice"), (80, "#0064c8", "Permanent water"),
              (90, "#0096a0", "Herbaceous wetland"), (100, "#fae6a0", "Moss and lichen")])
add(g_land, prot, True)
add(g_land, lu, False)
add(g_land, wc, False)

# ---- Imagery
img = ras("imagery_sentinel2_truecolor_10m.tif")
mb = QgsMultiBandColorRenderer(img.dataProvider(), 1, 2, 3)
mb.setAlphaBand(4)  # GDAL per-dataset mask, exposed by QGIS as band 4
img.setRenderer(mb)
img.setContrastEnhancement(QgsContrastEnhancement.ContrastEnhancementAlgorithm.StretchToMinimumMaximum,
                           QgsRasterMinMaxOrigin.Limits.CumulativeCut)
add(g_img, img, False)

# ---- Online basemaps
WEB = [("OpenStreetMap", "https://tile.openstreetmap.org/{z}/{x}/{y}.png", 19),
       ("OpenTopoMap", "https://tile.opentopomap.org/{z}/{x}/{y}.png", 17),
       ("Esri World Imagery",
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/"
        "{z}/{y}/{x}", 19)]
for name, url, zmax in WEB:
    uri = f"type=xyz&url={url.replace('{', '%7B').replace('}', '%7D')}&zmax={zmax}&zmin=0"
    lyr = QgsRasterLayer(uri, name, "wms")
    if lyr.isValid():
        add(g_web, lyr, False)
    else:
        print("skipping basemap (provider unavailable):", name, file=sys.stderr)

for grp in (g_infra, g_bld, g_soil, g_land, g_img, g_web):
    grp.setExpanded(False)

# ---------------------------------------------------------------- default styles + view
for lyr in project.mapLayers().values():
    if lyr.providerType() in ("ogr", "gdal"):
        save_default_style(lyr)

ext = county.extent()
ext.grow(3000)
project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(ext, project.crs()))

# ---------------------------------------------------------------- A3 print layout
LEGEND_TITLES = {county.id(): "County boundary", uat.id(): "UAT boundaries",
                 sett.id(): "Settlements", wl.id(): "Watercourses (OSM)",
                 wa.id(): "Water bodies (OSM)", st.id(): "Streams (DEM, Strahler order)",
                 prot.id(): "Protected areas", ct.id(): "Contours", pk.id(): "Terrain points",
                 dem.id(): "Elevation (m)", soil.id(): "Dominant soil (WRB 2022)",
                 wc.id(): "Land cover 2021", flood.id(): "Flood susceptibility (HAND)",
                 roads.id(): "Roads", rail.id(): "Railways"}

def make_layout(name, title, layers_visible):
    lay = QgsPrintLayout(project)
    lay.initializeDefaults()
    lay.setName(name)
    lay.pageCollection().page(0).setPageSize("A3", QgsLayoutItemPage.Orientation.Landscape)
    mp = QgsLayoutItemMap(lay)
    mp.attemptSetSceneRect(QRectF(10, 22, 320, 265))
    mp.setCrs(project.crs())
    mp.setExtent(ext)
    mp.setLayers(layers_visible)
    mp.setKeepLayerSet(True)
    mp.setFrameEnabled(True)
    lay.addLayoutItem(mp)
    t = QgsLayoutItemLabel(lay)
    t.setText(title)
    tf = QgsTextFormat()
    tf.setFont(QFont("Sans Serif"))
    tf.setSize(20)
    t.setTextFormat(tf)
    t.attemptMove(QgsLayoutPoint(10, 6))
    t.attemptResize(QgsLayoutSize(320, 14))
    lay.addLayoutItem(t)
    lg = QgsLayoutItemLegend(lay)
    lg.setLinkedMap(mp)
    lg.setAutoUpdateModel(False)
    lt = lg.model().rootGroup()
    lt.clear()
    for lyr in layers_visible:
        if lyr is hs:
            continue  # hillshade needs no legend entry
        node = lt.addLayer(lyr)
        node.setCustomProperty("legend/title-label", LEGEND_TITLES.get(lyr.id(), lyr.name()))
        if isinstance(lyr, QgsRasterLayer):
            nodes = lg.model().layerLegendNodes(node)
            keep = [i for i, n in enumerate(nodes)
                    if not str(n.data(Qt.ItemDataRole.DisplayRole) or "").startswith("Band ")]
            QgsMapLayerLegendUtils.setLegendNodeOrder(node, keep)
            lg.model().refreshLayerLegend(node)
    for style, size in ((QgsLegendStyle.Style.Title, 11), (QgsLegendStyle.Style.Group, 8),
                        (QgsLegendStyle.Style.Subgroup, 7.5),
                        (QgsLegendStyle.Style.SymbolLabel, 6.5)):
        ls = lg.style(style)
        tf = ls.textFormat()
        tf.setSize(size)
        ls.setTextFormat(tf)
        lg.setStyle(style, ls)
    lg.setSymbolHeight(3)
    lg.setSymbolWidth(6)
    lg.setTitle("Legend")
    lg.attemptMove(QgsLayoutPoint(335, 22))
    lg.attemptResize(QgsLayoutSize(80, 230))
    lg.setResizeToContents(False)
    lay.addLayoutItem(lg)
    sbar = QgsLayoutItemScaleBar(lay)
    sbar.setStyle("Single Box")
    sbar.setLinkedMap(mp)
    sbar.applyDefaultSize(QgsUnitTypes.DistanceUnit.DistanceKilometers)
    sbar.setUnits(QgsUnitTypes.DistanceUnit.DistanceKilometers)
    sbar.setUnitLabel("km")
    sbar.setNumberOfSegments(4)
    sbar.setUnitsPerSegment(5)
    sbar.attemptMove(QgsLayoutPoint(14, 275))
    lay.addLayoutItem(sbar)
    na = QgsLayoutItemPicture(lay)
    na.setPicturePath(QgsApplication.svgPaths()[0] + "/arrows/NorthArrow_02.svg")
    na.attemptMove(QgsLayoutPoint(312, 26))
    na.attemptResize(QgsLayoutSize(14, 14))
    lay.addLayoutItem(na)
    note = QgsLayoutItemLabel(lay)
    note.setText("EPSG:3844 Stereo 70 · Copernicus DEM GLO-30 · © OpenStreetMap contributors / "
                 "Overture Maps · ESA WorldCover · JRC GSW · FAO/IIASA HWSD v2 · geoBoundaries "
                 "(ANCPI)")
    nf = QgsTextFormat()
    nf.setFont(QFont("Sans Serif"))
    nf.setSize(7)
    note.setTextFormat(nf)
    note.attemptMove(QgsLayoutPoint(120, 289))
    note.attemptResize(QgsLayoutSize(295, 6))
    lay.addLayoutItem(note)
    project.layoutManager().addLayout(lay)
    return lay


overview_layers = [county, uat, sett, roads, rail, wa, wl, prot, ct, pk, hs, dem]
lay1 = make_layout("A3 - Overview (relief, water, roads)",
                   "Județul Brașov - relief, water and transport", overview_layers)
lay2 = make_layout("A3 - Water & flood susceptibility",
                   "Județul Brașov - hydrology and flood susceptibility (HAND)",
                   [county, uat, sett, wl, wa, st, flood, hs])
lay3 = make_layout("A3 - Soils (HWSD v2)", "Județul Brașov - soils (WRB 2022, HWSD v2)",
                   [county, uat, sett, wl, soil, hs])
lay4 = make_layout("A3 - Land cover (ESA WorldCover 2021)",
                   "Județul Brașov - land cover 2021", [county, uat, sett, wc])

ok = project.write(str(PROJECT_FILE))
print("project written:", ok, PROJECT_FILE)

# ---------------------------------------------------------------- previews
for lay, fn in ((lay1, "overview"), (lay2, "water"), (lay3, "soil"), (lay4, "landcover")):
    exp = QgsLayoutExporter(lay)
    s = QgsLayoutExporter.ImageExportSettings()
    s.dpi = 60
    res = exp.exportToImage(str(DOCS / f"layout_{fn}.png"), s)
    print("layout", fn, res)


def render(layers, fn, extent=ext, size=(1800, 1400)):
    ms = QgsMapSettings()
    ms.setLayers(layers)
    ms.setDestinationCrs(project.crs())
    ms.setExtent(extent)
    ms.setOutputSize(QSize(*size))
    ms.setBackgroundColor(QColor("white"))
    job = QgsMapRendererParallelJob(ms)
    job.start()
    job.waitForFinished()
    job.renderedImage().save(str(DOCS / fn))


# zoomed detail around Brașov city to check large-scale symbology
city = QgsRectangle(538000, 450000, 556000, 462000)
render([uat, sett, roads, rail, bld, wa, wl, ct, pk, hs, dem], "detail_brasov_city.png", city,
       (1800, 1200))
render([county, uat, img], "imagery.png")
app.exitQgis()
