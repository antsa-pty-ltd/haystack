"""Read the two supported edit envelopes without treating source text as instructions."""
import math
import re
from typing import Optional, Set, Tuple


class RefinementValidationError(ValueError):
    """An edit failed a measurable request; it must not be saved as a document."""


_NAME_TOKEN = re.compile(
    r'\[(?P<owner>CLIENT|PRACTITIONER)_(?P<part>FIRST_NAME|LAST_NAME|NAME)(?P<suffix>_\d+)?\]'
)
_NAME_REMOVAL = re.compile(
    r'\b(?:remove|omit|delete|exclude|drop)\b(?:(?![.!?\n]).){0,100}?'
    + _NAME_TOKEN.pattern,
    re.IGNORECASE,
)
_NEGATED_REMOVAL = re.compile(r"(?:do\s+not|don't|never)\s*$", re.IGNORECASE)


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
        # The practitioner requested a qualitative improvement, not a numeric
        # reduction. Requiring an arbitrary 25% cut rejects genuinely shorter
        # documents and misrepresents the request as a precise length target.
        return max(1, count - 1)
    return None


def requested_name_removal_tokens(instructions: str) -> Set[str]:
    """Return privacy tokens which must be absent after an explicit name edit.

    API-side refinement tokenization decomposes a full name into first/last
    tokens. If the model reintroduces the corresponding full-name token, API
    rehydration would restore the surname, so that token is forbidden too.
    """
    forbidden: Set[str] = set()
    for match in _NAME_REMOVAL.finditer(instructions):
        if _NEGATED_REMOVAL.search(instructions[max(0, match.start() - 20):match.start()]):
            continue
        owner = match.group('owner').upper()
        part = match.group('part').upper()
        suffix = match.group('suffix') or ''
        forbidden.add(f'[{owner}_{part}{suffix}]')
        if part in {'FIRST_NAME', 'LAST_NAME'}:
            forbidden.add(f'[{owner}_NAME{suffix}]')
        elif part == 'NAME':
            forbidden.update({
                f'[{owner}_FIRST_NAME{suffix}]',
                f'[{owner}_LAST_NAME{suffix}]',
            })
    return forbidden


def unmet_name_removals(instructions: str, generated_content: str) -> Set[str]:
    """Return requested name-removal tokens still present in model output."""
    return {
        token for token in requested_name_removal_tokens(instructions)
        if token in generated_content
    }
