"""
Agentic document generation endpoint.

This module contains the new agentic approach for document generation
that works ALONGSIDE the existing web_assistant and jaimee_therapist agents.
"""

import os
import asyncio
import logging
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from fastapi import HTTPException
from utils.session_utils import fetch_session_metadata, estimate_tokens_from_segments
from agents.document_agent import get_document_agent
from document_generation.generator import generate_document_from_context

logger = logging.getLogger(__name__)


async def generate_document_from_template_agentic(
    request,
    http_request,
    authorization: Optional[str],
    profileid: Optional[str],
    openai_client,
    emit_progress_func,
    detect_policy_violation_func,
    log_violation_func
):
    """
    Generate a document using agentic exploration (NEW APPROACH).
    
    This uses the DocumentExplorationAgent for autonomous session exploration.
    It works ALONGSIDE other agents (web_assistant, jaimee_therapist) - it's ONLY
    used for document generation, not for chat or other functionality.
    
    Args:
        request: GenerateDocumentRequest
        http_request: FastAPI Request object
        authorization: Authorization header
        profileid: Profile ID header  
        openai_client: OpenAI client instance
        emit_progress_func: Progress emission function
        detect_policy_violation_func: Policy violation detection function
        log_violation_func: Violation logging function
        
    Returns:
        GenerateDocumentResponse
    """
    generation_id = getattr(request, 'generationId', None)
    
    try:
        logger.info(f"🎨 [AGENTIC] Generating document from template: {request.template.get('name', 'Unknown')}")
        
        if not openai_client:
            raise HTTPException(status_code=500, detail="OpenAI client not configured")
        
        # Extract data from request
        template = request.template
        session_ids = request.sessionIds
        client_info = request.clientInfo
        practitioner_info = request.practitionerInfo
        generation_instructions = request.generationInstructions
        
        logger.info(f"📋 [AGENTIC] Generating from {len(session_ids)} sessions using '{template.get('name', 'Unknown')}'")
        
        # ===== POLICY CHECK (keep existing logic) =====
        await emit_progress_func(generation_id, {
            "type": "stage_started",
            "stage": "policy_check",
            "message": "Checking template for policy violations..."
        }, authorization)
        
        template_content = template.get('content', '')
        
        # Strip safety instructions for policy check
        original_template_content = template_content
        safety_instruction_marker = "CRITICAL INSTRUCTIONS FOR AI ASSISTANT:"
        if safety_instruction_marker in template_content:
            parts = template_content.split(safety_instruction_marker)
            if len(parts) > 1:
                last_safety_block = safety_instruction_marker + parts[-1]
                template_parts = last_safety_block.split('\n\n')
                for i, part in enumerate(template_parts):
                    if (not part.strip().startswith('-') and 
                        not part.strip().startswith('CRITICAL') and 
                        len(part.strip()) > 50):
                        original_template_content = '\n\n'.join(template_parts[i:])
                        break
        
        violation_check = await detect_policy_violation_func(original_template_content)
        
        if violation_check["is_violation"]:
            logger.warning(f"⚠️ [AGENTIC] Policy violation detected: {violation_check['violation_type']}")
            
            # Log violation (async, non-blocking)
            if profileid:
                try:
                    ip_address = http_request.client.host if http_request.client else None
                    user_agent = http_request.headers.get("user-agent")
                    
                    asyncio.create_task(log_violation_func(
                        profile_id=profileid,
                        template_id=template.get('id'),
                        template_name=template.get('name'),
                        violation_type=violation_check['violation_type'],
                        template_content=original_template_content,
                        reason=violation_check.get('reason'),
                        confidence=violation_check.get('confidence'),
                        client_id=client_info.get('id'),
                        metadata={
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "generationInstructions": generation_instructions,
                        },
                        ip_address=ip_address,
                        user_agent=user_agent
                    ))
                except Exception as e:
                    logger.error(f"❌ Failed to log violation: {e}")
            
            # Return violation message
            reason_section = f"\n\nReason: {violation_check['reason']}" if violation_check.get("reason") else ""
            warning_message = f"""⚠️ CONTENT POLICY VIOLATION DETECTED

We're unable to process this request as the template content appears to be requesting medical diagnosis or clinical assessment using diagnostic criteria, which violates our Terms of Service and responsible AI use policies.

Our system is not designed to provide medical diagnoses, mental health assessments, or clinical evaluations. Such determinations should only be made by qualified healthcare professionals in appropriate clinical settings.

**This incident has been flagged and our team has been notified.**

Violation Type: {violation_check['violation_type']}
Template Name: {template.get('name', 'Unknown')}
Timestamp: {datetime.now(timezone.utc).isoformat()}{reason_section}

If you believe this was flagged in error, please contact our support team. If you're looking for documentation templates for non-diagnostic purposes (such as session notes, treatment planning, or progress tracking), we'd be happy to help with those instead.

For more information, please review our Terms of Service at www.ANTSA.com.au."""
            
            from pydantic import BaseModel
            class GenerateDocumentResponse(BaseModel):
                content: str
                generatedAt: str
                metadata: dict
            
            return GenerateDocumentResponse(
                content=warning_message,
                generatedAt=datetime.now(timezone.utc).isoformat(),
                metadata={
                    "templateId": template.get("id"),
                    "templateName": template.get("name"),
                    "clientId": client_info.get("id"),
                    "practitionerId": practitioner_info.get("id"),
                    "policyViolation": True,
                    "violationType": violation_check["violation_type"],
                    "confidence": violation_check.get("confidence", "unknown"),
                    "reason": violation_check.get("reason"),
                    "flagged": True,
                    "processingMethod": "policy_violation_detected"
                }
            )
        
        # ===== FAST PATH: Single Small Session =====
        if len(session_ids) == 1:
            metadata = await fetch_session_metadata(session_ids[0], authorization)
            if metadata and metadata['totalSegments'] < 150:
                estimated_tokens = estimate_tokens_from_segments(metadata['totalSegments'])
                logger.info(f"✅ [FAST PATH] Single small session ({metadata['totalSegments']} segments, ~{estimated_tokens} tokens)")
                
                await emit_progress_func(generation_id, {
                    "type": "progress_update",
                    "stage": "analysing_sessions",
                    "message": "Analysing session size and content...",
                    "details": {"sessionCount": 1}
                }, authorization)
                
                await emit_progress_func(generation_id, {
                    "type": "progress_update",
                    "stage": "retrieving_content",
                    "message": f"Loading transcript ({metadata['totalSegments']} segments)...",
                    "details": {"segments": metadata['totalSegments'], "tokens": estimated_tokens}
                }, authorization)
                
                # Pull all segments directly using segments-by-sessions endpoint
                # (not semantic-search, which requires embeddings)
                api_url = os.getenv("NESTJS_API_URL", "http://localhost:8080")
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{api_url}/api/v1/ai/transcripts/segments-by-sessions",
                        json={
                            "session_ids": [session_ids[0]],
                            "limit_per_session": 1000
                        },
                        headers={"Authorization": authorization} if authorization else {}
                    )
                    response_data = response.json()
                    segments = response_data.get('segments', []) if isinstance(response_data, dict) else response_data
                
                await emit_progress_func(generation_id, {
                    "type": "progress_update",
                    "stage": "writing_document",
                    "message": f"Writing document using '{template.get('name', 'template')}'...",
                    "details": {"templateName": template.get('name')}
                }, authorization)
                
                # Generate directly (skip agent)
                result = await generate_document_from_context(
                    segments=segments,
                    template=template,
                    client_info=client_info,
                    practitioner_info=practitioner_info,
                    generation_instructions=generation_instructions,
                    openai_client=openai_client
                )
                
                await emit_progress_func(generation_id, {
                    "type": "stage_completed",
                    "stage": "document_ready",
                    "message": "Document generated successfully!",
                }, authorization)
                
                from pydantic import BaseModel
                class GenerateDocumentResponse(BaseModel):
                    content: str
                    generatedAt: str
                    metadata: dict
                
                return GenerateDocumentResponse(
                    content=result['content'],
                    generatedAt=result['generated_at'],
                    metadata=result['metadata']
                )
        
        # ===== AGENTIC PATH: Complex Multi-Session or Large Session =====
        logger.info(f"🤖 [AGENTIC] Using DocumentExplorationAgent for {len(session_ids)} sessions")
        
        await emit_progress_func(generation_id, {
            "type": "progress_update",
            "stage": "preparing_agent",
            "message": f"Preparing to analyse {len(session_ids)} session(s)...",
            "details": {"sessionCount": len(session_ids)}
        }, authorization)
        
        await emit_progress_func(generation_id, {
            "type": "stage_started",
            "stage": "agentic_exploration",
            "message": "AI agent is exploring session content..."
        }, authorization)
        
        # Get the document agent (doesn't affect other agents)
        agent = get_document_agent()
        if not agent:
            raise HTTPException(status_code=500, detail="Document agent not initialized")
        
        # Let agent autonomously explore and decide (with real-time reasoning updates)
        exploration_result = await agent.explore_and_decide(
            session_ids=session_ids,
            template_name=template.get('name', 'Unknown'),
            template_content=template_content,
            authorization=authorization,
            generation_id=generation_id,
            emit_progress_func=emit_progress_func
        )
        
        if not exploration_result['success']:
            raise Exception(f"Agent exploration failed: {exploration_result.get('error')}")
        
        # Log agent's exploration
        logger.info(f"🤖 [AGENTIC] Exploration complete:")
        logger.info(f"   - Segments: {len(exploration_result['segments'])}")
        logger.info(f"   - Tokens: {exploration_result['tokens_used']}")
        logger.info(f"   - Sessions: {exploration_result['sessions_explored']}")
        
        # CRITICAL: Check for empty or insufficient segments
        if len(exploration_result['segments']) == 0:
            logger.error(f"❌ [AGENTIC] No segments retrieved! This will produce a poor document.")
        elif len(exploration_result['segments']) < 20:
            logger.warning(f"⚠️ [AGENTIC] Only {len(exploration_result['segments'])} segments retrieved - may be insufficient for quality document")
        
        await emit_progress_func(generation_id, {
            "type": "stage_completed",
            "stage": "agentic_exploration",
            "message": f"Agent explored {len(exploration_result['sessions_explored'])} sessions and collected {len(exploration_result['segments'])} segments",
            "details": {
                "segments": len(exploration_result['segments']),
                "tokens": exploration_result['tokens_used'],
                "sessions": exploration_result['sessions_explored']
            }
        }, authorization)
        
        # Generate document from agent's accumulated context
        await emit_progress_func(generation_id, {
            "type": "stage_started",
            "stage": "generating_document",
            "message": "Generating document from accumulated context..."
        }, authorization)
        
        result = await generate_document_from_context(
            segments=exploration_result['segments'],
            template=template,
            client_info=client_info,
            practitioner_info=practitioner_info,
            generation_instructions=generation_instructions,
            openai_client=openai_client
        )
        
        # Add agent metadata
        result['metadata']['agent_exploration'] = {
            "tokens_used": exploration_result['tokens_used'],
            "sessions_explored": exploration_result['sessions_explored'],
            "decision_trail_length": len(exploration_result.get('decision_trail', []))
        }
        result['metadata']['processingMethod'] = 'agentic_exploration'
        
        await emit_progress_func(generation_id, {
            "type": "stage_completed",
            "stage": "document_ready",
            "message": "Document generated successfully!",
            "details": {
                "segments_used": len(exploration_result['segments']),
                "sessions_explored": len(exploration_result['sessions_explored'])
            }
        }, authorization)
        
        from pydantic import BaseModel
        class GenerateDocumentResponse(BaseModel):
            content: str
            generatedAt: str
            metadata: dict
        
        return GenerateDocumentResponse(
            content=result['content'],
            generatedAt=result['generated_at'],
            metadata=result['metadata']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [AGENTIC] Error: {e}")
        
        # User-friendly error
        error_content = f"""# Generation Error

An error occurred while generating your document.

**What you can do:**
- Click the Generate button again to retry
- Contact support if the problem persists

**Error details:** {str(e)[:200]}"""
        
        from pydantic import BaseModel
        class GenerateDocumentResponse(BaseModel):
            content: str
            generatedAt: str
            metadata: dict
        
        return GenerateDocumentResponse(
            content=error_content,
            generatedAt=datetime.now(timezone.utc).isoformat(),
            metadata={
                "error": True,
                "errorType": type(e).__name__,
                "errorMessage": str(e)[:500],
                "processingMethod": "error_handling"
            }
        )
