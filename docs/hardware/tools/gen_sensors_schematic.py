"""Генерирует docs/hardware/spacemouse_schematic.svg. Запуск: python3 gen_sensors_schematic.py"""
import os
W,H=1690,1060
o=[]
a=o.append
a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="DejaVu Sans, Arial, sans-serif">')
a('''<style>
.w{stroke:#2b2a27;stroke-width:2;fill:none}
.v{stroke:#c2410c;stroke-width:2.5;fill:none}
.g{stroke:#1d4e89;stroke-width:2.5;fill:none}
.box{fill:#fff;stroke:#2b2a27;stroke-width:2}
.t{font-size:14px;fill:#2b2a27}
.s{font-size:12px;fill:#55524c}
.m{font-family:DejaVu Sans Mono,monospace;font-size:13px;fill:#2b2a27}
.b{font-weight:bold}
.band{fill:#efebe3}
</style>''')
a(f'<rect width="{W}" height="{H}" fill="#faf8f3"/>')
a('<text x="30" y="50" class="t b" style="font-size:26px">Hall SpaceMouse — принципиальная схема</text>')
a('<text x="30" y="78" class="t" style="fill:#55524c">Blue Pill (STM32F103C8T6) · 8 × DRV5055 (TO-92) · питание от USB</text>')

XBP=450; XV=1000; XG=1180
rows=[310,400,480,570,650,740,820,910]
caps=[355,525,695,865]
def dot(x,y,c): a(f'<circle cx="{x}" cy="{y}" r="4.5" fill="{c}"/>')
def gnd(x,y):
    a(f'<path class="w" d="M{x-12} {y} H{x+12} M{x-7} {y+5} H{x+7} M{x-3} {y+10} H{x+3}"/>')
def hcap(x1,x2,y,cls1,cls2,label,sub):
    m=(x1+x2)//2
    a(f'<path class="{cls1}" d="M{x1} {y} H{m-4}"/><path class="{cls2}" d="M{m+4} {y} H{x2}"/>')
    a(f'<path class="w" d="M{m-4} {y-11} V{y+11} M{m+4} {y-11} V{y+11}" style="stroke-width:3"/>')
    a(f'<text x="{m}" y="{y-16}" class="s" text-anchor="middle">{label}</text>')
    if sub: a(f'<text x="{m}" y="{y+26}" class="s" text-anchor="middle">{sub}</text>')
    dot(x1,y,'#c2410c'); dot(x2,y,'#1d4e89')

# pair bands
for i in range(4):
    y0=280+170*i
    a(f'<rect class="band" x="735" y="{y0-8}" width="585" height="166" rx="10"/>')
    a(f'<text x="1200" y="{y0+14}" class="t b">Пара {i} · {i*90}°</text>')
    a(f'<text x="1200" y="{y0+32}" class="s">PA{2*i} / PA{2*i+1}</text>')

# USB
a('<rect class="box" x="30" y="540" width="120" height="80" rx="6"/>')
a('<text x="90" y="573" class="t b" text-anchor="middle">USB</text>')
a('<text x="90" y="595" class="s" text-anchor="middle">5 В · ≤500 мА</text>')
a('<path class="w" d="M150 580 H182"/><path d="M182 574 L190 580 L182 586 Z" fill="#2b2a27"/>')
# Blue Pill
a(f'<rect x="190" y="150" width="{XBP-190}" height="870" rx="8" fill="#e9eef5" stroke="#2b2a27" stroke-width="2"/>')
a('<text x="290" y="560" class="t b" text-anchor="middle" style="font-size:18px">Blue Pill</text>')
a('<text x="290" y="582" class="s" text-anchor="middle">STM32F103C8T6</text>')
a('<text x="290" y="602" class="s" text-anchor="middle">LDO 3.3 В на плате</text>')
a('<text x="290" y="622" class="s" text-anchor="middle">VDDA = 3.3 В</text>')
a(f'<text x="{XBP-8}" y="205" class="m" text-anchor="end">3.3</text>')
a(f'<text x="{XBP-8}" y="995" class="m" text-anchor="end">G</text>')

# power buses
a(f'<path class="v" d="M{XBP} 200 H{XV} V{rows[-1]-15}"/>')
a(f'<path class="g" d="M{XBP} 990 H{XG} V240"/>')
a(f'<text x="760" y="192" class="t b" style="fill:#c2410c">+3V3</text>')
a(f'<text x="620" y="1012" class="t b" style="fill:#1d4e89">GND</text>')
# bulk caps
for cx,lab,pol in ((490,'C1 10 мкФ',True),(620,'C2 100 нФ',False)):
    dot(cx,200,'#c2410c')
    a(f'<path class="w" d="M{cx} 200 V213 M{cx} 219 V230"/>')
    a(f'<path class="w" d="M{cx-13} 213 H{cx+13} M{cx-13} 219 H{cx+13}" style="stroke-width:3"/>')
    if pol: a(f'<text x="{cx-20}" y="211" class="s">+</text>')
    gnd(cx,230)
    a(f'<text x="{cx+18}" y="226" class="s">{lab}</text>')

