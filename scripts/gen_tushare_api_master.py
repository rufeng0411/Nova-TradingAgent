# -*- coding: utf-8 -*-
"""
生成 docs/TUSHARE_API_MASTER.zh.md：
- 官方 /document/2 侧栏全 doc 索引 + 积分类/独立类粗分；
- 对照 [数据索引 doc209](https://tushare.pro/document/2?doc_id=209) 正文摘要区链接（含侧栏未列的 doc_id），并标注与侧栏差异。

运行：uv run python scripts/gen_tushare_api_master.py
"""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path

DOC2 = "https://tushare.pro/document/2"
DOC108 = "https://tushare.pro/document/1?doc_id=108"
DOC290 = "https://tushare.pro/document/1?doc_id=290"
DOC209 = "https://tushare.pro/document/2?doc_id=209"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (TA-gen/1.0)"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8")


def parse_sidebar_titles(html: str) -> dict[str, str]:
    nav = re.search(
        r'<nav class="sidebar col-md-3 col-sm-4 col-xs-12">([\s\S]*?)</nav>',
        html,
    )
    if not nav:
        raise RuntimeError("sidebar not found")
    block = nav.group(1)
    out: dict[str, str] = {}
    for doc_id, title in re.findall(r'<a href="/document/2\?doc_id=(\d+)">([^<]+)</a>', block):
        out[doc_id] = title.strip()
    return out


def parse_doc108(html: str) -> dict[str, tuple[str, str]]:
    """doc_id -> (api, min_score)"""
    pat = re.compile(
        r'document/2\?doc_id=(\d+)\">([^<]+)</a></td>\s*<td>([a-zA-Z0-9_]+)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>',
        re.S,
    )
    m: dict[str, tuple[str, str]] = {}
    for doc_id, _t, api, _d, score in pat.findall(html):
        m[doc_id] = (api, score.strip())
    return m


def parse_doc209_index_chunk(html209: str) -> str | None:
    m = re.search(r"<h2[^>]*>[^<]*数据索引[^<]*</h2>", html209)
    if not m:
        return None
    return html209[m.end() : m.end() + 12000]


