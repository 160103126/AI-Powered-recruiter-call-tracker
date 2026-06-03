import os
import json
import re

PROMPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'scoring.txt')

def load_prompt():
    with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
        return f.read()

def score_opportunity(opportunity):
    prompt = load_prompt()
    gcp_project = os.getenv('GOOGLE_CLOUD_PROJECT')
    gemini_model = os.getenv('GEMINI_MODEL')
    payload = prompt + "\n\nOFFER:\n" + json.dumps(opportunity)

    # Try LangChain VertexAI wrapper for Gemini
    if gcp_project and gemini_model:
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
            ai_msg = llm.invoke(payload)
            # Extract text from AIMessage
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
            raise RuntimeError('ChatGoogleGenerativeAI VertexAI scoring failed: ' + str(e))
    else:
        # Try LangChain ChatOpenAI wrapper, then OpenAI API
        if not os.getenv('OPENAI_API_KEY'):
            raise EnvironmentError('OPENAI_API_KEY not set and no Vertex AI config found')
        try:
            try:
                from langchain.chat_models import ChatOpenAI
                model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
                chat = ChatOpenAI(model_name=model)
                txt = chat(payload)
            except Exception:
                import openai
                messages = [
                    {"role": "system", "content": "You are an opportunity rater."},
                    {"role": "user", "content": payload}
                ]
                resp = openai.ChatCompletion.create(model=os.getenv('OPENAI_MODEL','gpt-4o-mini'), messages=messages, max_tokens=300)
                txt = resp.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError('OpenAI scoring failed: ' + str(e))

    try:
        data = json.loads(txt)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", txt)
        if m:
            data = json.loads(m.group(0))
        else:
            raise
    return data
