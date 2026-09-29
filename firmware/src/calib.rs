//! Калибровка: данные, их применение к осям, хранение в байтах
//! и мастер калибровки (SW1 + SW5 при включении).
//!
//! Единицы: «сырые оси» — суммы/разности пар в отсчётах АЦП (sensors.rs),
//! «нормированные» — 1.0 = полный ход ручки = AXIS_LIMIT в HID.

use crate::config::*;

const AXES: usize = 6;

fn fabs(x: f32) -> f32 {
    if x < 0.0 { -x } else { x }
}

/// Результат калибровки.
#[derive(Clone, Copy, PartialEq, Debug)]
pub struct CalData {
    /// Матрица развязки: нормированные оси = m × сырые оси.
    /// Убирает перекрёстное влияние и задаёт знак и масштаб.
    pub m: [[f32; AXES]; AXES],
    /// Мёртвая зона в нормированных единицах.
    pub dz: [f32; AXES],
    /// Дополнительное усиление в «+» и «−» направлении.
    pub gpos: [f32; AXES],
    pub gneg: [f32; AXES],
}

impl CalData {
    /// Значения из config.rs — пока мышь не откалибрована.
    pub fn defaults() -> Self {
        let mut m = [[0.0; AXES]; AXES];
        let mut dz = [0.0; AXES];
        for k in 0..AXES {
            m[k][k] = GAIN[k] / AXIS_LIMIT as f32;
            dz[k] = DEADZONE[k] as f32 * GAIN[k] / AXIS_LIMIT as f32;
        }
        Self { m, dz, gpos: [1.0; AXES], gneg: [1.0; AXES] }
    }

    /// Сырые оси -> нормированные (до мёртвой зоны).
    pub fn normalize(&self, raw: &[i32; AXES]) -> [f32; AXES] {
        let mut u = [0.0; AXES];
        for k in 0..AXES {
            for j in 0..AXES {
                u[k] += self.m[k][j] * raw[j] as f32;
            }
        }
        u
    }

    /// Сырые оси -> значения для HID (±AXIS_LIMIT).
    pub fn apply(&self, raw: &[i32; AXES]) -> [i16; AXES] {
        let u = self.normalize(raw);
        let mut out = [0i16; AXES];
        for k in 0..AXES {
            let v = if INVERT[k] { -u[k] } else { u[k] };
            let mag = fabs(v) - self.dz[k];
            if mag > 0.0 {
                let g = if v > 0.0 { self.gpos[k] } else { self.gneg[k] };
                let x = (mag * g * AXIS_LIMIT as f32 + 0.5) as i32; // округление
                let x = x.min(AXIS_LIMIT);
                out[k] = (if v < 0.0 { -x } else { x }) as i16;
            }
        }
        out
    }

    // ------------------------------------------------ хранение ---

    pub const MAGIC: u32 = 0x3143_5253; // "SRC1"
    const FLOATS: usize = AXES * AXES + 3 * AXES;
    /// magic + данные + crc; длина чётная (запись во flash F1 — по 2 байта).
    pub const BYTES: usize = 4 + Self::FLOATS * 4 + 4;

    pub fn to_bytes(&self) -> [u8; Self::BYTES] {
        let mut b = [0u8; Self::BYTES];
        b[0..4].copy_from_slice(&Self::MAGIC.to_le_bytes());
        let mut i = 4;
        for v in self.floats() {
            b[i..i + 4].copy_from_slice(&v.to_le_bytes());
            i += 4;
        }
        let crc = crc32(&b[..i]);
        b[i..i + 4].copy_from_slice(&crc.to_le_bytes());
        b
    }

    /// None, если данных нет, они повреждены или содержат NaN/∞.
    pub fn from_bytes(b: &[u8]) -> Option<Self> {
        if b.len() < Self::BYTES {
            return None;
        }
        let word = |i: usize| u32::from_le_bytes([b[i], b[i + 1], b[i + 2], b[i + 3]]);
        let end = Self::BYTES - 4;
        if word(0) != Self::MAGIC || word(end) != crc32(&b[..end]) {
            return None;
        }
        let mut f = [0.0f32; Self::FLOATS];
        for (n, v) in f.iter_mut().enumerate() {
            *v = f32::from_bits(word(4 + 4 * n));
            if !v.is_finite() {
                return None;
            }
        }
        let mut c = Self { m: [[0.0; AXES]; AXES], dz: [0.0; AXES], gpos: [0.0; AXES], gneg: [0.0; AXES] };
        let mut it = f.iter().copied();
        for row in c.m.iter_mut() {
            for v in row.iter_mut() {
                *v = it.next()?;
            }
        }
        for arr in [&mut c.dz, &mut c.gpos, &mut c.gneg] {
            for v in arr.iter_mut() {
                *v = it.next()?;
            }
        }
        Some(c)
    }

