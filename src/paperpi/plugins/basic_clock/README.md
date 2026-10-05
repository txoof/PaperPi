# basic_clock

Shows the time in large digits, and optionally the date below it. It needs no network.

## Layouts

| Layout | Shows |
|---|---|
| `time` (default) | the time only, as large as fits |
| `time_date` | the time, with the date below it ("Monday 5 October") |

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `hours` | `24` | `24` shows 15:45, `12` shows 3:45 PM |

It suggests a refresh every 60 seconds, starting just after the minute changes.

```toml
[[plugin]]
name = "Clock"
type = "basic_clock"
layout = "time_date"
hours = 12
```

Try it without a screen: `paperpi render basic_clock --layout time_date --set hours=12`.

Sample images (sample time: 10:42 on Monday 5 October 2026) are in
[`tests/images/`](../../../../tests/images/), named `basic_clock-<layout>-<screen>.png`.
