from __future__ import annotations

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .audio import render_audiobook
from .models import AnalysisResult
from .providers.base import TTSProvider


ACTIVE_JOB_STATUSES = {"queued", "running", "pausing"}
RESUMABLE_JOB_STATUSES = {"paused", "partial", "failed"}
JOB_ID_PATTERN = re.compile(r"[a-f0-9]{12}")


class RenderJobNotFoundError(LookupError):
    pass


@dataclass
class _RenderWork:
    analysis: AnalysisResult
    provider: TTSProvider
    output_format: str
    max_characters: int
    max_segments: int
    max_attempts: int
    pause_requested: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RenderJobManager:
    """Run chapter renders in the background and expose small public snapshots."""

    def __init__(
        self,
        output_root: Path,
        cache_root: Path,
        *,
        max_workers: int = 2,
    ) -> None:
        self.output_root = output_root.resolve()
        self.cache_root = cache_root.resolve()
        self.job_root = self.output_root / "_jobs"
        self.job_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._work: dict[str, _RenderWork] = {}
        self._active: set[str] = set()
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, min(int(max_workers), 4)),
            thread_name_prefix="voxcast-render",
        )
        self._load_snapshots()

    def create_job(
        self,
        analysis: AnalysisResult,
        provider: TTSProvider,
        *,
        provider_name: str,
        output_format: str = "wav",
        max_characters: int = 20_000,
        max_segments: int = 120,
        max_attempts: int = 2,
        chapter_id: str = "",
        chapter_title: str = "",
    ) -> dict[str, Any]:
        job_id = uuid4().hex[:12]
        created_at = _now()
        snapshot: dict[str, Any] = {
            "job_id": job_id,
            "status": "queued",
            "provider": provider_name,
            "format": output_format,
            "chapter_id": chapter_id[:120],
            "chapter_title": chapter_title[:200],
            "created_at": created_at,
            "updated_at": created_at,
            "started_at": None,
            "finished_at": None,
            "total_segments": len(analysis.segments),
            "completed_segments": 0,
            "failed_segments": [],
            "current_segment_index": 0,
            "progress_percent": 0,
            "playable_segments": [],
            "audio_url": None,
            "wav_url": None,
            "manifest_url": f"/outputs/{job_id}/manifest.json",
            "retryable": False,
            "resumable": True,
            "message": "任务已进入后台队列",
        }
        work = _RenderWork(
            analysis=analysis,
            provider=provider,
            output_format=output_format,
            max_characters=max_characters,
            max_segments=max_segments,
            max_attempts=max_attempts,
        )
        with self._lock:
            self._jobs[job_id] = snapshot
            self._work[job_id] = work
            self._persist_locked(job_id)
            self._submit_locked(job_id)
            return self._copy_locked(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        self._validate_job_id(job_id)
        with self._lock:
            if job_id not in self._jobs:
                raise RenderJobNotFoundError(job_id)
            return self._copy_locked(job_id)

    def pause_job(self, job_id: str) -> dict[str, Any]:
        self._validate_job_id(job_id)
        with self._lock:
            job = self._require_locked(job_id)
            work = self._work.get(job_id)
            if work is None:
                raise ValueError("服务重启后无法暂停这个旧任务")
            if job["status"] not in {"queued", "running", "pausing"}:
                raise ValueError("当前任务不在生成中")
            work.pause_requested = True
            job["status"] = "pausing"
            job["message"] = "当前句完成后暂停"
            job["updated_at"] = _now()
            self._persist_locked(job_id)
            return self._copy_locked(job_id)

    def resume_job(self, job_id: str) -> dict[str, Any]:
        self._validate_job_id(job_id)
        with self._lock:
            job = self._require_locked(job_id)
            work = self._work.get(job_id)
            if work is None:
                raise ValueError(
                    "服务重启后无法继续这个旧任务，请重新提交章节"
                )
            if job["status"] not in RESUMABLE_JOB_STATUSES:
                raise ValueError("当前任务不需要继续")
            if job_id in self._active:
                raise ValueError("任务仍在结束当前句，请稍后再继续")
            work.pause_requested = False
            job.update(
                {
                    "status": "queued",
                    "failed_segments": [],
                    "retryable": False,
                    "finished_at": None,
                    "message": "任务已重新进入后台队列",
                    "updated_at": _now(),
                }
            )
            self._persist_locked(job_id)
            self._submit_locked(job_id)
            return self._copy_locked(job_id)

    def shutdown(self, *, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=False)

    def _submit_locked(self, job_id: str) -> None:
        self._active.add(job_id)
        try:
            self._executor.submit(self._run_job, job_id)
        except Exception:
            self._active.discard(job_id)
            raise

    def _run_job(self, job_id: str) -> None:
        try:
            with self._lock:
                job = self._require_locked(job_id)
                work = self._work[job_id]
                job["status"] = (
                    "pausing" if work.pause_requested else "running"
                )
                job["started_at"] = job["started_at"] or _now()
                job["updated_at"] = _now()
                job["message"] = (
                    "等待当前句结束后暂停"
                    if work.pause_requested
                    else "正在后台逐句生成"
                )
                self._persist_locked(job_id)

            result = render_audiobook(
                work.analysis,
                work.provider,
                self.output_root,
                max_characters=work.max_characters,
                max_segments=work.max_segments,
                cache_root=self.cache_root,
                max_attempts=work.max_attempts,
                output_format=work.output_format,
                job_id=job_id,
                progress_callback=lambda event: self._record_progress(
                    job_id, event
                ),
                should_pause=lambda: self._pause_requested(job_id),
            )
            with self._lock:
                job = self._require_locked(job_id)
                status = str(result["status"])
                job.update(
                    {
                        "status": status,
                        "completed_segments": int(
                            result["completed_segments"]
                        ),
                        "total_segments": int(result["total_segments"]),
                        "failed_segments": list(
                            result.get("failed_segments", [])
                        ),
                        "playable_segments": list(
                            result.get("playable_segments", [])
                        ),
                        "audio_url": result.get("audio_url"),
                        "wav_url": result.get("wav_url"),
                        "manifest_url": result.get("manifest_url"),
                        "retryable": bool(result.get("retryable")),
                        "resumable": True,
                        "updated_at": _now(),
                    }
                )
                total = max(1, int(job["total_segments"]))
                job["progress_percent"] = round(
                    int(job["completed_segments"]) * 100 / total
                )
                if status == "completed":
                    job["finished_at"] = _now()
                    job["message"] = "章节音频已全部生成"
                elif status == "partial":
                    job["finished_at"] = _now()
                    job["message"] = "部分句子失败，可继续补齐"
                else:
                    job["finished_at"] = None
                    job["message"] = "任务已暂停，已完成内容仍可播放"
                self._persist_locked(job_id)
        except Exception as exc:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job.update(
                        {
                            "status": "failed",
                            "retryable": True,
                            "resumable": job_id in self._work,
                            "finished_at": _now(),
                            "updated_at": _now(),
                            "message": f"生成失败：{str(exc)[:240]}",
                        }
                    )
                    self._persist_locked(job_id)
        finally:
            with self._lock:
                self._active.discard(job_id)

    def _record_progress(
        self, job_id: str, event: dict[str, object]
    ) -> None:
        with self._lock:
            job = self._require_locked(job_id)
            job["status"] = (
                "pausing"
                if self._work[job_id].pause_requested
                else "running"
            )
            job["current_segment_index"] = int(
                event.get("current_index", 0)
            )
            job["total_segments"] = int(
                event.get("total_segments", job["total_segments"])
            )
            job["completed_segments"] = max(
                int(job["completed_segments"]),
                int(event.get("completed_segments", 0)),
            )
            playable = event.get("playable_segment")
            if isinstance(playable, dict):
                items = {
                    str(item["segment_id"]): item
                    for item in job["playable_segments"]
                }
                items[str(playable["segment_id"])] = dict(playable)
                job["playable_segments"] = sorted(
                    items.values(), key=lambda item: int(item["index"])
                )
            failure = event.get("failure")
            if isinstance(failure, dict):
                failures = {
                    str(item["segment_id"]): item
                    for item in job["failed_segments"]
                }
                failures[str(failure["segment_id"])] = dict(failure)
                job["failed_segments"] = list(failures.values())
            total = max(1, int(job["total_segments"]))
            job["progress_percent"] = round(
                int(job["completed_segments"]) * 100 / total
            )
            job["updated_at"] = _now()
            job["message"] = (
                "等待当前句结束后暂停"
                if job["status"] == "pausing"
                else (
                    f"已完成 {job['completed_segments']} / "
                    f"{job['total_segments']} 句"
                )
            )
            self._persist_locked(job_id)

    def _pause_requested(self, job_id: str) -> bool:
        with self._lock:
            work = self._work.get(job_id)
            return bool(work and work.pause_requested)

    def _load_snapshots(self) -> None:
        paths = sorted(self.job_root.glob("*.json"))[-100:]
        for path in paths:
            if not JOB_ID_PATTERN.fullmatch(path.stem):
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict) or value.get("job_id") != path.stem:
                continue
            if value.get("status") in ACTIVE_JOB_STATUSES:
                value["status"] = "interrupted"
                value["retryable"] = False
                value["resumable"] = False
                value["message"] = (
                    "服务曾重启；已生成片段仍可播放，请重新提交章节"
                )
            elif value.get("status") in RESUMABLE_JOB_STATUSES:
                value["resumable"] = False
                value["retryable"] = False
            self._jobs[path.stem] = value

    def _persist_locked(self, job_id: str) -> None:
        self.job_root.mkdir(parents=True, exist_ok=True)
        target = self.job_root / f"{job_id}.json"
        temporary = self.job_root / f".{job_id}.{uuid4().hex}.tmp"
        temporary.write_text(
            json.dumps(self._jobs[job_id], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, target)

    def _copy_locked(self, job_id: str) -> dict[str, Any]:
        return json.loads(
            json.dumps(self._jobs[job_id], ensure_ascii=False)
        )

    def _require_locked(self, job_id: str) -> dict[str, Any]:
        if job_id not in self._jobs:
            raise RenderJobNotFoundError(job_id)
        return self._jobs[job_id]

    @staticmethod
    def _validate_job_id(job_id: str) -> None:
        if not JOB_ID_PATTERN.fullmatch(job_id):
            raise ValueError("生成任务 ID 格式错误")
