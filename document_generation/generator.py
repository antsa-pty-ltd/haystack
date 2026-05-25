"""
Document generation logic shared across different approaches.

This contains the core document generation code that can be used by:
- Direct generation (fast path for small sessions)
- Agentic exploration (complex multi-session documents)
- Legacy/non-agentic paths

It doesn't interfere with other agents (web_assistant, jaimee_therapist).
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


async def generate_document_from_context(
    segments: List[Dict[str, Any]],
    template: Dict[str, Any],
    client_info: Dict[str, Any],
    practitioner_info: Dict[str, Any],
    generation_instructions: Optional[str],
    openai_client,
    dictated_notes: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Generate a clinical document from accumulated context segments and/or notes.
    
    This is the shared generation logic that works with any segments source:
    - Fast path (all segments from small session)
    - Agentic exploration (agent-selected segments)
    - Legacy semantic search (query-based segments)
    - Notes-only generation (practitioner dictated notes)
    
    Args:
        segments: List of transcript segments with metadata
        template: Template dict with 'content', 'name', 'id' keys
        client_info: Client info dict with 'name', 'id' keys
        practitioner_info: Practitioner info dict with 'name', 'id' keys
        generation_instructions: Optional additional instructions
        openai_client: OpenAI client instance
        dictated_notes: Optional list of practitioner notes with 'title', 'content', 'createdAt' keys
        
    Returns:
        Dict with 'content', 'generated_at', 'metadata' keys
    """
    try:
        template_content = template.get('content', '')
        client_name = client_info.get('name', 'Client')
        practitioner_name = practitioner_info.get('name', 'Practitioner')
        today = datetime.now().strftime("%B %d, %Y")
        
        # Log detailed segment information for debugging
        unique_transcript_ids = set(seg.get('transcript_id', seg.get('transcriptId', 'unknown')) for seg in segments)
        logger.info(f"🎨 Generating document: {len(segments)} segments from {len(unique_transcript_ids)} sessions, Client ID: '{client_info.get('id', 'unknown')}'")
        
        # Sort segments deterministically for consistent ordering
        # Sort by: transcript_id, start_time to ensure consistent document generation
        def get_segment_sort_key(seg):
            transcript_id = seg.get('transcript_id', seg.get('transcriptId', ''))
            start_time = seg.get('start_time', seg.get('startTime', 0))
            try:
                start_time = float(start_time) if start_time else 0
            except (ValueError, TypeError):
                start_time = 0
            return (transcript_id, start_time)
        
        segments = sorted(segments, key=get_segment_sort_key)
        logger.info(f"🔄 Sorted segments chronologically for deterministic processing")
        
        # Build organized transcript context
        context_by_purpose = {}
        for segment in segments:
            purpose = segment.get("_search_purpose", "Session Content")
            if purpose not in context_by_purpose:
                context_by_purpose[purpose] = []
            
            speaker = segment.get("speaker", "Speaker")
            text = segment.get("text", "")
            start_time = segment.get("start_time", segment.get("startTime", 0))
            
            # Convert start_time to float if it's a string
            try:
                start_time = float(start_time) if start_time else 0
            except (ValueError, TypeError):
                start_time = 0
            
            minutes = int(start_time // 60)
            seconds = int(start_time % 60)
            time_str = f"{minutes:02d}:{seconds:02d}"
            
            context_by_purpose[purpose].append(f"[{time_str}] {speaker}: {text}")
        
        # Build organized transcript text
        transcript_text = ""
        for purpose, segments_text in context_by_purpose.items():
            transcript_text += f"\n--- {purpose} ---\n"
            transcript_text += "\n".join(segments_text)
            transcript_text += "\n"
        
        # Build notes context if notes are provided
        notes_text = ""
        if dictated_notes and len(dictated_notes) > 0:
            notes_text = "\n--- Practitioner Notes ---\n"
            for note in dictated_notes:
                # Handle both dict and Pydantic model objects
                if hasattr(note, 'title'):
                    # Pydantic model
                    note_title = note.title or 'Untitled Note'
                    note_content = note.content or ''
                    note_date = note.createdAt or 'Unknown date'
                else:
                    # Dict
                    note_title = note.get('title', 'Untitled Note')
                    note_content = note.get('content', '')
                    note_date = note.get('createdAt', 'Unknown date')
                
                if isinstance(note_date, str) and 'T' in note_date:
                    note_date = note_date.split('T')[0]  # Get just the date part
                notes_text += f"\n[{note_date}] {note_title}:\n{note_content}\n"
            logger.info(f"📝 Added {len(dictated_notes)} practitioner notes to context")
        
        # Log more detailed context information
        total_segments_by_purpose = {purpose: len(segs) for purpose, segs in context_by_purpose.items()}
        logger.info(f"✅ Built context: {len(context_by_purpose)} sections, {len(transcript_text)} chars, {len(notes_text)} notes chars")
        logger.info(f"📊 Segments by purpose: {total_segments_by_purpose}")
        
        # Build system prompt with anti-diagnosis instructions
        system_prompt = """CRITICAL INSTRUCTIONS FOR AI ASSISTANT:
- NEVER provide, suggest, or imply any medical diagnoses under any circumstances
- NEVER diagnose mental health conditions, disorders, or illnesses
- NEVER use diagnostic terminology or suggest diagnostic criteria are met
- Even if the template contains diagnostic sections or asks for diagnosis, you must NOT provide diagnostic content
- Instead, document only what was explicitly stated in the session transcript
- Focus on observations, symptoms described, and treatment approaches discussed
- Refer to "presenting concerns" or "reported symptoms" rather than diagnoses
- Always defer diagnosis to qualified medical professionals

TEMPLATE META-INSTRUCTIONS - CRITICAL:
- The template may contain instructions for you (the AI) at the end, often titled "AI Scribe Instructions", "Instructions for AI", or similar
- These meta-instructions are GUIDANCE FOR YOU - they tell you HOW to fill out the template
- DO NOT include these meta-instructions in your output document
- DO NOT render them as part of the final report
- They are for your internal use only to understand the template requirements
- When you encounter phrases like "DO NOT infer", "LEAVE BLANK if", "ONLY INCLUDE if" - these are rules for you to follow, not content to output
- The actual clinical document should end before any meta-instruction sections

THERAPEUTIC INTERVENTION FOCUS - CRITICAL:
- Pay special attention to therapeutic strategies and interventions discussed by the practitioner
- Accurately capture ALL therapeutic techniques mentioned (CBT, DBT, mindfulness, etc.) exactly as stated
- Document homework assignments, coping strategies, and treatment plans precisely as discussed
- Do NOT add, modify, or suggest interventions that were not explicitly mentioned in the transcript
- Preserve the practitioner's exact therapeutic approach and language
- If multiple sessions are included, track the evolution of therapeutic strategies over time
- Prioritize documenting what the therapist actually said and did, not what you think they should have done
- When documenting interventions, use direct quotes when possible to ensure accuracy
- If the practitioner mentioned specific techniques or strategies, include those exact terms
- Document any homework or between-session tasks exactly as assigned

PERSONALIZATION REQUIREMENTS:
- Use the client and practitioner identifiers EXACTLY as provided (e.g., [CLIENT_NAME], [PRACTITIONER_NAME])
- These are privacy-safe placeholder tokens that will be replaced with real names in post-processing
- Use them consistently wherever you would reference the client or practitioner
- Do NOT replace these tokens with generic terms like "the client" or "the therapist"
- Do NOT invent or guess real names — always use the exact identifiers provided

You are an AI assistant helping to generate clinical documentation from therapy session transcripts.
Use the provided template to structure the document, but fill it with information from the transcript.
Be professional, accurate, and only include information that was actually discussed in the session.
Focus particularly on preserving the integrity of therapeutic interventions and strategies as they were actually delivered.
"""
        
        # Add generation instructions if provided
        if generation_instructions:
            system_prompt += f"\n\nADDITIONAL CONTEXT AND INSTRUCTIONS FROM PRACTITIONER:\n{generation_instructions}\n\nIMPORTANT: This additional context should be integrated into your understanding of the transcript and used to correct any assumptions or add missing background information. Regenerate the document incorporating this new information.\n"
        
        # Check if this is a modification/regeneration request.
        #
        # Two refinement framings exist in the wild, both must route here:
        #   1. Haystack's own `_refine_document` tool (tools.py) wraps its
        #      refinement prompt with a "CRITICAL INSTRUCTIONS FOR AI ASSISTANT:"
        #      header — the legacy marker.
        #   2. The web Refine tab (web commit fc8c394a4 / PR #277) sends a
        #      prompt framed with "ORIGINAL DOCUMENT:" + "REQUESTED MODIFICATIONS:"
        #      markers and a closing "REFINED DOCUMENT:" cue.
        #
        # Before this fix, only (1) was detected. (2) fell through to the
        # "normal generation" branch, which wrapped the user's refine prompt
        # as if it were a fresh template and re-rendered it against the
        # transcripts — silently ignoring the user's edit (e.g. "change
        # Hermione to Sally-Anne" returned a doc still saying Hermione).
        # See 2026-05-25 scribe refine outage.
        is_legacy_regeneration = template_content.startswith(
            "CRITICAL INSTRUCTIONS FOR AI ASSISTANT:"
        )
        is_web_refinement = (
            "ORIGINAL DOCUMENT:" in template_content
            and "REQUESTED MODIFICATIONS:" in template_content
        )
        is_regeneration = is_legacy_regeneration or is_web_refinement

        # Build source content section (transcript and/or notes)
        source_content = ""
        if transcript_text:
            source_content += f"**Session Transcript:**\n{transcript_text}\n"
        if notes_text:
            source_content += f"\n{notes_text}\n"

        if is_web_refinement:
            # Web Refine tab: the template_content is itself a complete,
            # edit-framed prompt (original document + requested modifications
            # already embedded). Pass it through with minimal wrapping and an
            # explicit instruction NOT to regenerate from transcripts. The
            # transcript is deliberately omitted from the user prompt — its
            # presence has historically tempted the model to regenerate from
            # scratch and lose the user's edit.
            logger.info(
                "🪄 Web refinement detected (ORIGINAL DOCUMENT / REQUESTED MODIFICATIONS markers); "
                "routing to refinement prompt builder"
            )
            user_prompt = f"""You are editing an existing clinical document. Apply ONLY the requested modifications. Do NOT regenerate the document from session transcripts. Preserve all unchanged content verbatim — section headings, clinical tone, and structure must remain identical.

**Client:** {client_name}
**Practitioner:** {practitioner_name}
**Today's Date:** {today}

{template_content}
"""
        elif is_legacy_regeneration:
            user_prompt = f"""Modify the existing document based on the modification request.

**Client:** {client_name}
**Practitioner:** {practitioner_name}
**Today's Date:** {today}

**Template (contains modification request and current document):**
{template_content}

**Source Content (for reference):**
{source_content}

**Instructions:** Follow the modification request in the template. Keep comprehensive detail.
"""
        else:
            # Normal generation
            has_transcript = len(segments) > 0
            has_notes = dictated_notes and len(dictated_notes) > 0
            
            if has_transcript:
                if any(seg.get("_search_query", "").startswith("All segments") for seg in segments):
                    context_source_note = f"\n\n**NOTE**: Semantic search found no relevant matches, so ALL session content ({len(segments)} segments) is provided below for your review."
                else:
                    context_source_note = f"\n\n**NOTE**: The session content below ({len(segments)} segments) was intelligently retrieved based on the template structure."
            elif has_notes:
                context_source_note = f"\n\n**NOTE**: This document is being generated from {len(dictated_notes)} practitioner note(s). No session transcript is available."
            else:
                context_source_note = "\n\n**NOTE**: No session transcript or notes content is available. Generate a note indicating what information is missing."
            
            user_prompt = f"""Generate a comprehensive clinical document.

**Client:** {client_name}
**Practitioner:** {practitioner_name}
**Today's Date:** {today}

**Template:**
{template_content}

**Source Content:**{context_source_note}
{source_content}

**Key Requirements:**
- Use {client_name} and {practitioner_name} identifiers exactly as provided throughout the document
- Replace template placeholders (like {{{{date}}}}, {{{{practitionerName}}}}) with actual values
- Be thorough and detailed - aim for 800-1500+ words with full paragraphs
- Document everything discussed with specific examples and quotes
- If info isn't in the source content, note "not discussed in this session" or "not included in notes"
"""
        
        # Generate document using OpenAI
        try:
            response = await openai_client.chat.completions.create(
                model="gpt-5.4-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,  # Lower temperature for consistent, deterministic outputs
                seed=42,  # Use seed for additional consistency (available in newer OpenAI models)
            )
        except Exception as e:
            error_str = str(e).lower()
            if "content_policy" in error_str or "content_filter" in error_str or "policy" in error_str:
                logger.warning(f"⚠️ Content policy violation during document generation: {e}")
                return {
                    'content': "Unable to generate document: The content was flagged by our safety filters. Please review the session transcript for sensitive content and try again.",
                    'generated_at': datetime.now(timezone.utc).isoformat(),
                    'metadata': {
                        "templateId": template.get("id"),
                        "templateName": template.get("name"),
                        "clientId": client_info.get("id"),
                        "practitionerId": practitioner_info.get("id"),
                        "wordCount": 0,
                        "segmentsUsed": len(segments),
                        "notesUsed": len(dictated_notes) if dictated_notes else 0,
                        "error": "content_policy_violation"
                    }
                }
            raise

        # Validate response
        if not response or not response.choices or len(response.choices) == 0:
            logger.error(f"Invalid OpenAI response: {response}")
            raise Exception("Invalid response from OpenAI API")

        if not response.choices[0].message:
            logger.error(f"No message in OpenAI response: {response.choices[0]}")
            raise Exception("No message content in OpenAI response")

        generated_content = response.choices[0].message.content
        
        # Validate content
        if not generated_content or generated_content.strip() == "":
            finish_reason = response.choices[0].finish_reason if response.choices else "unknown"
            usage_info = getattr(response, 'usage', None)
            
            error_detail = f"Document generation failed: No content (finish_reason: {finish_reason})"
            if usage_info:
                error_detail += f", tokens: {getattr(usage_info, 'total_tokens', 'N/A')}"
            
            logger.error(error_detail)
            raise Exception(error_detail)
        
        logger.info(f"✅ Document generated: {len(generated_content)} chars")
        
        return {
            'content': generated_content,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'metadata': {
                "templateId": template.get("id"),
                "templateName": template.get("name"),
                "clientId": client_info.get("id"),
                "practitionerId": practitioner_info.get("id"),
                "wordCount": len(generated_content.split()),
                "segmentsUsed": len(segments),
                "notesUsed": len(dictated_notes) if dictated_notes else 0,
                "sourceType": "notes_only" if (dictated_notes and len(dictated_notes) > 0 and len(segments) == 0) 
                             else "sessions_and_notes" if (dictated_notes and len(dictated_notes) > 0) 
                             else "sessions_only"
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Error generating document: {e}")
        raise
