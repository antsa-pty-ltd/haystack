#!/usr/bin/env python3
"""
FastAPI Haystack Service - Simple Working Version
Basic OpenAI streaming with template support
"""

import os
import asyncio
import logging
import json
import uuid
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv
from ui_state_manager import ui_state_manager
from openai import AsyncOpenAI
from haystack_pipeline import HaystackPipelineManager
from personas import PersonaType
from session_manager import session_manager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure OpenAI
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    logger.error("OPENAI_API_KEY environment variable not set.")

# Create OpenAI client
openai_client = AsyncOpenAI(api_key=openai_api_key) if openai_api_key else None

# API configuration for logging violations
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:3000/api/v1")

# Simple tool loading (graceful fallback)
def load_templates_safely():
    """Safely load templates if available"""
    try:
        from tools import ToolManager
        tool_manager = ToolManager()
        return tool_manager
    except ImportError as e:
        logger.warning(f"Could not import tools: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error initializing tool manager: {e}")
        return None

# Try to load tools
tool_manager = load_templates_safely()

# Pipeline manager for tool-enabled conversations with history using Haystack
pipeline_manager = HaystackPipelineManager()

# Create FastAPI app
app = FastAPI(
    title="Haystack AU Service",
    description="AI Assistant Service with Template Support",
    version="3.0.0"
)

# Startup: initialize session store and pipeline
@app.on_event("startup")
async def on_startup():
    try:
        await session_manager.initialize()
    except Exception as e:
        logger.warning(f"Session manager init warning: {e}")
    try:
        await pipeline_manager.initialize()
    except Exception as e:
        logger.warning(f"Pipeline manager init warning: {e}")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Authorization", "ProfileID", "Content-Type"],
)

# In-memory UI state only (sessions are persisted via SessionManager)
websocket_connections: Dict[str, WebSocket] = {}
ui_states: Dict[str, Dict[str, Any]] = {}

class CreateSessionRequest(BaseModel):
    persona_type: str = "web_assistant"
    context: Dict[str, Any] = {}
    profile_id: Optional[str] = None

class SessionResponse(BaseModel):
    session_id: str
    persona_type: str
    created_at: str

class GenerateDocumentRequest(BaseModel):
    template: Dict[str, Any]
    transcript: Dict[str, Any]
    clientInfo: Dict[str, Any]
    practitionerInfo: Dict[str, Any]
    generationInstructions: Optional[str] = None

class GenerateDocumentResponse(BaseModel):
    content: str
    generatedAt: str
    metadata: Dict[str, Any] = {}

