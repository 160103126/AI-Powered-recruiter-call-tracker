TECHNICAL DETAILS — Call Recorder Pipeline

Summary
- Purpose: detailed technical explanation of how transcription, heuristic extraction, LLM extraction, validation, and data outputs work.

1) Whisper transcription (local)
- Library: `faster-whisper` is used via `services/transcriber.py`.
- Model selection: the model size is controlled by `WHISPER_MODEL_SIZE` (defaults to `small`). The loader attempts compute types in order (int8_float16, int8, fallback) to balance accuracy and compatibility.
- Runtime: `simple_pipeline.py` calls the loaded Whisper model's `transcribe()` method (beam decoding) and concatenates segment text into a single transcript string saved to `transcripts/<sha256>.txt`.
- Notes: set `WHISPER_MODEL_SIZE` to `tiny` or `small` on low-memory systems; install proper CPU/GPU dependencies for faster performance.

2) Heuristics extraction
- Implemented in `heuristics_extract()` in `simple_pipeline.py`.
- Techniques:
  - Regexes for phone numbers, salary formats (Indian formats and numeric ranges), common "from/at COMPANY" patterns, and interview timing phrases.
  - Keyword matching for `tech_stack` against a curated `TECH_KEYWORDS` list.
  - Role extraction via phrase patterns like "hiring for", "for the" followed by a noun phrase.
  - Summary: a lightweight summary is produced by taking the first two sentences (split on punctuation) from the transcript.
- Confidence scoring:
  - A simple count-based score (1–10) derived from presence of core fields (company, name, phone, role, salary).
  - The pipeline uses this `confidence_score` to decide whether to call the LLM (threshold now 9).

3) LLM extraction (Gemini / OpenAI via LangChain provider)
- Provider choice:
  - We use `langchain_google_genai`'s `ChatGoogleGenerativeAI` as the preferred path for Gemini/Vertex AI. This supports both Gemini Developer API and Vertex AI invocation.
  - Fallback to OpenAI path exists if `OPENAI_API_KEY` is set and GCP config is not available.
- Invocation pattern:
  - The pipeline builds a prompt from `prompts/extraction.txt` which explicitly requests strict JSON with a fixed schema.
  - For Gemini: `ChatGoogleGenerativeAI.invoke(prompt)` is used and the returned `AIMessage` content is parsed into a text string.
  - For OpenAI: LangChain's `ChatOpenAI` or the `openai` SDK is used depending on availability.
- Parsing and strictness:
  - We first attempt to parse the LLM output as JSON. If parsing fails, a robust regex extracts the first JSON-looking object and parses it.
  - To reduce hallucination, we run a conservative validation/merge step (in `simple_pipeline.py`):
    - `tech_stack`: accept entries only if the token appears in the transcript or matches a known keyword.
    - `recruiter_phone`: accept only if it matches the phone regex.
    - Free-text fields (`company`, `role`, `location`, `recruiter_name`, `next_action`): accept only when word-overlap with the transcript exists (minimum overlap rules applied).
    - `salary_min`/`salary_max`: accepted only if transcript contains a salary mention.
    - `call_summary` and `job_description_summary`: accepted only if there is multi-word overlap to avoid invented summaries.

4) Response format enforcement
- Current approach: prompt-based instruction in `extraction.txt` plus post-LLM JSON parsing and conservative merging.
- Recommended/next step: implement a LangChain `OutputParser` (e.g., `JsonOutputParser` or `PydanticOutputParser`) to enforce schema and fail when output is invalid. This prevents accidental acceptance of free-form text and improves reliability.

5) Data movement & outputs
- Input: audio files placed in `recordings/` (supported formats: `.mp3`, `.wav`, `.m4a`, `.aac`).
- Transcription: output saved to `transcripts/<sha256>.txt`.
- Extraction + Scoring: structured dict assembled and validated.
- Persistence:
  - Primary: `opportunities.xlsx` updated with a new row. Columns include filename, file_hash, company, recruiter_name, recruiter_phone, role, location, salary_min, salary_max, tech_stack, next_action, call_summary, transcript_path, audio_path, processed_at, confidence_score.
  - Optional: Google Sheets append when `SHEET_NAME` and service account credentials are provided.
- Post-processing: processed audio is moved to `recordings/processed/` to prevent reprocessing; a `processed_files.json` is updated with file hash and timestamp.

6) Errors, logging, and fallbacks
- Whisper model load errors gracefully fallback to alternate compute types.
- LLM provider mismatches: the code prefers `langchain_google_genai` and provides explicit error messages with pip install guidance.
- Vertex AI direct API usage was removed in favor of provider-level calls to reduce version incompatibilities.
- Sheets append failures log errors but do not stop pipeline; Excel is always written first.

7) Security / PII
- Default behavior: do not redact PII; full transcript is sent to LLM when configured.
- Optional: set `REDACT_PII=1` to replace phone-like patterns in the transcript before sending to LLM.

8) Config & env variables (most relevant)
- `WHISPER_MODEL_SIZE` — whisper model size
- `RECORDINGS`, `TRANSCRIPTS` — directories
- `OPENAI_API_KEY`, `OPENAI_MODEL` — OpenAI path
- `GOOGLE_CLOUD_PROJECT`, `GEMINI_MODEL`, `GOOGLE_CLOUD_LOCATION` — Gemini/Vertex AI path
- `SHEET_NAME`, `GOOGLE_SERVICE_ACCOUNT_JSON` — Google Sheets
- `REDACT_PII` — optional redact toggle

9) Where to improve
- Add LangChain `OutputParser` enforcement.
- Add rate-limited retries for LLM and Sheets requests and backoff.
- Add unit/integration tests for heuristics and LLM-merge logic using canned transcripts.


Created: 2026-06-03
