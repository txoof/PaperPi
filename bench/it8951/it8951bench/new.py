"""Candidate 3: a small new IT8951 driver using only ``spidev`` and ``gpiod``.

Written from the IT8951 datasheet for this test round. Design rules:
- every wait has a time limit and ends with ``DisplayTimeout`` instead of waiting forever
- GPIO lines and SPI are always released by ``close()``, also after an error, and
  ``close()`` can be called any number of times
- only GPIO 17 (reset) and GPIO 24 (busy, called HRDY in the datasheet) are claimed;
  chip select stays with the kernel's SPI driver

How the IT8951 talks over SPI: every transfer starts with a 2-byte "preamble" that says
what follows (command, data to write, or data to read), then 16-bit words, most
significant byte first. Before each transfer the host waits until the busy line is high
(the controller is ready). One transfer is one chip-select window, which spidev handles.
"""

import time

from PIL import Image

from .candidate import DeviceInfo, Mode

RESET_PIN = 17
BUSY_PIN = 24

# Preambles
_CMD = 0x6000
_WRITE = 0x0000
_READ = 0x1000

# Commands
SYS_RUN = 0x0001
SLEEP = 0x0003
REG_RD = 0x0010
REG_WR = 0x0011
LD_IMG_AREA = 0x0021
LD_IMG_END = 0x0022
DPY_AREA = 0x0034
VCOM = 0x0039
GET_DEV_INFO = 0x0302

# Registers
I80CPCR = 0x0004  # 1 = packed pixel mode
LISAR = 0x0208  # image buffer address (low word; high word at +2)
LUTAFSR = 0x1224  # non-zero while the controller is still redrawing

# Image loading: big-endian words, 4 bits per pixel, no rotation
_ENDIAN_BIG = 1
_PIXEL_4BPP = 2

# 2 nibbles per byte: first pixel in the high half (matches big-endian loading).
_HIGH = bytes(p & 0xF0 for p in range(256))
_LOW = bytes(p >> 4 for p in range(256))


class DisplayTimeout(TimeoutError):
    """The display did not answer within its time limit."""


def pack_4bpp(image: Image.Image) -> bytes:
    """Pack a grayscale image into 4 bits per pixel, two pixels per byte.

    Uses byte-table lookups and one big-integer OR instead of a Python loop, so a
    full 1200x825 screen packs quickly without numpy.
    """
    raw = image.tobytes()
    if len(raw) % 2:
        raw += b"\xff"
    hi = raw[0::2].translate(_HIGH)
    lo = raw[1::2].translate(_LOW)
    n = len(hi)
    return (int.from_bytes(hi, "big") | int.from_bytes(lo, "big")).to_bytes(n, "big")


