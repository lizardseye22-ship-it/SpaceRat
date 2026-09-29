"""Генерирует docs/hardware/buttons_encoder_schematic.svg. Запуск: python3 gen_buttons_schematic.py"""
import os
W,H=1380,1080
o=[];a=o.append
a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="DejaVu Sans, Arial, sans-serif">')
a('''<style>
.w{stroke:#2b2a27;stroke-width:2;fill:none}
.g{stroke:#1d4e89;stroke-width:2.5;fill:none}
.box{fill:#fff;stroke:#2b2a27;stroke-width:2}
.t{font-size:14px;fill:#2b2a27}.s{font-size:12px;fill:#55524c}
.m{font-family:DejaVu Sans Mono,monospace;font-size:13px;fill:#2b2a27}.b{font-weight:bold}
.band{fill:#efebe3}
</style>''')
a(f'<rect width="{W}" height="{H}" fill="#faf8f3"/>')
a('<text x="30" y="50" class="t b" style="font-size:26px">Hall SpaceMouse — энкодер, 5 кнопок и кольцо WS2812</text>')
a('<text x="30" y="78" class="t" style="fill:#55524c">EC11 + 5 клавиатурных свичей (Cherry MX / Kailh) · внутренние pull-up STM32 · кольцо WS2812 для подсказок</text>')
def dot(x,y,c='#2b2a27'): a(f'<circle cx="{x}" cy="{y}" r="4.5" fill="{c}"/>')
def gnd(x,y): a(f'<path class="w" d="M{x-12} {y} H{x+12} M{x-7} {y+5} H{x+7} M{x-3} {y+10} H{x+3}"/>')
XBP=320; XG=1000
# bands
a('<rect class="band" x="600" y="140" width="460" height="260" rx="10"/>')
a('<text x="616" y="164" class="t b">Энкодер (на корпусе)</text>')
a('<rect class="band" x="600" y="420" width="460" height="330" rx="10"/>')
a('<text x="616" y="444" class="t b">Кнопки хоткеев (на корпусе)</text>')
# Blue Pill
a(f'<rect x="60" y="120" width="{XBP-60}" height="900" rx="8" fill="#e9eef5" stroke="#2b2a27" stroke-width="2"/>')
a('<text x="170" y="430" class="t b" text-anchor="middle" style="font-size:18px">Blue Pill</text>')
a('<text x="170" y="452" class="s" text-anchor="middle">STM32F103C8T6</text>')
a('<text x="170" y="472" class="s" text-anchor="middle">вход + внутр. pull-up</text>')
a('<text x="170" y="492" class="s" text-anchor="middle">TIM2 — режим энкодера</text>')
a('<text x="170" y="512" class="s" text-anchor="middle">JTAG выкл., SWD вкл.</text>')
# GND bus
a(f'<path class="g" d="M{XBP} 740 H{XG} V200"/>')
a(f'<text x="{XBP-8}" y="745" class="m" text-anchor="end">G</text>')
a('<text x="640" y="768" class="t b" style="fill:#1d4e89">GND</text>')
# encoder
ey={'S':200,'A':260,'B':340}
pins={'S':'PB4','A':'PA15','B':'PB3'}
EX0,EX1=760,880
a(f'<rect class="box" x="{EX0}" y="180" width="{EX1-EX0}" height="190" rx="8"/>')
a(f'<circle cx="{(EX0+EX1)//2}" cy="285" r="26" fill="none" stroke="#2b2a27" stroke-width="2"/>')
a(f'<path class="w" d="M{(EX0+EX1)//2} 285 L{(EX0+EX1)//2+14} 270"/>')
a(f'<text x="{(EX0+EX1)//2}" y="232" class="t b" text-anchor="middle">EC11</text>')
a(f'<text x="{(EX0+EX1)//2}" y="355" class="s" text-anchor="middle">ENC1</text>')
for k,y in ey.items():
    a(f'<text x="{XBP-8}" y="{y+5}" class="m" text-anchor="end">{pins[k]}</text>')
    a(f'<path class="w" d="M{XBP} {y} H{EX0}"/>')
    a(f'<text x="{EX0+6}" y="{y+4}" class="s" style="font-size:11px">{ {"S":"S1","A":"A","B":"B"}[k]}</text>')