def get_enhanced_system_prompt(persona_type: str, ui_state: Dict[str, Any] = None) -> str:
    """Get enhanced system prompt with available capabilities"""
    
    base_prompt = """You are a helpful AI assistant for the ANTSA platform.

CRITICAL: NEVER PROVIDE MEDICAL DIAGNOSES
- NEVER diagnose mental health conditions, disorders, or illnesses under any circumstances
- NEVER suggest diagnostic criteria are met or provide diagnostic terminology
- NEVER imply, suggest, or state that someone has a specific mental health condition
- Even if templates contain diagnostic sections, you must NOT provide diagnostic content
- Document only what was explicitly stated in session transcripts
- Use terms like "presenting concerns", "reported symptoms", or "client-described experiences"
- Always defer diagnosis to qualified medical professionals
- Focus on observations, treatment approaches, and documented client statements only"""
    
    if persona_type == "web_assistant":
        base_prompt = """You are a helpful AI web assistant designed to assist users with navigating and using the ANTSA platform. Provide concise and direct answers.

CRITICAL: NEVER PROVIDE MEDICAL DIAGNOSES
- NEVER diagnose mental health conditions, disorders, or illnesses under any circumstances
- NEVER suggest diagnostic criteria are met or provide diagnostic terminology
- NEVER imply, suggest, or state that someone has a specific mental health condition
- Even if templates contain diagnostic sections, you must NOT provide diagnostic content
- Document only what was explicitly stated in session transcripts
- Use terms like "presenting concerns", "reported symptoms", or "client-described experiences"
- Always defer diagnosis to qualified medical professionals
- Focus on observations, treatment approaches, and documented client statements only"""
    elif persona_type == "data_assistant":
        base_prompt = """You are a data analysis AI assistant. Your primary goal is to help users understand and interpret their data.

CRITICAL: NEVER PROVIDE MEDICAL DIAGNOSES
- NEVER diagnose mental health conditions, disorders, or illnesses under any circumstances
- NEVER suggest diagnostic criteria are met or provide diagnostic terminology
- NEVER imply, suggest, or state that someone has a specific mental health condition
- Even if templates contain diagnostic sections, you must NOT provide diagnostic content
- Document only what was explicitly stated in session transcripts
- Use terms like "presenting concerns", "reported symptoms", or "client-described experiences"
- Always defer diagnosis to qualified medical professionals
- Focus on observations, treatment approaches, and documented client statements only"""
    
    # Add current page context if available
    if ui_state:
        derived_context = _build_page_context_from_ui_state(ui_state)
        if derived_context.get('page_display_name'):
            base_prompt += f"\n\nCURRENT PAGE: You are currently viewing the {derived_context['page_display_name']} page."
    
    # Add template capabilities if available
    capabilities = "\n\n🛠️ Available Capabilities:"
    
    if tool_manager:
        capabilities += "\n- Template access: I can help you find and load templates"
        capabilities += "\n- Client search: I can help you find client information"
        capabilities += "\n- Document generation: I can help create documents from templates"
    else:
        capabilities += "\n- General chat and assistance"
        capabilities += "\n- Guidance on using the platform"
    
    # Add current context
    if ui_state:
        page_url = ui_state.get('page_url', 'unknown')
        client_id = ui_state.get('client_id')
        client_name = ui_state.get('client_name')
        selected_template = ui_state.get('selected_template')
        active_document = ui_state.get('active_document')
        loaded_sessions = ui_state.get('loadedSessions', [])
        generated_documents = ui_state.get('generatedDocuments', [])
        
        capabilities += f"\n\n📍 Current Context:"
        capabilities += f"\n- Page: {page_url}"
        capabilities += f"\n- Client: {client_name if client_name else (client_id if client_id else 'None selected')}"
        capabilities += f"\n- Template: {selected_template.get('name') if selected_template else 'None'}"
        capabilities += f"\n- Loaded Sessions: {len(loaded_sessions) if isinstance(loaded_sessions, list) else 0}"
        capabilities += f"\n- Generated Documents: {len(generated_documents) if isinstance(generated_documents, list) else 0}"
        
        # Add active document context
        if active_document and active_document.get('document'):
            doc = active_document['document']
            capabilities += f"\n- Active Document: {doc.get('documentName', 'Unnamed')} (ID: {doc.get('documentId', 'Unknown')})"
            if doc.get('isGenerated'):
                capabilities += f" - Generated document"
            capabilities += f"\n- Document Content Preview: {doc.get('documentContent', '')[:100]}{'...' if len(doc.get('documentContent', '')) > 100 else ''}"
        
        # Add instructions for document generation
        if client_name and (loaded_sessions or generated_documents):
            capabilities += f"\n\n🎯 CRITICAL ACTIVE SESSION CONTEXT:"
            capabilities += f"\n- The client's name is '{client_name}' - use this instead of 'client' or 'the client'"
            capabilities += f"\n- You have access to {len(loaded_sessions) if isinstance(loaded_sessions, list) else 0} loaded session(s)"
            if generated_documents and isinstance(generated_documents, list) and len(generated_documents) > 0:
                capabilities += f"\n- There are {len(generated_documents)} existing document(s) currently visible"
                capabilities += f"\n\n🔄 CRITICAL DOCUMENT MODIFICATION INSTRUCTIONS:"
                capabilities += f"\n- When user asks to modify/regenerate/change an existing document, use the refine_document tool"
                capabilities += f"\n- Pass the document ID and the user's specific instructions in refinement_instructions parameter"
                capabilities += f"\n- The refine_document tool will regenerate the document with the requested changes"
                capabilities += f"\n- Do NOT just acknowledge requests - actively call refine_document to apply changes"
                capabilities += f"\n- For NEW documents (not modifying existing), use generate_document_auto with generation_instructions"
    
    return base_prompt + capabilities


def _get_human_readable_page_name(technical_name: str) -> str:
    """Convert technical page names to human-readable names"""
    page_name_map = {
        'dashboard': 'Dashboard',
        'clients_list': 'Clients',
        'client_details': 'Client Details', 
        'messages_page': 'Messages',
        'homework_page': 'Homework',
        'files_page': 'Files',
        'profile_page': 'Profile',
        'practitioners_page': 'Practitioners',
        'transcribe_page': 'Live Transcribe',
        'session_viewer': 'Session Viewer',
        'sessions_list': 'Sessions',
        'settings': 'Settings',
        'reports': 'Reports',
        'unknown': 'Unknown Page'
    }
    return page_name_map.get(technical_name, technical_name.replace('_', ' ').title())

def _build_page_context_from_ui_state(ui_state: Dict[str, Any]) -> Dict[str, Any]:
    """Derive a minimal page context for tools based on UI state."""
    if not ui_state:
        return {}

    capabilities: List[str] = []

    # Detect page type and URL from UI state
    page_url = ui_state.get("page_url") or ui_state.get("pageUrl") or ui_state.get("route") or ""
    page_type = ui_state.get("page_type") or ui_state.get("pageType") or ""

    # Heuristics: determine if on sessions/transcribe page
    is_sessions_page = False
    if page_type:
        is_sessions_page = page_type in ["transcribe_page", "sessions_page", "live_transcribe", "live-transcribe"]
    if not is_sessions_page and isinstance(page_url, str):
        is_sessions_page = ("/live-transcribe" in page_url) or ("/sessions" in page_url)

    # Capabilities inferred from UI state
    if isinstance(ui_state.get("loadedSessions"), list) and len(ui_state.get("loadedSessions")) > 0:
        capabilities.extend(["get_loaded_sessions", "get_session_content", "analyze_loaded_session", "generate_document_from_loaded"])
    if isinstance(ui_state.get("selectedTemplate"), dict):
        capabilities.append("set_selected_template")

    # If on sessions page, enable client/session actions AND template selection
    if is_sessions_page:
        capabilities.extend(["set_client_selection", "load_session_direct", "load_multiple_sessions", "set_selected_template"]) 

    # Default page type if still unknown
    if not page_type:
        page_type = "transcribe_page" if is_sessions_page else "unknown"

    return {
        "page_type": page_type,
        "page_display_name": _get_human_readable_page_name(page_type),
        "capabilities": capabilities,
    }


