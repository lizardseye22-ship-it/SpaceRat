//! HID-дескриптор и отчёты SpaceMouse Pro Wireless.
//! Формат описан в docs/firmware/usb-hid-protocol.md §3–4.

use embassy_usb::class::hid::{ReportId, RequestHandler};
use embassy_usb::control::OutResponse;

pub const REPORT_ID_AXES: u8 = 1;
pub const REPORT_ID_BUTTONS: u8 = 3;
pub const REPORT_ID_LED: u8 = 4;

pub const AXES_REPORT_LEN: usize = 13;
pub const BUTTONS_REPORT_LEN: usize = 5;

#[rustfmt::skip]
pub const REPORT_DESCRIPTOR: [u8; 92] = [
    0x05, 0x01,        // Usage Page (Generic Desktop)
    0x09, 0x08,        // Usage (Multi-axis Controller)
    0xA1, 0x01,        // Collection (Application)
    // Report 1: 6 осей
    0xA1, 0x00,        //   Collection (Physical)
    0x85, 0x01,        //     Report ID (1)
    0x16, 0xA2, 0xFE,  //     Logical Minimum (-350)
    0x26, 0x5E, 0x01,  //     Logical Maximum (350)
    0x36, 0x88, 0xFA,  //     Physical Minimum (-1400)
    0x46, 0x78, 0x05,  //     Physical Maximum (1400)
    0x55, 0x0C,        //     Unit Exponent (-4)
    0x65, 0x11,        //     Unit (SI Linear, cm)
    0x09, 0x30,        //     Usage (X)
    0x09, 0x31,        //     Usage (Y)
    0x09, 0x32,        //     Usage (Z)
    0x09, 0x33,        //     Usage (Rx)
    0x09, 0x34,        //     Usage (Ry)
    0x09, 0x35,        //     Usage (Rz)
    0x75, 0x10,        //     Report Size (16)
    0x95, 0x06,        //     Report Count (6)
    0x81, 0x02,        //     Input (Data,Var,Abs)
    0xC0,              //   End Collection
    // Report 3: 32 кнопки
    0xA1, 0x00,        //   Collection (Physical)
    0x85, 0x03,        //     Report ID (3)
    0x15, 0x00,        //     Logical Minimum (0)
    0x25, 0x01,        //     Logical Maximum (1)
    0x75, 0x01,        //     Report Size (1)
    0x95, 0x20,        //     Report Count (32)
    0x05, 0x09,        //     Usage Page (Button)
    0x19, 0x01,        //     Usage Minimum (1)
    0x29, 0x20,        //     Usage Maximum (32)
    0x81, 0x02,        //     Input (Data,Var,Abs)
    0xC0,              //   End Collection
    // Report 4: светодиод (ПК -> устройство)
    0xA1, 0x02,        //   Collection (Logical)
    0x85, 0x04,        //     Report ID (4)
    0x05, 0x08,        //     Usage Page (LEDs)
    0x09, 0x4B,        //     Usage (Generic Indicator)
    0x15, 0x00,        //     Logical Minimum (0)
    0x25, 0x01,        //     Logical Maximum (1)
    0x95, 0x01,        //     Report Count (1)
    0x75, 0x01,        //     Report Size (1)
    0x91, 0x02,        //     Output (Data,Var,Abs)
    0x95, 0x01,        //     Report Count (1)
    0x75, 0x07,        //     Report Size (7)
    0x91, 0x03,        //     Output (Const)
    0xC0,              //   End Collection
    0xC0,              // End Collection
];

/// Report 1: `01` и шесть int16 little-endian (X, Y, Z, Rx, Ry, Rz).
pub fn axes_report(axes: &[i16; 6]) -> [u8; AXES_REPORT_LEN] {
    let mut r = [0u8; AXES_REPORT_LEN];
    r[0] = REPORT_ID_AXES;
    for (i, v) in axes.iter().enumerate() {
        r[1 + 2 * i..3 + 2 * i].copy_from_slice(&v.to_le_bytes());
    }
    r
}

/// Report 3: `03` и 32 бита кнопок little-endian.
pub fn buttons_report(bits: u32) -> [u8; BUTTONS_REPORT_LEN] {
    let mut r = [0u8; BUTTONS_REPORT_LEN];
    r[0] = REPORT_ID_BUTTONS;
    r[1..].copy_from_slice(&bits.to_le_bytes());
    r
}

/// Отвечает на запросы класса HID от драйвера.
/// SET_REPORT (включая светодиод, Report 4) и SET_IDLE принимаем и игнорируем:
/// светодиода нет, а отказ драйвер может счесть ошибкой устройства.
pub struct Handler;

impl RequestHandler for Handler {
    fn set_report(&mut self, id: ReportId, data: &[u8]) -> OutResponse {
        if id == ReportId::Out(REPORT_ID_LED) {
            defmt::debug!("LED report: {=[u8]:x}", data);
        } else {
            defmt::debug!("SET_REPORT {:?}: {=[u8]:x}", id, data);
        }
        OutResponse::Accepted
    }

    fn set_idle_ms(&mut self, id: Option<ReportId>, duration_ms: u32) {
        defmt::debug!("SET_IDLE {:?} {} ms", id, duration_ms);
    }
}
