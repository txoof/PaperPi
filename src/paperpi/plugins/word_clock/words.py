"""The words of the word clock, agreed with txoof (2026-10-05, shortened 2026-10-25).

The time is rounded to the nearest 10 minutes (a "step"). A sentence is an opening, then
the minute words and the hour ("Twenty After Eight"), or for a full hour the hour and the
minute words ("Eight Sharp"). Each part is picked from its list, varied per step.
"""

#: Openings that are true at any time.
ALWAYS = (
    "It's more or less",
    "It's round about",
    "It is close to",
    "It is around",
    "It's roughly",
    "It is about",
)

#: Openings that are only true when the real time is a little before the step.
BEFORE = ("It is almost", "It's almost", "It's nearly")

#: Openings that are only true when the real time is a little after the step. None at
#: the moment (txoof, 2026-10-25): after the step the clock uses ALWAYS.
AFTER = ()

_NUMBERS = "twelve one two three four five six seven eight nine ten eleven".split()

#: Extra names for some hours (0-23), used as well as the number word.
NICKNAMES = {
    1: ("late",),
    2: ("go to bed",),
    3: ("too late",),
    12: ("noon", "lunch"),
    18: ("dinner",),
}

#: Words for each hour, 0-23.
HOURS = {hour: (_NUMBERS[hour % 12], *NICKNAMES.get(hour, ())) for hour in range(24)}

#: Words for each step. From 40 on, the sentence names the next hour ("Ten To Nine").
MINUTES = {
    0: ("o'clock", "on the dot", "sharp"),
    10: ("ten after", "ten past"),
    20: ("twenty after", "twenty past"),
    30: ("half past", "thirty after", "thirty past"),
    40: ("twenty 'til", "twenty to"),
    50: ("ten 'til", "ten to"),
}
