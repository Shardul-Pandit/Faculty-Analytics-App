"""
engine/query_parser.py
----------------------
Provider-agnostic AI layer for intent parsing and summary generation.

Providers are tried as an ordered failover chain, set via AI_PROVIDER in .env:
  AI_PROVIDER=gemini,openai   -> try Gemini, then OpenAI, then rule-based
  AI_PROVIDER=gemini          -> try Gemini, then rule-based
  AI_PROVIDER=basic           -> rule-based only (no API key required)

Supported providers:
  - "gemini"  - Google Gemini (model set by GEMINI_MODEL)
  - "openai"  - OpenAI (model set by OPENAI_MODEL)

A provider listed without an API key is skipped, never called.

The LLM NEVER performs statistical calculations.
It only:
  1. parse_intent_with_ai()     - converts natural language -> structured intent JSON
  2. generate_summary_with_ai() - turns pre-computed result dicts -> plain-English summary

Every provider call is wrapped in a try/except. On any failure (network error,
quota, bad JSON, timeout, or an intent that doesn't match the expected shape)
the next provider in the chain is tried. When every provider has failed, the
functions return None and the caller falls back to rule-based logic, so the
app always keeps working.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_INTENT_SYSTEM_PROMPT = """\
You are an intent parser for a faculty analytics application.
Convert the faculty member's question into a structured JSON object.
Return ONLY valid JSON — no commentary, no markdown fences.

JSON schema:
{
  "intent_type": "<one of: summary_one_file | summary_two_files | compare_terms | \
compare_majors | best_major | worst_major | slo_distribution | \
best_student | worst_student | top_improvers | biggest_declines | \
grade_bands | ttest | anova>",
  "file_scope": "<one of: file_a | file_b | both>",
  "filters": {
    "major":  "<string or null>",
    "term":   "<string or null>",
    "gender": "<string or null>",
    "year":   "<string or null>"
  },
  "compare_major_a": "<string or null>",
  "compare_major_b": "<string or null>",
  "top_n": "<integer or null>"
}

Intent type rules:
- "best_student" / "worst_student"  — for questions about individual student performance.
- "top_improvers"                   — improvement between two files (requires student names).
- "biggest_declines"                — biggest drops between two files.
- "grade_bands"                     — grade distribution (A/B/C/D/F buckets).
- "compare_terms"                   — same dataset across two time periods.
- "compare_majors"                  — comparing two specific majors.
- "summary_two_files"               — broad overview across two uploaded files.
- "slo_distribution"                — SLO attainment percentages.
- "best_major" / "worst_major"      — ranking majors by mean grade.
- Use null for any field you are not confident about.
"""

_SUMMARY_SYSTEM_PROMPT = """\
You summarise student assessment analytics results for non-technical faculty.
Write 1-3 clear, plain-English sentences.
- Highlight the most important finding first.
- Do NOT mention SD, median, ANOVA, t-test, or p-values unless explicitly asked.
- Do NOT mention JSON, code, or technical implementation details.
- Do NOT make up numbers that are not in the provided data.
- Be direct and faculty-friendly.
"""


# ---------------------------------------------------------------------------
# Public provider-agnostic API (ordered failover chain)
# ---------------------------------------------------------------------------

async def parse_intent_with_ai(
    question: str,
    schema_context: str,
) -> Optional[Dict[str, Any]]:
    """
    Parse a question into a structured intent dict, trying each configured
    provider in order. Returns the first valid intent, or None when every
    provider fails (the caller then uses the rule-based parser).
    """
    for name in configured_providers():
        result = await _PROVIDERS[name].parse_intent(question, schema_context)
        if is_valid_intent(result):
            logger.info("Intent parsed by %s", name)
            return result
        logger.warning("%s could not parse the intent; trying next provider", name)
    return None


async def generate_summary_with_ai(
    question: str,
    results: Dict[str, Any],
) -> Optional[str]:
    """
    Generate a plain-English summary, trying each configured provider in order.
    Returns None when every provider fails (the caller then uses the template).
    """
    for name in configured_providers():
        text = await _PROVIDERS[name].generate_summary(question, results)
        if text:
            return text
        logger.warning("%s could not write the summary; trying next provider", name)
    return None


def configured_providers() -> List[str]:
    """
    Providers from AI_PROVIDER, in order, keeping only known providers that
    have an API key. "basic" (or an empty list) means no AI providers.
    """
    from ..core.config import settings

    chain: List[str] = []
    for raw in settings.ai_provider.split(","):
        name = raw.strip().lower()
        provider = _PROVIDERS.get(name)
        if provider and name not in chain and provider.is_configured():
            chain.append(name)
    return chain


def is_valid_intent(intent: Any) -> bool:
    """
    Minimal shape check on an LLM-produced intent before it reaches the
    dispatcher, so a malformed response fails over instead of crashing.
    """
    if not isinstance(intent, dict):
        return False
    if not isinstance(intent.get("intent_type"), str) or not intent["intent_type"]:
        return False
    filters = intent.get("filters")
    if filters is not None and not isinstance(filters, dict):
        return False
    return True


# ---------------------------------------------------------------------------
# Gemini implementation
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    """Remove markdown code fences that some models add despite instructions."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop opening fence (```json or ```) and closing fence
        inner = lines[1:] if len(lines) > 1 else lines
        text = "\n".join(ln for ln in inner if ln.strip() != "```").strip()
    return text


