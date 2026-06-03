import os
import json
import re

PROMPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'extraction.txt')

def load_prompt():
    with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
        return f.read()

def extract_from_transcript_llm(transcript, model_name=None):
    """Extract structured JSON using either OpenAI or Vertex AI (Gemini).

    Selection logic:
    - If GOOGLE_CLOUD_PROJECT env is set and GEMINI_MODEL is configured, call Vertex AI.
    - Else, if OPENAI_API_KEY is set, call OpenAI ChatCompletion.

    Returns parsed dict from LLM output.
    """
    prompt = load_prompt()
    # Vertex AI / LangChain path
    gcp_project = os.getenv('GOOGLE_CLOUD_PROJECT')
    gemini_model = os.getenv('GEMINI_MODEL')
    if gcp_project and gemini_model:
        prompt_text = prompt + "\n\nTRANSCRIPT:\n" + transcript
        # Use LangChain VertexAI wrapper for Gemini (preferred).
        # Try multiple import paths across LangChain versions
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except Exception as e:
            raise RuntimeError(
                'langchain_google_genai not available. Install in your venv: pip install langchain-google-genai\nOriginal import error: '
                + str(e)
            )
        try:
            loc = os.getenv('GOOGLE_CLOUD_LOCATION', 'us-central1')
            llm = ChatGoogleGenerativeAI(model=gemini_model, project=gcp_project, location=loc)
            ai_msg = llm.invoke(prompt_text)
            # Extract text from AIMessage content
            txt = ''
            if hasattr(ai_msg, 'content'):
                content = ai_msg.content
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, dict) and 'text' in item:
                            parts.append(item.get('text'))
                        elif isinstance(item, str):
                            parts.append(item)
                    txt = '\n'.join([p for p in parts if p])
                elif isinstance(content, str):
                    txt = content
                else:
                    txt = str(content)
            else:
                txt = str(ai_msg)
        except Exception as e:
            raise RuntimeError('ChatGoogleGenerativeAI VertexAI call failed: ' + str(e))
    else:
        # OpenAI path
        if not os.getenv('OPENAI_API_KEY'):
            raise EnvironmentError('OPENAI_API_KEY not set and no Vertex AI config found')
        try:
            # Prefer LangChain OpenAI wrapper if available
            try:
                from langchain.chat_models import ChatOpenAI
                model = model_name or os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
                chat = ChatOpenAI(model_name=model)
                txt = chat(prompt + "\n\nTRANSCRIPT:\n" + transcript)
            except Exception:
                import openai
                messages = [
                    {"role": "system", "content": "You are an interview opportunity extraction system. Return only valid JSON."},
                    {"role": "user", "content": prompt + "\n\nTRANSCRIPT:\n" + transcript}
                ]
                model = model_name or os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
                resp = openai.ChatCompletion.create(model=model, messages=messages, max_tokens=1000)
                txt = resp.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError('OpenAI extraction failed: ' + str(e))

    # parse JSON from txt
    try:
        data = json.loads(txt)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", txt)
        if m:
            data = json.loads(m.group(0))
        else:
            raise
    return data
