# Candidate 1 (greg): viewing rubric answers

txoof, 2026-10-04, VCOM -1.90.

| # | Question | Answer |
|---|---|---|
| 1 | Gray steps: bars told apart | 16 |
| 2 | Fine text: smallest easy to read | 9 px |
| 3 | Fine text: sharpness (1-5) | 4 ("looks great"; first said 3) |
| 4 | Gradient smoothness | "The bands are clear and well defined. Rings are clear" (16 visible steps, as expected without dithering) |
| 5 | Clock DU, 10 fast updates: ghosting (1-5) | 4 ("minimal ghosting") |
| 6 | Clock A2, 10 fast updates: ghosting | worse than DU: "in the updated portion, there were vertical lines, leftover pixels, negative shadows" |
| 7 | Full-screen text DU over the A2 clock page: leftovers | "the seconds show up ghosted in the lower portion" |
| 8 | Gray steps again, full GC16: leftovers | "still a little ghosting. The seconds still appear as ghosts. The lines and some text appears as well" -> one GC16 does not fully clean after A2/DU; check INIT as the cleaning refresh |
