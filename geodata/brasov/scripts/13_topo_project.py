"""Topographic map of Brașov County, built on the same data and grid as brasov_county.qgz.

  brasov_topographic.qgz                 classic topographic symbology + two print layouts:
    * "Topographic map 1:50,000 (A2 atlas)"  29 sheets, Stereo 70 km grid, lat/long ticks,
                                             locator, adjacent sheets, legend
    * "Overview 1:200,000 (A1)"              whole county with the sheet index
  maps/topo_50k/BV50-<sheet>_<name>.pdf  every sheet, georeferenced PDF
  maps/brasov_topographic_overview_200k.pdf (+ .png preview)
  docs/topo_sheet_<id>.png               previews

Run with --no-export to only (re)write the project.
"""
import sys

from qgis.PyQt.QtCore import QRectF, QSizeF, Qt
from qgis.PyQt.QtGui import QColor, QFont, QPainter
from qgis.core import (
    Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsHillshadeRenderer,
    QgsLayoutExporter, QgsLayoutItemLabel, QgsLayoutItemLegend, QgsLayoutItemMap,
    QgsLayoutItemMapGrid, QgsLayoutItemPage, QgsLayoutItemPicture, QgsLayoutItemScaleBar,
    QgsLayoutPoint, QgsLayoutSize, QgsLegendStyle, QgsLineSymbol,
    QgsMapLayerLegendUtils, QgsMarkerLineSymbolLayer, QgsMarkerSymbol, QgsPalLayerSettings,
    QgsPointPatternFillSymbolLayer, QgsPrintLayout, QgsProject, QgsProperty, QgsRasterLayer,
    QgsRectangle, QgsReferencedRectangle, QgsSimpleLineSymbolLayer, QgsTextBackgroundSettings,
    QgsTextBufferSettings, QgsTextFormat, QgsUnitTypes, QgsVectorLayer,
    QgsFillSymbol, QgsRuleBasedLabeling, QgsGeometryGeneratorSymbolLayer,
)

from catalog import RASTERS, VECTORS
from common import DATA, RASTER, ROOT
from qgis_helpers import categorized, fill, line, marker, qc, ramp, rules, smooth_raster

app = QgsApplication([], False)
app.initQgis()

EXPORT = "--no-export" not in sys.argv
MAPS = ROOT / "maps"
SHEETS_DIR = MAPS / "topo_50k"
SHEETS_DIR.mkdir(parents=True, exist_ok=True)
DOCS = ROOT / "docs"
PROJECT_FILE = ROOT / "brasov_topographic.qgz"
SANS, SERIF = "Arial", "Times New Roman"   # Liberation Sans/Serif where Arial/Times are absent

TITLES = {layer: title for _, layer, _, title, _, _ in VECTORS}
RTITLES = {f: title for f, _, title, _, _ in RASTERS}

project = QgsProject.instance()
project.clear()
project.setCrs(QgsCoordinateReferenceSystem("EPSG:3844"))
project.setTitle("Județul Brașov - topographic map 1:50,000")
project.setFilePathStorage(Qgis.FilePathType.Relative)
project.setFileName(str(PROJECT_FILE))
project.setBackgroundColor(QColor("#ffffff"))
root = project.layerTreeRoot()

# ---------------------------------------------------------------- palette (classic topo)
CONTOUR, CONTOUR_IDX = "#b07a4c", "#8a5226"
WATER, WATER_FILL = "#2f7fc1", "#b6d9f2"
FOREST, SCRUB = "#c4e0ac", "#e2efcf"
BUILT, INDUSTRIAL = "#f4e2d4", "#e8dcec"
BUILDING = "#3c3c3c"
ADMIN = "#8e3a8e"
TEXT = "#1e1e1e"
RELIEF_TEXT = "#6b3d1a"


# ---------------------------------------------------------------- helpers
def vec(stem, layer, name=None):
    lyr = QgsVectorLayer(f"{DATA / (stem + '.gpkg')}|layername={layer}",
                         name or TITLES[layer], "ogr")
    assert lyr.isValid(), layer
    return lyr


def ras(fname, name=None):
    lyr = QgsRasterLayer(str(RASTER / fname), name or RTITLES[fname])
    assert lyr.isValid(), fname
    return lyr


def add(group, lyr, visible=True, minscale=0, maxscale=0):
    if minscale or maxscale:
        lyr.setScaleBasedVisibility(True)
        lyr.setMinimumScale(minscale)
        lyr.setMaximumScale(maxscale or 1)
    project.addMapLayer(lyr, False)
    node = group.addLayer(lyr)
    node.setItemVisibilityChecked(visible)
    node.setExpanded(False)
    return lyr


def text_format(size, color=TEXT, family=SANS, bold=False, italic=False, buffer=0.8,
                caps=False, spacing=0.0, buffer_color="#ffffff"):
    f = QFont(family)
    f.setBold(bold)
    f.setItalic(italic)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    fmt = QgsTextFormat()
    fmt.setFont(f)
    fmt.setSize(size)
    fmt.setSizeUnit(Qgis.RenderUnit.Points)
    fmt.setColor(qc(color))
    if caps:
        fmt.setCapitalization(Qgis.Capitalization.AllUppercase)
    if buffer:
        b = QgsTextBufferSettings()
        b.setEnabled(True)
        b.setSize(buffer)
        b.setColor(qc(buffer_color))
        b.setOpacity(0.85)
        fmt.setBuffer(b)
    return fmt


