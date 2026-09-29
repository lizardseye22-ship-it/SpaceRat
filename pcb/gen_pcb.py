"""SpaceRat — односторонняя плата под ЛУТ.

Генерирует в этой папке:
  spacerat_copper_print.svg / .pdf — рисунок меди 1:1 для печати (вид сверху, НЕ зеркалить)
  spacerat_assembly.svg            — сборочный чертёж (вид сверху и со стороны меди)
и проверяет плату: зазоры между цепями, связность каждой цепи, отсутствие «островов» заливки.

Запуск: python3 gen_pcb.py     (нужны shapely: pip install shapely)
Все размеры в мм. Координаты — вид СВЕРХУ (со стороны Blue Pill, медь «на просвет»),
x вправо, y вниз, начало — левый верхний угол платы.
"""
import math
import os
import sys

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------ параметры ---
W, H = 63.0, 71.0          # плата
P = 2.54                   # шаг гребёнки
TW, PW = 0.8, 1.2          # дорожка сигнала / питания
CLEAR = 0.6                # зазор заливки до чужих цепей
MIN_CLEAR = 0.5            # минимально допустимый зазор (проверка)
EDGE = 1.0                 # медь не ближе к краю платы
HDR_PAD, HDR_DRILL = 1.8, 1.0      # гнёзда под Blue Pill
WIRE_PAD, WIRE_DRILL = 2.4, 1.0    # площадки под провода
SMD_A, SMD_B, SMD_PITCH = 1.8, 1.6, 3.4   # площадка 1206: поперёк × вдоль, шаг центров
MOUNT_D, MOUNT_KEEP = 3.2, 3.0     # крепёжное отверстие М3 и радиус без меди

# Blue Pill: ряды гнёзд, 20 пинов, шаг 2.54, между рядами 15.24 (0.6").
X0, YT = 3.5, 16.0
YB = YT + 15.24
TOP = ['B12', 'B13', 'B14', 'B15', 'A8', 'A9', 'A10', 'A11', 'A12', 'A15',
       'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9', '5V', 'G', '3.3']
BOT = ['G', 'G', '3.3', 'R', 'B11', 'B10', 'B1', 'B0', 'A7', 'A6',
       'A5', 'A4', 'A3', 'A2', 'A1', 'A0', 'C15', 'C14', 'C13', 'VB']


def xk(k):
    return X0 + P * k


# --------------------------------------------------------------- модель ---
pads = []      # dict(net, x, y, d, drill, label, kind)
smds = []      # dict(ref, val, x, y, orient, nets)
traces = []    # dict(net, pts, w)
holes = []     # (x, y)


def pad(net, x, y, d, drill, label='', kind='wire'):
    pads.append(dict(net=net, x=x, y=y, d=d, drill=drill, label=label, kind=kind))


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


# ------------------------------------------------------ Blue Pill гнёзда ---
USED_TOP = {'B12', 'B13', 'B14', 'B15', 'A8', 'B5', 'B6', 'B7', 'B8', '5V', 'G'}
USED_BOT = {'G', '3.3', 'A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7'}


def pin_net(name, used):
    if name == 'G':
        return 'GND'
    if name == '3.3':
        return '3V3' if used else 'nc_3V3_top'
    return name if used else 'nc_' + name


for k, n in enumerate(TOP):
    pad(pin_net(n, n in USED_TOP), xk(k), YT, HDR_PAD, HDR_DRILL, n, 'hdr')
for k, n in enumerate(BOT):
    pad(pin_net(n, n in USED_BOT), xk(k), YB, HDR_PAD, HDR_DRILL, n, 'hdr')

# ------------------------------------------------- датчики: RC и разъёмы ---
# Группа g (слева направо) = пара 3−g. Площадки группы: 3V3, GND, B, A (шаг 3.175).
GX0, GPITCH, WP = 8.0, 12.7, 3.175
Y1 = YB + 2.6            # начало веера
YCT = 49.0               # C: верхняя площадка (узел)
YRT = 55.4               # R: верхняя площадка
YP = 64.0                # разъёмы датчиков
YBUS = 68.0              # шина 3.3 В
# пара -> (пин A, пин B); U-номер: пара p -> A = U(2p+1), B = U(2p+2)
PAIR_PINS = {0: ('A0', 'A1'), 1: ('A2', 'A3'), 2: ('A4', 'A5'), 3: ('A6', 'A7')}

