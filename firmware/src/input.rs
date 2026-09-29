//! Кнопки и энкодер: антидребезг, декодирование квадратуры,
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

/// Декодер квадратуры по таблице переходов. Недопустимые переходы
/// (дребезг, пропуск) игнорируются.
#[derive(Default)]
pub struct Encoder {
    prev: u8,
    acc: i8,
}

impl Encoder {
    // Индекс: (prev << 2) | cur, где состояние = (A << 1) | B.
    const TABLE: [i8; 16] = [0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0];

    pub fn new(a: bool, b: bool) -> Self {
        Self { prev: state(a, b), acc: 0 }
    }

    /// Возвращает +1 / −1 на каждый полный щелчок, иначе 0.
    pub fn update(&mut self, a: bool, b: bool) -> i8 {
        let cur = state(a, b);
        if cur == self.prev {
            return 0;
        }
        self.acc += Self::TABLE[((self.prev << 2) | cur) as usize];
        self.prev = cur;
        if self.acc >= ENC_STEPS_PER_DETENT {
            self.acc = 0;
            if ENC_REVERSE { -1 } else { 1 }
        } else if self.acc <= -ENC_STEPS_PER_DETENT {
            self.acc = 0;
            if ENC_REVERSE { 1 } else { -1 }
        } else {
            0
        }
    }
}

fn state(a: bool, b: bool) -> u8 {
    ((a as u8) << 1) | (b as u8)
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

    pub fn push(&mut self, step: i8) {
        match step {
            1 if self.cw + self.ccw < ENC_QUEUE_MAX => self.cw += 1,
            -1 if self.cw + self.ccw < ENC_QUEUE_MAX => self.ccw += 1,
            _ => {}
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