def pal(expr, fmt, placement=None, priority=5, obstacle=True, repeat_mm=0, size_expr=None,
        dist_mm=0.0, curved_max_angle=25, min_len_mm=0):
    s = QgsPalLayerSettings()
    s.fieldName = expr
    s.isExpression = True
    s.setFormat(fmt)
    s.priority = priority
    s.obstacleSettings().setIsObstacle(obstacle)
    if placement == "curved":
        s.placement = Qgis.LabelPlacement.Curved
        s.maxCurvedCharAngleIn = curved_max_angle
        s.maxCurvedCharAngleOut = -curved_max_angle
        s.lineSettings().setPlacementFlags(Qgis.LabelLinePlacementFlag.OnLine)
    elif placement == "line":
        s.placement = Qgis.LabelPlacement.Line
        s.lineSettings().setPlacementFlags(Qgis.LabelLinePlacementFlag.OnLine)
    elif placement == "horizontal":
        s.placement = Qgis.LabelPlacement.Horizontal
    elif placement == "around":
        s.placement = Qgis.LabelPlacement.OrderedPositionsAroundPoint
        s.dist = dist_mm or 1.0
    if placement in ("curved", "line", "horizontal"):
        # road/river segments are split at every junction: label the merged line once
        s.lineSettings().setMergeLines(True)
    if min_len_mm:
        s.minFeatureSize = min_len_mm   # skip short (merged) line parts
    if repeat_mm:
        s.repeatDistance = repeat_mm
        s.repeatDistanceUnit = Qgis.RenderUnit.Millimeters
    if size_expr:
        s.dataDefinedProperties().setProperty(QgsPalLayerSettings.Property.Size,
                                              QgsProperty.fromExpression(size_expr))
    return s


def label_rules(lyr, items):
    """items: (settings, zoomed-out limit, zoomed-in limit, filter)"""
    rr = QgsRuleBasedLabeling.Rule(None)
    for s, mins, maxs, flt in items:
        rr.appendChild(QgsRuleBasedLabeling.Rule(s, maxs, mins, flt or ""))
    lyr.setLabeling(QgsRuleBasedLabeling(rr))
    lyr.setLabelsEnabled(True)


def cased(fill_c, fill_w, case_c, case_w, fill_pass, dash=None):
    """Road/rail line in mm with a casing; casings render in pass 0 (needs symbol levels)."""
    sym = QgsLineSymbol()
    sym.deleteSymbolLayer(0)
    for color, w, rpass, d in ((case_c, case_w, 0, None), (fill_c, fill_w, fill_pass, dash)):
        if color is None:
            continue
        sl = QgsSimpleLineSymbolLayer(qc(color), w)
        sl.setPenCapStyle(Qt.PenCapStyle.FlatCap if d else Qt.PenCapStyle.RoundCap)
        sl.setPenJoinStyle(Qt.PenJoinStyle.RoundJoin)
        sl.setRenderingPass(rpass)
        if d:
            sl.setUseCustomDashPattern(True)
            sl.setCustomDashVector(d)
        sym.appendSymbolLayer(sl)
    return sym


def dashed(color, width, pattern):
    sym = line(color, width)
    sl = sym.symbolLayer(0)
    sl.setUseCustomDashPattern(True)
    sl.setCustomDashVector(pattern)
    sl.setPenCapStyle(Qt.PenCapStyle.FlatCap)
    return sym


def ticked_line(color, width, tick_len, interval, marker_shape="line"):
    """Line with perpendicular ticks (power lines, aerialways)."""
    sym = line(color, width)
    m = QgsMarkerSymbol.createSimple({"name": marker_shape, "color": color,
                                      "outline_color": color, "size": str(tick_len),
                                      "outline_width": str(width)})
    ml = QgsMarkerLineSymbolLayer(True, interval)
    ml.setSubSymbol(m)
    sym.appendSymbolLayer(ml)
    return sym


def pattern_fill(bg, dot_color, dot_size=0.45, spacing=1.6, shape="circle", outline=None):
    sym = fill(bg, outline or "#00000000", 0.15 if outline else 0)
    pp = QgsPointPatternFillSymbolLayer()
    pp.setDistanceX(spacing)
    pp.setDistanceY(spacing)
    pp.setDisplacementX(spacing / 2)
    pp.setSubSymbol(QgsMarkerSymbol.createSimple({"name": shape, "color": dot_color,
                                                  "outline_style": "no",
                                                  "size": str(dot_size)}))
    sym.appendSymbolLayer(pp)
    return sym


# ---------------------------------------------------------------- groups (top draws on top)
g_text = root.addGroup("Names, peaks & spot heights")
g_bnd = root.addGroup("Boundaries")
g_tr = root.addGroup("Transport & lines")
g_bld = root.addGroup("Buildings")
g_hyd = root.addGroup("Hydrography")
g_rel = root.addGroup("Contours")
g_shade = root.addGroup("Relief shading")
g_lc = root.addGroup("Land cover")
g_idx = root.addGroup("Sheet index")

OV = 100000   # generalisation threshold: finer content only at 1:100,000 and closer

# ---- names & points
sett = vec("brasov_admin", "settlements", "Settlements")
rules(sett, [("City / town", "\"class\" IN ('city','town')",
                               marker("#000000", 0.0, outline="#00000000"), 0)])
label_rules(sett, [
    (pal('"name"', text_format(13, bold=True, caps=True, spacing=0.6, buffer=1.2), "horizontal",
         priority=10), 0, 0, "\"class\" = 'city'"),
    (pal('"name"', text_format(10, bold=True, buffer=1.0), "horizontal", priority=9), 0, 0,
     "\"class\" = 'town'"),
    (pal('"name"', text_format(7.5, buffer=0.9), "horizontal", priority=8), 0, 0,
     "\"class\" = 'village'"),
    (pal('"name"', text_format(6.5, italic=True, buffer=0.8), "horizontal", priority=6), OV, 0,
     "\"class\" NOT IN ('city','town','village')"),
])

