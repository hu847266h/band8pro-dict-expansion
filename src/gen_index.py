#!/usr/bin/env python3
"""为 dic.bin 生成手环端 App 需要的硬编码前缀索引（与 App 查询逻辑严格对应）。

App 的 getResultByWord 逻辑（反编译自 com.givemefive.dic v1.0.0）：
- 词长 >= 3：从 l[前两字母] 锚点开始顺序扫描；若第三字母 >= 'n' 且存在
  l[前两字母 + 'n'] 锚点，则改从该锚点开始（大桶中点加速）。
- 词长 == 2：从 l[两字母] 开始；词长 == 1：从 l[单字母] 开始（'a' 固定从 0）。
- 扫描按 UTF-16 码元逐个读，遇 \\n 切换词/释义；词行结束时若以查询词为前缀则
  收集（最多 4 条），若词 > 查询词则停止。因此索引值必须是条目起始字节偏移，
  且全表必须严格有序——本脚本按实际文件字节偏移生成并自检。
"""
import bisect
import json
import sys


def build_index(dic_bytes: bytes):
    text = dic_bytes.decode("utf-16-le")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    words = lines[0::2]
    defs = lines[1::2]
    offsets = []
    pos = 0
    for w, d in zip(words, defs):
        offsets.append(pos)
        pos += (len(w) + len(d) + 2) * 2
    assert pos == len(dic_bytes), (pos, len(dic_bytes))
    assert all(words[i] < words[i + 1] or words[i] == words[i + 1] for i in range(len(words) - 1))

    index = {}
    # 单字母与双字母锚点：第一个以该前缀开头的条目
    prefixes = set()
    for w in words:
        prefixes.add(w[:1])
        if len(w) >= 2:
            prefixes.add(w[:2])
    for p in prefixes:
        i = bisect.bisect_left(words, p)
        if i < len(words) and words[i].startswith(p):
            index[p] = offsets[i]
    # 三字母 *n 锚点：每个双字母桶内第一个以 xy+'n' 开头的条目
    for p in list(prefixes):
        if len(p) != 2:
            continue
        key = p + "n"
        i = bisect.bisect_left(words, key)
        if i < len(words) and words[i].startswith(key):
            index[key] = offsets[i]
    return index, len(words)


def to_js_literal(index: dict) -> str:
    # 键必须带引号：原词库含 "a "（a+空格）、"o'" 等非字母前缀，
    # 无引号写法在 JS 中是语法错误或会产生重复键（原版索引因此丢了这些锚点，
    # 以空格/撇号居次字开头的短语条目在原版中实际不可达）。
    items = ",".join(f"{json.dumps(k)}:{index[k]}" for k in sorted(index))
    return "{" + items + "}"


if __name__ == "__main__":
    dic = open(sys.argv[1], "rb").read()
    index, count = build_index(dic)
    print(f"entries {count}, anchors {len(index)}, dic size {len(dic)}")
    json.dump(index, open(sys.argv[2], "w"))
