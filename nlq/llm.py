"""One provider-agnostic call to a language model: complete(system, user) -> the model's text reply.

The rest of the chat never talks to a provider directly, so another model could be swapped in here
without touching the planner. The default provider is Google Gemini (google-genai package):
  * GEMINI_API_KEY (and optionally a spare GEMINI_API_KEY_2) and GEMINI_MODEL are read from the
    environment, the project's .env file, or Streamlit's st.secrets;
  * temperature 0, so the same question gives the same plan, and the reply is requested as JSON;
  * if a call fails and GEMINI_API_KEY_2 exists, the call is tried once more with the spare key;
  * the free tier allows only about 20 requests per day PER MODEL, so when every key has used up a
    model's quota (or the model is missing or overloaded) the next model in the list is tried;
  * every failure becomes an LLMError with a plain-English message and a fix, so the page can show
    what went wrong (no internet, invalid key, quota used up ...) instead of crashing.
The model only ever returns text; it is never given the data and never calculates numbers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = "Gemini"
# Tried in this order (after GEMINI_MODEL, if set). Each model has its own free daily quota, so a
# used-up model moves on to the next. "-latest" follows Google's newest Flash model.
DEFAULT_MODELS = ("gemini-flash-latest", "gemini-3.6-flash", "gemini-2.5-flash", "gemini-flash-lite-latest")
# Errors after which another model may still work (each model has its own quota and servers).
NEXT_MODEL = {"quota", "model", "server"}
TIMEOUT_MS = 45_000


class LLMError(Exception):
    """A failed model call, explained for the person using the dashboard.

    kind: no_key | offline | invalid_key | quota | model | server | unknown.
    """

    def __init__(self, kind: str, message: str, fix: str):
        super().__init__(message)
        self.kind, self.message, self.fix = kind, message, fix


@dataclass(frozen=True)
class Settings:
    keys: tuple[str, ...]       # main key first, then the spare key (if any)
    models: tuple[str, ...]     # the configured model first, then the defaults, in the order tried


def _secret(name: str) -> str:
    """A setting from the environment / .env, else from Streamlit secrets; '' when missing."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    try:
        import streamlit as st
        return str(st.secrets.get(name, "")).strip()
    except Exception:   # no Streamlit, or no secrets.toml
        return ""


@lru_cache(maxsize=1)
def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass


def settings() -> Settings:
    _load_dotenv()
    keys = tuple(k for k in dict.fromkeys([_secret("GEMINI_API_KEY"), _secret("GEMINI_API_KEY_2")]) if k)
    model = _secret("GEMINI_MODEL")
    return Settings(keys, tuple(dict.fromkeys(([model] if model else []) + list(DEFAULT_MODELS))))


def _no_key() -> LLMError:
    return LLMError("no_key", "No Gemini API key was found, so the chat cannot read questions.",
                    "Copy .env.example to .env, paste your key after GEMINI_API_KEY= (get one free at "
                    "aistudio.google.com/apikey), save and restart the app.")


def _is_network_error(exc: BaseException) -> bool:
    names = {c.__name__ for c in type(exc).__mro__}
    return bool(names & {"ConnectError", "ConnectTimeout", "ReadTimeout", "TimeoutException", "NetworkError",
                         "TransportError", "ConnectionError", "TimeoutError", "gaierror"})


