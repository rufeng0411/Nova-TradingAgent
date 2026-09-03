# -*- coding: utf-8 -*-
"""Verify Tushare sidebar doc_id count vs docs/TUSHARE_API_MASTER.zh.md §3 table."""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8")


def main() -> None:
    html = fetch("https://tushare.pro/document/2")
    nav = re.search(
        r'<nav class="sidebar col-md-3 col-sm-4 col-xs-12">([\s\S]*?)</nav>',
        html,
    )
    assert nav
    block = nav.group(1)
    sidebar_ids = sorted(set(re.findall(r"/document/2\?doc_id=(\d+)", block)), key=int)
    whole_ids = set(re.findall(r"/document/2\?doc_id=(\d+)", html))
    extra_in_page = sorted(whole_ids - set(sidebar_ids), key=int)

    md = Path(__file__).resolve().parents[1] / "docs" / "TUSHARE_API_MASTER.zh.md"
    text = md.read_text(encoding="utf-8")
    sec = text.split("## 3. 全量官方导航")[1] if "## 3. 全量官方导航" in text else text
    md_ids = re.findall(r"^\| (\d{1,4}) \|", sec, re.M)
    md_ids_set = set(md_ids)

    print("sidebar nav unique doc_ids:", len(sidebar_ids), f"range {sidebar_ids[0]}..{sidebar_ids[-1]}")
    print("full /document/2 page unique doc_ids:", len(whole_ids))
    print("doc_ids on page but NOT in sidebar:", extra_in_page)
    print("TUSHARE_API_MASTER §3 table data rows:", len(md_ids), "unique:", len(md_ids_set))
    if md_ids_set != set(sidebar_ids):
        only_md = sorted(md_ids_set - set(sidebar_ids), key=int)
        only_web = sorted(set(sidebar_ids) - md_ids_set, key=int)
        print("only in MD (stale?):", only_md, "count", len(only_md))
        print("only on web (missing from MD?):", only_web, "count", len(only_web))


def debug_extra_ids() -> None:
    html = fetch("https://tushare.pro/document/2")
    nav = re.search(
        r'<nav class="sidebar col-md-3 col-sm-4 col-xs-12">([\s\S]*?)</nav>',
        html,
    )
    assert nav
    body = html.replace(nav.group(0), "")
    for did in ("31", "104"):
        m = re.search(r".{0,120}doc_id=%s.{0,120}" % did, body)
        print("context", did, ":", (m.group(0) if m else "NONE")[:240])


if __name__ == "__main__":
    main()
    print("---")
    debug_extra_ids()
