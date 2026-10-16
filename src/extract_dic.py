#!/usr/bin/env python3
"""从「词库安装器」表盘 .bin 中提取原始 dic 词库，并校验其与手环端 App 内置索引的一致性。

安装器 .bin 结构（实测解析）：
- 0x000: 表盘头（magic 5A A5 34 12，ID 字符串、名称「词库安装器」等），头长 0x800
- 0x110: 文件表，8 条记录 × 16B：[0x050000NN][0][blockOffset][blockSize]
- 每个 block：[3B 数据长度 LE][1B 文件名长度][16B 零] + 文件名 + 数据
- 其中名为 lua/dic 的 block 数据即词库本体（安装器 Lua 脚本把它 cp 到
  /data/quickapp/mass/com.givemefive.dic/dic.bin）

App（com.givemefive.dic）读取 internal://mass/dic.bin，格式为 UTF-16LE 文本：
每条词条两行：单词行 + 释义行，均以 \\n 结尾，全表按单词排序。
"""
import struct
import sys

HEADER_TABLE = 0x110
RECORDS = 8


def parse_blocks(data: bytes):
    blocks = []
    for i in range(RECORDS):
        tag, _zero, off, size = struct.unpack("<4I", data[HEADER_TABLE + i * 16: HEADER_TABLE + (i + 1) * 16])
        if off == 0 or size == 0:
            continue
        dlen = int.from_bytes(data[off:off + 3], "little")
        nlen = data[off + 3]
        name = data[off + 20:off + 20 + nlen].decode("utf8")
        payload = data[off + 20 + nlen: off + 20 + nlen + dlen]
        assert len(payload) == dlen, (name, len(payload), dlen)
        assert off + size == off + 20 + nlen + dlen, (name, size, dlen, nlen)
        blocks.append({"name": name, "offset": off, "size": size, "data": payload})
    return blocks


def main(installer_path: str, out_path: str):
    data = open(installer_path, "rb").read()
    blocks = parse_blocks(data)
    for b in blocks:
        print(f"block {b['name']!r} @ {b['offset']} size {b['size']} payload {len(b['data'])}")
    dic = next(b for b in blocks if b["name"] == "lua/dic")
    open(out_path, "wb").write(dic["data"])
    text = dic["data"].decode("utf-16-le")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    words = lines[0::2]
    print(f"dic bytes: {len(dic['data'])}, entries: {len(words)}, first: {words[0]!r}, last: {words[-1]!r}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
