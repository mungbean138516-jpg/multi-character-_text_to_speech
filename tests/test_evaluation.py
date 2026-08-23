import json
import unittest
from pathlib import Path

from evals.run_speaker_eval import DEFAULT_DATASET, evaluate


class SpeakerEvaluationTests(unittest.TestCase):
    def test_dataset_has_meaningful_category_coverage(self) -> None:
        dataset = json.loads(Path(DEFAULT_DATASET).read_text(encoding="utf-8"))
        categories = {case["category"] for case in dataset["cases"]}

        self.assertGreaterEqual(len(dataset["cases"]), 30)
        self.assertGreaterEqual(len(categories), 8)

    def test_local_baseline_meets_published_regression_floor(self) -> None:
        metrics = evaluate()

        self.assertGreaterEqual(metrics["dialogue_detection_f1"], 0.95)
        self.assertGreaterEqual(
            metrics["speaker_accuracy_on_matched_dialogues"], 0.80
        )
        self.assertGreaterEqual(metrics["joint_attribution_f1"], 0.80)


if __name__ == "__main__":
    unittest.main()
