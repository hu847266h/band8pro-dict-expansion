#!/usr/bin/env python3
"""按手环端 App 的真实算法逐字节模拟查询，验证扩充词库「在 App 里能查到」，
而不仅是「文件生成成功」。

模拟对象：com.givemefive.dic index 页的 g/m/f 函数与 getResultByWord 路由：
- readArrayBuffer 以 200 个 UTF-16 码元为一块按需加载、缓存；
- 逐码元扫描，码元 10(\\n) 切换词/释义；词行完成时以 startsWith 收集（上限 4）；
- 当前词 > 查询词时立即停止；索引路由见 gen_index.py 说明。
"""
import bisect
import json
import random
import sys
import time

CHUNK_UNITS = 200


class AppSim:
    def __init__(self, dic_bytes: bytes, index: dict):
        self.buf = dic_bytes
        self.size = len(dic_bytes)
        self.index = index
        self.cache = {}
        self.units_read = 0

    def _load(self, pos_units_from: int):
        start_byte = pos_units_from
        end_byte = min(start_byte + CHUNK_UNITS * 2, self.size - 2 if self.size >= 2 else 0)
        for byte in range(start_byte, end_byte, 2):
            self.cache[byte] = self.buf[byte] | (self.buf[byte + 1] << 8)
            self.units_read += 1

    def _search(self, start: int, word: str):
        results = []
        idx = start
        word_str = ""
        content_str = ""
        word_flag = True
        search_end = False
        reload_flag = False
        guard = 0
        while not search_end:
            guard += 1
            if guard > 5_000_000:
                raise RuntimeError("search did not terminate")
            t = self.cache.get(idx)
            if t is None:
                if not reload_flag:
                    reload_flag = True
                    self.cache = {}
                    self._load(idx)
                    continue
                search_end = True
                break
            reload_flag = False
            if t == 0:
                search_end = True
            else:
                idx += 2
                if t == 10:
                    word_flag = not word_flag
                    if word_flag:
                        if word_str.startswith(word):
                            results.append((word_str, content_str))
                            if len(results) >= 4:
                                search_end = True
                        elif word_str > word:
                            search_end = True
                        word_str = ""
                        content_str = ""
                elif word_flag:
                    word_str += chr(t)
                else:
                    content_str += chr(t)
        return results

    def query(self, word: str):
        self.cache = {}
        if len(word) >= 3:
            two = word[:2]
            if two not in self.index:
                return []
            start = self.index[two]
            three = two + "n"
            if word[2] >= "n" and three in self.index:
                start = self.index[three]
            return self._search(start, word)
        if word == "a":
            return self._search(0, word)
        if word not in self.index:
            return []
        return self._search(self.index[word], word)


def load_entries(dic_bytes: bytes):
    text = dic_bytes.decode("utf-16-le")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return list(zip(lines[0::2], lines[1::2]))


