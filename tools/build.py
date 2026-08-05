#!/usr/bin/env python3
"""tools/build.py - Nuitka 编译打包：产出自包含 dist/（免 Python、免 bpy 安装、无源码）

产物 dist/ 内含：
  converter.exe        双模式入口（无参数=Web 服务；serve=服务模式；其余=CLI）
  python 3.13 运行时 + bpy + flask（全部编译/打包，用户机器零依赖）
  web/                 界面与本地化 three.js 资源

构建机要求（仅打包者需要）：
  - Windows 10+，MSVC Build Tools（Nuitka 编译 C 代码用）
  - Python 3.13（与 vendor/ 的 cp313 wheel 匹配）
  - 依赖版本钉在根目录 requirements.txt（bpy/flask/nuitka），缺失时按它自动装进 vendor/

用法：
  python tools/build.py            # 完整构建（约 10-30 分钟），版本 0.0.0-dev
然后把 dist/ 整个文件夹压缩发给用户。
"""
import io
import os
import re
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
    """nuitka 不在 vendor/ 则按 requirements.txt 的钉版安装（与 CI 产物一致）。"""
    code = "import sys; sys.path.insert(0, r'%s'); import nuitka" % VENDOR
    if subprocess.run([py, "-c", code], capture_output=True).returncode == 0:
        print("[ok] nuitka 已就绪")
        return
    print("[run] 按 requirements.txt 安装依赖到 vendor/ ...")
    subprocess.run(
        [py, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt"), "--target", str(VENDOR)],
        check=True,
    )


def build():
    py = find_python313()
    print(f"[info] 构建解释器: {py}")
    ensure_nuitka(py)

    # 版本号唯一来源是 git tag：CI 注入 CONVERTER_VERSION（tag 名），本地构建
    # 未设置时标 dev。生成 _version.py，编译进产物供 convert 运行时引用。
    version = os.environ.get("CONVERTER_VERSION", "0.0.0-dev").lstrip("v")
    (ROOT / "_version.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    # Windows 版本资源要求最多 4 段纯数字（dev 版本提取数字部分，如 0.0.0-dev → 0.0.0.0）
    nums = re.findall(r"\d+", version)
    file_version = ".".join((nums + ["0", "0", "0", "0"])[:4])
    print(f"[info] 版本: {version} (exe 元数据 {file_version})")

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
    ]
    # exe 文件属性中的版本信息（右键 -> 属性 -> 详细信息）只在 CI 正式构建写入：
    # 写 exe 资源会被本机杀软实时防护锁定（实测腾讯电脑管家 QQPCRTP 锁 75MB 新 exe，
    # Nuitka 报 "Failed to add resources" 直接 FATAL）。本地 dev 构建版本号无意义，
    # 跳过即可正常出包；CLI --version / 启动横幅 / 版本角标来自 _version.py，不受影响。
    if os.environ.get("CONVERTER_VERSION"):
        cmd += [
            "--product-name=3DXML to FBX Converter",
            f"--file-version={file_version}",
            f"--product-version={file_version}",
            "--file-description=3DXML to FBX Converter (Three.js / Unity compatible)",
        ]
    cmd += [
        # bpy：二进制扩展包（__init__.pyd + DLL + 5.1/ 数据），
        # package-data 负责把 DLL/数据按目录结构带进产物
        "--include-package=bpy",
        "--include-package-data=bpy",
        # bpy 运行时依赖（二进制 pyd 的 import 无法静态分析，显式带上）
        "--include-package=numpy",
        # bpy 5.2 自带 addons_core/bl_pkg 插件在 register() 时 import cattrs
        # （bpy 内部脚本以数据形式拷贝，其 import 不被 Nuitka 静态分析跟踪），
        # 缺了会在用户机器启动时打 "Exception in module register()" 警告。
        "--include-package=cattrs",
        "--include-package=attrs",
        # Web 服务依赖（waitress 为函数级 import，显式带上）
        "--include-package=flask",
        "--include-package=waitress",
        # 本项目模块（函数级 import，显式声明避免漏收）
        "--include-module=convert",
        "--include-module=server",
        "--include-module=_version",
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
    # 只随包用户手册（docs/SETUP.md → dist 根目录）；DEVELOPMENT.md 为仓库技术文档，不进分发包
    doc = ROOT / "docs" / "SETUP.md"
    if doc.exists():
        shutil.copy2(doc, DIST / doc.name)

    print(f"\n[ok] 分发包已生成: {DIST}")
    print("     自包含（内置 Python 3.13 + bpy + Web 界面），压缩整个文件夹即可分发。")
    print("     请验证：converter.exe（服务模式）与 converter.exe input.3dxml（CLI 模式）")


if __name__ == "__main__":
    build()
