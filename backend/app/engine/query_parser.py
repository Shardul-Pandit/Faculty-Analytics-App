"""
engine/query_parser.py
----------------------
Provider-agnostic AI layer for intent parsing and summary generation.

Supported providers (selected via AI_PROVIDER in .env):
  - "gemini"  — Google Gemini (model set by GEMINI_MODEL, default gemini-3.5-flash-lite)
  - "openai"  — OpenAI (gpt-4o-mini)
  - "basic"   — rule-based only (no API key required)

The LLM NEVER performs statistical calculations.
It only:
  1. parse_intent_with_ai()    — converts natural language → structured intent JSON
  2. generate_summary_with_ai() — turns pre-computed result dicts → plain-English summary

Every AI call is wrapped in a try/except.  On any failure (network error, quota,
bad JSON, timeout) the function returns None and the caller silently falls back
to rule-based logic so the app always keeps working.

Legacy function signatures (parse_question_to_intent / generate_nl_summary) are
kept so any direct callers continue to work without modification.
"""

import json
import logging
from typing import Any, Dict, Optional

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
# Public provider-agnostic API
# ---------------------------------------------------------------------------

async def parse_intent_with_ai(
    question: str,
    schema_context: str,
) -> Optional[Dict[str, Any]]:
    """
    Parse a question into a structured intent dict using the configured AI provider.
    Returns None on any failure so the caller can use rule-based fallback.
    """
    from ..core.config import settings
    provider = settings.ai_provider.lower()

    if provider == "gemini" and settings.gemini_api_key:
        return await _gemini_parse_intent(question, schema_context)

    if provider == "openai" and settings.openai_api_key and settings.openai_api_key.startswith("sk-"):
        return await _openai_parse_intent(question, schema_context)

    return None


async def generate_summary_with_ai(
    question: str,
    results: Dict[str, Any],
) -> Optional[str]:
    """
    Generate a plain-English summary using the configured AI provider.
    Returns None on any failure so the caller uses the template summary.
    """
    from ..core.config import settings
    provider = settings.ai_provider.lower()

    if provider == "gemini" and settings.gemini_api_key:
        return await _gemini_generate_summary(question, results)

    if provider == "openai" and settings.openai_api_key and settings.openai_api_key.startswith("sk-"):
        return await _openai_generate_summary(question, results)

    return None


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
            model="gpt-4o-mini",
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
            model="gpt-4o-mini",
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
# Legacy shims — kept so any direct callers continue to work
# ---------------------------------------------------------------------------

async def parse_question_to_intent(
    question: str,
    schema_context: str,
    client: Any,  # ignored — provider resolved from config
) -> Dict[str, Any]:
    """Legacy signature.  Delegates to parse_intent_with_ai()."""
    result = await parse_intent_with_ai(question, schema_context)
    return result or {}


async def generate_nl_summary(
    question: str,
    results: Dict[str, Any],
    client: Any,  # ignored — provider resolved from config
) -> str:
    """Legacy signature.  Delegates to generate_summary_with_ai()."""
    result = await generate_summary_with_ai(question, results)
    return result or ""