for g in range(4):
    p = 3 - g
    gx = GX0 + g * GPITCH
    for side, col_off, pad_off in (('B', 3.81, 2 * WP), ('A', 8.89, 3 * WP)):
        pin = PAIR_PINS[p][0 if side == 'A' else 1]
        n = int(pin[1:]) + 1                     # U1..U8, R1..R8
        k = BOT.index(pin)
        xc = GX0 + g * GPITCH + col_off         # колонка C
        xr = xc + P                              # колонка R
        xp = gx + pad_off                        # площадка разъёма
        net, snet = pin, 'S_' + pin
        dx = xc - xk(k)
        trace(net, [(xk(k), YB), (xk(k), Y1), (xc, Y1 + abs(dx)), (xc, YCT)])
        smd(f'C{6 + n}', '10 нФ', xc, YCT + SMD_PITCH / 2, 'v', net, 'GND')
        trace(net, [(xc, YCT), (xr, YCT), (xr, YRT)])
        smd(f'R{n}', '1 кОм', xr, YRT + SMD_PITCH / 2, 'v', net, snet)
        yrb = YRT + SMD_PITCH
        if abs(xr - xp) < 0.01:
            trace(snet, [(xr, yrb), (xp, YP)])
        else:
            trace(snet, [(xr, yrb), (xr, 61.0), (xp, 61.0), (xp, YP)])
        pad(snet, xp, YP, WIRE_PAD, WIRE_DRILL, f'{side}{p}', 'wire')
    pad('3V3', gx, YP, WIRE_PAD, WIRE_DRILL, '+3.3', 'wire')
    pad('GND', gx + WP, YP, WIRE_PAD, WIRE_DRILL, 'GND', 'wire')
    trace('3V3', [(gx, YP), (gx, YBUS)], PW)
    # земля разъёма — к нижней площадке C своей колонки B
    trace('GND', [(gx + WP, YP), (gx + WP, YCT + SMD_PITCH)])

# питание 3.3 В: пин «3.3» нижнего ряда -> вниз -> шина под разъёмами
X3V = 5.0
k33 = BOT.index('3.3')
trace('3V3', [(xk(k33), YB), (xk(k33), 34.0), (X3V, 34.0), (X3V, YBUS), (GX0 + 3 * GPITCH, YBUS)], PW)
smd('C1', '10 мкФ', 8.3, 37.0, 'h', '3V3', 'GND')
smd('C2', '100 нФ', 8.3, 41.0, 'h', '3V3', 'GND')
trace('3V3', [(X3V, 37.0), (6.6, 37.0)], PW)
trace('3V3', [(X3V, 41.0), (6.6, 41.0)], PW)

# ---------------------------------------------------- кнопки и энкодер ---
YC = 8.0   # ряд разъёмов сверху


def fan_up(pin, xp):
    k = TOP.index(pin)
    x = xk(k)
    dx = xp - x
    # изгиб под 45°: диагональ заканчивается ровно на площадке
    yb = YC + abs(dx)
    assert yb <= YT - 1.5, f'{pin}: слишком большой сдвиг до площадки'
    trace(pin, [(x, YT), (x, yb), (xp, YC)])


# J2: SW2..SW5 (PB12..PB15) + GND
for pin, lab, xp in (('B12', 'SW2', 7.0), ('B13', 'SW3', 10.175), ('B14', 'SW4', 13.35), ('B15', 'SW5', 16.525)):
    fan_up(pin, xp)
    pad(pin, xp, YC, WIRE_PAD, WIRE_DRILL, lab)
