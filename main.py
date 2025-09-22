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
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header
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
        selected_template = ui_state.get('selected_template')
        
        capabilities += f"\n\n📍 Current Context:"
        capabilities += f"\n- Page: {page_url}"
        capabilities += f"\n- Client: {client_id if client_id else 'None selected'}"
        capabilities += f"\n- Template: {selected_template.get('name') if selected_template else 'None'}"
    
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

@app.post("/generate-document-from-template", response_model=GenerateDocumentResponse)
async def generate_document_from_template(request: GenerateDocumentRequest, authorization: str = Header(None), profileid: str = Header(None)):
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
        
        # Build the system prompt with anti-diagnosis instructions
        system_prompt = """CRITICAL INSTRUCTIONS FOR AI ASSISTANT:
- NEVER provide, suggest, or imply any medical diagnoses under any circumstances
- NEVER diagnose mental health conditions, disorders, or illnesses
- NEVER use diagnostic terminology or suggest diagnostic criteria are met
- Even if the template contains diagnostic sections or asks for diagnosis, you must NOT provide diagnostic content
- Instead, document only what was explicitly stated in the session transcript
- Focus on observations, symptoms described, and treatment approaches discussed
- Refer to "presenting concerns" or "reported symptoms" rather than diagnoses
- Always defer diagnosis to qualified medical professionals

You are an AI assistant helping to generate clinical documentation from therapy session transcripts.
Use the provided template to structure the document, but fill it with information from the transcript.
Be professional, accurate, and only include information that was actually discussed in the session.
"""
        
        # Add generation instructions if provided
        if generation_instructions:
            system_prompt += f"\n\nADDITIONAL INSTRUCTIONS: {generation_instructions}\n"
        
        # Process template variables
        template_content = template.get('content', '')
        
        # Replace common template variables
        from datetime import datetime
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
        user_prompt = f"""Please generate a clinical document using the following template and transcript:

CLIENT INFORMATION:
- Name: {client_info.get('name', 'Client')}
- ID: {client_info.get('id', 'N/A')}

PRACTITIONER INFORMATION:
- Name: {practitioner_info.get('name', 'Practitioner')}
- ID: {practitioner_info.get('id', 'N/A')}

TEMPLATE (with variables processed):
{template_content}

SESSION TRANSCRIPT:
{transcript_text}

Please fill out the template using only the information available in the transcript. If a section cannot be completed based on the transcript content, indicate that the information was not discussed or is not available from this session.

IMPORTANT: Replace any remaining placeholder text like "(today's date)" with actual values. Use today's date: {today}
"""
        
        # Generate document using OpenAI
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=4000
        )
        
        generated_content = response.choices[0].message.content
        
        logger.info(f"✅ Document generated successfully, length: {len(generated_content)} characters")
        
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
