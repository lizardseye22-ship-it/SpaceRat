"""SpaceRat — плата v3: односторонняя, под фоторезист (шаблон — лазерная печать на плёнке).

Blue Pill ставится на гнёзда со стороны БЕЗ меди, ноги паяются на медь; USB-разъём
выступает за левый край. Всё остальное — на стороне меди, между рядами гнёзд:
C1/C2 (1206) и площадки под провода (без отверстий, провод паяется сверху на площадку).

Генерирует в этой папке:
  spacerat_film.svg / .pdf  — шаблоны на плёнку 1:1: негатив (плёночный фоторезист)
                              и позитив (жидкий позитивный), по 2 копии
  spacerat_assembly.svg     — сборка: вид сверху (Blue Pill) и снизу (медь)
и проверяет плату: зазоры между цепями, связность каждой цепи, связность земли.

Запуск: python3 gen_pcb.py   (нужен shapely: pip install shapely; для PDF — Chromium)
Размеры в мм. Координаты — вид СВЕРХУ, со стороны Blue Pill (медь снизу, «на просвет»):
x вправо, y вниз, начало — левый верхний угол платы, USB слева.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------ параметры ---
P = 2.54                   # шаг гребёнки и площадок
ROWS = 15.24               # между рядами гнёзд Blue Pill (0.6")
PAD_D, DRILL = 1.8, 0.9    # площадка гнезда, сверло
EDGE = 1.08                # от края платы до меди (центр крайнего пина — 1.98 мм)
W = 19 * P + 2 * (PAD_D / 2 + EDGE)        # 52.22
H = ROWS + 2 * (PAD_D / 2 + EDGE)          # 19.20
X0 = YT = PAD_D / 2 + EDGE                 # центр пина 0 верхнего ряда
YB = YT + ROWS
TW, PW = 0.8, 1.0          # дорожка сигнала / питания
CLEAR = 0.6                # зазор заливки до чужих цепей
MIN_CLEAR = 0.5            # минимально допустимый зазор (проверка)
WP_W, WP_L = 1.8, 2.8      # площадка под провод (овал)
SMD_A, SMD_B, SMD_PITCH = 1.8, 1.6, 3.4   # площадка 1206: поперёк × вдоль, шаг центров

# Blue Pill сверху, USB слева (стандартная распиновка).
TOP = ['B12', 'B13', 'B14', 'B15', 'A8', 'A9', 'A10', 'A11', 'A12', 'A15',
       'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9', '5V', 'G', '3.3']
BOT = ['G', 'G', '3.3', 'R', 'B11', 'B10', 'B1', 'B0', 'A7', 'A6',
       'A5', 'A4', 'A3', 'A2', 'A1', 'A0', 'C15', 'C14', 'C13', 'VB']


def xk(k):
    return X0 + P * k


# --------------------------------------------------------------- модель ---
pads = []      # dict(net, x, y, kind, label, group)
smds = []      # dict(ref, val, x, y, nets)  — вертикальные: верх net1, низ net2
traces = []    # dict(net, pts, w)


def pad(net, x, y, kind, label='', group=''):
    pads.append(dict(net=net, x=x, y=y, kind=kind, label=label, group=group))


def pad_geom(p_):
    if p_['kind'] == 'hdr':
        return Point(p_['x'], p_['y']).buffer(PAD_D / 2, 32)
    d = (WP_L - WP_W) / 2
    return LineString([(p_['x'], p_['y'] - d), (p_['x'], p_['y'] + d)]).buffer(WP_W / 2, 32)


def trace(net, pts, w=TW):
    traces.append(dict(net=net, pts=pts, w=w))


def smd(ref, val, x, y, net1, net2):
    smds.append(dict(ref=ref, val=val, x=x, y=y, nets=(net1, net2)))


def smd_pads(s):
    h = SMD_PITCH / 2
    return [(s['nets'][0], s['x'], s['y'] - h), (s['nets'][1], s['x'], s['y'] + h)]


# ------------------------------------------------------ гнёзда Blue Pill ---
USED_TOP = {'A8', 'A15', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9', '5V', 'G'}
USED_BOT = {'G', '3.3', 'A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7'}


def pin_net(name, used):
    if name == 'G':
        return 'GND'
    if name == '3.3':
        return '3V3' if used else 'nc_3V3_top'
    return name if used else 'nc_' + name


for k, n in enumerate(TOP):
    pad(pin_net(n, n in USED_TOP), xk(k), YT, 'hdr', n, 'bp')
for k, n in enumerate(BOT):
    pad(pin_net(n, n in USED_BOT), xk(k), YB, 'hdr', n, 'bp')

# ------------------------------------ площадки под провода, между рядами ---
YU = YT + 3.9              # верхний ряд: кольцо, энкодер, кнопки
YL = YB - 3.9              # нижний ряд: питание и выходы датчиков
YCOMB = YT + 7.6           # гребёнка +3.3 между рядами

# верхний ряд — прямо под своими пинами
UPPER = [(4, 'A8', 'DIN'), (8, 'GND', 'GND'), (9, 'A15', 'ENC A'), (10, 'B3', 'ENC B'), (11, 'B4', 'ENC SW'),
         (12, 'B5', 'SW1'), (13, 'B6', 'SW2'), (14, 'B7', 'SW3'), (15, 'B8', 'SW4'), (16, 'B9', 'SW5'),
         (17, '5V', '5V'), (18, 'GND', 'GND')]
for k, net, lab in UPPER:
    grp = 'ring' if k in (4, 17, 18) else 'btn'
    pad(net, xk(k), YU, 'wire', lab, grp)
    if TOP[k] != 'A12':                       # под A12 (USB D+) площадка GND без связи с пином
        trace(net, [(xk(k), YT), (xk(k), YU)], PW if net in ('5V', 'GND') else TW)

# нижний ряд: земля и +3.3 для датчиков, выходы датчиков — прямо над своими пинами
SENSE = {'A7': 'B3', 'A6': 'A3', 'A5': 'B2', 'A4': 'A2', 'A3': 'B1', 'A2': 'A1', 'A1': 'B0', 'A0': 'A0'}
for k in (0, 1):
    pad('GND', xk(k), YL, 'wire', 'GND', 'spwr')
    trace('GND', [(xk(k), YB), (xk(k), YL)], PW)
for k in (2, 3, 4, 5):
    pad('3V3', xk(k), YL, 'wire', '+3.3', 'spwr')
for k in (6, 7):
    pad('GND', xk(k), YL, 'wire', 'GND', 'spwr')
for pin, lab in SENSE.items():
    k = BOT.index(pin)
    pad(pin, xk(k), YL, 'wire', lab, 'sens')
    trace(pin, [(xk(k), YB), (xk(k), YL)])

# +3.3: пин -> площадка k2 -> гребёнка -> площадки k3..k5; C1, C2 — на гребёнке
trace('3V3', [(xk(2), YB), (xk(2), YL)], PW)
trace('3V3', [(xk(2), YL), (xk(2), YCOMB), (xk(5), YCOMB)], PW)
for k in (3, 4, 5):
    trace('3V3', [(xk(k), YCOMB), (xk(k), YL)], PW)
YCAP = YCOMB - SMD_PITCH / 2 + 0.3          # C: верх — GND, низ — на гребёнке +3.3
smd('C1', '10 мкФ', xk(2), YCAP, 'GND', '3V3')
smd('C2', '100 нФ', xk(3), YCAP, 'GND', '3V3')

# ============================================================ геометрия ===
features = [(p_['net'], pad_geom(p_)) for p_ in pads]
for s in smds:
    for net, x, y in smd_pads(s):
        features.append((net, box(x - SMD_A / 2, y - SMD_B / 2, x + SMD_A / 2, y + SMD_B / 2)))
for t in traces:
    features.append((t['net'], LineString(t['pts']).buffer(t['w'] / 2, 16)))

nets = sorted({n for n, _ in features})
net_geom = {n: unary_union([g for m, g in features if m == n]) for n in nets}

board = box(0, 0, W, H)
inner = board.buffer(-EDGE + 0.01, join_style=2)
others = unary_union([net_geom[n].buffer(CLEAR, 16) for n in nets if n != 'GND'])
pour = inner.difference(others)
pour = pour.buffer(-0.3, 16).buffer(0.3, 16)          # убрать перемычки уже 0.6 мм
gnd_all = unary_union([pour, net_geom['GND']])
gnd_pins = [Point(p_['x'], p_['y']) for p_ in pads if p_['net'] == 'GND' and p_['group'] == 'bp']
parts = list(gnd_all.geoms) if gnd_all.geom_type == 'MultiPolygon' else [gnd_all]
keep = [pp for pp in parts if any(pp.contains(gp) for gp in gnd_pins)]
dropped = len(parts) - len(keep)
net_geom['GND'] = unary_union(keep)

# ============================================================== проверка ===
errors = []
for n in nets:
    g = net_geom[n]
    if g.geom_type != 'Polygon':
        errors.append(f'цепь {n}: не соединена ({len(g.geoms)} кусков)')
    if not board.buffer(-EDGE + 0.02, join_style=2).contains(g):
        errors.append(f'цепь {n}: ближе {EDGE} мм к краю платы')
min_gap = 99.0
for i, a in enumerate(nets):
    for b in nets[i + 1:]:
        d = net_geom[a].distance(net_geom[b])
        min_gap = min(min_gap, d)
        if d < MIN_CLEAR - 1e-6:
            errors.append(f'зазор {a} — {b}: {d:.2f} мм < {MIN_CLEAR}')
for p_ in pads:
    if not net_geom[p_['net']].contains(Point(p_['x'], p_['y'])):
        errors.append(f'площадка {p_["label"]} ({p_["x"]:.1f},{p_["y"]:.1f}) не на своей цепи')
for s in smds:
    for net, x, y in smd_pads(s):
        if not net_geom[net].contains(Point(x, y)):
            errors.append(f'{s["ref"]}: площадка {net} не на своей цепи')

print(f'плата {W:.1f}×{H:.1f} мм; цепей: {len(nets)}, площадок: {len(pads)}, SMD: {len(smds)}, дорожек: {len(traces)}')
print(f'минимальный зазор между цепями: {min_gap:.2f} мм, удалено островов заливки: {dropped}')
if errors:
    print('ОШИБКИ:')
    for e in errors:
        print('  -', e)
    sys.exit(1)
print('проверка пройдена')

# ================================================================= SVG ===


def path_d(geom, tf):
    polys = list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [geom]
    out = []
    for poly in polys:
        for ring in [poly.exterior, *poly.interiors]:
            out.append('M' + ' L'.join('%.3f %.3f' % tf(x, y) for x, y in ring.coords) + ' Z')
    return ' '.join(out)


copper = unary_union(list(net_geom.values()))
TEXT_AT = (xk(13.5), YCOMB + 0.9)          # надпись в заливке, между рядами площадок

# ---------------------------------------------------- шаблоны на плёнку ---
# Плёнка кладётся тонером к меди, поэтому печать = вид сверху (как в этом файле).
# Негатив: медь прозрачная, остальное чёрное (плёночный фоторезист).
# Позитив: медь чёрная (жидкий позитивный фоторезист).
PAGE_W, PAGE_H = 180.0, 150.0
M = 4.0                                       # чёрное поле вокруг негатива


def film(ox, oy, negative):
    def tf(x, y):
        return ox + x, oy + y
    ink, bg = ('#fff', '#000') if negative else ('#000', '#fff')
    o = []
    if negative:
        o.append(f'<rect x="{ox - M}" y="{oy - M}" width="{W + 2 * M}" height="{H + 2 * M}" fill="#000"/>')
    o.append(f'<path d="{path_d(copper, tf)}" fill="{ink}" fill-rule="evenodd"/>')
    o.append(f'<rect x="{ox}" y="{oy}" width="{W}" height="{H}" fill="none" stroke="{ink}" stroke-width="0.15"/>')
    for p_ in pads:
        if p_['kind'] == 'hdr':
            x, y = tf(p_['x'], p_['y'])
            o.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="0.3" fill="{bg}"/>')
    tx, ty = tf(*TEXT_AT)
    o.append(f'<text transform="translate({tx:.2f} {ty:.2f}) scale(-1 1)" font-size="1.8" font-weight="bold" '
             f'text-anchor="middle" fill="{bg}">SPACERAT v3</text>')
    return o


o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{PAGE_W}mm" height="{PAGE_H}mm" '
     f'viewBox="0 0 {PAGE_W} {PAGE_H}" font-family="DejaVu Sans, Arial, sans-serif">',
     f'<rect width="{PAGE_W}" height="{PAGE_H}" fill="#fff"/>',
     '<text x="8" y="8" font-size="3.4" font-weight="bold">SpaceRat v3 — шаблоны на плёнку, 1:1</text>',
     '<text x="8" y="13" font-size="2.6">Печать 100 %, без масштабирования и БЕЗ зеркала. Плёнку класть тонером к меди.</text>',
     '<text x="8" y="17.5" font-size="2.6">Надпись SPACERAT на плёнке зеркальная — так и нужно; на готовой меди читается прямо.</text>']
col = (8 + M, 8 + M + W + 2 * M + 14)
for row, (neg, title) in enumerate(((True, 'НЕГАТИВ — плёночный фоторезист (медь = прозрачное)'),
                                    (False, 'ПОЗИТИВ — жидкий позитивный фоторезист (медь = чёрное)'))):
    ty = 30 + row * 50
    o.append(f'<text x="8" y="{ty - 6}" font-size="2.8" font-weight="bold">{title}</text>')
    for cx in col:
        o += film(cx, ty, neg)
ry = 132
o.append(f'<path d="M8 {ry} H58" stroke="#000" stroke-width="0.3"/>')
for i in range(6):
    o.append(f'<path d="M{8 + 10 * i} {ry - 1.5} V{ry + 1.5}" stroke="#000" stroke-width="0.3"/>')
o.append(f'<text x="8" y="{ry + 5}" font-size="2.6">50 мм — проверить линейкой. Плата {W:.1f} × {H:.1f} мм.</text>')
o.append(f'<text x="8" y="{ry + 9.5}" font-size="2.6">Две копии — можно сложить две плёнки для плотности.</text>')
o.append('</svg>')
with open(os.path.join(HERE, 'spacerat_film.svg'), 'w') as f:
    f.write('\n'.join(o))

# ------------------------------------------------- сборочный чертёж ---
S = 16.0
OX1, OY = 90, 220
OX2 = OX1 + W * S + 170
AW = int(OX2 + W * S + 90)
AH = int(OY + H * S + 360)
BP_X0, BP_X1 = X0 - 2.37, X0 + 19 * P + 2.37       # Blue Pill 53 мм
BP_Y0, BP_Y1 = YT - 3.81, YB + 3.81                 # 22.86 мм


def tf_top(x, y):
    return OX1 + x * S, OY + y * S


def tf_bot(x, y):                                   # вид снизу — зеркально
    return OX2 + (W - x) * S, OY + y * S


a = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{AW}" height="{AH}" viewBox="0 0 {AW} {AH}" '
     'font-family="DejaVu Sans, Arial, sans-serif">',
     '''<style>.t{font-size:15px;fill:#2b2a27}.s{font-size:12px;fill:#2b2a27}.b{font-weight:bold}
.lab{font-size:11.5px;fill:#1f1e1b;font-weight:bold}.pin{font-size:10px;fill:#123a73;font-weight:bold}
.ref{font-size:10px;fill:#fff;font-weight:bold}</style>''',
     f'<rect width="{AW}" height="{AH}" fill="#faf8f3"/>',
     '<text x="30" y="42" class="t b" style="font-size:24px">SpaceRat — плата v3: сборка</text>',
     f'<text x="30" y="70" class="t" style="fill:#55524c">Односторонняя {W:.1f}×{H:.1f} мм, фоторезист. '
     'Blue Pill — со стороны без меди, USB выступает за левый край; ноги паяются на медь.</text>']

# ---- вид сверху: только плата и Blue Pill
x0, y0 = tf_top(0, 0)
a.append(f'<text x="{x0}" y="{OY - 95}" class="t b">Вид сверху — сторона Blue Pill (меди нет)</text>')
a.append(f'<rect x="{x0}" y="{y0}" width="{W * S}" height="{H * S}" fill="#e3dccb" stroke="#6b5a2e" stroke-width="1.5"/>')
bx, by = tf_top(BP_X0, BP_Y0)
a.append(f'<rect x="{bx}" y="{by}" width="{(BP_X1 - BP_X0) * S}" height="{(BP_Y1 - BP_Y0) * S}" rx="6" '
         'fill="#2b62b0" fill-opacity="0.85" stroke="#123a73" stroke-width="2"/>')
ux, uy = tf_top(BP_X0, YT + ROWS / 2)
a.append(f'<rect x="{ux - 34}" y="{uy - 60}" width="42" height="120" rx="4" fill="#b8bec4" stroke="#123a73" stroke-width="2"/>')
a.append(f'<text transform="translate({ux - 9} {uy}) rotate(-90)" class="s b" text-anchor="middle">USB</text>')
for k in range(20):
    for yy, names, dy in ((YT, TOP, 30), (YB, BOT, -20)):
        x, y = tf_top(xk(k), yy)
        a.append(f'<circle cx="{x}" cy="{y}" r="{0.64 * S / 2 + 2}" fill="#1b1b1b"/>')
        a.append(f'<text x="{x}" y="{y + dy}" class="pin" text-anchor="middle" style="fill:#fff">{names[k]}</text>')
x0, y0 = tf_top(0, 0)
a.append(f'<rect x="{x0}" y="{y0}" width="{W * S}" height="{H * S}" fill="none" stroke="#f2c14e" stroke-width="3" '
         'stroke-dasharray="10 6"/>')
a.append(f'<text x="{x0 + W * S}" y="{y0 + H * S + 70}" class="s b" text-anchor="end">'
         '<tspan style="fill:#c98a00">- - -</tspan> край платы: USB выступает за левый край</text>')
cx, cy = tf_top(X0 + 9.5 * P, YT + ROWS / 2)
a.append(f'<text x="{cx}" y="{cy - 4}" class="t b" text-anchor="middle" style="fill:#fff;font-size:22px">Blue Pill</text>')
a.append(f'<text x="{cx}" y="{cy + 18}" class="s" text-anchor="middle" style="fill:#fff">компонентами вверх, USB влево</text>')

# ---- вид снизу: медь, SMD, площадки
x0, y0 = tf_bot(W, 0)
a.append(f'<text x="{x0}" y="{OY - 95}" class="t b">Вид снизу — сторона меди (пайка), зеркально</text>')
a.append(f'<rect x="{x0}" y="{y0}" width="{W * S}" height="{H * S}" fill="#e6d3a3" stroke="#6b5a2e" stroke-width="1.5"/>')
COL = {'GND': '#c9a86a', '3V3': '#e8914f', '5V': '#e8914f'}
for n in nets:
    a.append(f'<path d="{path_d(net_geom[n], tf_bot)}" fill="{COL.get(n, "#b87333")}" fill-rule="evenodd"/>')
for p_ in pads:
    if p_['kind'] == 'hdr':
        x, y = tf_bot(p_['x'], p_['y'])
        a.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{DRILL / 2 * S:.1f}" fill="#faf8f3"/>')
        a.append(f'<text x="{x:.1f}" y="{y + (-16 if p_["y"] < H / 2 else 25):.1f}" class="pin" '
                 f'text-anchor="middle">{p_["label"]}</text>')
for s in smds:
    (_, xa, ya), (_, xb, yb) = smd_pads(s)
    cx, cy = tf_bot((xa + xb) / 2, (ya + yb) / 2)
    a.append(f'<rect x="{cx - 0.8 * S:.1f}" y="{cy - 1.6 * S:.1f}" width="{1.6 * S:.1f}" height="{3.2 * S:.1f}" '
             'fill="#2e2b28" stroke="#111" rx="2"/>')
    a.append(f'<text transform="translate({cx + 4:.1f} {cy:.1f}) rotate(-90)" class="ref" text-anchor="middle">{s["ref"]}</text>')
for p_ in pads:
    if p_['kind'] != 'wire':
        continue
    x, y = tf_bot(p_['x'], p_['y'])
    a.append(f'<text transform="translate({x + 3.5:.1f} {y:.1f}) rotate(-90)" class="lab" text-anchor="middle" '
             f'style="fill:#fff;font-size:{9 if len(p_["label"]) > 4 else 10}px">{p_["label"]}</text>')
ux, uy = tf_bot(0, YT + ROWS / 2)
a.append(f'<text x="{ux + 10}" y="{uy + 5}" class="s b">← USB</text>')


def bracket(k0, k1, y_mm, text, below):
    xa_, yy = tf_bot(xk(k0) - 1.0, y_mm)
    xb_, _ = tf_bot(xk(k1) + 1.0, y_mm)
    x1_, x2_ = min(xa_, xb_), max(xa_, xb_)
    a.append(f'<path d="M{x1_} {yy} H{x2_}" stroke="#2b2a27" stroke-width="1.5"/>')
    a.append(f'<text x="{(x1_ + x2_) / 2}" y="{yy + (18 if below else -8)}" class="s b" text-anchor="middle">{text}</text>')


bracket(8, 16, -3.2, 'энкодер + кнопки', False)
bracket(17, 18, -3.2, 'кольцо', False)
bracket(4, 4, -3.2, 'DIN', False)
bracket(0, 7, H + 3.2, 'питание датчиков', True)
for p, k0 in ((3, 8), (2, 10), (1, 12), (0, 14)):
    bracket(k0, k0 + 1, H + 3.2, f'пара {p}', True)

ly = OY + H * S + 150
notes = [
    'Порядок: 1) C1 (10 мкФ) и C2 (100 нФ), 1206 — на медь; 2) гнёзда 1×20 — сверху, пайка на медь;',
    '   3) провода — на площадки между рядами (без отверстий, лудить и паять сверху); 4) Blue Pill в гнёзда.',
    'Датчики: пара p = 4 провода — её A и B + по одному +3.3 и GND из группы «питание датчиков».',
    '   A0 → U1 (PA0), B0 → U2, A1 → U3, B1 → U4, A2 → U5, B2 → U6, A3 → U7, B3 → U8 (PA7).',
    'Кнопки SW1–SW5 → PB5–PB9, энкодер A/B → PA15/PB3, кнопка энкодера → PB4; вторые выводы — на GND.',
    'Кольцо: 5V, DIN (PA8), GND; подтяжка R9 1 кОм (DIN–5V) и 470 мкФ + 100 нФ — у кольца.',
    'Сверло 0.9 мм — только гнёзда Blue Pill.',
]
a.append(f'<text x="{OX1}" y="{ly}" class="t b">Сборка</text>')
for i, line in enumerate(notes):
    a.append(f'<text x="{OX1}" y="{ly + 24 + 20 * i}" class="s" style="font-size:13px">{line}</text>')
a.append('</svg>')
with open(os.path.join(HERE, 'spacerat_assembly.svg'), 'w') as f:
    f.write('\n'.join(a))

# ---------------------------------------------------------------- PDF ---
chrome = shutil.which('chromium') or shutil.which('google-chrome') or next(
    iter(glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')), None)
if chrome:
    svg = open(os.path.join(HERE, 'spacerat_film.svg')).read()
    inline = svg.replace('<svg ', '<svg style="position:absolute;left:15mm;top:15mm" ', 1)
    html = (f'<html><head><style>@page{{size:210mm 297mm;margin:0}}body{{margin:0}}</style></head><body>'
            f'{inline}</body></html>')
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False) as f:
        f.write(html)
    subprocess.run([chrome, '--headless', '--no-sandbox', '--no-pdf-header-footer',
                    f'--print-to-pdf={os.path.join(HERE, "spacerat_film.pdf")}', 'file://' + f.name],
                   check=True, capture_output=True)
    os.unlink(f.name)
    print('PDF: spacerat_film.pdf (A4, 1:1)')
else:
    print('Chromium не найден — PDF не создан, печатайте SVG в масштабе 100 %')
print('файлы: spacerat_film.svg, spacerat_assembly.svg')
