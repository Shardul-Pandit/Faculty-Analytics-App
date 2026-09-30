"""
Tests for the LLM failover chain in engine/query_parser.py.

No real API is ever called. Provider implementations are replaced with fakes
that succeed, fail, or return malformed output, and the tests check which
providers are tried, in what order, and what the caller gets back.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

import app.engine.query_parser as qp
from app.core.config import settings

VALID_INTENT = {"intent_type": "grade_bands", "filters": {"major": None}}


@pytest.fixture
def chain(monkeypatch):
    """Configure providers and keys for one test; settings are restored afterwards."""
    def configure(providers, gemini_key="gem-test-key", openai_key="sk-test-key"):
        monkeypatch.setattr(settings, "ai_provider", providers)
        monkeypatch.setattr(settings, "gemini_api_key", gemini_key)
        monkeypatch.setattr(settings, "openai_api_key", openai_key)
    return configure


@pytest.fixture
def calls(monkeypatch):
    """
    Replace both providers with recording fakes. Each fake's behaviour is set by
    the test through `outcomes`: a value to return, or an Exception to raise.
    """
    log = []
    outcomes = {"gemini": None, "openai": None}

    def fake(name, kind):
        async def _impl(*args):
            log.append(f"{name}.{kind}")
            outcome = outcomes[name]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return _impl

    for name in ("gemini", "openai"):
        monkeypatch.setattr(qp, f"_{name}_parse_intent", fake(name, "intent"))
        monkeypatch.setattr(qp, f"_{name}_generate_summary", fake(name, "summary"))
    return SimpleNamespace(log=log, outcomes=outcomes)


def parse(question="q"):
    return asyncio.run(qp.parse_intent_with_ai(question, "ctx"))


def summarize():
    return asyncio.run(qp.generate_summary_with_ai("q", {"x": 1}))


# ---------------------------------------------------------------------------
# Which providers are in the chain
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("setting, expected", [
    ("basic", []),
    ("", []),
    ("gemini", ["gemini"]),
    ("gemini,openai", ["gemini", "openai"]),
    ("openai,gemini", ["openai", "gemini"]),
    (" Gemini , OPENAI ", ["gemini", "openai"]),
    ("gemini,gemini,openai", ["gemini", "openai"]),
    ("gemini,claude,openai", ["gemini", "openai"]),   # unknown providers are ignored
])
def test_chain_order_follows_setting(chain, setting, expected):
    chain(setting)
    assert qp.configured_providers() == expected


def test_provider_without_key_is_skipped(chain):
    chain("gemini,openai", gemini_key="")
    assert qp.configured_providers() == ["openai"]


def test_openai_key_must_look_valid(chain):
    chain("gemini,openai", openai_key="not-an-openai-key")
    assert qp.configured_providers() == ["gemini"]


# ---------------------------------------------------------------------------
# Failover behaviour for intent parsing
# ---------------------------------------------------------------------------

def test_first_provider_success_stops_the_chain(chain, calls):
    chain("gemini,openai")
    calls.outcomes["gemini"] = VALID_INTENT
    assert parse() == VALID_INTENT
    assert calls.log == ["gemini.intent"]


def test_fails_over_to_second_provider(chain, calls):
    chain("gemini,openai")
    calls.outcomes["gemini"] = None                      # e.g. quota exceeded
    calls.outcomes["openai"] = {"intent_type": "best_major"}
    assert parse()["intent_type"] == "best_major"
    assert calls.log == ["gemini.intent", "openai.intent"]


def test_malformed_intent_triggers_failover(chain, calls):
    chain("gemini,openai")
    calls.outcomes["gemini"] = {"intent_type": 42, "filters": "none"}   # wrong types
    calls.outcomes["openai"] = VALID_INTENT
    assert parse() == VALID_INTENT
    assert calls.log == ["gemini.intent", "openai.intent"]


def test_all_providers_failing_returns_none_for_rule_based_fallback(chain, calls):
    chain("gemini,openai")
    assert parse() is None
    assert calls.log == ["gemini.intent", "openai.intent"]


def test_no_configured_provider_calls_nothing(chain, calls):
    chain("basic")
    assert parse() is None
    assert calls.log == []


def test_unkeyed_provider_is_never_called(chain, calls):
    chain("gemini,openai", openai_key="")
    calls.outcomes["gemini"] = None
    assert parse() is None
    assert calls.log == ["gemini.intent"]


# ---------------------------------------------------------------------------
# Failover behaviour for summaries
# ---------------------------------------------------------------------------

def test_summary_fails_over_on_empty_text(chain, calls):
    chain("gemini,openai")
    calls.outcomes["gemini"] = ""
    calls.outcomes["openai"] = "OpenAI summary"
    assert summarize() == "OpenAI summary"
    assert calls.log == ["gemini.summary", "openai.summary"]


def test_summary_returns_none_when_all_fail(chain, calls):
    chain("gemini")
    assert summarize() is None


# ---------------------------------------------------------------------------
# Intent validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("intent, valid", [
    ({"intent_type": "grade_bands"}, True),
    ({"intent_type": "grade_bands", "filters": None}, True),
    ({"intent_type": "grade_bands", "filters": {}}, True),
    ({"intent_type": ""}, False),
    ({"intent_type": None}, False),
    ({"filters": {}}, False),
    ({"intent_type": "grade_bands", "filters": ["major"]}, False),
    (["not", "a", "dict"], False),
    (None, False),
])
def test_is_valid_intent(intent, valid):
    assert qp.is_valid_intent(intent) is valid


# ---------------------------------------------------------------------------
# The real provider implementations never raise: errors become None
# ---------------------------------------------------------------------------

class _FakeGenaiClient:
    """Stands in for google.genai.Client. `reply` is the model's text, or an Exception."""
    reply = None

    def __init__(self, api_key):
        async def generate_content(**kwargs):
            if isinstance(self.reply, Exception):
                raise self.reply
            return SimpleNamespace(text=self.reply)
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))


@pytest.fixture
def fake_genai(monkeypatch):
    monkeypatch.setattr("google.genai.Client", _FakeGenaiClient)
    return _FakeGenaiClient


def test_gemini_outage_returns_none(fake_genai):
    fake_genai.reply = ConnectionError("503 Service Unavailable")
    assert asyncio.run(qp._gemini_parse_intent("q", "ctx")) is None
    assert asyncio.run(qp._gemini_generate_summary("q", {})) is None


def test_gemini_bad_json_returns_none(fake_genai):
    fake_genai.reply = "Sure! Here's the intent you asked for."
    assert asyncio.run(qp._gemini_parse_intent("q", "ctx")) is None


def test_gemini_fenced_json_is_parsed(fake_genai):
    fake_genai.reply = "```json\n" + json.dumps(VALID_INTENT) + "\n```"
    assert asyncio.run(qp._gemini_parse_intent("q", "ctx")) == VALID_INTENT


def test_openai_outage_returns_none(monkeypatch):
    class FailingOpenAI:
        def __init__(self, api_key):
            raise ConnectionError("simulated outage")
    monkeypatch.setattr("openai.AsyncOpenAI", FailingOpenAI)
    assert asyncio.run(qp._openai_parse_intent("q", "ctx")) is None
    assert asyncio.run(qp._openai_generate_summary("q", {})) is None


@pytest.mark.parametrize("raw, expected", [
    ('{"a": 1}', '{"a": 1}'),
    ('```json\n{"a": 1}\n```', '{"a": 1}'),
    ('```\n{"a": 1}\n```', '{"a": 1}'),
])
def test_strip_fences(raw, expected):
    assert qp._strip_fences(raw) == expected
