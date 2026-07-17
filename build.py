#!/usr/bin/env python3
"""build.py - 把分发所需的文件整理到 dist/。

用户拿到的文件夹应只含运行所需脚本 + 文档，排除示例数据与开发产物。
config.json 生成空路径版（解绑作者本机路径，让用户机器上的 find_python313
走自动探测：环境变量 → PATH → 默认安装路径）。

注意：./pip（bpy 依赖，350MB+）不打包进 dist，用户需自行安装 bpy：
  "<Python313>/python.exe" -m pip install bpy --target=./pip

用法：
  python build.py
然后把 dist/ 整个文件夹发给用户。
"""
import io
import json
import shutil
import sys
from pathlib import Path

# Windows 控制台默认编码可能非 UTF-8，强制 stdout/stderr 用 UTF-8 避免中文乱码。
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

# 根目录下原样 copy 的文件
COPY_FILES = [
    "convert.py",
    "convert_3dxml_to_fbx.py",
    "diagnose_fbx_units.py",
    "README.md",
    "SETUP.md",
]

# 需要保持相对子目录结构 copy 的文件（convert.py 的 --verify 依赖 __test__/verify_fbx.py）
COPY_SUBFILES = [
    "__test__/verify_fbx.py",
]


def build():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    for rel in COPY_FILES:
        src = ROOT / rel
        if not src.exists():
            print(f"[warn] 源文件缺失，跳过: {rel}")
            continue
        shutil.copy2(src, DIST / rel)
        print(f"[copy] {rel}")

    for rel in COPY_SUBFILES:
        src = ROOT / rel
        if not src.exists():
            print(f"[warn] 源文件缺失，跳过: {rel}")
            continue
        dst = DIST / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"[copy] {rel}")

    # config.json：生成空路径版（不 copy 作者本机的配置）
    with open(DIST / "config.json", "w", encoding="utf-8") as f:
        json.dump({"python_path": ""}, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("[gen]  config.json (python_path 留空，走自动探测)")

    print(f"\n[ok] 分发包已生成: {DIST}")

if __name__ == "__main__":
    build()