pk = vec("brasov_topographic", "topo_peaks_labelled", "Peaks & passes")
categorized(pk, "class", [
    ("peak", marker("#000000", 1.7, "triangle", "#ffffff"), "Peak"),
    ("saddle", marker("#000000", 1.3, "diamond", "#ffffff"), "Pass / saddle"),
    ("cave_entrance", marker("#000000", 1.4, "half_square", "#ffffff"), "Cave"),
], other=marker("#000000", 0.9))
label_rules(pk, [
    (pal("\"name\" || coalesce('\\n' || to_int(\"elev_label\"), '')",
         text_format(7, RELIEF_TEXT, SERIF, italic=True, buffer=0.9), "around", priority=7),
     OV, 0, "\"name\" IS NOT NULL AND \"class\" IN ('peak','saddle')"),
    (pal("\"name\" || coalesce('\\n' || to_int(\"elev_label\"), '')",
         text_format(7.5, RELIEF_TEXT, SERIF, italic=True, buffer=0.9), "around", priority=7),
     0, OV, "\"name\" IS NOT NULL AND \"class\" = 'peak' AND \"elev_label\" >= 1700"),
    (pal("to_int(\"elev_label\")", text_format(6, RELIEF_TEXT, buffer=0.7), "around",
         priority=4), OV, 0, "\"name\" IS NULL AND \"elev_label\" IS NOT NULL"),
])
spot = vec("brasov_topographic", "topo_spot_heights", "Spot heights (DEM)")
rules(spot, [("Spot height", "TRUE", marker("#000000", 0.55, outline="#00000000"),
                               OV)])
label_rules(spot, [(pal('"elev_m"', text_format(5.5, RELIEF_TEXT, buffer=0.6), "around",
                        priority=3), OV, 0, "")])
mtn = vec("brasov_topography", "land_natural_areas", "Mountain ranges (names)")
mtn.setSubsetString("\"class\" = 'mountain_range' AND \"name\" IS NOT NULL")
rules(mtn, [("Mountain range", "TRUE", fill("#00000000", "#00000000"), 0)])
label_rules(mtn, [(pal('"name"', text_format(11, RELIEF_TEXT, SERIF, italic=True, caps=True,
                                             spacing=3, buffer=0), "horizontal", priority=2,
                       obstacle=False), 0, 0, "")])
poi = vec("brasov_landuse_infrastructure", "places_poi", "Churches, monuments, huts")
POI_FILTER = ("\"category\" IN ('christian_place_of_worship','church_cathedral','monastery',"
              "'historic_site','monument','castle','fort','museum','mountain_hut','shelter',"
              "'landmark_and_historical_building','ruins')")
poi.setSubsetString(POI_FILTER)
rules(poi, [
    ("Church / monastery", "\"category\" IN ('christian_place_of_worship','church_cathedral',"
     "'monastery')", marker("#000000", 1.8, "cross2", "#000000"), OV),
    ("Castle / fortress", "\"category\" IN ('castle','fort')",
     marker("#7a1f1f", 2.2, "square", "#ffffff"), 0),
    ("Monument / historic site / museum", "\"category\" IN ('historic_site','monument','museum',"
     "'landmark_and_historical_building','ruins')", marker("#7a1f1f", 1.7, "star", "#ffffff"),
     OV),
    ("Mountain hut / shelter", "\"category\" IN ('mountain_hut','shelter')",
     marker("#b30000", 1.8, "triangle", "#ffffff"), 0),
])
label_rules(poi, [(pal('"name"', text_format(5.8, "#5a1a1a", italic=True, buffer=0.7),
                       "around", priority=3), 60000, 0,
                   "\"category\" IN ('castle','fort','mountain_hut','monastery')")])
for lyr, vis in ((sett, True), (pk, True), (spot, True), (mtn, True), (poi, True)):
    add(g_text, lyr, vis)

# ---- boundaries
county = vec("brasov_admin", "admin_county", "County boundary")
cs = QgsFillSymbol.createSimple({"style": "no", "outline_style": "no"})
for color, w, d in (("#e3c8e3", 3.0, None), (ADMIN, 0.7, [6, 1.2, 1, 1.2])):
    sl = QgsSimpleLineSymbolLayer(qc(color), w)
    if d:
        sl.setUseCustomDashPattern(True)
        sl.setCustomDashVector(d)
    gg = QgsGeometryGeneratorSymbolLayer.create({"geometryModifier": "boundary($geometry)",
                                                 "SymbolType": "Line"})
    ls = QgsLineSymbol()
    ls.deleteSymbolLayer(0)
    ls.appendSymbolLayer(sl)
    gg.setSubSymbol(ls)
    cs.appendSymbolLayer(gg)
cs.symbolLayer(0).setEnabled(False)
rules(county, [("County boundary", "TRUE", cs, 0)])
county.setOpacity(1.0)
uat = vec("brasov_admin", "admin_uat", "Commune / town boundaries")
rules(uat, [("UAT boundary", "TRUE", fill("#00000000", ADMIN, 0.3,
                                                         style="no", outline_style="dash dot"),
                             0)])
ctx = vec("brasov_admin", "admin_counties_context", "Neighbouring counties")
rules(ctx, [("County", "\"iso\" <> 'RO-BV'", fill("#00000000", "#9a9a9a", 0.5,
                                                                  style="no"), 0)])
label_rules(ctx, [(pal("upper(\"name\")", text_format(10, "#8a8a8a", bold=True, spacing=2,
                                                      buffer=0), "horizontal", priority=1,
                       obstacle=False), 0, 0, "\"iso\" <> 'RO-BV'")])
add(g_bnd, county)
add(g_bnd, uat)
add(g_bnd, ctx)

