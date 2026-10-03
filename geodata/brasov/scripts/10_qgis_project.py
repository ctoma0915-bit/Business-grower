"""Build the ready-to-open QGIS project (brasov_county.qgz) with grouped, styled layers, an A3
print layout, optional online basemaps, and preview renders in docs/.

With `--single <file.gpkg>` (called by 11_single_gpkg.py) every layer is read from that one
GeoPackage instead, and the project is stored inside it rather than written as a .qgz.

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
    QgsVectorLayerSimpleLabeling, QgsSimpleLineSymbolLayer, QgsGeometryGeneratorSymbolLayer,
    QgsRuleBasedLabeling, QgsHillshadeRenderer, QgsRasterDataProvider, QgsMapThemeCollection,
    QgsLayerTreeModel, QgsCoordinateTransform, QgsPointXY,
)

from catalog import RASTERS, VECTORS
from common import DATA, RASTER, ROOT

app = QgsApplication([], False)
app.initQgis()

DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)
PROJECT_FILE = ROOT / "brasov_county.qgz"
SINGLE = sys.argv[sys.argv.index("--single") + 1] if "--single" in sys.argv else None
PROJECT_NAME = "Brasov County"
PROJECT_URI = f"geopackage:{SINGLE}?projectName={PROJECT_NAME}" if SINGLE else str(PROJECT_FILE)

TITLES = {layer: title for _, layer, _, title, _, _ in VECTORS}
RTITLES = {f: title for f, _, title, _, _ in RASTERS}

project = QgsProject.instance()
project.clear()
project.setCrs(QgsCoordinateReferenceSystem("EPSG:3844"))
project.setTitle("Județul Brașov - geospatial base (topography, soil, water)")
project.setFilePathStorage(Qgis.FilePathType.Relative)
project.setFileName(PROJECT_URI)
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
    path = SINGLE or DATA / (stem + ".gpkg")
    lyr = QgsVectorLayer(f"{path}|layername={layer}", TITLES[layer], "ogr")
    assert lyr.isValid(), layer
    return lyr


def ras(fname: str) -> QgsRasterLayer:
    src = f"GPKG:{SINGLE}:{fname.rsplit('.', 1)[0]}" if SINGLE else str(RASTER / fname)
    lyr = QgsRasterLayer(src, RTITLES[fname])
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


def rules(lyr, rule_list, symbol_levels=False):
    """rule_list: (label, filter, symbol, zoomed-out limit [, zoomed-in limit]) as scale
    denominators, 0 = no limit. E.g. (.., 15000) shows a rule only at 1:15,000 and closer."""
    root_rule = QgsRuleBasedRenderer.Rule(None)
    for item in rule_list:
        label, flt, sym, minscale = item[:4]
        maxscale = item[4] if len(item) > 4 else 0
        root_rule.appendChild(QgsRuleBasedRenderer.Rule(sym, maxscale, minscale, flt, label))
    r = QgsRuleBasedRenderer(root_rule)
    r.setUsingSymbolLevels(symbol_levels)
    lyr.setRenderer(r)
    return r


M_UNIT = Qgis.RenderUnit.MetersInMapUnits


def road_symbol(fill_c, case_c, width_m, fill_pass, dash=False):
    """Large-scale road drawn at its real width (metres on the ground) with a 1 m casing.
    All casings render in pass 0 so junctions merge cleanly (needs symbol levels)."""
    sym = QgsLineSymbol()
    sym.deleteSymbolLayer(0)
    parts = [(case_c, width_m + 2.0, 0)] if case_c else []
    for color, w, rpass in parts + [(fill_c, width_m, fill_pass)]:
        sl = QgsSimpleLineSymbolLayer(qc(color), w)
        sl.setWidthUnit(M_UNIT)
        sl.setPenCapStyle(Qt.PenCapStyle.RoundCap)
        sl.setPenJoinStyle(Qt.PenJoinStyle.RoundJoin)
        sl.setRenderingPass(rpass)
        if dash and rpass == fill_pass:
            sl.setPenStyle(Qt.PenStyle.DashLine)
        sym.appendSymbolLayer(sl)
    return sym


def smoothed(sym, iterations=2):
    """Render a line symbol along a Chaikin-smoothed copy of the geometry (display only, the
    stored data is unchanged) - removes the 25 m grid stair-steps when zoomed in."""
    gg = QgsGeometryGeneratorSymbolLayer.create(
        {"geometryModifier": f"smooth($geometry, {iterations}, 0.25)", "SymbolType": "Line"})
    gg.setSubSymbol(sym)
    out = QgsLineSymbol()
    out.deleteSymbolLayer(0)
    out.appendSymbolLayer(gg)
    return out


def smooth_raster(lyr, zoomed_in="cubic"):
    """Interpolate continuous rasters when zoomed in past their native cell size, so they
    render as smooth surfaces instead of visible 25 m squares."""
    m = QgsRasterDataProvider.ResamplingMethod
    # Resample the *data* (provider stage), not the rendered image: the live hillshade needs
    # interpolated elevations, and the setting must live on the layer to survive save/load.
    lyr.setResamplingStage(Qgis.RasterResamplingStage.Provider)
    p = lyr.dataProvider()
    p.enableProviderResampling(True)
    p.setZoomedInResamplingMethod({"cubic": m.Cubic, "bilinear": m.Bilinear}[zoomed_in])
    p.setZoomedOutResamplingMethod(m.Average)
    p.setMaxOversampling(2.0)


def label_settings(expr, size=8, color="#222222", buffer=1.0, line_placement=False,
                   size_expr=None, bold=False, italic=False):
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
    return s


def labels(lyr, expr, size=8, color="#222222", buffer=1.0, line_placement=False,
           size_expr=None, bold=False, minscale=0, italic=False):
    s = label_settings(expr, size, color, buffer, line_placement, size_expr, bold, italic)
    if minscale:
        s.scaleVisibility = True
        s.minimumScale = minscale
        s.maximumScale = 1
    lyr.setLabeling(QgsVectorLayerSimpleLabeling(s))
    lyr.setLabelsEnabled(True)


def rule_labels(lyr, items):
    """items: (QgsPalLayerSettings, zoomed-out limit, zoomed-in limit, filter expression)."""
    root_rule = QgsRuleBasedLabeling.Rule(None)
    for st_, mins, maxs, flt in items:
        root_rule.appendChild(QgsRuleBasedLabeling.Rule(st_, maxs, mins, flt or ""))
    lyr.setLabeling(QgsRuleBasedLabeling(root_rule))
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


def add(group, lyr, visible=True, minscale=0, maxscale=0):
    """minscale = zoomed-out limit, maxscale = zoomed-in limit (scale denominators, 0 = none)."""
    if minscale or maxscale:
        lyr.setScaleBasedVisibility(True)
        lyr.setMinimumScale(minscale)
        lyr.setMaximumScale(maxscale or 1)
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
    elif not SINGLE:  # raster styles travel in the project when everything is one GeoPackage
        lyr.saveNamedStyle(str(RASTER / (lyr.source().rsplit("/", 1)[1].rsplit(".", 1)[0]
                                          + ".qml")))


# ---------------------------------------------------------------- groups (top draws on top)
g_admin = root.addGroup("Administrative")
g_infra = root.addGroup("Transport & infrastructure")
g_bld = root.addGroup("Buildings")
g_water = root.addGroup("Water & hydrology")
g_terr = root.addGroup("Contours & terrain points")
g_land = root.addGroup("Land use, land cover & trees")
g_soil = root.addGroup("Soil")
g_relief = root.addGroup("Relief & terrain analysis")
g_img = root.addGroup("Imagery")
g_web = root.addGroup("Online basemaps (need internet)")

# Close-zoom threshold: below this scale denominator the "street map" symbology takes over.
DETAIL = 15000

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
MINOR = "('residential','unclassified','living_street','unknown')"
PATHS = "('path','footway','steps','cycleway','bridleway')"
roads = vec("brasov_landuse_infrastructure", "transport_roads")
rules(roads, [
    # county / town scale: lines in mm
    ("Motorway", "\"class\" = 'motorway'", line("#e8336b", 1.4), 0, DETAIL),
    ("Trunk / DN (E)", "\"class\" = 'trunk'", line("#f07b3f", 1.1), 0, DETAIL),
    ("Primary", "\"class\" = 'primary'", line("#f4a442", 0.9), 0, DETAIL),
    ("Secondary", "\"class\" = 'secondary'", line("#e6c229", 0.7), 0, DETAIL),
    ("Tertiary", "\"class\" = 'tertiary'", line("#8c8c8c", 0.45), 400000, DETAIL),
    ("Local / residential", f"\"class\" IN {MINOR}", line("#a6a6a6", 0.25), 100000, DETAIL),
    ("Service", "\"class\" = 'service'", line("#bdbdbd", 0.18), 50000, DETAIL),
    ("Track", "\"class\" = 'track'", line("#a0522d", 0.25, "dash"), 100000, DETAIL),
    ("Path / footway", f"\"class\" IN {PATHS} OR \"class\" = 'pedestrian'",
     line("#7f7f7f", 0.18, "dot"), 50000, DETAIL),
    # street scale (1:15,000 and closer): real carriageway widths with casings
    ("Motorway (detail)", "\"class\" = 'motorway'",
     road_symbol("#e892a2", "#c0335f", 20, 8), DETAIL),
    ("Trunk (detail)", "\"class\" = 'trunk'", road_symbol("#f9b29c", "#c84e2f", 16, 7), DETAIL),
    ("Primary (detail)", "\"class\" = 'primary'", road_symbol("#fcd6a4", "#a06b00", 14, 6),
     DETAIL),
    ("Secondary (detail)", "\"class\" = 'secondary'",
     road_symbol("#f7fabf", "#707d05", 12, 5), DETAIL),
    ("Tertiary (detail)", "\"class\" = 'tertiary'", road_symbol("#ffffff", "#8f8f8f", 10, 4),
     DETAIL),
    ("Street (detail)", f"\"class\" IN {MINOR}", road_symbol("#ffffff", "#b0b0b0", 7, 3), DETAIL),
    ("Pedestrian street (detail)", "\"class\" = 'pedestrian'",
     road_symbol("#e4e4ee", "#a8a8b8", 6, 3), DETAIL),
    ("Service road (detail)", "\"class\" = 'service'", road_symbol("#ffffff", "#c2c2c2", 4, 2),
     DETAIL),
    ("Track (detail)", "\"class\" = 'track'", road_symbol("#a07a2c", None, 2.5, 1, dash=True),
     DETAIL),
    ("Cycleway (detail)", "\"class\" = 'cycleway'", road_symbol("#2b6ff2", None, 1.2, 1, dash=True),
     DETAIL),
    ("Footway / path / steps (detail)", "\"class\" IN ('path','footway','steps','bridleway')",
     road_symbol("#e8705f", None, 1.2, 1, dash=True), DETAIL),
], symbol_levels=True)
rule_labels(roads, [
    (label_settings("coalesce(\"ref\", \"name\")", size=6.5, line_placement=True), 150000, DETAIL,
     "\"class\" IN ('motorway','trunk','primary','secondary')"),
    (label_settings("\"name\"", size=7.5, color="#2b2b2b", line_placement=True, buffer=1.2), DETAIL,
     0, "\"name\" IS NOT NULL AND \"class\" NOT IN ('track')"),
    (label_settings("\"ref\"", size=7, color="#5a3200", line_placement=True, bold=True), DETAIL,
     0, "\"ref\" IS NOT NULL AND \"class\" IN ('motorway','trunk','primary','secondary')"),
])
rail = vec("brasov_landuse_infrastructure", "transport_rail")
rail_detail = QgsLineSymbol()
rail_detail.deleteSymbolLayer(0)
for color, w, dashed in (("#4d4d4d", 0.9, False), ("#ffffff", 0.5, True)):
    sl = QgsSimpleLineSymbolLayer(qc(color), w)
    if dashed:
        sl.setUseCustomDashPattern(True)
        sl.setCustomDashVector([3.0, 3.0])
    rail_detail.appendSymbolLayer(sl)
rules(rail, [("Railway", "TRUE", line("#262626", 0.6, "dash"), 0, 25000),
             ("Railway (detail)", "TRUE", rail_detail, 25000)])
infl = vec("brasov_landuse_infrastructure", "infrastructure_lines")
rules(infl, [
    ("Power line (HV)", "\"class\" = 'power_line'", line("#7b3294", 0.45, "dash dot"), 0),
    ("Power line (minor)", "\"class\" = 'minor_line'", line("#c2a5cf", 0.25, "dash dot"), 100000),
    ("Pipeline", "\"class\" = 'pipeline'", line("#5e3c99", 0.4, "dot"), 0),
    ("Dam", "\"class\" = 'dam'", line("#08306b", 1.0), 0),
    ("Aerialway / ski lift", "\"class\" IN ('chair_lift','cable_car','platter','drag_lift',"
     "'gondola','t-bar','j-bar','mixed_lift')", line("#000000", 0.3, "dash"), 0),
    ("City wall", "\"class\" = 'city_wall'", line("#6b4423", 0.9), 25000),
    ("Wall / retaining wall", "\"class\" IN ('wall','retaining_wall')", line("#5b5b5b", 0.3),
     DETAIL // 3),
    ("Fence", "\"class\" = 'fence'", line("#8c8c8c", 0.15, "dash"), DETAIL // 3),
    ("Hedge", "\"class\" = 'hedge'", line("#6f9a5c", 0.5), DETAIL // 3),
])
infp = vec("brasov_landuse_infrastructure", "infrastructure_points")
rules(infp, [
    ("Power tower / pole", "\"class\" IN ('power_tower','power_pole')",
     marker("#3d3d3d", 0.9, "square", "#ffffff"), 25000),
    ("Transformer / substation", "\"class\" IN ('transformer','substation')",
     marker("#7b3294", 1.2, "square"), DETAIL),
    ("Public transport stop", "\"class\" IN ('bus_stop','stop_position','stop','tram_stop')",
     marker("#1f6fd0", 1.3, "circle"), DETAIL // 2),
    ("Fire hydrant", "\"class\" = 'fire_hydrant'", marker("#d7301f", 0.9, "circle"), DETAIL // 3),
    ("Viewpoint", "\"class\" = 'viewpoint'", marker("#8c510a", 1.6, "star"), 50000),
])
infa = vec("brasov_landuse_infrastructure", "infrastructure_areas")
rules(infa, [
    ("Parking", "\"class\" IN ('parking','parking_space')", fill("#ececec", "#b8b8b8", 0.15),
     DETAIL),
    ("Power plant / substation / generator", "\"class\" IN ('plant','substation','generator')",
     fill("#e0d0e8", "#7b3294", 0.2), 50000),
    ("Other infrastructure area", "\"class\" NOT IN ('parking','parking_space','plant',"
     "'substation','generator')", fill("#dadaeb", "#6a51a3", 0.15), DETAIL),
])
labels(infa, "CASE WHEN \"class\" = 'parking' THEN 'P' END", size=6.5, color="#2b6ff2",
       bold=True, minscale=5000, buffer=0)
poi = vec("brasov_landuse_infrastructure", "places_poi")
POI = [
    ("Food & drink", "\"category\" IN ('restaurant','casual_eatery','bar','coffee_shop',"
     "'fast_food_restaurant','cafe','pub','pizza_restaurant','bakery')", "#e6550d", "circle"),
    ("Lodging", "\"category\" IN ('hotel','lodging','bed_and_breakfast','private_lodging',"
     "'hostel','motel','campground','resort')", "#2171b5", "square"),
    ("Health", "\"category\" LIKE '%clinic%' OR \"category\" LIKE '%hospital%' OR \"category\" "
     "LIKE '%pharmacy%' OR \"category\" LIKE '%doctor%' OR \"category\" LIKE '%medical%'",
     "#de2d26", "cross_fill"),
    ("Education", "\"category\" IN ('place_of_learning','education','school','kindergarten',"
     "'college_university','preschool','elementary_school','high_school')", "#756bb1",
     "triangle"),
    ("Worship", "\"category\" LIKE '%worship%' OR \"category\" = 'religious_organization'",
     "#525252", "cross2"),
    ("Shops", "\"category\" LIKE '%store%' OR \"category\" IN ('shopping','supermarket',"
     "'shopping_center')", "#31a354", "circle"),
    ("Heritage & tourism", "\"category\" IN ('historic_site','museum','monument',"
     "'tourist_attraction','castle','landmark_and_historical_building')", "#8c510a", "star"),
    ("Public services", "\"category\" IN ('government_office','post_office','police_station',"
     "'fire_station','town_hall','library','social_or_community_service')", "#08519c",
     "diamond"),
]
poi_rules = [(lab, flt, marker(c, 2.0, shp, "#ffffff"), 10000) for lab, flt, c, shp in POI]
poi_rules.append(("Other place", "ELSE", marker("#969696", 1.2), 5000))
root_rule = QgsRuleBasedRenderer.Rule(None)
for lab, flt, sym, mins in poi_rules:
    r = QgsRuleBasedRenderer.Rule(sym, 0, mins, "" if flt == "ELSE" else flt, lab)
    if flt == "ELSE":
        r.setIsElse(True)
    root_rule.appendChild(r)
poi.setRenderer(QgsRuleBasedRenderer(root_rule))
labels(poi, "\"name\"", size=6.5, color="#4a4a4a", italic=True, minscale=4000)
add(g_infra, roads)
add(g_infra, rail)
add(g_infra, infl)
add(g_infra, infp, True, 25000)
add(g_infra, infa, True, 50000)
add(g_infra, poi, True, 10000)

# ---- Buildings
bld = vec("brasov_buildings", "buildings")
BLD_OUT = "#8c6f60"
categorized(bld, "subtype", [
    ("residential", fill("#d9c3b5", BLD_OUT, 0.1), "Residential"),
    ("commercial", fill("#e9c9a3", BLD_OUT, 0.1), "Commercial"),
    ("industrial", fill("#cfc3db", "#7d6e8f", 0.1), "Industrial"),
    ("agricultural", fill("#dfd6bf", "#8f8466", 0.1), "Agricultural"),
    ("outbuilding", fill("#e2d8ce", BLD_OUT, 0.1), "Outbuilding / garage"),
    ("religious", fill("#c49c94", "#6e4a43", 0.15), "Religious"),
    ("education", fill("#f0c9a0", "#9c6a3a", 0.15), "Education"),
    ("civic", fill("#e6b8b8", "#8f5050", 0.15), "Civic / public"),
    ("medical", fill("#f2b6b6", "#a33a3a", 0.15), "Medical"),
    ("transportation", fill("#c9ccd6", "#666d80", 0.1), "Transport"),
], other=fill("#d4bfb1", BLD_OUT, 0.1))
# Name at 1:4,000; Romanian storey notation (P+n = ground floor + n) at 1:2,500 where known.
rule_labels(bld, [
    (label_settings("\"name\"", size=6.5, color="#4d3a30", italic=True), 4000, 0,
     "\"name\" IS NOT NULL"),
    (label_settings("CASE WHEN \"num_floors\" = 1 THEN 'P' ELSE 'P+' || (\"num_floors\" - 1) END",
                    size=6, color="#6b5548", buffer=0), 2500, 0,
     "\"name\" IS NULL AND \"num_floors\" > 0"),
])
add(g_bld, bld, True, 60000)

# ---- Water & hydrology
wa = vec("brasov_water", "water_areas")
wa.setRenderer(QgsSingleSymbolRenderer(fill("#a6cee3", "#1f78b4", 0.2)))
labels(wa, "CASE WHEN $area > 5000 THEN \"name\" END", size=7, color="#1f4e79", italic=True,
       minscale=50000)
wl = vec("brasov_water", "water_lines")
rules(wl, [
    ("River", "\"class\" = 'river'", line("#1f78b4", 0.9), 0),
    ("Canal", "\"class\" = 'canal'", line("#1f78b4", 0.5), 0),
    ("Stream", "\"class\" = 'stream'", line("#4a90d9", 0.35), 400000),
    ("Drain / ditch", "\"class\" IN ('drain','ditch')", line("#6baed6", 0.2), 100000),
])
rule_labels(wl, [
    (label_settings("\"name\"", size=7, color="#1f4e79", line_placement=True, italic=True),
     500000, 0, "\"class\" IN ('river','canal')"),
    (label_settings("\"name\"", size=6.5, color="#1f4e79", line_placement=True, italic=True),
     50000, 0, "\"class\" = 'stream'"),
])
wp = vec("brasov_water", "water_points")
wp.setRenderer(QgsSingleSymbolRenderer(marker("#2b8cbe", 1.4)))
labels(wp, "\"name\"", size=6, color="#1f4e79", italic=True, minscale=15000)
st = vec("brasov_water", "hydro_streams")
st_rules = []
for o, w, ms in [(1, 0.12, 100000), (2, 0.2, 200000), (3, 0.3, 0), (4, 0.45, 0), (5, 0.65, 0),
                 (6, 0.85, 0), (7, 1.2, 0), (8, 1.4, 0)]:
    st_rules.append((f"Strahler {o}", f"\"strahler\" = {o}", line("#2171b5", w), ms, 25000))
    st_rules.append((f"Strahler {o} (detail, smoothed)", f"\"strahler\" = {o}",
                     smoothed(line("#2171b5", w), 3), 25000))
rules(st, st_rules)
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

# Drawn from the continuous HAND surface with the class thresholds (identical classes to
# hydro_flood_susceptibility.tif), so class edges follow the interpolated terrain when zoomed
# in instead of showing 25 m squares.
flood = QgsRasterLayer(ras("hydro_hand_m.tif").source(), "Flood susceptibility (HAND classes)")
ramp(flood, [(1, "#08306b", "Very high (HAND < 1 m)"), (3, "#2171b5", "High (1-3 m)"),
             (5, "#6baed6", "Moderate (3-5 m)"), (10, "#c6dbef", "Low (5-10 m)"),
             (1e9, "#ffffff00", "Very low (>= 10 m)")], method="discrete", vmin=0, vmax=1000)
smooth_raster(flood)
hand = ras("hydro_hand_m.tif")
ramp(hand, [(0, "#08306b", "0 m"), (2, "#2171b5", "2"), (5, "#6baed6", "5"),
            (10, "#c6dbef", "10"), (30, "#f7fbff", "30+ m")])
smooth_raster(hand)
twi = ras("hydro_twi.tif")
ramp(twi, [(2, "#8c510a", "dry"), (6, "#dfc27d", ""), (9, "#f6e8c3", ""), (12, "#80cdc1", ""),
           (16, "#01665e", "wet")])
smooth_raster(twi)
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
for lyr, vis, ms in ((wp, True, 25000), (wa, True, 0), (wl, True, 0), (st, False, 0),
                     (sb, False, 0), (basins, False, 0), (flood, False, 0), (hand, False, 0),
                     (twi, False, 0), (upa, False, 0), (fdir, False, 0), (gsw_o, False, 0),
                     (gsw_r, False, 0), (gsw_s, False, 0), (gsw_t, False, 0)):
    add(g_water, lyr, vis, ms)

# ---- Contours & terrain points
ct = vec("brasov_topography", "topo_contours_10m")
rules(ct, [
    ("Index 100 m", "\"kind\" = 'index_100m'", line("#8c6239", 0.3), 300000, 25000),
    ("Intermediate 50 m", "\"kind\" = 'intermediate_50m'", line("#a67c52", 0.18), 100000, 25000),
    ("Index 100 m (detail)", "\"kind\" = 'index_100m'", smoothed(line("#8c6239", 0.35)), 25000),
    ("Intermediate 50 m (detail)", "\"kind\" = 'intermediate_50m'",
     smoothed(line("#a67c52", 0.22)), 25000),
    ("10 m", "\"kind\" = 'regular_10m'", smoothed(line("#c8a882", 0.12)), 30000),
])
rule_labels(ct, [
    (label_settings("\"elev_m\"", size=6, color="#8c6239", line_placement=True), 60000, 0,
     "\"kind\" = 'index_100m'"),
    (label_settings("\"elev_m\"", size=5.5, color="#a67c52", line_placement=True), DETAIL, 0,
     "\"kind\" = 'intermediate_50m'"),
])
pk = vec("brasov_topography", "topo_peaks")
categorized(pk, "class", [
    ("peak", marker("#5a3a1a", 2.0, "triangle", "#ffffff"), "Peak"),
    ("saddle", marker("#8c6239", 1.4, "diamond", "#ffffff"), "Saddle / pass"),
    ("cave_entrance", marker("#000000", 1.4, "half_square"), "Cave entrance"),
], other=marker("#8c6239", 1.0))
labels(pk, "CASE WHEN \"name\" IS NOT NULL THEN \"name\" || "
           "coalesce('\\n' || \"elevation\" || ' m', '') END", size=6.5, color="#4d2f12",
       minscale=250000)
lnl = vec("brasov_topography", "land_natural_lines")
lnl.setRenderer(QgsSingleSymbolRenderer(line("#6b4423", 0.3)))
for lyr, vis in ((ct, True), (pk, True), (lnl, False)):
    add(g_terr, lyr, vis)

# ---- Land use, land cover & trees
prot = vec("brasov_landuse_infrastructure", "protected_areas")
rules(prot, [
    ("Nature reserve / park", "\"class\" <> 'protected'",
     fill("#1a9850", "#1a9850", 0.6, style="b_diagonal"), 0),
    ("Protection zone (e.g. water wells)", "\"class\" = 'protected'",
     fill("#3182bd", "#3182bd", 0.3, style="f_diagonal"), 0),
])
labels(prot, "\"name\"", size=7, color="#1a7340", italic=True, minscale=100000)
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
lu.setOpacity(0.55)
labels(lu, "CASE WHEN \"subtype\" IN ('park','cemetery','education','recreation') THEN \"name\" END",
       size=6.5, color="#3d5c3a", italic=True, minscale=8000)
landn = vec("brasov_topography", "land_natural_areas")
categorized(landn, "subtype", [
    ("forest", fill("#9bc48f", "#00000000"), "Forest"),
    ("grass", fill("#d9ecb4", "#00000000"), "Grassland"),
    ("shrub", fill("#c3d69b", "#00000000"), "Scrub / heath"),
    ("wetland", fill("#b8e0d2", "#00000000"), "Wetland"),
    ("rock", fill("#d9d9d9", "#00000000"), "Rock / scree"),
])
canopy = ras("canopy_height_5m.vrt")
# clip: 0 (no canopy) stays transparent; the last stop carries 30-60 m in the same colour
ramp(canopy, [(2, "#d9f0a3", "2 m"), (8, "#a1d99b", "8 m"), (15, "#41ab5d", "15 m"),
              (22, "#238b45", "22 m"), (30, "#00441b", "30+ m"), (60, "#00441b", "")],
     vmin=2, vmax=60, clip=True)
canopy.setOpacity(0.6)
smooth_raster(canopy, zoomed_in="bilinear")
wc = ras("landcover_worldcover_10m.tif")
paletted(wc, [(10, "#006400", "Tree cover"), (20, "#ffbb22", "Shrubland"),
              (30, "#ffff4c", "Grassland"), (40, "#f096ff", "Cropland"),
              (50, "#fa0000", "Built-up"), (60, "#b4b4b4", "Bare / sparse vegetation"),
              (70, "#f0f0f0", "Snow and ice"), (80, "#0064c8", "Permanent water"),
              (90, "#0096a0", "Herbaceous wetland"), (100, "#fae6a0", "Moss and lichen")])
add(g_land, prot, True)
add(g_land, lu, True, 50000)
add(g_land, landn, False)
add(g_land, canopy, True, 50000)
add(g_land, wc, False)

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

# ---- Relief & terrain analysis
hs = ras("topo_hillshade.tif")
g = QgsSingleBandGrayRenderer(hs.dataProvider(), 1)
ce = QgsContrastEnhancement(hs.dataProvider().dataType(1))
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
smooth_raster(dem)


def lighten(c, f=0.65):
    q = qc(c)
    mix = lambda v: round(v + (255 - v) * f)  # noqa: E731
    return f"#{mix(q.red()):02x}{mix(q.green()):02x}{mix(q.blue()):02x}"


# Close zoom: the same tint washed towards white, so low-lying green does not read as forest
# (tree canopy has its own layer at that scale).
DEM_STOPS = [(400, "#5e9e4f", "400 m"), (550, "#9cc47a", ""), (700, "#d6e3a0", "700 m"),
             (900, "#efe2a2", ""), (1100, "#e3c27f", "1100 m"), (1400, "#c99a62", ""),
             (1700, "#a9784e", "1700 m"), (2000, "#9c8b7e", ""), (2300, "#cfc8c2", "2300 m"),
             (2550, "#ffffff", "2550 m")]
dem_light = QgsRasterLayer(dem.source(), "Elevation tint (close zoom, light)")
ramp(dem_light, [(v, lighten(c), lab) for v, c, lab in DEM_STOPS])
smooth_raster(dem_light)
# Close-zoom hillshade computed live by QGIS from the cubic-interpolated DEM at screen
# resolution: smooth relief at any zoom instead of enlarged 25 m pixels.
hs_live = QgsRasterLayer(dem.source(), "Hillshade (close zoom, live from DEM)")
hl = QgsHillshadeRenderer(hs_live.dataProvider(), 1, 315, 45)
hl.setMultiDirectional(True)
hl.setZFactor(1.5)
hs_live.setRenderer(hl)
smooth_raster(hs_live)
hs_live.setBlendMode(QPainter.CompositionMode.CompositionMode_Multiply)
hs_live.setOpacity(0.6)
# Same classes as topo_slope_classes.tif, drawn from the continuous slope (degrees equivalent of
# each % threshold: atan(p/100)) so class edges stay smooth at close zoom.
slc = QgsRasterLayer(ras("topo_slope_deg.tif").source(), "Slope classes (planning)")
ramp(slc, [(1.1458, "#1a9850", "< 2 %"), (2.8624, "#66bd63", "2-5 %"),
           (5.7106, "#a6d96a", "5-10 %"), (8.5308, "#d9ef8b", "10-15 %"),
           (14.0362, "#fee08b", "15-25 %"), (19.2900, "#fdae61", "25-35 %"),
           (26.5651, "#f46d43", "35-50 %"), (90, "#d73027", ">= 50 %")], method="discrete",
     vmin=0, vmax=90)
smooth_raster(slc)
sld = ras("topo_slope_deg.tif")
ramp(sld, [(0, "#ffffcc", "0°"), (10, "#fed976", "10°"), (20, "#fd8d3c", "20°"),
           (30, "#e31a1c", "30°"), (45, "#800026", "45°+")])
smooth_raster(sld)
asp = ras("topo_aspect_deg.tif")
ramp(asp, [(0, "#e41a1c", "N"), (90, "#ffff33", "E"), (180, "#4daf4a", "S"),
           (270, "#377eb8", "W"), (360, "#e41a1c", "N")])
tri = ras("topo_ruggedness_tri.tif")
ramp(tri, [(0, "#f7f7f7", "smooth"), (5, "#cccccc", ""), (15, "#969696", ""),
           (40, "#252525", "rugged")])
smooth_raster(tri)
gm = ras("topo_landforms_geomorphons.tif")
paletted(gm, [(1, "#dcdcdc", "Flat"), (2, "#380000", "Peak"), (3, "#c80000", "Ridge"),
              (4, "#ff5014", "Shoulder"), (5, "#fad23c", "Spur"), (6, "#ffff3c", "Slope"),
              (7, "#b4e614", "Hollow"), (8, "#3cfa96", "Footslope"), (9, "#0000ff", "Valley"),
              (10, "#000038", "Pit")])
for lyr, vis, mins, maxs in ((gm, False, 0, 0), (slc, False, 0, 0), (sld, False, 0, 0),
                             (asp, False, 0, 0), (tri, False, 0, 0),
                             (hs_live, True, 50000, 0), (hs, True, 0, 50000),
                             (dem_light, True, 50000, 0), (dem, True, 0, 50000)):
    add(g_relief, lyr, vis, mins, maxs)

# ---- Imagery
img = ras("imagery_sentinel2_truecolor_10m.tif")
mb = QgsMultiBandColorRenderer(img.dataProvider(), 1, 2, 3)
mb.setAlphaBand(4)  # GDAL per-dataset mask, exposed by QGIS as band 4
img.setRenderer(mb)
# One linear stretch shared by all three bands keeps the true-colour balance (a per-band
# cumulative cut over a mostly forested image turns towns pink).
for band, setter in ((1, mb.setRedContrastEnhancement), (2, mb.setGreenContrastEnhancement),
                     (3, mb.setBlueContrastEnhancement)):
    ce_ = QgsContrastEnhancement(img.dataProvider().dataType(band))
    ce_.setContrastEnhancementAlgorithm(
        QgsContrastEnhancement.ContrastEnhancementAlgorithm.StretchToMinimumMaximum)
    ce_.setMinimumValue(0)
    ce_.setMaximumValue(165)
    setter(ce_)
smooth_raster(img)
add(g_img, img, False)

# ---- Online basemaps
WEB = [("Esri World Imagery (sub-metre, close zoom)",
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/"
        "{z}/{y}/{x}", 19),
       ("OpenStreetMap", "https://tile.openstreetmap.org/{z}/{x}/{y}.png", 19),
       ("OpenTopoMap", "https://tile.opentopomap.org/{z}/{x}/{y}.png", 17)]
web = {}
for name, url, zmax in WEB:
    uri = f"type=xyz&url={url.replace('{', '%7B').replace('}', '%7D')}&zmax={zmax}&zmin=0"
    lyr = QgsRasterLayer(uri, name, "wms")
    if lyr.isValid() and name.startswith("Esri"):
        # Above the offline Sentinel-2 mosaic, close zoom only: online it shows sub-metre
        # imagery, offline it is simply empty and the 10 m mosaic shows through.
        lyr.setScaleBasedVisibility(True)
        lyr.setMinimumScale(50000)
        lyr.setMaximumScale(1)
        project.addMapLayer(lyr, False)
        g_img.insertLayer(0, lyr).setItemVisibilityChecked(False)
        web["Esri"] = lyr
    elif lyr.isValid():
        web[name.split(" ")[0]] = add(g_web, lyr, False)
    else:
        print("skipping basemap (provider unavailable):", name, file=sys.stderr)

for grp in (g_infra, g_bld, g_soil, g_land, g_img, g_web, g_terr):
    grp.setExpanded(False)

# ---------------------------------------------------------------- default styles + view
for lyr in project.mapLayers().values():
    # hsg and hs_live re-use another layer's data source; their styles are not the default
    if lyr.providerType() in ("ogr", "gdal") and lyr not in (hsg, hs_live, dem_light, flood, slc):
        save_default_style(lyr)
# Same table as the soil layer: stored as an alternative (non-default) style, selectable in
# Layer Properties > Style > Load Style > From database.
try:
    hsg.saveStyleToDatabaseV2("hydrologic soil group", "brasov pipeline", False, "")
except AttributeError:
    hsg.saveStyleToDatabase("hydrologic soil group", "brasov pipeline", False, "")

ext = county.extent()
ext.grow(3000)
project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(ext, project.crs()))

# ---------------------------------------------------------------- A3 print layout
LEGEND_TITLES = {county.id(): "County boundary", uat.id(): "UAT boundaries",
                 sett.id(): "Settlements", wl.id(): "Watercourses (OSM)",
                 wa.id(): "Water bodies (OSM)", st.id(): "Streams (DEM, Strahler order)",
                 prot.id(): "Protected areas", ct.id(): "Contours", pk.id(): "Terrain points",
                 dem.id(): "Elevation (m)", dem_light.id(): "Elevation (m)",
                 soil.id(): "Dominant soil (WRB 2022)",
                 wc.id(): "Land cover 2021", flood.id(): "Flood susceptibility (HAND)",
                 roads.id(): "Roads", rail.id(): "Railways", bld.id(): "Buildings",
                 canopy.id(): "Tree canopy height", lu.id(): "Land use",
                 poi.id(): "Places", infl.id(): "Lines (power, walls, fences)"}

def make_layout(name, title, layers_visible, scale=None, center=None, seg=5, unit="km",
                legend_layers=None):
    lay = QgsPrintLayout(project)
    lay.initializeDefaults()
    lay.setName(name)
    lay.pageCollection().page(0).setPageSize("A3", QgsLayoutItemPage.Orientation.Landscape)
    mp = QgsLayoutItemMap(lay)
    mp.attemptSetSceneRect(QRectF(10, 22, 320, 265))
    mp.setCrs(project.crs())
    mp.setExtent(ext)
    if scale:
        mp.setScale(scale)
        r = mp.extent()
        w, h = r.width(), r.height()
        mp.setExtent(QgsRectangle(center.x() - w / 2, center.y() - h / 2,
                                  center.x() + w / 2, center.y() + h / 2))
        mp.setScale(scale)
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
    for lyr in (legend_layers or layers_visible):
        if lyr in (hs, hs_live):
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
    lg.setLegendFilterByMapEnabled(True)  # list only what is actually drawn on this sheet
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
    du = (QgsUnitTypes.DistanceUnit.DistanceKilometers if unit == "km"
          else QgsUnitTypes.DistanceUnit.DistanceMeters)
    sbar.applyDefaultSize(du)
    sbar.setUnits(du)
    sbar.setUnitLabel(unit)
    sbar.setNumberOfSegments(4)
    sbar.setUnitsPerSegment(seg)
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


def to3844(lon, lat):
    tr = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), project.crs(),
                                project)
    return tr.transform(QgsPointXY(lon, lat))


CENTRE_BRASOV = to3844(25.5887, 45.6421)   # Piața Sfatului
DETAIL_LAYERS = [uat, sett, poi, infa, infl, roads, rail, bld, wp, wa, wl, ct, pk, prot, lu,
                 canopy, hs_live, dem_light]
lay5 = make_layout("A3 - Brașov centre 1:10,000 (street detail)",
                   "Brașov - centre, street-level detail (1:10,000)", DETAIL_LAYERS,
                   scale=10000, center=CENTRE_BRASOV, seg=250, unit="m",
                   legend_layers=[roads, rail, bld, poi, wl, wa, lu, canopy, prot, ct, dem_light])

# ---------------------------------------------------------------- map themes
# One-click views (Layers panel > "Manage Map Themes" eye icon). Each theme is a set of checked
# layers; scale-dependent layers still switch on/off with zoom inside a theme.
layer_nodes = {n.layer(): n for n in root.findLayers()}
default_on = {l for l, n in layer_nodes.items() if n.itemVisibilityChecked()}
model = QgsLayerTreeModel(root)
for grp in root.findGroups(True):
    grp.setItemVisibilityChecked(True)


def theme(name, on):
    for lyr_, node in layer_nodes.items():
        node.setItemVisibilityChecked(lyr_ in on)
    project.mapThemeCollection().insert(
        name, QgsMapThemeCollection.createThemeFromCurrentState(root, model))


BASE = {county, uat, sett, ctx}
esri = web.get("Esri")
theme("1 Planning base - relief, water, streets", default_on)
theme("2 Satellite + streets", BASE | {roads, rail, wa, wl, poi, img} | ({esri} if esri else set()))
theme("3 Water & flood susceptibility", BASE | {wa, wl, st, flood, hs, hs_live, roads})
theme("4 Slope classes (buildability)", BASE | {roads, wa, wl, ct, slc, hs, hs_live})
theme("5 Soils", BASE | {wl, soil, hs, hs_live})
theme("6 Land cover & tree canopy", BASE | {wl, wa, wc, canopy, hs, hs_live})
theme("7 Landforms", BASE | {wl, gm, hs, hs_live})
for lyr_, node in layer_nodes.items():
    node.setItemVisibilityChecked(lyr_ in default_on)

ok = project.write(PROJECT_URI)
print("project written:", ok, PROJECT_URI)
if SINGLE:
    app.exitQgis()
    sys.exit(0 if ok else 1)

# ---------------------------------------------------------------- previews
for lay, fn in ((lay1, "overview"), (lay2, "water"), (lay3, "soil"), (lay4, "landcover"),
                (lay5, "brasov_centre_10k")):
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
    ms.setOutputDpi(96)
    ms.setBackgroundColor(QColor("white"))
    job = QgsMapRendererParallelJob(ms)
    job.start()
    job.waitForFinished()
    job.renderedImage().save(str(DOCS / fn))


def at_scale(center, scale, size=(1600, 1100)):
    """Extent that renders `center` at 1:scale for `size` pixels at 96 dpi."""
    m_per_px = scale * 0.0254 / 96
    w, h = size[0] * m_per_px, size[1] * m_per_px
    return QgsRectangle(center.x() - w / 2, center.y() - h / 2, center.x() + w / 2,
                        center.y() + h / 2)


checked = [l for l in root.layerOrder() if root.findLayer(l.id()).isVisible()]
for fn, (lon, lat), scale in (("detail_brasov_5k.png", (25.5887, 45.6421), 5000),
                              ("detail_brasov_10k.png", (25.5960, 45.6450), 10000),
                              ("detail_prejmer_10k.png", (25.7731, 45.7224), 10000),
                              ("detail_bran_25k.png", (25.3672, 45.5153), 25000)):
    render(checked, fn, at_scale(to3844(lon, lat), scale), (1600, 1100))
render([county, uat, img], "imagery.png")
app.exitQgis()
