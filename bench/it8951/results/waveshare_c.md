# Candidate 2: Waveshare C driver — not tested

Decision by txoof on 2026-10-04: dropped before hardware testing, for these reasons.

Source checked: github.com/waveshareteam/IT8951-ePaper, `Raspberry/`, commit `86406933` (2024-01-23).

1. **It cannot run unchanged on a normal trixie setup without direct chip access.** The
   driver switches the SPI chip-select wire (GPIO 8) by hand between the parts of each
   transfer (`EPD_IT8951.c`, e.g. `EPD_IT8951_WriteCommand`). With SPI enabled the normal
   way (`dtparam=spi=on`), the Linux kernel owns GPIO 8 as `spi0 CS0`, so the driver's
   `GPIOD` and `LGPIO` builds cannot claim it. Only the default `BCM` build works, and it
   uses the `bcm2835` library to access the chip directly, which the project ruled out
   (only `gpiod`/`spidev`, so the Pi 5 can work).
2. **Making it run would need system changes or a rewrite:** a `config.txt` change that
   frees GPIO 8 (plus a reboot, and the same change in the Docker install for every
   user), the `liblgpio-dev` or `libgpiod-dev` header package, and for `GPIOD` a port of
   its helper to the libgpiod 2 interface (it uses the old libgpiod 1 interface). Rewriting
   its SPI code instead would no longer test Waveshare's driver.
3. **Its waits have no time limit.** `EPD_IT8951_ReadBusy` is `while (busy) {}` and
   `EPD_IT8951_WaitForDisplayReady` loops on the `LUTAFSR` register forever: the same
   pattern that froze v1. It would fail the fault test.