pad('GND', 19.7, YC, WIRE_PAD, WIRE_DRILL, 'GND')
# J3: кнопка энкодера, A, B (PB5..PB7), SW1 (PB8) + GND
for pin, lab, xp in (('B5', 'ENC S', 33.0), ('B6', 'ENC A', 36.175), ('B7', 'ENC B', 39.35), ('B8', 'SW1', 42.525)):
    fan_up(pin, xp)
    pad(pin, xp, YC, WIRE_PAD, WIRE_DRILL, lab)
pad('GND', 45.7, YC, WIRE_PAD, WIRE_DRILL, 'GND')

# ------------------------------------------------------- кольцо WS2812 ---
XR9, XRING = 56.0, 60.5
# 5V и PA8 идут под Blue Pill (между рядами гнёзд), чтобы не резать землю сверху.
Y5V, YDIN, YRG = 19.6, 23.6, 27.6
k5 = TOP.index('5V')
trace('5V', [(xk(k5), YT), (xk(k5), Y5V), (XR9, Y5V)], PW)
smd('R9', '1 кОм', XR9, Y5V + SMD_PITCH / 2, 'v', '5V', 'A8')
trace('5V', [(XR9, Y5V), (XRING, Y5V)], PW)
k8 = TOP.index('A8')
trace('A8', [(xk(k8), YT), (xk(k8), YDIN), (XRING, YDIN)])
trace('A8', [(XR9, Y5V + SMD_PITCH), (XR9, YDIN)])
pad('5V', XRING, Y5V, WIRE_PAD, WIRE_DRILL, '5V')
pad('A8', XRING, YDIN, WIRE_PAD, WIRE_DRILL, 'DIN')
pad('GND', XRING, YRG, WIRE_PAD, WIRE_DRILL, 'GND')

# ----------------------------------------------------------- крепёж ---
holes += [(3.0, 3.0), (W - 3.0, 3.0), (W - 3.0, H - 3.0)]

# ============================================================ геометрия ===
features = []   # (net, geom)
for p_ in pads:
    features.append((p_['net'], Point(p_['x'], p_['y']).buffer(p_['d'] / 2, 32)))
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

# заливка землёй: всё, кроме чужих цепей с зазором, краёв и крепежа
others = unary_union([net_geom[n].buffer(CLEAR, 16) for n in nets if n != 'GND'])
pour = inner.difference(others).difference(hole_keep)
pour = pour.buffer(-0.3, 16).buffer(0.3, 16)          # убрать тонкие перемычки (<0.6 мм)
gnd_all = unary_union([pour, net_geom['GND']])
gnd_pins = [Point(p_['x'], p_['y']) for p_ in pads if p_['net'] == 'GND' and p_['kind'] == 'hdr']
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
    if not inner.buffer(0.01).contains(g) and n != 'GND':
        errors.append(f'цепь {n}: выходит за край платы')
    if n != 'GND' and g.intersects(hole_keep):
        errors.append(f'цепь {n}: заходит в зону крепёжного отверстия')
for i, a in enumerate(nets):
    for b in nets[i + 1:]:
        d = net_geom[a].distance(net_geom[b])
        if d < MIN_CLEAR - 1e-6:
            errors.append(f'зазор {a} — {b}: {d:.2f} мм < {MIN_CLEAR}')
# каждая площадка/SMD земли — в итоговой земле
for p_ in pads:
    if p_['net'] == 'GND' and not net_geom['GND'].contains(Point(p_['x'], p_['y'])):
        errors.append(f'площадка GND {p_["label"]} ({p_["x"]:.1f},{p_["y"]:.1f}) не связана с землёй')
min_gap = min(net_geom[a].distance(net_geom[b]) for i, a in enumerate(nets) for b in nets[i + 1:])

print(f'цепей: {len(nets)}, площадок: {len(pads)}, SMD: {len(smds)}, дорожек: {len(traces)}')
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

# ---------------------------------------------------- печать для ЛУТа ---
MX, MY = 14.0, 14.0
PW_, PH_ = W + 2 * MX, H + 2 * MY + 22


def tf_print(x, y):
    return x + MX, y + MY


