#!/usr/bin/env python3
"""server.py - 3DXML → FBX 本地转换服务（Flask）

无参数双击 exe 时的默认模式：在本机起一个 HTTP 服务并自动打开浏览器，
页面里拖入 .3dxml 即可转换、预览、下载 FBX。

端点：
  GET  /            web/index.html（上传/任务列表/预览界面）
  GET  /vendor/...  前端依赖（本地化 three.js 等，exe 离线可用）
  POST /convert     multipart 上传 .3dxml（字段 file，可选 relpath），返回 {ok,id,name,error}
  GET  /file/<id>   下载转换产物 .fbx（也供页面内 FBXLoader 预览加载）
  POST /zip         {ids:[...]} → 按 relpath 保持目录结构打包 zip 返回
  GET  /health      存活检查

线程模型：Flask threaded=True，但 bpy 非线程安全——所有转换经 CONVERT_LOCK
串行执行（前端也逐个提交，锁只是兜底）。会话文件写入临时目录，进程退出清理。
"""
import atexit
import io
import json
import shutil
import socket
import sys
import tempfile
import threading
import uuid
import webbrowser
import zipfile
from pathlib import Path

# Windows 控制台默认编码可能非 UTF-8，强制 stdout/stderr 用 UTF-8 避免中文乱码。
# 已包装过则跳过（重复包装会被 GC 关闭底层流）。
try:
    if (sys.stdout.encoding or "").lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

FROZEN = getattr(sys, "frozen", False) or "__compiled__" in globals()
# 冻结模式：web/ 等数据文件由 Nuitka 放在 exe 旁；开发模式：相对本文件。
BASE_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"

CONVERT_LOCK = threading.Lock()  # bpy 非线程安全：转换全局串行
SESSION_DIR = None               # 本次服务的临时目录（mkdtemp，退出清理）
TASKS = {}                       # id -> {fbx: Path, relpath: str, name: str}
TASKS_LOCK = threading.Lock()

app = None  # main() 中创建 Flask app（便于冻结模式下控制 import 时机）


def _cleanup_session():
    if SESSION_DIR and Path(SESSION_DIR).exists():
        shutil.rmtree(SESSION_DIR, ignore_errors=True)


def _json_error(message, status=400):
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False), status, \
        {"Content-Type": "application/json; charset=utf-8"}


def create_app():
    from flask import Flask, jsonify, request, send_file, send_from_directory

    global SESSION_DIR
    SESSION_DIR = Path(tempfile.mkdtemp(prefix="3dxml_fbx_"))
    atexit.register(_cleanup_session)

    flask_app = Flask(__name__, static_folder=None)

    @flask_app.get("/")
    def index():
        return send_file(WEB_DIR / "index.html")

    @flask_app.get("/vendor/<path:filename>")
    def vendor(filename):
        return send_from_directory(WEB_DIR / "vendor", filename)

    @flask_app.get("/<path:filename>")
    def web_static(filename):
        # web/ 下的静态资源（app.js/app.css/图标等）；send_from_directory 自带路径穿越防护
        return send_from_directory(WEB_DIR, filename)

    @flask_app.get("/health")
    def health():
        return jsonify({"ok": True})

    @flask_app.post("/convert")
    def convert_api():
        # 延迟 import：convert 模块在 setup_bpy_runtime() 之后才可用
        import convert as cli

        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return _json_error("缺少上传文件（字段 file）")
        filename = Path(upload.filename).name  # 剥掉浏览器可能附带的路径
        if not filename.lower().endswith(".3dxml"):
            return _json_error(f"仅支持 .3dxml 文件: {filename}")

        relpath = request.form.get("relpath", "").strip() or filename
        # relpath 仅用于 zip 内目录结构；清洗掉盘符/上级路径，防目录穿越
        rel_parts = [p for p in Path(relpath.replace("\\", "/")).parts
                     if p not in ("", ".", "..") and not p.endswith(":")]
        safe_rel = Path(*rel_parts) if rel_parts else Path(filename)

        task_id = uuid.uuid4().hex[:12]
        task_dir = SESSION_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        in_path = task_dir / filename
        out_path = task_dir / (Path(filename).stem + ".fbx")
        upload.save(str(in_path))

        with CONVERT_LOCK:
            ok = cli.convert_one(in_path, out_path)
            last_error = cli.LAST_ERROR

        if not ok or not out_path.exists():
            shutil.rmtree(task_dir, ignore_errors=True)
            return _json_error(f"转换失败: {filename}: {last_error or '未知错误'}", status=500)

        with TASKS_LOCK:
            TASKS[task_id] = {
                "fbx": out_path,
                "relpath": str(safe_rel.with_suffix(".fbx")).replace("\\", "/"),
                "name": filename,
            }
        return jsonify({
            "ok": True,
            "id": task_id,
            "name": filename,
            "size": out_path.stat().st_size,
        })

    @flask_app.get("/file/<task_id>")
    def file_api(task_id):
        with TASKS_LOCK:
            task = TASKS.get(task_id)
        if not task or not task["fbx"].exists():
            return _json_error("任务不存在或文件已清理", status=404)
        return send_file(task["fbx"], as_attachment=False,
                         download_name=task["fbx"].name,
                         mimetype="application/octet-stream")

    @flask_app.post("/zip")
    def zip_api():
        ids = (request.get_json(silent=True) or {}).get("ids", [])
        with TASKS_LOCK:
            tasks = [(tid, TASKS.get(tid)) for tid in ids]
        tasks = [(tid, t) for tid, t in tasks if t and t["fbx"].exists()]
        if not tasks:
            return _json_error("没有可打包的成功任务")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for tid, task in tasks:
                zf.write(task["fbx"], arcname=task["relpath"])
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name="fbx_export.zip",
                         mimetype="application/zip")

    return flask_app


def _pick_port(preferred):
    """preferred 为 0 或被占用时，让系统分配空闲端口。"""
    if preferred:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", preferred))
                return preferred
            except OSError:
                print(f"[warn] 端口 {preferred} 被占用，改用系统分配端口")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(host="127.0.0.1", port=0, open_browser=True):
    import convert as cli

    # 冻结模式直接 import bpy；开发模式必要时自动切到 Python 3.13。
    cli.ensure_python313()
    cli.setup_bpy_runtime()

    global app
    app = create_app()

    port = _pick_port(port)
    display_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    url = f"http://{display_host}:{port}/"
    print(f"[info] 转换服务已启动: {url}（监听 {host}:{port}）")
    if host == "0.0.0.0":
        print("[info] 局域网模式：其他设备访问 http://<本机IP>:%d/" % port)
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
