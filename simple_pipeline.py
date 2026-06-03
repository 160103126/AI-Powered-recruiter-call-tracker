import os
import time
import json
import logging
from datetime import datetime
import re
import pandas as pd
from dotenv import load_dotenv
import shutil

from services.utils import file_sha256
from services.extractor_llm import extract_from_transcript_llm
from services.scorer import score_opportunity

try:
    from faster_whisper import WhisperModel
except Exception as e:
    WhisperModel = None

BASE = os.path.dirname(__file__)

# Load .env from project root if present
try:
    load_dotenv(os.path.join(BASE, '.env'))
except Exception:
    pass

# Paths: allow overriding via environment variables
RECORDINGS = os.getenv('RECORDINGS', os.path.join(BASE, 'recordings'))
TRANSCRIPTS = os.getenv('TRANSCRIPTS', os.path.join(BASE, 'transcripts'))
PROCESSED_JSON = os.path.join(BASE, 'processed_files.json')
OUT_XLSX = os.path.join(BASE, 'opportunities.xlsx')
PROCESSED_DIR = os.path.join(RECORDINGS, 'processed')

os.makedirs(RECORDINGS, exist_ok=True)
os.makedirs(TRANSCRIPTS, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('call-tracker')
def load_processed():
    if not os.path.exists(PROCESSED_JSON):
        return {}
    with open(PROCESSED_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_processed(d):
    with open(PROCESSED_JSON, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=2)
    logger.debug('Updated processed_files.json')

def transcribe(path, model=None):
    if WhisperModel is None:
        raise RuntimeError('faster-whisper not installed')
    if model is None:
        model = WhisperModel('small', device='cpu', compute_type='int8_float16')
    segments, info = model.transcribe(path, beam_size=5)
    text = ' '.join([s.text for s in segments])
    return text

PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s-])?(?:\(\d{2,4}\)|\d{2,4})[\s-]?\d{6,8}")
SALARY_RE = re.compile(r"(?:₹|rs\.?\s?)?([\d,]{2,7})(?:\s*(lakh|lakhs|lpa|k|kpa|per annum|pa))?", re.I)

TECH_KEYWORDS = [
    'python','azure','openai','langchain','rag','docker','kubernetes','aws','gcp','pytorch','tensorflow','nlp','sql','postgres','react','node'
]

def heuristics_extract(transcript):
    t = transcript
    data = {
        'company': None,
        'recruiter_name': None,
        'recruiter_phone': None,
        'role': None,
        'location': None,
        'salary_min': None,
        'salary_max': None,
        'tech_stack': [],
        'next_action': None,
        'call_summary': None,
    }
    # recruiter name: "this is NAME", "I'm NAME", "I am NAME"
    m = re.search(r"\b(?:this is|i'm|i am|this's)\s+([A-Z][a-zA-Z]+)\b", t)
    if m:
        data['recruiter_name'] = m.group(1)
    # company: "from COMPANY" or "at COMPANY"
    m = re.search(r"\bfrom\s+([A-Z][A-Za-z0-9 &.-]{2,50})", t)
    if m:
        data['company'] = m.group(1).strip()
    else:
        m = re.search(r"\bat\s+([A-Z][A-Za-z0-9 &.-]{2,50})", t)
        if m:
            data['company'] = m.group(1).strip()
    # phone
    m = re.search(r"(\+?\d[\d\s\-]{6,}\d)", t)
    if m:
        data['recruiter_phone'] = re.sub(r"\s+", '', m.group(1))
    # role
    m = re.search(r"(?:for the|for a|hiring for|position|role[:]? )\s*([A-Za-z0-9 \-+&]+?)(?:\.|,|\n| for | at )", t, re.I)
    if m:
        data['role'] = m.group(1).strip()
    # salary
    m = SALARY_RE.search(t)
    if m:
        num = m.group(1)
        num = int(re.sub(r',','', num))
        unit = m.group(2) or ''
        if unit.lower().startswith('l') or 'lakh' in unit.lower() or 'lpa' in unit.lower():
            data['salary_min'] = num * 100000
            data['salary_max'] = num * 100000
        else:
            data['salary_min'] = num
            data['salary_max'] = num
    # tech stack detection
    lower = t.lower()
    for k in TECH_KEYWORDS:
        if k in lower:
            data['tech_stack'].append(k)
    # next action: look for interview date/time phrases
    m = re.search(r"interview (?:on|at) ([A-Za-z0-9:, ]{3,40})", t, re.I)
    if m:
        data['next_action'] = 'Interview on ' + m.group(1)
    # call summary: first two sentences
    s = re.split(r'(?<=[.!?])\s+', t.strip())
    data['call_summary'] = ' '.join(s[:2]) if s else t[:300]

    # confidence: count how many main fields we found
    cnt = 0
    for f in ['company','recruiter_name','recruiter_phone','role','salary_min']:
        if data.get(f):
            cnt += 1
    data['confidence_score'] = int(min(10, max(1, round((cnt/5)*10))))
    return data

