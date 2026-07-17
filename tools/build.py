#!/usr/bin/env python3
"""tools/build.py - Nuitka 编译打包：产出自包含 dist/（免 Python、免 bpy 安装、无源码）

产物 dist/ 内含：
  converter.exe        双模式入口（无参数=Web 服务；serve=服务模式；其余=CLI）
  python 3.13 运行时 + bpy + flask（全部编译/打包，用户机器零依赖）
  web/                 界面与本地化 three.js 资源

构建机要求（仅打包者需要）：
  - Windows 10+，MSVC Build Tools（Nuitka 编译 C 代码用）
  - Python 3.13（与 vendor/ 的 cp313 wheel 匹配）
  - 依赖自动装进 vendor/：nuitka（flask 应已随 server 开发装好）

用法：
  python tools/build.py            # 完整构建（约 10-30 分钟）
然后把 dist/ 整个文件夹压缩发给用户。
"""
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Windows 控制台默认编码可能非 UTF-8，强制 stdout/stderr 用 UTF-8 避免中文乱码。
# 已包装过则跳过（重复包装会被 GC 关闭底层流）。
try:
    if (sys.stdout.encoding or "").lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor"
DIST = ROOT / "dist"
NUITKA_OUT = ROOT / "build" / "nuitka"
ENTRY = ROOT / "app.py"

sys.path.insert(0, str(ROOT))


def find_python313():
    """当前解释器即 3.13 则用之，否则复用 convert.find_python313 的探测链。"""
    if sys.version_info[:2] == (3, 13):
        return sys.executable
    from convert import find_python313 as detect
    py = detect()
    if not py:
        print("[error] 构建需要 Python 3.13（vendor/ 为 cp313 wheel），但未找到解释器")
        sys.exit(1)
    return py


def ensure_nuitka(py):
    """nuitka 不在 vendor/ 则自动安装（含 ordered-set/zstandard 依赖）。"""
    code = "import sys; sys.path.insert(0, r'%s'); import nuitka" % VENDOR
    if subprocess.run([py, "-c", code], capture_output=True).returncode == 0:
        print("[ok] nuitka 已就绪")
        return
    print("[run] 安装 nuitka 到 vendor/ ...")
    subprocess.run(
        [py, "-m", "pip", "install", "nuitka", "--target", str(VENDOR)],
        check=True,
    )


def build():
    py = find_python313()
    print(f"[info] 构建解释器: {py}")
    ensure_nuitka(py)

    if not (ROOT / "web" / "index.html").exists():
        print("[error] web/index.html 不存在，请先完成界面文件")
        sys.exit(1)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(VENDOR) + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [
        py, "-m", "nuitka",
        "--standalone",
        "--assume-yes-for-downloads",
        "--msvc=latest",
        f"--output-dir={NUITKA_OUT}",
        "--output-filename=converter.exe",
        # bpy：二进制扩展包（__init__.pyd + DLL + 5.1/ 数据），
        # package-data 负责把 DLL/数据按目录结构带进产物
        "--include-package=bpy",
        "--include-package-data=bpy",
        # bpy 运行时依赖（二进制 pyd 的 import 无法静态分析，显式带上）
        "--include-package=numpy",
        # Web 服务依赖
        "--include-package=flask",
        # 本项目模块（函数级 import，显式声明避免漏收）
        "--include-module=convert",
        "--include-module=server",
        "--include-package=converter",
        # 界面与本地化 three.js
        f"--include-data-dir={ROOT / 'web'}=web",
        str(ENTRY),
    ]
    print("[run] " + " ".join(cmd[2:]))
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)

    app_dist = NUITKA_OUT / "app.dist"
    if not app_dist.is_dir():
        print(f"[error] 未找到 Nuitka 产物: {app_dist}")
        sys.exit(1)

    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.move(str(app_dist), str(DIST))
    # 只随包用户手册（SETUP.md）；README.md 为仓库技术文档，不进分发包
    doc = ROOT / "SETUP.md"
    if doc.exists():
        shutil.copy2(doc, DIST / doc.name)

    print(f"\n[ok] 分发包已生成: {DIST}")
    print("     自包含（内置 Python 3.13 + bpy + Web 界面），压缩整个文件夹即可分发。")
    print("     请验证：converter.exe（服务模式）与 converter.exe input.3dxml（CLI 模式）")


if __name__ == "__main__":
    build()