    fn floats(&self) -> impl Iterator<Item = f32> + '_ {
        self.m
            .iter()
            .flat_map(|r| r.iter().copied())
            .chain(self.dz.iter().copied())
            .chain(self.gpos.iter().copied())
            .chain(self.gneg.iter().copied())
    }
}

/// CRC-32 (IEEE), побитно — данных мало.
pub fn crc32(data: &[u8]) -> u32 {
    let mut crc = 0xFFFF_FFFFu32;
    for &byte in data {
        crc ^= byte as u32;
        for _ in 0..8 {
            crc = if crc & 1 != 0 { (crc >> 1) ^ 0xEDB8_8320 } else { crc >> 1 };
        }
    }
    !crc
}

/// Обратная матрица 6×6 методом Гаусса–Жордана с выбором ведущего элемента.
/// None, если матрица вырождена (шаги калибровки не различаются).
pub fn invert(a: &[[f32; AXES]; AXES]) -> Option<[[f32; AXES]; AXES]> {
    let mut m = *a;
    let mut inv = [[0.0f32; AXES]; AXES];
    for (i, row) in inv.iter_mut().enumerate() {
        row[i] = 1.0;
    }
    // Порог вырожденности относительно масштаба матрицы.
    let scale = m.iter().flat_map(|r| r.iter()).fold(0.0f32, |acc, v| acc.max(fabs(*v)));
    if scale == 0.0 {
        return None;
    }
    for col in 0..AXES {
        let pivot = (col..AXES).max_by(|&x, &y| fabs(m[x][col]).total_cmp(&fabs(m[y][col])))?;
        if fabs(m[pivot][col]) < scale * 1e-4 {
            return None;
        }
        m.swap(col, pivot);
        inv.swap(col, pivot);
        let p = m[col][col];
        for j in 0..AXES {
            m[col][j] /= p;
            inv[col][j] /= p;
        }
        for r in 0..AXES {
            if r != col {
                let f = m[r][col];
                if f != 0.0 {
                    for j in 0..AXES {
                        m[r][j] -= f * m[col][j];
                        inv[r][j] -= f * inv[col][j];
                    }
                }
            }
        }
    }
    Some(inv)
}

// ================================================================ мастер ===

/// Что сейчас показывать на кольце.
#[derive(Clone, Copy, PartialEq, Debug)]
pub enum CalView {
    /// Шаг 1–6: выполнить движение `axis` и держать. `hold` 0..1 — сколько удержано.
    Step { axis: u8, hold: f32 },
    /// Шаг записан или отклонён — отпустить ручку в центр.
    Release { rejected: bool },
    /// Свободное вращение во все стороны, `progress` 0..1.
    Free { progress: f32 },
    /// Отпустить ручку и не трогать, замер шума, `progress` 0..1.
    Noise { progress: f32 },
}

/// Событие для прошивки.
#[derive(Clone, Copy, PartialEq, Debug)]
pub enum CalEvent {
    None,
    Captured(u8),
    Rejected(u8),
    Finished(CalData),
    /// Шаги не дали обратимую матрицу — калибровку надо повторить.
    Failed,
}

#[derive(Clone, Copy)]
enum Phase {
    Step,
    Release { rejected: bool },
    Free { t: u32 },
    WaitRest,
    Noise { t: u32 },
    Done,
}

pub struct Calibrator {
    phase: Phase,
    step: usize,
    /// Отклик сырых осей на каждое из 6 движений (столбцы).
    resp: [[f32; AXES]; AXES],
    used: [bool; AXES],
    ema: [f32; AXES],
    stable_ms: u32,
    m: [[f32; AXES]; AXES],
    umax: [f32; AXES],
    umin: [f32; AXES],
    noise: [f32; AXES],
}

impl Calibrator {
    pub const fn new() -> Self {
        Self {
            phase: Phase::Step,
            step: 0,
            resp: [[0.0; AXES]; AXES],
            used: [false; AXES],
            ema: [0.0; AXES],
            stable_ms: 0,
            m: [[0.0; AXES]; AXES],
            umax: [0.0; AXES],
            umin: [0.0; AXES],
            noise: [0.0; AXES],
        }
    }

    pub fn view(&self) -> CalView {
        match self.phase {
            Phase::Step => CalView::Step {
                axis: self.step as u8,
                hold: (self.stable_ms as f32 / CAL_HOLD_MS as f32).min(1.0),
            },
            Phase::Release { rejected } => CalView::Release { rejected },
            Phase::Free { t } => CalView::Free { progress: t as f32 / CAL_FREE_MS as f32 },
            Phase::WaitRest => CalView::Noise { progress: 0.0 },
            Phase::Noise { t } => CalView::Noise { progress: t as f32 / CAL_NOISE_MS as f32 },
            Phase::Done => CalView::Noise { progress: 1.0 },
        }
    }

