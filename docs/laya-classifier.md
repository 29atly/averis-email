# Laya email classifier

This is a separate, local classifier for the same five email categories. It
passes an email as the state and five named options as a single `choice`
question, ranks the returned probabilities, and applies human-review gates.
Set `EMAIL_CLASSIFIER_MODE=laya` to select it in the pipeline. Rules and hosted
LLM classifiers remain available through the other modes.

## What the research established

Laya is an encoder plus a decision head, rather than a text-generating chat
model. Its option-scoring interface accepts task-specific labels at inference
time. The root checkpoint targets English; the router selects a multilingual
checkpoint for other languages. The authors warn about overconfident predictions
and recommend domain calibration. Published benchmark scores do not establish
accuracy on this email dataset. See the [model card](https://huggingface.co/convaiinnovations/laya).

The [SDK implementation](https://github.com/NandhaKishorM/laya/blob/main/laya/agent.py)
returns each option's probability, an entropy-derived `confidence`, and an
`act_probability`. The entropy score is **not** the winning probability. The
SDK also applies checkpoint temperatures before returning probabilities.

The [sequence builder](https://github.com/NandhaKishorM/laya/blob/main/laya/common.py)
allocates separate question/options and state budgets, and silently trims text
that exceeds them. Our adapter checks those budgets before inference and sends
oversized inputs to review. Long instructions can also be trimmed, so the
question and option descriptions are deliberately compact. We use the SDK
directly rather than a generic Transformers text-classification pipeline.

## Install and run

```bash
pip install -e '.[laya]'
python -m averis_email.laya_classifier email.txt
averis-classify-laya "Averis Hackathon Instruction/sdoc-hackathon-docker/data_v2/inbox/email_001.json"
echo 'Please clarify invoice 42.' | averis-classify-laya -
```

The first call downloads the selected public checkpoint into `.cache/laya`;
later calls reuse it. Downloads require internet access, but email inference is
local. No API key is required; `HF_TOKEN` is optional for Hub access. The English
weights are approximately 808 MB, and runtime memory is larger. CPU is the default;
`--device mps` or `--device cuda` can select supported hardware.

The integration pins SDK 0.3.4 and model revision
`1c5edc17a7acd8701df6fc341c0d179f1c62c982`. It downloads only the selected
checkpoint's five required files, avoiding the SDK root loader's download of
all bundled variants. Heavy imports and downloads occur on first classification,
not package import. Reuse one classifier instance to retain loaded models.

```python
from averis_email.laya_classifier import LayaEmailClassifier

classifier = LayaEmailClassifier.from_env()
result = classifier.classify("Please check the draft BL against the SI.")
if result.review_required:
    print("Human review:", result.review_reason, result.probabilities)
else:
    print(result.category, result.confidence)
```

Text files and stdin are accepted as-is. Inbox JSON uses subject and body only;
attachment contents and ground truth never enter inference. This adapter retains
the full supplied email rather than destructively stripping text. The question
asks for the latest intent, but long threads may exceed the token budget and
require review. SI/BL attachment text alone is not representative email input.

## Output and gates

The category options are `BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`,
`GENERAL`, and `SPAM`. Descriptions live in `questions.py`.

Automatic classification requires all of the following:

- Winning probability at least `LAYA_MIN_PROBABILITY` (default `0.80`).
- Gap over the runner-up at least `LAYA_MIN_MARGIN` (default `0.20`). Ties always require review.
- Action probability at least `LAYA_MIN_ACT_PROBABILITY` (default `0.50`).
- Valid, complete scores for exactly the five options, with finite probabilities
  between zero and one, summing to one within the SDK's rounding tolerance.

These are initial operating thresholds, not calibrated accuracy guarantees.
There is no sixth option competing with the categories: human review is a
separate decision applied after scoring. The act head supplies an additional
abstention signal, not a guarantee of reliability.

Accepted results have `status: "CLASSIFIED"` and a category. Review results have
`status: "NEEDS_REVIEW"`, `category: null`, and a reason. When scores are available,
`suggested_category` preserves the best candidate for the reviewer. `confidence`
means the winning probability; `entropy_confidence` preserves the differently
defined SDK field. Full scores, margin, act probability, checkpoint routing,
revision, and token usage are also returned.

Input overflow, unsupported language under an English override, missing model
dependencies, download/inference failure, and invalid responses also require
review. The calling application must enqueue these results or display them in
its review UI; this module does not create external tickets. Its nullable category
contract should not be sent directly to the hackathon submission endpoint.

Configuration loads `.env` with process environment taking precedence. The
`LAYA_*` settings are listed in `.env.example`; `LAYA_REVISION` can override the
pinned checkpoint. `LAYA_LOCAL_FILES_ONLY=true` disables model download/network
lookup after the required checkpoint is cached. `LAYA_CHECKPOINT=auto` routes by
language; `english` refuses detected non-English input; `multilingual` forces
that checkpoint. Language detection itself can make mistakes.

## Evaluation

```bash
python -m averis_email.laya_classifier.evaluate \
  "Averis Hackathon Instruction/sdoc-hackathon-docker/data_v2" \
  --limit 40 --seed 42 --out outputs/laya-evaluation.json
```

This samples inbox files independently of labels, then uses `ground_truth.json`
only to score predictions. The report includes review reasons, category counts,
coverage, accuracy among accepted predictions, and top-choice accuracy among
inputs that received scores. No accepted predictions means accepted accuracy
is `null`, not zero or 100%. Use `--limit 0` for the entire inbox.

Threshold fitting, temperature calibration, or fine-tuning should use a separate
development split, followed by evaluation on untouched data. The included
evaluation command does not fit anything. Unit tests cover scoring, review gates,
malformed output, configuration, evaluation denominators, and optional SDK
context/routing contracts without downloading weights.

### Observed local run

The seed-42 sample of 40 emails, using the pinned model and default gates, gave:

| Measure | Result |
| --- | --- |
| Automatically classified | 8/40 (20% coverage) |
| Correct among accepted | 8/8 |
| Correct top choice among scored | 27/32 (84.4%) |
| Review: low probability | 24 |
| Review: token budget exceeded | 8 |

The accepted emails were five invoice queries and three spam messages. No SI,
document-comparison, or general message passed the gates in this sample. All
scored inputs used the English checkpoint; multilingual inference was not
exercised. This small sample does not establish production accuracy or
calibration. The full per-email report is saved locally in
`outputs/laya-evaluation.json`, with no email bodies or secrets. Thresholds were
not adjusted after inspecting these results.
