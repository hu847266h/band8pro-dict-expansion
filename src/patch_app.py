#!/usr/bin/env python3
"""把新索引与新词库大小 patch 进手环端 App 的 RPK，并重建 META-INF/CERT 的 hash.json。

- pages/index/index.js：替换硬编码总大小 r（原 1690316）与索引对象字面量 l。
- manifest.json / manifest-watch.json / app.js 内嵌清单：版本 1.0.0/2 -> 1.1.0/3，
  以便与原版区分并走覆盖安装。
- META-INF/CERT 是只含 hash.json 的 ZIP（SHA-256 清单）；重算全部文件摘要后重打包。
  注意：hash.json 不是带私钥的签名，无法伪造原作者签名身份；此举仅保持原包的
  完整性清单结构与内容一致。设备/工具是否校验签名以实测为准（见报告）。
"""
import hashlib
import io
import json
import re
import sys
import zipfile

from gen_index import build_index, to_js_literal

OLD_SIZE = "1690316"


def patch_index_js(src: str, dic_bytes: bytes) -> str:
    assert src.count(OLD_SIZE) == 1
    index, _count = build_index(dic_bytes)
    i = src.find(OLD_SIZE)
    seg = src[i:]
    start = seg.find("{")
    depth = 0
    end = None
    for j, ch in enumerate(seg[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = j
                break
    new_seg = seg[:start] + to_js_literal(index) + seg[end + 1:]
    return src[:i] + str(len(dic_bytes)) + new_seg[len(OLD_SIZE):]


def extract_index(src: str, size_str: str) -> dict:
    """从 index.js 中按对象字面量边界提取索引（供验证使用，避免全文件正则误匹配）。"""
    i = src.find(size_str)
    assert i >= 0
    seg = src[i:]
    start = seg.find("{")
    depth = 0
    end = None
    for j, ch in enumerate(seg[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = j
                break
    obj = seg[start:end + 1]
    pairs = re.findall(r'"([^"]+)":(\d+)|([a-z]+):(\d+)', obj)
    return {a or c: int(b or d) for a, b, c, d in pairs}


def bump_version(text: str) -> str:
    text = text.replace('"versionName":"1.0.0"', '"versionName":"1.1.0"')
    text = text.replace('"versionName": "1.0.0"', '"versionName": "1.1.0"')
    text = text.replace('"versionCode":2', '"versionCode":3')
    text = text.replace('"versionCode": 2', '"versionCode": 3')
    return text


def main(rpk_in: str, dic_path: str, rpk_out: str):
    dic_bytes = open(dic_path, "rb").read()
    zin = zipfile.ZipFile(rpk_in)
    files = {}
    order = []
    for info in zin.infolist():
        if info.filename.endswith("/"):
            continue
        files[info.filename] = zin.read(info.filename)
        order.append(info.filename)

    idx = files["pages/index/index.js"].decode("utf8")
    files["pages/index/index.js"] = patch_index_js(idx, dic_bytes).encode("utf8")
    for name in ("manifest.json", "manifest-watch.json", "app.js"):
        files[name] = bump_version(files[name].decode("utf8")).encode("utf8")

    digests = {
        name: hashlib.sha256(data).hexdigest()
        for name, data in files.items()
        if name != "META-INF/CERT"
    }
    hash_json = json.dumps({"algorithm": "SHA-256", "digests": digests}, separators=(",", ":"))
    cert_buf = io.BytesIO()
    with zipfile.ZipFile(cert_buf, "w", zipfile.ZIP_DEFLATED) as cz:
        cz.writestr("hash.json", hash_json)
    files["META-INF/CERT"] = cert_buf.getvalue()

    with zipfile.ZipFile(rpk_out, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in order:
            zout.writestr(name, files[name])
    print(f"wrote {rpk_out}: index anchors regenerated, size const -> {len(dic_bytes)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