# ---- transport & lines
roads = vec("brasov_landuse_infrastructure", "transport_roads", "Roads")
rules(roads, [
    ("Motorway", "\"class\" = 'motorway'", cased("#e4312b", 1.1, "#5c0d0a", 1.7, 9), 0),
    ("National road (DN, E-route)", "\"class\" = 'trunk'",
     cased("#e4312b", 0.85, "#2b2b2b", 1.35, 8), 0),
    ("National road (DN)", "\"class\" = 'primary'", cased("#ef6a2a", 0.75, "#2b2b2b", 1.2, 7), 0),
    ("County road (DJ)", "\"class\" = 'secondary'", cased("#f8a83c", 0.6, "#2b2b2b", 1.0, 6), 0),
    ("Communal road", "\"class\" = 'tertiary'", cased("#ffe36b", 0.45, "#3a3a3a", 0.8, 5), 0),
    ("Street / local road", "\"class\" IN ('residential','unclassified','living_street',"
     "'unknown','pedestrian')", cased("#ffffff", 0.3, "#4a4a4a", 0.6, 4), OV),
    ("Service road", "\"class\" = 'service'", line("#5a5a5a", 0.18), 60000),
    ("Track / forest road", "\"class\" = 'track'", dashed("#3a2a1a", 0.25, [2.2, 0.8]), OV),
    ("Path / footpath", "\"class\" IN ('path','footway','bridleway','steps','cycleway')",
     dashed("#1a1a1a", 0.18, [0.8, 0.7]), OV),
], symbol_levels=True)
ref_fmt = text_format(5.5, "#000000", bold=True, buffer=0)
bg = QgsTextBackgroundSettings()
bg.setEnabled(True)
bg.setType(QgsTextBackgroundSettings.ShapeType.ShapeRectangle)
bg.setSizeType(QgsTextBackgroundSettings.SizeType.SizeBuffer)
bg.setSize(QSizeF(0.5, 0.25))
bg.setFillColor(QColor("#ffffff"))
bg.setStrokeColor(QColor("#000000"))
bg.setStrokeWidth(0.15)
ref_fmt.setBackground(bg)
label_rules(roads, [
    (pal("regexp_substr(\"ref\", '(DN\\\\d+[A-Z]?|DJ\\\\d+[A-Z]?|A\\\\d+)')", ref_fmt,
         "horizontal", priority=9, repeat_mm=150, min_len_mm=18), 0, 0,
     "\"class\" IN ('motorway','trunk','primary','secondary','tertiary') AND \"ref\" IS NOT NULL"),
    (pal('"name"', text_format(5.5, "#333333", italic=True, buffer=0.7), "curved",
         priority=2, repeat_mm=80), 30000, 0,
     "\"name\" IS NOT NULL AND \"class\" NOT IN ('track','path','footway','steps','service')"),
])
rail = vec("brasov_landuse_infrastructure", "transport_rail", "Railways")
rail_sym = QgsLineSymbol()
rail_sym.deleteSymbolLayer(0)
for color, w, d in (("#000000", 0.75, None), ("#ffffff", 0.4, [2.5, 2.5])):
    sl = QgsSimpleLineSymbolLayer(qc(color), w)
    sl.setPenCapStyle(Qt.PenCapStyle.FlatCap)
    if d:
        sl.setUseCustomDashPattern(True)
        sl.setCustomDashVector(d)
    rail_sym.appendSymbolLayer(sl)
rules(rail, [
    ("Railway", "\"class\" NOT IN ('abandoned','disused','tram','funicular')", rail_sym, 0),
    ("Tram / funicular", "\"class\" IN ('tram','funicular')", line("#000000", 0.3), OV),
])
lines_inf = vec("brasov_landuse_infrastructure", "infrastructure_lines", "Power lines, lifts, dams")
rules(lines_inf, [
    ("High-voltage power line", "\"class\" = 'power_line'",
     ticked_line("#3a3a3a", 0.18, 0.9, 6), OV),
    ("Cable car / ski lift", "\"class\" IN ('chair_lift','cable_car','gondola','platter',"
     "'drag_lift','t-bar','j-bar','mixed_lift')", ticked_line("#000000", 0.25, 0.8, 3, "circle"),
     0),
    ("Dam", "\"class\" = 'dam'", line("#000000", 0.9), 0),
    ("City wall", "\"class\" = 'city_wall'", line("#5a3a1a", 0.6), OV),
])
add(g_tr, rail)
add(g_tr, roads)
add(g_tr, lines_inf)

# ---- buildings
bld = vec("brasov_buildings", "buildings", "Buildings")
rules(bld, [
    ("Building", "\"subtype\" IS NULL OR \"subtype\" NOT IN ('religious','industrial','agricultural')",
     fill(BUILDING), OV),
    ("Industrial / agricultural building", "\"subtype\" IN ('industrial','agricultural')",
     fill("#6e6e6e"), OV),
    ("Church", "\"subtype\" = 'religious'", fill("#000000"), OV),
])
add(g_bld, bld)

# ---- hydrography
wa = vec("brasov_water", "water_areas", "Lakes, reservoirs, rivers (area)")
rules(wa, [("Water body", "TRUE", fill(WATER_FILL, WATER, 0.15), 0)])
label_rules(wa, [(pal('"name"', text_format(7, WATER, SERIF, italic=True, buffer=0.7),
                      "horizontal", priority=6), OV, 0, "\"name\" IS NOT NULL AND $area > 20000")])
wl = vec("brasov_water", "water_lines", "Rivers, streams, canals")
rules(wl, [
    ("River", "\"class\" = 'river'", line(WATER, 0.55), 0),
    ("Canal", "\"class\" = 'canal'", line(WATER, 0.4), 0),
    ("Stream", "\"class\" = 'stream'", line(WATER, 0.22), OV),
    ("Drain / ditch", "\"class\" IN ('drain','ditch')", line(WATER, 0.13), 60000),
])
label_rules(wl, [
    (pal('"name"', text_format(8, WATER, SERIF, italic=True, buffer=0.8), "curved", priority=7,
         repeat_mm=140), 0, 0, "\"class\" IN ('river','canal')"),
    (pal('"name"', text_format(6.5, WATER, SERIF, italic=True, buffer=0.7), "curved",
         priority=5, repeat_mm=110), OV, 0, "\"class\" = 'stream'"),
])
us = vec("brasov_topographic", "topo_streams_unmapped", "Streams (from terrain, unmapped)")
rules(us, [("Stream from terrain model (not surveyed)", "TRUE",
                           dashed(WATER, 0.16, [1.6, 0.8]), OV)])