def parse_doc209_sections(chunk: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """
    解析 doc209 正文「数据索引」下各 blockquote 分区及其后紧跟的若干 <p> 内链接。
    返回 [(分区标题, [(doc_id, 锚文本), ...]), ...]
    """
    out: list[tuple[str, list[tuple[str, str]]]] = []
    pos = 0
    while True:
        bq = re.search(
            r"<blockquote>\s*<p>\s*([^<]+)</p>\s*</blockquote>",
            chunk[pos:],
        )
        if not bq:
            break
        pos += bq.end()
        sec = bq.group(1).strip()
        links: list[tuple[str, str]] = []
        while True:
            rel = chunk[pos:]
            if rel.lstrip().startswith("<blockquote>"):
                break
            pm = re.match(r"\s*<p>([\s\S]*?)</p>", rel)
            if not pm:
                break
            body = pm.group(1)
            pos += pm.end()
            for did, txt in re.findall(
                r'(?:https://tushare\.pro)?/document/2\?doc_id=(\d+)">([^<]+)</a>',
                body,
            ):
                links.append((did, txt.strip()))
        out.append((sec, links))
    return out


def first_label_per_doc(sections: list[tuple[str, list[tuple[str, str]]]]) -> dict[str, str]:
    first: dict[str, str] = {}
    for _sec, links in sections:
        for did, txt in links:
            if did not in first:
                first[did] = txt
    return first


def classify_row(
    doc_id: str,
    display_title: str,
    doc108: dict[str, tuple[str, str]],
    standalone_docs: set[str],
    index_label: str | None,
) -> tuple[str, str]:
    """粗分类 + 说明。index_label 为数据索引中的首见锚文本（若有）。"""
    label = index_label or ""
    combined = f"{display_title} {label}"
    low = combined.lower()
    if (
        "分钟" in combined
        or "Tick" in combined
        or "tick" in low
        or doc_id in standalone_docs
    ):
        if doc_id in doc108:
            return (
                "独立权限（或含独立分钟/实时等）",
                f"doc108 亦有记录: `{doc108[doc_id][0]}` / {doc108[doc_id][1]}",
            )
        return "独立权限（或含独立分钟/实时等）", "以 [doc290 表二](https://tushare.pro/document/1?doc_id=290) 及各接口页「单独开权限」为准"
    if doc_id in doc108:
        return "积分门槛", f"`{doc108[doc_id][0]}` 最低分 {doc108[doc_id][1]}"
    return "积分门槛（默认）", "未在 doc108 简表；请打开接口页核对「积分」与是否单独权限"


def sidebar_mismatch_note(doc_id: str, index_label: str | None, sidebar_native: str | None) -> str:
    """数据索引锚文本与侧栏标题明显不一致时给一句注。"""
    if not index_label:
        return ""
    st = sidebar_native or ""
    if doc_id == "128" and "复权" in index_label and "复权" not in st:
        return "索引将「复权因子」指向 doc128，侧栏「复权因子」为 [doc28](https://tushare.pro/document/2?doc_id=28)；以侧栏与 `接口：` 为准。"
    if doc_id == "104":
        return "侧栏无 doc104；侧栏「沪深港通股票列表」为 [doc398](https://tushare.pro/document/2?doc_id=398)。索引链可能为历史页。"
    if doc_id == "31" and "停" in index_label:
        return "侧栏「每日停复牌信息」为 [doc214](https://tushare.pro/document/2?doc_id=214)。doc31 请以实际接口页为准。"
    if doc_id == "198":
        return "侧栏无 doc198；「涨跌停统计」类能力请对照 [doc298 涨跌停和炸板数据](https://tushare.pro/document/2?doc_id=298) 等现网条目。"
    return ""


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_md = root / "docs" / "TUSHARE_API_MASTER.zh.md"

    html2 = fetch(DOC2)
    titles = parse_sidebar_titles(html2)
    html108 = fetch(DOC108)
    doc108 = parse_doc108(html108)
    html290 = fetch(DOC290)
    html209 = fetch(DOC209)

    standalone_docs = set(re.findall(r"document/2\?doc_id=(\d+)", html290))
    standalone_docs.discard("291")
    for did, title in titles.items():
        if "分钟" in title or "Tick" in title or "tick" in title.lower():
            standalone_docs.add(did)

    chunk = parse_doc209_index_chunk(html209) or ""
    sections = parse_doc209_sections(chunk) if chunk else []
    index_first = first_label_per_doc(sections)
    index_doc_ids = set(index_first.keys())
    sidebar_ids = set(titles.keys())
    index_only_ids = sorted(index_doc_ids - sidebar_ids, key=int)

    merged_titles: dict[str, str] = dict(titles)
    for did in index_only_ids:
        merged_titles[did] = f"（仅数据索引 doc209）{index_first[did]}"

    lines: list[str] = []
    lines.append("# Tushare Pro 数据接口全量归类（积分类 / 独立类）")
    lines.append("")
    lines.append("> 自动生成说明：侧栏与 [数据索引 doc209](https://tushare.pro/document/2?doc_id=209) 正文摘要区由脚本抓取；**积分数值以各接口页与 [关于权限 doc108](https://tushare.pro/document/1?doc_id=108) / [腾讯积分明细表](https://docs.qq.com/sheet/DT0FIYUxYakJ5c1FF?tab=BB08J2) 为准**。")
    lines.append("> **独立权限**以 [积分与频次 doc290](https://tushare.pro/document/1?doc_id=290) 表二及接口页「单独开权限」为准；凡侧栏/索引词含「分钟」「Tick」等，一般属独立分钟/高频产品线。")
    lines.append(">")
    lines.append(
        f"> **数量**：侧栏不重复 `doc_id` **{len(sidebar_ids)}** 条；[数据索引](https://tushare.pro/document/2?doc_id=209) 正文摘要区另含侧栏未收录 **{len(index_only_ids)}** 个链（`{', '.join(index_only_ids)}`），合并入下方 **§4** 表。全页若含侧栏+索引去重共 **{len(sidebar_ids | index_doc_ids)}** 个 `doc_id`。"
    )
    lines.append(
        "> **边界**：不含 [document/1](https://tushare.pro/document/1) 平台说明文；粗分类不能替代账号在 [权限中心](https://tushare.pro/weborder/#/permission) 的实际开通。"
    )
    lines.append("")
    lines.append("## 1. 权限总规则（官方）")
    lines.append("")
    lines.append("- **积分类**：达到积分门槛即可调用（积分作门槛、一般不消耗）；档位与频次见 [doc290 表一](https://tushare.pro/document/1?doc_id=290)。")
    lines.append("- **独立类**：与积分无关，按产品单独开通（分钟、港美股、公告、新闻、`rt_k`、`stk_auction` 等）。详见 [doc290 表二](https://tushare.pro/document/1?doc_id=290)。")
    lines.append("")
    lines.append("| 类型（官方概括） | 文档入口 |")
    lines.append("|------------------|----------|")
    lines.append("| 股票历史/实时分钟、期货/期权分钟、申万分钟等 | [doc290 表二](https://tushare.pro/document/1?doc_id=290) |")
    lines.append("| A 股实时日线 `rt_k` | [doc372](https://tushare.pro/document/2?doc_id=372) |")
    lines.append("| 指数实时日线 | [doc403](https://tushare.pro/document/2?doc_id=403) |")
    lines.append("| 申万指数实时行情 | [doc417](https://tushare.pro/document/2?doc_id=417) |")
    lines.append("| ETF 实时日线 / 实时参考 | [doc400](https://tushare.pro/document/2?doc_id=400) / [doc454](https://tushare.pro/document/2?doc_id=454) |")
    lines.append("| 港股/美股日线与财报、实时等 | 表二内链 |")
    lines.append("| 新闻 / 公告 / 互动易 / 集合竞价 / 盘前股本 / 研报 / 政策法规等 | 表二内链 |")
    lines.append("")
    lines.append("## 2. 《关于权限》doc108 已列明的接口与最低积分（子集）")
    lines.append("")
    lines.append("| doc_id | API | 最低分值 | 说明（doc108 原文档标题） |")
    lines.append("|--------|-----|----------|-----------------------------|")
    pat108 = re.compile(
        r'document/2\?doc_id=(\d+)\">([^<]+)</a></td>\s*<td>([a-zA-Z0-9_]+)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>',
        re.S,
    )
    for doc_id, title108, api, desc, score in pat108.findall(html108):
        dsc = (desc or "").replace("|", "\\|").strip()
        lines.append(f"| {doc_id} | `{api}` | {score.strip()} | {title108.strip()}；{dsc} |")
    lines.append("")

    lines.append("## 3. 官方「数据索引」doc209 正文对照（相对侧栏）")
    lines.append("")
    lines.append(
        "以下自 [doc209](https://tushare.pro/document/2?doc_id=209) **「Tushare数据索引」标题之后**的正文解析；侧栏标题以 `/document/2` 侧栏为准。**粗分类**仍按 doc108/doc290 +「分钟」规则推断。"
    )
    lines.append("")
    if not sections:
        lines.append("（未能解析数据索引正文，请检查官网 HTML 结构是否变更。）")
    else:
        for sec, links in sections:
            lines.append(f"### {sec}")
            lines.append("")
            lines.append("| 索引锚文本 | doc_id | 侧栏同 id 标题 | 与侧栏/常识核对 | 粗分类 | 说明 |")
            lines.append("|------------|--------|----------------|------------------|--------|------|")
            for did, txt in links:
                txts = txt.replace("|", "\\|")
                side = titles.get(did, "—（侧栏无此 id）").replace("|", "\\|")
                note = sidebar_mismatch_note(did, txt, titles.get(did)).replace("|", "\\|")
                if did == "45" and "业绩快报" in txt:
                    note = (
                        "数据索引将「业绩快报」指向 doc45；侧栏「业绩预告」为 [doc45](https://tushare.pro/document/2?doc_id=45)、"
                        "「业绩快报」为 [doc46](https://tushare.pro/document/2?doc_id=46)。请以侧栏与接口页为准。"
                    )
                if did == "46" and "业绩预告" in txt:
                    note = (
                        "数据索引将「业绩预告」指向 doc46；侧栏对应关系见 [doc45](https://tushare.pro/document/2?doc_id=45) / [doc46](https://tushare.pro/document/2?doc_id=46)。请以侧栏与接口页为准。"
                    )
                disp = merged_titles.get(did, side)
                bucket, det = classify_row(did, disp, doc108, standalone_docs, txt)
                det = det.replace("|", "\\|")
                lines.append(f"| {txts} | {did} | {side} | {note or '—'} | {bucket} | {det} |")
            lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"## 4. 全量 `doc_id` 索引（侧栏 {len(sidebar_ids)} + 仅索引 {len(index_only_ids)} = {len(merged_titles)} 行）")
    lines.append("")
    lines.append("| doc_id | 展示标题 | 粗分类 | 说明 | 官方链接 |")
    lines.append("|--------|----------|--------|------|----------|")
    for doc_id in sorted(merged_titles, key=int):
        title = merged_titles[doc_id].replace("|", "\\|")
        idx_lab = index_first.get(doc_id)
        bucket, detail = classify_row(
            doc_id,
            merged_titles[doc_id],
            doc108,
            standalone_docs,
            idx_lab,
        )
        extra = ""
        if idx_lab and doc_id in titles:
            n = sidebar_mismatch_note(doc_id, idx_lab, titles[doc_id])
            if n:
                extra = "；" + n
        detail = (detail + extra).replace("|", "\\|")
        url = f"https://tushare.pro/document/2?doc_id={doc_id}"
        lines.append(f"| {doc_id} | {title} | {bucket} | {detail} | {url} |")
    lines.append("")
    lines.append("## 5. 维护")
    lines.append("")
    lines.append("- 重新生成：在项目根执行 `uv run python scripts/gen_tushare_api_master.py`。")
    lines.append("- 若 doc209 或侧栏 HTML 结构变更导致 §3 解析失败，需同步调整本脚本中的正则。")
    lines.append("")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", out_md, "merged rows", len(merged_titles), "index-only", index_only_ids)


if __name__ == "__main__":
    main()
