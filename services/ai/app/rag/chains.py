"""Prompt building helpers for study action generation."""


def build_prompt(context: str, question: str, instructions: str = "") -> str:
    """Build a structured prompt with explicit section delimiters.

    Used to format the human-turn message before sending to QVAC /generate.
    Delimiters reduce prompt-injection risk and improve instruction following.
    """
    parts: list[str] = []
    if context:
        parts.append(f"=== CONTEXT ===\n{context}\n=== END CONTEXT ===")
    parts.append(f"=== QUESTION ===\n{question}\n=== END QUESTION ===")
    if instructions:
        parts.append(f"=== INSTRUCTIONS ===\n{instructions}\n=== END INSTRUCTIONS ===")
    return "\n\n".join(parts)
