#!/usr/bin/env python3
"""
Build the Human Trafficking Roundup archive site from data/*.json.

Usage:  python3 build.py

Reads every data/YYYY-MM-DD.json file and writes:

  index.html                  latest roundup + link to the archive
  archive/index.html          list of every day
  archive/YYYY-MM-DD.html     one page per day
  latest.json                 compact feed for a phone widget

Nothing else is touched. Safe to re-run at any time; output is
regenerated from scratch, so the JSON files are the only source of truth.
"""

import json
import html
import shutil
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import tally

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ARCHIVE = ROOT / "archive"

SITE_TITLE = "Human Trafficking Roundup"

# GitHub Pages reads the custom domain from a CNAME file in the repo root.
# build.py rewrites it every run so the domain cannot be lost to an accidental
# deletion. Empty string = no custom domain; the site stays on github.io and
# no CNAME file is written.
CUSTOM_DOMAIN = ""

SITE_URL = "https://therealwizofoz.github.io/trafficking-roundup/"

SITE_BLURB = (
    "A daily digest of human trafficking enforcement news — victims "
    "recovered, federal and local cases, international operations and "
    "notable prosecutions."
)

# GoatCounter analytics. Set to the site code only -- the bit before
# .goatcounter.com. An empty string disables tracking completely and the
# pages build exactly as they did before.
GOATCOUNTER_CODE = ""

# Canonical section order. A day's JSON may list sections in any order or
# omit them entirely; output always follows this sequence. Recoveries lead,
# because the point of this roundup is who got out.
SECTION_ORDER = [
    ("rescues", "Victims Recovered"),
    ("federal", "National / Federal (US)"),
    ("local", "Local & State Cases"),
    ("world", "International"),
    ("ongoing", "Ongoing Cases with New Developments"),
]


def e(s):
    """Escape a value for HTML text content."""
    return html.escape(str(s), quote=True)


def pretty_date(iso):
    y, m, d = (int(p) for p in iso.split("-"))
    return date(y, m, d).strftime("%A, %B %-d, %Y")


def short_date(iso):
    y, m, d = (int(p) for p in iso.split("-"))
    return date(y, m, d).strftime("%b %-d, %Y")


def load_days():
    days = []
    for path in sorted(DATA.glob("*.json")):
        with path.open(encoding="utf-8") as fh:
            day = json.load(fh)
        day.setdefault("date", path.stem)
        day.setdefault("window", "")
        day.setdefault("sections", [])
        days.append(day)
    days.sort(key=lambda d: d["date"], reverse=True)
    return days


def ordered_sections(day):
    """Return [(id, name, [stories])] in canonical order."""
    by_id = {s.get("id"): s for s in day.get("sections", [])}
    out = []
    for sid, default_name in SECTION_ORDER:
        sec = by_id.get(sid, {})
        out.append((sid, sec.get("name") or default_name, sec.get("stories") or []))
    return out


def image_html(story, css_prefix=""):
    """
    Thumbnail for a story, when a photo is available.

    Only public-domain images are ever stored in assets/img -- in practice
    that means US federal agency releases (HSI, FBI, DOJ, DHS), whose works
    are not subject to copyright under 17 U.S.C. section 105. Photos from
    news outlets and wire agencies are not reproduced.

    Never a victim, never a mugshot. See the run prompt for the full rule.
    """
    img = story.get("image")
    if not img or not img.get("file"):
        return ""
    credit = img.get("credit", "")
    caption = f'<figcaption>{e(credit)}</figcaption>' if credit else ""
    return (
        f'<figure class="shot">'
        f'<img src="{css_prefix}assets/img/{e(img["file"])}" '
        f'alt="{e(img.get("alt", ""))}" loading="lazy" decoding="async">'
        f"{caption}</figure>"
    )


