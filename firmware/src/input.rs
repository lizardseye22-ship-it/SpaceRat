//! Кнопки и энкодер: антидребезг, щелчки по счётчику TIM4,
//! превращение щелчков энкодера в короткие «нажатия» кнопок.
//! Вызывается раз в INPUT_PERIOD_MS.

use crate::config::*;

/// Антидребезг одной кнопки: состояние меняется, только если вход
/// DEBOUNCE_MS тиков подряд отличается от текущего.
#[derive(Clone, Copy, Default)]
pub struct Debouncer {
    pressed: bool,
    count: u8,
}

impl Debouncer {
    pub fn update(&mut self, raw_pressed: bool) -> bool {
        if raw_pressed == self.pressed {
            self.count = 0;
        } else {
            self.count += 1;
            if self.count >= DEBOUNCE_MS {
                self.pressed = raw_pressed;
                self.count = 0;
            }
        }
        self.pressed
    }
}

/// Щелчки энкодера по счётчику аппаратного декодера (TIM4, режим энкодера 3:
/// считаются все 4 фронта за цикл). Дребезг одного канала даёт +1/−1 и
/// взаимно гасится самим счётчиком.
pub struct EncoderCounter {
    last: u16,
    acc: i32,
}

impl EncoderCounter {
    pub fn new(count: u16) -> Self {
        Self { last: count, acc: 0 }
    }

    /// По новому значению счётчика возвращает число полных щелчков:
    /// > 0 — по часовой, < 0 — против. Переполнение счётчика учитывается.
    pub fn update(&mut self, count: u16) -> i32 {
        let delta = count.wrapping_sub(self.last) as i16 as i32;
        self.last = count;
        self.acc += if ENC_REVERSE { -delta } else { delta };
        let steps = ENC_STEPS_PER_DETENT as i32;
        let detents = self.acc / steps;
        self.acc -= detents * steps;
        detents
    }
}

enum PulsePhase {
    Idle,
    Press { bit: u8, left: u16 },
    Gap { left: u16 },
}

/// Очередь щелчков энкодера -> последовательность нажатие/пауза.
pub struct EncoderPulser {
    cw: u8,
    ccw: u8,
    phase: PulsePhase,
}

impl EncoderPulser {
    pub const fn new() -> Self {
        Self { cw: 0, ccw: 0, phase: PulsePhase::Idle }
    }

    /// Добавить щелчки в очередь (> 0 — по часовой, < 0 — против).
    pub fn push(&mut self, detents: i32) {
        for _ in 0..detents.unsigned_abs() {
            if self.cw + self.ccw >= ENC_QUEUE_MAX {
                break;
            }
            if detents > 0 {
                self.cw += 1;
            } else {
                self.ccw += 1;
            }
        }
    }

    /// Тик: возвращает маску «нажатой» сейчас кнопки энкодера (или 0).
    pub fn tick(&mut self) -> u32 {
        self.phase = match self.phase {
            PulsePhase::Idle => {
                if self.cw > 0 {
                    self.cw -= 1;
                    PulsePhase::Press { bit: ENC_CW_BIT, left: ENC_PRESS_MS }
                } else if self.ccw > 0 {
                    self.ccw -= 1;
                    PulsePhase::Press { bit: ENC_CCW_BIT, left: ENC_PRESS_MS }
                } else {
                    PulsePhase::Idle
                }
            }
            PulsePhase::Press { bit, left } if left > 1 => PulsePhase::Press { bit, left: left - 1 },
            PulsePhase::Press { .. } => PulsePhase::Gap { left: ENC_GAP_MS },
            PulsePhase::Gap { left } if left > 1 => PulsePhase::Gap { left: left - 1 },
            PulsePhase::Gap { .. } => PulsePhase::Idle,
        };
        match self.phase {
            PulsePhase::Press { bit, .. } => 1 << bit,
            _ => 0,
        }
    }
}
