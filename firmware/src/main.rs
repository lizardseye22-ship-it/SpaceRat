//! SpaceRat — прошивка Blue Pill (STM32F103C8) на Embassy.
//!
//! Устройство представляется ПК как 3Dconnexion SpaceMouse Pro Wireless (cabled)
//! и работает с драйвером 3DxWare под Windows.
//! Железо: docs/hardware, протокол: docs/firmware/usb-hid-protocol.md.

#![no_std]
#![no_main]

mod calib;
mod config;
mod hid;
mod input;
mod led;
mod sensors;
mod storage;

use core::cell::Cell;

use defmt::{debug, info, warn};
use embassy_executor::Spawner;
use embassy_futures::join::{join, join5};
use embassy_stm32::adc::{Adc, AdcChannel, AnyAdcChannel, SampleTime};
use embassy_stm32::flash::Flash;
use embassy_stm32::gpio::{AfioRemap, Input, Level, Output, OutputType, Pull, Speed};
use embassy_stm32::pac::timer::vals::{Ckd, FilterValue};
use embassy_stm32::peripherals::ADC1;
use embassy_stm32::time::khz;
use embassy_stm32::timer::Channel;
use embassy_stm32::timer::low_level::CountingMode;
use embassy_stm32::timer::qei::{Qei, QeiMode};
use embassy_stm32::timer::simple_pwm::{PwmPin, SimplePwm};
use embassy_stm32::time::Hertz;
use embassy_stm32::usb::Driver;
use embassy_stm32::{Config, adc, bind_interrupts, dma, peripherals, usb};
use embassy_time::{Duration, Instant, Ticker, Timer};
use embassy_usb::Builder;
use embassy_usb::class::hid::{HidBootProtocol, HidReaderWriter, HidSubclass, State};
use {defmt_rtt as _, panic_probe as _};

use crate::calib::{CalData, CalEvent, Calibrator};
use crate::config::*;
use crate::input::{Debouncer, EncoderCounter, EncoderPulser};
use crate::led::LedState;
use crate::sensors::{Processor, SENSORS};

bind_interrupts!(struct Irqs {
    USB_LP_CAN1_RX0 => usb::InterruptHandler<peripherals::USB>;
    ADC1_2 => adc::InterruptHandler<ADC1>;
    DMA1_CHANNEL5 => dma::InterruptHandler<peripherals::DMA1_CH5>;
});

