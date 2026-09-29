"""Генерирует docs/hardware/mechanics_layout.svg — размеры для магнитов 10×2.
Запуск: python3 gen_mechanics_drawing.py"""
import math
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'mechanics_layout.svg')

# --- размеры, мм ---
R = 25.0          # радиус окружности центров пар
PITCH = 9.0       # шаг датчиков в паре (центр-центр)
MAG_D, MAG_H = 10.0, 2.0
GAP = 5.5         # зазор магнит — лицевая сторона датчика (A3)
TO92_W, TO92_L, TO92_T = 4.5, 5.0, 3.6  # ширина, длина корпуса, толщина
ELEM = 1.0        # глубина чувствительного элемента под лицевой стороной (примерно)
TRAVEL = 1.5

W, H = 1720, 1100
o = []
a = o.append
a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
  'font-family="DejaVu Sans, Arial, sans-serif">')
a('''<style>
.t{font-size:14px;fill:#2b2a27}.s{font-size:12px;fill:#55524c}.b{font-weight:bold}
.dim{stroke:#b4412c;stroke-width:1.3;fill:none}.dimt{font-size:13px;fill:#b4412c;font-weight:bold}
.thin{stroke:#8a8378;stroke-width:1;fill:none;stroke-dasharray:5 4}
.body{fill:#fff;stroke:#2b2a27;stroke-width:1.8}
.mag{fill:#cfd9e6;stroke:#1d4e89;stroke-width:1.8}
.magtop{fill:#cfd9e6;fill-opacity:.55;stroke:#1d4e89;stroke-width:1.6;stroke-dasharray:6 4}
.leg{stroke:#2b2a27;stroke-width:1.6}
.base{fill:#e8e3d8;stroke:#8a8378;stroke-width:1}
</style>
<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
<path d="M0 0 L10 5 L0 10 Z" fill="#b4412c"/></marker>
<marker id="ag" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
<path d="M0 0 L10 5 L0 10 Z" fill="#2b2a27"/></marker></defs>''')
a(f'<rect width="{W}" height="{H}" fill="#faf8f3"/>')
a('<text x="30" y="46" class="t b" style="font-size:26px">SpaceRat — размеры под магниты 10×2</text>')
a('<text x="30" y="74" class="t" style="fill:#55524c">DRV5055A3 (TO-92, лёжа маркировкой вверх) · 4 пары по кругу · все размеры в мм · стартовые значения, зазор регулируемый</text>')


def dim_line(x1, y1, x2, y2, label, off=0, lx=None, ly=None, anchor='middle'):
    a(f'<line class="dim" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
      'marker-start="url(#ah)" marker-end="url(#ah)"/>')
    if lx is None:
        lx, ly = (x1 + x2) / 2, (y1 + y2) / 2 - 8 + off
    a(f'<text x="{lx:.1f}" y="{ly:.1f}" class="dimt" text-anchor="{anchor}">{label}</text>')


# ================================================================ ВИД СВЕРХУ
S = 10.0                     # px на мм
CX, CY = 440, 590
a('<text x="60" y="130" class="t b" style="font-size:18px">Вид сверху (подвижная часть снята, магниты — пунктиром)</text>')
a(f'<circle cx="{CX}" cy="{CY}" r="{R*S}" class="thin"/>')
a(f'<line x1="{CX-10}" y1="{CY}" x2="{CX+10}" y2="{CY}" class="leg"/>'
  f'<line x1="{CX}" y1="{CY-10}" x2="{CX}" y2="{CY+10}" class="leg"/>')


def P(x, y):  # мм (математические оси, y вверх) -> px
    return CX + x * S, CY - y * S


