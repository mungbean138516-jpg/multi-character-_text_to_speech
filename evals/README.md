# Speaker attribution evaluation

`speaker_attribution_cases.json` contains small, original Chinese fiction snippets
covering the patterns VoxCast currently claims to support. It is deliberately kept
outside the unit-test fixtures so that product quality can be reported separately
from engineering test counts.

Run the evaluation from the repository root:

```bash
python evals/run_speaker_eval.py
python evals/run_speaker_eval.py --json
```

The primary metric is **joint attribution F1**: a prediction is correct only when
both the dialogue text and its speaker match. The dataset is a regression set, not
an industry benchmark; results should always be published with the dataset size and
known failure cases.
