#!/usr/bin/env python3
"""convert.py - 3DXML → FBX 一键转换（Unity + Three.js 双兼容）

自动串行执行：
  1. Blender headless 运行 convert_3dxml_to_fbx.py 导出中间 FBX
  2. diagnose_fbx_units.py --patch 将 UnitScaleFactor 改为 100.0
     （Unity 按 USF/100 缩放视觉尺寸；Three.js 忽略该字段，故同一个 FBX
      在 Three.js 中按原始几何坐标显示，在 Unity 中视觉尺寸与 Three.js 一致）
  3. 可选：--verify 调用 Blender 回读验证

支持单文件转换或批量转换整个目录。
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
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
CONVERT_SCRIPT = SCRIPT_DIR / "convert_3dxml_to_fbx.py"
VERIFY_SCRIPT = SCRIPT_DIR / "__test__" / "verify_fbx.py"

# 把脚本目录加入 sys.path：Blender 以 `--python convert.py` 加载本脚本时，
# 脚本所在目录默认不在 sys.path 中，需显式加入才能 import 同目录模块。
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from diagnose_fbx_units import patch as patch_fbx  # noqa: E402

DEFAULT_BLENDER_PATHS = [
    r"E:\Blender\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
]


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


def find_blender():
    """按优先级查找 Blender 可执行文件路径。"""
    # 1. 配置文件
    cfg = load_config()
    blender = cfg.get("blender_path")
    if blender:
        blender = Path(blender).expanduser()
        if blender.exists():
            return str(blender)
        print(f"[warn] 配置文件中的 Blender 路径不存在: {blender}")

    # 2. 环境变量
    blender = os.environ.get("BLENDER")
    if blender:
        blender = Path(blender).expanduser()
        if blender.exists():
            return str(blender)
        print(f"[warn] BLENDER 环境变量指向的路径不存在: {blender}")

    # 3. PATH
    for name in ("blender.exe", "blender"):
        found = shutil.which(name)
        if found:
            return found

    # 4. 常见安装路径
    for p in DEFAULT_BLENDER_PATHS:
        if Path(p).exists():
            return p

    return None


def fail_no_blender():
    print("[error] 找不到 Blender。请按以下方式之一配置：")
    print(f"  1. 编辑 {CONFIG_PATH}，填写 blender_path（如 E:/Blender/blender.exe）")
    print(f"  2. 或设置 BLENDER 环境变量")
    sys.exit(1)


def run(cmd, *, need_shell=False, description=None):
    """运行外部命令，失败时打印并退出。"""
    desc = description or " ".join(str(c) for c in cmd)
    print(f"[run] {desc}")
    try:
        result = subprocess.run(
            [str(c) for c in cmd],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=need_shell,
        )
    except FileNotFoundError as e:
        print(f"[error] 命令未找到: {e}")
        sys.exit(1)

    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        print(f"[error] 命令失败 (exit {result.returncode}): {desc}")
        sys.exit(result.returncode)
    return result


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


def convert_one(in_path, out_path, blender, no_patch=False, verify=False):
    """转换单个文件。成功返回 True，失败返回 False。"""
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
        # 1. Blender 导出中间 FBX
        run(
            [
                blender,
                "--background",
                "--factory-startup",
                "--python",
                CONVERT_SCRIPT,
                "--",
                in_path,
                tmp_fbx,
            ],
            description=f"Blender 导出 {tmp_fbx.name}",
        )

        # 2. patch USF=100（默认启用）—— 进程内调用 diagnose_fbx_units.patch，
        #    无需系统 Python：用的是启动本脚本的解释器（系统 Python 或 Blender 皆可）。
        if not no_patch:
            print(f"[run] patch UnitScaleFactor → {out_path.name}")
            patch_fbx(str(tmp_fbx), str(out_path))
        else:
            shutil.move(str(tmp_fbx), str(out_path))
            print(f"[info] 已跳过 patch，直接复制到 {out_path}")

        print(f"[ok] 输出: {out_path}")

        # 3. 可选验证
        if verify:
            run(
                [
                    blender,
                    "--background",
                    "--factory-startup",
                    "--python",
                    VERIFY_SCRIPT,
                    "--",
                    out_path,
                ],
                description=f"Blender 回读验证 {out_path.name}",
            )
        return True
    except SystemExit as e:
        # run() 失败时调用 sys.exit，这里捕获并记为失败
        if e.code != 0:
            print(f"[error] 转换失败: {in_path}")
            return False
        raise
    finally:
        if tmp_fbx.exists():
            tmp_fbx.unlink()


def main():
    parser = argparse.ArgumentParser(
        description="3DXML → FBX 一键转换（Unity + Three.js 双兼容）"
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
        help="转换后使用 Blender 回读验证",
    )
    parser.add_argument(
        "--blender",
        help="临时指定 Blender 可执行文件路径（仅本次生效）",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="批量模式下单个文件失败后继续处理其他文件",
    )
    # 兼容两种启动：系统 Python（`python convert.py ...`）与 Blender
    # （`blender --python convert.py -- ...`）。后者 sys.argv 含 Blender 自身参数，
    # 需取 '--' 之后的参数。
    raw_argv = sys.argv
    args = parser.parse_args(
        raw_argv[raw_argv.index('--') + 1:] if '--' in raw_argv else raw_argv[1:]
    )

    input_path = Path(args.input).resolve()
    input_files = collect_inputs(input_path, recursive=args.recursive)
    if not input_files:
        sys.exit(0)

    # 单文件 / 批量模式校验
    is_batch = len(input_files) > 1 or input_path.is_dir()
    if is_batch and args.output:
        print("[error] 批量模式下第二个位置参数不可用，请用 -o/--output-dir 指定输出目录")
        sys.exit(1)

    blender = args.blender
    if not blender:
        blender = find_blender()
    if not blender:
        fail_no_blender()
    blender = Path(blender).resolve()
    print(f"[info] blender = {blender}")

    # 单文件模式：output 为文件路径；批量模式：output 由 resolve_output_for_batch 决定
    if not is_batch:
        out_path = Path(args.output).resolve() if args.output else input_files[0].with_suffix(".fbx")
        ok = convert_one(
            input_files[0],
            out_path,
            blender,
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
            blender,
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
