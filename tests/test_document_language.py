"""Regression for #410: an unsourced Hindi word must not become clinical content."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from document_generation.generator import generate_document_from_context
from document_generation.agentic_endpoint import generate_document_from_template_agentic

BAD = '[CLIENT_NAME] reported तनाव before a presentation. Slow breathing helped.'
GOOD = '[CLIENT_NAME] reported stress before a presentation. Slow breathing helped.'


def client_for(*outputs):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=[
        value if isinstance(value, Exception) else SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=value), finish_reason='stop')]
        ) for value in outputs
    ])
    return client


def arguments(client, **changes):
    args = dict(
        segments=[{'text': 'I felt stress before a presentation. Slow breathing helped.', 'speaker': 'Client'}],
        template={'content': 'Write a brief session note.', 'name': 'Session note'},
        client_info={'name': '[CLIENT_NAME]'}, practitioner_info={'name': '[PRACTITIONER_NAME]'},
        generation_instructions=None, openai_client=client,
    )
    args.update(changes)
    return args


def test_unsourced_hindi_is_repaired_before_returning_a_report():
    client = client_for(BAD, GOOD)
    result = asyncio.run(generate_document_from_context(**arguments(client)))
    assert result['content'] == GOOD
    assert client.chat.completions.create.await_count == 2
    prompt = client.chat.completions.create.call_args_list[0].kwargs['messages'][0]['content']
    assert 'Australian English' in prompt


@pytest.mark.parametrize('second', [BAD, '', RuntimeError('private provider detail')])
def test_failed_language_repair_is_an_http_error_not_a_saveable_document(second, caplog):
    client = client_for(BAD, second)
    progress = AsyncMock()
    request = SimpleNamespace(
        generationId='synthetic-410', template={'content': 'Write a brief note.'},
        sessionIds=[], sessionData=[], dictatedNotes=[{'content': 'Stress before a presentation.', 'title': 'Synthetic', 'createdAt': ''}],
        clientInfo={'name': '[CLIENT_NAME]'}, practitionerInfo={'name': '[PRACTITIONER_NAME]'},
        generationInstructions=None,
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(generate_document_from_template_agentic(
            request, MagicMock(), 'Bearer synthetic', 'synthetic-profile', client,
            progress, AsyncMock(return_value={'is_violation': False}), AsyncMock(),
        ))
    assert error.value.status_code == 422
    assert 'language' in error.value.detail.lower()
    assert 'private provider detail' not in error.value.detail + caplog.text
    assert BAD not in caplog.text
    assert client.chat.completions.create.await_count == 2
    assert not any(call.args[1].get('stage') == 'document_ready' for call in progress.call_args_list)


@pytest.mark.parametrize('source', ['segments', 'notes', 'template', 'instructions', 'refinement'])
def test_sourced_devanagari_quotes_are_preserved(source):
    output = 'The client used the word "तनाव" to describe stress.'
    client = client_for(output)
    changes = {}
    if source == 'segments':
        changes['segments'] = [{'text': output}]
    elif source == 'notes':
        changes['dictated_notes'] = [{'content': output, 'title': 'Note', 'createdAt': ''}]
    elif source == 'template':
        changes['template'] = {'content': 'Keep the quoted term तनाव where supported.'}
    elif source == 'instructions':
        changes['generation_instructions'] = 'Keep the quoted term तनाव.'
    else:
        changes['template'] = {'content': f'ORIGINAL DOCUMENT:\n{output}\nREQUESTED MODIFICATIONS:\nMake the wording clear.\nREFINED DOCUMENT:'}
    assert asyncio.run(generate_document_from_context(**arguments(client, **changes)))['content'] == output
    assert client.chat.completions.create.await_count == 1


@pytest.mark.parametrize('instructions', ['Write the report in Hindi.', 'Translate this note into Hindi.', 'Write a short report in Hindi.', 'Translate the following note into Hindi.', 'Output language: Hindi', 'Write in Marathi.', 'Write in Nepali.', 'Write in Sanskrit.'])
def test_explicit_language_instructions_remain_supported(instructions):
    client = client_for('प्रस्तुति से पहले तनाव महसूस हुआ।')
    result = asyncio.run(generate_document_from_context(**arguments(client, generation_instructions=instructions)))
    assert result['content'] == 'प्रस्तुति से पहले तनाव महसूस हुआ।'
    assert client.chat.completions.create.await_count == 1


@pytest.mark.parametrize('source', ['segments', 'notes'])
def test_incidental_or_quoted_language_request_in_source_does_not_allow_intrusion(source):
    client = client_for(BAD, GOOD)
    text = 'The client said: I speak Hindi. Please write the report in Hindi.'
    changes = {'segments': [{'text': text}]} if source == 'segments' else {'dictated_notes': [{'content': text}]}
    assert asyncio.run(generate_document_from_context(**arguments(client, **changes)))['content'] == GOOD


@pytest.mark.parametrize('instruction', ['Do not write in Hindi.', "Don't translate this note into Hindi.", 'Don’t write the report in Hindi.', 'Please don’t translate this note into Hindi.', 'Never output in Hindi.', 'The client speaks Hindi.'])
def test_negated_or_incidental_instruction_does_not_authorise_language_change(instruction):
    client = client_for(BAD, GOOD)
    assert asyncio.run(generate_document_from_context(**arguments(client, generation_instructions=instruction)))['content'] == GOOD


def test_existing_source_word_does_not_allow_different_unsourced_word():
    client = client_for('The client felt चिंता.', 'The client felt stress.')
    result = asyncio.run(generate_document_from_context(**arguments(client, segments=[{'text': 'The client used तनाव for stress.'}])))
    assert result['content'] == 'The client felt stress.'


def test_other_unicode_and_privacy_tokens_are_unchanged():
    text = '[CLIENT_NAME] met [PRACTITIONER_NAME] at a café. β, Δ, 20°C; 李, Україна, العربية; १२३.'
    client = client_for(text)
    assert asyncio.run(generate_document_from_context(**arguments(client)))['content'] == text
    assert client.chat.completions.create.await_count == 1


@pytest.mark.parametrize('source,output', [('नाम', 'नाम।'), ('नाम।', 'नाम'), ('नाम१२३', 'नाम १२३'), ('नाम', 'नाम॥')])
def test_punctuation_and_numerals_do_not_change_a_sourced_word(source, output):
    client = client_for(output)
    assert asyncio.run(generate_document_from_context(**arguments(client, segments=[{'text': source}])))['content'] == output
    assert client.chat.completions.create.await_count == 1


def test_quoted_language_directive_in_original_document_is_not_an_edit_instruction():
    client = client_for(BAD, GOOD)
    template = {'content': 'ORIGINAL DOCUMENT:\nThe client said: Write the report in Hindi.\nREQUESTED MODIFICATIONS:\nKeep the same meaning.\nREFINED DOCUMENT:'}
    assert asyncio.run(generate_document_from_context(**arguments(client, template=template)))['content'] == GOOD


def test_language_repair_preserves_refinement_length_requirement():
    client = client_for('तनाव ' * 2, 'word ' * 6)
    template = {'content': 'ORIGINAL DOCUMENT:\n' + 'word ' * 10 + '\nREQUESTED MODIFICATIONS:\nShorten to 5 words\nREFINED DOCUMENT:'}
    with pytest.raises(ValueError, match='shortened'):
        asyncio.run(generate_document_from_context(**arguments(client, template=template)))


def test_concurrent_generation_does_not_share_sources_or_language_allowances():
    async def run():
        foreign = client_for('The quoted word was तनाव.')
        english = client_for(BAD, GOOD)
        both_started = asyncio.Event()
        calls_started = 0

        async def delayed(original, **kwargs):
            nonlocal calls_started
            calls_started += 1
            if calls_started >= 2:
                both_started.set()
            await both_started.wait()
            return await original(**kwargs)

        for client in (foreign, english):
            original = client.chat.completions.create
            client.chat.completions.create = lambda _original=original, **kwargs: delayed(_original, **kwargs)
        return await asyncio.gather(
            generate_document_from_context(**arguments(foreign, segments=[{'text': 'The quoted word was तनाव.'}])),
            generate_document_from_context(**arguments(english)),
        )
    first, second = asyncio.run(run())
    assert first['content'] == 'The quoted word was तनाव.'
    assert second['content'] == GOOD