sp = vec("brasov_water", "water_points", "Springs & wells")
rules(sp, [("Spring / well", "TRUE", marker(WATER, 1.1, "circle", "#ffffff"),
                           60000)])
add(g_hyd, sp)
add(g_hyd, wa)
add(g_hyd, wl)
add(g_hyd, us)

# ---- contours (20 m interval, 100 m index; display-smoothed)
ct = vec("brasov_topography", "topo_contours_10m", "Contours")
rules(ct, [
    ("Index contour (100 m)", "\"kind\" = 'index_100m'", line(CONTOUR_IDX, 0.22), 0),
    ("Contour (20 m)", "\"elev_m\" % 20 = 0 AND \"kind\" <> 'index_100m'",
     line(CONTOUR, 0.1), OV),
])
label_rules(ct, [(pal('"elev_m"', text_format(5.2, CONTOUR_IDX, buffer=0.6,
                                              buffer_color="#ffffff"), "line", priority=1,
                      repeat_mm=100), OV, 0, "\"kind\" = 'index_100m'")])
add(g_rel, ct)

# ---- relief shading (live, from the cubic-interpolated DEM)
dem_src = str(RASTER / "topo_dem_25m.tif")
shade = QgsRasterLayer(dem_src, "Relief shading")
hr = QgsHillshadeRenderer(shade.dataProvider(), 1, 315, 45)
hr.setMultiDirectional(True)
hr.setZFactor(1.3)
shade.setRenderer(hr)
smooth_raster(shade)
shade.setBlendMode(QPainter.CompositionMode.CompositionMode_Multiply)
# Shadow-only shading: lift flat ground and sunlit slopes to white so lowlands stay white
# (classic topographic look) and only slopes facing away from the light are darkened.
shade.brightnessFilter().setBrightness(75)
shade.brightnessFilter().setContrast(15)
shade.setOpacity(0.6)
add(g_shade, shade)

# ---- land cover
prot = vec("brasov_landuse_infrastructure", "protected_areas", "Protected areas")
rules(prot, [("Nature reserve / park boundary", "\"class\" <> 'protected'",
                               fill("#00000000", "#2e8b57", 0.45, style="no",
                                    outline_style="dash"), 0)])
label_rules(prot, [(pal('"name"', text_format(6.5, "#1f6b3f", italic=True, buffer=0.7),
                        "horizontal", priority=2), OV, 0, "\"class\" <> 'protected'")])
lu = vec("brasov_landuse_infrastructure", "landuse", "Land use")
rules(lu, [
    ("Built-up area", "\"subtype\" IN ('residential','education','pedestrian','construction')",
     fill(BUILT), 0),
    ("Industrial / commercial", "\"subtype\" = 'developed'", fill(INDUSTRIAL), 0),
    ("Orchard / vineyard / garden", "\"subtype\" = 'horticulture'",
     pattern_fill("#eef6e2", "#6c9a4c", 0.5, 1.8), OV),
    ("Cemetery", "\"subtype\" = 'cemetery'", pattern_fill("#e6eee2", "#555555", 0.9, 2.0,
                                                          "cross2"), OV),
    ("Park / sport", "\"subtype\" IN ('park','recreation','managed')", fill("#dcefd0"), OV),
    ("Quarry", "\"subtype\" = 'resource_extraction'", pattern_fill("#ece4da", "#8a7a6a", 0.45,
                                                                   1.4), 0),
    ("Military area", "\"subtype\" = 'military'", fill("#f6d6d6", "#b04040", 0.2), 0),
])
nat = vec("brasov_topography", "land_natural_areas", "Rock, scree, wetland")
rules(nat, [
    ("Bare rock / scree", "\"subtype\" = 'rock'", pattern_fill("#e9e6e1", "#7d7d7d", 0.35, 1.2), 0),
    ("Wetland / marsh", "\"subtype\" = 'wetland'",
     pattern_fill("#e4f1f8", WATER, 0.9, 2.2, "line"), 0),
])
forest = ras("canopy_height_5m.tif", "Forest & trees")
# discrete classes are "<= value": 0-1 (no canopy) must be its own transparent class
ramp(forest, [(1.5, "#ffffff00", ""), (5, SCRUB, "Scrub / young trees (2-5 m)"),
              (100, FOREST, "Forest / trees (> 5 m)")], method="discrete", vmin=0, vmax=100,
     clip=True)
smooth_raster(forest, zoomed_in="bilinear")
add(g_lc, prot)
add(g_lc, lu)
add(g_lc, nat)
add(g_lc, forest)

# ---- sheet index (overview / locator)
idx = vec("brasov_topographic", "topo_sheet_index_50k", "Sheet index 1:50,000")
rules(idx, [("Sheet 1:50,000", "TRUE", fill("#00000000", "#c0392b", 0.35,
                                                            style="no"), 0)])
label_rules(idx, [(pal("\"sheet\" || '\\n' || \"name\"",
                       text_format(9, "#c0392b", bold=True, buffer=1.0), "horizontal",
                       priority=10, obstacle=False), 0, 0, "")])
add(g_idx, idx, False)
for grp in (g_text, g_bnd, g_tr, g_bld, g_hyd, g_rel, g_shade, g_lc, g_idx):
    grp.setExpanded(False)

county_ext = county.extent()
county_ext.grow(2000)
project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(county_ext, project.crs()))

MAP_LAYERS = [sett, pk, spot, mtn, poi, county, uat, ctx, rail, roads, lines_inf, bld, sp, wa, wl,
              us, ct, shade, prot, lu, nat, forest]
LEGEND_LAYERS = [roads, rail, lines_inf, bld, lu, nat, forest, wl, us, wa, sp, ct, pk, spot,
                 poi, prot, county, uat]


