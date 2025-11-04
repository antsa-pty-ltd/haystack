"""
UI State Manager for storing and accessing frontend UI state in Redis.
This allows AI tools to access information about loaded sessions, selected clients, etc.
"""
import logging
import json
import os
from typing import Dict, List, Optional, TypedDict, Union, cast
from datetime import datetime

try:
    import redis.asyncio as redis_async
    import redis as redis_sync  # Sync client for tool execution in threads
except ImportError:
    import redis as redis_async  # type: ignore
    redis_sync = redis_async  # type: ignore

logger = logging.getLogger(__name__)

# Type definitions for UI state structure
class LoadedSessionData(TypedDict, total=False):
    sessionId: str
    clientId: str
    clientName: str
    content: str
    metadata: Dict[str, Union[str, int, float]]

class CurrentClientData(TypedDict, total=False):
    clientId: str
    clientName: str

class TemplateData(TypedDict, total=False):
    templateId: str
    templateName: str
    templateContent: str
    templateDescription: str

class DocumentData(TypedDict, total=False):
    documentId: str
    documentName: str
    documentContent: str

class UIState(TypedDict, total=False):
    session_id: str
    last_updated: str
    page_type: str
    page_url: str
    loadedSessions: List[LoadedSessionData]
    currentClient: Optional[CurrentClientData]
    selectedTemplate: Optional[TemplateData]
    generatedDocuments: List[DocumentData]
    sessionCount: int
    documentCount: int
    client_id: Optional[str]
    active_tab: Optional[str]

