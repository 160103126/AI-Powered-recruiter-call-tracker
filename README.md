AI-Powered Recruiter Call Tracker - MVP

Quickstart

1. Create a Python venv and install requirements:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Configure environment variables:

- `OPENAI_API_KEY` (for extraction/scoring)

LLM fallback (optional)

- Set `OPENAI_API_KEY` to enable LLM-based extraction when heuristics are uncertain.
- By default the full transcript (including phone numbers) is sent to the LLM so extracted data can be saved verbatim. If you prefer redaction, set `REDACT_PII=1` to redact phone numbers before sending.
- The system calls the LLM only when heuristic confidence < 7.


Google Sheets (optional)

1. Create a Google Cloud service account with Sheets API enabled and download the JSON key.
2. Set environment variable `GOOGLE_SERVICE_ACCOUNT_JSON` to the path of the JSON key file.
3. Create a Google Sheet and share it with the service account email.
4. Set environment variable `SHEET_NAME` to the spreadsheet name.


3. Run the watcher (starts processing new files dropped into `recordings/`):

```powershell
python main.py
```

4. Run dashboard:

```powershell
streamlit run dashboard/app.py
```

Notes
- This is an MVP scaffold. Install `faster-whisper` to enable local transcription.