centers = []
for p in range(4):
    th = math.radians(90 * p)
    cx, cy = R * math.cos(th), R * math.sin(th)
    centers.append((cx, cy))
    tx, ty = -math.sin(th), math.cos(th)   # касательная, против часовой
    rx, ry = math.cos(th), math.sin(th)    # радиальное направление
    X, Y = P(cx, cy)
    a(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="{MAG_D/2*S:.1f}" fill="#cfd9e6" fill-opacity=".45"/>')
    # датчики A и B
    for k, sgn in (('A', -1), ('B', 1)):
        sx, sy = cx + sgn * PITCH / 2 * tx, cy + sgn * PITCH / 2 * ty
        # ножки наружу по радиусу
        for off in (-1.27, 0, 1.27):
            lx0, ly0 = sx + off * tx + rx * TO92_L / 2, sy + off * ty + ry * TO92_L / 2
            lx1, ly1 = lx0 + rx * 6, ly0 + ry * 6
            X0, Y0 = P(lx0, ly0)
            X1, Y1 = P(lx1, ly1)
            a(f'<line class="leg" x1="{X0:.1f}" y1="{Y0:.1f}" x2="{X1:.1f}" y2="{Y1:.1f}"/>')
        corners = []
        for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            mx = sx + u * TO92_W / 2 * tx + v * TO92_L / 2 * rx
            my = sy + u * TO92_W / 2 * ty + v * TO92_L / 2 * ry
            corners.append('%.1f,%.1f' % P(mx, my))
        a(f'<polygon class="body" points="{" ".join(corners)}"/>')
        X, Y = P(sx, sy)
        a(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="2.5" fill="#b4412c"/>')
        LX, LY = P(sx + sgn * (TO92_W / 2 + 1.6) * tx, sy + sgn * (TO92_W / 2 + 1.6) * ty)
        a(f'<text x="{LX:.1f}" y="{LY+5:.1f}" class="t b" text-anchor="middle">{k}</text>')
    # магнит
    X, Y = P(cx, cy)
    a(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="{MAG_D/2*S:.1f}" fill="none" stroke="#1d4e89" stroke-width="1.6" stroke-dasharray="6 4"/>')
    # стрелка A->B
    ax0, ay0 = P(cx - 2.2 * tx - rx * 7.5, cy - 2.2 * ty - ry * 7.5)
    ax1, ay1 = P(cx + 2.2 * tx - rx * 7.5, cy + 2.2 * ty - ry * 7.5)
    a(f'<line x1="{ax0:.1f}" y1="{ay0:.1f}" x2="{ax1:.1f}" y2="{ay1:.1f}" stroke="#2b2a27" '
      'stroke-width="1.4" marker-end="url(#ag)"/>')
    # подпись пары снаружи
    if p % 2:   # сверху/снизу — за ножками
        LX, LY = P(cx + rx * 13, cy + ry * 13)
        LY += 8 if p == 3 else -8
    else:       # справа/слева — над парой
        LX, LY = P(cx + rx * 5, cy + 11)
    u = ('U1/U2', 'U3/U4', 'U5/U6', 'U7/U8')[p]
    a(f'<text x="{LX:.1f}" y="{LY-4:.1f}" class="t b" text-anchor="middle">Пара {p} · {90*p}°</text>')
    a(f'<text x="{LX:.1f}" y="{LY+14:.1f}" class="s" text-anchor="middle">{u} · PA{2*p}/PA{2*p+1}</text>')

# размер R (к паре 3 — вниз, чтобы не мешать)
X0, Y0 = P(0, 0)
X1, Y1 = P(centers[3][0], centers[3][1] + MAG_D / 2)
dim_line(X0, Y0 + 14, X1, Y1 - 2, '', 0)
a(f'<text x="{X0+10:.1f}" y="{(Y0+Y1)/2+4:.1f}" class="dimt">R 25</text>')
a(f'<text x="{X0+10:.1f}" y="{(Y0+Y1)/2+20:.1f}" class="s">(22–30)</text>')
# шаг в паре 1 (горизонтальная касательная сверху)
cx, cy = centers[1]
Xa, Ya = P(cx + PITCH / 2, cy + 7.2)
Xb, Yb = P(cx - PITCH / 2, cy + 7.2)
for xs in (cx + PITCH / 2, cx - PITCH / 2):
    x0, y0 = P(xs, cy)
    a(f'<line class="thin" x1="{x0:.1f}" y1="{y0:.1f}" x2="{x0:.1f}" y2="{Ya+6:.1f}"/>')
dim_line(Xb, Ya, Xa, Ya, '9 (8–10)')
# диаметр магнита у пары 0
cx, cy = centers[0]
X0, Y0 = P(cx - MAG_D / 2, cy - 11)
X1, Y1 = P(cx + MAG_D / 2, cy - 11)
dim_line(X0, Y0, X1, Y1, 'Ø10', lx=(X0 + X1) / 2, ly=Y0 + 20)
# расстояние между соседними парами
X0, Y0 = P(*centers[0])
X1, Y1 = P(*centers[1])
a(f'<line class="thin" x1="{X0:.1f}" y1="{Y0:.1f}" x2="{X1:.1f}" y2="{Y1:.1f}"/>')
a(f'<text x="{(X0+X1)/2-5:.1f}" y="{(Y0+Y1)/2-65:.1f}" class="dimt">35 между соседями</text>')

a(f'<text x="{CX}" y="{CY+R*S+175}" class="s" text-anchor="middle">● — чувствительный элемент · стрелка A→B — все пары против часовой · ножки наружу по радиусу</text>')
a(f'<text x="{CX}" y="{CY+R*S+197}" class="s" text-anchor="middle">Линия A–B каждой пары — по касательной к окружности · магнит над серединой пары</text>')

# ================================================================ ВИД СБОКУ
S2 = 22.0
BX, BY = 1000, 470            # точка: середина пары на уровне основания
a('<text x="940" y="130" class="t b" style="font-size:18px">Вид сбоку (разрез вдоль пары, ручка в покое)</text>')


def Q(x, z):  # мм -> px, z вверх от основания
    return BX + 180 + x * S2, BY - z * S2


# основание
X0, Y0 = Q(-11, 0)
a(f'<rect class="base" x="{X0:.1f}" y="{Y0:.1f}" width="{22*S2:.1f}" height="{1.6*S2:.1f}"/>')
a(f'<text x="{X0+6:.1f}" y="{Y0+24:.1f}" class="s">плата / основание</text>')
# датчики
for k, xs in (('A', -PITCH / 2), ('B', PITCH / 2)):
    X, Y = Q(xs - TO92_W / 2, TO92_T)
    a(f'<rect class="body" x="{X:.1f}" y="{Y:.1f}" width="{TO92_W*S2:.1f}" height="{TO92_T*S2:.1f}" rx="6"/>')
    X, Y = Q(xs, TO92_T - ELEM)
    a(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="4" fill="#b4412c"/>')
    X, Y = Q(xs, TO92_T / 2 - 0.9)
    a(f'<text x="{X:.1f}" y="{Y:.1f}" class="t b" text-anchor="middle">{k}</text>')
X, Y = Q(-PITCH / 2, TO92_T + 0.25)
a(f'<text x="{X:.1f}" y="{Y:.1f}" class="s" text-anchor="middle">маркировка вверх</text>')
# магнит
top_s = TO92_T
X, Y = Q(-MAG_D / 2, top_s + GAP + MAG_H)
a(f'<rect class="mag" x="{X:.1f}" y="{Y:.1f}" width="{MAG_D*S2:.1f}" height="{MAG_H*S2:.1f}"/>')
X, Y = Q(0, top_s + GAP + MAG_H / 2)
a(f'<text x="{X:.1f}" y="{Y+5:.1f}" class="t b" text-anchor="middle" style="fill:#1d4e89">магнит 10×2 · N вниз</text>')
# держатель (подвижная часть)
X, Y = Q(-8, top_s + GAP + MAG_H + 1.5)
a(f'<rect x="{X:.1f}" y="{Y:.1f}" width="{16*S2:.1f}" height="{1.5*S2:.1f}" fill="#efebe3" stroke="#8a8378"/>')
a(f'<text x="{X+8:.1f}" y="{Y-8:.1f}" class="s">подвижная часть (держатель магнита)</text>')

# размеры сбоку
xr = 7.2
X0, Y0 = Q(xr, top_s)
X1, Y1 = Q(xr, top_s + GAP)
a(f'<line class="thin" x1="{Q(PITCH/2+TO92_W/2,0)[0]:.1f}" y1="{Y0:.1f}" x2="{X0+10:.1f}" y2="{Y0:.1f}"/>')
a(f'<line class="thin" x1="{Q(MAG_D/2,0)[0]:.1f}" y1="{Y1:.1f}" x2="{X0+10:.1f}" y2="{Y1:.1f}"/>')
dim_line(X0, Y0, X0, Y1, '', 0)
a(f'<text x="{X0+12:.1f}" y="{(Y0+Y1)/2-2:.1f}" class="dimt">зазор 5–6</text>')
a(f'<text x="{X0+12:.1f}" y="{(Y0+Y1)/2+16:.1f}" class="s">(для A3)</text>')
X2, Y2 = Q(xr + 4.6, top_s - ELEM)
X3, Y3 = Q(xr + 4.6, top_s + GAP)
a(f'<line class="thin" x1="{Q(PITCH/2,0)[0]:.1f}" y1="{Y2:.1f}" x2="{X2+10:.1f}" y2="{Y2:.1f}"/>')
dim_line(X2, Y2, X2, Y3, '', 0)
a(f'<text x="{X2+12:.1f}" y="{(Y2+Y3)/2+40:.1f}" class="s">до элемента</text>')
a(f'<text x="{X2+12:.1f}" y="{(Y2+Y3)/2+56:.1f}" class="s">≈ зазор + 1</text>')
# шаг
X0, Y0 = Q(-PITCH / 2, -2.6)
X1, Y1 = Q(PITCH / 2, -2.6)
for xs in (-PITCH / 2, PITCH / 2):
    x0, _ = Q(xs, 0)
    a(f'<line class="thin" x1="{x0:.1f}" y1="{Q(0, TO92_T-ELEM)[1]:.1f}" x2="{x0:.1f}" y2="{Y0+6:.1f}"/>')
dim_line(X0, Y0, X1, Y1, 'шаг 9 (≈ Ø магнита)', lx=(X0 + X1) / 2, ly=Y0 + 22)
# толщина магнита
X0, Y0 = Q(-MAG_D / 2 - 0.9, top_s + GAP)
X1, Y1 = Q(-MAG_D / 2 - 0.9, top_s + GAP + MAG_H)
dim_line(X0, Y0, X0, Y1, '2', lx=X0 - 10, ly=(Y0 + Y1) / 2 + 5, anchor='end')
# ход ручки
X, Y = Q(-MAG_D / 2 - 3.2, top_s + GAP + MAG_H / 2)
a(f'<line class="dim" x1="{X:.1f}" y1="{Y-TRAVEL*S2:.1f}" x2="{X:.1f}" y2="{Y+TRAVEL*S2:.1f}" '
  'marker-start="url(#ah)" marker-end="url(#ah)"/>')
a(f'<text x="{X-8:.1f}" y="{Y+5:.1f}" class="dimt" text-anchor="end">ход ±1.5</text>')

# ================================================================ ТАБЛИЦА
tx0, ty0 = 940, 640
rows = [
    ('Датчик', 'Зазор до корпуса', 'Поле в покое', ''),
    ('DRV5055A2', '7–9 мм', '~25–35 мТ', ''),
    ('DRV5055A3', '5–6 мм', '~40–55 мТ', 'рекомендуется'),
    ('DRV5055A4', '3–4 мм', '~80–110 мТ', 'компактно'),
]
cols = [0, 150, 320, 470]
for i, r in enumerate(rows):
    y = ty0 + i * 30
    if i == 2:
        a(f'<rect x="{tx0-8}" y="{y-20}" width="620" height="28" fill="#f3e4dc"/>')
    for j, c in enumerate(r):
        cls = 't b' if i == 0 or (i == 2 and j == 0) else 't'
        a(f'<text x="{tx0+cols[j]}" y="{y}" class="{cls}">{c}</text>')
a(f'<line x1="{tx0-8}" y1="{ty0+8}" x2="{tx0+612}" y2="{ty0+8}" stroke="#8a8378"/>')

notes = [
    'Все 4 магнита — одним полюсом вниз (аксиальные, полюса на плоских сторонах).',
    'Зазор сделать регулируемым: проставки / резьба с шагом 0.5 мм.',
    'Стали рядом нет: винты — пластик, латунь или нержавейка A2; пружины подальше от пар.',
    'Проверка: OUT в покое ≈ 2.2–2.5 В, при полном ходе ≤ 3.0 В. Ближе к 3.1 В — увеличить зазор.',
    'Соседние магниты на 35 мм влияют на ~0.5–1 мТ — постоянно, уходит калибровкой нуля.',
    'Основание целиком ≈ 80–90 мм.',
]
y = ty0 + 150
a(f'<text x="{tx0}" y="{y}" class="t b">Важно</text>')
for n in notes:
    y += 24
    a(f'<text x="{tx0}" y="{y}" class="s" style="font-size:13px">• {n}</text>')

a('</svg>')
with open(OUT, 'w') as f:
    f.write('\n'.join(o))