def append_to_excel(row):
    cols = ['filename','file_hash','company','recruiter_name','recruiter_phone','role','location','salary_min','salary_max','tech_stack','next_action','call_summary','transcript_path','audio_path','processed_at','confidence_score']
    df_row = {k: row.get(k) for k in cols}
    # Prevent duplicate by checking file_hash in existing Excel
    if os.path.exists(OUT_XLSX):
        try:
            df_existing = pd.read_excel(OUT_XLSX)
            if 'file_hash' in df_existing.columns and str(df_row.get('file_hash')) in df_existing['file_hash'].astype(str).values:
                logger.info('Duplicate detected in Excel for %s — skipping append', df_row.get('file_hash'))
                return
            df = pd.concat([df_existing, pd.DataFrame([df_row])], ignore_index=True)
        except Exception as e:
            logger.warning('Failed reading existing Excel file: %s — will overwrite', e)
            df = pd.DataFrame([df_row], columns=cols)
    else:
        df = pd.DataFrame([df_row], columns=cols)
    df.to_excel(OUT_XLSX, index=False)
    logger.info('Appended row to %s', OUT_XLSX)

    # Optionally append to Google Sheets if SHEET_NAME is provided
    sheet_name = os.getenv('SHEET_NAME')
    if sheet_name:
        try:
            from services.sheets import append_row as gs_append
            row_values = [df_row.get(c) if not isinstance(df_row.get(c), list) else ','.join(df_row.get(c)) for c in cols]
            gs_append(sheet_name, row_values)
            logger.info('Appended row to Google Sheet %s', sheet_name)
        except Exception as e:
            logger.error('Google Sheets append failed: %s', e)

