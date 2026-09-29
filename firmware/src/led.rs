//! Кольцо WS2812: что показывать в каждом состоянии и упаковка кадра
//! в длительности импульсов для TIM1 + DMA.
//!
//! Углы (вид сверху): 0° = вправо, 90° = от себя, отсчёт против часовой.

use core::f32::consts::PI;

use crate::calib::CalView;
use crate::config::*;

#[derive(Clone, Copy, Default, PartialEq, Debug)]
pub struct Rgb {
    pub r: u8,
    pub g: u8,
    pub b: u8,
}

const fn rgb(r: u8, g: u8, b: u8) -> Rgb {
    Rgb { r, g, b }
}

const OFF: Rgb = rgb(0, 0, 0);
const WHITE: Rgb = rgb(255, 255, 255);
const GREEN: Rgb = rgb(0, 255, 40);
const RED: Rgb = rgb(255, 0, 0);
const PURPLE: Rgb = rgb(170, 0, 255);

/// Что сейчас происходит — задаётся прошивкой, кольцо рисует.
#[derive(Clone, Copy, PartialEq, Debug)]
pub enum LedState {
    /// Калибровка нуля при включении — не трогать.
    Boot,
    /// Обычная работа.
    Normal { axes: [i16; 6], calibrated: bool },
    /// Режим калибровки.
    Cal(CalView),
    /// Калибровка сохранена.
    Saved,
    /// Калибровка не удалась, остаются старые значения.
    Failed,
}

pub type Frame = [Rgb; LED_COUNT];

/// Геометрия кольца: угол, cos и sin каждого светодиода — считаются один раз.
pub struct Ring {
    angle: [f32; LED_COUNT],
    cos: [f32; LED_COUNT],
    sin: [f32; LED_COUNT],
}

/// Единичный вектор направления (cos θ, sin θ).
#[derive(Clone, Copy)]
struct Dir(f32, f32);

const RIGHT: Dir = Dir(1.0, 0.0);
const AWAY: Dir = Dir(0.0, 1.0);
const USER: Dir = Dir(0.0, -1.0);

impl Ring {
    pub fn new() -> Self {
        let mut r = Self { angle: [0.0; LED_COUNT], cos: [0.0; LED_COUNT], sin: [0.0; LED_COUNT] };
        let step = 2.0 * PI / LED_COUNT as f32;
        let dir = if LED_CLOCKWISE { -1.0 } else { 1.0 };
        for i in 0..LED_COUNT {
            let a = LED_FIRST_ANGLE_DEG * PI / 180.0 + dir * step * i as f32;
            r.angle[i] = a;
            r.cos[i] = libm::cosf(a);
            r.sin[i] = libm::sinf(a);
        }
        r
    }

    /// cos угла между светодиодом i и направлением d.
    fn dot(&self, i: usize, d: Dir) -> f32 {
        self.cos[i] * d.0 + self.sin[i] * d.1
    }

    /// «Лепесток»: 1.0 на направлении d, спадает к бокам.
    fn lobe(&self, i: usize, d: Dir) -> f32 {
        let c = self.dot(i, d);
        if c <= 0.0 { 0.0 } else { c * c * c * c }
    }

    /// Светодиод, ближайший к направлению d.
    fn nearest(&self, d: Dir) -> usize {
        (0..LED_COUNT).max_by(|&a, &b| self.dot(a, d).total_cmp(&self.dot(b, d))).unwrap_or(0)
    }

    /// Вращающаяся точка: `dir` = −1 по часовой, +1 против.
    fn chase(&self, f: &mut Frame, t_ms: u32, dir: f32, c: Rgb) {
        let theta = dir * 2.0 * PI * (t_ms % 1200) as f32 / 1200.0;
        let d = Dir(libm::cosf(theta), libm::sinf(theta));
        for (i, px) in f.iter_mut().enumerate() {
            let l = self.lobe(i, d);
            *px = max(*px, scale(c, l * l));
        }
    }
}

