# USB HID: как самодельная 3D-мышь притворяется SpaceMouse

Сводка по открытым проектам: какие USB-идентификаторы, HID-дескрипторы, форматы
отчётов и частоты они используют, чтобы драйвер 3Dconnexion (3DxWare) и Linux
`spacenavd` принимали устройство за настоящую SpaceMouse.

## Источники

| Проект | Что взято | Версия |
|---|---|---|
| [AndunHH/spacemouse](https://github.com/AndunHH/spacemouse) — основная открытая прошивка (ветка от TeachingTech «Open Source SpaceMouse», есть вариант на 8 датчиках Холла) | `spacemouse-keys/SpaceMouseHID.{h,cpp}`, `config_sample*.h`, `set_hwids.py`, `SpaceNavigator.md`, `SpaceMouseWireless.md` (снифф настоящих устройств Wireshark'ом) | коммит `e23af0e` (2026-02-21) |
| [FreeSpacenav/spacenavd](https://github.com/FreeSpacenav/spacenavd) — драйвер для Linux | таблица VID/PID и раскладка кнопок, `src/dev.c` | коммит `6cb68b6` (2026-09-15) |
| [ANTz wiki: 3D-Mouse device list](https://github.com/openantz/antz/wiki/3D-Mouse#device-list) | список устройств (по ссылке из AndunHH) | — |

> ⚠️ VID 0x256f принадлежит 3Dconnexion. Эмуляция чужого VID/PID годится только для
> личного использования, не для продажи устройств.

---

## 1. Какое устройство эмулировать

Все открытые проекты (TeachingTech → AndunHH и их форки) представляются как
**SpaceMouse Pro Wireless (cabled)**. У этой модели 15 кнопок, 3DxWare
распознаёт их и даёт назначать им действия для каждой программы.

| Поле | Значение |
|---|---|
| idVendor | **0x256F** (3Dconnexion) |
| idProduct | **0xC631** (SpaceMouse Pro Wireless, кабель) |
| iManufacturer | `3Dconnexion` |
| iProduct | `SpaceMouse Pro Wireless (cabled)` |
| bcdUSB | 0x0200, Full Speed |
| bDeviceClass | 0x00 (класс задаётся в интерфейсе) |

Другие PID, которые узнаёт `spacenavd` (`src/dev.c`):

| VID:PID | Устройство | Кнопок в spacenavd |
|---|---|---|
| 046d:c626 | Space Navigator (Logitech-эра) | 2 |
| 046d:c62b | SpaceMouse Pro | 15 |
| 256f:c62e | SpaceMouse Wireless (кабель) | 2 |
| 256f:c631 | **SpaceMouse Pro Wireless (кабель)** | **15** |
| 256f:c632 | SpaceMouse Pro Wireless (приёмник) | 15 |
| 256f:c633 | SpaceMouse Enterprise | 31 |
| 256f:c635 | SpaceMouse Compact | 2 |

Для всех этих моделей `spacenavd` ставит флаги `DF_SWAPYZ | DF_INVYZ`: оси Y и Z
в HID-отчёте поменяны местами и инвертированы относительно системы координат
spacenavd.

## 2. Конфигурация USB

Один интерфейс HID и два interrupt-эндпоинта (AndunHH, `getInterface()`):

```
Interface: bInterfaceClass 0x03 (HID), SubClass 0, Protocol 0, bNumEndpoints 2
HID:       bcdHID 0x0111, bCountryCode 0, 1 дескриптор типа 0x22 (Report), длина = sizeof(report descriptor)
EP IN:     interrupt, устройство → ПК (оси, кнопки)
EP OUT:    interrupt, ПК → устройство (светодиод)
```

У AndunHH размер пакета берётся из ядра Arduino (64 байта), а `bInterval`
равен 0. Для STM32 лучше ставить **bInterval = 8 мс**: это период отчётов у
оригинального Space Navigator (§5). Сам bInterval оригинала в сниффах не записан. Размер эндпоинта хватит 16 байт: самый длинный отчёт — 13 байт.

Запросы класса HID (так делает AndunHH):
- `SET_IDLE`, `SET_PROTOCOL`: подтвердить и запомнить;
- `SET_REPORT`: подтвердить, данные можно игнорировать. При нажатии Calibrate
  драйвер шлёт Space Navigator'у `wValue=0x0307`, данные `07 00`. Эмуляции
  Pro Wireless драйвер этот запрос не отправляет;
- `GET_REPORT`, `GET_PROTOCOL`: не реализованы, работает и так.

## 3. Report-дескриптор (рекомендуемый, 92 байта)

Это дескриптор AndunHH: он повторяет SpaceMouse Pro Wireless, но расширяет
кнопки до 32 бит и выкидывает вендорские feature-отчёты.

```c
static const uint8_t SpaceMouseReportDescriptor[92] = {
    0x05, 0x01,        // Usage Page (Generic Desktop)
    0x09, 0x08,        // Usage (Multi-axis Controller)
    0xA1, 0x01,        // Collection (Application)
    // --- Report 1: 6 осей ---
    0xA1, 0x00,        //   Collection (Physical)
    0x85, 0x01,        //     Report ID (1)
    0x16, 0xA2, 0xFE,  //     Logical Minimum (-350)
    0x26, 0x5E, 0x01,  //     Logical Maximum (350)
    0x36, 0x88, 0xFA,  //     Physical Minimum (-1400)
    0x46, 0x78, 0x05,  //     Physical Maximum (1400)
    0x55, 0x0C,        //     Unit Exponent (-4)
    0x65, 0x11,        //     Unit (SI Linear, cm)
    0x09, 0x30,        //     Usage (X)
    0x09, 0x31,        //     Usage (Y)
    0x09, 0x32,        //     Usage (Z)
    0x09, 0x33,        //     Usage (Rx)
    0x09, 0x34,        //     Usage (Ry)
    0x09, 0x35,        //     Usage (Rz)
    0x75, 0x10,        //     Report Size (16)
    0x95, 0x06,        //     Report Count (6)
    0x81, 0x02,        //     Input (Data,Var,Abs)   ← 0x81,0x06 = Rel, см. §6
    0xC0,              //   End Collection
    // --- Report 3: 32 кнопки ---
    0xA1, 0x00,        //   Collection (Physical)
    0x85, 0x03,        //     Report ID (3)
    0x15, 0x00,        //     Logical Minimum (0)
    0x25, 0x01,        //     Logical Maximum (1)
    0x75, 0x01,        //     Report Size (1)
    0x95, 0x20,        //     Report Count (32)
    0x05, 0x09,        //     Usage Page (Button)
    0x19, 0x01,        //     Usage Minimum (1)
    0x29, 0x20,        //     Usage Maximum (32)
    0x81, 0x02,        //     Input (Data,Var,Abs)
    0xC0,              //   End Collection
    // --- Report 4: светодиод (ПК → устройство) ---
    0xA1, 0x02,        //   Collection (Logical)
    0x85, 0x04,        //     Report ID (4)
    0x05, 0x08,        //     Usage Page (LEDs)
    0x09, 0x4B,        //     Usage (Generic Indicator)
    0x15, 0x00,        //     Logical Minimum (0)
    0x25, 0x01,        //     Logical Maximum (1)
    0x95, 0x01,        //     Report Count (1)
    0x75, 0x01,        //     Report Size (1)
    0x91, 0x02,        //     Output (Data,Var,Abs)
    0x95, 0x01,        //     Report Count (1)
    0x75, 0x07,        //     Report Size (7)
    0x91, 0x03,        //     Output (Const) — padding
    0xC0,              //   End Collection
    0xC0               // End Collection
};
```

Отчёт светодиода (Report 4) оставляем, даже если светодиода нет: драйвер его шлёт,
устройство просто принимает и игнорирует.

### Для справки: как у оригинальных устройств

- **Space Navigator (046d:c626)** — 217 байт. Оси разделены на Report 1
  (X, Y, Z, `Input 0x06` — relative) и Report 2 (Rx, Ry, Rz, relative).
  Report 3 содержит 2 кнопки и 14 бит padding. Report 4 — светодиод. Дальше идут вендорские
  feature-отчёты 5–11 и 19 (Usage Page 0xFF00). Полный дамп лежит в
  `SpaceNavigator.md` у AndunHH.
- **SpaceMouse Wireless (256f:c62e)** — все 6 осей одним Report 1 (absolute),
  Report 3 — кнопки, Report 4 — светодиод, 0x17 — заряд батареи.

## 4. Форматы кадров

Все значения little-endian, int16 со знаком, рабочий диапазон **−350…+350**.
Первым байтом идёт Report ID.

### Report 1 — оси (устройство → ПК), 13 байт

```
байт:  0     1  2    3  4    5  6    7  8    9  10   11 12
     [01] [X lo X hi][Y lo Y hi][Z lo Z hi][Rx lo Rx hi][Ry lo Ry hi][Rz lo Rz hi]
```

Пример: только Ry = −30 (0xFFE2):
`01 00 00 00 00 00 00 00 00 E2 FF 00 00`

Старый формат Space Navigator — два отчёта по 7 байт:
`01 Xl Xh Yl Yh Zl Zh`, затем `02 RXl RXh RYl RYh RZl RZh`.
Пример из сниффа: `02 00 00 e2 ff 00 00`.

### Report 3 — кнопки (устройство → ПК), 5 байт

```
[03] [b0] [b1] [b2] [b3]    бит N (0…31) = кнопка N, байт = N/8, бит = N%8
```

Space Navigator отправляет 3 байта: `03 01 00` (нажата кнопка 1), `03 00 00` (отпущено),
`03 03 00` (нажаты обе).

### Report 4 — светодиод (ПК → устройство), 2 байта

`04 01` — включить, `04 00` — выключить.

## 5. Скорость и порядок отправки

| Устройство | Период | Частота |
|---|---|---|
| Space Navigator (снифф) | 8 мс между отчётами, по кругу R1 → R2 → (R3, если менялись кнопки) | 125 отчётов/с |
| SpaceMouse Wireless (снифф) | 16 мс | 62.5 отчётов/с |
| AndunHH (`HIDUPDATERATE_MS`) | **16 мс** между любыми двумя отчётами | 62.5 отчётов/с |

Правила, общие для сниффов и AndunHH:
1. Пока хоть одна ось ≠ 0, Report 1 уходит каждый период.
2. После того как все оси обнулились, отправить **ещё 3 нулевых** Report 1, потом
   замолчать. Иначе драйвер может «залипнуть» на последнем ненулевом значении.
3. Report 3 отправлять **только при изменении** кнопок, в очередном слоте
   расписания (не чаще одного отчёта за период).
4. В тишине (оси 0, кнопки не менялись) не отправлять ничего.

Для нашей прошивки: опрос АЦП и фильтрация идут быстрее (например, 1 кГц), а отчёты
отправляются по таймеру раз в 8–16 мс.

## 6. Absolute или relative

Подробнее — в обсуждении [spacenavd#108](https://github.com/FreeSpacenav/spacenavd/issues/108).

- **Absolute (0x81 0x02), по умолчанию.** Так делают современные 3Dconnexion. В Windows
  с 3DxWare работает. В Linux ядро генерирует событие только при **изменении**
  значения, поэтому если ручку держать неподвижно, движение в spacenavd
  останавливается.
- **Relative (0x81 0x06).** Так было у старого Space Navigator. События идут на каждый
  отчёт, но ось, не вернувшаяся точно в 0, продолжает «ехать».
- **Jiggle.** Решение AndunHH для Linux: оставить absolute и в каждом втором отчёте
  менять младший бит ненулевых значений (`|1` / `&~1`). Тогда значение всегда
  «меняется». Точность при этом не страдает.

Рекомендация: absolute + jiggle (включаемый опцией), так работают и Windows, и Linux.

## 7. Кнопки: какие биты реально понимает драйвер

Отчёт вмещает 32 кнопки, но драйвер для **SpaceMouse Pro** понимает только
15 бит. Индексы взяты из `bnhack_smpro` в spacenavd (Linux-код `BTN_0 + N`
= бит N) и совпадают с константами `SM_*` у AndunHH:

| Бит | Кнопка SpaceMouse Pro | Константа AndunHH |
|---|---|---|
| 0 | Menu | `SM_MENU` |
| 1 | Fit | `SM_FIT` |
| 2 | Top [T] | `SM_T` |
| 4 | Right [R] | `SM_R` |
| 5 | Front [F] | `SM_F` |
| 8 | Roll 90° CW | `SM_RCW` |
| 12 | 1 | `SM_1` |
| 13 | 2 | `SM_2` |
| 14 | 3 | `SM_3` |
| 15 | 4 | `SM_4` |
| 22 | Esc | `SM_ESC` |
| 23 | Alt | `SM_ALT` |
| 24 | Shift | `SM_SHFT` |
| 25 | Ctrl | `SM_CTRL` |
| 26 | Rotate (lock) | `SM_ROT` |

Остальные биты spacenavd игнорирует. Как 3DxWare ведёт себя с ними для модели Pro,
в источниках не проверено, так что закладываться на них не стоит.
**Практический предел — 15 кнопок**, а не 32. У SpaceMouse Enterprise (c633) 31
кнопка, но её индексы уходят за 32 бит (например, V1–V3 = биты 102–104). Это другой,
более длинный отчёт, и в этот дескриптор он не влезает.

В 3DxWare любую из этих кнопок можно переназначить на произвольную команду или
сочетание клавиш для каждой программы. Поэтому названия («Fit», «Top») значат только
действие по умолчанию.

### Раскладка для SpaceRat (8 хоткеев из `docs/hardware`)

| Вход | Бит | Кнопка по умолчанию |
|---|---|---|
| SW1 | 12 | 1 |
| SW2 | 13 | 2 |
| SW3 | 14 | 3 |
| SW4 | 15 | 4 |
| SW5 | 1 | Fit |
| Энкодер вправо | 2 | Top [T] |
| Энкодер влево | 4 | Right [R] |
| Нажатие энкодера | 5 | Front [F] |

Esc/Alt/Shift/Ctrl (биты 22–25) по умолчанию работают как клавиши клавиатуры,
их лучше оставить свободными. Биты 2/4/5 — обычные кнопки, в 3DxWare им назначаются любые действия.

Энкодер как кнопки (у AndunHH `ROTARY_KEYS`): каждый щелчок = «нажатие» бита
на ~20–30 мс, потом «отпускание». Это два Report 3, между ними минимум один
период отчётов. Быстрое вращение ставить в очередь, не склеивать.

## 8. Оси и направления

HID-оси: X, Y, Z (перемещение) и Rx, Ry, Rz (поворот). В AndunHH рекомендованы
такие инверсии для Windows + 3DxWare (`config_sample_hall_effect.h`, пометка «3Dc»):

| Ось | Инверсия |
|---|---|
| X (pan влево/вправо) | нет |
| Y (pan вверх/вниз) | да |
| Z (zoom) | да |
| Rx (наклон вперёд/назад) | нет |
| Ry (наклон влево/вправо) | да |
| Rz (поворот) | да |

Финальные знаки всё равно подбираются на живом устройстве. Удобно сделать их
настройкой, а не константами.

### Вариант AndunHH на 8 датчиках Холла (для сравнения)

Датчики HES0…HES9 (без 4 и 5) стоят парами по 4 сторонам, вид сверху, USB сзади:

```
      7   6
   8    |    3
     ---+---
   9    |    2
      0   1
```

```c
TX = (H1 - H0 + H6 - H7) / 2;
TY = (H2 - H3 + H9 - H8) / 2;
TZ = (H0 + H1 + H2 + H3 + H6 + H7 + H8 + H9) / 4;
RX = (H0 + H1 - H6 - H7) / 2;
RY = (H8 + H9 - H2 - H3) / 2;
RZ = (H0 + H2 + H6 + H8 - H1 - H3 - H7 - H9) / 4;
```

Это та же схема «сумма пары → Z/наклон, разность пары → сдвиг/поворот», что и в
`docs/hardware/README.md`, только в другой нумерации. Дальше AndunHH делит
результат на чувствительность, пропускает через нелинейную «modifier function» и
ограничивает ±350.

## 9. Чек-лист для прошивки на STM32

- [ ] Device descriptor: VID 0x256F, PID 0xC631, строки `3Dconnexion` /
      `SpaceMouse Pro Wireless (cabled)`.
- [ ] Один HID-интерфейс, EP IN + EP OUT interrupt, bInterval 8, размер 16–64.
- [ ] Report-дескриптор из §3 (92 байта).
- [ ] Ответы на SET_IDLE / SET_PROTOCOL / SET_REPORT (ACK).
- [ ] Report 1 (13 байт) каждые 8–16 мс, пока есть движение, плюс 3 нулевых после.
- [ ] Report 3 (5 байт) только при изменении кнопок, биты по таблице §7.
- [ ] Приём Report 4 (светодиод): прочитать и игнорировать.
- [ ] Значения ограничены ±350, опционально jiggle для Linux.
