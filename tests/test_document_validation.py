"""Structural template contract for generated clinical documents.

The headings in a template (or in the original document of a refinement
request) are a contract: every required section must appear in the generated
document exactly once, with content beneath it. The same deterministic — never
model-based — validation runs on the first draft and again after every rewrite
(refinement retry, language repair). A failure surfaces as HTTP 422 from the
agentic endpoint and must never be persisted as a successful document.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from document_generation.agentic_endpoint import generate_document_from_template_agentic
from document_generation.generator import generate_document_from_context
from document_generation.structure import (
    DocumentStructureError,
    structure_problems,
    structural_contract,
    validate_document_structure,
)

CONTRACT_TEMPLATE = '## Presenting Issues\n\n## Interventions\n\n## Risks And Actions\n'
COMPLETE_DOCUMENT = (
    '## Presenting Issues\n\nStress at work.\n\n'
    '## Interventions\n\nSlow breathing.\n\n'
    '## Risks And Actions\n\nMonitor mood daily.\n'
)


def client_for(*outputs):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=[
        value if isinstance(value, Exception) else SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=value), finish_reason='stop')]
        ) for value in outputs
    ])
    return client


def generation_arguments(client, **changes):
    args = dict(
        segments=[{'text': 'The client discussed work stress. Breathing exercises helped.', 'speaker': 'Client'}],
        template={'id': 't', 'name': 'Care plan', 'content': CONTRACT_TEMPLATE},
        client_info={'name': '[CLIENT_NAME]'}, practitioner_info={'name': '[PRACTITIONER_NAME]'},
        generation_instructions=None, openai_client=client,
    )
    args.update(changes)
    return args


def endpoint_request(template_content):
    return SimpleNamespace(
        generationId='synthetic-validation',
        template={'id': 't', 'name': 'Care plan', 'content': template_content},
        sessionIds=[], sessionData=[],
        dictatedNotes=[{'content': 'Stress at work.', 'title': 'Note', 'createdAt': ''}],
        clientInfo={'name': '[CLIENT_NAME]'}, practitionerInfo={'name': '[PRACTITIONER_NAME]'},
        generationInstructions=None,
    )


def run_endpoint(request, client, progress=None):
    return asyncio.run(generate_document_from_template_agentic(
        request, MagicMock(), 'Bearer synthetic', 'synthetic-profile', client,
        progress or AsyncMock(), AsyncMock(return_value={'is_violation': False}), AsyncMock(),
    ))


def test_absent_required_section_is_a_validation_failure():
    contract = structural_contract(CONTRACT_TEMPLATE)
    document = '## Presenting Issues\n\nStress at work.\n'
    problems = structure_problems(contract, document)
    assert any('Interventions' in problem and 'missing' in problem for problem in problems)
    with pytest.raises(DocumentStructureError, match='Interventions'):
        validate_document_structure(contract, document)


def test_empty_required_section_is_a_validation_failure():
    contract = structural_contract(CONTRACT_TEMPLATE)
    document = '## Presenting Issues\n\n## Interventions\n\nSlow breathing.\n## Risks And Actions\n\nMonitor mood.\n'
    problems = structure_problems(contract, document)
    assert any('Presenting Issues' in problem and 'empty' in problem for problem in problems)
    with pytest.raises(DocumentStructureError, match='empty'):
        validate_document_structure(contract, document)


def test_duplicate_required_section_is_a_validation_failure():
    contract = structural_contract(CONTRACT_TEMPLATE)
    document = (
        '## Presenting Issues\n\nStress at work.\n\n## Presenting Issues\n\nMore stress.\n\n'
        '## Interventions\n\nSlow breathing.\n\n## Risks And Actions\n\nMonitor mood.\n'
    )
    problems = structure_problems(contract, document)
    assert any('Presenting Issues' in problem and '2 times' in problem for problem in problems)
    with pytest.raises(DocumentStructureError, match='2 times'):
        validate_document_structure(contract, document)


def test_template_without_headings_carries_no_structural_contract():
    # A prose template is a supported shape: no contract to enforce, and the
    # existing non-empty-content checks still apply upstream.
    assert structural_contract('Write a brief session note about the client.') is None
    assert structure_problems(None, 'Any prose at all.') == []


def test_unparseable_heading_marker_fails_validation_instead_of_passing_silently():
    with pytest.raises(DocumentStructureError, match='no section title'):
        structural_contract('## Presenting Issues\n\n##\n\n## Risks And Actions\n')


def test_bold_template_labels_match_markdown_headings_in_the_document():
    contract = structural_contract('**Presenting Issues:**\n\n**Interventions:**\n')
    assert contract == ('Presenting Issues', 'Interventions')
    document = '## Presenting Issues\n\nStress.\n\n## Interventions\n\nBreathing.\n'
    assert structure_problems(contract, document) == []


def test_missing_section_is_retried_within_the_bound_then_failed_not_saved():
    incomplete = '## Presenting Issues\n\nStress at work.\n'
    client = client_for(incomplete, incomplete, incomplete)
    with pytest.raises(DocumentStructureError, match='Interventions'):
        asyncio.run(generate_document_from_context(**generation_arguments(client)))
    # The existing bounded-retry shape: the draft plus at most two repairs.
    assert client.chat.completions.create.await_count == 3
    repair_request = client.chat.completions.create.call_args_list[1].kwargs['messages'][-1]['content']
    assert 'Interventions' in repair_request
    assert 'required template structure' in repair_request


TWO_SECTION_TEMPLATE = '## Presenting Issues\n\n## Interventions\n'


def test_language_repair_that_breaks_structure_is_revalidated_and_fails():
    draft = (
        '## Presenting Issues\n\nThe client reported तनाव before presentations.\n\n'
        '## Interventions\n\nSlow breathing.\n'
    )
    broken_repair = '## Presenting Issues\n\nStress before presentations.\n'
    client = client_for(draft, broken_repair)
    with pytest.raises(DocumentStructureError, match='Interventions'):
        asyncio.run(generate_document_from_context(**generation_arguments(
            client, template={'id': 't', 'name': 'Care plan', 'content': TWO_SECTION_TEMPLATE},
        )))
    # One draft and one language repair; the repaired text failed the same
    # structural validation and no document was returned.
    assert client.chat.completions.create.await_count == 2


def test_valid_language_repair_passes_validation_and_is_returned_as_the_document():
    draft = (
        '## Presenting Issues\n\nThe client reported तनाव before presentations.\n\n'
        '## Interventions\n\nSlow breathing.\n'
    )
    repaired = (
        '## Presenting Issues\n\nStress before presentations.\n\n'
        '## Interventions\n\nSlow breathing.\n'
    )
    client = client_for(draft, repaired)
    result = asyncio.run(generate_document_from_context(**generation_arguments(
        client, template={'id': 't', 'name': 'Care plan', 'content': TWO_SECTION_TEMPLATE},
    )))
    assert result['content'] == repaired
    assert client.chat.completions.create.await_count == 2


def test_structural_retry_exhaustion_reaches_the_client_as_http_422():
    progress = AsyncMock()
    incomplete = '## Presenting Issues\n\nStress at work.\n'
    client = client_for(incomplete, incomplete, incomplete)
    with pytest.raises(HTTPException) as error:
        run_endpoint(endpoint_request(CONTRACT_TEMPLATE), client, progress)
    assert error.value.status_code == 422
    assert 'Interventions' in error.value.detail
    assert client.chat.completions.create.await_count == 3
    # A failed validation must never be announced as a finished document.
    assert not any(
        call.args[1].get('stage') == 'document_ready' for call in progress.call_args_list
    )


def test_unsupported_template_shape_is_a_422_without_wasting_a_provider_call():
    client = client_for('unused draft')
    with pytest.raises(HTTPException) as error:
        run_endpoint(endpoint_request('##\n\n## Presenting Issues\n'), client)
    assert error.value.status_code == 422
    assert 'no section title' in error.value.detail
    assert client.chat.completions.create.await_count == 0


def test_valid_document_passes_the_contract_and_is_returned_for_persistence():
    client = client_for(COMPLETE_DOCUMENT)
    result = run_endpoint(endpoint_request(CONTRACT_TEMPLATE), client)
    assert result.content == COMPLETE_DOCUMENT
    assert result.metadata['wordCount'] == len(COMPLETE_DOCUMENT.split())
    assert client.chat.completions.create.await_count == 1
