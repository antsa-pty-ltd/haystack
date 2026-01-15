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
from haystack_pipeline import haystack_pipeline_manager
from personas import PersonaType, persona_manager
from session_manager import session_manager
from agents.document_agent import initialize_agent, get_document_agent
from document_generation.generator import generate_document_from_context
from utils.session_utils import fetch_session_metadata, estimate_tokens_from_segments

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
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8080/api/v1")

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
pipeline_manager = haystack_pipeline_manager

# ===== SEMANTIC SEARCH CONFIGURATION =====
# These settings control the quality vs. coverage tradeoff for document generation
SEMANTIC_SEARCH_CONFIG = {
    # Base similarity threshold (will be relaxed if results are sparse)
    "base_similarity_threshold": 0.5,
    
    # Minimum similarity threshold (won't go below this)
    "min_similarity_threshold": 0.2,
    
    # Threshold reduction per retry attempt
    "threshold_reduction_step": 0.15,
    
    # Temporal context window (segments before/after high-relevance matches)
    "temporal_context_window": 2,
    
    # Minimum relevance score to fetch temporal context (0.0-1.0)
    "min_relevance_for_context": 0.6,
    
    # Maximum retry attempts when relaxing threshold
    "max_threshold_attempts": 3,
    
    # Minimum expected results as fraction of requested (e.g., 0.33 = expect at least 1/3)
    "min_result_fraction": 0.33,
    
    # ===== INTELLIGENT RETRIEVAL CONFIGURATION =====
    # Token threshold for "pull all" strategy (~50K tokens, well under 128K context limit)
    "pull_all_token_threshold": 50000,
    
    # Segment count threshold per session (< 100 segments = small session)
    "small_session_segment_threshold": 100,
    
    # Max sessions for "pull all" strategy
    "max_sessions_for_pull_all": 2,
    
    # Average tokens per segment (for estimation)
    "avg_tokens_per_segment": 75,
}
# ==========================================

# ===== PROGRESS EMISSION HELPER =====
async def emit_progress(generation_id: str, data: dict, authorization: Optional[str] = None):
    """
    Emit progress update to API via HTTP POST, which will broadcast via WebSocket
    """
    if not generation_id:
        # No generationId means no progress tracking (legacy mode)
        return
    
    try:
        api_url = os.getenv("NESTJS_API_URL", "http://localhost:8080")
        
        payload = {
            "generationId": generation_id,
            **data
        }
        
        # Use Authorization header if provided
        headers = {}
        if authorization:
            headers["Authorization"] = authorization
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{api_url}/api/v1/ai/websocket/document-progress",
                json=payload,
                headers=headers
            )
            
            if response.status_code != 200:
                logger.warning(f"Failed to emit progress (HTTP {response.status_code}): {response.text}")
    except Exception as e:
        # Don't fail document generation if progress emission fails
        logger.error(f"Failed to emit progress for generation {generation_id}: {e}")
# ====================================

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
        await ui_state_manager.initialize()
        logger.info("✅ UI State Manager initialized")
    except Exception as e:
        logger.warning(f"⚠️ UI State Manager init warning: {e}")
    try:
        await session_manager.initialize()
    except Exception as e:
        logger.warning(f"Session manager init warning: {e}")
    
    # Initialize document exploration agent
    if openai_api_key:
        try:
            initialize_agent(openai_api_key, model="gpt-5.2")
            logger.info("✅ Document Exploration Agent initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Document Agent: {e}")
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

# WebSocket connections and message buffers for ordering
websocket_connections: Dict[str, WebSocket] = {}
message_buffers: Dict[str, List[Dict[str, Any]]] = {}

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
    sessionIds: List[str]
    clientInfo: Dict[str, Any]
    practitionerInfo: Dict[str, Any]
    generationInstructions: Optional[str] = None
    clientContextData: Optional[Dict[str, Any]] = None
    generationId: Optional[str] = None  # For progress tracking via WebSocket

class GenerateDocumentResponse(BaseModel):
    content: str
    generatedAt: str
    metadata: Dict[str, Any] = {}

class ChatRequest(BaseModel):
    message: str
    persona_type: str = "web_assistant"
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    content: str  # API expects 'content' or 'message'
    message: str  # Alias for compatibility
    session_id: str
    message_id: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None

