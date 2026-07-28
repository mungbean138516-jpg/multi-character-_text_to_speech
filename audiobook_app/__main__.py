from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analyzer import HeuristicNovelAnalyzer
from .qwen import QwenNovelAnalyzer
from .server import run_server
from .textio import read_text_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="自动识别小说角色并生成多角色听书脚本"
    )
    subparsers = parser.add_subparsers(dest="command")
    serve = subparsers.add_parser("serve", help="启动本地网页")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    analyze = subparsers.add_parser(
        "analyze", help="分析 UTF-8、UTF-16 或 GB18030 文本文件"
    )
    analyze.add_argument("path", type=Path)
    analyze.add_argument("--qwen", action="store_true", help="启用千问增强")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command in {None, "serve"}:
        run_server(
            getattr(args, "host", "127.0.0.1"),
            getattr(args, "port", 8000),
        )
        return
    if args.command == "analyze":
        text = read_text_file(args.path).text
        analyzer = QwenNovelAnalyzer() if args.qwen else HeuristicNovelAnalyzer()
        print(json.dumps(analyzer.analyze(text).to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
