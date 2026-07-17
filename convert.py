#!/usr/bin/env python3
"""convert.py - 3DXML → FBX 一键转换（Unity + Three.js 双兼容）

使用 pip 安装的 bpy（位于本项目 ./vendor 目录，cp313 wheel），无需安装 Blender。

自动串行执行：
  1. 进程内调用 convert_3dxml_to_fbx.convert() 导出中间 FBX
  2. diagnose_fbx_units.patch 将 UnitScaleFactor 改为 100.0
     （Unity 按 USF/100 缩放视觉尺寸；Three.js 忽略该字段，故同一个 FBX
      在 Three.js 中按原始几何坐标显示，在 Unity 中视觉尺寸与 Three.js 一致）
  3. 可选：--verify 进程内回读验证

bpy wheel 仅支持 Python 3.13。若本进程不是 3.13，会自动查找 Python 3.13
解释器并重新执行自身（os.execv），用户无需手动指定解释器。

支持单文件转换或批量转换整个目录。
"""

import argparse
import io
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

# Windows 控制台默认编码可能不是 UTF-8，强制标准输出/错误使用 UTF-8，
# 避免中文提示显示为乱码。
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
PIP_DIR = SCRIPT_DIR / "vendor"

# 由 setup_bpy_runtime() 填充：进程内调用的转换/验证模块
_convert_module = None
_verify_module = None


def load_config():
    """读取 config.json（如果存在）。返回 dict。"""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"[error] 配置文件 {CONFIG_PATH} 格式错误: {e}")
            sys.exit(1)
    return {}


