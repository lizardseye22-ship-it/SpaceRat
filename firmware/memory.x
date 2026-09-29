/* STM32F103C8: 64 КБ flash, 20 КБ RAM.
   Последняя страница flash (1 КБ) отдана под калибровку (src/storage.rs),
   поэтому программе — 63 КБ: при переполнении линкер выдаст ошибку. */
MEMORY
{
  FLASH : ORIGIN = 0x08000000, LENGTH = 63K
  RAM   : ORIGIN = 0x20000000, LENGTH = 20K
}
