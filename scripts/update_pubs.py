"""Refresh publication data for the homepage from NASA ADS.

Reads the hand-written PUBS list in index.html (it stays the main source),
then writes data/ads.json with:
  - the current ADS citation count of each listed paper,
  - the journal reference of listed papers that ADS now shows as published,
  - papers found with my ORCID that are not in PUBS yet.
index.html merges this file when the page loads. If the file is missing, the page shows PUBS as written.

Needs the repository secret ADS_TOKEN (https://ui.adsabs.harvard.edu/user/settings/token).
Only the Python standard library is needed.
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
OUT = ROOT / "data" / "ads.json"
ORCID = "0000-0002-1688-8708"
ME = "Yamasaki, S"
ADS_URL = "https://api.adsabs.harvard.edu/v1/search/query"
FL = "bibcode,identifier,title,author,pub,volume,page,year,pubdate,citation_count,property,doctype"
# ADS records never to add automatically (bibcodes). Add here if a wrong paper appears.
EXCLUDE = set()
KEEP_DOCTYPES = {"article", "eprint"}

JOURNALS = {  # ADS bibstem -> short name used on the page
    "ApJ": "ApJ", "ApJS": "ApJS", "AJ": "AJ", "MNRAS": "MNRAS", "A&A": "A&A", "PASJ": "PASJ",
    "PASP": "PASP", "PASA": "PASA", "Natur": "Nature", "NatAs": "Nature Astronomy", "Sci": "Science",
    "PhRvD": "PRD", "PhRvL": "PRL", "JCAP": "JCAP", "ARA&A": "ARA&A", "RAA": "RAA", "Univ": "Universe",
    "SSRv": "Space Sci. Rev.", "JHEAp": "JHEAp", "ApJL": "ApJL",
}


def ads_search(q, fl=FL, rows=200):
    token = re.sub(r"^Bearer:?\s*", "", os.environ["ADS_TOKEN"].strip()).strip()
    docs, start = [], 0
    while True:
        url = ADS_URL + "?" + urllib.parse.urlencode({"q": q, "fl": fl, "rows": rows, "start": start, "sort": "date desc"})
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        for i in range(3):
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    res = json.loads(r.read())["response"]
                break
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    sys.exit(f"ADS rejected the token (HTTP {e.code}). Update the ADS_TOKEN secret.")
                if i == 2:
                    raise
                time.sleep(5 * (i + 1))
            except Exception:  # noqa: BLE001
                if i == 2:
                    raise
                time.sleep(5 * (i + 1))
        docs += res["docs"]
        start += len(res["docs"])
        if not res["docs"] or start >= res["numFound"]:
            return docs


def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def arxiv_of(doc):
    for ident in doc.get("identifier") or []:
        m = re.fullmatch(r"(?:arXiv:)?(\d{4}\.\d{4,5})(v\d+)?", ident)
        if m:
            return m.group(1)
    return None


def title_of(doc):
    t = doc.get("title") or [""]
    return t[0] if isinstance(t, list) else t


def journal_ref(doc):
    """Short reference like 'ApJL, 997, L6' or 'MNRAS Letters, 528, L133'. None if not a journal paper."""
    bib = doc.get("bibcode", "")
    stem = bib[4:9].strip(".")
    if stem == "arXiv" or "REFEREED" not in (doc.get("property") or []):
        return None
    name = JOURNALS.get(stem, doc.get("pub") or stem)
    page = (doc.get("page") or [""])[0]
    if page.startswith("L") and name in ("ApJ", "MNRAS"):
        name = "ApJL" if name == "ApJ" else "MNRAS Letters"
    parts = [name] + [x for x in (doc.get("volume"), page) if x]
    return ", ".join(parts)


def author_string(authors):
    """Same style as the hand-written list."""
    sur = [a.split(",")[0].strip() for a in authors]
    idx = next((i for i, a in enumerate(authors) if a.startswith(ME)), None)
    if idx is None:
        return None, None
    sur[idx] = "<b>Yamasaki</b>"
    if idx == 0:
        if len(sur) == 1:
            s = sur[0]
        elif len(sur) <= 4:
            s = ", ".join(sur[:-1]) + " & " + sur[-1]
        else:
            s = ", ".join(sur[:3]) + ", et al."
        return s, "first"
    if idx <= 3:
        s = ", ".join(sur[:idx + 1]) + (", et al." if len(sur) > idx + 1 else "")
    else:
        s = f"{sur[0]} et al. incl. <b>Yamasaki</b>"
    return s, "co"


def read_curated():
    html = INDEX.read_text(encoding="utf-8")
    block = re.search(r"const PUBS = \[(.*?)\n\];", html, re.S).group(1)
    items = []
    for line in block.splitlines():
        if "t:\"" not in line:
            continue
        t = re.search(r'\bt:"((?:[^"\\]|\\.)*)"', line).group(1)
        ax = re.search(r'\bax:"([^"]+)"', line)
        items.append({"t": t, "ax": ax.group(1) if ax else None})
    return items


def main():
    if not os.environ.get("ADS_TOKEN"):
        print("ADS_TOKEN is not set: nothing to do.")
        return
    curated = read_curated()
    ax_ids = [c["ax"] for c in curated if c["ax"]]
    titles = {norm_title(c["t"]): c["t"] for c in curated}
    print(f"{len(curated)} papers in index.html ({len(ax_ids)} with arXiv ids)")

    by_ax = {}
    for i in range(0, len(ax_ids), 20):
        q = "identifier:(" + " OR ".join(f'"arXiv:{a}"' for a in ax_ids[i:i + 20]) + ")"
        for d in ads_search(q):
            a = arxiv_of(d)
            if a in ax_ids:
                # Prefer the refereed record if ADS has two.
                if a not in by_ax or "REFEREED" in (d.get("property") or []):
                    by_ax[a] = d

    mine = ads_search(f'orcid:"{ORCID}"')
    print(f"{len(mine)} ADS records with my ORCID")
    by_title = {}
    new = []
    for d in mine:
        a, nt = arxiv_of(d), norm_title(title_of(d))
        if a in ax_ids:
            continue
        if nt in titles:
            by_title[nt] = d
            continue
        if d["bibcode"] in EXCLUDE or d.get("doctype") not in KEEP_DOCTYPES:
            continue
        a_str, cat = author_string(d.get("author") or [])
        if not a_str:
            continue
        jr = journal_ref(d)
        new.append({
            "a": a_str, "t": title_of(d), "y": int(d["year"]) if jr and d.get("year") else "",
            "j": jr or "arXiv preprint", "ax": a, "c": d.get("citation_count") or 0, "cat": cat,
            "bibcode": d["bibcode"], "date": d.get("pubdate", ""),
        })
    # One entry per paper even if ADS lists the preprint and the journal version separately.
    seen, uniq = set(), []
    for p in sorted(new, key=lambda p: p["j"] == "arXiv preprint"):
        k = p["ax"] or norm_title(p["t"])
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    new = sorted(uniq, key=lambda p: p["date"], reverse=True)

    def rec(d):
        return {"c": d.get("citation_count") or 0, "j": journal_ref(d),
                "y": int(d["year"]) if d.get("year") else None, "bibcode": d["bibcode"]}

    out = {
        "updated": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "by_arxiv": {a: rec(d) for a, d in by_ax.items()},
        "by_title": {titles[k]: rec(d) for k, d in by_title.items()},
        "new": new,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"matched {len(by_ax)} by arXiv id, {len(by_title)} by title, {len(new)} new papers -> {OUT}")


if __name__ == "__main__":
    main()
