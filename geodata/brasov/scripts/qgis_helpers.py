"""Shared PyQGIS styling helpers for the Brașov projects (10_qgis_project.py, 13_topo_project.py).
Call only after a QgsApplication has been initialised."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis, QgsCategorizedSymbolRenderer, QgsColorRampShader, QgsFillSymbol,
    QgsGeometryGeneratorSymbolLayer, QgsLineSymbol, QgsMarkerSymbol, QgsPalLayerSettings,
    QgsPalettedRasterRenderer, QgsProperty, QgsRasterDataProvider, QgsRasterShader,
    QgsRendererCategory, QgsRuleBasedLabeling, QgsRuleBasedRenderer, QgsSimpleLineSymbolLayer,
    QgsSingleBandPseudoColorRenderer, QgsTextBufferSettings, QgsTextFormat,
    QgsVectorLayerSimpleLabeling,
)


def qc(c: str) -> QColor:
    """'#RRGGBB' or '#RRGGBBAA' (CSS order; Qt would read 8 digits as #AARRGGBB)."""
    if len(c) == 9:
        return QColor(int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16), int(c[7:9], 16))
    return QColor(c)


def pc(c: str) -> str:
    """Colour as a QGIS symbol property string 'r,g,b,a'."""
    q = qc(c)
    return f"{q.red()},{q.green()},{q.blue()},{q.alpha()}"


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
