from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


EMOTION_AXES = {
    "neutral": (0, 20, 50),
    "happy": (70, 65, 60),
    "sad": (-70, 30, 25),
    "angry": (-60, 90, 75),
    "excited": (45, 85, 65),
    "questioning": (0, 40, 45),
}


def direct_text(text: str, kind: str = "dialogue") -> dict[str, Any]:
    pace, energy, pause, emotion, score = 1.0, 0.45, 260, "neutral", 0.55
    reasons: list[str] = []
    exclamations = text.count("！") + text.count("!")
    if exclamations:
        energy += min(0.35, exclamations * 0.1)
        pace += 0.06
        reasons.append("感叹号提高强度")
    short_sentences = [part for part in re.split(r"[。！？!?]+", text) if part.strip()]
    if len(short_sentences) >= 3 and sum(map(len, short_sentences)) / len(short_sentences) <= 8:
        pace += 0.1
        pause -= 70
        reasons.append("连续短句加快节奏")
    rules = (
        (("低声说道", "轻声说", "低声说"), -0.12, -0.18, 80, "restrained", "低声表达"),
        (("怒吼", "吼道", "咆哮"), 0.16, 0.35, -80, "angry", "怒吼提高强度和语速"),
        (("沉默片刻", "停顿片刻", "良久"), -0.05, -0.08, 300, "restrained_sadness", "沉默增加停顿"),
    )
    for markers, pace_delta, energy_delta, pause_delta, target, reason in rules:
        if any(marker in text for marker in markers):
            pace += pace_delta
            energy += energy_delta
            pause += pause_delta
            emotion = target
            score += 0.12
            reasons.append(reason)
    if kind == "narration" and len(text) >= 80:
        pace -= 0.1
        pause += 100
        reasons.append("长段描写放慢旁白")
    valence, arousal, dominance = EMOTION_AXES.get(emotion, (0, round(energy * 100), 50))
    return {
        "pace": round(max(0.65, min(1.35, pace)), 2),
        "energy": round(max(0.0, min(1.0, energy)), 2),
        "pause_after_ms": max(80, min(1200, pause)),
        "emotion": emotion,
        "confidence": round(min(0.95, score), 2),
        "valence": valence,
        "arousal": arousal,
        "dominance": dominance,
        "reasons": reasons or ["使用中性朗读基线"],
    }


def consistency_check(chapters: list[dict[str, Any]]) -> dict[str, Any]:
    snapshots: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chapter_index, chapter in enumerate(chapters):
        analysis = chapter.get("analysis") or {}
        for character in analysis.get("characters", []):
            if character.get("id") == "narrator":
                continue
            key = str(character.get("id") or character.get("name", "")).strip()
            if key:
                snapshots[key].append({
                    "chapter_id": str(chapter.get("id", chapter_index)),
                    "chapter_title": str(chapter.get("title", f"第 {chapter_index + 1} 章")),
                    "character": character,
                })
    issues = []
    fields = (("gender", "性别呈现"), ("age_group", "年龄段"), ("voice_id", "声音"))
    for character_id, entries in snapshots.items():
        name = str(entries[0]["character"].get("name", character_id))
        for field, label in fields:
            values = defaultdict(list)
            for entry in entries:
                value = str(entry["character"].get(field, "") or "unknown")
                if value not in {"", "unknown"}:
                    values[value].append(entry["chapter_title"])
            if len(values) > 1:
                issues.append({
                    "severity": "high" if field == "voice_id" else "medium",
                    "character_id": character_id,
                    "character_name": name,
                    "field": field,
                    "message": f"{name}的{label}在章节间发生变化",
                    "variants": [
                        {"value": value, "chapters": titles}
                        for value, titles in values.items()
                    ],
                })
        trait_sets = {
            tuple(sorted(map(str, entry["character"].get("traits", []))))
            for entry in entries
            if entry["character"].get("traits")
        }
        if len(trait_sets) > 1:
            issues.append({
                "severity": "low",
                "character_id": character_id,
                "character_name": name,
                "field": "traits",
                "message": f"{name}的人物特征描述不一致",
                "variants": [{"value": "、".join(value), "chapters": []} for value in trait_sets],
            })
    return {
        "status": "issues_found" if issues else "consistent",
        "checked_chapters": len(chapters),
        "checked_characters": len(snapshots),
        "issue_count": len(issues),
        "issues": issues,
    }