# ---------------------------------------------------------------- layout building blocks
def label_item(lay, text, x, y, w, h, fmt, align=Qt.AlignmentFlag.AlignLeft, html=False):
    it = QgsLayoutItemLabel(lay)
    it.setText(text)
    it.setTextFormat(fmt)
    it.setHAlign(align)
    it.setMode(QgsLayoutItemLabel.Mode.ModeHtml if html else QgsLayoutItemLabel.Mode.ModeFont)
    it.attemptMove(QgsLayoutPoint(x, y))
    it.attemptResize(QgsLayoutSize(w, h))
    lay.addLayoutItem(it)
    return it


def add_grids(mp, km, geo_minutes, ann_size=7.0):
    g1 = QgsLayoutItemMapGrid("Stereo 70 grid (km)", mp)
    mp.grids().addGrid(g1)
    g1.setCrs(project.crs())
    g1.setIntervalX(km * 1000)
    g1.setIntervalY(km * 1000)
    g1.setStyle(QgsLayoutItemMapGrid.GridStyle.Solid)
    gs = QgsLineSymbol.createSimple({"line_color": "80,80,80,140", "line_width": "0.1"})
    g1.setLineSymbol(gs)
    g1.setFrameStyle(QgsLayoutItemMapGrid.FrameStyle.Zebra)
    g1.setFrameWidth(1.4)
    g1.setFramePenSize(0.2)
    g1.setAnnotationEnabled(True)
    g1.setAnnotationFormat(QgsLayoutItemMapGrid.AnnotationFormat.CustomFormat)
    g1.setAnnotationExpression("format_number(@grid_number / 1000, 0)")
    g1.setAnnotationTextFormat(text_format(ann_size, "#202020", buffer=0))
    g1.setAnnotationFrameDistance(0.8)
    g1.setAnnotationPrecision(0)
    for side in (QgsLayoutItemMapGrid.BorderSide.Left, QgsLayoutItemMapGrid.BorderSide.Right,
                 QgsLayoutItemMapGrid.BorderSide.Top, QgsLayoutItemMapGrid.BorderSide.Bottom):
        g1.setAnnotationPosition(QgsLayoutItemMapGrid.AnnotationPosition.OutsideMapFrame, side)
        g1.setAnnotationDirection(QgsLayoutItemMapGrid.AnnotationDirection.Horizontal, side)
    g2 = QgsLayoutItemMapGrid("Geographic (WGS84)", mp)
    mp.grids().addGrid(g2)
    g2.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    g2.setIntervalX(geo_minutes / 60)
    g2.setIntervalY(geo_minutes / 60)
    g2.setStyle(QgsLayoutItemMapGrid.GridStyle.Cross)
    g2.setCrossLength(2.5)
    g2.setLineSymbol(QgsLineSymbol.createSimple({"line_color": "0,0,0,255", "line_width": "0.15"}))
    g2.setFrameStyle(QgsLayoutItemMapGrid.FrameStyle.ExteriorTicks)
    g2.setFrameWidth(2.0)
    g2.setFramePenSize(0.25)
    g2.setAnnotationEnabled(True)
    g2.setAnnotationFormat(QgsLayoutItemMapGrid.AnnotationFormat.DegreeMinute)
    g2.setAnnotationTextFormat(text_format(ann_size - 1, "#404040", italic=True, buffer=0))
    g2.setAnnotationFrameDistance(5.5)
    g2.setAnnotationPrecision(0)
    for side in (QgsLayoutItemMapGrid.BorderSide.Left, QgsLayoutItemMapGrid.BorderSide.Right,
                 QgsLayoutItemMapGrid.BorderSide.Top, QgsLayoutItemMapGrid.BorderSide.Bottom):
        g2.setAnnotationPosition(QgsLayoutItemMapGrid.AnnotationPosition.OutsideMapFrame, side)
        g2.setAnnotationDirection(QgsLayoutItemMapGrid.AnnotationDirection.Horizontal, side)


def legend_item(lay, mp, x, y, w, h, layers, columns=1, size=6.5):
    lg = QgsLayoutItemLegend(lay)
    lg.setLinkedMap(mp)
    lg.setAutoUpdateModel(False)
    lt = lg.model().rootGroup()
    lt.clear()
    for lyr in layers:
        node = lt.addLayer(lyr)
        node.setCustomProperty("legend/title-label", lyr.name())
        if isinstance(lyr, QgsRasterLayer):
            nodes = lg.model().layerLegendNodes(node)
            keep = [i for i, n in enumerate(nodes)
                    if str(n.data(Qt.ItemDataRole.DisplayRole) or "").strip()
                    and not str(n.data(Qt.ItemDataRole.DisplayRole)).startswith("Band ")]
            QgsMapLayerLegendUtils.setLegendNodeOrder(node, keep)
            lg.model().refreshLayerLegend(node)
    for style, sz, bold in ((QgsLegendStyle.Style.Title, 10, True),
                            (QgsLegendStyle.Style.Subgroup, size + 0.5, True),
                            (QgsLegendStyle.Style.SymbolLabel, size, False)):
        ls = lg.style(style)
        ls.setTextFormat(text_format(sz, bold=bold, buffer=0))
        lg.setStyle(style, ls)
    lg.setTitle("Legend")
    lg.setColumnCount(columns)
    lg.setSplitLayer(True)
    lg.setSymbolHeight(2.6)
    lg.setSymbolWidth(7)
    lg.setLegendFilterByMapEnabled(True)
    lg.setResizeToContents(False)
    lg.attemptMove(QgsLayoutPoint(x, y))
    lg.attemptResize(QgsLayoutSize(w, h))
    lay.addLayoutItem(lg)
    return lg


