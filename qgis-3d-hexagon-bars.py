import math
from collections import defaultdict
from qgis.core import (
    QgsProject, QgsFeature, QgsGeometry, QgsField,
    QgsVectorLayer, QgsPointXY, QgsGraduatedSymbolRenderer,
    QgsSymbol, QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsRendererRange
)
from PyQt5.QtCore import QVariant
from PyQt5.QtGui import QColor

# ───────── PARAMETERS ─────────
field_name      = "HEIGHT"     # Fieldname for height
value_multiplier = 5           # Multiplier
height_scale    = 5000         # Height scale
hex_scale       = 0.4          # Hexagon width
base_opacity    = 0.9          # Bars opacity
vertical_offset = 5            # Vertical offset 
colors = [                     # Colors
    "#c3964e",
    "#d7bc98",
    "#e0cbaf",
    "#e9dac6",
    "#f2e9dd",
    "#fbf8f4"
]

# ───────── AGGREGATION ─────────
src = iface.activeLayer()
agg = defaultdict(lambda: {"geom": None, "value": 0})

for f in src.getFeatures():
    fid = f["id"]
    val = (f[field_name] or 0) * value_multiplier
    if agg[fid]["geom"] is None:
        agg[fid]["geom"] = f.geometry()
    agg[fid]["value"] += val

# ───────── CREATE 3D LAYER ─────────
crs_src  = src.crs()
crs_dest = QgsCoordinateReferenceSystem("EPSG:3395")
xform    = QgsCoordinateTransform(crs_src, crs_dest, QgsProject.instance())

layer = QgsVectorLayer("Polygon?crs=EPSG:3395", "hex_bar_3D", "memory")
prov  = layer.dataProvider()
prov.addAttributes([QgsField("value", QVariant.Double), QgsField("fid_src", QVariant.Int)])
layer.updateFields()

def hexagon(c, r):
    pts = [QgsPointXY(c.x()+r*math.cos(math.radians(60*i)),
                      c.y()+r*math.sin(math.radians(60*i))) for i in range(6)]
    pts.append(pts[0])
    return pts

def extrude(b, z0, z1):
    out = []
    for i in range(6):
        p1, p2 = b[i], b[i+1]
        out.append([QgsPointXY(p1.x(), p1.y()+z0),
                    QgsPointXY(p2.x(), p2.y()+z0),
                    QgsPointXY(p2.x(), p2.y()+z1),
                    QgsPointXY(p1.x(), p1.y()+z1),
                    QgsPointXY(p1.x(), p1.y()+z0)])
    return out

def roof(b, z):
    ring = [QgsPointXY(p.x(), p.y()+z) for p in b[:-1]] + [QgsPointXY(b[0].x(), b[0].y()+z)]
    return ring

for fid, d in agg.items():
    if d["value"] == 0:
        continue
    g = QgsGeometry(d["geom"])
    g.transform(xform)
    cen = g.centroid().asPoint()
    R = g.boundingBox().width() / 2 * hex_scale
    base = hexagon(cen, R)
    h = d["value"] * height_scale
    z = vertical_offset
    for face in extrude(base, z, z + h):
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPolygonXY([face]))
        f.setAttributes([d["value"], fid])
        prov.addFeature(f)
    rf = QgsFeature()
    rf.setGeometry(QgsGeometry.fromPolygonXY([roof(base, z + h)]))
    rf.setAttributes([d["value"], fid])
    prov.addFeature(rf)

# ───────── STYLING WITH CUSTOM RAMP ─────────
layer.updateExtents()
QgsProject.instance().addMapLayer(layer)

values = [f["value"] for f in layer.getFeatures()]
vmin, vmax = min(values), max(values)

classes = len(colors)
step = (vmax - vmin) / classes if vmax > vmin else 1
ranges = []
for i, hexcol in enumerate(colors):
    lower = vmin + i * step
    upper = lower + step
    sym = QgsSymbol.defaultSymbol(layer.geometryType())
    sym.setColor(QColor(hexcol))
    sym.setOpacity(base_opacity)
    sym.symbolLayer(0).setStrokeColor(QColor(0, 0, 0, 100))
    sym.symbolLayer(0).setStrokeWidth(0.2)
    ranges.append(QgsRendererRange(lower, upper, sym,
                  f"{round(lower,1)}–{round(upper,1)}"))

renderer = QgsGraduatedSymbolRenderer("value", ranges)
renderer.setMode(QgsGraduatedSymbolRenderer.GraduatedColor)
layer.setRenderer(renderer)
layer.triggerRepaint()