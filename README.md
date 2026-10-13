# Safety headlines for the AutoTQ industry pages

Each AutoTQ industry page has a "Safety in the news" section: up to four recent headlines about safety in that
industry, with the publisher and the date, each linking out to the publisher. No article text is copied.

- `sources.json` lists the feeds (trade and safety publications, safety agencies) and the rules.
- `fetch.py` reads them and writes one small JSON file per industry into `docs/`. Standard library only.
- `.github/workflows/update.yml` runs it every four hours and commits what changed.
- GitHub Pages serves `docs/`, so a page reads `https://healthcarevisor.github.io/autotq-news/<industry>.json`.

Nothing here is secret. No key is needed: the headlines come from the publishers' own feeds.

## What the rules do

A headline is kept when it is about safety in that industry (a pattern per industry plus a shared safety pattern), is
no older than 90 days (150 where news is thin), and is not on the block list (politics, lawsuits, deals, cyber
security, vendor announcements). On the pages about campuses, venues, parks, schools and law enforcement, incident
wording (shootings, arrests, deaths) is dropped too, so the list stays about readiness. No list shows more than one
headline about a death, and no more than two or three from one publisher. A feed that does not answer is tried three
times, and a list is never replaced by an empty one.

See what was kept and why the rest was dropped:

    python fetch.py --show

## Running it by hand

    python fetch.py --out docs

## Adding a news API key (optional)

The free plans of the common news APIs do not allow use on a live commercial site (NewsAPI.org, GNews, Mediastack
and Perigon say so in their terms, read 2026-10-13). TheNewsAPI's paid plan ($19 a month) allows it and can be
limited to a list of publishers. To use one: add the repository variable `NEWS_API_PROVIDER` and the secret
`NEWS_API_KEY` (Settings > Secrets and variables > Actions). Its results go through the same rules as the feeds.
The provider code has not been run with a live key yet.