o = []
o.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{PW_}mm" height="{PH_}mm" '
         f'viewBox="0 0 {PW_} {PH_}" font-family="DejaVu Sans, Arial, sans-serif">')
o.append(f'<rect width="{PW_}" height="{PH_}" fill="#fff"/>')
o.append(f'<path d="{path_d(copper, tf_print)}" fill="#000" fill-rule="evenodd"/>')
# контур платы (линия реза)
o.append(f'<rect x="{MX}" y="{MY}" width="{W}" height="{H}" fill="none" stroke="#000" stroke-width="0.2"/>')
# центры сверловки: белые точки
for p_ in pads:
    x, y = tf_print(p_['x'], p_['y'])
    o.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="0.35" fill="#fff"/>')
for hx, hy in holes:
    x, y = tf_print(hx, hy)
    o.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{MOUNT_D / 2}" fill="none" stroke="#000" stroke-width="0.25"/>')
    o.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="0.35" fill="#000"/>')
# надпись в заливке: зеркальная на печати -> на готовой меди читается нормально
tx, ty = tf_print(33.0, 28.0)
o.append(f'<text transform="translate({tx:.2f} {ty:.2f}) scale(-1 1)" font-size="2.6" font-weight="bold" '
         f'text-anchor="middle" fill="#fff">SPACERAT v1</text>')
# линейка 50 мм и подписи вне платы
ry = MY + H + 8
o.append(f'<path d="M{MX} {ry} H{MX + 50}" stroke="#000" stroke-width="0.3"/>')
for i in range(6):
    o.append(f'<path d="M{MX + 10 * i} {ry - 1.5} V{ry + 1.5}" stroke="#000" stroke-width="0.3"/>')
o.append(f'<text x="{MX}" y="{ry + 5}" font-size="3">50 мм — проверить линейкой</text>')
o.append(f'<text x="{MX}" y="{ry + 10}" font-size="3">Печать 100%, без масштабирования,</text>')
o.append(f'<text x="{MX}" y="{ry + 14.5}" font-size="3">БЕЗ зеркала. SPACERAT на меди читается прямо.</text>')
o.append(f'<text x="{MX}" y="{MY - 4}" font-size="3">SpaceRat v1 · медь · вид сверху (как есть)</text>')
o.append('</svg>')
with open(os.path.join(HERE, 'spacerat_copper_print.svg'), 'w') as f:
    f.write('\n'.join(o))

# ------------------------------------------------- сборочный чертёж ---
S = 12.0         # px на мм
GAP = 170
AW = int(2 * W * S + GAP + 120)
AH = int(H * S + 400)
OX1, OY = 60, 190
OX2 = OX1 + W * S + GAP


def tf_top(x, y):
    return OX1 + x * S, OY + y * S


def tf_bot(x, y):
    return OX2 + (W - x) * S, OY + y * S


NET_COL = {'GND': '#9cc3e6', '3V3': '#f4b183', '5V': '#f8cbad'}
a = []
a.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{AW}" height="{AH}" viewBox="0 0 {AW} {AH}" '
         'font-family="DejaVu Sans, Arial, sans-serif">')
a.append('''<style>.t{font-size:15px;fill:#2b2a27}.s{font-size:11px;fill:#2b2a27}.b{font-weight:bold}
.lab{font-size:10px;fill:#1f1e1b;font-weight:bold}.ref{font-size:10px;fill:#8a2c0d;font-weight:bold}</style>''')
a.append(f'<rect width="{AW}" height="{AH}" fill="#faf8f3"/>')
a.append('<text x="30" y="40" class="t b" style="font-size:24px">SpaceRat — плата v1: сборка</text>')
a.append(f'<text x="30" y="66" class="t" style="fill:#55524c">Односторонняя, {W:.0f}×{H:.0f} мм · SMD 1206 со стороны меди · '
         'Blue Pill на гнёздах сверху · всё остальное — проводами</text>')