async def _ensure_tools_context(session_id: str, message_data: Dict[str, Any]):
    """Ensure ToolManager has auth, profile and page context for this session."""
    if not tool_manager:
        return

    # Prefer token from incoming message, else from stored UI state manager, else from stored session
    incoming_token = message_data.get("auth_token") or message_data.get("token")
    ui_state_token = ui_state_manager.get_auth_token(session_id)
    
    # Also check the stored session for auth token
    session_token = None
    try:
        sess = await session_manager.get_session(session_id)
        if sess:
            session_token = sess.auth_token
    except Exception:
        pass
    
    token = incoming_token or ui_state_token or session_token

    logger.info(f"🔍 Debug auth context for session {session_id}: incoming_token={bool(incoming_token)}, ui_state_token={bool(ui_state_token)}, session_token={bool(session_token)}, final_token={bool(token)}")

    if token:
        profile_id = message_data.get("profile_id") or message_data.get("profileId")
        logger.info(f"🔍 Debug profile_id extraction: from_message={profile_id}")
        try:
            # Only attach profile_id for practitioner contexts; clients use JWT clientId, not profile header
            if profile_id and isinstance(profile_id, str) and not profile_id.startswith("client-"):
                tool_manager.set_auth_token(token, profile_id)
            else:
                tool_manager.set_auth_token(token)
            logger.info(f"🔍 Debug: set auth token, profile_id={getattr(tool_manager, 'profile_id', None)}")
        except Exception:
            # Non-fatal; tool calls will fail clearly if required
            pass

    # Set profile id explicitly only for practitioner contexts (avoid client-* IDs)
    profile_id = message_data.get("profile_id") or message_data.get("profileId")
    if profile_id and isinstance(profile_id, str) and not profile_id.startswith("client-"):
        logger.info(f"🔍 Debug: explicitly setting profile_id={profile_id}")
        try:
            tool_manager.set_profile_id(profile_id)
        except Exception:
            pass
    elif profile_id and isinstance(profile_id, str) and profile_id.startswith("client-"):
        logger.info("🔍 Debug: skipping explicit profile_id set for client context")

    # Attach page context derived from latest UI state for this session
    ui_state = ui_states.get(session_id) or {}
    page_context = _build_page_context_from_ui_state(ui_state)
    if page_context:
        try:
            tool_manager.set_page_context(page_context)
        except Exception:
            pass

@app.get("/")
async def root():
    return {
        "service": "Haystack AU Service", 
        "status": "running",
        "version": "3.0.0",
        "streaming": "openai",
        "tools_available": bool(tool_manager),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "haystack-au-service",
        "version": "3.0.0",
        "openai": "enabled" if openai_api_key else "disabled",
        "streaming": "active",
        "tools": "available" if tool_manager else "unavailable"
    }

@app.post("/sessions", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest, authorization: str = Header(None), profileid: str = Header(None)):
    try:
        logger.info(f"🔐 Received headers - Authorization: {authorization[:20] + '...' if authorization else 'None'}, ProfileID: {profileid}")
        
        # Extract auth token from Authorization header
        auth_token = None
        if authorization and authorization.startswith("Bearer "):
            auth_token = authorization[7:]  # Remove "Bearer " prefix
        
        # Use profileid from header if not provided in request
        profile_id = request.profile_id or profileid
        
        logger.info(f"Creating session with auth_token: {bool(auth_token)}, profile_id: {profile_id}")
        
        # Create persisted session
        session_id = await session_manager.create_session(
            persona_type=request.persona_type,
            context=request.context or {},
            auth_token=auth_token,
            profile_id=profile_id,
        )
        created_at = datetime.now(timezone.utc).isoformat()
        logger.info(f"Session created: {session_id} for persona {request.persona_type}")
        return SessionResponse(session_id=session_id, persona_type=request.persona_type, created_at=created_at)
        
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def log_violation_to_api(
    profile_id: str,
    template_id: str,
    template_name: str,
    violation_type: str,
    template_content: str,
    reason: str,
    confidence: str,
    client_id: str = None,
    metadata: Dict = None,
    ip_address: str = None,
    user_agent: str = None
) -> None:
    """Log policy violation to the API database"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            payload = {
                "profileId": profile_id,
                "templateId": template_id,
                "templateName": template_name,
                "violationType": violation_type,
                "templateContent": template_content,
                "reason": reason,
                "confidence": confidence,
                "clientId": client_id,
                "metadata": metadata or {},
                "ipAddress": ip_address,
                "userAgent": user_agent,
            }
            
            response = await client.post(
                f"{API_BASE_URL}/admin/policy-violations",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ Successfully logged violation to API for profile {profile_id}")
            else:
                logger.error(f"❌ Failed to log violation to API: {response.status_code} - {response.text}")
    
    except Exception as e:
        logger.error(f"❌ Error logging violation to API: {e}")
        # Don't raise - we don't want to break the violation detection if API logging fails


async def detect_policy_violation(template_content: str) -> Dict[str, Any]:
    """
    Detect if template content violates terms of service by requesting medical diagnosis
    Uses LLM to intelligently analyze template content for policy violations
    Returns: {"is_violation": bool, "violation_type": str, "reason": str}
    """
    try:
        if not openai_client:
            logger.warning("OpenAI client not available for policy check, allowing template")
            return {"is_violation": False, "violation_type": None, "reason": None}
        
        # Use LLM to analyze template for policy violations
        system_prompt = """You are a content policy enforcement system for a mental health practice management platform.

