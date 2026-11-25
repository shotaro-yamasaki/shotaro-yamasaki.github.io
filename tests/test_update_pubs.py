"""Offline test of scripts/update_pubs.py with a fake ADS. Run: python tests/test_update_pubs.py
Writes the result to a temporary folder (the real data/ads.json is not touched).
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import update_pubs as U  # noqa: E402


def doc(bib, ax, title, authors, cites, refereed=True, page=None, vol=None, year="2026", doctype="article"):
    return {"bibcode": bib, "identifier": [f"arXiv:{ax}"] if ax else [], "title": [title], "author": authors,
            "citation_count": cites, "property": ["REFEREED"] if refereed else [], "page": [page] if page else None,
            "volume": vol, "year": year, "pubdate": f"{year}-11-00", "doctype": doctype, "pub": ""}


def fake(q, fl=U.FL, rows=200):
    if q.startswith("identifier:("):
        ids = re.findall(r"arXiv:(\d{4}\.\d{4,5})", q)
        out = []
        for a in ids:
            if a == "2611.15099":  # submitted paper is now published in ApJ
                out.append(doc("2027ApJ...999..123Y", a, "x", ["Yamasaki, Shotaro"], 3, page="123", vol="999", year="2027"))
                out.append(doc("2026arXiv261115099Y", a, "x", ["Yamasaki, Shotaro"], 3, refereed=False))
            elif a == "1909.00849":
                out.append(doc("2020ApJ...888..105Y", a, "x", ["Yamasaki, Shotaro"], 181, page="105", vol="888", year="2020"))
            else:
                out.append(doc(f"2020XXX{a}", a, "x", ["Yamasaki, Shotaro"], 7))
        return out
    return [  # ORCID query
        doc("2026arXiv261200001Y", "2612.00001", "A brand new first-author paper on FRB scattering",
            ["Yamasaki, Shotaro", "Hashimoto, Tetsuya"], 0, refereed=False, year="2026", doctype="eprint"),
        doc("2026MNRAS.540..777C", "2610.00002", "A new coauthored paper",
            ["Chen, A.", "Lee, B.", "Yamasaki, Shotaro", "Wu, C.", "Lin, D."], 2, page="777", vol="540"),
        doc("2026MNRAS.541L..12K", "2610.00003", "Letter with many authors",
            ["Kim, A.", "B, B.", "C, C.", "D, D.", "E, E.", "Yamasaki, S."], 1, page="L12", vol="541"),
        doc("2026AAS...24710101Y", None, "Conference abstract", ["Yamasaki, Shotaro"], 0, refereed=False, doctype="abstract"),
        doc("2026ApJ...990...10S", None, "A Possible Solution to the Fermi Paradox? The Lethal Impact of Asteroid Collisions, Supernova Explosions, and Giant Molecular Clouds on Advanced Technological Civilization Migration",
            ["Senjaya, X.", "Yamasaki, Shotaro"], 5, page="10", vol="990"),
    ]


def main():
    U.ads_search = fake
    U.OUT = Path(tempfile.mkdtemp()) / "ads.json"
    os.environ["ADS_TOKEN"] = "fake"
    U.main()
    A = json.loads(U.OUT.read_text())
    assert A["by_arxiv"]["2611.15099"]["j"] == "ApJ, 999, 123", A["by_arxiv"]["2611.15099"]
    assert A["by_arxiv"]["1909.00849"]["c"] == 181
    t = "A Possible Solution to the Fermi Paradox? The Lethal Impact of Asteroid Collisions, Supernova Explosions, and Giant Molecular Clouds on Advanced Technological Civilization Migration"
    assert A["by_title"][t]["c"] == 5
    new = {p["t"]: p for p in A["new"]}
    assert "Conference abstract" not in new
    assert new["A brand new first-author paper on FRB scattering"]["a"] == "<b>Yamasaki</b> & Hashimoto"
    assert new["A brand new first-author paper on FRB scattering"]["j"] == "arXiv preprint"
    assert new["A new coauthored paper"]["a"] == "Chen, Lee, <b>Yamasaki</b>, et al."
    assert new["Letter with many authors"]["a"] == "Kim et al. incl. <b>Yamasaki</b>"
    assert new["Letter with many authors"]["j"] == "MNRAS Letters, 541, L12"
    print(json.dumps(A["new"], ensure_ascii=False, indent=1)[:600])
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(U.OUT.read_text())
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