#[embassy_executor::main]
async fn main(_spawner: Spawner) {
    // 8 МГц кварц -> PLL ×9 = 72 МГц, USB = 72 / 1.5 = 48 МГц.
    let mut config = Config::default();
    {
        use embassy_stm32::rcc::*;
        config.rcc.hse = Some(Hse { freq: Hertz(8_000_000), mode: HseMode::Oscillator });
        config.rcc.pll = Some(Pll { src: PllSource::HSE, prediv: PllPreDiv::DIV1, mul: PllMul::MUL9 });
        config.rcc.sys = Sysclk::PLL1_P;
        config.rcc.ahb_pre = AHBPrescaler::DIV1;
        config.rcc.apb1_pre = APBPrescaler::DIV2;
        config.rcc.apb2_pre = APBPrescaler::DIV1;
    }
    let mut p = embassy_stm32::init(config);
    info!("SpaceRat start");

    // На Blue Pill D+ подтянут резистором к 3.3 В постоянно. Прижимаем D+ к земле,
    // чтобы ПК увидел переподключение после перезагрузки/прошивки.
    {
        let _dp = Output::new(p.PA12.reborrow(), Level::Low, Speed::Low);
        Timer::after_millis(10).await;
    }

    // ------------------------------------------------------------- USB ---
    let driver = Driver::new(p.USB, Irqs, p.PA12, p.PA11);

    let mut usb_config = embassy_usb::Config::new(USB_VID, USB_PID);
    usb_config.manufacturer = Some(USB_MANUFACTURER);
    usb_config.product = Some(USB_PRODUCT);
    usb_config.serial_number = None;
    usb_config.max_power = 100;
    usb_config.max_packet_size_0 = 64;
    usb_config.device_class = 0;
    usb_config.device_sub_class = 0;
    usb_config.device_protocol = 0;
    usb_config.composite_with_iads = false;

    let mut config_descriptor = [0; 256];
    let mut bos_descriptor = [0; 256];
    let mut control_buf = [0; 64];
    let mut control_handler = hid::Handler;
    let mut out_handler = hid::Handler;
    let mut hid_state = State::new();

    let mut builder = Builder::new(
        driver,
        usb_config,
        &mut config_descriptor,
        &mut bos_descriptor,
        &mut [],
        &mut control_buf,
    );

    let hid_config = embassy_usb::class::hid::Config {
        report_descriptor: &hid::REPORT_DESCRIPTOR,
        request_handler: Some(&mut control_handler),
        poll_ms: REPORT_PERIOD_MS as u8,
        max_packet_size: 16,
        hid_subclass: HidSubclass::No,
        hid_boot_protocol: HidBootProtocol::None,
    };
    let hid = HidReaderWriter::<_, 8, 16>::new(&mut builder, &mut hid_state, hid_config);
    let (reader, mut writer) = hid.split();
    let mut usb = builder.build();

    // Общее состояние между задачами (один поток исполнения, блокировки не нужны).
    let axes: Cell<[i16; 6]> = Cell::new([0; 6]);
    let keys: Cell<u32> = Cell::new(0);
    let led_state: Cell<LedState> = Cell::new(LedState::Boot);
    // SW1 + SW5 зажаты при включении -> режим калибровки (ставит input_fut,
    // снимает sensor_fut по окончании). Пока он активен, кнопки в ПК не уходят.
    let cal_active: Cell<bool> = Cell::new(false);

    // --------------------------------------------------------- Датчики ---
    let sensor_fut = async {
        let mut adc = Adc::new(p.ADC1);
        let mut ch: [AnyAdcChannel<'_, ADC1>; SENSORS] = [
            p.PA0.degrade_adc(),
            p.PA1.degrade_adc(),
            p.PA2.degrade_adc(),
            p.PA3.degrade_adc(),
            p.PA4.degrade_adc(),
            p.PA5.degrade_adc(),
            p.PA6.degrade_adc(),
            p.PA7.degrade_adc(),
        ];
        let mut proc = Processor::new();

        let mut flash = Flash::new_blocking(p.FLASH);
        let stored = storage::load(&mut flash);
        let mut calibrated = stored.is_some();
        let mut cal = stored.unwrap_or_else(CalData::defaults);
        info!("калибровка из flash: {}", if calibrated { "есть" } else { "нет, значения из config.rs" });

        // Калибровка нуля: ручку в это время не трогать.
        Timer::after_millis(CALIBRATION_SETTLE_MS).await;
        let mut sum = [0u32; SENSORS];
        for _ in 0..CALIBRATION_CYCLES {
            let raw = read_all(&mut adc, &mut ch).await;
            for i in 0..SENSORS {
                sum[i] += raw[i] as u32;
            }
            Timer::after_millis(SENSOR_PERIOD_MS).await;
        }
        let zero = sum.map(|s| s / CALIBRATION_CYCLES);
        proc.set_zero(&zero);
        info!("zero (ADC): {}", zero);
        for (i, z) in zero.iter().enumerate() {
            if *z < ADC_RAIL_MARGIN as u32 || *z > (4095 - ADC_RAIL_MARGIN) as u32 {
                warn!("U{}: {} близко к рельсу — магнит слишком близко или обрыв", i + 1, z);
            }
        }

        let mut ticker = Ticker::every(Duration::from_millis(SENSOR_PERIOD_MS));

        // ---------------------------------------------- режим калибровки ---
        if cal_active.get() {
            info!("режим калибровки");
            let mut wizard = Calibrator::new();
            let result = loop {
                ticker.next().await;
                let raw = read_all(&mut adc, &mut ch).await;
                let ra = proc.raw_axes(&raw);
                match wizard.update(&ra, SENSOR_PERIOD_MS as u32) {
                    CalEvent::Captured(n) => info!("шаг {} записан: {}", n + 1, ra),
                    CalEvent::Rejected(n) => warn!("шаг {}: эта ось уже записана, повторите движение", n + 1),
                    CalEvent::Finished(c) => break Some(c),
                    CalEvent::Failed => break None,
                    CalEvent::None => {}
                }
                led_state.set(LedState::Cal(wizard.view()));
            };
            match result {
                Some(c) => {
                    led_state.set(LedState::Saved);
                    Timer::after_millis(50).await; // дать кольцу показать статус до стирания flash
                    if storage::save(&mut flash, &c) {
                        info!("калибровка сохранена");
                        cal = c;
                        calibrated = true;
                    } else {
                        warn!("не удалось записать flash");
                        led_state.set(LedState::Failed);
                    }
                }
                None => {
                    warn!("калибровка не удалась: движения не различаются, повторите");
                    led_state.set(LedState::Failed);
                }
            }
            Timer::after_millis(2000).await;
            cal_active.set(false);
            ticker = Ticker::every(Duration::from_millis(SENSOR_PERIOD_MS));
        }

        // ------------------------------------------------ обычная работа ---
        let mut n: u32 = 0;
        loop {
            ticker.next().await;
            let raw = read_all(&mut adc, &mut ch).await;
            let raw_axes = proc.raw_axes(&raw);
            let out = proc.output(&raw_axes, &cal);
            axes.set(out);
            led_state.set(LedState::Normal { axes: out, calibrated });

            // Раз в секунду — значения для настройки (DEFMT_LOG=debug).
            n = n.wrapping_add(1);
            if n % (1000 / SENSOR_PERIOD_MS as u32) == 0 {
                debug!("raw {} axes_raw {} hid {}", raw, raw_axes, out);
                if raw.iter().any(|v| *v < ADC_RAIL_MARGIN || *v > 4095 - ADC_RAIL_MARGIN) {
                    warn!("насыщение датчика: {}", raw);
                }
            }
        }
    };

    // ------------------------------------------------ Кнопки, энкодер ---
    let input_fut = async {
        let buttons = [
            Input::new(p.PB8, Pull::Up),
            Input::new(p.PB12, Pull::Up),
            Input::new(p.PB13, Pull::Up),
            Input::new(p.PB14, Pull::Up),
            Input::new(p.PB15, Pull::Up),
        ];
        let enc_button = Input::new(p.PB5, Pull::Up);

        // Энкодер: TIM4 в режиме энкодера, PB6 = CH1 (A), PB7 = CH2 (B), подтяжки внутренние.
        // Системное время Embassy перенесено на TIM3 (Cargo.toml: time-driver-tim3).
        let mut qei_config = embassy_stm32::timer::qei::Config::default();
        qei_config.ch1_pull = Pull::Up;
        qei_config.ch2_pull = Pull::Up;
        qei_config.mode = QeiMode::Mode3;
        let qei = Qei::new(p.TIM4, p.PB6, p.PB7, qei_config);
        // Максимальный цифровой фильтр входов: fDTS = 72 МГц / 4, выборка fDTS / 32, 8 подряд.
        // Отсекает короткие иголки; дребезг контактов гасится самим счётом квадратуры.
        {
            let tim = embassy_stm32::pac::TIM4;
            tim.cr1().modify(|w| w.set_cen(false));
            tim.cr1().modify(|w| w.set_ckd(Ckd::DIV4));
            tim.ccmr_input(0).modify(|w| {
                w.set_icf(0, FilterValue::FDTS_DIV32_N8);
                w.set_icf(1, FilterValue::FDTS_DIV32_N8);
            });
            tim.cr1().modify(|w| w.set_cen(true));
        }

        // SW1 + SW5 при включении — режим калибровки.
        Timer::after_millis(20).await;
        if buttons[0].is_low() && buttons[4].is_low() {
            cal_active.set(true);
        }

        let mut debounce = [Debouncer::default(); 6];
        let mut encoder = EncoderCounter::new(qei.count());
        let mut pulser = EncoderPulser::new();

        let mut ticker = Ticker::every(Duration::from_millis(INPUT_PERIOD_MS));
        loop {
            ticker.next().await;
            let mut bits = 0u32;
            for (i, b) in buttons.iter().enumerate() {
                if debounce[i].update(b.is_low()) {
                    bits |= 1 << BUTTON_BITS[i];
                }
            }
            if debounce[5].update(enc_button.is_low()) {
                bits |= 1 << ENC_BUTTON_BIT;
            }
            pulser.push(encoder.update(qei.count()));
            bits |= pulser.tick();
            keys.set(if cal_active.get() { 0 } else { bits });
        }
    };

    // ------------------------------------------------------ HID-отчёты ---
    // Расписание как у оригинала: один отчёт за слот REPORT_PERIOD_MS.
    // Оси — пока есть движение и ещё TRAILING_ZERO_REPORTS нулевых после;
    // кнопки — только при изменении, чередуясь с осями.
    let report_fut = async {
        let mut ticker = Ticker::every(Duration::from_millis(REPORT_PERIOD_MS));
        let mut sent_keys: u32 = 0;
        let mut zeros: u8 = TRAILING_ZERO_REPORTS;
        let mut last_was_keys = false;
        loop {
            writer.ready().await;
            ticker.next().await;

            let k = keys.get();
            let a = axes.get();
            let moving = a.iter().any(|v| *v != 0);
            let axes_due = moving || zeros < TRAILING_ZERO_REPORTS;
            let keys_due = k != sent_keys;

            let result = if keys_due && !(axes_due && last_was_keys) {
                last_was_keys = true;
                sent_keys = k;
                writer.write(&hid::buttons_report(k)).await
            } else if axes_due {
                last_was_keys = false;
                zeros = if moving { 0 } else { zeros + 1 };
                writer.write(&hid::axes_report(&a)).await
            } else {
                continue;
            };

            if let Err(e) = result {
                warn!("HID write: {:?}", e);
                // После переподключения отправить состояние заново.
                sent_keys = !k;
                zeros = 0;
            }
        }
    };

    // ------------------------------------------------------ Кольцо WS2812 ---
    // PA8 = TIM1_CH1, открытый сток + подтяжка 1 кОм к 5 В. Кадр уходит через
    // DMA по событию обновления таймера (TIM1_UP -> DMA1 канал 5).
    let led_fut = async {
        let mut pwm = SimplePwm::new(
            p.TIM1,
            Some(PwmPin::<_, _, AfioRemap<0>>::new(p.PA8, OutputType::OpenDrain)),
            None,
            None,
            None,
            khz(800),
            CountingMode::EdgeAlignedUp,
        );
        let max = pwm.max_duty_cycle() as u16;
        let n0 = max * 8 / 25; // «0»: ~0.4 мкс высокого уровня из 1.25
        let n1 = n0 * 2; //       «1»: ~0.8 мкс
        pwm.channel(Channel::Ch1).set_duty_cycle(0);
        let mut dma_ch = p.DMA1_CH5;

        let ring = led::Ring::new();
        let mut buf = [0u16; led::DMA_LEN];
        let mut ticker = Ticker::every(Duration::from_millis(LED_FRAME_MS));
        let mut prev = led_state.get();
        let mut since = Instant::now();
        loop {
            ticker.next().await;
            let state = led_state.get();
            if core::mem::discriminant(&state) != core::mem::discriminant(&prev) {
                since = Instant::now();
            }
            prev = state;
            let frame = led::render(&ring, &state, since.elapsed().as_millis() as u32);
            led::encode(&frame, n0, n1, &mut buf);
            pwm.waveform_up(dma_ch.reborrow(), Irqs, Channel::Ch1, &buf).await;
        }
    };

    let out_fut = reader.run(true, &mut out_handler);

    join(join5(usb.run(), out_fut, sensor_fut, input_fut, report_fut), led_fut).await;
}

/// Прочитать все 8 датчиков с усреднением OVERSAMPLE выборок.
async fn read_all(adc: &mut Adc<'_, ADC1>, ch: &mut [AnyAdcChannel<'_, ADC1>; SENSORS]) -> [u16; SENSORS] {
    let mut out = [0u16; SENSORS];
    for i in 0..SENSORS {
        let mut s: u32 = 0;
        for _ in 0..OVERSAMPLE {
            s += adc.read(&mut ch[i], SampleTime::CYCLES71_5).await as u32;
        }
        out[i] = (s / OVERSAMPLE) as u16;
    }
    out
}
