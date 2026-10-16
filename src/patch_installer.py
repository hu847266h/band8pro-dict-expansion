#!/usr/bin/env python3
"""把扩充版 dic 重新打包进「词库安装器」表盘.bin。

只改动三处，其余字节与原文件保持一致：
1. lua/dic block 的数据段替换为新词库，并更新其 block 头 3B 数据长度；
2. 文件表中 dic block 的 size，以及 dic 之后所有 block 的 offset（整体平移）；
3. dic 之后各 block 原样搬移（其 block 头与内容不变）。
表盘头、lua 脚本、图片 block 均不修改，安装流程（点cp 到
/data/quickapp/mass/com.givemefive.dic/dic.bin）不变。
"""
import struct
import sys

HEADER_TABLE = 0x110
RECORDS = 8


def parse(data: bytes):
    recs = []
    for i in range(RECORDS):
        tag, zero, off, size = struct.unpack(
            "<4I", data[HEADER_TABLE + i * 16: HEADER_TABLE + (i + 1) * 16])
        if off == 0:
            recs.append(None)
            continue
        dlen = int.from_bytes(data[off:off + 3], "little")
        nlen = data[off + 3]
        name = data[off + 20:off + 20 + nlen].decode("utf8")
        recs.append({"tag": tag, "off": off, "size": size, "dlen": dlen, "nlen": nlen,
                     "name": name, "raw": data[off:off + size]})
    return recs


def main(installer_in: str, dic_path: str, installer_out: str):
    data = open(installer_in, "rb").read()
    new_dic = open(dic_path, "rb").read()
    recs = parse(data)
    blocks = [r for r in recs if r]
    first_off = blocks[0]["off"]
    out = bytearray(data[:first_off])  # 头部原样（含文件表，后面回填）
    table_updates = {}
    for r in blocks:
        raw = r["raw"]
        if r["name"] == "lua/dic":
            hdr = bytearray(raw[:20])
            hdr[0:3] = len(new_dic).to_bytes(3, "little")
            raw = bytes(hdr) + raw[20:20 + r["nlen"]] + new_dic
        table_updates[r["name"]] = (len(out), len(raw))
        out += raw
    order = [r["name"] for r in blocks]
    for i, r in enumerate(recs):
        if not r:
            continue
        off, size = table_updates[r["name"]]
        struct.pack_into("<4I", out, HEADER_TABLE + i * 16, r["tag"], 0, off, size)
    open(installer_out, "wb").write(bytes(out))
    print(f"wrote {installer_out}: {len(data)} -> {len(out)} bytes; dic {blocks[1]['dlen']} -> {len(new_dic)}")
    assert order[1] == "lua/dic"


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
