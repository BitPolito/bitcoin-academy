"""LLM chain helpers for study action generation."""
import logging
import os

logger = logging.getLogger(__name__)

_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
_TIMEOUT = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))


def run_llm_chain(prompt_template: str, query: str, context: str) -> str | None:
    """Render prompt_template, call LLM, return generated text.

    Returns None if OPENAI_API_KEY is not set or the call fails.
    Callers are responsible for providing a fallback when None is returned.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.debug("OPENAI_API_KEY not set — skipping LLM generation")
        return None

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import PromptTemplate

        llm = ChatOpenAI(model=_MODEL, temperature=0.3, timeout=_TIMEOUT)
        prompt = PromptTemplate.from_template(prompt_template)
        chain = prompt | llm
        result = chain.invoke({"query": query, "context": context})
        text = result.content if hasattr(result, "content") else str(result)
        return str(text) if text else None
    except ImportError:
        logger.warning("langchain_openai not installed — LLM generation unavailable")
        return None
    except Exception as exc:
        logger.warning("LLM chain failed: %s", exc)
        return None
