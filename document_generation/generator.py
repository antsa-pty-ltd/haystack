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
    openai_client
) -> Dict[str, Any]:
    """
    Generate a clinical document from accumulated context segments.
    
    This is the shared generation logic that works with any segments source:
    - Fast path (all segments from small session)
    - Agentic exploration (agent-selected segments)
    - Legacy semantic search (query-based segments)
    
    Args:
        segments: List of transcript segments with metadata
        template: Template dict with 'content', 'name', 'id' keys
        client_info: Client info dict with 'name', 'id' keys
        practitioner_info: Practitioner info dict with 'name', 'id' keys
        generation_instructions: Optional additional instructions
        openai_client: OpenAI client instance
        
    Returns:
        Dict with 'content', 'generated_at', 'metadata' keys
    """
    try:
        template_content = template.get('content', '')
        client_name = client_info.get('name', 'Client')
        practitioner_name = practitioner_info.get('name', 'Practitioner')
        today = datetime.now().strftime("%B %d, %Y")
        
        logger.info(f"🎨 Generating document: {len(segments)} segments, Client: '{client_name}', Practitioner: '{practitioner_name}'")
        
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
        
        logger.info(f"✅ Built context: {len(context_by_purpose)} sections, {len(transcript_text)} chars")
        
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

PERSONALIZATION REQUIREMENTS - ABSOLUTELY CRITICAL:
- This is the MOST IMPORTANT requirement: You MUST use the specific names provided
- NEVER EVER use generic terms like "Client", "the client", "client", "the patient", "patient", "the individual", "the counselor", "the therapist", or "the practitioner"
- The CLIENT INFORMATION section contains the client's actual name - use it every single time
- The PRACTITIONER INFORMATION section contains the practitioner's actual name - use it every single time
- Every reference to the client or practitioner MUST use their specific names
- This requirement overrides all other instructions - names are mandatory
- Double-check every sentence to ensure you used the correct names

You are an AI assistant helping to generate clinical documentation from therapy session transcripts.
Use the provided template to structure the document, but fill it with information from the transcript.
Be professional, accurate, and only include information that was actually discussed in the session.
Focus particularly on preserving the integrity of therapeutic interventions and strategies as they were actually delivered.
Always personalize the document by using the actual client and practitioner names provided.
"""
        
        # Add generation instructions if provided
        if generation_instructions:
            system_prompt += f"\n\nADDITIONAL CONTEXT AND INSTRUCTIONS FROM PRACTITIONER:\n{generation_instructions}\n\nIMPORTANT: This additional context should be integrated into your understanding of the transcript and used to correct any assumptions or add missing background information. Regenerate the document incorporating this new information.\n"
        
        # Check if this is a modification/regeneration request
        is_regeneration = template_content.startswith("CRITICAL MODIFICATION REQUEST")
        
        if is_regeneration:
            user_prompt = f"""Modify the existing document based on the modification request.

**Client:** {client_name}
**Practitioner:** {practitioner_name}
**Today's Date:** {today}

**Template (contains modification request and current document):**
{template_content}

**Session Transcript (for reference):**
{transcript_text}

**Instructions:** Follow the modification request in the template. Keep comprehensive detail.
"""
        else:
            # Normal generation
            if len(segments) > 0:
                if any(seg.get("_search_query", "").startswith("All segments") for seg in segments):
                    context_source_note = f"\n\n**NOTE**: Semantic search found no relevant matches, so ALL session content ({len(segments)} segments) is provided below for your review."
                else:
                    context_source_note = f"\n\n**NOTE**: The session content below ({len(segments)} segments) was intelligently retrieved based on the template structure."
            else:
                context_source_note = "\n\n**NOTE**: No session transcript content is available. Generate a note indicating what information is missing from the provided sessions."
            
            user_prompt = f"""Generate a comprehensive clinical document.

**Client:** {client_name}
**Practitioner:** {practitioner_name}
**Today's Date:** {today}

**Template:**
{template_content}

**Session Transcript:**{context_source_note}
{transcript_text}

**Key Requirements:**
- Use {client_name} and {practitioner_name} throughout (never "the client" or "the therapist")
- Replace template placeholders (like {{{{date}}}}, {{{{practitionerName}}}}) with actual values
- Be thorough and detailed - aim for 800-1500+ words with full paragraphs
- Document everything discussed with specific examples and quotes
- If info isn't in transcript, note "not discussed in this session"
"""
        
        # Generate document using OpenAI
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.8,  # Higher for comprehensive detail
        )
        
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
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Error generating document: {e}")
        raise