# right side pins: S2 -> GND, C -> GND
for lab,y in (('S2',200),('C',300)):
    a(f'<text x="{EX1-6}" y="{y+4}" class="s" text-anchor="end" style="font-size:11px">{lab}</text>')
    a(f'<path class="g" d="M{EX1} {y} H{XG}"/>'); dot(XG,y,'#1d4e89')
# 10nF caps at encoder pins A,B (optional)
for n,(k,y) in enumerate((('A',260),('B',340))):
    cx=720
    dot(cx,y)
    a(f'<path class="w" d="M{cx} {y} V{y+13} M{cx} {y+19} V{y+28}"/>')
    a(f'<path class="w" d="M{cx-12} {y+13} H{cx+12} M{cx-12} {y+19} H{cx+12}" style="stroke-width:3"/>')
    gnd(cx,y+28)
    a(f'<text x="{cx-18}" y="{y+22}" class="s" text-anchor="end">C{n+15} 10 нФ</text>')
a('<text x="616" y="392" class="s">C15, C16 — на выводах A/B энкодера, опционально</text>')
# buttons
btns=[('PB5',490),('PB6',540),('PB7',590),('PB8',640),('PB9',690)]
for i,(p,y) in enumerate(btns):
    x0,x1=800,860
    a(f'<text x="{XBP-8}" y="{y+5}" class="m" text-anchor="end">{p}</text>')
    a(f'<path class="w" d="M{XBP} {y} H{x0-5}"/>')
    a(f'<circle cx="{x0}" cy="{y}" r="4.5" fill="#fff" stroke="#2b2a27" stroke-width="2"/>')
    a(f'<circle cx="{x1}" cy="{y}" r="4.5" fill="#fff" stroke="#2b2a27" stroke-width="2"/>')
    a(f'<path class="w" d="M{x0+4} {y-3} L{x1-2} {y-18}"/>')
    a(f'<path class="w" d="M{(x0+x1)//2} {y-12} V{y-24} M{(x0+x1)//2-8} {y-24} H{(x0+x1)//2+8}"/>')
    a(f'<text x="{x0-40}" y="{y-8}" class="s" text-anchor="end">SW{i+1}</text>')
    a(f'<path class="g" d="M{x1+5} {y} H{XG}"/>'); dot(XG,y,'#1d4e89')
    a(f'<text x="{x1+20}" y="{y-8}" class="s">кнопка {["1","2","3","4","Fit"][i]}</text>')
# ring WS2812
a('<rect class="band" x="600" y="780" width="460" height="260" rx="10"/>')
a('<text x="616" y="804" class="t b">Кольцо WS2812 (под рукояткой)</text>')
ya, yv, yg = 840, 900, 980   # DIN, 5V, GND кольца
V5 = 'stroke:#c2410c;stroke-width:2.5;fill:none'
a(f'<text x="{XBP-8}" y="{ya+5}" class="m" text-anchor="end">PA8</text>')
a(f'<text x="{XBP-8}" y="{yv+5}" class="m" text-anchor="end">5V</text>')
a(f'<text x="{XBP-8}" y="{yg+5}" class="m" text-anchor="end">G</text>')
a(f'<path class="w" d="M{XBP} {ya} H860"/>')
a(f'<path d="M{XBP} {yv} H860" style="{V5}"/>')
a(f'<path class="g" d="M{XBP} {yg} H860"/>')
# подтяжка R9 1к между линией данных и 5 В — у кольца
XR = 620
dot(XR,ya); dot(XR,yv,'#c2410c')
a(f'<path class="w" d="M{XR} {ya} V{ya+14} M{XR} {yv-14} V{yv}"/>')
a(f'<rect x="{XR-7}" y="{ya+14}" width="14" height="{yv-ya-28}" fill="#fff" stroke="#2b2a27" stroke-width="2"/>')
a(f'<text x="{XR+16}" y="{(ya+yv)//2-6}" class="s">R9 1 кОм</text>')
a(f'<text x="{XR+16}" y="{(ya+yv)//2+8}" class="s">у кольца</text>')
# свитая пара 5V/GND: отметки скрутки
for x in range(470, 581, 22):
    a(f'<path d="M{x} {yv+6} L{x+14} {yg-6} M{x} {yg-6} L{x+14} {yv+6}" style="stroke:#8a8378;stroke-width:1.2;fill:none"/>')