/// Направление вектора (x, y) и его длина.
fn dir_of(x: f32, y: f32) -> (Dir, f32) {
    let len = libm::sqrtf(x * x + y * y);
    if len < 1e-6 { (RIGHT, 0.0) } else { (Dir(x / len, y / len), len) }
}

fn scale(c: Rgb, k: f32) -> Rgb {
    let k = k.clamp(0.0, 1.0);
    rgb((c.r as f32 * k) as u8, (c.g as f32 * k) as u8, (c.b as f32 * k) as u8)
}

fn mix(a: Rgb, b: Rgb, t: f32) -> Rgb {
    let t = t.clamp(0.0, 1.0);
    let l = |x: u8, y: u8| (x as f32 + (y as f32 - x as f32) * t) as u8;
    rgb(l(a.r, b.r), l(a.g, b.g), l(a.b, b.b))
}

fn max(a: Rgb, b: Rgb) -> Rgb {
    rgb(a.r.max(b.r), a.g.max(b.g), a.b.max(b.b))
}

/// Плавное «дыхание» 0..1 с периодом `period_ms`.
fn breathe(t_ms: u32, period_ms: u32) -> f32 {
    let ph = (t_ms % period_ms) as f32 / period_ms as f32;
    0.5 - 0.5 * libm::cosf(2.0 * PI * ph)
}

fn blink(t_ms: u32, period_ms: u32) -> bool {
    t_ms % period_ms < period_ms / 2
}

