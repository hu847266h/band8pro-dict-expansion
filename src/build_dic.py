#!/usr/bin/env python3
"""构建扩充版 dic.bin。

数据来源：
1. 原始词库（用户提供的安装器中提取，40013 条）——全部保留，不覆盖、不删除。
2. ECDICT（https://github.com/skywind3000/ECDICT，MIT License）——新增词条池：
   - 考试标签词：zk(中考)/gk(高考)/cet4/cet6/ky(考研)/toefl/ielts/gre
   - 或 BNC/COCA 词频排名 <= 20000（覆盖日常高频与次高频词），
     或牛津核心词（oxford=1），或柯林斯星级 >= 4
   （选池实测：原词库已有 4 万条，考试词与高频词大半已收录；放宽到 20000 名
    后新增词元约 9000 条，词库约 3.0MB，安装器约 3.9MB，兼顾覆盖与体积。）
3. 词形条目：由 ECDICT exchange 字段为新增词元生成过去式/过去分词/现在分词/
   第三人称单数/复数/比较级/最高级重定向条目，释义为「（词元 的X）+ 词元简释」，
   使手环端无需改查询算法即可查到常见词形（App 为前缀检索，词形条目独立成条）。

输出格式与原版完全一致：UTF-16LE（无 BOM），每条两行「单词\\n释义\\n」，
全表按 JS 字符串序（UTF-16 码元序；词面均为 ASCII，等价于 Python 默认序）严格排序。
严格排序同时修复原版约 1382 处乱序（短语/撇号词条错位会导致 App 提前停止扫描而漏查）。
"""
import csv
import json
import re
import sys

csv.field_size_limit(10 ** 9)

WORD_RE = re.compile(r"^[a-z][a-z' -]*[a-z]$|^[a-z]$")
EXAM_TAGS = {"zk", "gk", "cet4", "cet6", "ky", "toefl", "ielts", "gre"}
FREQ_LIMIT = 20000
DEF_CAP = 96
FORM_DEF_CAP = 64
MAX_FORMS = 8000
# ECDICT 对部分现代常用词没有词频/标签数据（如 smartphone 的 bnc/frq 均为 0），
# 用一小份人工核对的现代常用词清单强制纳入（ECDICT 有译文且原词库未收录时才生效）。
FORCE_WORDS = {
    "smartphone", "app", "wifi", "online", "website", "email", "blog", "emoji",
    "selfie", "screenshot", "upload", "login", "username", "password", "bluetooth",
    "laptop", "tablet", "software", "hardware", "download", "update", "install",
    "battery", "charger", "screen", "keyboard", "video", "photo", "camera",
    "internet", "data", "file", "folder", "music", "movie", "game", "sport",
}
FORM_LABEL = {
    "p": "过去式", "d": "过去分词", "i": "现在分词", "3": "第三人称单数",
    "s": "复数", "r": "比较级", "t": "最高级",
}


def clean_def(raw: str, cap: int) -> str:
    s = (raw or "").replace("\\n", ";").replace("\n", ";")
    s = s.split("[网络]")[0]
    s = re.sub(r"\s+", " ", s).strip(" ;")
    if len(s) > cap:
        cut = s.rfind(";", 0, cap)
        s = s[:cut] if cut >= 40 else s[:cap]
    return s.strip()


def rank_of(row) -> int:
    vals = []
    for key in ("bnc", "frq"):
        try:
            v = int(row[key] or 0)
        except ValueError:
            v = 0
        if v > 0:
            vals.append(v)
    return min(vals) if vals else 999999


def main(orig_dic_path: str, ecdict_csv: str, out_path: str, stats_path: str):
    raw = open(orig_dic_path, "rb").read()
    text = raw.decode("utf-16-le")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    orig_entries = list(zip(lines[0::2], lines[1::2]))
    orig_words = {w.strip().lower() for w, _ in orig_entries}
    print(f"original entries: {len(orig_entries)}")

    rows = list(csv.DictReader(open(ecdict_csv, encoding="utf8")))
    lemmas = {}  # word -> (def, rank, exchange)
    for row in rows:
        w = (row["word"] or "").strip().lower()
        if not WORD_RE.match(w) or len(w) > 32:
            continue
        if w in orig_words or w in lemmas:
            continue
        trans = clean_def(row["translation"] or "", DEF_CAP)
        if not trans:
            continue
        tags = set((row["tag"] or "").split())
        rank = rank_of(row)
        try:
            collins = int(row["collins"] or 0)
        except ValueError:
            collins = 0
        if not (tags & EXAM_TAGS or rank <= FREQ_LIMIT or row["oxford"] == "1" or collins >= 4
                or w in FORCE_WORDS):
            continue
        lemmas[w] = (trans, rank, row["exchange"] or "")
    print(f"new lemmas selected: {len(lemmas)}")

    forms = {}
    form_candidates = []
    for w, (trans, rank, exchange) in lemmas.items():
        for token in exchange.split("/"):
            if ":" not in token:
                continue
            kind, form = token.split(":", 1)
            form = form.strip().lower()
            if kind not in FORM_LABEL or not WORD_RE.match(form) or len(form) > 32:
                continue
            if form in orig_words or form in lemmas or form == w:
                continue
            form_candidates.append((rank, form, w, kind, trans))
    form_candidates.sort()
    for _rank, form, lemma, kind, trans in form_candidates[:MAX_FORMS]:
        if form in forms:
            continue
        note = f"（{lemma} 的{FORM_LABEL[kind]}）"
        forms[form] = (note + trans)[:FORM_DEF_CAP]
    print(f"form entries generated: {len(forms)}")

    entries = list(orig_entries)
    entries += [(w, d) for w, (d, _r, _e) in lemmas.items()]
    entries += list(forms.items())
    entries.sort(key=lambda kv: kv[0])  # 稳定排序：同词条目保持原始相对顺序且相邻
    out = "".join(f"{w}\n{d}\n" for w, d in entries).encode("utf-16-le")
    open(out_path, "wb").write(out)
    stats = {
        "orig_entries": len(orig_entries),
        "new_lemmas": len(lemmas),
        "form_entries": len(forms),
        "total_entries": len(entries),
        "dic_bytes": len(out),
    }
    json.dump(stats, open(stats_path, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