def story_html(story, css_prefix="", day_date=""):
    chips = []
    if story.get("victims"):
        chips.append(f'<span class="chip qty">{e(story["victims"])}</span>')
    if story.get("location"):
        chips.append(f'<span class="chip">{e(story["location"])}</span>')
    if story.get("arrests"):
        chips.append(f'<span class="chip">{e(story["arrests"])}</span>')
    chip_block = f'<div class="chips">{"".join(chips)}</div>' if chips else ""

    url = story.get("url", "")
    src = story.get("source") or "Source"
    link = (
        f'<div class="source"><span class="label">Source</span>'
        f'<a href="{e(url)}"{click_attr(url)} rel="noopener noreferrer nofollow" target="_blank">{e(src)}</a></div>'
        if url
        else ""
    )

    body = (
        f'<h3>{e(story.get("headline", "Untitled"))}</h3>'
        f"{chip_block}"
        f'<p>{e(story.get("body", ""))}</p>'
        f"{link}"
    )

    shot = image_html(story, css_prefix)
    if shot:
        return f'<article class="story has-shot"><div class="story-text">{body}</div>{shot}</article>'
    return f'<article class="story">{body}</article>'


def tally_table(bucket):
    """
    One expandable row per place. The summary carries the place and the
    number of people recovered there; tapping it reveals the detail.

    <details> keeps the breakdown reachable on a phone without JavaScript,
    and scales: by December this list is long, and totals with detail on
    demand read better than a wall of text.
    """
    out = ""
    for place, cell in tally.rows(bucket):
        ops = cell["ops"]
        items = [("people recovered", cell["victims"])]
        if cell["minors"]:
            items.append(("of whom minors", cell["minors"]))
        if cell["arrests"]:
            items.append(("suspects arrested or charged", cell["arrests"]))
        rows = "".join(
            f'<li><span class="d">{e(label)}</span>'
            f'<span class="w">{tally.fmt_n(n)}</span></li>'
            for label, n in items
        )
        out += (
            '<details class="place">'
            f'<summary><span class="p">{e(place)}</span>'
            f'<span class="n">{ops} {"operation" if ops == 1 else "operations"}</span>'
            f'<span class="t">{tally.fmt_n(cell["victims"])}</span></summary>'
            f'<ul class="drugs">{rows}</ul>'
            "</details>"
        )
    return f'<div class="places">{out}</div>'


def tally_groups(us, intl):
    out = ""
    if us:
        out += f"<h3>United States</h3>{tally_table(us)}"
    if intl:
        out += f"<h3>International</h3>{tally_table(intl)}"
    return out


def tally_meta(t, n_editions, places):
    bits = [f'{n_editions} {"edition" if n_editions == 1 else "editions"}']
    bits.append(f'{places} {"place" if places == 1 else "places"}')
    if t["minors"]:
        bits.append(f'{tally.fmt_n(t["minors"])} minors')
    if t["arrests"]:
        bits.append(f'{tally.fmt_n(t["arrests"])} arrested')
    return " · ".join(bits)


def render_prior_years(days, upto_date):
    """Closed years, newest first, each collapsed to a summary line."""
    years = tally.closed_years(days, upto_date)
    if not years:
        return ""
    items = ""
    for year in years:
        us, intl, n, t = tally.year_summary(days, year)
        if not tally.has_data(us, intl):
            continue
        places = len(us) + len(intl)
        items += f"""<details class="year">
<summary><span class="y">{e(year)}</span>
<span class="t">{tally.fmt_n(t["victims"])} recovered</span>
<span class="m">{tally_meta(t, n, places)}</span></summary>
<div class="year-body">{tally_groups(us, intl)}</div>
</details>"""
    if not items:
        return ""
    all_us, all_intl, _ = tally.collect(days, upto_date, restrict_year=False)
    all_time = tally.totals(all_us, all_intl)
    return f"""<div class="prior-years">
<h3>Previous years</h3>
{items}
<p class="all-time"><span class="label">All time</span>
<span class="v">{tally.fmt_n(all_time["victims"])} recovered</span></p>
</div>"""


def render_tally(days, upto_date):
    us, intl, n = tally.collect(days, upto_date)
    prior = render_prior_years(days, upto_date)
    if not tally.has_data(us, intl) and not prior:
        return ""
    t = tally.totals(us, intl)
    places = len(us) + len(intl)
    year = tally.year_of(upto_date)
    return f"""<section class="block tally" id="tally">
<h2>{e(year)} Running Tally</h2>
<p class="tally-note">People recovered across every story covered so far this
year, through {e(short_date(upto_date))} — located and removed from a trafficking
situation, or found in the endangered-missing operations aimed at it. Counts each
operation once at the time it is reported — later indictments and
sentencings in the same case are not added again — and resets to zero each
1 January. Figures are as stated by the source; where a report gives no number,
nothing is counted. Earlier years are kept below.</p>
<div class="tally-headline"><span class="big">{tally.fmt_n(t["victims"])}</span>
<span class="meta">{tally_meta(t, n, places)}</span></div>
{tally_groups(us, intl)}
{prior}
</section>"""


