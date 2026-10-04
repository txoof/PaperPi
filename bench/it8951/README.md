# IT8951 driver test round (M2)

Test programs that measure three IT8951 driver candidates on the 9.7" display in the
same way. **Not part of PaperPi.** The chosen driver is rewritten properly in epdlib
in M3; this folder stays as a record of how the choice was made.

Issues: #197 (these tools), #198–#200 (the candidates), #201 (long run, report, decision).

## Safety
- The fault test is **software only**: it holds the reset line (GPIO 17) low with
  `pinctrl` while a write runs. **Never unplug a cable while the Pi is powered**; it can
  destroy the driver board and damage the Pi.
- The screen sleeps after every write.
- `--vcom` has no default. Use the value printed on the panel's ribbon cable.

## Setup
The venv uses the GPIO packages that come with Raspberry Pi OS (`python3-libgpiod`,
`python3-spidev`, `python3-rpi-lgpio`), because some of them do not build from PyPI on
Python 3.13 (for example `lgpio` needs `swig`).
```bash
cd bench/it8951
uv venv --system-site-packages
uv sync
uv run pytest            # unit tests of the tools, no hardware needed

# candidate 1 (GregDMeyer, upstream commit 9f136139, checked out at ~/src/IT8951)
uv pip install cython setuptools
uv pip install --no-build-isolation ~/src/IT8951
```
Use `uv run` (not `uv sync`) afterwards: `uv sync` removes packages that are not in
the lock file, such as the candidate drivers.

## Running
```bash
uv run python -m it8951bench <candidate> basic --vcom <v>   # timings + pin check
uv run python -m it8951bench <candidate> fault --vcom <v>   # stops with an error, or hangs?
uv run python -m it8951bench <candidate> view  --vcom <v>   # viewing session, see rubric.md
```
Results are saved as CSV in `results/`.

## What is measured
| Test | How |
|---|---|
| Full refresh | Full-screen GC16 writes of gray steps, fine text and a gradient |
| Partial update | A 480×160 clock area written in GC16, DU and A2 |
| Fast update | Full-screen black-and-white text in DU and A2 |
| Pin check | `gpioinfo` before, during and after: the candidate may take only GPIO 17 and 24, and must release them on close. The HiFiBerry uses 18–21 and 2–3. |
| Recovery | Reset held low during a write: does the write stop with an error within its time limit? Does the next write work, in the same process and in a new one? A candidate that does not return within 60 s counts as hung and is killed. |
| Quality | txoof's viewing session, scored with `rubric.md` |

Every scenario runs in a child process that is killed after a time limit, so a hanging
candidate cannot stop the test round.

## Candidates
Each candidate is a module in `it8951bench/` with a `make()` function that returns an
object following `candidate.py`. `fake.py` is a stand-in without hardware, for the tests.
