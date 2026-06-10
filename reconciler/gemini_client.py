import os
import json
import re
import time
from dotenv import load_dotenv
from pathlib import Path
from google import genai
from google.genai import types

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

_client = None

def get_client():
    global _client
    if _client is None:
        use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
        
        if use_vertex:
            _client = genai.Client(
                vertexai=True,
                project=os.getenv("GOOGLE_CLOUD_PROJECT"),
                location=os.getenv("GOOGLE_CLOUD_LOCATION"),
                http_options=types.HttpOptions(api_version="v1beta1")
            )
        else:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not set in .env")
            _client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(api_version="v1alpha")
            )
    return _client


def gemini_call(prompt: str, system: str = None, retries: int = 5) -> str:
    client = get_client()
    full_prompt = f"{system}\n\n{prompt}" if system else prompt

    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_prompt
            )
            time.sleep(2)
            return response.text.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "503" in err:
                wait = 60 * (attempt + 1)
                print(f"Rate limited — waiting {wait}s (attempt {attempt+1}/{retries})...")
                time.sleep(wait)
                continue
            raise

    raise ValueError("Max retries exceeded.")


def gemini_json_call(prompt: str, system: str = None) -> dict:
    raw = gemini_call(prompt, system)
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini returned non-JSON: {raw[:300]}") from e