async def _gemini_parse_intent(
    question: str,
    schema_context: str,
) -> Optional[Dict[str, Any]]:
    try:
        from google import genai  # lazy import — not required if provider != gemini
        from google.genai import types

        from ..core.config import settings

        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = (
            f"System instructions:\n{_INTENT_SYSTEM_PROMPT}\n\n"
            f"Dataset context: {schema_context}\n\n"
            f"Question: {question}"
        )

        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=512,
            ),
        )
        raw = _strip_fences(response.text or "{}")
        result = json.loads(raw)
        logger.debug("Gemini intent: %s", result.get("intent_type"))
        return result

    except json.JSONDecodeError as e:
        logger.warning("Gemini intent — bad JSON: %s", e)
        return None
    except Exception as e:
        logger.warning("Gemini intent parse failed: %s", e)
        return None


async def _gemini_generate_summary(
    question: str,
    results: Dict[str, Any],
) -> Optional[str]:
    try:
        from google import genai
        from google.genai import types

        from ..core.config import settings

        client = genai.Client(api_key=settings.gemini_api_key)
        results_str = json.dumps(results, indent=2, default=str)
        if len(results_str) > 6000:
            results_str = results_str[:6000] + "\n... (truncated)"

        prompt = (
            f"{_SUMMARY_SYSTEM_PROMPT}\n\n"
            f'Faculty question: "{question}"\n\n'
            f"Pre-computed analysis results (do not modify these numbers):\n{results_str}"
        )

        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=300,
            ),
        )
        text = (response.text or "").strip()
        return text or None

    except Exception as e:
        logger.warning("Gemini summary generation failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# OpenAI implementation
# ---------------------------------------------------------------------------

async def _openai_parse_intent(
    question: str,
    schema_context: str,
) -> Optional[Dict[str, Any]]:
    try:
        from openai import AsyncOpenAI  # lazy import

        from ..core.config import settings

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _INTENT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Dataset context: {schema_context}\n\nQuestion: {question}"
                    ),
                },
            ],
            temperature=0,
            max_tokens=512,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        return json.loads(raw)

    except json.JSONDecodeError as e:
        logger.warning("OpenAI intent — bad JSON: %s", e)
        return None
    except Exception as e:
        logger.warning("OpenAI intent parse failed: %s", e)
        return None


async def _openai_generate_summary(
    question: str,
    results: Dict[str, Any],
) -> Optional[str]:
    try:
        from openai import AsyncOpenAI

        from ..core.config import settings

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        results_str = json.dumps(results, indent=2, default=str)
        if len(results_str) > 6000:
            results_str = results_str[:6000] + "\n... (truncated)"

        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f'Faculty question: "{question}"\n\n'
                        f"Analysis results:\n{results_str}"
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=400,
        )
        text = (response.choices[0].message.content or "").strip()
        return text or None

    except Exception as e:
        logger.warning("OpenAI summary generation failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Provider:
    parse_intent: Callable[[str, str], Awaitable[Optional[Dict[str, Any]]]]
    generate_summary: Callable[[str, Dict[str, Any]], Awaitable[Optional[str]]]
    is_configured: Callable[[], bool]


def _gemini_configured() -> bool:
    from ..core.config import settings
    return bool(settings.gemini_api_key)


def _openai_configured() -> bool:
    from ..core.config import settings
    return bool(settings.openai_api_key and settings.openai_api_key.startswith("sk-"))


# The lambdas look the implementation up at call time (not import time), so a
# test can replace e.g. _gemini_parse_intent with a fake that simulates an outage.
_PROVIDERS: Dict[str, _Provider] = {
    "gemini": _Provider(
        parse_intent=lambda q, ctx: _gemini_parse_intent(q, ctx),
        generate_summary=lambda q, r: _gemini_generate_summary(q, r),
        is_configured=_gemini_configured,
    ),
    "openai": _Provider(
        parse_intent=lambda q, ctx: _openai_parse_intent(q, ctx),
        generate_summary=lambda q, r: _openai_generate_summary(q, r),
        is_configured=_openai_configured,
    ),
}
