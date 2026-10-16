#!/usr/bin/env python3
"""按原包的 ZIP 容器元数据重打包 RPK（v2 修复版）。

背景：v1 用 Python zipfile 默认参数打包（create_system=3、无目录条目、
1980 时间戳、默认文件属性），与原包（create_system=0、带目录条目、
构建时间戳）差异较大。内容级校验（JS 语法、hash.json 摘要）均已证明无误，
故 v2 逐项克隆原条目的 ZipInfo 元数据，只替换文件内容，排除容器层差异。

用法：repack_rpk.py <原RPK> <替换文件目录或-> <输出RPK>
替换文件以同名路径文件形式给出（pages/index/index.js 等），由调用方准备。
"""
import io
import sys
import zipfile


def clone_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    z = zipfile.ZipInfo(info.filename, info.date_time)
    z.compress_type = info.compress_type
    z.create_system = info.create_system
    z.create_version = info.create_version
    z.extract_version = info.extract_version
    z.internal_attr = info.internal_attr
    z.external_attr = info.external_attr
    z.volume = info.volume
    z.flag_bits = info.flag_bits & ~0x08  # 不使用数据描述符，与原包一致
    return z


def repack(rpk_in: str, replacements: dict, rpk_out: str):
    zin = zipfile.ZipFile(rpk_in)
    with zipfile.ZipFile(rpk_out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = b"" if info.filename.endswith("/") else zin.read(info.filename)
            if info.filename in replacements:
                data = replacements[info.filename]
            zout.writestr(clone_info(info), data)
            # zipfile.writestr 会把 external_attr==0 强制改成 0o600<<16；
            # 中央目录在 close 时按 filelist 写出，这里改回原值保持与原包一致。
            zout.filelist[-1].external_attr = info.external_attr
    print(f"repacked -> {rpk_out}")


def build_cert_like_original(orig_cert_bytes: bytes, hash_json: str) -> bytes:
    """按原 CERT 内条目的元数据重建只含 hash.json 的 CERT zip。"""
    cz = zipfile.ZipFile(io.BytesIO(orig_cert_bytes))
    info = cz.infolist()[0]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(clone_info(info), hash_json)
        z.filelist[-1].external_attr = info.external_attr
    return buf.getvalue()


if __name__ == "__main__":
    print("library module; use build_v2.py")
