"""
test_models.py - בדיקות לבחירת מודל, הגדרות-לפי-מודל ושרשרת הנפילה.
הרץ: pytest test_models.py -v   (בלי רשת - _run_session מדומה)
"""
import asyncio

import pytest

import voice_engine as ve
from google.genai import types


def _engine(**kw):
    base = dict(api_key="x", deep_thinking=True, thinking_level="medium",
                web_search=True)
    base.update(kw)
    return ve.VoiceEngine(**base)


def test_default_model_is_latest():
    e = _engine()
    assert e.model == "gemini-3.8-live"
    assert ve.MODEL_FALLBACK_CHAIN[0] == "gemini-3.8-live"


def test_unknown_model_falls_back_to_default():
    e = _engine(model="gemini-99-live")
    assert e.model == ve.DEFAULT_MODEL


def test_config_per_model():
    e = _engine()
    # 3.8 בסיסי: בלי thinking_config, עם דחיסת הקשר והמשך סשן, v1beta
    client, cfg = e._build_conversation_setup("gemini-3.8-live")
    assert "thinking_config" not in cfg
    assert isinstance(cfg["context_window_compression"],
                      types.ContextWindowCompressionConfig)
    assert isinstance(cfg["session_resumption"], types.SessionResumptionConfig)
    assert cfg["tools"] == [{"google_search": {}}]

    # 3.8 extended: thinking_level (לא budget)
    _, cfg = e._build_conversation_setup("gemini-3.8-live-extended-thinking")
    tc = cfg["thinking_config"]
    assert tc.thinking_level == "MEDIUM"
    assert tc.thinking_budget is None

    # 2.5: thinking_budget (לא level)
    _, cfg = e._build_conversation_setup(
        "gemini-2.5-flash-native-audio-preview-12-2025")
    tc = cfg["thinking_config"]
    assert tc.thinking_budget == 2048
    assert tc.thinking_level is None


def test_extended_maps_minimal_to_low():
    e = _engine(thinking_level="minimal")
    _, cfg = e._build_conversation_setup("gemini-3.8-live-extended-thinking")
    assert cfg["thinking_config"].thinking_level == "LOW"


def test_tools_disabled_after_rejection():
    e = _engine()
    e._tools_disabled = True
    _, cfg = e._build_conversation_setup("gemini-3.8-live")
    assert "tools" not in cfg


def test_fallback_chain_moves_to_next_model():
    """המודל הנבחר לא זמין → עוברים אוטומטית לבא בתור, בלי להפיל את השיחה."""
    e = _engine(model="gemini-3.8-live-extended-thinking")
    e._running = True
    tried = []

    async def fake_run(client, model, config):
        tried.append(model)
        if model == "gemini-3.8-live-extended-thinking":
            raise ve._ModelUnavailable("404 not found")
        return None

    e._run_session = fake_run
    asyncio.run(e._session_main())
    assert tried == ["gemini-3.8-live-extended-thinking", "gemini-3.8-live"]
    assert e.active_model == "gemini-3.8-live"


def test_tools_rejected_retries_same_model_without_tools():
    e = _engine()
    e._running = True
    tried = []

    async def fake_run(client, model, config):
        tried.append((model, "tools" in config))
        if "tools" in config:
            raise ve._ToolsUnsupported("tool google_search is not supported")
        return None

    e._run_session = fake_run
    asyncio.run(e._session_main())
    assert tried == [("gemini-3.8-live", True), ("gemini-3.8-live", False)]


def test_all_models_unavailable_is_fatal():
    e = _engine()
    e._running = True

    async def fake_run(client, model, config):
        raise ve._ModelUnavailable("404")

    e._run_session = fake_run
    with pytest.raises(ve._FatalError):
        asyncio.run(e._session_main())


def test_run_session_classifies_errors():
    """שגיאות מהשרת ממופות נכון: מודל חסר / כלים / קטלני."""
    e = _engine()
    e._running = True

    class _Boom:
        def __init__(self, msg):
            self.msg = msg

        def connect(self, model, config):
            raise RuntimeError(self.msg)

    class _Client:
        def __init__(self, msg):
            self.aio = type("A", (), {"live": _Boom(msg)})()

    async def run(msg, cfg):
        await e._run_session(_Client(msg), "m", cfg)

    with pytest.raises(ve._ModelUnavailable):
        asyncio.run(run("models/m was not found", {}))
    with pytest.raises(ve._ToolsUnsupported):
        asyncio.run(run("400 tool google_search is not supported",
                        {"tools": [{"google_search": {}}]}))
    with pytest.raises(ve._FatalError):
        asyncio.run(run("API_KEY_INVALID", {}))
