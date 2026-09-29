//! SpaceRat — прошивка Blue Pill (STM32F103C8) на Embassy.
//!
//! Устройство представляется ПК как 3Dconnexion SpaceMouse Pro Wireless (cabled)
//! и работает с драйвером 3DxWare под Windows.
//! Железо: docs/hardware, протокол: docs/firmware/usb-hid-protocol.md.

#![no_std]
#![no_main]

mod config;
mod hid;
mod input;
mod sensors;

use core::cell::Cell;

use defmt::{debug, info, warn};
use embassy_executor::Spawner;
use embassy_futures::join::join5;
use embassy_stm32::adc::{Adc, AdcChannel, AnyAdcChannel, SampleTime};
use embassy_stm32::gpio::{Input, Level, Output, Pull, Speed};
use embassy_stm32::peripherals::ADC1;
use embassy_stm32::time::Hertz;
use embassy_stm32::usb::Driver;
use embassy_stm32::{Config, adc, bind_interrupts, peripherals, usb};
use embassy_time::{Duration, Ticker, Timer};
use embassy_usb::Builder;
use embassy_usb::class::hid::{HidBootProtocol, HidReaderWriter, HidSubclass, State};
use {defmt_rtt as _, panic_probe as _};

use crate::config::*;
use crate::input::{Debouncer, Encoder, EncoderPulser};
use crate::sensors::{Processor, SENSORS};

bind_interrupts!(struct Irqs {
    USB_LP_CAN1_RX0 => usb::InterruptHandler<peripherals::USB>;
    ADC1_2 => adc::InterruptHandler<ADC1>;
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
        let mut n: u32 = 0;
        loop {
            ticker.next().await;
            let raw = read_all(&mut adc, &mut ch).await;
            let (out, raw_axes) = proc.update(&raw);
            axes.set(out);

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
        let enc_a = Input::new(p.PB6, Pull::Up);
        let enc_b = Input::new(p.PB7, Pull::Up);

        let mut debounce = [Debouncer::default(); 6];
        let mut encoder = Encoder::new(enc_a.is_high(), enc_b.is_high());
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
            pulser.push(encoder.update(enc_a.is_high(), enc_b.is_high()));
            bits |= pulser.tick();
            keys.set(bits);
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

    let out_fut = reader.run(true, &mut out_handler);

    join5(usb.run(), out_fut, sensor_fut, input_fut, report_fut).await;
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