    /// Один цикл: сырые оси, прошедшее время.
    pub fn update(&mut self, raw: &[i32; AXES], dt_ms: u32) -> CalEvent {
        let r = raw.map(|v| v as f32);
        let level = r.iter().fold(0.0f32, |a, v| a.max(fabs(*v)));

        match self.phase {
            Phase::Step => {
                if level < CAL_MIN_SIGNAL {
                    self.stable_ms = 0;
                    self.ema = r;
                    return CalEvent::None;
                }
                // Удержание: текущее значение близко к сглаженному.
                let mut dev = 0.0f32;
                for k in 0..AXES {
                    self.ema[k] += (r[k] - self.ema[k]) * 0.05;
                    dev = dev.max(fabs(r[k] - self.ema[k]));
                }
                if dev > CAL_STABLE_TOL * level {
                    self.stable_ms = 0;
                    return CalEvent::None;
                }
                self.stable_ms += dt_ms;
                if self.stable_ms < CAL_HOLD_MS {
                    return CalEvent::None;
                }
                // Записываем шаг. Самая сильная сырая ось не должна совпадать
                // с уже записанной — иначе движение перепутано.
                let v = self.ema;
                let dom = (0..AXES).max_by(|&a, &b| fabs(v[a]).total_cmp(&fabs(v[b]))).unwrap_or(0);
                let s = self.step as u8;
                self.stable_ms = 0;
                if self.used[dom] {
                    self.phase = Phase::Release { rejected: true };
                    return CalEvent::Rejected(s);
                }
                self.used[dom] = true;
                for k in 0..AXES {
                    self.resp[k][self.step] = v[k];
                }
                self.step += 1;
                self.phase = Phase::Release { rejected: false };
                CalEvent::Captured(s)
            }
            Phase::Release { .. } => {
                if level < CAL_MIN_SIGNAL * 0.5 {
                    if self.step < AXES {
                        self.phase = Phase::Step;
                    } else {
                        // Все 6 шагов: m = resp⁻¹, тогда движение j даёт 1.0 по оси j.
                        match invert(&self.resp) {
                            Some(m) => {
                                self.m = m;
                                self.phase = Phase::Free { t: 0 };
                            }
                            None => {
                                self.phase = Phase::Done;
                                return CalEvent::Failed;
                            }
                        }
                    }
                }
                CalEvent::None
            }
            Phase::Free { t } => {
                let u = self.normalize(raw);
                for k in 0..AXES {
                    self.umax[k] = self.umax[k].max(u[k]);
                    self.umin[k] = self.umin[k].min(u[k]);
                }
                let t = t + dt_ms;
                self.phase = if t >= CAL_FREE_MS { Phase::WaitRest } else { Phase::Free { t } };
                CalEvent::None
            }
            Phase::WaitRest => {
                if level < CAL_MIN_SIGNAL * 0.5 {
                    self.phase = Phase::Noise { t: 0 };
                }
                CalEvent::None
            }
            Phase::Noise { t } => {
                let u = self.normalize(raw);
                for k in 0..AXES {
                    self.noise[k] = self.noise[k].max(fabs(u[k]));
                }
                let t = t + dt_ms;
                if t < CAL_NOISE_MS {
                    self.phase = Phase::Noise { t };
                    return CalEvent::None;
                }
                self.phase = Phase::Done;
                CalEvent::Finished(self.result())
            }
            Phase::Done => CalEvent::None,
        }
    }

    fn normalize(&self, raw: &[i32; AXES]) -> [f32; AXES] {
        let mut u = [0.0; AXES];
        for k in 0..AXES {
            for j in 0..AXES {
                u[k] += self.m[k][j] * raw[j] as f32;
            }
        }
        u
    }

    fn result(&self) -> CalData {
        let mut c = CalData { m: self.m, dz: [0.0; AXES], gpos: [1.0; AXES], gneg: [1.0; AXES] };
        for k in 0..AXES {
            c.dz[k] = (self.noise[k] * CAL_DZ_FACTOR).max(CAL_DZ_MIN);
            // Если в свободной фазе ось докрутили хотя бы до 30 % — уточняем масштаб
            // так, чтобы максимум (за вычетом мёртвой зоны) давал полный ход.
            if self.umax[k] > 0.3 {
                c.gpos[k] = 1.0 / (self.umax[k] - c.dz[k]).max(0.1);
            }
            if -self.umin[k] > 0.3 {
                c.gneg[k] = 1.0 / (-self.umin[k] - c.dz[k]).max(0.1);
            }
        }
        c
    }
}
