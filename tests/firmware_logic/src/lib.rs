//! Проверка логики прошивки на ПК: cargo test (из этой папки).
//! Модули подключаются из firmware/src как есть.
#![allow(dead_code)]
#[path = "../../../firmware/src/config.rs"] pub mod config;
#[path = "../../../firmware/src/input.rs"] pub mod input;
#[path = "../../../firmware/src/sensors.rs"] pub mod sensors;
#[cfg(test)]
mod tests {
    use super::input::*;
    use super::sensors::*;
    use super::config::*;

    fn seq(enc: &mut Encoder, states: &[(bool,bool)]) -> i32 {
        states.iter().map(|&(a,b)| enc.update(a,b) as i32).sum()
    }
    #[test] fn encoder_one_detent_each_way() {
        let mut e = Encoder::new(true,true);
        // 11 -> 01 -> 00 -> 10 -> 11 : one full cycle
        let cw = seq(&mut e, &[(false,true),(false,false),(true,false),(true,true)]);
        let ccw = seq(&mut e, &[(true,false),(false,false),(false,true),(true,true)]);
        assert_eq!(cw.abs(), 1); assert_eq!(ccw, -cw);
    }
    #[test] fn encoder_bounce_ignored() {
        let mut e = Encoder::new(true,true);
        let n = seq(&mut e, &[(false,true),(true,true),(false,true),(true,true),(false,true),(true,true)]);
        assert_eq!(n, 0);
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
        let mut p=Processor::new();
        p.set_zero(&[2000;8]);
        let (o,_) = p.update(&[2000;8]); assert_eq!(o,[0;6]);
        let mut o=[0;6];
        for _ in 0..50 { o = p.update(&[2300;8]).0; } // all closer: big TZ
        assert!(o[2] > 0 && o[2] <= AXIS_LIMIT as i16); assert_eq!(o[0],0); assert_eq!(o[5],0);
        for _ in 0..50 { o = p.update(&[1000;8]).0; }
        assert_eq!(o[2], -(AXIS_LIMIT as i16)); // clamped
    }
}
