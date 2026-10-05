"""The words of the word clock, agreed with txoof (2026-10-05).

The time is rounded to the nearest 10 minutes (a "step"). A sentence is an opening, then
the minute words and the hour ("Twenty After Eight"), or for a full hour the hour and the
minute words ("Eight Sharp"). Each part is picked from its list, varied per step.
"""

#: Openings that are true at any time.
ALWAYS = (
    "It is about",
    "It is around",
    "It is close to",
    "It's round about",
    "It's roughly",
    "It's more or less",
    "Give or take, it's",
)

#: Openings that are only true when the real time is a little before the step.
BEFORE = ("The time is nearly", "It is almost", "It's nearly", "It's coming up on", "It's almost")

#: Openings that are only true when the real time is a little after the step.
AFTER = ("It's a little past", "It's a bit after", "It's shortly after")

_NUMBERS = "twelve one two three four five six seven eight nine ten eleven".split()

#: Extra names for some hours (0-23), used as well as the number word.
NICKNAMES = {
    0: ("midnight", "dark"),
    1: ("late",),
    2: ("really late", "go to bed"),
    3: ("too late",),
    4: ("early morning", "stupid early"),
    5: ("crack of dark",),
    6: ("crack of dawn",),
    7: ("breakfast",),
    12: ("noon", "lunch", "midday"),
    18: ("dinner",),
    22: ("bedtime",),
}

#: Words for each hour, 0-23.
HOURS = {hour: (_NUMBERS[hour % 12], *NICKNAMES.get(hour, ())) for hour in range(24)}

#: Words for each step. From 40 on, the sentence names the next hour ("Ten To Nine").
MINUTES = {
    0: ("o'clock", "on the dot", "sharp", "on the nose"),
    10: ("ten after", "ten past"),
    20: ("twenty after", "twenty past"),
    30: ("half past", "thirty after", "thirty past"),
    40: ("twenty 'til", "twenty to", "twenty before"),
    50: ("ten 'til", "ten to", "ten before"),
}
