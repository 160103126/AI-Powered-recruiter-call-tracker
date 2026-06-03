import os
import json
import openai

PROMPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'extraction.txt')

def load_prompt():
    with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
        return f.read()

def extract_from_transcript(transcript):
    prompt = load_prompt()
    messages = [
        {"role": "system", "content": "You are a structured extractor."},
        {"role": "user", "content": prompt + "\n\nTRANSCRIPT:\n" + transcript}
    ]
    resp = openai.ChatCompletion.create(model='gpt-4o-mini', messages=messages, max_tokens=1000)
    txt = resp.choices[0].message.content.strip()
    try:
        data = json.loads(txt)
    except Exception:
        # Try to extract JSON substring
        import re
        m = re.search(r"\{[\s\S]*\}", txt)
        if m:
            data = json.loads(m.group(0))
        else:
            raise
    return data
