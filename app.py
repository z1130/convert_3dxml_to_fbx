#!/usr/bin/env python3
"""app.py - converter.exe 双模式入口

  converter.exe                          无参数 → Web 服务模式（默认 127.0.0.1:自动端口，自动开浏览器）
  converter.exe serve [--host H] [--port P] [--no-browser]
                                         显式服务模式；--host 0.0.0.0 即局域网模式
  converter.exe <其他参数>                → CLI 模式，等价于 python convert.py（参数原样透传）

开发模式同样适用：python app.py / python app.py serve / python app.py input.3dxml
"""
import argparse
import sys

# Windows 控制台默认编码可能非 UTF-8，强制 stdout/stderr 用 UTF-8 避免中文乱码。
# 已包装过（encoding=utf-8）则跳过，否则重复包装会让旧包装器被 GC 关闭底层流。
try:
    import io
    if (sys.stdout.encoding or "").lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def serve_main(argv):
    parser = argparse.ArgumentParser(
        prog="converter serve",
        description="以 Web 服务模式启动（浏览器界面转换 3DXML → FBX）",
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="监听地址（默认 127.0.0.1；0.0.0.0 为局域网模式）")
    parser.add_argument("--port", type=int, default=0,
                        help="监听端口（默认 0 = 自动选择空闲端口）")
    parser.add_argument("--no-browser", action="store_true",
                        help="启动后不自动打开浏览器")
    args = parser.parse_args(argv)

    import server
    server.main(host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "serve":
        return serve_main(argv[1:])
    if argv:
        # CLI 模式：参数原样交给 convert.main()
        import convert
        convert.main()
        return 0
    # 无参数：默认 Web 服务模式
    return serve_main([])


if __name__ == "__main__":
    sys.exit(main())