def get_enhanced_system_prompt(persona_type: str, ui_state: Dict[str, Any] = None) -> str:
    """Get enhanced system prompt using personas.py"""
    try:
        # Convert string to PersonaType enum
        persona_enum = PersonaType(persona_type)
    except ValueError:
        persona_enum = PersonaType.WEB_ASSISTANT
    
    # Get base system prompt from personas.py
    base_prompt = persona_manager.get_system_prompt(persona_enum)
    
    # Add UI-specific context enhancements
    if ui_state:
        derived_context = _build_page_context_from_ui_state(ui_state)
        
        # Add current page context
        if derived_context.get('page_display_name'):
            base_prompt += f"\n\n📍 CURRENT PAGE: {derived_context['page_display_name']}"
        
        # Add UI state context
        page_url = ui_state.get('page_url', '')
        client_name = ui_state.get('client_name')
        client_id = ui_state.get('client_id')
        selected_template = ui_state.get('selected_template')
        loaded_sessions = ui_state.get('loadedSessions', [])
        generated_documents = ui_state.get('generatedDocuments', [])
        active_document = ui_state.get('active_document')
        
        context_parts = []
        context_parts.append(f"Page: {page_url}")
        
        # IMPORTANT: Only show client info if both name AND id are present (indicates active selection)
        # Do NOT inject client_id alone as it may be stale from previous sessions
        if client_name and client_id:
            context_parts.append(f"Client: {client_name} ({client_id})")
        elif client_name:
            context_parts.append(f"Client: {client_name} (use search_clients to get ID)")
        else:
            context_parts.append(f"Client: None (use search_clients if needed)")
        
        context_parts.append(f"Template: {selected_template.get('name') if selected_template else 'None'}")
        context_parts.append(f"Loaded Sessions: {len(loaded_sessions)}")
        context_parts.append(f"Generated Documents: {len(generated_documents)}")
        
        base_prompt += f"\n\n🔍 UI STATE:\n" + "\n".join(f"- {part}" for part in context_parts)
        
        # Add active document info
        if active_document and active_document.get('document'):
            doc = active_document['document']
            base_prompt += f"\n\n📄 ACTIVE DOCUMENT: {doc.get('documentName', 'Unnamed')} (ID: {doc.get('documentId')})"
    
    return base_prompt


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
    ui_state_token = await ui_state_manager.get_auth_token(session_id)
    
    # Also check the stored session for auth token and profile_id
    session_token = None
    session_profile_id = None
    try:
        sess = await session_manager.get_session(session_id)
        if sess:
            session_token = sess.auth_token
            session_profile_id = sess.profile_id
    except Exception:
        pass
    
    token = incoming_token or ui_state_token or session_token

    logger.info(f"🔍 Debug auth context for session {session_id}: incoming_token={bool(incoming_token)}, ui_state_token={bool(ui_state_token)}, session_token={bool(session_token)}, final_token={bool(token)}")

    if token:
        # Try to get profile_id from message, then fall back to session
        profile_id = message_data.get("profile_id") or message_data.get("profileId") or session_profile_id
        logger.info(f"🔍 Debug profile_id extraction: from_message={message_data.get('profile_id') or message_data.get('profileId')}, from_session={session_profile_id}, final={profile_id}")
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
    # Try message first, then session fallback
    profile_id = message_data.get("profile_id") or message_data.get("profileId") or session_profile_id
    if profile_id and isinstance(profile_id, str) and not profile_id.startswith("client-"):
        logger.info(f"🔍 Debug: explicitly setting profile_id={profile_id}")
        try:
            tool_manager.set_profile_id(profile_id)
        except Exception:
            pass
    elif profile_id and isinstance(profile_id, str) and profile_id.startswith("client-"):
        logger.info("🔍 Debug: skipping explicit profile_id set for client context")
    else:
        logger.warning(f"⚠️ No valid profile_id found for session {session_id} - tool calls requiring practitioner context may fail")

    # Attach page context derived from latest UI state for this session
    ui_state = await ui_state_manager.get_state(session_id)
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

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, authorization: str = Header(None), profileid: str = Header(None)):
    """Send a chat message and get a complete response (non-streaming)"""
    try:
        logger.info(f"📨 Chat request received - persona: {request.persona_type}, session: {request.session_id}")
        
        # Extract auth token from Authorization header
        auth_token = None
        if authorization and authorization.startswith("Bearer "):
            auth_token = authorization[7:]
        
        # Create session if not provided
        session_id = request.session_id
        if not session_id:
            session_id = await session_manager.create_session(
                persona_type=request.persona_type,
                context=request.context or {},
                auth_token=auth_token,
                profile_id=profileid,
            )
            logger.info(f"Created new session for chat: {session_id}")
        
        # Get session info and UI state
        sess = await session_manager.get_session(session_id)
        persona_type = sess.persona_type if sess else request.persona_type
        ui_state = await ui_state_manager.get_state(session_id)
        
        # Get enhanced system prompt
        system_prompt = get_enhanced_system_prompt(persona_type, ui_state)
        
        # Add user message to session history
        await session_manager.add_message(session_id, "user", request.message)
        
        # Get conversation history
        history = await session_manager.get_messages(session_id, limit=20)
        
        # Build messages for OpenAI
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})
        
        # Generate response using OpenAI
        if not openai_client:
            raise HTTPException(status_code=500, detail="OpenAI client not configured")
        
        response = await openai_client.chat.completions.create(
            model="gpt-5.2",
            messages=messages,
            temperature=0.7,
            max_completion_tokens=4096
        )
        
        response_text = response.choices[0].message.content or ""
        
        # Add assistant response to session history
        message_id = str(uuid.uuid4())
        await session_manager.add_message(session_id, "assistant", response_text)
        
        logger.info(f"✅ Chat response generated for session {session_id}")
        
        return ChatResponse(
            content=response_text,
            message=response_text,
            session_id=session_id,
            message_id=message_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={"persona_type": persona_type}
        )
        
    except Exception as e:
        logger.error(f"❌ Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def fetch_session_metadata(session_id: str, authorization: str = None) -> Optional[Dict[str, Any]]:
    """
    Fetch metadata for a session including duration, segment count, and dates.
    
    Args:
        session_id: The transcript/session ID
        authorization: Authorization header for API requests
        
    Returns:
        Dict with keys: totalSegments, duration, recordingDate, createdAt, sessionId
        Returns None if fetch fails
    """
    try:
        api_url = os.getenv("NESTJS_API_URL", "http://localhost:8080")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {}
            if authorization:
                headers["Authorization"] = authorization
            
            response = await client.get(
                f"{api_url}/api/v1/ai/transcriptions/{session_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "sessionId": session_id,
                    "totalSegments": data.get("totalSegments", 0),
                    "duration": data.get("duration", 0),
                    "recordingDate": data.get("recordingDate"),
                    "createdAt": data.get("createdAt"),
                }
            else:
                logger.warning(f"Failed to fetch metadata for session {session_id}: HTTP {response.status_code}")
                return None
                
    except Exception as e:
        logger.error(f"Error fetching session metadata for {session_id}: {e}")
        return None


def estimate_tokens_from_segments(segment_count: int) -> int:
    """
    Estimate token count from segment count.
    
    Uses conservative estimate of avg_tokens_per_segment from config.
    
    Args:
        segment_count: Number of segments in the session
        
    Returns:
        Estimated token count
    """
    return segment_count * SEMANTIC_SEARCH_CONFIG["avg_tokens_per_segment"]


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
            max_completion_tokens=200
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
    """
    Generate a document using agentic exploration of therapy sessions.
    
    This endpoint uses the DocumentExplorationAgent which is SEPARATE from
    the web_assistant and jaimee_therapist agents. It doesn't interfere with
    those agents - it's only used for document generation.
    """
    from document_generation.agentic_endpoint import generate_document_from_template_agentic
    
    return await generate_document_from_template_agentic(
        request=request,
        http_request=http_request,
        authorization=authorization,
        profileid=profileid,
        openai_client=openai_client,
        emit_progress_func=emit_progress,
        detect_policy_violation_func=detect_policy_violation,
        log_violation_func=log_violation_to_api
    )
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
                # Handle UI state update - supports BOTH formats:
                # 1. Full state format: { type: "ui_state_update", state: {...}, auth_token: "..." }
                # 2. Incremental format: { type: "ui_state_update", changeType: "...", payload: {...}, ... }
                
                # Extract auth token if present
                auth_token = message_data.get("auth_token") or message_data.get("token")
                
                # Extract profile_id if present
                profile_id = message_data.get("profile_id") or message_data.get("profileId")
                
                # Check which format we received
                if "state" in message_data:
                    # Full state format from ai-ui-integration.ts
                    full_state = message_data.get("state", {})
                    timestamp = full_state.get("timestamp", datetime.now(timezone.utc).isoformat())
                    
                    # Add profile_id to state for tracking
                    if profile_id:
                        full_state["profile_id"] = profile_id
                    
                    # Store the full state directly
                    try:
                        await ui_state_manager.update_state(session_id, full_state, auth_token=auth_token)
                        logger.info(f"✅ Updated full UI state for session {session_id}: {len(full_state.get('generatedDocuments', []))} docs, {len(full_state.get('loadedSessions', []))} sessions")
                        success = True
                    except Exception as e:
                        logger.error(f"❌ Failed to update UI state for {session_id}: {e}")
                        success = False
                else:
                    # Incremental format with changeType/payload
                    change_type = message_data.get("changeType", "unknown")
                    payload = message_data.get("payload", {})
                    timestamp = message_data.get("timestamp", datetime.now(timezone.utc).isoformat())
                    page_type = message_data.get("page_type", "")
                    page_url = message_data.get("page_url", "")
                    sequence = message_data.get("sequence", 0)
                    
                    # Build incremental changes dict
                    changes: Dict[str, Any] = {
                        change_type: payload,
                        "page_type": page_type,
                        "page_url": page_url,
                    }
                    
                    # Add profile_id to changes if present
                    if profile_id:
                        changes["profile_id"] = profile_id
                    
                    # Add sequence if provided
                    if sequence:
                        changes["sequence"] = sequence
                    
                    # Persist to Redis via ui_state_manager
                    try:
                        success = await ui_state_manager.update_incremental(
                            session_id, changes, timestamp
                        )
                        
                        # Also store auth token if provided
                        if auth_token and success:
                            await ui_state_manager.update_state(
                                session_id, 
                                await ui_state_manager.get_state(session_id),
                                auth_token=auth_token
                            )
                        
                        logger.info(f"✅ Updated UI state for session {session_id}: {change_type}")
                    except Exception as e:
                        logger.error(f"❌ Failed to update UI state for {session_id}: {e}")
                        success = False
                
                # Send acknowledgment
                await websocket.send_text(json.dumps({
                    "type": "ui_state_ack",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "success": success,
                    "session_id": session_id
                }))
                
                # Proactively set tool context if available
                await _ensure_tools_context(session_id, message_data)
                
                # Process any buffered chat messages waiting for state
                if session_id in message_buffers and message_buffers[session_id]:
                    logger.info(f"🔄 Processing {len(message_buffers[session_id])} buffered messages for {session_id}")
                    buffered = message_buffers[session_id]
                    message_buffers[session_id] = []
                    for buffered_msg in buffered:
                        # Re-process buffered message (will be handled by main loop)
                        pass
                
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
                ui_state = await ui_state_manager.get_state(session_id)
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
                auth_token = message_data.get("auth_token") or message_data.get("token") or await ui_state_manager.get_auth_token(session_id)

                # Progress callback for tool call visibility
                async def send_progress(data: dict):
                    """Send progress updates to frontend via WebSocket"""
                    try:
                        await websocket.send_text(json.dumps(data))
                    except Exception as e:
                        logger.warning(f"Failed to send progress update: {e}")

                # Stream via Haystack pipeline manager (tool-enabled, history-aware)
                full_content = ""
                async for out_chunk in pipeline_manager.generate_response_with_chaining(
                    session_id=session_id,
                    persona_type=persona_enum,
                    user_message=message,
                    context=context_for_pipeline,
                    auth_token=auth_token,
                    progress_callback=send_progress,
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
        # Note: UI state is NOT cleaned up here - it persists with 24h TTL in Redis
        # This allows reconnection and state recovery
        # Cleanup message buffer
        message_buffers.pop(session_id, None)
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        if session_id in websocket_connections:
            del websocket_connections[session_id]
        # On error, also keep state for potential recovery
        message_buffers.pop(session_id, None)

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
        ui_state = await ui_state_manager.get_state(session_id)
        
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

# Debug endpoints for state inspection
@app.get("/debug/sessions/{session_id}/state")
async def debug_session_state(session_id: str, authorization: Optional[str] = Header(None)):
    """Debug endpoint - get UI state for a specific session (requires auth in production)"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized - Authorization header required")
    
    ui_state = await ui_state_manager.get_state(session_id)
    capabilities = await ui_state_manager.get_page_capabilities(session_id)
    
    return {
        "session_id": session_id,
        "ui_state": ui_state,
        "available_capabilities": capabilities,
        "last_updated": ui_state.get("last_updated"),
        "redis_connected": ui_state_manager._initialized
    }

@app.get("/debug/sessions")
async def debug_all_sessions(authorization: Optional[str] = Header(None)):
    """Debug endpoint - list all active sessions (requires auth in production)"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized - Authorization header required")
    
    # Get all sessions summary from ui_state_manager
    sessions = await ui_state_manager.get_all_sessions_summary()
    
    return {
        "total_sessions": len(sessions),
        "sessions": sessions,
        "redis_connected": ui_state_manager._initialized
    }

@app.get("/debug/redis/health")
async def debug_redis_health(authorization: Optional[str] = Header(None)):
    """Debug endpoint - check Redis connection health"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized - Authorization header required")
    
    try:
        if ui_state_manager._initialized and ui_state_manager.redis_client:
            await ui_state_manager.redis_client.ping()
            return {
                "redis_connected": True,
                "status": "healthy",
                "message": "Redis connection is working"
            }
        else:
            return {
                "redis_connected": False,
                "status": "disconnected",
                "message": "Redis client not initialized (using in-memory fallback)"
            }
    except Exception as e:
        return {
            "redis_connected": False,
            "status": "error",
            "message": f"Redis connection error: {str(e)}"
        }

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
