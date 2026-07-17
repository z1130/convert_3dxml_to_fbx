#!/usr/bin/env python3
"""tools/release.py - 一键发布脚本

用法：
  python tools/release.py v0.1.0
  python tools/release.py v0.1.0 --notes "修复了..."
  python tools/release.py v0.1.0 --skip-build --draft

前置要求：
  - 已安装 gh CLI 并登录（gh auth login）
  - 当前仓库有 origin 推送权限
  - 工作区干净（没有未提交改动）
  - 默认分支建议为 main（不是时会提示确认）
"""
import argparse
import io
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD_SCRIPT = ROOT / "tools" / "build.py"
DEFAULT_ZIP_NAME = "converter-{tag}-windows-x64"


def run(cmd, check=True, **kwargs):
    print(f"[run] {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, check=check, cwd=ROOT, **kwargs)


def ensure_utf8():
    """Windows 控制台默认编码可能非 UTF-8，强制 UTF-8 避免中文乱码。"""
    try:
        if (sys.stdout.encoding or "").lower() != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def parse_args():
    parser = argparse.ArgumentParser(description="一键发布 converter 到 GitHub Releases")
    parser.add_argument("tag", help="版本标签，例如 v0.1.0")
    parser.add_argument("--title", help="Release 标题，默认同 tag")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--notes", help="Release 说明文字")
    group.add_argument("--notes-file", help="Release 说明文件（Markdown）")
    parser.add_argument(
        "--zip-name",
        help="发布包文件名（不含 .zip），默认 converter-{tag}-windows-x64",
    )
    parser.add_argument("--skip-build", action="store_true", help="跳过 Nuitka 构建（使用已有 dist/）")
    parser.add_argument("--draft", action="store_true", help="创建草稿 Release")
    parser.add_argument("--prerelease", action="store_true", help="标记为预发布")
    parser.add_argument("--yes", "-y", action="store_true", help="不确认直接执行")
    return parser.parse_args()


def check_git(tag):
    """检查工作区干净、分支合适、标签不存在。"""
    result = run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if result.stdout.strip():
        print("[error] 工作区不干净，请先提交或清理：")
        print(result.stdout)
        sys.exit(1)

    branch = run(
        ["git", "branch", "--show-current"], capture_output=True, text=True
    ).stdout.strip()
    print(f"[info] 当前分支：{branch}")
    if branch != "main":
        ans = input("当前不是 main 分支，是否继续？[y/N]: ")
        if not ans.lower().startswith("y"):
            sys.exit(0)

    tags = run(["git", "tag", "--list", tag], capture_output=True, text=True).stdout.strip()
    if tags:
        print(f"[error] 标签 {tag} 已存在")
        sys.exit(1)

    # 检查分支是否有上游；没有也只是警告，不阻断
    upstream = run(
        ["git", "rev-parse", "--abbrev-ref", f"{branch}@{{u}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if upstream.returncode != 0:
        print(f"[warning] 当前分支没有上游远程分支，请确保能推送标签")


def check_gh():
    """检查 gh CLI 已安装且已登录。"""
    result = run(["gh", "--version"], check=False, capture_output=True)
    if result.returncode != 0:
        print("[error] 未找到 gh CLI，请先安装：https://cli.github.com/")
        sys.exit(1)

    result = run(["gh", "auth", "status"], check=False, capture_output=True)
    if result.returncode != 0:
        print("[error] gh CLI 未登录，请先运行：gh auth login")
        sys.exit(1)


def build():
    """调用 Nuitka 构建脚本。"""
    print("[info] 开始 Nuitka 构建，可能需要 10–30 分钟...")
    run([sys.executable, str(BUILD_SCRIPT)], check=True)
    if not (DIST / "converter.exe").exists():
        print("[error] 构建失败，未找到 dist/converter.exe")
        sys.exit(1)
    print("[ok] 构建完成")


def make_zip(tag, zip_name):
    """把 dist/ 压缩成发布包。"""
    name = zip_name or DEFAULT_ZIP_NAME.format(tag=tag)
    zip_path = ROOT / f"{name}.zip"
    if zip_path.exists():
        print(f"[info] 删除旧包 {zip_path.name}")
        zip_path.unlink()

    print(f"[info] 打包 {DIST} -> {zip_path.name}")
    shutil.make_archive(str(ROOT / name), "zip", root_dir=str(DIST))
    if not zip_path.exists():
        print("[error] 打包失败")
        sys.exit(1)
    print(f"[ok] 包已生成: {zip_path}")
    return zip_path


def tag_and_push(tag):
    """创建并推送标签。"""
    run(["git", "tag", "-a", tag, "-m", f"Release {tag}"], check=True)
    run(["git", "push", "origin", tag], check=True)
    print(f"[ok] 标签 {tag} 已推送")


def create_release(args, zip_path):
    """创建 GitHub Release 并上传 zip。"""
    tag = args.tag
    title = args.title or tag

    if args.notes_file:
        notes = Path(args.notes_file).read_text(encoding="utf-8")
    elif args.notes:
        notes = args.notes
    else:
        notes = ""

    # 检查是否已存在同名 release
    result = run(["gh", "release", "view", tag], check=False, capture_output=True)
    if result.returncode == 0:
        print(f"[error] GitHub Release {tag} 已存在")
        sys.exit(1)

    cmd = [
        "gh",
        "release",
        "create",
        tag,
        str(zip_path),
        "--title",
        title,
    ]
    if notes:
        cmd += ["--notes", notes]
    else:
        cmd += ["--generate-notes"]
    if args.draft:
        cmd.append("--draft")
    if args.prerelease:
        cmd.append("--prerelease")

    run(cmd, check=True)
    print(f"[ok] Release 发布完成：gh release view {tag}")


def main():
    ensure_utf8()
    args = parse_args()
    tag = args.tag

    if not tag.startswith("v"):
        print("[warn] 建议版本号以 v 开头，例如 v0.1.0")

    print(f"[info] 准备发布版本：{tag}")
    check_git(tag)
    check_gh()

    if not args.skip_build:
        build()
    else:
        if not (DIST / "converter.exe").exists():
            print("[error] 使用 --skip-build 但 dist/converter.exe 不存在")
            sys.exit(1)

    zip_path = make_zip(tag, args.zip_name)

    if not args.yes:
        ans = input(f"确认发布 {tag} 并上传 {zip_path.name}？[y/N]: ")
        if not ans.lower().startswith("y"):
            print("[info] 已取消")
            sys.exit(0)

    tag_and_push(tag)
    create_release(args, zip_path)


if __name__ == "__main__":
    main()
