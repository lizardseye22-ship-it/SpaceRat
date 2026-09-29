"""SpaceRat — односторонняя плата под ЛУТ, всё на стороне меди.

Blue Pill (на гнёздах), все SMD и провода — на стороне меди; обратная сторона гладкая.
RC-фильтры и конденсаторы питания стоят под Blue Pill и сразу под её пинами.

Генерирует в этой папке:
  spacerat_copper_print.svg / .pdf — медь 1:1 для печати (уже зеркальная — печатать как есть)
  spacerat_assembly.svg            — сборочный чертёж (вид на сторону меди)
и проверяет плату: зазоры между цепями, связность каждой цепи, связность заливки земли.

Запуск: python3 gen_pcb.py     (нужен shapely: pip install shapely; для PDF — Chromium)
Размеры в мм. Координаты — вид НА СТОРОНУ МЕДИ (как видно при сборке),
x вправо, y вниз, начало — левый верхний угол платы.
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
W, H = 60.0, 37.0          # плата
P = 2.54                   # шаг гребёнки и площадок
TW, PW = 0.8, 1.2          # дорожка сигнала / питания
CLEAR = 0.6                # зазор заливки до чужих цепей
MIN_CLEAR = 0.5            # минимально допустимый зазор (проверка)
EDGE = 1.0                 # медь не ближе к краю платы
PAD_D, DRILL = 1.8, 0.9    # круглая площадка гнезда Blue Pill, сверло
OBL_L = 2.8                # длина овальной площадки под провод (ширина = PAD_D)
SMD_A, SMD_B, SMD_PITCH = 1.8, 1.6, 3.4   # площадка 1206: поперёк × вдоль, шаг центров
MOUNT_D, MOUNT_KEEP = 3.2, 3.0            # крепёж М3 и радиус без меди

# Blue Pill сверху (как стоит на плате), USB слева.
# Ряды гнёзд: 20 пинов, шаг 2.54, между рядами 15.24 (0.6").
X0, YT = 3.5, 9.0
YB = YT + 15.24
TOP = ['B12', 'B13', 'B14', 'B15', 'A8', 'A9', 'A10', 'A11', 'A12', 'A15',
       'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9', '5V', 'G', '3.3']
BOT = ['G', 'G', '3.3', 'R', 'B11', 'B10', 'B1', 'B0', 'A7', 'A6',
       'A5', 'A4', 'A3', 'A2', 'A1', 'A0', 'C15', 'C14', 'C13', 'VB']


def xk(k):
    return X0 + P * k


# --------------------------------------------------------------- модель ---
pads = []      # dict(net, x, y, shape, label, group)
smds = []      # dict(ref, val, x, y, orient, nets)
traces = []    # dict(net, pts, w)
holes = []     # (x, y)


def pad(net, x, y, shape='round', label='', group=''):
    """shape: round (гнездо), v (овал вертикальный), h (овал горизонтальный)."""
    pads.append(dict(net=net, x=x, y=y, shape=shape, label=label, group=group))


def pad_geom(p_):
    x, y = p_['x'], p_['y']
    if p_['shape'] == 'round':
        return Point(x, y).buffer(PAD_D / 2, 32)
    d = (OBL_L - PAD_D) / 2
    seg = [(x, y - d), (x, y + d)] if p_['shape'] == 'v' else [(x - d, y), (x + d, y)]
    return LineString(seg).buffer(PAD_D / 2, 32)


def trace(net, pts, w=TW):
    traces.append(dict(net=net, pts=pts, w=w))


def smd(ref, val, x, y, orient, net1, net2):
    """orient 'v': площадки сверху (net1) и снизу (net2); 'h': слева (net1) и справа (net2)."""
    smds.append(dict(ref=ref, val=val, x=x, y=y, orient=orient, nets=(net1, net2)))


def smd_pads(s):
    h = SMD_PITCH / 2
    if s['orient'] == 'v':
        return [(s['nets'][0], s['x'], s['y'] - h, SMD_A, SMD_B), (s['nets'][1], s['x'], s['y'] + h, SMD_A, SMD_B)]
    return [(s['nets'][0], s['x'] - h, s['y'], SMD_B, SMD_A), (s['nets'][1], s['x'] + h, s['y'], SMD_B, SMD_A)]


# ------------------------------------------------------ гнёзда Blue Pill ---
USED_TOP = {'B12', 'B13', 'B14', 'B15', 'A8', 'B5', 'B6', 'B7', 'B8', '5V', 'G'}
USED_BOT = {'G', '3.3', 'A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7'}


def pin_net(name, used):
    if name == 'G':
        return 'GND'
    if name == '3.3':
        return '3V3' if used else 'nc_3V3_top'
    return name if used else 'nc_' + name


for k, n in enumerate(TOP):
    pad(pin_net(n, n in USED_TOP), xk(k), YT, 'round', n, 'bp')
for k, n in enumerate(BOT):
    pad(pin_net(n, n in USED_BOT), xk(k), YB, 'round', n, 'bp')

# ------------------------------------------------------------- датчики ---
# Каждый вход АЦП — прямой столбик: C (10 нФ, под Blue Pill) — пин — R (1 кОм) — площадка.
YC_NODE, YC_GND = YB - 2.6, YB - 6.0      # C: у пина (узел) и земля
YR_TOP, YR_BOT = YB + 2.6, YB + 6.0       # R: у пина и к площадке
YPAD = YB + 9.4                           # ряд площадок снизу
# вход -> подпись площадки (пара p: A и B) и номер R/C (U-номер = номер PA + 1)
SENSE = {'A7': 'B3', 'A6': 'A3', 'A5': 'B2', 'A4': 'A2', 'A3': 'B1', 'A2': 'A1', 'A1': 'B0', 'A0': 'A0'}
for pin, lab in SENSE.items():
    k = BOT.index(pin)
    x = xk(k)
    n = int(pin[1:]) + 1
    smd(f'C{6 + n}', '10 нФ', x, (YC_NODE + YC_GND) / 2, 'v', 'GND', pin)
    trace(pin, [(x, YB), (x, YC_NODE)])
    smd(f'R{n}', '1 кОм', x, (YR_TOP + YR_BOT) / 2, 'v', pin, 'S_' + pin)
    trace(pin, [(x, YB), (x, YR_TOP)])
    trace('S_' + pin, [(x, YR_BOT), (x, YPAD)])
    pad('S_' + pin, x, YPAD, 'v', lab, 'sens')

# питание датчиков: площадки под пинами G G 3.3 R (земля) и B11..B0 (3.3 В)
k33 = BOT.index('3.3')
Y33 = YB + 4.3
for k in range(4):
    pad('GND', xk(k), YPAD, 'v', 'GND', 'pwr')
for k in range(4, 8):
    pad('3V3', xk(k), YPAD, 'v', '+3.3', 'pwr')
    trace('3V3', [(xk(k), Y33), (xk(k), YPAD)], TW)
trace('3V3', [(xk(k33), YB), (xk(k33), Y33), (xk(7), Y33)], PW)
# C1, C2 — у пина 3.3, под Blue Pill
smd('C1', '10 мкФ', xk(k33), (YC_NODE + YC_GND) / 2, 'v', 'GND', '3V3')
smd('C2', '100 нФ', xk(k33 + 1), (YC_NODE + YC_GND) / 2, 'v', 'GND', '3V3')
trace('3V3', [(xk(k33), YB), (xk(k33), YC_NODE), (xk(k33 + 1), YC_NODE)], PW)

# ------------------------------------------------- кнопки и энкодер (сверху) ---
YTOP = YT - 5.0
for pin, lab in (('B12', 'SW2'), ('B13', 'SW3'), ('B14', 'SW4'), ('B15', 'SW5')):
    x = xk(TOP.index(pin))
    trace(pin, [(x, YT), (x, YTOP)])
    pad(pin, x, YTOP, 'v', lab, 'btn')
pad('GND', xk(4), YTOP, 'v', 'GND', 'btn')
for pin, lab in (('B5', 'ENC S'), ('B6', 'ENC A'), ('B7', 'ENC B'), ('B8', 'SW1')):
    x = xk(TOP.index(pin))
    trace(pin, [(x, YT), (x, YTOP)])
    pad(pin, x, YTOP, 'v', lab, 'enc')
pad('GND', xk(16), YTOP, 'v', 'GND', 'enc')

# ------------------------------------------------------- кольцо WS2812 ---
# 5V и PA8 — под Blue Pill к площадкам справа; R9 (подтяжка PA8 к 5 В) — под Blue Pill.
Y5V, YDIN = YT + 2.8, YT + 5.5
XR9, XRING = 50.0, 55.9
k5, k8 = TOP.index('5V'), TOP.index('A8')
trace('5V', [(xk(k5), YT), (xk(k5), Y5V), (XRING, Y5V)], PW)
trace('A8', [(xk(k8), YT), (xk(k8), YDIN), (XRING, YDIN)])
smd('R9', '1 кОм', XR9, (Y5V + YDIN) / 2 + 0.3, 'v', '5V', 'A8')
trace('5V', [(XR9, Y5V), (XR9, (Y5V + YDIN) / 2 + 0.3 - SMD_PITCH / 2)], PW)
trace('A8', [(XR9, YDIN), (XR9, (Y5V + YDIN) / 2 + 0.3 + SMD_PITCH / 2)])
pad('5V', XRING, Y5V, 'h', '5V', 'ring')
pad('A8', XRING, YDIN, 'h', 'DIN', 'ring')
pad('GND', XRING, YDIN + 2.7, 'h', 'GND', 'ring')

# ----------------------------------------------------------- крепёж ---
holes += [(W - 3.0, 3.2), (W - 3.0, H - 3.2)]

# ============================================================ геометрия ===
features = [(p_['net'], pad_geom(p_)) for p_ in pads]
for s in smds:
    for net, x, y, a, b in smd_pads(s):
        features.append((net, box(x - a / 2, y - b / 2, x + a / 2, y + b / 2)))
for t in traces:
    features.append((t['net'], LineString(t['pts']).buffer(t['w'] / 2, 16)))

nets = sorted({n for n, _ in features})
net_geom = {n: unary_union([g for m, g in features if m == n]) for n in nets}

board = box(0, 0, W, H)
inner = board.buffer(-EDGE, join_style=2)
hole_keep = unary_union([Point(x, y).buffer(MOUNT_KEEP, 32) for x, y in holes])

others = unary_union([net_geom[n].buffer(CLEAR, 16) for n in nets if n != 'GND'])
pour = inner.difference(others).difference(hole_keep)
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
    if n != 'GND' and not inner.buffer(0.01).contains(g):
        errors.append(f'цепь {n}: ближе {EDGE} мм к краю платы')
    if n != 'GND' and g.intersects(hole_keep):
        errors.append(f'цепь {n}: заходит в зону крепёжного отверстия')
min_gap = 99.0
for i, a in enumerate(nets):
    for b in nets[i + 1:]:
        d = net_geom[a].distance(net_geom[b])
        min_gap = min(min_gap, d)
        if d < MIN_CLEAR - 1e-6:
            errors.append(f'зазор {a} — {b}: {d:.2f} мм < {MIN_CLEAR}')
for p_ in pads:
    if p_['net'] == 'GND' and not net_geom['GND'].contains(Point(p_['x'], p_['y'])):
        errors.append(f'площадка GND ({p_["x"]:.1f},{p_["y"]:.1f}) не связана с землёй')
for s in smds:
    for net, x, y, _, _ in smd_pads(s):
        if not net_geom[net].contains(Point(x, y)):
            errors.append(f'{s["ref"]}: площадка {net} не на своей цепи')

print(f'плата {W:.0f}×{H:.0f} мм; цепей: {len(nets)}, площадок: {len(pads)}, SMD: {len(smds)}, дорожек: {len(traces)}')
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
            pts = [tf(x, y) for x, y in ring.coords]
            out.append('M' + ' L'.join(f'{x:.3f} {y:.3f}' for x, y in pts) + ' Z')
    return ' '.join(out)


copper = unary_union(list(net_geom.values()))
TEXT_AT = (50.5, 30.0)   # надпись в заливке (справа снизу, свободное место)

# ---------------------------------------------------- печать для ЛУТа ---
# Бумага кладётся тонером на медь, поэтому печать — зеркало вида на медь.
MX, MY = 14.0, 16.0
PW_, PH_ = W + 2 * MX, H + 2 * MY + 26


def tf_print(x, y):
    return MX + (W - x), MY + y


o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{PW_}mm" height="{PH_}mm" '
     f'viewBox="0 0 {PW_} {PH_}" font-family="DejaVu Sans, Arial, sans-serif">',
     f'<rect width="{PW_}" height="{PH_}" fill="#fff"/>',
     f'<path d="{path_d(copper, tf_print)}" fill="#000" fill-rule="evenodd"/>',
     f'<rect x="{MX}" y="{MY}" width="{W}" height="{H}" fill="none" stroke="#000" stroke-width="0.2"/>']
for p_ in pads:
    x, y = tf_print(p_['x'], p_['y'])
    o.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="0.3" fill="#fff"/>')
for hx, hy in holes:
    x, y = tf_print(hx, hy)
    o.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{MOUNT_D / 2}" fill="none" stroke="#000" stroke-width="0.25"/>')
    o.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="0.35" fill="#000"/>')
tx, ty = tf_print(*TEXT_AT)
o.append(f'<text transform="translate({tx:.2f} {ty:.2f}) scale(-1 1)" font-size="2.0" font-weight="bold" '
         f'text-anchor="middle" fill="#fff">SPACERAT v2</text>')
ry = MY + H + 8
o.append(f'<path d="M{MX} {ry} H{MX + 50}" stroke="#000" stroke-width="0.3"/>')
for i in range(6):
    o.append(f'<path d="M{MX + 10 * i} {ry - 1.5} V{ry + 1.5}" stroke="#000" stroke-width="0.3"/>')
o.append(f'<text x="{MX}" y="{ry + 5}" font-size="3">50 мм — проверить линейкой</text>')
o.append(f'<text x="{MX}" y="{ry + 10}" font-size="3">Печать 100 %, как есть —</text>')
o.append(f'<text x="{MX}" y="{ry + 14.5}" font-size="3">рисунок уже зеркальный.</text>')
o.append(f'<text x="{MX}" y="{ry + 19}" font-size="3">На меди SPACERAT читается прямо.</text>')
o.append(f'<text x="{MX}" y="{MY - 4}" font-size="3">SpaceRat v2 · медь (зеркально, для переноса)</text>')
o.append('</svg>')
with open(os.path.join(HERE, 'spacerat_copper_print.svg'), 'w') as f:
    f.write('\n'.join(o))

# ------------------------------------------------- сборочный чертёж ---
S = 15.0
OX, OY = 70, 200
AW = int(W * S + 2 * OX + 260)
AH = int(OY + H * S + 330)


def tf(x, y):
    return OX + x * S, OY + y * S


NET_COL = {'GND': '#c9a86a', '3V3': '#e8914f', '5V': '#e8914f'}
a = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{AW}" height="{AH}" viewBox="0 0 {AW} {AH}" '
     'font-family="DejaVu Sans, Arial, sans-serif">',
     '''<style>.t{font-size:15px;fill:#2b2a27}.s{font-size:12px;fill:#2b2a27}.b{font-weight:bold}
.lab{font-size:11px;fill:#1f1e1b;font-weight:bold}.pin{font-size:9.5px;fill:#123a73;font-weight:bold}
.ref{font-size:10.5px;fill:#fff;font-weight:bold}</style>''',
     f'<rect width="{AW}" height="{AH}" fill="#faf8f3"/>',
     '<text x="30" y="42" class="t b" style="font-size:24px">SpaceRat — плата v2: сборка</text>',
     f'<text x="30" y="70" class="t" style="fill:#55524c">Односторонняя {W:.0f}×{H:.0f} мм. Вид на сторону меди: '
     'здесь стоит всё — Blue Pill на гнёздах, SMD 1206, провода. Обратная сторона гладкая.</text>']
x0, y0 = tf(0, 0)
a.append(f'<rect x="{x0}" y="{y0}" width="{W * S}" height="{H * S}" fill="#e6d3a3" stroke="#6b5a2e" stroke-width="1.5"/>')
for n in nets:
    a.append(f'<path d="{path_d(net_geom[n], tf)}" fill="{NET_COL.get(n, "#b87333")}" fill-rule="evenodd"/>')
for hx, hy in holes:
    x, y = tf(hx, hy)
    a.append(f'<circle cx="{x}" cy="{y}" r="{MOUNT_D / 2 * S}" fill="#faf8f3" stroke="#6b5a2e"/>')
for p_ in pads:
    x, y = tf(p_['x'], p_['y'])
    a.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{DRILL / 2 * S:.1f}" fill="#faf8f3"/>')
# SMD
for s in smds:
    (_, xa, ya, _, _), (_, xb, yb, _, _) = smd_pads(s)
    cx, cy = tf((xa + xb) / 2, (ya + yb) / 2)
    w_, h_ = (1.6 * S, 3.2 * S) if s['orient'] == 'v' else (3.2 * S, 1.6 * S)
    a.append(f'<rect x="{cx - w_ / 2:.1f}" y="{cy - h_ / 2:.1f}" width="{w_:.1f}" height="{h_:.1f}" '
             'fill="#2e2b28" stroke="#111" rx="2"/>')
    a.append(f'<text transform="translate({cx + 4:.1f} {cy:.1f}) rotate(-90)" class="ref" '
             f'text-anchor="middle">{s["ref"]}</text>')
# Blue Pill: сплошной контур поверх (полупрозрачный), подписи пинов
bx0, by0 = tf(X0 - 2.4, YT - 3.3)
bw, bh = (19 * P + 4.8) * S, (15.24 + 6.6) * S
a.append(f'<rect x="{bx0}" y="{by0}" width="{bw}" height="{bh}" rx="8" fill="#1e5aa8" fill-opacity="0.16" '
         'stroke="#1e5aa8" stroke-width="3"/>')
ux, uy = tf(X0 - 2.4, YT + 7.62)
a.append(f'<rect x="{ux - 26}" y="{uy - 22}" width="30" height="44" rx="4" fill="#9aa4ad" stroke="#1e5aa8" stroke-width="2"/>')
a.append(f'<text transform="translate({ux - 15} {uy}) rotate(-90)" class="s b" text-anchor="middle">USB</text>')
cx, cy = tf(X0 + 9.5 * P, YT + 7.62)
a.append(f'<text x="{cx}" y="{cy - 2}" class="t b" text-anchor="middle" style="fill:#1e5aa8;font-size:20px">'
         'Blue Pill</text>')
a.append(f'<text x="{cx}" y="{cy + 18}" class="s" text-anchor="middle" style="fill:#1e5aa8">'
         'компонентами вверх, USB слева · под ней C1, C2, C7–C14, R9</text>')
for k in range(20):
    x, y = tf(xk(k), YT)
    a.append(f'<text x="{x}" y="{y + 26}" class="pin" text-anchor="middle">{TOP[k]}</text>')
    x, y = tf(xk(k), YB)
    a.append(f'<text x="{x}" y="{y - 17}" class="pin" text-anchor="middle">{BOT[k]}</text>')
# подписи площадок под провода
for p_ in pads:
    if p_['group'] == 'bp':
        continue
    x, y = tf(p_['x'], p_['y'])
    if p_['group'] == 'ring':
        a.append(f'<text x="{x + 30:.1f}" y="{y + 4:.1f}" class="lab">{p_["label"]}</text>')
    elif p_['y'] < H / 2:
        a.append(f'<text transform="translate({x + 4:.1f} {y - 26:.1f}) rotate(-90)" class="lab">{p_["label"]}</text>')
    else:
        a.append(f'<text transform="translate({x + 4:.1f} {y + 26:.1f}) rotate(-90)" class="lab" '
                 f'text-anchor="end">{p_["label"]}</text>')
# группы: скобки и названия за краем платы


def bracket(k0, k1, y, text, below):
    x1, yy = tf(xk(k0) - 1.1, y)
    x2, _ = tf(xk(k1) + 1.1, y)
    a.append(f'<path d="M{x1} {yy} H{x2}" stroke="#2b2a27" stroke-width="1.5"/>')
    a.append(f'<text x="{(x1 + x2) / 2}" y="{yy + (16 if below else -6)}" class="s b" text-anchor="middle">{text}</text>')


bracket(0, 4, -4.2, 'кнопки SW2–SW5', False)
bracket(12, 16, -4.2, 'энкодер + SW1', False)
for g, (k0, text) in enumerate(((0, 'земля датчиков'), (4, '+3.3 датчиков'))):
    bracket(k0, k0 + 3, H + 4.4, text, True)
for p, k0 in ((3, 8), (2, 10), (1, 12), (0, 14)):
    bracket(k0, k0 + 1, H + 4.4, f'пара {p}', True)
    x, y = tf((xk(k0) + xk(k0 + 1)) / 2, H + 4.4)
    a.append(f'<text x="{x}" y="{y + 30}" class="s" text-anchor="middle">U{2 * p + 1},U{2 * p + 2}</text>')
x, y = tf(XRING, YT - 1.0)
a.append(f'<text x="{x + 30}" y="{y}" class="s b">кольцо</text>')

ly = OY + H * S + 130
notes = [
    'Порядок сборки: 1) SMD (в т.ч. под Blue Pill); 2) гнёзда 1×20; 3) провода; 4) Blue Pill.',
    'Гнёзда — со стороны меди: пины в отверстия, корпус гнезда приподнять на ~2 мм и пропаять',
    '   у площадки (или взять SMD-гнёзда 1×20, шаг 2.54). Blue Pill — компонентами вверх.',
    'R1–R9 — 1 кОм; C7–C14 — 10 нФ; C1 — 10 мкФ (≥10 В); C2 — 100 нФ. Всё 1206. Сверло 0.9 мм, крепёж 3.2 мм.',
    'Пара датчиков = 4 провода: A, B (снизу под парой) + свои +3.3 и GND из левых групп.',
    'Не на плате (как на схеме): 100 нФ у каждой пары, 470 мкФ + 100 нФ у кольца.',
]
a.append(f'<text x="{OX}" y="{ly}" class="t b">Сборка</text>')
for i, line in enumerate(notes):
    a.append(f'<text x="{OX}" y="{ly + 24 + 20 * i}" class="s" style="font-size:13px">{line}</text>')
a.append('</svg>')
with open(os.path.join(HERE, 'spacerat_assembly.svg'), 'w') as f:
    f.write('\n'.join(a))

# ---------------------------------------------------------------- PDF ---
chrome = shutil.which('chromium') or shutil.which('google-chrome') or next(
    iter(glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')), None)
if chrome:
    svg = os.path.join(HERE, 'spacerat_copper_print.svg')
    # SVG вставляется в страницу целиком (не картинкой) — так Chromium не округляет масштаб
    inline = open(svg).read().replace('<svg ', '<svg style="position:absolute;left:15mm;top:15mm" ', 1)
    html = (f'<html><head><style>@page{{size:210mm 297mm;margin:0}}body{{margin:0}}</style></head><body>'
            f'{inline}</body></html>')
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False) as f:
        f.write(html)
    subprocess.run([chrome, '--headless', '--no-sandbox', '--no-pdf-header-footer',
                    f'--print-to-pdf={os.path.join(HERE, "spacerat_copper_print.pdf")}', 'file://' + f.name],
                   check=True, capture_output=True)
    os.unlink(f.name)
    print('PDF: spacerat_copper_print.pdf (A4, 1:1)')
else:
    print('Chromium не найден — PDF не создан, печатайте SVG в масштабе 100 %')
print('файлы: spacerat_copper_print.svg, spacerat_assembly.svg')