def find_python313():
    """按优先级查找 Python 3.13 解释器路径。"""
    # 1. 配置文件
    cfg = load_config()
    py = cfg.get("python_path")
    if py:
        py = Path(py).expanduser()
        if py.exists():
            return str(py)
        print(f"[warn] 配置文件中的 python_path 不存在: {py}")

    # 2. 环境变量
    py = os.environ.get("PYTHON313")
    if py:
        py = Path(py).expanduser()
        if py.exists():
            return str(py)
        print(f"[warn] PYTHON313 环境变量指向的路径不存在: {py}")

    # 3. PATH
    for name in ("python3.13.exe", "python3.13"):
        found = shutil.which(name)
        if found:
            return found

    # 4. 常见安装路径（Windows + Linux；不存在的会被 exists() 过滤）
    candidates = [
        # Windows
        Path.home() / "AppData/Local/Programs/Python/Python313/python.exe",
        Path("C:/Python313/python.exe"),
        Path("C:/Program Files/Python313/python.exe"),
        # Linux
        Path("/usr/bin/python3.13"),
        Path("/usr/local/bin/python3.13"),
        Path.home() / ".local/bin/python3.13",
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    return None


def ensure_python313():
    """bpy wheel 仅 cp313。若当前解释器不是 3.13，找到 3.13 并 execv 重启自身。"""
    if sys.version_info[:2] == (3, 13):
        return
    py = find_python313()
    if not py:
        print("[error] 加载 bpy 需要 Python 3.13，但找不到 Python 3.13 解释器。")
        print("        请按以下方式之一配置：")
        print(f"  1. 编辑 {CONFIG_PATH}，填写 python_path")
        print(f"  2. 设置 PYTHON313 环境变量")
        print(f"  3. 安装 Python 3.13 到默认路径")
        sys.exit(1)
    print(f"[info] 当前 Python {sys.version.split()[0]}，自动切换到 {py}")
    # execv 替换当前进程：新进程重新跑 convert.py，此时已是 3.13。
    os.execv(py, [py, str(SCRIPT_DIR / "convert.py")] + sys.argv[1:])


def setup_bpy_runtime():
    """加载 ./vendor 中的 bpy 及转换/验证模块。必须在 ensure_python313 之后调用。"""
    global _convert_module, _verify_module

    if not PIP_DIR.is_dir():
        print(f"[error] 未找到 bpy 安装目录: {PIP_DIR}")
        print("        请先在项目根目录安装 bpy：")
        print(f'          "<Python313>/python.exe" -m pip install bpy --target="{PIP_DIR.name}"')
        sys.exit(1)

    pip_str = str(PIP_DIR)
    if pip_str not in sys.path:
        sys.path.insert(0, pip_str)
    try:
        import bpy as _bpy
    except ImportError as e:
        print(f"[error] 加载 bpy 失败（{PIP_DIR}）: {e}")
        print("        bpy wheel 为 cp313，请确认当前解释器为 Python 3.13。")
        sys.exit(1)
    print(f"[info] bpy {_bpy.app.version_string} / python {sys.version.split()[0]}")

    # 转换/验证/补丁模块（converter 包，同目录）
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from converter import convert_3dxml_to_fbx as _c
    _convert_module = _c

    from converter import verify_fbx as _v
    _verify_module = _v

    # diagnose_fbx_units（纯 Python）——延迟到此处 import，
    # 与上方 SCRIPT_DIR 注入 sys.path 的逻辑一致。
    global patch_fbx
    from converter.diagnose_fbx_units import patch as patch_fbx  # noqa: E402


def collect_inputs(input_path, recursive=False):
    """根据输入路径收集所有待转换的 .3dxml 文件。"""
    if input_path.is_file():
        if input_path.suffix.lower() != ".3dxml":
            print(f"[error] 输入文件不是 .3dxml: {input_path}")
            sys.exit(1)
        return [input_path]

    if not input_path.is_dir():
        print(f"[error] 输入路径不存在: {input_path}")
        sys.exit(1)

    pattern = "**/*.3dxml" if recursive else "*.3dxml"
    files = sorted(input_path.glob(pattern))
    if not files:
        print(f"[warn] 目录中未找到 .3dxml 文件: {input_path}")
    return files


def resolve_output_for_batch(input_file, output_dir):
    """批量模式下确定单个输入文件的输出路径。"""
    if output_dir:
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / input_file.with_suffix(".fbx").name
    return input_file.with_suffix(".fbx")


def convert_one(in_path, out_path, no_patch=False, verify=False):
    """转换单个文件。成功返回 True，失败返回 False（不抛出，便于批量继续）。"""
    print(f"\n[info] input   = {in_path}")
    print(f"[info] output  = {out_path}")

    # 自动创建输出目录（包括单文件模式下的父目录）
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[error] 无法创建输出目录 {out_path.parent}: {e}")
        return False

    tmp_fbx = Path(tempfile.mktemp(suffix=".fbx"))
    try:
        # 1. 进程内导出中间 FBX
        print(f"[run] 导出 {tmp_fbx.name}")
        _convert_module.convert(str(in_path), str(tmp_fbx))

        # 2. patch USF=100（默认启用）——进程内调用 diagnose_fbx_units.patch。
        if not no_patch:
            print(f"[run] patch UnitScaleFactor → {out_path.name}")
            patch_fbx(str(tmp_fbx), str(out_path))
        else:
            shutil.move(str(tmp_fbx), str(out_path))
            print(f"[info] 已跳过 patch，直接复制到 {out_path}")

        print(f"[ok] 输出: {out_path}")

        # 3. 可选验证（进程内回读）
        if verify:
            print(f"[run] 回读验证 {out_path.name}")
            _verify_module.verify(str(out_path))
        return True
    except Exception as e:
        print(f"[error] 转换失败: {in_path}: {e}")
        traceback.print_exc()
        return False
    finally:
        if tmp_fbx.exists():
            tmp_fbx.unlink()


def main():
    parser = argparse.ArgumentParser(
        description="3DXML → FBX 一键转换（Unity + Three.js 双兼容，基于 pip 版 bpy）"
    )
    parser.add_argument(
        "input",
        help="输入 .3dxml 文件路径或包含 .3dxml 的目录",
    )
    parser.add_argument(
        "output",
        nargs="?",
        help="单文件模式下输出 .fbx 路径；批量模式下请用 -o/--output-dir",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        help="批量模式下指定输出目录",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="递归扫描子目录中的 .3dxml（仅对目录输入有效）",
    )
    parser.add_argument(
        "--no-patch",
        action="store_true",
        help="跳过 USF=100 patch（仅 Three.js 用，不兼容 Unity）",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="转换后回读验证",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="批量模式下单个文件失败后继续处理其他文件",
    )
    args = parser.parse_args()

    # bpy wheel 仅 cp313：必要时切换到 Python 3.13，然后加载 bpy 与子模块。
    ensure_python313()
    setup_bpy_runtime()

    input_path = Path(args.input).resolve()
    input_files = collect_inputs(input_path, recursive=args.recursive)
    if not input_files:
        sys.exit(0)

    # 单文件 / 批量模式校验
    is_batch = len(input_files) > 1 or input_path.is_dir()
    if is_batch and args.output:
        print("[error] 批量模式下第二个位置参数不可用，请用 -o/--output-dir 指定输出目录")
        sys.exit(1)

    # 单文件模式：output 为文件路径；批量模式：output 由 resolve_output_for_batch 决定
    if not is_batch:
        out_path = Path(args.output).resolve() if args.output else input_files[0].with_suffix(".fbx")
        ok = convert_one(
            input_files[0],
            out_path,
            no_patch=args.no_patch,
            verify=args.verify,
        )
        sys.exit(0 if ok else 1)

    # 批量模式
    total = len(input_files)
    successes = []
    failures = []
    start_all = time.monotonic()
    for idx, in_file in enumerate(input_files, 1):
        elapsed = time.monotonic() - start_all
        avg = elapsed / (idx - 1) if idx > 1 else 0
        remain = avg * (total - idx + 1)
        print(
            f"\n{'='*60}\n"
            f"[batch {idx}/{total}] {in_file.name}\n"
            f"  已用 {elapsed:.0f}s, 预计剩余 {remain:.0f}s\n"
            f"{'='*60}"
        )
        sys.stdout.flush()
        out_file = resolve_output_for_batch(in_file, args.output_dir)
        ok = convert_one(
            in_file,
            out_file,
            no_patch=args.no_patch,
            verify=args.verify,
        )
        if ok:
            successes.append(in_file)
        else:
            failures.append(in_file)
            if not args.continue_on_error:
                break

    total_elapsed = time.monotonic() - start_all
    print(f"\n[summary] 成功 {len(successes)} 个，失败 {len(failures)} 个，总耗时 {total_elapsed:.1f}s")
    if failures:
        for f in failures:
            print(f"  [fail] {f}")
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