def analytics_html():
    """GoatCounter beacon, or nothing at all when tracking is off."""
    if not GOATCOUNTER_CODE:
        return ""
    return (
        '<script data-goatcounter="https://'
        f'{GOATCOUNTER_CODE}.goatcounter.com/count"'
        ' async src="//gc.zgo.at/count.js"></script>\n'
    )


def click_attr(url):
    """Count a click as ext-<host> so sources aggregate across editions."""
    if not GOATCOUNTER_CODE or not url:
        return ""
    host = urlsplit(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return ""
    return f' data-goatcounter-click="ext-{e(host)}"'


def page(title, body, css_prefix=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{e(title)}</title>
<meta name="description" content="{e(SITE_BLURB)}">
<link rel="stylesheet" href="{css_prefix}assets/style.css">
</head>
<body>
<div class="wrap">{body}</div>
{analytics_html()}</body>
</html>
"""


def render_day(day, css_prefix="", is_home=False, day_count=0, all_days=()):
    sections = ordered_sections(day)
    total = sum(len(s[2]) for s in sections)
    tally_html = render_tally(all_days, day["date"])

    nav = (
        '<nav class="top">'
        + (
            f'<a href="{css_prefix}index.html" aria-current="page">Latest</a>'
            if is_home
            else f'<a href="{css_prefix}index.html">Latest</a>'
        )
        + f'<a href="{css_prefix}archive/index.html">Archive'
        + (f" ({day_count})" if day_count else "")
        + "</a>"
        + "</nav>"
    )

    toc_items = "".join(
        f'<li><a href="#{sid}">{e(name)}</a>'
        f'<span class="count">{len(stories)}</span></li>'
        for sid, name, stories in sections
    )
    if tally_html:
        toc_items += '<li class="toc-tally"><a href="#tally">Running Tally</a></li>'

    blocks = []
    for i, (sid, name, stories) in enumerate(sections, start=1):
        inner = (
            "".join(story_html(s, css_prefix, day["date"]) for s in stories)
            if stories
            else '<p class="empty">'
            + (
                "Nothing significant found for this month."
                if tally.is_retrospective(day)
                else "Nothing significant in the past 24 hours."
            )
            + "</p>"
        )
        blocks.append(
            f'<section class="block" id="{sid}">'
            f'<h2><span class="num">{i}</span>{e(name)}</h2>'
            f"{inner}</section>"
        )

    window = f'<p class="window">{e(day["window"])}</p>' if day.get("window") else ""

    retro = tally.is_retrospective(day)
    if retro:
        kicker = "Archive"
        dateline = e(day.get("period") or pretty_date(day["date"]))
        note = (
            "<p>A retrospective edition, compiled after the fact to fill in "
            "the record before this site began publishing daily. Coverage is "
            "the month's significant events rather than every incident.</p>"
        )
    else:
        kicker = "Edition " + e(
            tally.fmt_edition(tally.edition_number(all_days, day["date"]))
        )
        dateline = e(pretty_date(day["date"]))
        note = (
            "<p>Compiled automatically each morning at 6:00 AM Central. Every "
            "story is deduplicated against a running log, so nothing repeats "
            "between editions.</p>"
        )

    body = f"""<header class="masthead">
<p class="kicker">{kicker}</p>
<h1>{e(SITE_TITLE)}</h1>
<p class="dateline">{dateline} · {total} {"story" if total == 1 else "stories"}</p>
{window}{nav}</header>
<div class="toc"><h2>In this edition</h2><ol>{toc_items}</ol></div>
{"".join(blocks)}
{tally_html}
<footer>{note}
<p>Links go to the original reporting; victim counts and arrest figures are as
stated by the source. Victims are never named or pictured here.</p></footer>"""

    return page(f"{SITE_TITLE} — {short_date(day['date'])}", body, css_prefix)


def archive_items(days):
    return "".join(
        f'<li><a href="{e(d["date"])}.html">'
        f'<span class="d">'
        f'{e(d.get("period") or pretty_date(d["date"]))}</span>'
        f'<span class="n">{sum(len(s.get("stories") or []) for s in d.get("sections", []))} stories</span>'
        "</a></li>"
        for d in days
    )


def render_archive(days):
    daily = [d for d in days if not tally.is_retrospective(d)]
    retro = [d for d in days if tally.is_retrospective(d)]
    items = archive_items(daily)
    retro_block = (
        '<h2 class="arch-h">Retrospectives</h2>'
        '<p class="arch-note">Backfilled monthly summaries covering the period '
        'before daily publication began.</p>'
        f'<ul class="archive">{archive_items(retro)}</ul>'
        if retro
        else ""
    )
    body = f"""<header class="masthead">
<p class="kicker">Archive</p>
<h1>{e(SITE_TITLE)}</h1>
<p class="dateline">{len(daily)} {"edition" if len(daily) == 1 else "editions"}
{f" · {len(retro)} retrospectives" if retro else ""}</p>
<nav class="top"><a href="../index.html">Latest</a>
<a href="index.html" aria-current="page">Archive</a></nav></header>
<ul class="archive">{items}</ul>
{retro_block}
<footer><p>Every edition since the roundup began. Stories are never repeated
across editions.</p></footer>"""
    return page(f"{SITE_TITLE} — Archive", body, css_prefix="../")


# ---------------------------------------------------------------------------
# Widget feed
#
# latest.json is a stripped-down version of the newest edition, written to the
# site root so a phone widget can fetch one small file instead of parsing
# HTML. Headlines and metadata only -- no bodies, no markup.
# ---------------------------------------------------------------------------

FEED_STORY_LIMIT = 12
FEED_SUMMARY_CHARS = 180


def summarize(text, limit=FEED_SUMMARY_CHARS):
    """Trim a story body to a widget-sized summary, preferring a sentence break."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if stop > 80:
        return cut[: stop + 1]
    space = cut.rfind(" ")
    return (cut[:space] if space > 0 else cut).rstrip(",;:") + "…"


def render_feed(day, all_days):
    sections = ordered_sections(day)
    stories = []
    for sid, name, items in sections:
        for story in items:
            stories.append(
                {
                    "section": sid,
                    "sectionName": name,
                    "headline": story.get("headline", ""),
                    "summary": summarize(story.get("body", "")),
                    "location": story.get("location", ""),
                    "victims": story.get("victims", ""),
                    "arrests": story.get("arrests", ""),
                    "source": story.get("source", ""),
                    "url": story.get("url", ""),
                }
            )
    us, intl, _ = tally.collect(all_days, day["date"])
    t = tally.totals(us, intl)
    return {
        "date": day["date"],
        "dateLabel": pretty_date(day["date"]),
        "window": day.get("window", ""),
        "siteUrl": SITE_URL,
        "storyCount": len(stories),
        "yearToDate": {
            "year": tally.year_of(day["date"]),
            "victims": t["victims"],
            "minors": t["minors"],
            "arrests": t["arrests"],
        },
        "sectionCounts": [
            {"id": sid, "name": name, "count": len(items)}
            for sid, name, items in sections
            if items
        ],
        "stories": stories[:FEED_STORY_LIMIT],
    }


def main():
    days = load_days()
    if not days:
        raise SystemExit("No data files found in data/ -- nothing to build.")

    newest = next((d for d in days if not tally.is_retrospective(d)), days[0])

    if ARCHIVE.exists():
        shutil.rmtree(ARCHIVE)
    ARCHIVE.mkdir(parents=True)

    (ROOT / "index.html").write_text(
        render_day(newest, css_prefix="", is_home=True, day_count=len(days),
                   all_days=days),
        encoding="utf-8",
    )
    for day in days:
        (ARCHIVE / f"{day['date']}.html").write_text(
            render_day(day, css_prefix="../", is_home=False, day_count=len(days),
                       all_days=days),
            encoding="utf-8",
        )
    (ARCHIVE / "index.html").write_text(render_archive(days), encoding="utf-8")

    (ROOT / ".nojekyll").touch()
    if CUSTOM_DOMAIN:
        (ROOT / "CNAME").write_text(CUSTOM_DOMAIN + "\n", encoding="utf-8")
    (ROOT / "latest.json").write_text(
        json.dumps(render_feed(newest, days), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"Built {len(days)} edition(s).")


if __name__ == "__main__":
    main()