def scalebar(lay, mp, x, y, seg_km, nseg, style="Single Box"):
    sb = QgsLayoutItemScaleBar(lay)
    sb.setStyle(style)
    sb.setLinkedMap(mp)
    sb.applyDefaultSize(QgsUnitTypes.DistanceUnit.DistanceKilometers)
    sb.setUnits(QgsUnitTypes.DistanceUnit.DistanceKilometers)
    sb.setUnitLabel("km")
    sb.setUnitsPerSegment(seg_km)
    sb.setNumberOfSegments(nseg)
    sb.setNumberOfSegmentsLeft(2)
    sb.setHeight(2.2)
    sb.setTextFormat(text_format(7, buffer=0))
    sb.attemptMove(QgsLayoutPoint(x, y))
    lay.addLayoutItem(sb)
    return sb


def north_arrow(lay, x, y, s=12):
    na = QgsLayoutItemPicture(lay)
    na.setPicturePath(QgsApplication.svgPaths()[0] + "/arrows/NorthArrow_04.svg")
    na.attemptMove(QgsLayoutPoint(x, y))
    na.attemptResize(QgsLayoutSize(s, s))
    lay.addLayoutItem(na)


CREDITS = ("Projection: Stereographic 1970 (EPSG:3844), Krasovsky 1940 / Dealul Piscului 1970 "
           "datum. Grid: Stereo 70 km grid; ticks: WGS84 latitude/longitude. Elevations: "
           "Copernicus DEM GLO-30 (EGM2008 geoid, surface model). Contour interval 20 m, index "
           "contours 100 m. Data: © OpenStreetMap contributors / Overture Maps (ODbL); "
           "Copernicus DEM © DLR/Airbus; canopy © Meta & WRI (CC BY 4.0); boundaries ANCPI via "
           "geoBoundaries (CC BY 4.0); derived streams, spot heights: this dataset. "
           "Not an official ANCPI map.")

# ---------------------------------------------------------------- 1:50,000 atlas (A2)
sheet = QgsPrintLayout(project)
sheet.initializeDefaults()
sheet.setName("Topographic map 1:50,000 (A2 atlas)")
sheet.pageCollection().page(0).setPageSize("A2", QgsLayoutItemPage.Orientation.Landscape)
atlas = sheet.atlas()
atlas.setCoverageLayer(idx)
atlas.setEnabled(True)
atlas.setHideCoverage(False)
atlas.setPageNameExpression('"sheet"')
atlas.setSortFeatures(True)
atlas.setSortExpression('"page"')
atlas.setFilenameExpression("\"sheet\" || '_' || regexp_replace(\"name\", '[^A-Za-z0-9ăâîșțĂÂÎȘȚ]+', '_')")

MX, MY, MW, MH = 18, 42, 400, 300
mp = QgsLayoutItemMap(sheet)
mp.attemptSetSceneRect(QRectF(MX, MY, MW, MH))
mp.setCrs(project.crs())
mp.setLayers(MAP_LAYERS)
mp.setKeepLayerSet(True)
mp.setAtlasDriven(True)
mp.setAtlasScalingMode(QgsLayoutItemMap.AtlasScalingMode.Fixed)
mp.setExtent(QgsRectangle(530000, 450000, 550000, 465000))
mp.setScale(50000)
mp.setFrameEnabled(True)
# Multiply over the white page looks identical but makes PDF export rasterize the map body at
# the export dpi: ~7 MB instead of ~23 MB per sheet, and blend modes / patterns render exactly
# as on screen (the vector path drew the forest too pale and dropped some dashed lines).
mp.setBlendMode(QPainter.CompositionMode.CompositionMode_Multiply)
sheet.addLayoutItem(mp)
add_grids(mp, 2, 5)

label_item(sheet, "JUDEȚUL BRAȘOV  ·  TOPOGRAPHIC MAP", MX, 8, 260, 10,
           text_format(17, bold=True, spacing=1.0, buffer=0))
label_item(sheet, "Scale 1:50 000  ·  Brașov County, Romania  ·  built from open data",
           MX, 19, 260, 7, text_format(9, "#404040", buffer=0))
label_item(sheet, "[% \"sheet\" %]", MX + MW - 150, 6, 150, 13,
           text_format(22, "#c0392b", bold=True, buffer=0), Qt.AlignmentFlag.AlignRight)
label_item(sheet, "[% \"name\" %]", MX + MW - 150, 19, 150, 9,
           text_format(13, bold=True, buffer=0), Qt.AlignmentFlag.AlignRight)

# below the map: scale bar, numeric scale, contour note, credits
scalebar(sheet, mp, MX, MY + MH + 13, 1, 4)
label_item(sheet, "1:50 000", MX + 125, MY + MH + 12, 40, 8,
           text_format(12, bold=True, buffer=0))
label_item(sheet, "Contour interval 20 m · index contours every 100 m · 1 grid square = 2 × 2 km",
           MX + 175, MY + MH + 13, 230, 6, text_format(8, buffer=0))
label_item(sheet, CREDITS, MX, MY + MH + 27, MW, 18, text_format(6.5, "#404040", buffer=0))

# right column: locator, adjacent sheets, legend, info
RX, RW = 438, 140
north_arrow(sheet, RX + RW - 14, 6)
loc_idx = QgsVectorLayer(idx.source(), "Sheet locator", "ogr")
rules(loc_idx, [
    ("This sheet", "\"sheet\" = attribute(@atlas_feature, 'sheet')",
     fill("#c0392bcc", "#7b1d14", 0.4), 0),
    ("Other sheets", "\"sheet\" <> attribute(@atlas_feature, 'sheet')",
     fill("#00000000", "#999999", 0.2, style="no"), 0),
])
label_rules(loc_idx, [(pal("substr(\"sheet\", 6)", text_format(4.5, "#555555", buffer=0),
                           "horizontal", obstacle=False), 0, 0, "")])
