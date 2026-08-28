#!/usr/bin/env python3
"""
Year-to-date tally of victims recovered, shared by build.py.

Every story may carry a "recovered" list of structured, summable records:

    "recovered": [
      {"victims": 12, "minors": 4, "arrests": 3, "place": "Texas"},
      {"victims": 40, "place": "Colombia"}
    ]

Rules:
  - "victims" is the number of people located and removed from a
    trafficking situation in THIS operation. Required.
  - "minors" is how many of those victims were under 18, when the
    reporting says. Omit when unknown -- never guess, and never assume
    the remainder are adults.
  - "arrests" is suspects arrested or charged in the same operation.
    Optional; it feeds a secondary counter, not the headline figure.
  - "place" is a US state name for US operations, otherwise a country
    name. build.py matches these strings exactly.
  - Count each operation once. Indictments, sentencings and court
    outcomes describe rescues that happened months or years earlier and
    were almost certainly counted then -- give those stories no
    "recovered" field at all.
  - Omit "recovered" entirely when no victim count is reported. A raid
    with "multiple victims" is not a number and must not be invented.

The tally for a given edition covers that edition's calendar year, up to
and including its own date -- so it resets to zero on 1 January.
"""

from collections import defaultdict

US_STATES = {
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming",
    "District of Columbia", "Puerto Rico", "Guam", "U.S. Virgin Islands",
    # Multi-state federal operations report one national figure and have no
    # single state to file under.
    "United States",
}


def year_of(iso):
    return iso.split("-")[0]


def is_retrospective(day):
    """True for a backfilled monthly retrospective.

    Retrospectives are historical catch-up editions, not days the
    roundup actually ran, so they stay out of the edition numbering.
    Their recoveries still count toward the tally.
    """
    return bool(day.get("retrospective"))


def edition_number(days, date_iso):
    """
    Sequential edition number, oldest edition = 1, counting up one per
    published day. Continuous across years -- an issue number, not a
    year-to-date counter, so it never resets.
    """
    return 1 + sum(
        1
        for d in days
        if d.get("date") and d["date"] < date_iso and not is_retrospective(d)
    )


def fmt_edition(n):
    """O'001, O'002 ... O'999, then O'1000 onward without padding."""
    return f"O'{n:03d}"


def _blank():
    return {"victims": 0, "minors": 0, "arrests": 0, "ops": 0}


def collect(days, upto_date, restrict_year=True):
    """
    Sum every recovery from editions dated on or before `upto_date`.

    With restrict_year=True (the default) only editions in the same
    calendar year as `upto_date` count -- the year-to-date tally, which
    resets on 1 January. With restrict_year=False every edition up to
    that date counts, giving the all-time total.

    Returns (us, intl, n_editions) where us/intl map
    place -> {"victims", "minors", "arrests", "ops"}.
    """
    year = year_of(upto_date) if restrict_year else None
    us = defaultdict(_blank)
    intl = defaultdict(_blank)
    n = 0

    for day in days:
        d = day.get("date", "")
        if not d or d > upto_date:
            continue
        if year is not None and year_of(d) != year:
            continue
        n += 1
        for section in day.get("sections", []):
            for story in section.get("stories") or []:
                for r in story.get("recovered") or []:
                    place = (r.get("place") or "").strip()
                    try:
                        victims = int(r.get("victims") or 0)
                        minors = int(r.get("minors") or 0)
                        arrests = int(r.get("arrests") or 0)
                    except (TypeError, ValueError):
                        continue
                    if not place or victims <= 0:
                        continue
                    bucket = us if place in US_STATES else intl
                    cell = bucket[place]
                    cell["victims"] += victims
                    cell["minors"] += min(minors, victims)
                    cell["arrests"] += arrests
                    cell["ops"] += 1

    return {p: dict(v) for p, v in us.items()}, {p: dict(v) for p, v in intl.items()}, n


def closed_years(days, upto_date):
    """
    Calendar years strictly before `upto_date`'s year that have at least
    one edition, newest first.
    """
    current = year_of(upto_date)
    years = {
        year_of(day.get("date", ""))
        for day in days
        if day.get("date") and year_of(day["date"]) < current
    }
    return sorted(years, reverse=True)


def year_summary(days, year):
    """(us, intl, n_editions, totals) for one complete year."""
    us, intl, n = collect(days, f"{year}-12-31")
    return us, intl, n, totals(us, intl)


def fmt_n(n):
    return f"{n:,}"


def rows(bucket):
    """[(place, cell)] sorted by victims recovered, descending."""
    out = list(bucket.items())
    out.sort(key=lambda r: (-r[1]["victims"], r[0]))
    return out


def totals(us, intl):
    """Combined {"victims", "minors", "arrests", "ops"} across both buckets."""
    out = _blank()
    for bucket in (us, intl):
        for cell in bucket.values():
            for k in out:
                out[k] += cell[k]
    return out


def has_data(us, intl):
    return bool(us or intl)