def draw_board(tf, title, bottom):
    x0, y0 = tf(0, 0)
    x1, _ = tf(W, 0)
    xl = min(x0, x1)
    a.append(f'<text x="{xl}" y="{OY - 70}" class="t b">{title}</text>')
    a.append(f'<rect x="{xl}" y="{y0}" width="{W * S}" height="{H * S}" fill="#e6d3a3" stroke="#6b5a2e" stroke-width="1.5"/>')
    a.append(f'<path d="{path_d(net_geom["GND"], tf)}" fill="#c9a86a" fill-rule="evenodd" opacity="{0.9 if bottom else 0.35}"/>')
    for n in nets:
        if n == 'GND':
            continue
        a.append(f'<path d="{path_d(net_geom[n], tf)}" fill="{NET_COL.get(n, "#b87333")}" '
                 f'fill-rule="evenodd" opacity="{1 if bottom else 0.35}"/>')
    for hx, hy in holes:
        x, y = tf(hx, hy)
        a.append(f'<circle cx="{x}" cy="{y}" r="{MOUNT_D / 2 * S}" fill="#faf8f3" stroke="#6b5a2e"/>')
    for p_ in pads:
        x, y = tf(p_['x'], p_['y'])
        a.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{p_["drill"] / 2 * S:.1f}" fill="#faf8f3"/>')


draw_board(tf_top, 'Вид сверху — сторона Blue Pill и проводов', False)
draw_board(tf_bot, 'Вид со стороны меди — пайка SMD', True)

# Blue Pill (сверху): контур и подписи пинов
x0, y0 = tf_top(X0 - 2.4, YT - 3.4)
a.append(f'<rect x="{x0}" y="{y0}" width="{(19 * P + 4.8) * S}" height="{(15.24 + 6.8) * S}" fill="#2b5fa8" '
         'fill-opacity="0.12" stroke="#2b5fa8" stroke-width="1.5" stroke-dasharray="6 4" rx="6"/>')
cx, cy = tf_top(X0 + 9.5 * P, YT + 7.62)
a.append(f'<text x="{cx}" y="{cy - 4}" class="t b" text-anchor="middle" style="fill:#2b5fa8">Blue Pill</text>')
a.append(f'<text x="{cx}" y="{cy + 14}" class="s" text-anchor="middle">подписи пинов на плате Blue Pill должны совпасть</text>')
for k in range(20):
    x, y = tf_top(xk(k), YT)
    a.append(f'<text x="{x}" y="{y + 26}" class="lab" text-anchor="middle" style="fill:#2b5fa8">{TOP[k]}</text>')
    x, y = tf_top(xk(k), YB)
    a.append(f'<text x="{x}" y="{y - 18}" class="lab" text-anchor="middle" style="fill:#2b5fa8">{BOT[k]}</text>')

# подписи площадок под провода (обе стороны): вертикально, чтобы не налезали
for p_ in pads:
    if p_['kind'] != 'wire':
        continue
    for tf in (tf_top, tf_bot):
        x, y = tf(p_['x'], p_['y'])
        r = p_['d'] / 2 * S
        if p_['x'] > W - 5:  # кольцо справа — подпись сбоку
            lx = x + (r + 6 if tf is tf_top else -r - 6)
            anchor = 'start' if tf is tf_top else 'end'
            a.append(f'<text x="{lx:.1f}" y="{y + 4:.1f}" class="lab" text-anchor="{anchor}">{p_["label"]}</text>')
        elif p_['y'] < H / 2:  # верхние разъёмы — подпись вверх от площадки
            a.append(f'<text transform="translate({x + 4:.1f} {y - r - 4:.1f}) rotate(-90)" class="lab">{p_["label"]}</text>')
        else:                  # разъёмы датчиков — подпись вниз от площадки
            a.append(f'<text transform="translate({x + 4:.1f} {y + r + 4:.1f}) rotate(-90)" class="lab" '
                     f'text-anchor="end">{p_["label"]}</text>')