for k,y in enumerate(rows):
    n=k+1
    # pin label
    a(f'<text x="{XBP-8}" y="{y+5}" class="m" text-anchor="end">PA{k}</text>')
    # R
    a(f'<path class="w" d="M{XBP} {y} H510 M570 {y} H760"/>')
    a(f'<rect x="510" y="{y-7}" width="60" height="14" fill="#fff" stroke="#2b2a27" stroke-width="2"/>')
    a(f'<text x="540" y="{y-12}" class="s" text-anchor="middle">R{n} 1 кОм</text>')
    # C to gnd
    dot(620,y,'#2b2a27')
    a(f'<path class="w" d="M620 {y} V{y+13} M620 {y+19} V{y+28}"/>')
    a(f'<path class="w" d="M607 {y+13} H633 M607 {y+19} H633" style="stroke-width:3"/>')
    gnd(620,y+28)
    a(f'<text x="640" y="{y+24}" class="s">C{6+n} 10 нФ</text>')
    # sensor
    a(f'<rect class="box" x="760" y="{y-30}" width="140" height="60" rx="5"/>')
    a(f'<text x="830" y="{y-4}" class="t b" text-anchor="middle">U{n} · {"AB"[k%2]}</text>')
    a(f'<text x="830" y="{y+14}" class="s" text-anchor="middle">DRV5055</text>')
    a(f'<text x="766" y="{y+4}" class="s" style="font-size:10px">OUT</text>')
    a(f'<text x="894" y="{y-11}" class="s" text-anchor="end" style="font-size:10px">VCC</text>')
    a(f'<text x="894" y="{y+19}" class="s" text-anchor="end" style="font-size:10px">GND</text>')
    a(f'<text x="750" y="{y-5}" class="s" text-anchor="end">3</text>')
    a(f'<text x="908" y="{y-20}" class="s">1</text>')
    a(f'<text x="908" y="{y+30}" class="s">2</text>')
    a(f'<path class="v" d="M900 {y-15} H{XV}"/>')
    a(f'<path class="g" d="M900 {y+15} H{XG}"/>')
    dot(XV,y-15,'#c2410c'); dot(XG,y+15,'#1d4e89')

for i,y in enumerate(caps):
    hcap(XV,XG,y,'v','g',f'C{3+i} 100 нФ','у ножек пары')

# legend
lx=1350
L=[('b','Обозначения'),
   ('dot',''),('s','пересечение без точки — нет соединения'),
   ('v','+3V3 (от пина 3.3 Blue Pill)'),('g','GND'),
   ('sp',''),('b','Цоколёвка DRV5055, TO-92'),('s','маркировкой к себе, слева направо:'),('m','1 VCC · 2 GND · 3 OUT'),
   ('sp',''),('b','Где ставить'),('s','Компоненты нарисованы там,'),('s','где они стоят физически:'),('s','C1, C2 — у пина 3.3 Blue Pill'),('s','C3–C6 — у ножек своей пары'),
   ('s','R1–R8, C7–C14 — у пинов PA0–PA7'),('s','(RC-фильтр, опционально)'),('gs','— земля (GND)'),
   ('sp',''),('b','Питание'),('s','STM32 ~30–50 мА'),('s','8 × DRV5055 48–80 мА'),('s','LED ~2–5 мА'),
   ('s','Кольцо WS2812 (5 В) до ~230 мА'),('t','Итого до ~370 мА — USB хватает'),('s','LDO Blue Pill 150–300 мА, запас есть'),
   ('sp',''),('b','Важно'),('s','Датчики — только от 3.3 В, не от 5 В'),('s','(иначе выход > 3.3 В на входе АЦП)'),
   ('s','Если ПК не видит USB: 1.8 кОм'),('s','между PA12 и 3.3 В (фикс R10)'),
   ('s','Земля датчиков и кольца WS2812'),('s','сходятся только на Blue Pill:'),('s','кольцо — своей парой 5V/GND'),
]
y=160
for kind,txt in L:
    if kind=='sp': y+=12; continue
    if kind=='b': a(f'<text x="{lx}" y="{y}" class="t b">{txt}</text>')
    elif kind=='dot': dot(lx+6,y-5,'#2b2a27'); a(f'<text x="{lx+20}" y="{y}" class="s">— соединение</text>')
    elif kind=='v': a(f'<path class="v" d="M{lx} {y-5} H{lx+30}"/><text x="{lx+40}" y="{y}" class="s">{txt}</text>')
    elif kind=='g': a(f'<path class="g" d="M{lx} {y-5} H{lx+30}"/><text x="{lx+40}" y="{y}" class="s">{txt}</text>')
    elif kind=='gs': gnd(lx+8,y-12); a(f'<text x="{lx+28}" y="{y}" class="s">{txt}</text>')
    elif kind=='m': a(f'<text x="{lx}" y="{y}" class="m">{txt}</text>')
    else: a(f'<text x="{lx}" y="{y}" class="{"t b" if kind=="t" else "s"}">{txt}</text>')
    y+=22
a('</svg>')
open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','spacemouse_schematic.svg'),'w').write('\n'.join(o))
