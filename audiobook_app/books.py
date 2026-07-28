from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import AnalysisResult
from .registry import CharacterRegistry


PROJECT_SCHEMA = "voxcast-book-project"
PROJECT_VERSION = 1
MAX_PROJECT_CHAPTERS = 500
MAX_PROJECT_CHARACTERS = 5_000_000


@dataclass
class BookChapter:
    id: str
    title: str
    text: str
    source_path: str = ""
    analysis: AnalysisResult | None = None

    def __post_init__(self) -> None:
        self.id = self.id.strip()
        self.title = self.title.strip() or "未命名章节"
        self.text = self.text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not self.id:
            raise ValueError("章节缺少 ID")
        if not self.text:
            raise ValueError(f"“{self.title}”没有可朗读文字")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "text": self.text,
            "source_path": self.source_path,
            "analysis": self.analysis.to_dict() if self.analysis else None,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BookChapter":
        raw_analysis = value.get("analysis")
        return cls(
            id=str(value["id"]),
            title=str(value.get("title", "未命名章节")),
            text=str(value["text"]),
            source_path=str(value.get("source_path", "")),
            analysis=(
                AnalysisResult.from_dict(raw_analysis)
                if isinstance(raw_analysis, dict)
                else None
            ),
        )


@dataclass
class BookProject:
    title: str
    chapters: list[BookChapter]
    author: str = ""
    source_name: str = ""
    source_type: str = "epub"
    selected_chapter_id: str = ""
    character_registry: CharacterRegistry = field(
        default_factory=CharacterRegistry
    )
    pronunciations: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.title = self.title.strip() or "未命名书籍"
        self.author = self.author.strip()
        if not self.chapters:
            raise ValueError("项目里没有可朗读章节")
        if len(self.chapters) > MAX_PROJECT_CHAPTERS:
            raise ValueError(f"项目最多保存 {MAX_PROJECT_CHAPTERS} 个章节")
        chapter_ids = [chapter.id for chapter in self.chapters]
        if len(set(chapter_ids)) != len(chapter_ids):
            raise ValueError("项目包含重复的章节 ID")
        total_characters = sum(len(chapter.text) for chapter in self.chapters)
        if total_characters > MAX_PROJECT_CHARACTERS:
            raise ValueError(
                f"项目文字总量不能超过 {MAX_PROJECT_CHARACTERS:,} 字"
            )
        if self.selected_chapter_id not in set(chapter_ids):
            self.selected_chapter_id = chapter_ids[0]
        normalized_pronunciations: dict[str, str] = {}
        for source, reading in self.pronunciations.items():
            source_text = str(source).strip()
            reading_text = str(reading).strip()
            if (
                source_text
                and reading_text
                and source_text != reading_text
                and len(source_text) <= 32
                and len(reading_text) <= 64
            ):
                normalized_pronunciations[source_text] = reading_text
        if len(normalized_pronunciations) > 100:
            raise ValueError("全书发音词典最多保存 100 条")
        self.pronunciations = normalized_pronunciations
        self.warnings = [str(warning) for warning in self.warnings if str(warning)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROJECT_SCHEMA,
            "version": PROJECT_VERSION,
            "title": self.title,
            "author": self.author,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "selected_chapter_id": self.selected_chapter_id,
            "chapters": [chapter.to_dict() for chapter in self.chapters],
            "character_registry": self.character_registry.to_dict(),
            "pronunciations": dict(self.pronunciations),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BookProject":
        if value.get("schema") != PROJECT_SCHEMA:
            raise ValueError("这不是声场书籍项目文件")
        if int(value.get("version", 0)) != PROJECT_VERSION:
            raise ValueError("暂不支持这个版本的声场项目文件")
        raw_chapters = value.get("chapters", [])
        if not isinstance(raw_chapters, list):
            raise ValueError("项目章节格式错误")
        raw_pronunciations = value.get("pronunciations", {})
        if not isinstance(raw_pronunciations, dict):
            raw_pronunciations = {}
        return cls(
            title=str(value.get("title", "未命名书籍")),
            author=str(value.get("author", "")),
            source_name=str(value.get("source_name", "")),
            source_type=str(value.get("source_type", "project")),
            selected_chapter_id=str(value.get("selected_chapter_id", "")),
            chapters=[
                BookChapter.from_dict(chapter)
                for chapter in raw_chapters
                if isinstance(chapter, dict)
            ],
            character_registry=CharacterRegistry.from_dict(
                value.get("character_registry")
            ),
            pronunciations={
                str(source): str(reading)
                for source, reading in raw_pronunciations.items()
            },
            warnings=[
                str(warning)
                for warning in value.get("warnings", [])
                if str(warning)
            ],
        )