a(f'<text x="470" y="{yg+24}" class="s">5V + GND кольца — отдельная свитая пара</text>')
a(f'<text x="470" y="{yg+40}" class="s">к своему пину G, земли сходятся только на Blue Pill</text>')
# кольцо
a('<rect class="box" x="860" y="820" width="170" height="180" rx="8"/>')
a('<circle cx="960" cy="910" r="30" fill="none" stroke="#2b2a27" stroke-width="2" stroke-dasharray="5 4"/>')
a('<text x="960" y="914" class="s" text-anchor="middle">N шт.</text>')
for lab,y in (('DIN',ya),('5V',yv),('GND',yg)):
    a(f'<text x="866" y="{y+4}" class="s" style="font-size:11px">{lab}</text>')
# конденсаторы у кольца: между 5 В и GND кольца
mid = (yv + yg) // 2
for cx,lab in ((680,'470 мкФ'),(790,'100 нФ')):
    dot(cx,yv,'#c2410c'); dot(cx,yg,'#1d4e89')
    a(f'<path class="w" d="M{cx} {yv} V{mid-3} M{cx} {mid+3} V{yg}"/>')
    a(f'<path class="w" d="M{cx-12} {mid-3} H{cx+12} M{cx-12} {mid+3} H{cx+12}" style="stroke-width:3"/>')
    a(f'<text x="{cx+16}" y="{mid+5}" class="s">{lab}</text>')
a(f'<text x="470" y="{yg+56}" class="s">R9 и конденсаторы — у кольца</text>')

# notes
lx=1090
L=[('b','Кнопки SpaceMouse Pro'),('s','SW1–SW4 → 1–4, SW5 → Fit'),('s','ENC вправо / влево → T / R'),('s','ENC нажатие → F'),('s','(щелчок = «нажатие» 30 мс)'),('s','SW1 + SW5 при включении —'),('s','режим калибровки'),
   ('sp',''),('b','Обвязка'),('s','Кнопки: вывод → пин, вывод → GND'),('s','Pull-up — внутренние, в прошивке'),('s','Дребезг — программно, 5–10 мс'),('s','Внешних резисторов нет'),
   ('sp',''),('b','EC11, вид снизу'),('s','3 вывода: A · C · B'),('s','(C — средний, на GND)'),('s','2 вывода: S1 · S2 — кнопка'),
   ('sp',''),('b','Не использовать'),('s','PB2 (BOOT1); JTAG выключен'),('s','PA11/PA12 (USB), PA13/PA14 (SWD)'),('s','PA0–PA7 заняты датчиками'),
   ('sp',''),('b','Кольцо WS2812'),('s','PA8 — TIM1_CH1, открытый сток,'),('s','5 В-толерантный; R9 1 кОм к 5 В'),('s','Питание 5 В с USB (пин 5V)'),('s','5V + GND — своей свитой парой,'),('s','не через землю датчиков/кнопок'),('s','C 470 мкФ + 100 нФ — у кольца'),('s','Яркость ограничена в прошивке'),
   ('sp',''),('b','Обозначения'),('dot','— соединение'),('gs','— земля (GND)'),('g','шина GND'),]
y=140
for kind,txt in L:
    if kind=='sp': y+=12; continue
    if kind=='b': a(f'<text x="{lx}" y="{y}" class="t b">{txt}</text>')
    elif kind=='dot': dot(lx+6,y-5); a(f'<text x="{lx+20}" y="{y}" class="s">{txt}</text>')
    elif kind=='gs': gnd(lx+8,y-12); a(f'<text x="{lx+28}" y="{y}" class="s">{txt}</text>')
    elif kind=='g': a(f'<path class="g" d="M{lx} {y-5} H{lx+30}"/><text x="{lx+40}" y="{y}" class="s">{txt}</text>')
    else: a(f'<text x="{lx}" y="{y}" class="s">{txt}</text>')
    y+=22
a('</svg>')
open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','buttons_encoder_schematic.svg'),'w').write('\n'.join(o))
