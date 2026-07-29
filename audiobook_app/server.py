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

from . import __version__
from .analyzer import HeuristicNovelAnalyzer
from .audio import build_render_plan, mp3_is_available, render_audiobook
from .epub import parse_epub
from .jobs import RenderJobManager, RenderJobNotFoundError
from .models import AnalysisResult
from .providers import (
    DashScopeTTSProvider,
    DemoToneProvider,
    MacOSLocalTTSProvider,
    NeuralVoicePackProvider,
    dashscope_tts_is_configured,
    macos_local_tts_is_available,
    neural_voice_pack_is_available,
)
from .qwen import QwenNovelAnalyzer, qwen_is_configured
from .registry import CharacterRegistry
from .voices import FREE_VOICE_IDS, catalog_as_dicts


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = PROJECT_ROOT / "web"
OUTPUT_ROOT = Path(
    os.getenv("APP_OUTPUT_DIR", str(PROJECT_ROOT / "data" / "outputs"))
).resolve()
CACHE_ROOT = Path(
    os.getenv("APP_TTS_CACHE_DIR", str(OUTPUT_ROOT / "_cache"))
).resolve()
MAX_REQUEST_BYTES = int(os.getenv("APP_MAX_REQUEST_BYTES", "2000000"))
MAX_EPUB_BYTES = int(os.getenv("APP_MAX_EPUB_BYTES", "20000000"))
MAX_ANALYZE_CHARACTERS = int(os.getenv("APP_MAX_ANALYZE_CHARACTERS", "50000"))
MAX_RENDER_CHARACTERS = int(os.getenv("APP_MAX_RENDER_CHARACTERS", "20000"))
MAX_RENDER_SEGMENTS = int(os.getenv("APP_MAX_RENDER_SEGMENTS", "120"))
MAX_PRIMARY_CHARACTERS = max(
    1,
    min(10, int(os.getenv("APP_MAX_PRIMARY_CHARACTERS", "10"))),
)
TTS_MAX_ATTEMPTS = int(os.getenv("APP_TTS_MAX_ATTEMPTS", "2"))
RENDER_JOB_WORKERS = max(
    1,
    min(4, int(os.getenv("APP_RENDER_JOB_WORKERS", "2"))),
)


def _optional_nonnegative_float(name: str) -> float | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


DASHSCOPE_PRICE_PER_10K_CNY = _optional_nonnegative_float(
    "DASHSCOPE_TTS_PRICE_PER_10K_CNY"
)


def _provider_for_name(name: str):
    if name == "demo":
        return DemoToneProvider()
    if name == "local":
        if not macos_local_tts_is_available():
            raise ValueError(
                "Mac 本地语音不可用；请安装中文系统声音，"
                "或改用浏览器试听 / 百炼 CosyVoice"
            )
        return MacOSLocalTTSProvider()
    if name == "neural":
        if not neural_voice_pack_is_available():
            raise ValueError(
                "免费 Neural 声线包尚未安装；请先运行 "
                "python3 -m pip install edge-tts miniaudio"
            )
        return NeuralVoicePackProvider()
    if name == "dashscope":
        if not dashscope_tts_is_configured():
            raise ValueError("尚未配置百炼 TTS 环境变量")
        return DashScopeTTSProvider()
    raise ValueError("未知 TTS 提供方")


class AudiobookHTTPServer(ThreadingHTTPServer):
    def server_close(self) -> None:
        manager = getattr(self, "render_job_manager", None)
        if manager is not None:
            manager.shutdown(wait=False)
        super().server_close()


