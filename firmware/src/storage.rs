//! Калибровка во flash: последняя страница (1 КБ) памяти программы.

use embassy_stm32::flash::{Blocking, FLASH_SIZE, Flash};

use crate::calib::CalData;

const PAGE: u32 = 1024;
/// Смещение от начала flash. Прошивка занимает ~40 КБ из 64, страница свободна.
const OFFSET: u32 = FLASH_SIZE as u32 - PAGE;

pub fn load(flash: &mut Flash<'_, Blocking>) -> Option<CalData> {
    let mut buf = [0u8; CalData::BYTES];
    flash.blocking_read(OFFSET, &mut buf).ok()?;
    CalData::from_bytes(&buf)
}

/// Стереть страницу и записать. Во время стирания процессор стоит ~20–40 мс
/// (код выполняется из той же flash) — это один раз, после калибровки.
pub fn save(flash: &mut Flash<'_, Blocking>, cal: &CalData) -> bool {
    let bytes = cal.to_bytes();
    flash.blocking_erase(OFFSET, OFFSET + PAGE).is_ok()
        && flash.blocking_write(OFFSET, &bytes).is_ok()
        && load(flash).as_ref() == Some(cal)
}
