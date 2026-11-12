"""Deterministic structural contract between a template and its document.

The headings in a template — or, for an edit, in the original document being
refined — name the sections the generated document must contain. The same
contract is enforced on the first draft and again after every rewrite
(refinement retry, language repair), so a rewrite that breaks the structure
fails like any other validation error and is never saved as a document.

Parsing is pure regex over text: no model calls, no network, no new
dependencies. Supported shapes:

- sources with at least one parseable heading (a Markdown ATX ``## Name`` line
  or a standalone bold ``**Name**`` label): every parsed section must appear in
  the document exactly once, with content beneath it;
- sources with no heading lines at all carry no structural contract; the
  existing non-empty-content checks still apply.

A heading marker without a title (a line holding only ``#``/``##``) cannot name
a section, so such a source is unsupported and fails validation instead of
passing silently.
"""
import re
from typing import List, Optional, Tuple


class DocumentStructureError(ValueError):
    """Structural validation failed; this text must not be saved as a document."""


_ATX_HEADING = re.compile(r'^#{1,6}\s+(?P<name>.+?)\s*#*\s*$')
_BARE_HEADING = re.compile(r'^#{1,6}\s*$')
_BOLD_HEADING = re.compile(r'^\*\*(?P<name>[^*\n]+?)\s*:?\*\*:?\s*$')
# A filled-in label: ``**Date:** 12 November``. Only the colon form counts, so
# a sentence that merely opens with bold text is not read as a section.
_BOLD_INLINE = re.compile(r'^\*\*(?P<name>[^*\n]+?)(?::\*\*|\*\*:)\s*(?P<value>\S.*)$')
_BOLD_LEVEL = 7  # below every ATX heading


def _normalise(name: str) -> str:
    return re.sub(r'\s+', ' ', name.strip().rstrip(':')).casefold()


def _parse_sections(text: str) -> List[Tuple[str, str, str, bool]]:
    """Return ``(display name, normalised name, body, has_subsections)`` per
    heading, in order. ``has_subsections`` marks a heading directly followed
    by a deeper one (a title or a parent of sub-headings): its content lives
    in those subsections, so it has no body of its own.

    Raises ``DocumentStructureError`` for a heading marker with no section
    title: the structure cannot be named, so it must fail rather than pass
    silently.
    """
    sections: List[Tuple[str, str, str, bool]] = []
    display: Optional[str] = None
    normalised = ''
    level = 0
    body: List[str] = []
    for line in text.splitlines():
        bare = _BARE_HEADING.match(line)
        atx = None if bare else _ATX_HEADING.match(line)
        bold = None if bare or atx else (_BOLD_HEADING.match(line) or _BOLD_INLINE.match(line))
        if bare:
            raise DocumentStructureError(
                'A heading marker has no section title, so the required '
                'document structure cannot be validated.'
            )
        if atx or bold:
            new_level = len(line) - len(line.lstrip('#')) if atx else _BOLD_LEVEL
            if display is not None:
                text_body = '\n'.join(body).strip()
                sections.append((display, normalised, text_body, not text_body and new_level > level))
            level = new_level
            heading = (atx or bold).group('name')
            normalised = _normalise(heading)
            if not normalised:
                raise DocumentStructureError(
                    'A heading marker has no section title, so the required '
                    'document structure cannot be validated.'
                )
            display = heading.strip()
            body = [bold.group('value')] if bold and bold.re is _BOLD_INLINE else []
        elif display is not None:
            body.append(line)
    if display is not None:
        sections.append((display, normalised, '\n'.join(body).strip(), False))
    return sections


def structural_contract(source: str) -> Optional[tuple]:
    """Return the required section display names, or ``None`` when the source
    defines no section headings (a supported, contract-free shape)."""
    seen = set()
    names: List[str] = []
    for display, normalised, _body, _parent in _parse_sections(source):
        if normalised not in seen:
            seen.add(normalised)
            names.append(display)
    return tuple(names) if names else None


def structure_problems(contract, document: str) -> List[str]:
    """Return every way ``document`` fails the contract; empty when it passes
    (including when the contract is ``None``)."""
    if not contract:
        return []
    counts = {}
    bodies = {}
    for _display, normalised, body, has_subsections in _parse_sections(document):
        counts[normalised] = counts.get(normalised, 0) + 1
        bodies[normalised] = body or has_subsections
    problems: List[str] = []
    for name in contract:
        key = _normalise(name)
        count = counts.get(key, 0)
        if count == 0:
            problems.append(f'required section "{name}" is missing')
        elif count > 1:
            problems.append(f'required section "{name}" appears {count} times')
        elif not bodies.get(key):
            problems.append(f'required section "{name}" is empty')
    return problems


def validate_document_structure(contract, document: str) -> None:
    """Raise ``DocumentStructureError`` unless ``document`` satisfies ``contract``."""
    problems = structure_problems(contract, document)
    if problems:
        raise DocumentStructureError(
            'The document does not match the required template structure: '
            + '; '.join(problems)
            + '. Please try again. No document has been saved by this generation.'
        )
