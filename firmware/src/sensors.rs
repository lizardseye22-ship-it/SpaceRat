//! Обработка 8 датчиков Холла: ноль, фильтр, пары -> 6 осей.
//! Схема и формулы: docs/hardware/README.md.

use crate::config::*;

pub const SENSORS: usize = 8;

/// Внутренние значения хранятся ×16, чтобы IIR и подстройка нуля не теряли дробную часть.
const SCALE_SHIFT: u32 = 4;

pub struct Processor {
    filt: [i32; SENSORS],
    zero: [i32; SENSORS],
    still_ms: u32,
}

impl Processor {
    pub const fn new() -> Self {
        Self { filt: [0; SENSORS], zero: [0; SENSORS], still_ms: 0 }
    }

    /// Задать ноль по усреднённым сырым значениям (единицы АЦП).
    pub fn set_zero(&mut self, raw: &[u32; SENSORS]) {
        for i in 0..SENSORS {
            self.zero[i] = (raw[i] as i32) << SCALE_SHIFT;
            self.filt[i] = self.zero[i];
        }
        self.still_ms = 0;
    }

    /// Один цикл: сырые значения (единицы АЦП) -> оси для HID.
    /// Возвращает также сырые оси (до мёртвой зоны и усиления) для отладки.
    pub fn update(&mut self, raw: &[u16; SENSORS]) -> ([i16; 6], [i32; 6]) {
        let mut c = [0i32; SENSORS];
        for i in 0..SENSORS {
            let x = (raw[i] as i32) << SCALE_SHIFT;
            self.filt[i] += (x - self.filt[i]) >> FILTER_SHIFT;
            c[i] = (self.filt[i] - self.zero[i]) >> SCALE_SHIFT;
        }

        let raw_axes = pairs_to_axes(&c);

        let mut out = [0i16; 6];
        let mut still = true;
        for k in 0..6 {
            let a = if INVERT[k] { -raw_axes[k] } else { raw_axes[k] };
            let mag = a.abs() - DEADZONE[k];
            if mag > 0 {
                still = false;
                let v = (mag as f32 * GAIN[k]) as i32;
                let v = v.min(AXIS_LIMIT);
                out[k] = (if a < 0 { -v } else { v }) as i16;
            }
        }

        // Медленно подтягиваем ноль, пока ручку не трогают.
        if still {
            self.still_ms = self.still_ms.saturating_add(SENSOR_PERIOD_MS as u32);
            if DRIFT_TRACKING && self.still_ms >= DRIFT_HOLD_MS {
                for i in 0..SENSORS {
                    self.zero[i] += (self.filt[i] - self.zero[i]) >> DRIFT_SHIFT;
                }
            }
        } else {
            self.still_ms = 0;
        }

        (out, raw_axes)
    }
}

/// Пара p — датчики 2p (A) и 2p+1 (B): U1/U2 = пара 0 (0°), U3/U4 = пара 1 (90°) и т.д.
/// Sp = A + B (магнит ближе/дальше), Dp = A − B (сдвиг вдоль касательной).
/// Результат: [TX, TY, TZ, RX, RY, RZ].
pub fn pairs_to_axes(c: &[i32; SENSORS]) -> [i32; 6] {
    let s = |p: usize| c[2 * p] + c[2 * p + 1];
    let d = |p: usize| c[2 * p] - c[2 * p + 1];
    [
        d(3) - d(1),               // TX
        d(0) - d(2),               // TY
        s(0) + s(1) + s(2) + s(3), // TZ
        s(1) - s(3),               // RX
        s(2) - s(0),               // RY
        d(0) + d(1) + d(2) + d(3), // RZ
    ]
}
