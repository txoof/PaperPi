# Viewing session rubric

One viewing session per candidate, about 5 minutes. Run:

```bash
uv run python -m it8951bench <candidate> view --vcom <value printed on the ribbon cable>
```

Each image has its step label in the top-left corner. Images stay 20 seconds.
Answer in the terminal; Claude records the answers in `results/<candidate>-rubric.md`.

| # | Look at | Question | Answer |
|---|---|---|---|
| 1 | Step 1: gray steps (GC16) | How many separate bars can you tell apart? | 0–16 |
| 2 | Step 2: fine text (GC16) | Smallest text size that is easy to read? | 40, 32, 24, 18, 14, 11 or 9 px |
| 3 | Step 2: fine text (GC16) | How sharp are the letters and the thin lines? | 1 (blurry or broken) – 5 (crisp) |
| 4 | Step 3: gradient (GC16) | How smooth is the gradient? | 1 (strong bands) – 5 (smooth) |
| 5 | Step 4: clock, 10 fast DU updates | After the 10 updates, how much ghosting (faint old digits) is left? | 1 (heavy) – 5 (none) |
| 6 | Step 5: clock, 10 fast A2 updates | Same question for A2. | 1 (heavy) – 5 (none) |
| 7 | Steps 4–6 | Did the fast updates flash the screen? | none / small area / whole screen |
| 8 | Step 7: gray steps again (GC16) | Any leftovers from earlier images? | 1 (clearly visible) – 5 (none) |
| 9 | Whole session | Anything odd: lines, noise, wrong area, parts not updating, unusual sounds? | free text |
