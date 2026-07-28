from __future__ import annotations

import json
import mimetypes
import os
import posixpath
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .analyzer import HeuristicNovelAnalyzer
from .audio import render_audiobook
from .models import AnalysisResult
from .providers import (
    DashScopeTTSProvider,
    DemoToneProvider,
    dashscope_tts_is_configured,
)
from .qwen import QwenNovelAnalyzer, qwen_is_configured
from .voices import catalog_as_dicts


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = PROJECT_ROOT / "web"
OUTPUT_ROOT = Path(
    os.getenv("APP_OUTPUT_DIR", str(PROJECT_ROOT / "data" / "outputs"))
).resolve()
MAX_REQUEST_BYTES = int(os.getenv("APP_MAX_REQUEST_BYTES", "2000000"))
MAX_ANALYZE_CHARACTERS = int(os.getenv("APP_MAX_ANALYZE_CHARACTERS", "50000"))
MAX_RENDER_CHARACTERS = int(os.getenv("APP_MAX_RENDER_CHARACTERS", "20000"))


class AudiobookRequestHandler(BaseHTTPRequestHandler):
    server_version = "MultiVoiceAudiobook/0.1"

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; media-src 'self' blob:; connect-src 'self'",
        )

    def _send_json(
        self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise ValueError("请求体不能为空")
        if content_length > MAX_REQUEST_BYTES:
            raise ValueError("请求体过大")
        raw = self.rfile.read(content_length)
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return value

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json({"status": "ok", "version": "0.1.0"})
            return
        if path == "/api/config":
            self._send_json(
                {
                    "analyzers": {
                        "local": {"ready": True, "label": "本地规则（免费）"},
                        "qwen": {
                            "ready": qwen_is_configured(),
                            "label": "千问增强",
                        },
                    },
                    "providers": {
                        "browser": {
                            "ready": True,
                            "label": "浏览器试听（免费，不导出）",
                        },
                        "demo": {
                            "ready": True,
                            "label": "离线音频流水线检测",
                        },
                        "dashscope": {
                            "ready": dashscope_tts_is_configured(),
                            "label": "阿里云百炼 CosyVoice",
                        },
                    },
                    "voices": catalog_as_dicts(),
                    "limits": {
                        "analyze_characters": MAX_ANALYZE_CHARACTERS,
                        "render_characters": MAX_RENDER_CHARACTERS,
                    },
                }
            )
            return
        if path.startswith("/outputs/"):
            self._serve_output(path)
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/analyze":
                self._handle_analyze(payload)
            elif path == "/api/render/plan":
                self._handle_render_plan(payload)
            elif path == "/api/render":
                self._handle_render(payload)
            else:
                self._send_json(
                    {"error": "not_found", "message": "接口不存在"},
                    HTTPStatus.NOT_FOUND,
                )
        except json.JSONDecodeError:
            self._send_json(
                {"error": "invalid_json", "message": "JSON 格式错误"},
                HTTPStatus.BAD_REQUEST,
            )
        except ValueError as exc:
            self._send_json(
                {"error": "invalid_request", "message": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
        except RuntimeError as exc:
            self._send_json(
                {"error": "provider_error", "message": str(exc)},
                HTTPStatus.BAD_GATEWAY,
            )
        except Exception as exc:  # defensive boundary for a live demo
            self._send_json(
                {
                    "error": "internal_error",
                    "message": f"服务端错误：{type(exc).__name__}",
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _handle_analyze(self, payload: dict[str, Any]) -> None:
        text = str(payload.get("text", "")).strip()
        if not text:
            raise ValueError("请先粘贴小说文本")
        if len(text) > MAX_ANALYZE_CHARACTERS:
            raise ValueError(f"单次最多分析 {MAX_ANALYZE_CHARACTERS} 个字符")
        mode = str(payload.get("mode", "local"))
        if mode == "qwen":
            analysis = QwenNovelAnalyzer().analyze(text)
        elif mode == "local":
            analysis = HeuristicNovelAnalyzer().analyze(text)
        else:
            raise ValueError("未知分析模式")
        self._send_json(analysis.to_dict())

    def _handle_render_plan(self, payload: dict[str, Any]) -> None:
        analysis = AnalysisResult.from_dict(payload.get("analysis", {}))
        provider = str(payload.get("provider", "demo"))
        characters = sum(len(segment.text) for segment in analysis.segments)
        if characters > MAX_RENDER_CHARACTERS:
            raise ValueError(f"单次最多生成 {MAX_RENDER_CHARACTERS} 个字符")
        self._send_json(
            {
                "provider": provider,
                "segments": len(analysis.segments),
                "billable_characters": characters,
                "note": (
                    "实际费用以供应商控制台为准；每个片段会产生一次 TTS 请求。"
                    if provider == "dashscope"
                    else "离线检测不消耗 API 额度。"
                ),
            }
        )

    def _handle_render(self, payload: dict[str, Any]) -> None:
        analysis = AnalysisResult.from_dict(payload.get("analysis", {}))
        if not analysis.segments:
            raise ValueError("没有可生成的脚本片段")
        provider_name = str(payload.get("provider", "demo"))
        if provider_name == "demo":
            provider = DemoToneProvider()
        elif provider_name == "dashscope":
            if not dashscope_tts_is_configured():
                raise ValueError("尚未配置百炼 TTS 环境变量")
            if payload.get("confirm_cost") is not True:
                raise ValueError("调用付费 TTS 前需要确认可能产生费用")
            provider = DashScopeTTSProvider()
        else:
            raise ValueError("未知 TTS 提供方")
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        result = render_audiobook(
            analysis,
            provider,
            OUTPUT_ROOT,
            max_characters=MAX_RENDER_CHARACTERS,
        )
        self._send_json(result, HTTPStatus.CREATED)

    def _serve_static(self, request_path: str) -> None:
        clean = posixpath.normpath(unquote(request_path)).lstrip("/")
        if clean in {"", "."}:
            clean = "index.html"
        candidate = (WEB_ROOT / clean).resolve()
        if WEB_ROOT.resolve() not in candidate.parents and candidate != WEB_ROOT.resolve():
            self._send_json(
                {"error": "forbidden", "message": "非法路径"},
                HTTPStatus.FORBIDDEN,
            )
            return
        if not candidate.is_file():
            self._send_json(
                {"error": "not_found", "message": "页面不存在"},
                HTTPStatus.NOT_FOUND,
            )
            return
        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {
            "application/javascript",
            "application/json",
        }:
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_output(self, request_path: str) -> None:
        relative = posixpath.normpath(unquote(request_path[len("/outputs/") :]))
        candidate = (OUTPUT_ROOT / relative).resolve()
        if OUTPUT_ROOT not in candidate.parents or not candidate.is_file():
            self._send_json(
                {"error": "not_found", "message": "输出文件不存在"},
                HTTPStatus.NOT_FOUND,
            )
            return
        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if candidate.suffix == ".wav":
            self.send_header(
                "Content-Disposition", f'inline; filename="{candidate.name}"'
            )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[audiobook] {self.address_string()} - {format % args}")


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), AudiobookRequestHandler)
    print(f"MultiVoice Audiobook running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

