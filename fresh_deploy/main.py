import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from personas import PersonaType, persona_manager
from session_manager import session_manager, ChatMessage
from pipeline_manager import pipeline_manager
from haystack_pipeline import haystack_pipeline_manager

# Configure logging
logging.basicConfig(level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)

# Pydantic models for API
class ChatRequest(BaseModel):
    message: str
    persona_type: PersonaType
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    message_id: str
    timestamp: str

class SessionRequest(BaseModel):
    persona_type: PersonaType
    context: Optional[Dict[str, Any]] = None
    profile_id: Optional[str] = None

class SessionResponse(BaseModel):
    session_id: str
    persona_type: str
    created_at: str

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    service_info: Dict[str, Any]

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.session_connections: Dict[str, List[str]] = {}  # session_id -> [connection_ids]
    
    async def connect(self, websocket: WebSocket, connection_id: str, session_id: str):
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        
        if session_id not in self.session_connections:
            self.session_connections[session_id] = []
        self.session_connections[session_id].append(connection_id)
        
        logger.info(f"WebSocket connected: {connection_id} for session: {session_id}")
    
    def disconnect(self, connection_id: str, session_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        
        if session_id in self.session_connections:
            if connection_id in self.session_connections[session_id]:
                self.session_connections[session_id].remove(connection_id)
            
            # Clean up empty session connections
            if not self.session_connections[session_id]:
                del self.session_connections[session_id]
        
        logger.info(f"WebSocket disconnected: {connection_id} from session: {session_id}")
    
    async def send_to_session(self, session_id: str, message: dict):
        """Send message to all connections for a session"""
        if session_id not in self.session_connections:
            return
        
        disconnected_connections = []
        
        for connection_id in self.session_connections[session_id]:
            if connection_id in self.active_connections:
                try:
                    await self.active_connections[connection_id].send_text(json.dumps(message))
                except Exception as e:
                    logger.warning(f"Failed to send to connection {connection_id}: {e}")
                    disconnected_connections.append(connection_id)
        
        # Clean up failed connections
        for connection_id in disconnected_connections:
            self.disconnect(connection_id, session_id)

manager = ConnectionManager()

# Application lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting Haystack AI Service...")
    
    try:
        # Initialize services
        await session_manager.initialize()
        await pipeline_manager.initialize()
        await haystack_pipeline_manager.initialize()
        
        logger.info("✅ Haystack AI Service started successfully")
        yield
        
    except Exception as e:
        logger.error(f"❌ Failed to start service: {e}")
        raise
    
    finally:
        # Shutdown
        logger.info("🛑 Shutting down Haystack AI Service...")
        await pipeline_manager.shutdown()
        await session_manager.close()
        logger.info("✅ Service shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="Haystack AI Service",
    description="Scalable AI chat service using Haystack pipelines",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    try:
        session_count = await session_manager.get_active_sessions_count()
        
        # Simplified pipeline status to avoid serialization issues
        pipeline_status = {
            "initialized": pipeline_manager._initialized,
            "active_requests": len(pipeline_manager.active_requests)
        }
        
        return HealthResponse(
            status="healthy",
            timestamp=datetime.utcnow().isoformat(),
            service_info={
                "active_sessions": session_count,
                "active_websocket_connections": len(manager.active_connections),
                "pipeline_status": pipeline_status,
                "max_concurrent_requests": settings.max_concurrent_requests
            }
        )
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return HealthResponse(
            status="error",
            timestamp=datetime.utcnow().isoformat(),
            service_info={"error": str(e)}
        )

# Session management endpoints
@app.post("/sessions", response_model=SessionResponse)
async def create_session(request: SessionRequest, authorization: Optional[str] = Header(None)):
    """Create a new chat session"""
    try:
        # Extract auth token from Authorization header
        auth_token = None
        if authorization and authorization.startswith("Bearer "):
            auth_token = authorization.replace("Bearer ", "")
        
        session_id = await session_manager.create_session(
            request.persona_type.value,
            request.context,
            auth_token,
            request.profile_id
        )
        
        session = await session_manager.get_session(session_id)
        
        return SessionResponse(
            session_id=session_id,
            persona_type=session.persona_type,
            created_at=session.created_at.isoformat()
        )
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, limit: Optional[int] = None):
    """Get messages from a session"""
    try:
        messages = await session_manager.get_messages(session_id, limit)
        return {
            "session_id": session_id,
            "messages": [msg.to_dict() for msg in messages]
        }
    except Exception as e:
        logger.error(f"Error getting session messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session"""
    try:
        deleted = await session_manager.delete_session(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {"message": "Session deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Chat endpoint (non-streaming)
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, background_tasks: BackgroundTasks, authorization: Optional[str] = Header(None)):
    """Send a chat message and get a complete response"""
    try:
        # Extract auth token from Authorization header
        auth_token = None
        if authorization and authorization.startswith("Bearer "):
            auth_token = authorization.replace("Bearer ", "")
        
        # Create session if not provided
        session_id = request.session_id
        if not session_id:
            session_id = await session_manager.create_session(
                request.persona_type.value,
                request.context,
                auth_token
            )
        
        # Generate response
        response_text = await pipeline_manager.generate_non_streaming_response(
            session_id=session_id,
            persona_type=request.persona_type,
            user_message=request.message,
            context=request.context,
            auth_token=auth_token
        )
        
        # Get the latest assistant message
        messages = await session_manager.get_messages(session_id, limit=1)
        latest_message = messages[-1] if messages else None
        
        return ChatResponse(
            response=response_text,
            session_id=session_id,
            message_id=latest_message.message_id if latest_message else "",
            timestamp=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket endpoint for streaming chat
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str, authorization: Optional[str] = None):
    """WebSocket endpoint for real-time streaming chat"""
    connection_id = f"{session_id}_{datetime.utcnow().timestamp()}"
    
    # Try to extract auth token from query params as fallback
    query_token = None
    if hasattr(websocket, 'query_params') and 'token' in websocket.query_params:
        query_token = websocket.query_params['token']
    
    try:
        await manager.connect(websocket, connection_id, session_id)
        
        # Send connection confirmation
        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "session_id": session_id,
            "connection_id": connection_id
        }))
        
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data.get("type") == "chat_message":
                user_message = message_data.get("message", "")
                persona_type = PersonaType(message_data.get("persona_type", "web_assistant"))
                context = message_data.get("context", {})
                # Get auth token from session first, then fallback to message/query
                session = await session_manager.get_session(session_id)
                auth_token = None
                
                if session and session.auth_token:
                    auth_token = session.auth_token
                    logger.info(f"Using session auth token for {session_id}")
                else:
                    # Fallback to message or query params
                    auth_token = message_data.get("auth_token") or query_token
                    if auth_token:
                        # Update session with new token
                        await session_manager.update_session_auth_token(session_id, auth_token)
                        logger.info(f"Updated session auth token for {session_id}")
                    else:
                        logger.warning(f"No auth token found for session {session_id}")
                
                # Send typing indicator
                await manager.send_to_session(session_id, {
                    "type": "typing",
                    "typing": True
                })
                
                # Generate streaming response
                full_response = ""
                print(f"🔍 DEBUG: Starting streaming response generation...")
                try:
                    async for chunk in pipeline_manager.generate_response(
                        session_id=session_id,
                        persona_type=persona_type,
                        user_message=user_message,
                        context=context,
                        auth_token=auth_token
                    ):
                        full_response += chunk
                        
                        # Send chunk to all connections for this session
                        await manager.send_to_session(session_id, {
                            "type": "message_chunk",
                            "content": chunk,
                            "full_content": full_response
                        })
                    
                    print(f"🔍 DEBUG: Streaming completed, now checking for UI actions...")
                except Exception as e:
                    print(f"🔍 DEBUG: Exception during streaming: {e}")
                    raise
                
                # Check for UI actions from both pipeline managers
                print(f"🔍 DEBUG: Checking for UI actions...")
                print(f"🔍 DEBUG: pipeline_manager has _ui_actions: {hasattr(pipeline_manager, '_ui_actions')}")
                print(f"🔍 DEBUG: haystack_pipeline_manager has _ui_actions: {hasattr(haystack_pipeline_manager, '_ui_actions')}")
                
                ui_actions = []
                # Check regular pipeline_manager first
                if hasattr(pipeline_manager, '_ui_actions') and pipeline_manager._ui_actions:
                    ui_actions.extend(pipeline_manager._ui_actions.copy())
                    print(f"🔍 DEBUG: Found {len(pipeline_manager._ui_actions)} UI actions from pipeline_manager")
                    pipeline_manager._ui_actions.clear()  # Clear after extracting
                
                # Check haystack_pipeline_manager (this is where the tools run)
                if hasattr(haystack_pipeline_manager, '_ui_actions') and haystack_pipeline_manager._ui_actions:
                    ui_actions.extend(haystack_pipeline_manager._ui_actions.copy())
                    print(f"🔍 DEBUG: Found {len(haystack_pipeline_manager._ui_actions)} UI actions from haystack_pipeline_manager")
                    haystack_pipeline_manager._ui_actions.clear()  # Clear after extracting
                    
                if not ui_actions:
                    print(f"🔍 DEBUG: No UI actions found in either pipeline manager")
                
                # Send any UI actions as separate messages
                for ui_action in ui_actions:
                    print(f"🚀 SENDING UI ACTION VIA WEBSOCKET: {ui_action}")
                    await manager.send_to_session(session_id, {
                        "type": "ui_action",
                        "action": ui_action,
                        "pipeline": "haystack"
                    })
                
                # Send completion indicator
                await manager.send_to_session(session_id, {
                    "type": "message_complete",
                    "full_content": full_response,
                    "typing": False
                })
            
            elif message_data.get("type") == "ui_state_update":
                # Handle UI state updates from frontend
                ui_state = message_data.get("state", {})
                auth_token = message_data.get("auth_token")
                
                print(f"🔍 DEBUG: Received UI state update: {ui_state}")
                
                # Store UI state globally for AI tools to access
                from ui_state_manager import ui_state_manager
                ui_state_manager.update_state(session_id, ui_state, auth_token)
                
                print(f"🔍 DEBUG: UI state stored for session {session_id}")
                
            elif message_data.get("type") == "heartbeat":
                # Handle heartbeat messages from frontend to keep session alive
                timestamp = message_data.get("timestamp", "unknown")
                print(f"💗 DEBUG: Received heartbeat from session {session_id} at {timestamp}")
                
                # Update session activity to prevent timeout
                await session_manager.update_session_activity(session_id)
                
                # Send heartbeat acknowledgment
                await websocket.send_text(json.dumps({
                    "type": "heartbeat_ack",
                    "timestamp": timestamp,
                    "server_time": datetime.now().isoformat()
                }))
                
            elif message_data.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                
    except WebSocketDisconnect:
        manager.disconnect(connection_id, session_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(connection_id, session_id)

# Additional utility endpoints
@app.get("/personas")
async def get_personas():
    """Get available personas"""
    return {
        "personas": [
            {
                "type": persona_type.value,
                "config": persona_manager.get_persona(persona_type).dict()
            }
            for persona_type in PersonaType
        ]
    }

@app.get("/stats")
async def get_service_stats():
    """Get service statistics"""
    return {
        "active_sessions": await session_manager.get_active_sessions_count(),
        "active_websocket_connections": len(manager.active_connections),
        "pipeline_status": await pipeline_manager.health_check(),
        "haystack_pipeline_status": await haystack_pipeline_manager.health_check()
    }

# New Haystack Pipeline endpoints
class HaystackChatRequest(BaseModel):
    message: str
    persona_type: PersonaType
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    pipeline_type: str = "multi_tool"  # basic, multi_tool, evaluator_optimizer

@app.post("/chat/haystack", response_model=ChatResponse)
async def chat_with_haystack_pipeline(
    request: HaystackChatRequest,
    authorization: Optional[str] = Header(None)
):
    """Chat using Haystack Pipeline with advanced tool chaining"""
    try:
        # Extract auth token
        auth_token = None
        if authorization and authorization.startswith("Bearer "):
            auth_token = authorization[7:]
        
        # Create session if not provided
        session_id = request.session_id
        if not session_id:
            session_id = await session_manager.create_session(
                persona_type=request.persona_type,
                context=request.context or {}
            )
        
        # Generate response using Haystack pipeline
        response_parts = []
        async for chunk in haystack_pipeline_manager.generate_response_with_chaining(
            session_id=session_id,
            persona_type=request.persona_type,
            user_message=request.message,
            context=request.context,
            auth_token=auth_token,
            pipeline_type=request.pipeline_type
        ):
            response_parts.append(chunk)
        
        full_response = "".join(response_parts)
        
        return ChatResponse(
            response=full_response,
            session_id=session_id,
            message_id=f"msg_{datetime.now().isoformat()}",
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error in Haystack chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/haystack/{session_id}")
async def websocket_haystack_endpoint(
    websocket: WebSocket, 
    session_id: str,
    token: Optional[str] = None
):
    """WebSocket endpoint for Haystack Pipeline with tool chaining"""
    await websocket.accept()
    connection_id = f"haystack_{session_id}_{datetime.now().timestamp()}"
    manager.connect(websocket, connection_id, session_id)
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data.get("type") == "chat":
                user_message = message_data.get("message", "")
                persona_type = PersonaType(message_data.get("persona_type", "WEB_ASSISTANT"))
                context = message_data.get("context", {})
                pipeline_type = message_data.get("pipeline_type", "multi_tool")
                auth_token = message_data.get("auth_token") or token
                
                # Send typing indicator
                await manager.send_to_session(session_id, {
                    "type": "typing",
                    "typing": True,
                    "pipeline": "haystack"
                })
                
                # Generate streaming response with Haystack
                full_response = ""
                ui_actions = []
                
                print(f"🔍 DEBUG: Starting streaming response generation...")
                try:
                    async for chunk in haystack_pipeline_manager.generate_response_with_chaining(
                        session_id=session_id,
                        persona_type=persona_type,
                        user_message=user_message,
                        context=context,
                        auth_token=auth_token,
                        pipeline_type=pipeline_type
                    ):
                        full_response += chunk
                        
                        # Send chunk to all connections for this session
                        await manager.send_to_session(session_id, {
                            "type": "message_chunk",
                            "content": chunk,
                            "full_content": full_response,
                            "pipeline": "haystack"
                        })
                    
                    print(f"🔍 DEBUG: Streaming completed, now checking for UI actions...")
                except Exception as e:
                    print(f"🔍 DEBUG: Exception during streaming: {e}")
                    raise
                
                # Check for UI actions from the pipeline manager
                # Access the pipeline manager instance that was used
                from pipeline_manager import pipeline_manager
                print(f"🔍 DEBUG: Checking for UI actions...")
                print(f"🔍 DEBUG: pipeline_manager has _ui_actions: {hasattr(pipeline_manager, '_ui_actions')}")
                
                ui_actions = []
                if hasattr(pipeline_manager, '_ui_actions'):
                    ui_actions = pipeline_manager._ui_actions.copy()
                    print(f"🔍 DEBUG: Found {len(ui_actions)} UI actions: {ui_actions}")
                    pipeline_manager._ui_actions.clear()  # Clear after extracting
                else:
                    print(f"🔍 DEBUG: No _ui_actions attribute found on pipeline_manager")
                
                # Send any UI actions as separate messages
                for ui_action in ui_actions:
                    print(f"🚀 SENDING UI ACTION VIA WEBSOCKET: {ui_action}")
                    await manager.send_to_session(session_id, {
                        "type": "ui_action",
                        "action": ui_action,
                        "pipeline": "haystack"
                    })
                
                # Send completion indicator
                await manager.send_to_session(session_id, {
                    "type": "message_complete",
                    "full_content": full_response,
                    "typing": False,
                    "pipeline": "haystack"
                })
            
            elif message_data.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "pipeline": "haystack"}))
                
    except WebSocketDisconnect:
        manager.disconnect(connection_id, session_id)
    except Exception as e:
        logger.error(f"Haystack WebSocket error: {e}")
        manager.disconnect(connection_id, session_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level=settings.log_level.lower()
    )