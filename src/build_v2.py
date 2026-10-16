#!/usr/bin/env python3
"""构建两个 v2 包（容器元数据与原包一致）：
A) app-expanded-v2.rpk —— 内容 patch 版（新索引+新大小+版本 1.1.0）
B) app-original-repack-diag.rpk —— 诊断版：内容与原版逐字节相同，仅重打包。
   若 B 能装而 A 不能，问题在内容 patch；若 B 也崩，问题在打包容器/渠道。
"""
import hashlib
import io
import json
import sys
import zipfile

sys.path.insert(0, "src")
from patch_app import patch_index_js, bump_version
from repack_rpk import repack, build_cert_like_original


def make_cert(orig_cert: bytes, files: dict) -> bytes:
    digests = {n: hashlib.sha256(d).hexdigest() for n, d in files.items() if n != "META-INF/CERT"}
    hash_json = json.dumps({"algorithm": "SHA-256", "digests": digests}, separators=(",", ":"))
    return build_cert_like_original(orig_cert, hash_json)


def main(rpk_in, dic_path, out_a, out_b):
    zin = zipfile.ZipFile(rpk_in)
    files = {}
    for info in zin.infolist():
        if not info.filename.endswith("/"):
            files[info.filename] = zin.read(info.filename)
    orig_cert = files["META-INF/CERT"]
    dic_bytes = open(dic_path, "rb").read()

    # A: 内容 patch
    patched = dict(files)
    patched["pages/index/index.js"] = patch_index_js(
        files["pages/index/index.js"].decode("utf8"), dic_bytes).encode("utf8")
    for name in ("manifest.json", "manifest-watch.json", "app.js"):
        patched[name] = bump_version(files[name].decode("utf8")).encode("utf8")
    patched["META-INF/CERT"] = make_cert(orig_cert, patched)
    repack(rpk_in, {k: v for k, v in patched.items() if v != files[k]}, out_a)

    # B: 诊断版：不替换任何内容，纯容器重打包（内容与原包逐字节相同）
    repack(rpk_in, {}, out_b)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