Your job is to analyze documentation templates and determine if they violate our Terms of Service.

STRICT POLICY - Templates that violate ToS:
1. Templates that explicitly request medical diagnosis or diagnostic assessments
2. Templates that ask the AI to determine if someone meets diagnostic criteria (DSM, ICD, etc.)
3. Templates that ask to evaluate whether a client "has" or "should be diagnosed with" a specific condition
4. Templates that request clinical diagnosis of mental health conditions
5. Templates that ask the AI to make diagnostic determinations

ALLOWED - Templates that are acceptable:
1. Templates for session notes documenting what was discussed
2. Templates for treatment planning and progress tracking
3. Templates that document "presenting concerns" or "reported symptoms"
4. Templates that document practitioner observations (not AI diagnosis)
5. Templates asking to document what the practitioner said/did in session
6. Templates with anti-diagnosis warnings (these are our safety instructions)

IMPORTANT: 
- Multiple anti-diagnosis warnings in a template are SAFETY INSTRUCTIONS, not violations
- Only flag templates that are ASKING THE AI to diagnose, not templates preventing diagnosis
- Be strict but fair - we want to catch actual misuse, not legitimate clinical documentation

Analyze the template and respond ONLY with valid JSON in this exact format:
{
  "is_violation": true/false,
  "violation_type": "medical_diagnosis_request" or null,
  "reason": "Brief explanation" or null,
  "confidence": "high/medium/low"
}"""

        user_prompt = f"""Analyze this template for Terms of Service violations:

TEMPLATE CONTENT:
{template_content}

Respond with JSON only."""

        # Call LLM for analysis
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",  # Fast and cost-effective for this task
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,  # Low temperature for consistent policy enforcement
            max_tokens=200
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Parse JSON response
        # Remove markdown code blocks if present
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        result = json.loads(result_text)
        
        logger.info(f"🔍 Policy check result: {result}")
        
        return {
            "is_violation": result.get("is_violation", False),
            "violation_type": result.get("violation_type"),
            "reason": result.get("reason"),
            "confidence": result.get("confidence", "unknown")
        }
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse policy check response: {e}, Response: {result_text if 'result_text' in locals() else 'N/A'}")
        # Fail open - allow template if we can't parse the response
        return {"is_violation": False, "violation_type": None, "reason": None}
    except Exception as e:
        logger.error(f"Error detecting policy violation: {e}")
        # Fail open - allow template on error to avoid breaking legitimate use
        return {"is_violation": False, "violation_type": None, "reason": None}


@app.post("/generate-document-from-template", response_model=GenerateDocumentResponse)
async def generate_document_from_template(
    request: GenerateDocumentRequest, 
    http_request: Request,
    authorization: str = Header(None), 
    profileid: str = Header(None)
):
    """Generate a document using a template and transcript data"""
    try:
        logger.info(f"🎨 Generating document from template: {request.template.get('name', 'Unknown')}")
        
        if not openai_client:
            raise HTTPException(status_code=500, detail="OpenAI client not configured")
        
        # Extract data from request
        template = request.template
        transcript = request.transcript
        client_info = request.clientInfo
        practitioner_info = request.practitionerInfo
        generation_instructions = request.generationInstructions
        
        # Check for policy violations in template content
        template_content = template.get('content', '')
        
        # Strip out the prepended safety instructions to get original template
        # These are added by the template service but we don't want them in the violation log
        original_template_content = template_content
        safety_instruction_marker = "CRITICAL INSTRUCTIONS FOR AI ASSISTANT:"
        if safety_instruction_marker in template_content:
            # Find the last occurrence of the safety instructions
            parts = template_content.split(safety_instruction_marker)
            if len(parts) > 1:
                # The last part after the final safety instruction block is the original template
                # Find where the safety block ends (look for double newline after it)
                last_safety_block = safety_instruction_marker + parts[-1]
                # Split on double newline to separate safety instructions from actual template
                template_parts = last_safety_block.split('\n\n')
                # Find the first part that doesn't contain safety instruction keywords
                for i, part in enumerate(template_parts):
                    if (not part.strip().startswith('-') and 
                        not part.strip().startswith('CRITICAL') and 
                        len(part.strip()) > 50):  # Original template is usually longer
                        original_template_content = '\n\n'.join(template_parts[i:])
                        break
        
        violation_check = await detect_policy_violation(original_template_content)
        
        if violation_check["is_violation"]:
            logger.warning(f"⚠️ Policy violation detected in template '{request.template.get('name', 'Unknown')}' - Type: {violation_check['violation_type']}")
            logger.warning(f"⚠️ User: {profileid}, Template ID: {template.get('id', 'N/A')}, Confidence: {violation_check.get('confidence', 'unknown')}")
            logger.warning(f"⚠️ Reason: {violation_check.get('reason', 'No reason provided')}")
            
            # Extract request metadata
            ip_address = http_request.client.host if http_request.client else None
            user_agent = http_request.headers.get("user-agent")
            
            logger.info(f"📤 Preparing to log violation to API - Profile ID: {profileid}, Template ID: {template.get('id')}")
            
            # Check if we have required data
            if not profileid:
                logger.error("❌ Cannot log violation: profileid is None or empty!")
            else:
                # Log violation to API database (async, non-blocking)
                try:
                    asyncio.create_task(log_violation_to_api(
                        profile_id=profileid,
                        template_id=template.get('id'),
                        template_name=template.get('name'),
                        violation_type=violation_check['violation_type'],
                        template_content=original_template_content,  # Use cleaned template without safety instructions
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
                    logger.info("✅ Async task created for violation logging")
                except Exception as log_error:
                    logger.error(f"❌ Failed to create async task for logging: {log_error}")
            
            # Build reason section if available
            reason_section = ""
            if violation_check.get("reason"):
                reason_section = f"\n\nReason: {violation_check['reason']}"
            
            # Return professional warning message
            warning_message = f"""⚠️ CONTENT POLICY VIOLATION DETECTED