class AudiobookRequestHandler(BaseHTTPRequestHandler):
    server_version = f"MultiVoiceAudiobook/{__version__}"

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

    def _read_body(self, max_bytes: int) -> bytes:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length 格式错误") from exc
        if content_length <= 0:
            raise ValueError("请求体不能为空")
        if content_length > max_bytes:
            raise ValueError("请求体过大")
        return self.rfile.read(content_length)

    def _read_json(self) -> dict[str, Any]:
        raw = self._read_body(MAX_REQUEST_BYTES)
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return value

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json({"status": "ok", "version": __version__})
            return
        if path == "/api/config":
            local_tts_ready = macos_local_tts_is_available()
            neural_tts_ready = neural_voice_pack_is_available()
            self._send_json(
                {
                    "analyzers": {
                        "auto": {
                            "ready": True,
                            "label": "自动识别（推荐）",
                            "selected": (
                                "qwen" if qwen_is_configured() else "local"
                            ),
                        },
                        "local": {"ready": True, "label": "本地规则（免费）"},
                        "qwen": {
                            "ready": qwen_is_configured(),
                            "label": "千问增强",
                        },
                    },
                    "providers": {
                        "browser": {
                            "ready": True,
                            "label": "设备自然试听（免费，不导出）",
                        },
                        "neural": {
                            "ready": neural_tts_ready,
                            "label": "免费 Neural 中文声线（联网）",
                            "detail": (
                                "五类精选中文角色声线，可试听、播放和导出"
                                if neural_tts_ready
                                else "安装 edge-tts 与 miniaudio 后启用"
                            ),
                            "experimental": True,
                            "install_command": (
                                "python3 -m pip install edge-tts miniaudio"
                            ),
                        },
                        "local": {
                            "ready": local_tts_ready,
                            "label": "Mac 本地中文语音（免费）",
                            "detail": (
                                "使用 Mac 已安装的中文系统声音，可播放和导出"
                                if local_tts_ready
                                else "仅在安装了中文系统声音的 Mac 上可用"
                            ),
                        },
                        "dashscope": {
                            "ready": dashscope_tts_is_configured(),
                            "label": "阿里云百炼 CosyVoice",
                        },
                    },
                    "voices": catalog_as_dicts(),
                    "voice_access": {
                        "free_voice_ids": sorted(FREE_VOICE_IDS),
                        "free_role_count": len(FREE_VOICE_IDS),
                        "premium_ready": dashscope_tts_is_configured(),
                    },
                    "formats": {
                        "wav": {"ready": True, "label": "WAV 无损"},
                        "mp3": {
                            "ready": mp3_is_available(),
                            "label": "MP3 128 kbps",
                        },
                    },
                    "limits": {
                        "analyze_characters": MAX_ANALYZE_CHARACTERS,
                        "epub_bytes": MAX_EPUB_BYTES,
                        "primary_characters": MAX_PRIMARY_CHARACTERS,
                        "render_characters": MAX_RENDER_CHARACTERS,
                        "render_segments": MAX_RENDER_SEGMENTS,
                    },
                    "imports": {
                        "txt": True,
                        "epub": True,
                        "voxcast_project": True,
                    },
                    "features": {
                        "pronunciation_dictionary": True,
                        "single_segment_render": True,
                        "book_projects": True,
                        "cross_chapter_characters": True,
                        "background_render_jobs": True,
                        "progressive_playback": True,
                        "render_pause_resume": True,
                        "refresh_job_recovery": True,
                        "neural_character_preview": True,
                        "voice_access_tiers": True,
                    },
                }
            )
            return
        if path.startswith("/api/render/jobs/"):
            job_id = path.removeprefix("/api/render/jobs/").strip("/")
            if "/" in job_id:
                self._send_json(
                    {"error": "not_found", "message": "接口不存在"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            try:
                self._send_json(self._job_manager().get_job(job_id))
            except RenderJobNotFoundError:
                self._send_json(
                    {"error": "not_found", "message": "生成任务不存在"},
                    HTTPStatus.NOT_FOUND,
                )
            except ValueError as exc:
                self._send_json(
                    {"error": "invalid_request", "message": str(exc)},
                    HTTPStatus.BAD_REQUEST,
                )
            return
        if path.startswith("/outputs/"):
            self._serve_output(path)
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/import/epub":
                raw = self._read_body(MAX_EPUB_BYTES)
                source_name = unquote(
                    self.headers.get("X-VoxCast-Filename", "book.epub")
                )
                self._handle_import_epub(raw, source_name)
                return

            payload = self._read_json()
            if path == "/api/analyze":
                self._handle_analyze(payload)
            elif path == "/api/render/plan":
                self._handle_render_plan(payload)
            elif path == "/api/render/segment":
                self._handle_render_segment(payload)
            elif path == "/api/render/jobs":
                self._handle_render_job_create(payload)
            elif path.startswith("/api/render/jobs/"):
                self._handle_render_job_action(path, payload)
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
        except RenderJobNotFoundError:
            self._send_json(
                {"error": "not_found", "message": "生成任务不存在"},
                HTTPStatus.NOT_FOUND,
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
        mode = str(payload.get("mode", "auto"))
        if mode == "auto":
            mode = "qwen" if qwen_is_configured() else "local"
        if mode == "qwen":
            analysis = QwenNovelAnalyzer().analyze(text)
        elif mode == "local":
            analysis = HeuristicNovelAnalyzer().analyze(text)
        else:
            raise ValueError("未知分析模式")
        registry = CharacterRegistry.from_dict(
            payload.get("character_registry"),
            default_limit=MAX_PRIMARY_CHARACTERS,
        )
        registry.reconcile(analysis)
        response = analysis.to_dict()
        response["character_registry"] = registry.to_dict()
        self._send_json(response)

    def _handle_import_epub(self, raw: bytes, source_name: str) -> None:
        if not source_name.casefold().endswith(".epub"):
            raise ValueError("请选择 EPUB 文件")
        project = parse_epub(raw, source_name)
        self._send_json(project.to_dict(), HTTPStatus.CREATED)

    def _handle_render_plan(self, payload: dict[str, Any]) -> None:
        analysis = AnalysisResult.from_dict(payload.get("analysis", {}))
        provider_name = str(payload.get("provider", "local"))
        provider = _provider_for_name(provider_name)
        plan = build_render_plan(
            analysis,
            provider,
            CACHE_ROOT,
            max_characters=MAX_RENDER_CHARACTERS,
            max_segments=MAX_RENDER_SEGMENTS,
            price_per_10k_cny=(
                DASHSCOPE_PRICE_PER_10K_CNY
                if provider_name == "dashscope"
                else 0.0
            ),
        )
        if provider_name == "dashscope":
            plan["note"] = (
                "只估算未命中缓存的字符与请求；实际费用以供应商账单为准。"
                if DASHSCOPE_PRICE_PER_10K_CNY is not None
                else "未配置每万字符单价；已估算未缓存字符与请求数，实际费用以供应商账单为准。"
            )
        elif provider_name == "neural":
            plan["note"] = (
                "使用免 Key 的在线 Neural 中文声线；不会产生 API 费用，"
                "但需要联网，服务可用性不作保证。"
            )
        elif provider_name == "local":
            plan["note"] = (
                "使用 Mac 已安装的中文系统声音，不消耗 API 额度；"
                "重复片段会直接复用缓存。"
            )
        else:
            plan["note"] = "内部音频管线检查不消耗 API 额度。"
        self._send_json(plan)

    def _handle_render(self, payload: dict[str, Any]) -> None:
        analysis = AnalysisResult.from_dict(payload.get("analysis", {}))
        if not analysis.segments:
            raise ValueError("没有可生成的脚本片段")
        provider_name = str(payload.get("provider", "local"))
        if provider_name == "dashscope" and payload.get("confirm_cost") is not True:
            raise ValueError("调用付费 TTS 前需要确认可能产生费用")
        provider = _provider_for_name(provider_name)
        output_format = str(payload.get("format", "wav")).lower()
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        result = render_audiobook(
            analysis,
            provider,
            OUTPUT_ROOT,
            max_characters=MAX_RENDER_CHARACTERS,
            max_segments=MAX_RENDER_SEGMENTS,
            cache_root=CACHE_ROOT,
            max_attempts=TTS_MAX_ATTEMPTS,
            output_format=output_format,
        )
        self._send_json(result, HTTPStatus.CREATED)

    def _handle_render_job_create(self, payload: dict[str, Any]) -> None:
        analysis = AnalysisResult.from_dict(payload.get("analysis", {}))
        if not analysis.segments:
            raise ValueError("没有可生成的脚本片段")
        provider_name = str(payload.get("provider", "local"))
        if provider_name == "dashscope" and payload.get("confirm_cost") is not True:
            raise ValueError("调用付费 TTS 前需要确认可能产生费用")
        output_format = str(payload.get("format", "wav")).lower()
        if output_format not in {"wav", "mp3"}:
            raise ValueError("输出格式只支持 WAV 或 MP3")
        if output_format == "mp3" and not mp3_is_available():
            raise ValueError("当前服务器未安装 ffmpeg，暂不能输出 MP3")
        provider = _provider_for_name(provider_name)
        build_render_plan(
            analysis,
            provider,
            CACHE_ROOT,
            max_characters=MAX_RENDER_CHARACTERS,
            max_segments=MAX_RENDER_SEGMENTS,
        )
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        job = self._job_manager().create_job(
            analysis,
            provider,
            provider_name=provider_name,
            output_format=output_format,
            max_characters=MAX_RENDER_CHARACTERS,
            max_segments=MAX_RENDER_SEGMENTS,
            max_attempts=TTS_MAX_ATTEMPTS,
            chapter_id=str(payload.get("chapter_id", "")),
            chapter_title=str(payload.get("chapter_title", "")),
        )
        self._send_json(job, HTTPStatus.ACCEPTED)

    def _handle_render_job_action(
        self, path: str, payload: dict[str, Any]
    ) -> None:
        del payload
        parts = path.strip("/").split("/")
        if len(parts) != 5 or parts[:3] != ["api", "render", "jobs"]:
            self._send_json(
                {"error": "not_found", "message": "接口不存在"},
                HTTPStatus.NOT_FOUND,
            )
            return
        job_id, action = parts[3], parts[4]
        if action == "pause":
            job = self._job_manager().pause_job(job_id)
        elif action == "resume":
            job = self._job_manager().resume_job(job_id)
        else:
            self._send_json(
                {"error": "not_found", "message": "接口不存在"},
                HTTPStatus.NOT_FOUND,
            )
            return
        self._send_json(job)

    def _job_manager(self) -> RenderJobManager:
        manager = getattr(self.server, "render_job_manager", None)
        if manager is None:
            manager = RenderJobManager(
                OUTPUT_ROOT,
                CACHE_ROOT,
                max_workers=RENDER_JOB_WORKERS,
            )
            setattr(self.server, "render_job_manager", manager)
        return manager

    def _handle_render_segment(self, payload: dict[str, Any]) -> None:
        analysis = AnalysisResult.from_dict(payload.get("analysis", {}))
        segment_id = str(payload.get("segment_id", "")).strip()
        if not segment_id:
            raise ValueError("缺少要重新生成的句子")
        selected_segment = next(
            (
                segment
                for segment in analysis.segments
                if segment.id == segment_id
            ),
            None,
        )
        if selected_segment is None:
            raise ValueError("找不到要重新生成的句子")

        provider_name = str(payload.get("provider", "local"))
        if provider_name == "dashscope" and payload.get("confirm_cost") is not True:
            raise ValueError("调用付费 TTS 前需要确认可能产生费用")
        provider = _provider_for_name(provider_name)
        single_analysis = AnalysisResult(
            characters=analysis.characters,
            segments=[selected_segment],
            analyzer=analysis.analyzer,
            pronunciations=analysis.pronunciations,
        )
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        result = render_audiobook(
            single_analysis,
            provider,
            OUTPUT_ROOT,
            max_characters=MAX_RENDER_CHARACTERS,
            max_segments=1,
            cache_root=CACHE_ROOT,
            max_attempts=TTS_MAX_ATTEMPTS,
            output_format="wav",
        )
        result["segment_id"] = selected_segment.id
        result["speaker_id"] = selected_segment.speaker_id
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
        private_roots = {"_cache", "_jobs"}
        first_part = relative.split("/", 1)[0]
        if first_part in private_roots:
            self._send_json(
                {"error": "not_found", "message": "输出文件不存在"},
                HTTPStatus.NOT_FOUND,
            )
            return
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
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("Content-Length", str(len(body)))
        if candidate.suffix in {".wav", ".mp3"}:
            self.send_header(
                "Content-Disposition", f'inline; filename="{candidate.name}"'
            )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[audiobook] {self.address_string()} - {format % args}")


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = AudiobookHTTPServer((host, port), AudiobookRequestHandler)
    print(f"MultiVoice Audiobook running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
