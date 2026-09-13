"""Read the two supported edit envelopes without treating source text as instructions."""
import math
import re
from typing import Optional, Tuple


class RefinementValidationError(ValueError):
    """An edit failed a measurable request; it must not be saved as a document."""


def refinement_parts(content: str) -> Optional[Tuple[str, str]]:
    if 'ORIGINAL DOCUMENT:' in content and 'REQUESTED MODIFICATIONS:' in content:
        original, instructions = content.split('ORIGINAL DOCUMENT:', 1)[1].rsplit('REQUESTED MODIFICATIONS:', 1)
        return original.strip(), instructions.rsplit('REFINED DOCUMENT:', 1)[0].strip()
    if content.startswith('CRITICAL INSTRUCTIONS FOR AI ASSISTANT:') and '**Original Document:**' in content:
        instructions, original = content.split('**Original Document:**', 1)
        instructions = instructions.split('**Refinement Instructions:**', 1)[-1]
        return original.split('**Instructions for refinement:**', 1)[0].strip(), instructions.strip()
    return None


def shortening_word_limit(original: str, instructions: str) -> Optional[int]:
    """Resolve common explicit shortening requests against the document being edited.

    Never truncate clinical content to meet the limit: generation must retry or fail.
    Percentages are only recognised next to a shortening verb, not in clinical data.
    """
    count = len(original.split())
    if not count:
        return None
    text = instructions.lower()
    # A negated request must not become an instruction to shorten.
    if re.search(r"(?:do not|don't|never)\s+(?:shorten|reduce|condense|make.*?concise)", text):
        return None
    target = r"(?:\s+(?:(?:the|this|that|my|original|current|existing|whole|entire|full)\s+)?(?:document|report|note|text|word count|length|it))?"
    percent = re.search(r'\b(?:shorten|reduce|cut|condense)' + target + r'\s+(by|to)\s+(\d{1,2}(?:\.\d+)?)\s*(?:%|percent)', text)
    if percent:
        fraction = float(percent.group(2)) / 100
        if percent.group(1) == 'by':
            fraction = 1 - fraction
        return max(1, math.floor(count * fraction))
    if re.search(r'\b(?:shorten|reduce|cut|condense)' + target + r'\s+(?:in|by|to)\s+half\b', text):
        return max(1, count // 2)
    words = re.search(r'(?:to|under|at most|maximum(?: of)?|no more than)\s+(\d+)\s+words?\b', text)
    if words and int(words.group(1)) < count:
        return max(1, int(words.group(1)) - (1 if words.group(0).startswith('under') else 0))
    if (re.search(r'\b(?:shorten|condense)' + target + r'(?=\s*(?:[.!?]|$))', text)
            or re.search(r'\bmake' + target + r'\s+(?:much\s+)?(?:shorter|more concise|less verbose)\b', text)
            or re.fullmatch(r'\s*(?:shorter|more concise|less verbose)[.!?]?\s*', text)):
        return max(1, math.floor(count * 0.75))
    return None
