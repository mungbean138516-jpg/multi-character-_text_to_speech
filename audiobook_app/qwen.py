from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from .analyzer import HeuristicNovelAnalyzer, _character_id
from .models import AnalysisResult, CharacterProfile
from .voices import cast_characters


def qwen_is_configured() -> bool:
    return bool(os.getenv("DASHSCOPE_API_KEY") and os.getenv("DASHSCOPE_LLM_BASE_URL"))


def _extract_json(value: str) -> dict[str, Any]:
    cleaned = value.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("模型没有返回 JSON 对象")
    return json.loads(cleaned[start : end + 1])


class QwenNovelAnalyzer:
    """Uses Qwen to enrich a deterministic segmentation result.

    The local analyzer always runs first. If the model call fails, callers can
    safely keep the local result instead of losing the whole demo.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.base_url = os.getenv("DASHSCOPE_LLM_BASE_URL", "").rstrip("/")
        self.model = os.getenv("DASHSCOPE_LLM_MODEL", "qwen3.7-flash")
        self.timeout = float(os.getenv("DASHSCOPE_TIMEOUT_SECONDS", "45"))

    def analyze(self, text: str) -> AnalysisResult:
        baseline = HeuristicNovelAnalyzer().analyze(text)
        if not self.api_key or not self.base_url:
            baseline.warnings.append("未配置千问 API，已自动使用本地规则分析")
            return baseline

        speaker_lookup = {
            character.id: character.name for character in baseline.characters
        }
        segment_rows = [
            {
                "id": segment.id,
                "kind": segment.kind,
                "text": segment.text,
                "current_speaker": speaker_lookup.get(segment.speaker_id, "未知"),
            }
            for segment in baseline.segments
            if segment.kind == "dialogue"
        ]
        prompt = {
            "task": (
                "你是中文小说配音导演。只根据原文证据识别每句对话的说话人，并推断"
                "角色性别、年龄段与声音特质。不要把不确定信息写成事实。"
            ),
            "rules": {
                "gender": ["female", "male", "neutral", "unknown"],
                "age_group": ["child", "teen", "adult", "elder", "unknown"],
                "speaker_assignments": "键为 segment id，值为角色姓名",
                "confidence": "0 到 1",
                "output": "只返回一个 JSON 对象，不要 Markdown",
            },
            "required_schema": {
                "characters": [
                    {
                        "name": "角色姓名或可区分的称谓",
                        "gender": "female|male|neutral|unknown",
                        "age_group": "child|teen|adult|elder|unknown",
                        "traits": ["最多4个简短中文声音特质"],
                        "confidence": 0.0,
                        "evidence": ["原文中的简短依据"],
                    }
                ],
                "speaker_assignments": {"seg_001": "角色姓名"},
                "warnings": ["仍需人工确认的歧义"],
            },
            "dialogues": segment_rows,
            "source_text": text,
        }
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你只输出严格 JSON。不得虚构原文不存在的人物信息。",
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt, ensure_ascii=False),
                },
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            enrichment = _extract_json(content)
            return self._merge(baseline, enrichment)
        except (KeyError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
            baseline.warnings.append(
                f"千问增强失败，已保留本地分析结果：{type(exc).__name__}"
            )
            return baseline

    @staticmethod
    def _merge(
        baseline: AnalysisResult, enrichment: dict[str, Any]
    ) -> AnalysisResult:
        narrator = baseline.characters[0]
        by_name: dict[str, CharacterProfile] = {
            character.name: character for character in baseline.characters[1:]
        }
        for item in enrichment.get("characters", []):
            name = str(item.get("name", "")).strip()
            if not name or name == "旁白":
                continue
            profile = by_name.get(name)
            if profile is None:
                profile = CharacterProfile(id=_character_id(name), name=name)
                by_name[name] = profile
            profile.gender = str(item.get("gender", profile.gender))
            profile.age_group = str(item.get("age_group", profile.age_group))
            profile.traits = [
                str(value) for value in item.get("traits", profile.traits)
            ][:4]
            profile.confidence = float(
                item.get("confidence", profile.confidence)
            )
            profile.evidence = [
                str(value)[:100]
                for value in item.get("evidence", profile.evidence)
            ][:4]
            profile.__post_init__()

        assignments = enrichment.get("speaker_assignments", {})
        by_segment = {segment.id: segment for segment in baseline.segments}
        for segment_id, speaker_name in assignments.items():
            segment = by_segment.get(str(segment_id))
            name = str(speaker_name).strip()
            if segment is None or not name or name == "旁白":
                continue
            profile = by_name.get(name)
            if profile is None:
                profile = CharacterProfile(
                    id=_character_id(name),
                    name=name,
                    traits=["待确认"],
                    confidence=0.4,
                )
                by_name[name] = profile
            segment.speaker_id = profile.id

        characters = [narrator, *by_name.values()]
        cast_characters(characters)
        warnings = [
            *baseline.warnings,
            *[str(item) for item in enrichment.get("warnings", [])],
        ]
        return AnalysisResult(
            characters=characters,
            segments=baseline.segments,
            analyzer="heuristic-v1 + qwen",
            warnings=list(dict.fromkeys(warnings)),
        )

