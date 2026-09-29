# SpaceRat

Самодельная 3D-мышь (6DOF) на датчиках Холла: Blue Pill (STM32F103C8), 8 × DRV5055,
магниты 10×2, энкодер EC11, 5 кнопок, кольцо WS2812. Прошивка на Rust + Embassy,
эмулирует 3Dconnexion SpaceMouse Pro Wireless (256f:c631).

## Общение

- **Отвечать пользователю на русском** — всё, включая короткие промежуточные
  сообщения о ходе работы.
- Целевая платформа — **только Windows + 3DxWare**. Linux не поддерживаем.

## Структура

| Путь | Что |
|---|---|
| `firmware/` | прошивка (Embassy); все настройки — `firmware/src/config.rs` |
| `firmware/README.md` | сборка, прошивка, калибровка, кольцо |
| `docs/hardware/` | схемы (SVG + PNG), чертёж размеров, распиновка, перечень компонентов |
| `docs/hardware/tools/` | Python-скрипты, генерирующие SVG-схемы |
| `docs/firmware/usb-hid-protocol.md` | USB HID SpaceMouse: дескрипторы, отчёты, частоты, биты кнопок |
| `tests/firmware_logic/` | тесты логики прошивки на ПК (модули из `firmware/src` через `#[path]`) |

## Команды

```sh
cd firmware && cargo build --release          # сборка (thumbv7m-none-eabi)
cd tests/firmware_logic && cargo test         # тесты логики на ПК
python3 docs/hardware/tools/gen_*.py          # перегенерировать схемы
```

## Соглашения

- Схемы не рисовать руками: править генератор в `docs/hardware/tools/` и
  перегенерировать SVG; PNG — рендер через Chromium для проверки.
- На схемах компоненты рисуются **там, где они стоят физически**
  (конденсатор у пина 3.3 — у пина 3.3), а не подписями.
- Логику, не зависящую от железа, держать в модулях без embassy
  (`calib.rs`, `input.rs`, `sensors.rs`, `led.rs`) и покрывать тестами в `tests/firmware_logic`.
- Flash: программе 63 КБ (`firmware/memory.x`), последняя страница — калибровка.
- Таймеры: TIM3 — время Embassy, TIM4 — энкодер, TIM1 + DMA1 ch5 — WS2812 (PA8).
- Не заявлять, что что-то работает на железе, если это проверено только сборкой/тестами.