# SMD (со стороны меди)
for s in smds:
    (_, xa, ya, pa, pb), (_, xb, yb, _, _) = smd_pads(s)
    xs = [tf_bot(xa, ya)[0], tf_bot(xb, yb)[0]]
    ys = [tf_bot(xa, ya)[1], tf_bot(xb, yb)[1]]
    cx, cy = sum(xs) / 2, sum(ys) / 2
    if s['orient'] == 'v':
        w_, h_ = 1.6 * S, 3.2 * S
    else:
        w_, h_ = 3.2 * S, 1.6 * S
    a.append(f'<rect x="{cx - w_ / 2:.1f}" y="{cy - h_ / 2:.1f}" width="{w_:.1f}" height="{h_:.1f}" '
             'fill="#3a3a3a" fill-opacity="0.55" stroke="#1f1e1b" rx="2"/>')
    a.append(f'<text x="{cx + (w_ / 2 + 4):.1f}" y="{cy + 4:.1f}" class="ref">{s["ref"]}</text>')

# подписи групп датчиков
for g in range(4):
    p = 3 - g
    gx = GX0 + g * GPITCH
    for tf in (tf_top, tf_bot):
        x1, y1 = tf(gx - 1.2, H)
        x2, _ = tf(gx + 3 * WP + 1.2, H)
        a.append(f'<path d="M{x1} {y1 + 10} H{x2}" stroke="#2b2a27" stroke-width="1.2"/>')
        a.append(f'<text x="{(x1 + x2) / 2}" y="{y1 + 26}" class="s b" text-anchor="middle">пара {p}</text>')
        a.append(f'<text x="{(x1 + x2) / 2}" y="{y1 + 40}" class="s" text-anchor="middle">A=U{2 * p + 1} B=U{2 * p + 2}</text>')
# надписи разъёмов сверху
for tf in (tf_top, tf_bot):
    x, y = tf(13.4, 0)
    a.append(f'<text x="{x}" y="{y - 10}" class="s b" text-anchor="middle">кнопки SW2–SW5</text>')
    x, y = tf(39.4, 0)
    a.append(f'<text x="{x}" y="{y - 10}" class="s b" text-anchor="middle">энкодер + SW1</text>')
    x, y = tf(XRING, 31.0)
    a.append(f'<text x="{x}" y="{y + 12}" class="s b" text-anchor="middle">кольцо</text>')

# перечень
ly = OY + H * S + 90
bom = [
    'R1–R8, R9: 1 кОм 1206 (R9 — подтяжка PA8 к 5 В для кольца)',
    'C7–C14: 10 нФ 1206 · C1: 10 мкФ 1206 (≥10 В) · C2: 100 нФ 1206',
    'Гнёзда 1×20, шаг 2.54 — 2 шт. (под Blue Pill) · сверловка: 1.0 мм, крепёж М3 — 3.2 мм',
    'Провода к датчикам: 4 провода на пару (+3.3, GND, B, A); конденсатор 100 нФ пары — у датчиков',
    'Кольцо: 5V, DIN, GND; 470 мкФ + 100 нФ — у кольца. Энкодер: S, A, B + GND (C и S2 энкодера — на GND)',
]
a.append(f'<text x="{OX1}" y="{ly}" class="t b">Компоненты на плате</text>')
for i, line in enumerate(bom):
    a.append(f'<text x="{OX1}" y="{ly + 24 + 20 * i}" class="s" style="font-size:13px">• {line}</text>')
a.append('</svg>')
with open(os.path.join(HERE, 'spacerat_assembly.svg'), 'w') as f:
    f.write('\n'.join(a))

# ---------------------------------------------------------------- PDF ---
# A4, рисунок 1:1. Нужен Chromium; если его нет — печатайте SVG (100 %).
import glob
import shutil
import subprocess
import tempfile

chrome = shutil.which('chromium') or shutil.which('google-chrome') or next(
    iter(glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')), None)
if chrome:
    svg = os.path.join(HERE, 'spacerat_copper_print.svg')
    html = (f'<html><head><style>@page{{size:210mm 297mm;margin:0}}body{{margin:0}}</style></head><body>'
            f'<img src="file://{svg}" style="position:absolute;left:15mm;top:15mm;width:{PW_}mm;height:{PH_}mm">'
            f'</body></html>')
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
