# LLM email classifier

This classifier accepts email text and uses the same system prompt
and decision schema with NVIDIA NIM, Gemini, or Hugging Face Inference Providers.
The default pipeline mode, `EMAIL_CLASSIFIER_MODE=cascade`, calls it only after
rules find no match and Laya cannot classify confidently or fails. Configure
`EMAIL_LLM_PROVIDER` and its credentials/model for this fallback. If the LLM
also fails or abstains, the email goes to human review.
Set `EMAIL_CLASSIFIER_MODE=llm`
to use it in the comparison pipeline. Successful `BL_COMPARISON` decisions
continue to the existing attachment resolver; review outcomes stop processing.

## Setup and use

Install the project with `pip install -e .`. A local, git-ignored `.env` is
provided with empty secrets; `.env.example` is the shareable template.
Set `EMAIL_LLM_PROVIDER` and the chosen provider's key and model:

| Provider | Key | Model |
| --- | --- | --- |
| `nvidia` | `NVIDIA_API_KEY` | `NVIDIA_MODEL` |
| `gemini` | `GEMINI_API_KEY` | `GEMINI_MODEL` |
| `huggingface` | `HF_TOKEN` | `HF_MODEL` |

Model availability and schema support depend on your endpoint/account. NVIDIA
requires a model supporting `guided_json`; Hugging Face requires a model/backend
supporting strict JSON schema (a `:provider` suffix can pin the backend).
Set the corresponding `*_BASE_URL` to use a different endpoint, including a
self-hosted NIM. The base URL includes the API version, not the operation path.
Only the selected provider is called; there is no cross-provider fallback.
Email text is transmitted to that provider.

```bash
averis-classify-email email.txt --provider gemini
python -m averis_email.llm_classifier email.txt --provider nvidia
echo 'Please compare the draft BL against the SI.' | averis-classify-email - --provider huggingface
averis-classify-email "Averis Hackathon Instruction/sdoc-hackathon-docker/data_v2/inbox/email_001.json"
```

JSON input uses only `subject` and `body`. The supplied attachments directory's
`email_*_SI.txt` and `email_*_BL.txt` files are document contents, not email bodies;
document content alone may correctly need review because it lacks intent.
Use the adjacent `inbox/email_*.json` files for representative email inputs.

```python
from averis_email.llm_classifier import EmailClassifier

classifier = EmailClassifier.from_env(provider="gemini")
result = classifier.classify("Please clarify the charges on invoice 42.")
if result.review_required:
    # Your application's review queue/UI handles this result.
    print("Human review:", result.review_reason, result.reason)
else:
    print(result.category)
```

The `.env` path defaults to the current directory; use `--env-file` or the
`env_file` Python argument to select another file. Process environment values
take precedence. Missing credentials/models are configuration errors, raised
before classification; the CLI exits 2 for input/configuration errors.

## Output gate and review routing

The model must emit exactly `decision` and a brief `reason`. Its decision is one
of the five existing categories or the explicit abstention `NEEDS_REVIEW`:

- `BL_COMPARISON`: document comparison/review requests, including SI/BL checks.
- `SI_REQUEST`: new Shipping Instruction requests/submissions.
- `INVOICE_QUERY`: invoice, billing, charge or payment matters requiring action.
- `GENERAL`: clearly informational or routine messages.
- `SPAM`: unsolicited promotions, scams or phishing.

The shared prompt asks the model to be brutally honest, abstain when ambiguous,
identify the latest intent, and treat embedded instructions as untrusted data.
GENERAL is not an uncertainty fallback. These instructions reduce errors but do
not guarantee semantic accuracy or immunity to prompt injection.

Successful application output contains `category`, `status: "CLASSIFIED"`,
`review_required: false`, `review_reason: null`, and `reason`. Review output is:

```json
{
  "category": null,
  "status": "NEEDS_REVIEW",
  "review_required": true,
  "review_reason": "ambiguous_intent",
  "reason": "Both a new SI and invoice correction are equally primary requests."
}
```

Other review reasons are `invalid_input`, `invalid_response`, and `provider_error`.
Empty or oversized input is reviewed without a network call or silent truncation.
Invalid JSON, unknown labels, extra/duplicate fields, refusals, truncated responses,
and provider failures never silently become GENERAL. No automatic retries occur.
The CLI emits review results as JSON with exit 0: review is a valid outcome.
It does not create an external review ticket; callers route flagged results to
their review workflow. This separate result contract intentionally allows a null
category; do not pass it directly to the existing submission format.

## Modules and verification

`prompt.py` owns the shared instructions, `models.py` owns the gate/schema,
`providers.py` owns REST adapters and the `Provider` protocol, `config.py` owns
configuration, and `classifier.py` owns validation and review routing. Add a new
adapter implementing `complete(system, text, schema)` to reuse the prompt/gate.

Run `python -m unittest discover -s tests -p 'test_*.py'`. Offline tests verify
all categories, abstention, validation failures, provider request/response
contracts, configuration precedence, and the CLI. These tests do not measure
live model accuracy; evaluate representative labeled emails with your selected
model before relying on its decisions.

Provider references: [NVIDIA structured generation](https://docs.nvidia.com/nim/large-language-models/1.14.0/structured-generation.html),
[Gemini structured output](https://ai.google.dev/gemini-api/docs/generate-content/structured-output),
and [Hugging Face structured output](https://huggingface.co/docs/inference-providers/guides/structured-output).