project.addMapLayer(loc_idx, False)
loc = QgsLayoutItemMap(sheet)
loc.attemptSetSceneRect(QRectF(RX, MY, RW, 105))
loc.setCrs(project.crs())
loc.setLayers([loc_idx, county, ctx])
loc.setKeepLayerSet(True)
le = county.extent()
le.grow(4000)
loc.setExtent(le)
loc.setFrameEnabled(True)
loc.setBackgroundColor(QColor("#fbfbf8"))
sheet.addLayoutItem(loc)
label_item(sheet, "Sheet location in Brașov County", RX, MY - 6, RW, 5,
           text_format(7.5, bold=True, buffer=0))
adj = ("<table style='font-family:Arial;font-size:7.5pt;width:100%;text-align:center;"
       "border-collapse:collapse'>"
       "<tr><td></td><td style='border:0.3px solid #888'>[% \"adj_n\" %]</td><td></td></tr>"
       "<tr><td style='border:0.3px solid #888'>[% \"adj_w\" %]</td>"
       "<td style='border:1px solid #c0392b;font-weight:bold;color:#c0392b'>[% \"sheet\" %]</td>"
       "<td style='border:0.3px solid #888'>[% \"adj_e\" %]</td></tr>"
       "<tr><td></td><td style='border:0.3px solid #888'>[% \"adj_s\" %]</td><td></td></tr>"
       "</table>")
label_item(sheet, "Adjoining sheets", RX, MY + 113, RW, 5, text_format(7.5, bold=True, buffer=0))
label_item(sheet, adj, RX + 10, MY + 119, RW - 20, 18, text_format(7.5, buffer=0), html=True)
legend_item(sheet, mp, RX, MY + 142, RW, 190, LEGEND_LAYERS, columns=2, size=5.8)
project.layoutManager().addLayout(sheet)

# ---------------------------------------------------------------- 1:200,000 overview (A1)
ov = QgsPrintLayout(project)
ov.initializeDefaults()
ov.setName("Overview 1:200,000 with sheet index (A1)")
ov.pageCollection().page(0).setPageSize("A1", QgsLayoutItemPage.Orientation.Landscape)
OX, OY, OW, OH = 18, 44, 600, 480
omp = QgsLayoutItemMap(ov)
omp.attemptSetSceneRect(QRectF(OX, OY, OW, OH))
omp.setCrs(project.crs())
omp.setLayers([idx] + MAP_LAYERS)
omp.setKeepLayerSet(True)
c = county.extent().center()
w, h = OW * 200, OH * 200   # mm * scale / 1000 -> m
omp.setExtent(QgsRectangle(c.x() - w / 2, c.y() - h / 2, c.x() + w / 2, c.y() + h / 2))
omp.setScale(200000)
omp.setFrameEnabled(True)
omp.setBlendMode(QPainter.CompositionMode.CompositionMode_Multiply)
ov.addLayoutItem(omp)
add_grids(omp, 10, 15, ann_size=8)
label_item(ov, "JUDEȚUL BRAȘOV  ·  TOPOGRAPHIC OVERVIEW", OX, 8, 450, 12,
           text_format(22, bold=True, spacing=1.2, buffer=0))
label_item(ov, "Scale 1:200 000  ·  with the index of the 29 sheets of the 1:50 000 series "
           "(red)", OX, 22, 450, 8, text_format(11, "#404040", buffer=0))
scalebar(ov, omp, OX, OY + OH + 14, 5, 4)
label_item(ov, "1:200 000", OX + 140, OY + OH + 13, 50, 9, text_format(14, bold=True, buffer=0))
label_item(ov, CREDITS.replace("Contour interval 20 m, index contours 100 m",
                               "Contours: 100 m index contours; 20 m contours on the 1:50 000 "
                               "sheets"), OX, OY + OH + 30, OW, 16,
           text_format(7.5, "#404040", buffer=0))
north_arrow(ov, OX + OW + 190, 8, 16)
legend_item(ov, omp, OX + OW + 16, OY, 200, OH, LEGEND_LAYERS + [idx], columns=1, size=7.5)
project.layoutManager().addLayout(ov)

ok = project.write(str(PROJECT_FILE))
print("project written:", ok, PROJECT_FILE)

# ---------------------------------------------------------------- exports
if EXPORT:
    pdf = QgsLayoutExporter.PdfExportSettings()
    pdf.dpi = 250
    pdf.appendGeoreference = True          # georeferenced PDF (opens aligned in QGIS/GIS)
    pdf.exportMetadata = True
    pdf.rasterizeWholeImage = False
    pdf.simplifyGeometries = True
    pdf.textRenderFormat = Qgis.TextRenderFormat.AlwaysText
    only = [a for a in sys.argv if a.startswith("--sheet=")]
    only = only[0].split("=", 1)[1].split(",") if only else None
    atlas.beginRender()
    n = 0
    for i in range(atlas.count()):
        atlas.seekTo(i)
        sid = atlas.nameForPage(i)
        if only and sid not in only:
            continue
        fn = SHEETS_DIR / f"{atlas.currentFilename()}.pdf"
        res = QgsLayoutExporter(sheet).exportToPdf(str(fn), pdf)
        n += 1
        print(f"  {sid} -> {fn.name} ({fn.stat().st_size / 1e6:.1f} MB) result={res}", flush=True)
        if sid in ("BV50-E4", "BV50-F3"):
            img = QgsLayoutExporter.ImageExportSettings()
            img.dpi = 90
            QgsLayoutExporter(sheet).exportToImage(str(DOCS / f"topo_sheet_{sid}.png"), img)
    atlas.endRender()
    if not only:
        res = QgsLayoutExporter(ov).exportToPdf(str(MAPS / "brasov_topographic_overview_200k.pdf"),
                                                pdf)
        img = QgsLayoutExporter.ImageExportSettings()
        img.dpi = 60
        QgsLayoutExporter(ov).exportToImage(str(DOCS / "topo_overview_200k.png"), img)
        print("overview:", res)
app.exitQgis()
