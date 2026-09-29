# SpaceRat — прошивка (Embassy, Blue Pill)

Прошивка для STM32F103C8 (Blue Pill) на Rust + [Embassy](https://embassy.dev).
Устройство представляется как **3Dconnexion SpaceMouse Pro Wireless (cabled)**
(VID 0x256F, PID 0xC631) и работает с драйвером **3DxWare под Windows**.

- Железо и распиновка: [`../docs/hardware`](../docs/hardware)
- USB-протокол: [`../docs/firmware/usb-hid-protocol.md`](../docs/firmware/usb-hid-protocol.md)

## Что делает

| Задача | Как |
|---|---|
| 8 датчиков Холла, PA0–PA7 | АЦП, 8 выборок на канал, цикл 2 мс, IIR-фильтр |
| Калибровка нуля | при включении: 0.5 с пауза, затем усреднение ~0.3 с. **Ручку в это время не трогать** |
| Дрейф нуля | медленная подстройка, если ручку не трогают дольше 1 с |
| 6 осей | суммы/разности пар → TX TY TZ RX RY RZ, мёртвая зона, усиление, ограничение ±350 |
| 5 кнопок, PB8 PB12–PB15 | внутренние pull-up, антидребезг 5 мс |
| Энкодер EC11, PB6/PB7 + кнопка PB5 | программная квадратура (1 кГц), щелчок → «нажатие» 30 мс + пауза 30 мс |
| USB HID | отчёт раз в 8 мс: оси (Report 1), пока есть движение, + 3 нулевых; кнопки (Report 3) при изменении; светодиод (Report 4) принимается и игнорируется |

Кнопки → кнопки SpaceMouse Pro (в 3DxWare им назначается что угодно):

| Вход | Кнопка SpaceMouse Pro |
|---|---|
| SW1–SW4 | 1–4 |
| SW5 | Fit |
| Энкодер вправо / влево | Top [T] / Right [R] |
| Нажатие энкодера | Front [F] |

## Сборка

Нужен Rust (https://rustup.rs). Цель `thumbv7m-none-eabi` поставится сама
по `rust-toolchain.toml`.

```sh
cd firmware
cargo build --release
```

Результат: `target/thumbv7m-none-eabi/release/spacerat` (ELF). Размер ~31 КБ flash, ~3 КБ RAM.

## Прошивка

**ST-Link + probe-rs** (рекомендуется, заодно виден лог):

```sh
cargo install probe-rs-tools
cargo run --release          # прошьёт и покажет лог defmt
```

**ST-Link + STM32CubeProgrammer / st-flash** (нужен .bin):

```sh
cargo install cargo-binutils && rustup component add llvm-tools
cargo objcopy --release -- -O binary spacerat.bin
# STM32CubeProgrammer: адрес 0x08000000
# или: st-flash write spacerat.bin 0x8000000
```

Джамперы BOOT0/BOOT1 на Blue Pill — в 0 (обычный режим).

## Первое включение

1. Подключить USB, **не трогать ручку ~1 с** (калибровка нуля).
2. В диспетчере устройств Windows появится HID-устройство, 3DxWare покажет
   SpaceMouse Pro Wireless.
3. В 3DxWare проверить оси (окно Test/Calibrate) и назначить кнопки.

## Настройка

Все параметры — в [`src/config.rs`](src/config.rs):

| Параметр | Что |
|---|---|
| `INVERT` | инверсия каждой оси — подобрать знаки под 3DxWare |
| `GAIN` | усиление: полное отклонение ручки должно давать ~350 |
| `DEADZONE` | мёртвая зона в сырых единицах (дрожание в покое) |
| `BUTTON_BITS`, `ENC_*_BIT` | какая кнопка SpaceMouse Pro на каком входе |
| `ENC_STEPS_PER_DETENT`, `ENC_REVERSE` | тип и направление энкодера |
| `REPORT_PERIOD_MS` | период HID-отчётов (8 мс = как Space Navigator) |

Сырые значения для настройки видны в логе при `DEFMT_LOG=debug`:

```sh
DEFMT_LOG=debug cargo run --release
# raw [..8 датчиков..] axes_raw [..6 осей до усиления..] hid [..что уходит в ПК..]
```

Порядок: сначала `INVERT` (знаки), затем `GAIN` (чтобы полный ход ≈ 350),
затем `DEADZONE` (чуть больше дрожания `axes_raw` в покое).
В логе также есть предупреждение, если датчик близок к рельсу (магнит слишком близко).

## Проверка логики на ПК

Энкодер, антидребезг, формулы осей и калибровка покрыты тестами, которые
идут на ПК без платы:

```sh
# из корня репозитория
cd tests/firmware_logic
cargo test
```

## Структура

| Файл | Что |
|---|---|
| `src/main.rs` | тактирование, USB, задачи: датчики, кнопки, отчёты |
| `src/config.rs` | все настройки |
| `src/hid.rs` | HID-дескриптор (92 байта), сборка отчётов, ответы на запросы класса |
| `src/sensors.rs` | ноль, фильтр, пары → оси, мёртвая зона, усиление |
| `src/input.rs` | антидребезг, квадратура энкодера, щелчки → нажатия |