def main(dic_path, index_json, orig_dic_path, report_path):
    from gen_index import build_index
    dic_bytes = open(dic_path, "rb").read()
    index, _ = build_index(dic_bytes)
    if index_json != "-":
        index = json.load(open(index_json))
    entries = load_entries(dic_bytes)
    words = [w for w, _ in entries]
    sim = AppSim(dic_bytes, index)
    report = {"dic_bytes": len(dic_bytes), "entries": len(entries), "tests": {}}

    def found(word):
        res = sim.query(word)
        return any(k == word for k, _v in res), res

    # T1 原词库回归：随机抽样 800 词 + 每个双字母桶首词，必须精确命中
    orig_entries = load_entries(open(orig_dic_path, "rb").read())
    orig_words = [w for w, _ in orig_entries]
    rng = random.Random(42)
    sample = rng.sample(orig_words, 800)
    bucket_first = {}
    for w in orig_words:
        bucket_first.setdefault(w[:2], w)
    t1_set = list(dict.fromkeys(sample + list(bucket_first.values())))
    t1_fail = [w for w in t1_set if not found(w)[0]]
    report["tests"]["T1_orig_regression"] = {"checked": len(t1_set), "fail": t1_fail[:20]}

    # T2 新词抽查：原词库没有、扩充版必须命中（含实测缺失的常见词）
    must_have = ["student", "deadline", "feedback", "download", "smartphone", "serendipity",
                 "including", "organisation", "theatre", "media", "homework", "deadlines"]
    orig_set = set(orig_words)
    t2 = {w: found(w)[0] for w in must_have if w not in orig_set}
    report["tests"]["T2_new_words"] = t2

    # T3 词形条目抽查
    t3_words = [w for w, d in entries if " 的" in d and "）" in d][:5000]
    t3_sample = rng.sample(t3_words, min(200, len(t3_sample := t3_words)))
    t3_fail = [w for w in t3_sample if not found(w)[0]]
    report["tests"]["T3_word_forms"] = {"pool": len(t3_words), "checked": len(t3_sample), "fail": t3_fail[:20]}

    # T4 不存在的词不崩溃且返回空
    t4 = {}
    for w in ["zzzzqqq", "qqzxwv", "notawordreallyxyz", "学生x"]:
        try:
            t4[w] = sim.query(w) if all(ord(c) < 0x2E80 or True for c in w) else "skip"
        except Exception as e:  # noqa
            t4[w] = f"ERROR {e}"
    report["tests"]["T4_nonexistent"] = {k: (v if v == "skip" else len(v)) for k, v in t4.items()}

    # T5 多词性/多义：抽查释义含 ';' 的条目结果完整性（App 返回的 v 与文件一致）
    multi = [w for w, d in entries if d.count(";") >= 2][:2000]
    t5_sample = rng.sample(multi, 100)
    t5_fail = []
    for w in t5_sample:
        ok, res = found(w)
        expect = dict(entries).get(w)
        got = next((v for k, v in res if k == w), None)
        if not ok or got != expect:
            t5_fail.append(w)
    report["tests"]["T5_multi_sense"] = {"checked": len(t5_sample), "fail": t5_fail[:10]}

    # T6 乱码/格式：严格解码、无替换字符、释义不含换行（行式格式前提）
    bad = [w for w, d in entries if "�" in w + d]
    report["tests"]["T6_encoding"] = {"replacement_char_entries": len(bad)}

    # T7 英美变体对
    pairs = [("colour", "color"), ("centre", "center"), ("organise", "organize"),
             ("theatre", "theater"), ("traveller", "traveler"), ("favourite", "favorite")]
    report["tests"]["T7_variants"] = {f"{a}/{b}": (found(a)[0], found(b)[0]) for a, b in pairs}

    # T8 性能：模拟扫描码元数分布（近似设备端读取量）
    probe = rng.sample(words, 300)
    units = []
    t0 = time.time()
    for w in probe:
        sim.units_read = 0
        before = sim.units_read
        sim.query(w)
        units.append(sim.units_read)
    elapsed = time.time() - t0
    units.sort()
    report["tests"]["T8_scan_units"] = {
        "queries": len(probe), "median": units[len(units) // 2],
        "p95": units[int(len(units) * 0.95)], "max": units[-1],
        "sim_seconds_for_300": round(elapsed, 2),
    }
    # bisect 对照：索引锚点正确性（每个锚点落在以其为前缀的条目上）
    anch_bad = 0
    offs = []
    pos = 0
    for w, d in entries:
        offs.append(pos)
        pos += (len(w) + len(d) + 2) * 2
    for key, off in index.items():
        i = bisect.bisect_left(offs, off)
        if i >= len(entries) or not words[i].startswith(key):
            anch_bad += 1
    report["tests"]["T9_anchor_alignment"] = {"anchors": len(index), "bad": anch_bad}

    json.dump(report, open(report_path, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
