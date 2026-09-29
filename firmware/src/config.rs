//! Настройки прошивки. Всё, что подбирается на живом устройстве, — здесь.

// ---------------------------------------------------------------- USB ---

/// 3Dconnexion SpaceMouse Pro Wireless (cabled). См. docs/firmware/usb-hid-protocol.md §1.
pub const USB_VID: u16 = 0x256F;
pub const USB_PID: u16 = 0xC631;
pub const USB_MANUFACTURER: &str = "3Dconnexion";
pub const USB_PRODUCT: &str = "SpaceMouse Pro Wireless (cabled)";

/// Период отправки HID-отчётов (bInterval и шаг расписания), мс.
pub const REPORT_PERIOD_MS: u64 = 8;

/// Сколько нулевых отчётов осей отправить после остановки ручки.
pub const TRAILING_ZERO_REPORTS: u8 = 3;

/// Максимум по модулю для осей в HID-отчёте (логический диапазон дескриптора).
pub const AXIS_LIMIT: i32 = 350;

// ----------------------------------------------------------- Датчики ---

/// Период цикла опроса датчиков, мс.
pub const SENSOR_PERIOD_MS: u64 = 2;

/// Выборок АЦП на канал за цикл (усреднение).
pub const OVERSAMPLE: u32 = 8;

/// Сглаживание IIR: новое = старое + (сырое − старое) / 2^FILTER_SHIFT.
pub const FILTER_SHIFT: u32 = 2;

/// Пауза после включения перед калибровкой нуля, мс (не трогать ручку).
pub const CALIBRATION_SETTLE_MS: u64 = 500;

/// Циклов усреднения при калибровке нуля.
pub const CALIBRATION_CYCLES: u32 = 128;

/// Медленная подстройка нуля, пока ручку не трогают.
/// Включается, если все оси были в мёртвой зоне не меньше DRIFT_HOLD_MS.
pub const DRIFT_TRACKING: bool = true;
pub const DRIFT_HOLD_MS: u32 = 1000;
/// Скорость подстройки: ноль += (текущее − ноль) / 2^DRIFT_SHIFT за цикл.
pub const DRIFT_SHIFT: u32 = 6;

/// Предупреждение в лог, если датчик близок к рельсу (насыщение), в отсчётах АЦП.
pub const ADC_RAIL_MARGIN: u16 = 100;

// --------------------------------------------------------------- Оси ---
//
// Порядок осей везде: TX, TY, TZ, RX, RY, RZ (как в HID: X, Y, Z, Rx, Ry, Rz).
// Сырые оси считаются из пар датчиков (docs/hardware/README.md, «Оси»),
// единица — отсчёты АЦП.

/// Мёртвая зона по каждой оси, в сырых единицах (до усиления).
pub const DEADZONE: [i32; 6] = [12, 12, 20, 12, 12, 16];

/// Усиление: HID-значение = (|сырое| − мёртвая зона) × GAIN.
/// Подбирается так, чтобы полное отклонение ручки давало ~350.
pub const GAIN: [f32; 6] = [0.5, 0.5, 0.3, 0.5, 0.5, 0.4];

/// Инверсия осей. Знаки подбираются на собранном устройстве под 3DxWare.
pub const INVERT: [bool; 6] = [false, false, false, false, false, false];

// ------------------------------------------------ Кнопки и энкодер ---
//
// Номера битов в Report 3 — кнопки SpaceMouse Pro, понятные 3DxWare
// (docs/firmware/usb-hid-protocol.md §7). В 3DxWare им можно назначить что угодно.

pub const BIT_1: u8 = 12;
pub const BIT_2: u8 = 13;
pub const BIT_3: u8 = 14;
pub const BIT_4: u8 = 15;
pub const BIT_FIT: u8 = 1;
pub const BIT_TOP: u8 = 2;
pub const BIT_RIGHT: u8 = 4;
pub const BIT_FRONT: u8 = 5;

/// Биты для кнопок SW1…SW5 (PB8, PB12, PB13, PB14, PB15).
pub const BUTTON_BITS: [u8; 5] = [BIT_1, BIT_2, BIT_3, BIT_4, BIT_FIT];

/// Бит для нажатия на вал энкодера (PB5).
pub const ENC_BUTTON_BIT: u8 = BIT_FRONT;
/// Биты для щелчка энкодера по / против часовой стрелки.
pub const ENC_CW_BIT: u8 = BIT_TOP;
pub const ENC_CCW_BIT: u8 = BIT_RIGHT;

/// Период опроса кнопок и энкодера, мс.
pub const INPUT_PERIOD_MS: u64 = 1;

/// Антидребезг кнопок: столько мс подряд в новом состоянии.
pub const DEBOUNCE_MS: u8 = 5;

/// Переходов квадратуры на один щелчок (EC11 обычно 4, у некоторых 2).
pub const ENC_STEPS_PER_DETENT: i8 = 4;
/// Поменять направление энкодера.
pub const ENC_REVERSE: bool = false;

/// Длительность «нажатия» и паузы после него на один щелчок, мс.
/// Должны быть больше 2 × REPORT_PERIOD_MS, чтобы драйвер увидел оба отчёта.
pub const ENC_PRESS_MS: u16 = 30;
pub const ENC_GAP_MS: u16 = 30;
/// Сколько щелчков максимум держать в очереди при быстром вращении.
pub const ENC_QUEUE_MAX: u8 = 8;
