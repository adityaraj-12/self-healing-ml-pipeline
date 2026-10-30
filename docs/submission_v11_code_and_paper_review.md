# Code and manuscript review — Repository V11 / Paper Revision 10

## Verification performed

- Python version: 3.13.5.
- Offline test suite: **109 passed**; local run took about one second.
- Family-detector regression: **34/34 expected labels**, implementation hash matched. Developer-authored regression fixture only; not independent or production evidence.
- Locked root-cause subcode evaluation: **33/36 (91.67%)**, implementation hash matched. Developer-authored locked set; not third-party blind.
- LLM-run manifest tests check settings fields, API-key non-disclosure, endpoint sanitization, missing configuration, and SDK-version mismatch detection.
- No live LLM API calls were made.

## LLM configuration recovered from source

- Model ID is read from `OPENAI_MODEL`; the uploaded archive does not contain its historical value.
- `OPENAI_API_KEY` is read from the environment but only its presence is recorded by the manifest.
- `OPENAI_BASE_URL` is optional and sanitized before recording.
- Repair generation and LLM RCA both use `temperature=0` and JSON-object response format.
- Repair generation may make up to two candidate attempts if structural checks fail; LLM RCA makes one request per analysis.
- `top_p` and token limits are not explicitly supplied; provider defaults apply.
- `requirements-llm.txt` pins `openai==3.20.0` for future runs. That optional SDK is not installed in the offline core test environment.
- The repeated-trials runner writes a timestamped sanitized manifest beside each new run. It records installed/declared SDK versions, sanitized endpoint, Python/platform, source hashes and source-observable request options without recording the API-key value.

## Historical LLM comparison remains unreproducible

The original model identifier and request record were absent from the archive. The prior LLM results are therefore retained as historical results, not described as newly reproduced. A fresh run requires explicit model configuration and valid credentials and must archive raw candidate outputs and the generated manifest alongside trial-level results.

## Suggested live-run sequence (requires the user's own credentials)

```bash
python -m pip install -r requirements-llm.txt
cp .env.example .env  # edit locally; never commit .env
python -m benchmarks.llm_run_manifest --output research_artifacts/llm_run_manifest_preflight.json
python -m benchmarks.repeated_trials --repeats 5
```

The manifest command makes no API request. It reports an incomplete configuration and exits nonzero if model/credentials/SDK are missing or the SDK differs from the declared pin. Never share `.env` or print its contents.

## Remaining publication blockers

1. Obtain independent labels from two annotators and coordinator adjudication for the external RCA candidate packet.
2. Run the LLM comparison with a documented model and archive its manifest, raw candidates and trial outputs.
3. Vary data-split/fault-generation seeds and report scenario-level uncertainty.
4. Push and tag a repository commit that exactly matches Paper Revision 10.
5. Verify target-venue formatting and run an approved similarity checker. No Turnitin/iThenticate report has been run; no AI-detector outcome can be guaranteed.