/// Отрисовать кадр. `t_ms` — время в текущем состоянии.
pub fn render(ring: &Ring, state: &LedState, t_ms: u32) -> Frame {
    let mut f: Frame = [OFF; LED_COUNT];
    match *state {
        LedState::Boot => ring.chase(&mut f, t_ms, -1.0, WHITE),

        LedState::Normal { axes, calibrated } => {
            let color = rgb(LED_COLOR[0], LED_COLOR[1], LED_COLOR[2]);
            // Фон: ровное свечение; пока нет калибровки — медленно «дышит».
            let mut base = LED_IDLE_LEVEL;
            if !calibrated {
                base *= 0.35 + 0.65 * breathe(t_ms, 3000);
            }
            let mut level = [base; LED_COUNT];
            if LED_SHOW_MOTION {
                let n = |v: i16| (v as f32 / AXIS_LIMIT as f32).clamp(-1.0, 1.0);
                let (tx, ty, tz, rx, ry, rz) = (n(axes[0]), n(axes[1]), n(axes[2]), n(axes[3]), n(axes[4]), n(axes[5]));
                // Нажали (TZ+) — всё кольцо ярче до максимума, подняли — тусклее.
                let z = if tz >= 0.0 { base + tz * (1.0 - base) } else { base * (1.0 + 0.85 * tz) };
                // Куда сдвигаем / наклоняем — та сторона ярче, противоположная гаснет.
                // Наклон от себя (RX+) — сторона 90°, вправо (RY+) — 0°.
                let (t_dir, t_len) = dir_of(tx, ty);
                let (r_dir, r_len) = dir_of(ry, rx);
                // Поворот: пятно уезжает от переднего края (90°) в сторону вращения,
                // на полном повороте — на 90°. RZ+ = по часовой.
                let rot = PI / 2.0 - rz * PI / 2.0;
                let rot_dir = Dir(libm::cosf(rot), libm::sinf(rot));
                let side = |i: usize, d: Dir, len: f32| len * (ring.lobe(i, d) - 0.5 * ring.lobe(i, Dir(-d.0, -d.1)));
                for (i, l) in level.iter_mut().enumerate() {
                    *l = z + LED_DIR_GAIN
                        * (side(i, t_dir, t_len) + side(i, r_dir, r_len) + side(i, rot_dir, libm::fabsf(rz)));
                }
            }
            for (px, l) in f.iter_mut().zip(level) {
                *px = scale(color, l);
            }
        }

        LedState::Cal(view) => match view {
            CalView::Step { axis, hold } => {
                // Что сделать: 0 вправо, 1 от себя, 2 нажать, 3 наклон от себя,
                // 4 наклон вправо, 5 поворот по часовой. Сдвиги — зелёные,
                // наклоны — фиолетовые; по мере удержания цвет уходит в белый.
                let base = if axis == 3 || axis == 4 { PURPLE } else { GREEN };
                let c = mix(base, WHITE, hold);
                match axis {
                    0 | 4 => f.iter_mut().enumerate().for_each(|(i, px)| *px = scale(c, ring.lobe(i, RIGHT))),
                    1 | 3 => f.iter_mut().enumerate().for_each(|(i, px)| *px = scale(c, ring.lobe(i, AWAY))),
                    2 => {
                        let k = 0.3 + 0.7 * breathe(t_ms, 700);
                        f.iter_mut().for_each(|px| *px = scale(c, k));
                    }
                    _ => ring.chase(&mut f, t_ms, -1.0, c),
                }
                // Номер шага: столько белых точек со стороны пользователя (270°).
                let center = ring.nearest(USER) as isize;
                let count = axis as isize + 1;
                for n in 0..count {
                    let i = (center + n - count / 2).rem_euclid(LED_COUNT as isize) as usize;
                    f[i] = scale(WHITE, 0.5);
                }
            }
            CalView::Release { rejected } => {
                if rejected {
                    let c = if blink(t_ms, 300) { RED } else { OFF };
                    f.iter_mut().for_each(|px| *px = scale(c, 0.7));
                } else {
                    f.iter_mut().for_each(|px| *px = scale(GREEN, 0.4));
                }
            }
            CalView::Free { progress } => {
                // Радуга по заполненной части круга: «крутите во все стороны».
                let lit = (progress.clamp(0.0, 1.0) * LED_COUNT as f32) as usize;
                for (i, px) in f.iter_mut().enumerate() {
                    let hue = ((i * 256 / LED_COUNT) as u32 + t_ms / 8) as u8;
                    let k = if i < lit { 1.0 } else { 0.08 };
                    *px = scale(wheel(hue), k);
                }
            }
            CalView::Noise { progress } => {
                // Не трогать: белое заполнение.
                let lit = (progress.clamp(0.0, 1.0) * LED_COUNT as f32) as usize;
                for (i, px) in f.iter_mut().enumerate() {
                    *px = scale(WHITE, if i < lit { 0.6 } else { 0.1 });
                }
            }
        },

        LedState::Saved => {
            let c = if blink(t_ms, 400) { GREEN } else { OFF };
            f.iter_mut().for_each(|px| *px = c);
        }
        LedState::Failed => {
            let c = if blink(t_ms, 400) { RED } else { OFF };
            f.iter_mut().for_each(|px| *px = c);
        }
    }
    f
}

/// Цветовой круг 0..255 -> цвет.
fn wheel(h: u8) -> Rgb {
    let h = h as u16;
    match h {
        0..=84 => rgb((255 - h * 3) as u8, (h * 3) as u8, 0),
        85..=169 => {
            let h = h - 85;
            rgb(0, (255 - h * 3) as u8, (h * 3) as u8)
        }
        _ => {
            let h = h - 170;
            rgb((h * 3) as u8, 0, (255 - h * 3) as u8)
        }
    }
}

/// Длина буфера DMA: 24 бита на светодиод + 0 в конце (линия остаётся в 0).
pub const DMA_LEN: usize = LED_COUNT * 24 + 1;

/// Кадр -> длительности импульсов. Порядок бит WS2812: G, R, B, старший бит первым.
/// `n0`/`n1` — значения сравнения таймера для «0» и «1».
pub fn encode(frame: &Frame, n0: u16, n1: u16, out: &mut [u16; DMA_LEN]) {
    let mut i = 0;
    for px in frame {
        for c in [px.g, px.r, px.b] {
            let c = (c as u16 * LED_BRIGHTNESS as u16 / 255) as u8;
            for bit in (0..8).rev() {
                out[i] = if c >> bit & 1 != 0 { n1 } else { n0 };
                i += 1;
            }
        }
    }
    out[i] = 0;
}