We're unable to process this request as the template content appears to be requesting medical diagnosis or clinical assessment using diagnostic criteria, which violates our Terms of Service and responsible AI use policies.

Our system is not designed to provide medical diagnoses, mental health assessments, or clinical evaluations. Such determinations should only be made by qualified healthcare professionals in appropriate clinical settings.

**This incident has been flagged and our team has been notified.**

Violation Type: {violation_check['violation_type']}
Template Name: {template.get('name', 'Unknown')}
Timestamp: {datetime.now(timezone.utc).isoformat()}{reason_section}

If you believe this was flagged in error, please contact our support team. If you're looking for documentation templates for non-diagnostic purposes (such as session notes, treatment planning, or progress tracking), we'd be happy to help with those instead.

For more information, please review our Terms of Service at www.ANTSA.com.au."""
            
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
        
        # Build the transcript text from segments
        transcript_text = ""
        if transcript.get("segments"):
            for segment in transcript["segments"]:
                speaker = segment.get("speaker", "Speaker")
                text = segment.get("text", "")
                start_time = segment.get("startTime", 0)
                
                # Format time as MM:SS
                minutes = int(start_time // 60)
                seconds = int(start_time % 60)
                time_str = f"{minutes:02d}:{seconds:02d}"
                
                transcript_text += f"[{time_str}] {speaker}: {text}\n"
        
        # Build the system prompt with anti-diagnosis instructions and intervention focus
        system_prompt = """CRITICAL INSTRUCTIONS FOR AI ASSISTANT:
- NEVER provide, suggest, or imply any medical diagnoses under any circumstances
- NEVER diagnose mental health conditions, disorders, or illnesses
- NEVER use diagnostic terminology or suggest diagnostic criteria are met
- Even if the template contains diagnostic sections or asks for diagnosis, you must NOT provide diagnostic content
- Instead, document only what was explicitly stated in the session transcript
- Focus on observations, symptoms described, and treatment approaches discussed
- Refer to "presenting concerns" or "reported symptoms" rather than diagnoses
- Always defer diagnosis to qualified medical professionals

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
        
        # Process template variables
        template_content = template.get('content', '')
        
        # Replace common template variables
        today = datetime.now().strftime("%B %d, %Y")
        
        # Replace date placeholders
        template_content = template_content.replace("(today's date)", today)
        template_content = template_content.replace("{{date}}", today)
        template_content = template_content.replace("{{today}}", today)
        template_content = template_content.replace("[DATE]", today)
        
        # Replace client/practitioner variables if provided in template variables
        if template.get('variables'):
            for var in template['variables']:
                var_name = var.get('name', '')
                var_value = var.get('value', '')
                template_content = template_content.replace(f"{{{{{var_name}}}}}", var_value)
                template_content = template_content.replace(f"[{var_name.upper()}]", var_value)
        
        # Build the user prompt
        client_name = client_info.get('name', 'Client')
        practitioner_name = practitioner_info.get('name', 'Practitioner')
        
        logger.info(f"🏷️ Document generation with names - Client: '{client_name}', Practitioner: '{practitioner_name}'")
        
        # Detect if this is a regeneration request (template contains existing document)
        is_regeneration = template_content.startswith("CRITICAL MODIFICATION REQUEST")
        
        if is_regeneration:
            user_prompt = f"""Please generate a clinical document using the following template and transcript:

CLIENT INFORMATION:
- Name: {client_name}
- ID: {client_info.get('id', 'N/A')}

PRACTITIONER INFORMATION:
- Name: {practitioner_name}
- ID: {practitioner_info.get('id', 'N/A')}

TEMPLATE (contains modification request and current document):
{template_content}

SESSION TRANSCRIPT (for reference only - do NOT regenerate from scratch):
{transcript_text}

COMPREHENSIVE OUTPUT REQUIREMENTS - CRITICAL:
- Document ALL topics, themes, and subjects discussed in chronological order - do NOT selectively highlight only major themes
- For SOAP-style templates: The Subjective section must comprehensively cover EVERYTHING the client discussed, not just key highlights
- For Planning sections: List ALL interventions, techniques, tools, and homework assignments mentioned - omit NOTHING
- Provide detailed, thorough responses for each section with specific examples from the transcript
- Include direct quotes when relevant to support your observations
- Avoid summarizing or condensing - err on the side of being exhaustive rather than concise
- If a topic was mentioned even briefly, include it - the practitioner needs a complete record
- Do NOT editorialize or decide what's important - document everything discussed

Please fill out the template using ALL information available in the transcript. If a section cannot be completed based on the transcript content, indicate that the information was not discussed or is not available from this session.

IMPORTANT: Replace any remaining placeholder text like "(today's date)" with actual values. Use today's date: {today}
"""
        else:
            # Normal generation (not regeneration) - include full personalization requirements
            user_prompt = f"""Please generate a clinical document using the following template and transcript:

CLIENT INFORMATION:
- Name: {client_name}
- ID: {client_info.get('id', 'N/A')}

PRACTITIONER INFORMATION:
- Name: {practitioner_name}
- ID: {practitioner_info.get('id', 'N/A')}

CRITICAL PERSONALIZATION REQUIREMENTS - READ THIS CAREFULLY:
YOU MUST USE THESE EXACT NAMES THROUGHOUT THE ENTIRE DOCUMENT:
- Client name: {client_name}
- Practitioner name: {practitioner_name}

FORBIDDEN TERMS - NEVER USE THESE:
- "Client" or "the client" or "client" (use "{client_name}" instead)
- "The counselor" or "counselor" (use "{practitioner_name}" instead) 
- "The therapist" or "therapist" (use "{practitioner_name}" instead)
- "The practitioner" or "practitioner" (use "{practitioner_name}" instead)
- "The patient" or "patient" (use "{client_name}" instead)

CORRECT EXAMPLES:
✓ "{client_name} expressed feeling overwhelmed..."
✓ "{practitioner_name} observed that {client_name} appeared anxious..."
✓ "{practitioner_name} suggested a collaborative approach..."
✓ "{client_name} reported difficulty sleeping..."

INCORRECT EXAMPLES (DO NOT USE):
✗ "The client expressed feeling overwhelmed..."
✗ "The counselor observed that the client appeared anxious..."
✗ "The therapist suggested a collaborative approach..."
✗ "Client reported difficulty sleeping..."

TEMPLATE (with variables processed):
{template_content}

SESSION TRANSCRIPT:
{transcript_text}

FINAL REMINDER BEFORE YOU START WRITING:
- Client name to use: {client_name}
- Practitioner name to use: {practitioner_name}
- Replace ALL instances of generic terms with these specific names
- Check your output before finalizing to ensure you used the names correctly

COMPREHENSIVE OUTPUT REQUIREMENTS - CRITICAL:
- Document ALL topics, themes, and subjects discussed in chronological order - do NOT selectively highlight only major themes
- For SOAP-style templates: The Subjective section must comprehensively cover EVERYTHING the client discussed, not just key highlights
- For Planning sections: List ALL interventions, techniques, tools, and homework assignments mentioned - omit NOTHING
- Provide detailed, thorough responses for each section with specific examples from the transcript
- Include direct quotes when relevant to support your observations
- Avoid summarizing or condensing - err on the side of being exhaustive rather than concise
- If a topic was mentioned even briefly, include it - the practitioner needs a complete record
- Do NOT editorialize or decide what's important - document everything discussed

Please fill out the template using ALL information available in the transcript. If a section cannot be completed based on the transcript content, indicate that the information was not discussed or is not available from this session.

IMPORTANT: Replace any remaining placeholder text like "(today's date)" with actual values. Use today's date: {today}
"""
        
        # Generate document using OpenAI - upgraded to gpt-4o for better intervention analysis
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7  # Increased from 0.3 to allow more comprehensive coverage
            # No max_tokens limit - let the model naturally complete the document
            # GPT-4o supports up to 16,384 output tokens if needed for comprehensive documentation
        )
        
        # Defensive null checks
        if not response or not response.choices or len(response.choices) == 0:
            logger.error(f"Invalid OpenAI response structure: {response}")
            raise HTTPException(status_code=500, detail="Invalid response from OpenAI API")
        
        if not response.choices[0].message:
            logger.error(f"No message in OpenAI response: {response.choices[0]}")
            raise HTTPException(status_code=500, detail="No message content in OpenAI response")
            
        generated_content = response.choices[0].message.content
        
        # Validate response content with detailed error messaging
        if not generated_content or generated_content.strip() == "":
            finish_reason = response.choices[0].finish_reason if response.choices else "unknown"
            usage_info = getattr(response, 'usage', None)
            
            error_detail = "Document generation failed: No content was generated. "
            
            if finish_reason == "content_filter":
                error_detail += "The content was filtered by OpenAI's safety system. Please review your template and transcript for potentially sensitive content."
            elif finish_reason == "length":
                error_detail += "The response was truncated due to token limits. Try using a shorter transcript or simpler template."
            else:
                error_detail += f"This may be due to content filtering, token limits, or prompt issues. (Finish reason: {finish_reason})"
            
            if usage_info:
                error_detail += f" Tokens used: {usage_info.total_tokens if hasattr(usage_info, 'total_tokens') else 'N/A'}"
            
            logger.error(f"Empty content returned from OpenAI - Completion: {response.choices[0]}, Usage: {usage_info}, Finish Reason: {finish_reason}")
            raise HTTPException(
                status_code=500, 
                detail=error_detail
            )
        
        logger.info(f"✅ Document generated successfully, length: {len(generated_content)} characters")
        
        # Note: Document persistence is handled by the API layer to ensure proper
        # handling of preview mode, authentication context, and transaction management.
        # Haystack service is responsible only for document generation via AI.
        
        return GenerateDocumentResponse(
            content=generated_content,
            generatedAt=datetime.now(timezone.utc).isoformat(),
            metadata={
                "templateId": template.get("id"),
                "templateName": template.get("name"),
                "clientId": client_info.get("id"),
                "practitionerId": practitioner_info.get("id"),
                "wordCount": len(generated_content.split()),
                "processingMethod": "haystack_openai"
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Error generating document from template: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate document: {str(e)}")

@app.post("/summarize-ai-conversations")
async def summarize_ai_conversations_endpoint(request: dict):
    """
    Summarize multiple AI conversations between a client and assistant.
    
    Expected request format:
    {
        "conversations": [
            {
                "id": "conversation_id",
                "createdAt": "2024-01-01T00:00:00Z",
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there!"}
                ]
            }
        ]
    }
    """
    try:
        logger.info("🔄 Processing AI conversation summarization request")
        
        conversations_data = request.get("conversations", [])
        if not conversations_data:
            raise HTTPException(status_code=400, detail="No conversations provided")
        
        logger.info(f"📊 Summarizing {len(conversations_data)} conversations")
        
        # Import the function from tools
        from tools import summarize_ai_conversations
        
        # Generate the summary
        result = summarize_ai_conversations(conversations_data)
        
        if result.get("status") == "error":
            logger.error(f"❌ Summarization failed: {result.get('error')}")
            raise HTTPException(status_code=500, detail=result.get("error"))
        
        logger.info("✅ Successfully generated AI conversation summary")
        
        return {
            "summary": result.get("summary"),
            "metadata": result.get("metadata", {}),
            "status": "success"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in conversation summarization endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to summarize conversations: {str(e)}")

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    websocket_connections[session_id] = websocket
    logger.info(f"WebSocket connected for session {session_id}")
    
    await websocket.send_text(json.dumps({
        "type": "connection_established",
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }))
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data.get("type") == "heartbeat":
                await websocket.send_text(json.dumps({
                    "type": "heartbeat_ack",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "session_id": session_id
                }))
                continue
                
            if message_data.get("type") == "ui_state_update":
                # Store UI state and (optionally) auth token
                state = message_data.get("state", {})
                auth_token = message_data.get("auth_token") or message_data.get("token")
                ui_states[session_id] = state
                try:
                    ui_state_manager.update_state(session_id, state, auth_token=auth_token)
                except Exception as e:
                    logger.warning(f"Failed to persist UI state via manager: {e}")
                logger.info(f"Updated UI state for session {session_id}")
                # Proactively set tool context if available
                await _ensure_tools_context(session_id, message_data)
                continue
            
            message = message_data.get("message", "")
            if not message.strip():
                continue
                
            logger.info(f"Processing message for session {session_id}: {message[:50]}...")
            
            await websocket.send_text(json.dumps({
                "type": "typing",
                "typing": True,
                "session_id": session_id
            }))
            
            try:
                # Ensure tools have context (auth/page/profile) before handling
                await _ensure_tools_context(session_id, message_data)

                # Build context for pipeline
                ui_state = ui_states.get(session_id) or {}
                derived = _build_page_context_from_ui_state(ui_state)
                
                # Extract profile_id for session recovery
                profile_id = message_data.get("profile_id") or message_data.get("profileId")
                
                context_for_pipeline: Dict[str, Any] = {
                    "page_url": ui_state.get("page_url"),
                    "ui_capabilities": derived.get("capabilities", []),
                    "client_id": ui_state.get("client_id"),
                    "active_tab": ui_state.get("active_tab"),
                    "page_context": derived.get("page_type"),
                    "profile_id": profile_id,  # Include profile_id for session recovery
                }

                # Resolve persona and auth token
                sess = await session_manager.get_session(session_id)
                persona_str = (sess.persona_type if sess else "web_assistant")
                try:
                    persona_enum = PersonaType(persona_str)
                except Exception:
                    persona_enum = PersonaType.WEB_ASSISTANT
                auth_token = message_data.get("auth_token") or message_data.get("token") or ui_state_manager.get_auth_token(session_id)

                # Stream via Haystack pipeline manager (tool-enabled, history-aware)
                full_content = ""
                async for out_chunk in pipeline_manager.generate_response_with_chaining(
                    session_id=session_id,
                    persona_type=persona_enum,
                    user_message=message,
                    context=context_for_pipeline,
                    auth_token=auth_token,
                ):
                    if not isinstance(out_chunk, str):
                        continue
                    full_content += out_chunk
                    await websocket.send_text(json.dumps({
                        "type": "message_chunk",
                        "content": out_chunk,
                        "full_content": full_content,
                        "session_id": session_id
                    }))

                # Persist assistant reply
                try:
                    from session_manager import session_manager as _sm
                    await _sm.add_message(session_id, "assistant", full_content)
                except Exception:
                    pass

                # Deliver any collected UI actions to the frontend
                try:
                    ui_actions = pipeline_manager.pop_ui_actions()
                    logger.info(f"🎯 [WEBSOCKET] Retrieved {len(ui_actions)} UI actions from pipeline")
                    for action in ui_actions:
                        logger.info(f"🎯 [WEBSOCKET] Sending UI action to frontend: {action}")
                        await websocket.send_text(json.dumps({
                            "type": "ui_action",
                            "action": action,
                            "session_id": session_id
                        }))
                        logger.info(f"🎯 [WEBSOCKET] UI action sent successfully")
                except Exception as e:
                    logger.error(f"🚨 [WEBSOCKET] Failed to deliver UI actions: {e}")

                # Signal completion to the UI
                await websocket.send_text(json.dumps({
                    "type": "message_complete",
                    "session_id": session_id
                }))
                    
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                await send_streaming_response(websocket, session_id, 
                    "I encountered an error processing your request. Please try again.")
            
            await websocket.send_text(json.dumps({
                "type": "typing",
                "typing": False,
                "session_id": session_id
            }))
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
        if session_id in websocket_connections:
            del websocket_connections[session_id]
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        if session_id in websocket_connections:
            del websocket_connections[session_id]

async def handle_template_request(message: str, session_id: str) -> str:
    """Handle template-related requests"""
    
    message_lower = message.lower()
    
    try:
        if "get" in message_lower or "show" in message_lower or "what" in message_lower:
            # Get templates via tool wrapper to receive a success flag consistently
            if not tool_manager:
                return "Templates are unavailable right now."

            tool_result = await tool_manager.execute_tool("get_templates", {})
            if tool_result.get("success"):
                result_payload = tool_result.get("result") or {}
                templates = result_payload.get("templates", [])
                if templates:
                    response = "Here are your available templates:\n\n"
                    for i, template in enumerate(templates[:10], 1):
                        name = template.get('name', 'Unnamed')
                        description = template.get('description', 'No description')
                        response += f"**{i}. {name}**\n   {description}\n\n"

                    response += "\nTo load a template, just tell me which one you'd like to use!"
                    return response
                else:
                    return "No templates are currently available."
            else:
                return f"I couldn't access templates: {tool_result.get('error', 'Unknown error')}"
        
        elif "load" in message_lower or "select" in message_lower:
            return "To load a template, I'll need to know which template you'd like to use. Please ask me to 'show templates' first to see what's available."
        
        else:
            return "I can help you with templates! You can ask me to:\n- Show available templates\n- Load a specific template\n- Generate documents from templates"
            
    except Exception as e:
        logger.error(f"Template request error: {e}")
        return f"I encountered an error with templates: {str(e)}"

async def handle_openai_chat(websocket: WebSocket, session_id: str, message: str, message_data: Dict[str, Any]):
    """Handle regular OpenAI chat with streaming"""
    
    try:
        # Get session info
        sess = await session_manager.get_session(session_id)
        persona_type = (sess.persona_type if sess else "web_assistant")
        ui_state = ui_states.get(session_id, {})
        
        system_prompt = get_enhanced_system_prompt(persona_type, ui_state)
        
        # Add context from message_data
        context = message_data.get("context", {})
        if context:
            context_str = f"\nAdditional Context: {json.dumps(context, indent=2)}"
            system_prompt += context_str
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]
        
        # OpenAI streaming
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            stream=True,
            max_tokens=1000,
            temperature=0.7
        )
        
        full_content = ""
        
        async for chunk in response:
            if hasattr(chunk, 'choices') and chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content') and delta.content:
                    content_chunk = delta.content
                    full_content += content_chunk
                    
                    await websocket.send_text(json.dumps({
                        "type": "message_chunk",
                        "content": content_chunk,
                        "full_content": full_content,
                        "session_id": session_id
                    }))
        
        await websocket.send_text(json.dumps({
            "type": "message_complete",
            "session_id": session_id
        }))
        
    except Exception as e:
        logger.error(f"OpenAI chat error: {e}")
        await send_streaming_response(websocket, session_id,
            "I apologize, but I encountered an error. Please try again.")

async def send_streaming_response(websocket: WebSocket, session_id: str, response_text: str):
    """Send response with streaming effect"""
    words = response_text.split(' ')
    full_content = ""
    
    for i, word in enumerate(words):
        if i == 0:
            full_content = word
        else:
            full_content += " " + word
        
        await websocket.send_text(json.dumps({
            "type": "message_chunk",
            "content": word if i == 0 else " " + word,
            "full_content": full_content,
            "session_id": session_id
        }))
        
        await asyncio.sleep(0.02)
    
    await websocket.send_text(json.dumps({
        "type": "message_complete",
        "session_id": session_id
    }))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    host = os.environ.get("HOST", "0.0.0.0")
    
    logger.info(f"Starting Haystack Service on {host}:{port}")
    logger.info(f"Tools available: {bool(tool_manager)}")
    
    uvicorn.run(
        app, 
        host=host, 
        port=port,
        log_level="info"
    )
