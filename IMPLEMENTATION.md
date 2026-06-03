**Project: Call Recorder — Implementation Notes**

**Overview**
- **Purpose:** A minimal local pipeline that watches a recordings folder, transcribes recruiter call audio, extracts structured opportunity data, scores opportunities, and appends results to an Excel file (and optionally Google Sheets).
- **Design goals:** Keep it simple (no heavy DBs), preserve full data (no automatic redaction by default), provide robust local transcription with an LLM fallback for extraction when heuristics are uncertain.

**What We Built**
- **Watcher + pipeline:** `simple_pipeline.py` — main runner that polls `recordings/`, transcribes audio, extracts fields, appends to `opportunities.xlsx`, saves transcripts, and moves processed audio to `recordings/processed/`.
- **Services:** small modular helpers under `services/`:
  - `services/transcriber.py` — faster-whisper loader and transcription wrapper.
  - `services/extractor_llm.py` — LLM extraction using LangChain provider for Google Gemini (via `langchain_google_genai.ChatGoogleGenerativeAI`) or OpenAI fallback.
  - `services/scorer.py` — LLM scoring helper (same provider selection as extractor).
  - `services/sheets.py` — Google Sheets append helper (uses service account JSON if provided).
  - `services/utils.py` — utilities (file SHA256 hashing, etc.).
  - `services/watcher.py` — older watcher implementation (kept for reference).
- **Prompts:** `prompts/extraction.txt` and `prompts/scoring.txt` — instruction templates sent to the LLM.
- **Config:** `.env` (env-driven) and `requirements.txt` list dependencies.

**Why We Made These Choices**
- **faster-whisper (local transcription):** fast, accurate for offline transcription; keeps processing local and avoids sending raw audio to external APIs.
- **Hybrid extractor (heuristics + LLM):** heuristics are fast and deterministic; LLM is called only when heuristics confidence is low to reduce cost and hallucination surface.
- **LangChain provider `langchain_google_genai` for Gemini/VertexAI:** the installed provider exposes `ChatGoogleGenerativeAI` which cleanly supports both Gemini Developer API and Vertex AI modes; using the provider avoids low-level client incompatibilities.
- **Excel + optional Google Sheets:** user wanted a simple, file-backed solution — Excel is easy to inspect; Sheets is optional via `GOOGLE_SERVICE_ACCOUNT_JSON`.
- **Conservative merging:** to reduce hallucination we validate and accept LLM outputs only if they have demonstrable overlap with the transcript (special rules for `tech_stack`, phone, salary, summaries).

**Key Implementation Notes**
- **Heuristics & Confidence:** `heuristics_extract()` in `simple_pipeline.py` inspects the transcript for company, role, phone, salary, tech keywords and builds a `confidence_score` (1–10). The fall-back threshold was raised from 7 to 9 to call the LLM more often when heuristics are uncertain.
- **LLM Extraction:** `services/extractor_llm.py` uses `ChatGoogleGenerativeAI.invoke()` to call Gemini (Vertex AI) when `GOOGLE_CLOUD_PROJECT` + `GEMINI_MODEL` are set; otherwise it uses the OpenAI path. The prompt enforces JSON-only output. We parse JSON robustly and then run a strict validation/merge.
- **Strict merging rules (to limit hallucination):**
  - `tech_stack`: accept only items that appear in transcript or match known keywords.
  - `recruiter_phone`: accept only if a phone regex matches.
  - `company`, `role`, `location`, `recruiter_name`, `next_action`: accept only if word-overlap with transcript exists.
  - `salary_*`: accepted only if transcript contained a salary mention.
  - `call_summary`, `job_description_summary`: require multi-word overlap before replacing heuristic summary.
- **LangChain/Provider compatibility:** some langchain releases do not expose a `VertexAI` class; the safe provider in this environment is `langchain_google_genai` (uses `ChatGoogleGenerativeAI`). If missing, install via:

  - `pip install langchain langchain-google-genai`

- **Processed-file handling:** After successful append, audio is moved to `recordings/processed/`. The move logic checks for source existence and avoids trying to move files already in the processed folder.

**Files of Interest**
- `simple_pipeline.py` — main runner and heuristics (entrypoint)
- `services/transcriber.py` — Whisper model loader and `transcribe_file` helpers
- `services/extractor_llm.py` — LLM extraction logic (Gemini / OpenAI selection)
- `services/scorer.py` — scoring wrapper
- `services/sheets.py` — Google Sheets append helper
- `prompts/extraction.txt` — extraction schema prompt (expects strict JSON)
- `requirements.txt` — dependency list (faster-whisper, langchain, langchain-google-genai, google-cloud-aiplatform, etc.)

**How It Works (flow)**
1. Drop audio into `recordings/`.
2. The pipeline polls `recordings/` (or watcher notifies) and transcribes audio via `faster-whisper`.
3. `heuristics_extract()` builds initial `data` and `confidence_score`.
4. If `confidence_score < 9` and LLM is available, call `extract_from_transcript_llm()` and strictly validate/merge returned fields.
5. Optionally call `score_opportunity()` to generate a numeric score.
6. Append a row to `opportunities.xlsx` and optionally to Google Sheets if `SHEET_NAME` is set.
7. Move processed audio to `recordings/processed/` and save the transcript file under `transcripts/<file_hash>.txt`.

**Configuration & Run Instructions (quick)**
- Create and activate a virtualenv, install requirements:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

- Set environment variables in `.env` or your shell. Minimal for OpenAI path:
  - `OPENAI_API_KEY` — your OpenAI key
  - `WHISPER_MODEL_SIZE` — e.g., `small` or `tiny` (defaults to `small`)

- For Gemini/Vertex AI usage:
  - `GOOGLE_CLOUD_PROJECT` — your GCP project
  - `GEMINI_MODEL` — e.g., `gemini-2.5-pro` (depends on availability)
  - Ensure ADC or `GOOGLE_SERVICE_ACCOUNT_JSON` is configured, or set `GOOGLE_API_KEY` and `GOOGLE_GENAI_USE_VERTEXAI=true` per `langchain_google_genai` docs.

- Run the pipeline:

```powershell
python simple_pipeline.py
```

**Notes on Response Formatting & Hallucination**
- The prompt `prompts/extraction.txt` requests "Return ONLY valid JSON" and lists fields. This helps but does not fully prevent hallucination.
- Best enforcement: use LangChain's `OutputParser` / `response_format` (JSON schema) with strict parsing. I can add a LangChain `PydanticOutputParser` or `JsonOutputParser` wrapper to `services/extractor_llm.py` to force strict schema output and fail when validation fails.

**Troubleshooting**
- If LLM calls fail with import errors: ensure `langchain` and `langchain-google-genai` are installed in the active venv.
- Vertex AI client errors: different `google-cloud-aiplatform` versions have API differences — we prefer to call through `langchain_google_genai` to avoid low-level version incompatibilities.
- If transcription compute errors occur (faster-whisper compute_type unsupported), change `WHISPER_MODEL_SIZE` to `small`, `tiny`, or remove `compute_type` to let it choose defaults.

**Next Improvements (optional)**
- Add LangChain `OutputParser` to enforce JSON schema strictly on LLM output.
- Add rate-limiting and retry/backoff for LLM/Sheets/API calls.
- Add an end-to-end test harness that runs on a sample audio and asserts desired extracted fields.
- Add a small CLI for one-shot processing and for reprocessing archived files.


----
Generated on: 2026-06-03

If you want, I can:
- Add the LangChain `JsonOutputParser` implementation now, or
- Re-run a single processing pass on the archived audio to validate the stricter merging rules.
