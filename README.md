# Human Trafficking Roundup

A daily digest of human trafficking enforcement news, published to
<https://therealwizofoz.github.io/trafficking-roundup/>.

The lead of every edition is the people who got out. Enforcement, prosecutions
and policy are covered because they bear on that.

## How it runs

Everything happens on GitHub's machines. Nothing depends on a local computer.

1. `.github/workflows/roundup.yml` fires daily at 6:00 AM Central. GitHub cron
   is UTC and ignores daylight saving, so the workflow fires at both candidate
   hours and a guard job drops the one that is not 06:00 in America/Chicago.
2. Claude reads `.github/roundup-prompt.md` — the trusted spec for the job —
   researches the past 24 hours, and writes one file: `data/YYYY-MM-DD.json`.
3. `build.py` regenerates the whole site from `data/*.json`.
4. A workflow step commits, pushes, asks GitHub Pages to rebuild, and verifies
   the new archive page returns 200 before the run is called a success.

## The pieces

| Path | What it is |
| --- | --- |
| `data/YYYY-MM-DD.json` | One edition. The only source of truth. |
| `data/trafficking-log.csv` | Every story ever published. The dedupe source. |
| `data/last-run.txt` | Report from the most recent run. |
| `build.py` | Generates `index.html`, `archive/`, `latest.json`. |
| `tally.py` | The running tally of people recovered. |
| `assets/style.css` | The whole design. No build step. |
| `.github/roundup-prompt.md` | What the daily job is told to do. |

**Never hand-edit an HTML file.** The next build overwrites it. Change the JSON
or change `build.py`.

## Running it by hand

```bash
python3 build.py       # rebuild from data/
./publish.sh           # rebuild, commit and push
```

## Editorial rules that are not negotiable

- Victims are never named and never pictured, adults included.
- Abuse is not described in detail.
- Images are US federal government photographs only — never a victim, never a
  mugshot, never a wire-service photo.
- Summaries are written from the facts, in original words. See the prompt.

## Setup this repo needs once

- **Repository secret `CLAUDE_CODE_OAUTH_TOKEN`** — generate with
  `claude setup-token`, then
  `gh secret set CLAUDE_CODE_OAUTH_TOKEN -R therealwizofoz/trafficking-roundup`.
  The daily workflow cannot run without it.
- **GitHub Pages** — enabled, serving `main` from the repository root.
- **Custom domain** — none yet. To add one, set `CUSTOM_DOMAIN` in `build.py`;
  it rewrites the `CNAME` file on every build so the domain cannot be lost.
