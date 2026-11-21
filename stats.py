# Data for the "today" strip shown under the deck list.
from __future__ import annotations

from dataclasses import dataclass

from anki.collection import Collection

DAY = 86400
# revlog types that count as real study (not manual reschedules)
STUDY_TYPES = "(0, 1, 2, 3)"


@dataclass
class TodayStats:
    cards: int
    seconds: int
    streak: int
    studied_yesterday: bool
    due: int


def collect(col: Collection) -> TodayStats:
    cutoff = col.sched.day_cutoff  # start of tomorrow, in seconds
    today_start_ms = (cutoff - DAY) * 1000

    cards, secs = col.db.first(
        f"select count(), coalesce(sum(time), 0) / 1000 from revlog "
        f"where id >= ? and type in {STUDY_TYPES}",
        today_start_ms,
    )

    # Distinct study days, as "days ago" relative to today (0 = today).
    rows = col.db.list(
        f"select distinct cast(({cutoff} - id / 1000) / {DAY} as int) "
        f"from revlog where type in {STUDY_TYPES} order by 1"
    )
    days = set(rows)
    studied_today = 0 in days
    studied_yesterday = 1 in days
    streak = 0
    day = 0 if studied_today else 1
    while day in days:
        streak += 1
        day += 1

    tree = col.sched.deck_due_tree()
    due = tree.new_count + tree.learn_count + tree.review_count

    return TodayStats(
        cards=int(cards),
        seconds=int(secs),
        streak=streak,
        studied_yesterday=studied_yesterday,
        due=due,
    )


def fmt_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if minutes else f"{hours}h"
