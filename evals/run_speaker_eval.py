#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from audiobook_app.analyzer import HeuristicNovelAnalyzer  # noqa: E402


DEFAULT_DATASET = Path(__file__).with_name("speaker_attribution_cases.json")


def _f1(true_positive: int, predicted: int, expected: int) -> float:
    if not predicted and not expected:
        return 1.0
    precision = true_positive / predicted if predicted else 0.0
    recall = true_positive / expected if expected else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def evaluate(dataset_path: Path = DEFAULT_DATASET) -> dict[str, Any]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    analyzer = HeuristicNovelAnalyzer()
    expected_total = 0
    predicted_total = 0
    detected_total = 0
    matched_total = 0
    speaker_correct = 0
    joint_correct = 0
    failures: list[dict[str, Any]] = []
    categories: dict[str, dict[str, int]] = defaultdict(
        lambda: {"cases": 0, "expected": 0, "matched": 0, "speaker_correct": 0}
    )

    for case in dataset["cases"]:
        result = analyzer.analyze(case["text"])
        characters = {item.id: item.name for item in result.characters}
        predicted = [
            {"text": segment.text, "speaker": characters[segment.speaker_id]}
            for segment in result.segments
            if segment.kind == "dialogue"
        ]
        expected = case["expected_dialogues"]
        category = categories[case["category"]]
        category["cases"] += 1
        category["expected"] += len(expected)
        expected_total += len(expected)
        predicted_total += len(predicted)

        expected_texts = Counter(item["text"] for item in expected)
        predicted_texts = Counter(item["text"] for item in predicted)
        detected = sum((expected_texts & predicted_texts).values())
        detected_total += detected

        unused = set(range(len(predicted)))
        case_matched = 0
        case_speaker_correct = 0
        for expected_row in expected:
            match_index = next(
                (
                    index
                    for index in sorted(unused)
                    if predicted[index]["text"] == expected_row["text"]
                ),
                None,
            )
            if match_index is None:
                continue
            unused.remove(match_index)
            case_matched += 1
            if predicted[match_index]["speaker"] == expected_row["speaker"]:
                case_speaker_correct += 1

        matched_total += case_matched
        speaker_correct += case_speaker_correct
        joint_correct += case_speaker_correct
        category["matched"] += case_matched
        category["speaker_correct"] += case_speaker_correct
        if predicted != expected:
            failures.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "expected": expected,
                    "predicted": predicted,
                }
            )

    metrics = {
        "dataset": dataset["name"],
        "cases": len(dataset["cases"]),
        "expected_dialogues": expected_total,
        "predicted_dialogues": predicted_total,
        "dialogue_detection_f1": round(
            _f1(detected_total, predicted_total, expected_total), 4
        ),
        "speaker_accuracy_on_matched_dialogues": round(
            speaker_correct / matched_total if matched_total else 1.0,
            4,
        ),
        "joint_attribution_f1": round(
            _f1(joint_correct, predicted_total, expected_total), 4
        ),
        "exact_case_accuracy": round(
            (len(dataset["cases"]) - len(failures)) / len(dataset["cases"]),
            4,
        ),
        "categories": dict(categories),
        "failures": failures,
    }
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate VoxCast local speaker attribution."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--json", action="store_true", help="Print complete JSON")
    parser.add_argument(
        "--fail-below",
        type=float,
        default=None,
        metavar="SCORE",
        help="Exit non-zero when joint attribution F1 is below SCORE",
    )
    args = parser.parse_args()
    metrics = evaluate(args.dataset)
    if args.json:
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    else:
        print(
            f"{metrics['dataset']}: {metrics['cases']} cases / "
            f"{metrics['expected_dialogues']} dialogues"
        )
        print(f"Dialogue detection F1: {metrics['dialogue_detection_f1']:.1%}")
        print(
            "Speaker accuracy on matched dialogues: "
            f"{metrics['speaker_accuracy_on_matched_dialogues']:.1%}"
        )
        print(f"Joint attribution F1: {metrics['joint_attribution_f1']:.1%}")
        print(f"Exact case accuracy: {metrics['exact_case_accuracy']:.1%}")
        print(f"Known failure cases: {len(metrics['failures'])}")
    if args.fail_below is not None:
        return int(metrics["joint_attribution_f1"] < args.fail_below)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