class UIStateManager:
    """Redis-backed UI state manager with strict typing"""
    
    STATE_TTL = 86400  # 24 hours in seconds
    
    def __init__(self) -> None:
        self.redis_client: Optional[redis_async.Redis] = None  # Async client for FastAPI
        self.redis_client_sync: Optional[redis_sync.Redis] = None  # Sync client for tool execution
        self._initialized: bool = False
        self._in_memory_fallback: Dict[str, str] = {}  # Fallback storage if Redis fails
        self._in_memory_tokens: Dict[str, str] = {}
    
    async def initialize(self) -> None:
        """Initialize Redis connection (async for FastAPI)"""
        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            # Initialize async client
            self.redis_client = await redis_async.from_url(redis_url, decode_responses=True)
            await self.redis_client.ping()
            # Initialize sync client for tool execution
            self.redis_client_sync = redis_sync.from_url(redis_url, decode_responses=True)
            self.redis_client_sync.ping()
            self._initialized = True
            logger.info(f"✅ UIStateManager initialized with Redis at {redis_url} (async + sync clients)")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Redis: {e}")
            logger.warning("⚠️  Falling back to in-memory state storage")
            self._initialized = False
    
    def _state_key(self, session_id: str) -> str:
        """Generate Redis key for UI state"""
        return f"ui_state:{session_id}"
    
    def _token_key(self, session_id: str) -> str:
        """Generate Redis key for auth token"""
        return f"auth_token:{session_id}"
    
    async def update_incremental(
        self, 
        session_id: str, 
        changes: Dict[str, Union[str, int, List[LoadedSessionData], CurrentClientData, TemplateData, None]], 
        timestamp: str
    ) -> bool:
        """Apply incremental state changes with timestamp ordering"""
        try:
            if self._initialized and self.redis_client is not None:
                # Redis path
                key = self._state_key(session_id)
                
                # Get current state
                current_json = await self.redis_client.get(key)
                current: UIState = json.loads(current_json) if current_json else {}
                
                # Check timestamp ordering
                last_updated = current.get("last_updated", "1970-01-01T00:00:00Z")
                if timestamp < last_updated:
                    logger.warning(f"⏭️  Ignoring stale update for {session_id}: {timestamp} < {last_updated}")
                    return False
                
                # Merge changes (type-safe update)
                for key_name, value in changes.items():
                    current[key_name] = value  # type: ignore
                
                current["last_updated"] = timestamp
                current["session_id"] = session_id
                
                # Store with TTL
                await self.redis_client.setex(key, self.STATE_TTL, json.dumps(current))
                logger.info(f"✅ Updated UI state for {session_id} (Redis)")
                return True
            else:
                # In-memory fallback
                key = self._state_key(session_id)
                current_json = self._in_memory_fallback.get(key, "{}")
                current: UIState = json.loads(current_json)
                
                last_updated = current.get("last_updated", "1970-01-01T00:00:00Z")
                if timestamp < last_updated:
                    logger.warning(f"⏭️  Ignoring stale update for {session_id}: {timestamp} < {last_updated}")
                    return False
                
                for key_name, value in changes.items():
                    current[key_name] = value  # type: ignore
                
                current["last_updated"] = timestamp
                current["session_id"] = session_id
                
                self._in_memory_fallback[key] = json.dumps(current)
                logger.info(f"✅ Updated UI state for {session_id} (in-memory fallback)")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error updating incremental state for {session_id}: {e}")
            return False
    
    async def update_state(
        self, 
        session_id: str, 
        ui_state: UIState, 
        auth_token: Optional[str] = None
    ) -> bool:
        """Full state update (replaces existing)"""
        try:
            ui_state["last_updated"] = datetime.utcnow().isoformat()
            ui_state["session_id"] = session_id
            
            if self._initialized and self.redis_client is not None:
                # Redis path
                key = self._state_key(session_id)
                await self.redis_client.setex(key, self.STATE_TTL, json.dumps(ui_state))
                
                if auth_token:
                    token_key = self._token_key(session_id)
                    await self.redis_client.setex(token_key, self.STATE_TTL, auth_token)
                
                logger.info(f"✅ Full state update for {session_id} (Redis)")
                return True
            else:
                # In-memory fallback
                key = self._state_key(session_id)
                self._in_memory_fallback[key] = json.dumps(ui_state)
                
                if auth_token:
                    token_key = self._token_key(session_id)
                    self._in_memory_tokens[token_key] = auth_token
                
                logger.info(f"✅ Full state update for {session_id} (in-memory fallback)")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error updating full state for {session_id}: {e}")
            return False
    
    async def get_state(self, session_id: str) -> UIState:
        """Get UI state for session"""
        try:
            if self._initialized and self.redis_client is not None:
                # Redis path
                key = self._state_key(session_id)
                state_json = await self.redis_client.get(key)
                if state_json:
                    return cast(UIState, json.loads(state_json))
                return {}
            else:
                # In-memory fallback
                key = self._state_key(session_id)
                state_json = self._in_memory_fallback.get(key)
                if state_json:
                    return cast(UIState, json.loads(state_json))
                return {}
                
        except Exception as e:
            logger.error(f"❌ Error getting state for {session_id}: {e}")
            return {}
    
    async def get_loaded_sessions(self, session_id: str) -> List[LoadedSessionData]:
        """Get loaded sessions for a session"""
        ui_state = await self.get_state(session_id)
        return ui_state.get("loadedSessions", [])
    
    async def get_current_client(self, session_id: str) -> Optional[CurrentClientData]:
        """Get currently selected client for a session"""
        ui_state = await self.get_state(session_id)
        return ui_state.get("currentClient")
    
    async def get_selected_template(self, session_id: str) -> Optional[TemplateData]:
        """Get currently selected template for a session"""
        ui_state = await self.get_state(session_id)
        return ui_state.get("selectedTemplate")
    
    async def get_generated_documents(self, session_id: str) -> List[DocumentData]:
        """Get generated documents for a session"""
        ui_state = await self.get_state(session_id)
        return ui_state.get("generatedDocuments", [])
    
    async def get_auth_token(self, session_id: str) -> Optional[str]:
        """Get auth token for session"""
        try:
            if self._initialized and self.redis_client is not None:
                # Redis path
                token_key = self._token_key(session_id)
                return await self.redis_client.get(token_key)
            else:
                # In-memory fallback
                token_key = self._token_key(session_id)
                return self._in_memory_tokens.get(token_key)
                
        except Exception as e:
            logger.error(f"❌ Error getting auth token for {session_id}: {e}")
            return None
    
    async def cleanup_session(self, session_id: str) -> None:
        """Clean up state for disconnected session"""
        try:
            if self._initialized and self.redis_client is not None:
                # Redis path
                await self.redis_client.delete(self._state_key(session_id))
                await self.redis_client.delete(self._token_key(session_id))
                logger.info(f"🧹 Cleaned up state for {session_id} (Redis)")
            else:
                # In-memory fallback
                self._in_memory_fallback.pop(self._state_key(session_id), None)
                self._in_memory_tokens.pop(self._token_key(session_id), None)
                logger.info(f"🧹 Cleaned up state for {session_id} (in-memory)")
                
        except Exception as e:
            logger.error(f"❌ Error cleaning up session {session_id}: {e}")
    
    async def get_page_capabilities(self, session_id: str) -> List[str]:
        """Get available tools for current page"""
        state = await self.get_state(session_id)
        page_type = state.get("page_type", "unknown")
        
        capability_map: Dict[str, List[str]] = {
            "transcribe_page": [
                "set_client_selection", "load_session_direct", "load_multiple_sessions",
                "set_selected_template", "select_template_by_name", "get_loaded_sessions",
                "get_session_content", "analyze_loaded_session", "generate_document_from_loaded"
            ],
            "client_details": [
                "get_client_summary", "get_client_homework_status", "load_session_direct"
            ],
            "sessions_list": [
                "load_session_direct", "load_multiple_sessions"
            ],
            "messages_page": [
                "search_clients", "get_conversations", "get_conversation_messages"
            ],
        }
        
        base_tools = ["search_clients", "get_clinic_stats", "suggest_navigation"]
        return base_tools + capability_map.get(page_type, [])
    
    async def get_all_sessions_summary(self) -> Dict[str, Dict[str, Union[str, int]]]:
        """Get summary of all active sessions (for debugging)"""
        summary: Dict[str, Dict[str, Union[str, int]]] = {}
        
        try:
            if self._initialized and self.redis_client is not None:
                # Redis path - scan for all ui_state:* keys
                keys = await self.redis_client.keys("ui_state:*")
                for key in keys:
                    if isinstance(key, str):
                        session_id = key.split(":", 1)[1]
                        state = await self.get_state(session_id)
                        summary[session_id] = {
                            "page_type": state.get("page_type", "unknown"),
                            "last_updated": state.get("last_updated", "unknown"),
                            "loaded_sessions": len(state.get("loadedSessions", []))
                        }
            else:
                # In-memory fallback
                for key, state_json in self._in_memory_fallback.items():
                    if key.startswith("ui_state:"):
                        session_id = key.split(":", 1)[1]
                        state = cast(UIState, json.loads(state_json))
                        summary[session_id] = {
                            "page_type": state.get("page_type", "unknown"),
                            "last_updated": state.get("last_updated", "unknown"),
                            "loaded_sessions": len(state.get("loadedSessions", []))
                        }
                        
        except Exception as e:
            logger.error(f"❌ Error getting sessions summary: {e}")
        
        return summary
    
    # ====================================================================================
    # SYNC METHODS - For tool execution in threads (avoids event loop conflicts)
    # ====================================================================================
    
    def get_all_sessions_summary_sync(self) -> Dict[str, Dict[str, Union[str, int]]]:
        """SYNC version: Get summary of all active sessions"""
        summary: Dict[str, Dict[str, Union[str, int]]] = {}
        
        try:
            if self._initialized and self.redis_client_sync is not None:
                # Use sync Redis client
                keys = self.redis_client_sync.keys("ui_state:*")
                for key in keys:
                    if isinstance(key, (str, bytes)):
                        session_id = (key.decode() if isinstance(key, bytes) else key).split(":", 1)[1]
                        state = self.get_state_sync(session_id)
                        summary[session_id] = {
                            "page_type": state.get("page_type", "unknown"),
                            "last_updated": state.get("last_updated", "unknown"),
                            "loaded_sessions": len(state.get("loadedSessions", []))
                        }
            else:
                # In-memory fallback
                for key, state_json in self._in_memory_fallback.items():
                    if key.startswith("ui_state:"):
                        session_id = key.split(":", 1)[1]
                        state = cast(UIState, json.loads(state_json))
                        summary[session_id] = {
                            "page_type": state.get("page_type", "unknown"),
                            "last_updated": state.get("last_updated", "unknown"),
                            "loaded_sessions": len(state.get("loadedSessions", []))
                        }
        except Exception as e:
            logger.error(f"❌ Error getting sessions summary (sync): {e}")
        
        return summary
    
    def get_state_sync(self, session_id: str) -> UIState:
        """SYNC version: Get UI state for session"""
        try:
            if self._initialized and self.redis_client_sync is not None:
                key = self._state_key(session_id)
                state_json = self.redis_client_sync.get(key)
                if state_json:
                    return cast(UIState, json.loads(state_json))
                return {}
            else:
                # In-memory fallback
                key = self._state_key(session_id)
                state_json = self._in_memory_fallback.get(key)
                if state_json:
                    return cast(UIState, json.loads(state_json))
                return {}
        except Exception as e:
            logger.error(f"❌ Error getting state (sync) for {session_id}: {e}")
            return {}
    
    def get_loaded_sessions_sync(self, session_id: str) -> List[LoadedSessionData]:
        """SYNC version: Get loaded sessions"""
        state = self.get_state_sync(session_id)
        return state.get("loadedSessions", [])
    
    def get_current_client_sync(self, session_id: str) -> Optional[CurrentClientData]:
        """SYNC version: Get current client"""
        state = self.get_state_sync(session_id)
        return state.get("currentClient")
    
    def get_selected_template_sync(self, session_id: str) -> Optional[TemplateData]:
        """SYNC version: Get selected template"""
        state = self.get_state_sync(session_id)
        return state.get("selectedTemplate")
    
    def get_generated_documents_sync(self, session_id: str) -> List[DocumentData]:
        """SYNC version: Get generated documents"""
        state = self.get_state_sync(session_id)
        return state.get("generatedDocuments", [])

# Global instance
ui_state_manager = UIStateManager()