def _classify(exc: BaseException) -> LLMError:
    """Turn any provider exception into an LLMError with a friendly message and a fix."""
    if isinstance(exc, LLMError):
        return exc
    if _is_network_error(exc):
        return LLMError("offline", "The Gemini service could not be reached (no internet connection, or it "
                                   "took too long to answer).",
                        "Check the Wi-Fi or hotspot and ask again. The Question Bank and Explore pages work "
                        "without internet.")
    code = getattr(exc, "code", None)
    text = f"{getattr(exc, 'status', '')} {getattr(exc, 'message', '')} {exc}".lower()
    if code == 429 or "resource_exhausted" in text or "quota" in text or "rate limit" in text:
        return LLMError("quota", "The Gemini key has used up its free quota or hit the rate limit (too many "
                                 "questions in a short time).",
                        "Wait a minute and ask again, or add a second key as GEMINI_API_KEY_2 in .env.")
    if code in (401, 403) or "api_key_invalid" in text or "api key not valid" in text or "permission" in text:
        return LLMError("invalid_key", "Gemini rejected the API key (it is wrong, expired or not enabled for "
                                       "the Gemini API).",
                        "Create a new key at aistudio.google.com/apikey, put it after GEMINI_API_KEY= in .env "
                        "and restart the app.")
    if code == 404 or ("not found" in text and "model" in text):
        return LLMError("model", "The Gemini model name in the settings does not exist (any more).",
                        "Set GEMINI_MODEL in .env to a current model, e.g. gemini-flash-latest, or remove the "
                        "line to use the default.")
    if isinstance(code, int) and code >= 500:
        return LLMError("server", "The Gemini service had a temporary problem on its side.",
                        "Ask again in a few seconds.")
    return LLMError("unknown", f"The Gemini call failed: {str(exc)[:200]}",
                    "Ask again; if it keeps failing, use the Question Bank or the Explore pages.")


def _gemini(key: str, model: str, system: str, user: str, json_mode: bool) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key, http_options=types.HttpOptions(
        timeout=TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1)))
    config = types.GenerateContentConfig(system_instruction=system, temperature=0,
                                         response_mime_type="application/json" if json_mode else None)
    response = client.models.generate_content(model=model, contents=user, config=config)
    text = (response.text or "").strip()
    if not text:
        raise LLMError("unknown", "Gemini sent back an empty answer.", "Ask again, perhaps in other words.")
    return text


def complete(system: str, user: str, json_mode: bool = True) -> str:
    """Send `user` with the `system` instructions to the model and return its text reply.

    For each model in turn, the main key is tried, then the spare key GEMINI_API_KEY_2. When every key
    fails with a used-up quota, a missing model or a server problem, the next model is tried; no
    internet or rejected keys stop at once. The model that answered is kept in LAST_MODEL (shown in
    the accuracy report). Raises LLMError.
    """
    global LAST_MODEL
    s = settings()
    if not s.keys:
        raise _no_key()
    error: LLMError | None = None
    for model in s.models:
        for key in s.keys:
            try:
                text = _gemini(key, model, system, user, json_mode)
                LAST_MODEL = model
                return text
            except Exception as exc:  # every provider failure is explained, never shown as a traceback
                error = _classify(exc)
                if error.kind == "offline":
                    raise error
        if error.kind not in NEXT_MODEL:
            break
    raise error


LAST_MODEL: str | None = None


def check_connection() -> tuple[bool, str]:
    """(working?, short status text) for the sidebar: is a key loaded, and does Gemini accept it?

    Asks for the model's description (models.get), which checks key and model without generating text.
    """
    s = settings()
    if not s.keys:
        return False, "No key found. Add GEMINI_API_KEY to .env."
    from google import genai
    from google.genai import types

    error: LLMError | None = None
    for key in s.keys:
        for model in s.models:
            try:
                client = genai.Client(api_key=key, http_options=types.HttpOptions(
                    timeout=15_000, retry_options=types.HttpRetryOptions(attempts=1)))
                client.models.get(model=model)
                spare = " (spare key)" if key != s.keys[0] else ""
                return True, f"Key loaded and working{spare} · {model}"
            except Exception as exc:
                error = _classify(exc)
                if error.kind != "model":
                    break
    label = {"offline": "No internet: Gemini cannot be reached.", "invalid_key": "Key loaded but rejected.",
             "quota": "Key loaded, quota used up for now.", "model": "Key loaded, model name unknown."}
    return False, label.get(error.kind, "Key loaded but Gemini is not answering.")