class New:
    name = "new"

    def __init__(
        self,
        spi_device: tuple[int, int] = (0, 0),
        cmd_hz: int = 12_000_000,
        data_hz: int = 24_000_000,
        ready_timeout: float = 2.0,
        refresh_timeout: float = 15.0,
        chip: str = "/dev/gpiochip0",
    ) -> None:
        self.spi_device = spi_device
        self.cmd_hz = cmd_hz
        self.data_hz = data_hz
        self.ready_timeout = ready_timeout
        self.refresh_timeout = refresh_timeout
        self.chip = chip
        self.spi = None
        self.lines = None
        self.block = 4096
        self.info: DeviceInfo | None = None
        self._img_addr = 0

    # ------------------------------------------------------------ open / close

    def open(self, vcom: float) -> DeviceInfo:
        if not -5.0 < vcom < 0.0:
            raise ValueError(f"VCOM must be between -5 and 0, got {vcom}")
        import gpiod
        import spidev
        from gpiod.line import Direction, Value

        self.close()
        try:
            self.lines = gpiod.request_lines(
                self.chip,
                consumer="it8951-new",
                config={
                    RESET_PIN: gpiod.LineSettings(
                        direction=Direction.OUTPUT, output_value=Value.ACTIVE
                    ),
                    BUSY_PIN: gpiod.LineSettings(direction=Direction.INPUT),
                },
            )
            self.spi = spidev.SpiDev()
            self.spi.open(*self.spi_device)
            self.spi.mode = 0
            self.spi.max_speed_hz = self.cmd_hz
            try:
                with open("/sys/module/spidev/parameters/bufsiz") as f:
                    self.block = min(int(f.read()), 65536)
            except (OSError, ValueError):
                self.block = 4096
            self._reset()
            self.info = self._read_info()
            self._write_reg(I80CPCR, 1)
            self._command(VCOM, 1, round(-vcom * 1000))
            self._command(VCOM, 0)
            vcom_read = -self._read_words(1)[0] / 1000
            self.info = DeviceInfo(
                self.info.width, self.info.height, self.info.firmware, self.info.lut, vcom_read
            )
            return self.info
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        spi, self.spi = self.spi, None
        lines, self.lines = self.lines, None
        try:
            if spi is not None:
                spi.close()
        finally:
            if lines is not None:
                lines.release()

    def __enter__(self) -> "New":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------ public

    def write(self, image: Image.Image, mode: Mode, xy: tuple[int, int] = (0, 0)) -> None:
        if self.spi is None or self.info is None:
            raise RuntimeError("not open")
        if image.mode != "L":
            raise ValueError("image must be grayscale (mode L)")
        x, y = xy
        w, h = image.size
        if x % 4 or w % 4:
            raise ValueError("x and width must be multiples of 4 (4 pixels per 16-bit word)")
        if x < 0 or y < 0 or x + w > self.info.width or y + h > self.info.height:
            raise ValueError(f"area {xy} {image.size} is outside the screen")

        self._command(SYS_RUN)
        self._wait_refresh_done()
        self._write_reg(LISAR + 2, self._img_addr >> 16)
        self._write_reg(LISAR, self._img_addr & 0xFFFF)
        arg = (_ENDIAN_BIG << 8) | (_PIXEL_4BPP << 4)
        self._command(LD_IMG_AREA, arg, x, y, w, h)
        self._write_pixels(pack_4bpp(image))
        self._command(LD_IMG_END)
        self._command(DPY_AREA, x, y, w, h, int(mode))
        self._wait_refresh_done()

    def sleep(self) -> None:
        if self.spi is not None:
            self._command(SLEEP)

    # ------------------------------------------------------------ low level

    def _reset(self) -> None:
        from gpiod.line import Value

        self.lines.set_value(RESET_PIN, Value.INACTIVE)
        time.sleep(0.1)
        self.lines.set_value(RESET_PIN, Value.ACTIVE)
        self._wait_ready(timeout=5.0)

    def _wait_ready(self, timeout: float | None = None) -> None:
        """Wait until the busy line is high (controller ready for the next transfer)."""
        from gpiod.line import Value

        deadline = time.monotonic() + (timeout or self.ready_timeout)
        while self.lines.get_value(BUSY_PIN) != Value.ACTIVE:
            if time.monotonic() > deadline:
                raise DisplayTimeout("display not ready (busy line stayed low)")
            time.sleep(0.0002)

    def _wait_refresh_done(self) -> None:
        """Wait until the controller has finished drawing (LUTAFSR register is 0)."""
        deadline = time.monotonic() + self.refresh_timeout
        while self._read_reg(LUTAFSR):
            if time.monotonic() > deadline:
                raise DisplayTimeout("display still redrawing after time limit")
            time.sleep(0.005)

    def _transfer(self, data: list[int] | bytes, hz: int) -> list[int]:
        self._wait_ready()
        return self.spi.xfer3(list(data) if isinstance(data, bytes) else data, hz)

    @staticmethod
    def _words(preamble: int, words: tuple[int, ...] | list[int]) -> list[int]:
        out = [preamble >> 8, preamble & 0xFF]
        for word in words:
            out += [(word >> 8) & 0xFF, word & 0xFF]
        return out

    def _command(self, cmd: int, *args: int) -> None:
        self._transfer(self._words(_CMD, [cmd]), self.cmd_hz)
        for arg in args:
            self._transfer(self._words(_WRITE, [arg]), self.cmd_hz)

    def _read_words(self, count: int) -> list[int]:
        # preamble (2 bytes) + 2 dummy bytes, then the data
        rx = self._transfer([_READ >> 8, _READ & 0xFF] + [0] * (2 + 2 * count), self.cmd_hz)
        data = rx[4:]
        return [(data[2 * i] << 8) | data[2 * i + 1] for i in range(count)]

    def _read_reg(self, reg: int) -> int:
        self._command(REG_RD, reg)
        return self._read_words(1)[0]

    def _write_reg(self, reg: int, value: int) -> None:
        self._command(REG_WR, reg)
        self._transfer(self._words(_WRITE, [value]), self.cmd_hz)

    def _write_pixels(self, packed: bytes) -> None:
        step = (self.block - 2) // 2 * 2  # whole 16-bit words per transfer
        self.spi.max_speed_hz = self.data_hz
        try:
            for start in range(0, len(packed), step):
                self._wait_ready()
                self.spi.writebytes2(b"\x00\x00" + packed[start : start + step])
        finally:
            self.spi.max_speed_hz = self.cmd_hz

    def _read_info(self) -> DeviceInfo:
        self._command(GET_DEV_INFO)
        w = self._read_words(20)
        if not any(w):
            raise RuntimeError("no answer from the display (device info is all zeros)")
        self._img_addr = (w[3] << 16) | w[2]

        def text(words: list[int]) -> str:
            raw = b"".join(word.to_bytes(2, "big") for word in words)
            return raw.split(b"\x00")[0].decode("ascii", "replace")

        return DeviceInfo(width=w[0], height=w[1], firmware=text(w[4:12]), lut=text(w[12:20]))


def make() -> New:
    return New()
