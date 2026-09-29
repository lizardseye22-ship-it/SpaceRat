//! Проверка логики прошивки на ПК: cargo test (из этой папки).
//! Модули подключаются из firmware/src как есть.
#![allow(dead_code)]
#[path = "../../../firmware/src/config.rs"] pub mod config;
#[path = "../../../firmware/src/input.rs"] pub mod input;
#[path = "../../../firmware/src/sensors.rs"] pub mod sensors;
#[path = "../../../firmware/src/calib.rs"] pub mod calib;
#[path = "../../../firmware/src/led.rs"] pub mod led;
#[cfg(test)]
mod tests {
    use super::input::*;
    use super::sensors::*;
    use super::config::*;

    #[test] fn encoder_counter_detents() {
        let steps = ENC_STEPS_PER_DETENT as u16;
        let mut e = EncoderCounter::new(100);
        assert_eq!(e.update(100 + steps - 1), 0);      // не дошли до щелчка
        let cw = e.update(100 + steps);                  // полный щелчок
        assert_eq!(cw.abs(), 1);
        assert_eq!(e.update(100), -cw);                  // обратно
        assert_eq!(e.update(100 + 3 * steps), 3 * cw);  // три щелчка за раз
    }
    #[test] fn encoder_counter_bounce_and_wrap() {
        let mut e = EncoderCounter::new(0);
        for _ in 0..20 { assert_eq!(e.update(1), 0); assert_eq!(e.update(0), 0); } // дребезг ±1
        let mut e = EncoderCounter::new(65534);
        let steps = ENC_STEPS_PER_DETENT as u16;
        assert_eq!(e.update(65534u16.wrapping_add(steps)).abs(), 1); // через переполнение
    }
    #[test] fn pulser_queue_limit() {
        let mut p = EncoderPulser::new();
        p.push(100);
        let presses = core::iter::once(0).chain((0..10_000).map(|_| p.tick())).collect::<Vec<_>>()
            .windows(2).filter(|w| w[0] == 0 && w[1] != 0).count();
        assert_eq!(presses, ENC_QUEUE_MAX as usize);
    }
    #[test] fn pulser_press_then_gap() {
        let mut p = EncoderPulser::new();
        p.push(1); p.push(-1);
        let v: Vec<u32> = (0..200).map(|_| p.tick()).collect();
        let cw = v.iter().filter(|&&x| x == 1<<ENC_CW_BIT).count();
        let ccw = v.iter().filter(|&&x| x == 1<<ENC_CCW_BIT).count();
        assert_eq!(cw, ENC_PRESS_MS as usize); assert_eq!(ccw, ENC_PRESS_MS as usize);
        let first_ccw = v.iter().position(|&x| x == 1<<ENC_CCW_BIT).unwrap();
        let last_cw = v.iter().rposition(|&x| x == 1<<ENC_CW_BIT).unwrap();
        assert!(first_ccw - last_cw > ENC_GAP_MS as usize);
    }
    #[test] fn debounce() {
        let mut d = Debouncer::default();
        for _ in 0..DEBOUNCE_MS-1 { assert!(!d.update(true)); }
        assert!(d.update(true));
        assert!(d.update(false)); // single glitch doesn't release
        assert!(d.update(true));
    }
    #[test] fn axes_formulas() {
        let mut c=[0i32;8];
        c[0]=10; c[1]=10; // pair0 closer: TZ, RY
        let a=pairs_to_axes(&c); assert_eq!(a,[0,0,20,0,-20,0]);
        let c=[5,-5,5,-5,5,-5,5,-5]; // all tangential same: pure RZ
        assert_eq!(pairs_to_axes(&c),[0,0,0,0,0,40]);
    }
    #[test] fn processor_zero_and_deadzone() {
        let cal = super::calib::CalData::defaults();
        let mut p=Processor::new();
        p.set_zero(&[2000;8]);
        let ra = p.raw_axes(&[2000;8]); assert_eq!(p.output(&ra, &cal),[0;6]);
        let mut o=[0;6];
        for _ in 0..50 { let ra = p.raw_axes(&[2300;8]); o = p.output(&ra, &cal); } // all closer: big TZ
        assert!(o[2] > 0 && o[2] <= AXIS_LIMIT as i16); assert_eq!(o[0],0); assert_eq!(o[5],0);
        for _ in 0..50 { let ra = p.raw_axes(&[1000;8]); o = p.output(&ra, &cal); }
        assert_eq!(o[2], -(AXIS_LIMIT as i16)); // clamped
    }

    // ------------------------------------------------ калибровка ---
    use super::calib::*;

    #[test] fn defaults_match_config() {
        let c = CalData::defaults();
        let mut raw = [0i32; 6]; raw[0] = 100;
        let o = c.apply(&raw);
        assert_eq!(o[0], ((100 - DEADZONE[0]) as f32 * GAIN[0]) as i16);
        assert_eq!(c.apply(&[DEADZONE[0] - 1, 0, 0, 0, 0, 0]), [0; 6]);
    }

    #[test] fn bytes_roundtrip_and_corruption() {
        let mut c = CalData::defaults();
        c.m[2][3] = -0.125; c.dz[1] = 0.02; c.gneg[5] = 1.3;
        let b = c.to_bytes();
        assert_eq!(b.len() % 2, 0);
        assert_eq!(CalData::from_bytes(&b), Some(c));
        let mut bad = b; bad[20] ^= 1;
        assert_eq!(CalData::from_bytes(&bad), None);
        assert_eq!(CalData::from_bytes(&[0xFF; CalData::BYTES]), None); // стёртая flash
        let mut nan = c; nan.dz[0] = f32::NAN;
        assert_eq!(CalData::from_bytes(&nan.to_bytes()), None);
    }

    fn matmul(a: &[[f32; 6]; 6], b: &[[f32; 6]; 6]) -> [[f32; 6]; 6] {
        let mut r = [[0.0; 6]; 6];
        for i in 0..6 { for j in 0..6 { for k in 0..6 { r[i][j] += a[i][k] * b[k][j]; } } }
        r
    }

    /// «Мышь» с перекрёстным влиянием: сырые оси = A × движение.
    fn mixing() -> [[f32; 6]; 6] {
        let mut a = [[0.0f32; 6]; 6];
        let diag = [420.0, -380.0, 900.0, 520.0, -610.0, 700.0];
        for i in 0..6 {
            a[i][i] = diag[i];
            for j in 0..6 { if i != j { a[i][j] = ((i * 7 + j * 3) % 11) as f32 * 9.0 - 45.0; } }
        }
        a
    }

    #[test] fn invert_works_and_detects_singular() {
        let a = mixing();
        let inv = invert(&a).unwrap();
        let p = matmul(&a, &inv);
        for i in 0..6 { for j in 0..6 {
            let e = if i == j { 1.0 } else { 0.0 };
            assert!((p[i][j] - e).abs() < 1e-4, "{i},{j}: {}", p[i][j]);
        } }
        let mut s = a; s[5] = s[4];
        let st: [[f32;6];6] = core::array::from_fn(|i| core::array::from_fn(|j| s[j][i]));
        assert!(invert(&st).is_none());
        assert!(invert(&[[0.0; 6]; 6]).is_none());
    }

    fn raw_of(a: &[[f32; 6]; 6], m: &[f32; 6]) -> [i32; 6] {
        core::array::from_fn(|i| (0..6).map(|j| a[i][j] * m[j]).sum::<f32>().round() as i32)
    }

    /// Прогон мастера: `order` — какие движения пользователь делает на шагах 1–6.
    fn run(a: &[[f32; 6]; 6], order: &[usize]) -> (Vec<CalEvent>, Option<CalData>) {
        let mut c = Calibrator::new();
        let mut ev = Vec::new();
        let mut feed = |c: &mut Calibrator, m: [f32; 6], ms: u32, ev: &mut Vec<CalEvent>| -> Option<CalData> {
            for _ in 0..ms / 2 {
                let e = c.update(&raw_of(a, &m), 2);
                if e != CalEvent::None { ev.push(e); }
                if let CalEvent::Finished(d) = e { return Some(d); }
            }
            None
        };
        feed(&mut c, [0.0; 6], 500, &mut ev);
        for &j in order {
            let mut m = [0.0; 6];
            for step in 1..=20 { m[j] = step as f32 / 20.0; feed(&mut c, m, 20, &mut ev); } // плавно до упора
            feed(&mut c, m, 1500, &mut ev);                                                 // держим
            feed(&mut c, [0.0; 6], 300, &mut ev);                                           // отпустили
        }
        // свободная фаза: каждую ось в + и − (в «−» только до 80 %)
        for j in 0..6 {
            let mut m = [0.0; 6];
            m[j] = 1.0; feed(&mut c, m, 800, &mut ev);
            m[j] = -0.8; feed(&mut c, m, 800, &mut ev);
        }
        let mut done = feed(&mut c, [0.0; 6], CAL_FREE_MS, &mut ev);
        if done.is_none() { done = feed(&mut c, [0.0; 6], CAL_NOISE_MS + 500, &mut ev); }
        (ev, done)
    }

    #[test] fn wizard_removes_crosstalk() {
        let a = mixing();
        let (ev, done) = run(&a, &[0, 1, 2, 3, 4, 5]);
        assert_eq!(ev.iter().filter(|e| matches!(e, CalEvent::Captured(_))).count(), 6, "{ev:?}");
        let cal = done.expect("калибровка не завершилась");
        for j in 0..6 {
            for sign in [1.0f32, -1.0] {
                let mut m = [0.0; 6]; m[j] = sign * if sign > 0.0 { 1.0 } else { 0.8 };
                let o = cal.apply(&raw_of(&a, &m));
                for k in 0..6 {
                    let want = if k == j { sign * AXIS_LIMIT as f32 } else { 0.0 };
                    let want = if INVERT[k] { -want } else { want };
                    assert!((o[k] as f32 - want).abs() <= 12.0, "движение {j}{sign:+}: ось {k} = {} (ждали {want})", o[k]);
                }
            }
        }
        // половина хода — примерно половина шкалы
        let mut m = [0.0; 6]; m[2] = 0.5;
        let o = cal.apply(&raw_of(&a, &m));
        assert!((o[2] as f32 - 175.0).abs() < 20.0, "{}", o[2]);
    }

    #[test] fn wizard_rejects_repeated_motion() {
        let a = mixing();
        let (ev, _) = run(&a, &[0, 0, 1, 2, 3, 4, 5]);
        assert!(ev.contains(&CalEvent::Rejected(1)), "{ev:?}");
        assert!(ev.contains(&CalEvent::Captured(5)), "{ev:?}");
    }

    // ------------------------------------------------ кольцо ---
    use super::led::*;

    #[test] fn led_render_all_states() {
        let ring = Ring::new();
        let states = [
            LedState::Boot,
            LedState::Normal { axes: [0; 6], calibrated: true },
            LedState::Normal { axes: [350, -200, 100, -50, 300, -350], calibrated: false },
            LedState::Cal(CalView::Step { axis: 0, hold: 0.5 }),
            LedState::Cal(CalView::Step { axis: 5, hold: 1.0 }),
            LedState::Cal(CalView::Release { rejected: true }),
            LedState::Cal(CalView::Free { progress: 0.3 }),
            LedState::Cal(CalView::Noise { progress: 1.0 }),
            LedState::Saved,
            LedState::Failed,
        ];
        for s in &states { for t in (0..5000).step_by(37) { let _ = render(&ring, s, t); } }
    }

    fn ring_level(axes: [i16; 6]) -> Vec<u32> {
        let f = render(&Ring::new(), &LedState::Normal { axes, calibrated: true }, 0);
        f.iter().map(|p| p.r as u32 + p.g as u32 + p.b as u32).collect()
    }
    /// Индекс светодиода, ближайшего к углу (градусы, 0 = вправо, 90 = от себя).
    fn led_at(deg: f32) -> usize {
        (0..LED_COUNT).min_by(|&a, &b| {
            let d = |i: usize| {
                let dir = if LED_CLOCKWISE { -1.0 } else { 1.0 };
                let ang = LED_FIRST_ANGLE_DEG + dir * 360.0 * i as f32 / LED_COUNT as f32;
                ((ang - deg).rem_euclid(360.0)).min((deg - ang).rem_euclid(360.0))
            };
            d(a).total_cmp(&d(b))
        }).unwrap()
    }

    #[test] fn led_idle_is_even_color_glow() {
        let f = render(&Ring::new(), &LedState::Normal { axes: [0; 6], calibrated: true }, 0);
        assert!(f.iter().all(|p| *p == f[0]), "в покое кольцо равномерное");
        let want = |c: u8| (c as f32 * LED_IDLE_LEVEL) as u8;
        assert_eq!((f[0].r, f[0].g, f[0].b), (want(LED_COLOR[0]), want(LED_COLOR[1]), want(LED_COLOR[2])));
        // без калибровки — «дышит»: в разные моменты разная яркость
        let a = render(&Ring::new(), &LedState::Normal { axes: [0; 6], calibrated: false }, 0);
        let b = render(&Ring::new(), &LedState::Normal { axes: [0; 6], calibrated: false }, 1500);
        assert!(b[0].r > a[0].r);
    }

    #[test] fn led_press_brighter_lift_dimmer() {
        let idle: u32 = ring_level([0; 6]).iter().sum();
        let press: u32 = ring_level([0, 0, 350, 0, 0, 0]).iter().sum();
        let lift: u32 = ring_level([0, 0, -350, 0, 0, 0]).iter().sum();
        assert!(press > idle * 2, "{press} vs {idle}");
        assert!(lift < idle / 3, "{lift} vs {idle}");
    }

    #[test] fn led_side_of_motion_is_brighter() {
        let (r, f, l, b) = (led_at(0.0), led_at(90.0), led_at(180.0), led_at(270.0));
        let tilt_right = ring_level([0, 0, 0, 0, 300, 0]);
        assert!(tilt_right[r] > tilt_right[l] + 20);
        let tilt_away = ring_level([0, 0, 0, 300, 0, 0]);
        assert!(tilt_away[f] > tilt_away[b] + 20);
        let shift_left = ring_level([-300, 0, 0, 0, 0, 0]);
        assert!(shift_left[l] > shift_left[r] + 20);
        // поворот по часовой: пятно уходит от переднего края вправо (к 0°)
        let cw = ring_level([0, 0, 0, 0, 0, 200]);
        assert!(cw[led_at(45.0)] > cw[led_at(135.0)] + 10);
        let ccw = ring_level([0, 0, 0, 0, 0, -200]);
        assert!(ccw[led_at(135.0)] > ccw[led_at(45.0)] + 10);
    }

    #[test] fn led_encode_bits() {
        let mut f = [Rgb::default(); LED_COUNT];
        f[0] = Rgb { r: 0, g: 255, b: 0 };
        let mut buf = [0u16; DMA_LEN];
        encode(&f, 10, 20, &mut buf);
        assert_eq!(buf[DMA_LEN - 1], 0);
        let g = (255u16 * LED_BRIGHTNESS as u16 / 255) as u8;
        for bit in 0..8 { assert_eq!(buf[bit], if g >> (7 - bit) & 1 != 0 { 20 } else { 10 }); }
        assert!(buf[8..24].iter().all(|&v| v == 10)); // R и B = 0
    }
}
