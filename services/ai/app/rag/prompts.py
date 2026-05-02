"""Prompt templates for study action LLM chains."""

EXPLAIN_PROMPT = """\
You are a Bitcoin expert tutor. Explain the concept of '{query}' based ONLY on the
following source passages. Include specific details and examples from the text.
If the passages do not contain enough information, say so clearly.

Source passages:
{context}

Explanation:"""

SUMMARIZE_PROMPT = """\
You are a Bitcoin expert tutor. Summarize the following passages about '{query}'
in a clear, structured way. Preserve all key technical details and definitions.
Use bullet points where appropriate.

Source passages:
{context}

Summary:"""

OPEN_Q_PROMPT = """\
You are a Bitcoin expert tutor creating study materials. Generate exactly 5
open-ended study questions about '{query}' based ONLY on the following passages.
Each question must require conceptual understanding, not simple recall.
Number the questions 1-5.

Source passages:
{context}

Study questions:"""

QUIZ_PROMPT = """\
You are a Bitcoin expert tutor. Generate exactly 3 multiple-choice quiz questions
about '{query}' based ONLY on the following passages.
Format each question exactly as:

Q: <question text>
A) <option>
B) <option>
C) <option>
D) <option>
Answer: <letter>) <brief explanation>

Source passages:
{context}

Quiz:"""

ORAL_PROMPT = """\
You are a university oral exam examiner in a Bitcoin and blockchain course.
Generate exactly 3 oral exam questions about '{query}' from the following passages.
Order them from most conceptual to most technical.
For each question, add a brief note on what a complete answer should cover.

Format:
Q<n>: <question>
Expected: <what a good answer should cover>

Source passages:
{context}

Oral exam questions:"""