def process_file(path, model):
    h = file_sha256(path)
    processed = load_processed()
    if h in processed:
        logger.debug('Already processed: %s', path)
        return
    logger.info('Processing %s', path)
    try:
        transcript = transcribe(path, model)
    except Exception as e:
        logger.error('Transcription error for %s: %s', path, e)
        return
    tpath = os.path.join(TRANSCRIPTS, h + '.txt')
    with open(tpath, 'w', encoding='utf-8') as f:
        f.write(transcript)
    data = heuristics_extract(transcript)
    # If heuristics confidence is low, optionally call LLM extractor
    try:
        conf = int(data.get('confidence_score') or 0)
    except Exception:
        conf = 0
    if conf < 9 and (os.getenv('OPENAI_API_KEY') or os.getenv('GOOGLE_CLOUD_PROJECT')):
        logger.info('Low confidence (%s). Calling LLM extractor...', conf)
        # By default DO NOT redact PII — send full transcript. Set REDACT_PII=1 to redact phone numbers.
        redact = os.getenv('REDACT_PII') == '1'
        send_transcript = re.sub(r"(\+?\d[\d\s\-]{6,}\d)", '[REDACTED_PHONE]', transcript) if redact else transcript
        try:
            llm_data = extract_from_transcript_llm(send_transcript)
            # merge: prefer llm_data values when present, but validate strictly to avoid hallucination
            def _words(s):
                return set(re.findall(r"\w{2,}", (s or '').lower()))

            def _overlap(a, b, min_overlap=2):
                if not a or not b:
                    return False
                return len(_words(a) & _words(b)) >= min_overlap

            # Validate and accept LLM fields conservatively
            for k, v in llm_data.items():
                if v is None or v == '':
                    continue
                try:
                    if k == 'tech_stack':
                        # normalize list
                        if isinstance(v, str):
                            items = [x.strip().lower() for x in re.split(r'[;,\n]|\s+', v) if x.strip()]
                        else:
                            items = [str(x).strip().lower() for x in v if x]
                        # only accept techs that appear in transcript or are in known keywords
                        accepted = []
                        for t in items:
                            if t in lower or any(kw == t or kw in t or t in kw for kw in TECH_KEYWORDS):
                                accepted.append(t)
                        if accepted:
                            data['tech_stack'] = accepted
                    elif k == 'recruiter_phone':
                        if re.search(r"(\+?\d[\d\s\-]{6,}\d)", str(v)):
                            data['recruiter_phone'] = re.sub(r"\s+", '', str(v))
                    elif k in ('company', 'role', 'location', 'recruiter_name'):
                        # only accept if there's word overlap with transcript
                        if _overlap(str(v), transcript, min_overlap=1):
                            data[k] = str(v)
                    elif k in ('salary_min', 'salary_max'):
                        # accept numeric-looking salary only if transcript contained a salary mention
                        if SALARY_RE.search(transcript):
                            data[k] = v
                    elif k in ('next_action','interview_date','interview_time'):
                        if _overlap(str(v), transcript, min_overlap=1):
                            data[k] = str(v)
                    elif k in ('call_summary','job_description_summary'):
                        # require at least 3 overlapping words with transcript to accept LLM summary
                        if _overlap(str(v), transcript, min_overlap=3):
                            data[k] = str(v)
                    else:
                        # conservative default: accept only when overlap exists
                        if _overlap(str(v), transcript, min_overlap=1):
                            data[k] = v
                except Exception:
                    continue
            # optionally run scorer
            try:
                sc = score_opportunity(data)
                data['score'] = sc.get('score')
            except Exception:
                pass
        except Exception as e:
            logger.error('LLM extraction failed: %s', e)
    row = {
        'filename': os.path.basename(path),
        'file_hash': h,
        'company': data.get('company'),
        'recruiter_name': data.get('recruiter_name'),
        'recruiter_phone': data.get('recruiter_phone'),
        'role': data.get('role'),
        'location': data.get('location'),
        'salary_min': data.get('salary_min'),
        'salary_max': data.get('salary_max'),
        'tech_stack': ','.join(data.get('tech_stack') or []),
        'next_action': data.get('next_action'),
        'call_summary': data.get('call_summary'),
        'transcript_path': tpath,
        'audio_path': path,
        'processed_at': datetime.utcnow(),
        'confidence_score': data.get('confidence_score')
    }
    append_to_excel(row)
    processed[h] = {'file': os.path.basename(path), 'processed_at': str(datetime.utcnow())}
    save_processed(processed)
    logger.info('Saved to %s', OUT_XLSX)
    # Move processed audio to archive folder to avoid repeated polling
    try:
        # If file is already in processed dir, skip move
        if os.path.abspath(os.path.dirname(path)) == os.path.abspath(PROCESSED_DIR):
            logger.debug('Source file already in processed dir, skipping move: %s', path)
        else:
            if os.path.exists(path):
                dest = os.path.join(PROCESSED_DIR, os.path.basename(path))
                shutil.move(path, dest)
                logger.info('Moved processed audio to %s', dest)
            else:
                logger.warning('Source audio file not found when attempting move: %s', path)
    except Exception as e:
        logger.warning('Failed to move processed file: %s', e)

def main(poll_interval=8):
    if WhisperModel is None:
        logger.error('faster-whisper not available. Install via pip install faster-whisper')
        return
    # Load Whisper model with safe compute-type fallback
    try:
        from services.transcriber import _load_whisper_model
        model, used_compute = _load_whisper_model(os.getenv('WHISPER_MODEL_SIZE','small'))
        logger.info('Loaded Whisper model (compute_type=%s)', used_compute)
    except Exception as e:
        logger.error('Failed to load faster-whisper model: %s', e)
        return
    logger.info('Watching %s', RECORDINGS)
    while True:
        files = [os.path.join(RECORDINGS,f) for f in os.listdir(RECORDINGS) if f.lower().endswith(('.mp3','.wav','.m4a','.aac'))]
        for f in files:
            process_file(f, model)
        time.sleep(poll_interval)

if __name__ == '__main__':
    main()
