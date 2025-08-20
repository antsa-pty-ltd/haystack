"""
UI State Manager for storing and accessing frontend UI state in the backend.
This allows AI tools to access information about loaded sessions, selected clients, etc.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class UIStateManager:
    """Manages UI state from frontend for AI tool access"""
    
    def __init__(self):
        # Store UI state per session ID
        self._ui_states: Dict[str, Dict[str, Any]] = {}
        # Store auth tokens per session for tool authentication
        self._auth_tokens: Dict[str, str] = {}
    
    def update_state(self, session_id: str, ui_state: Dict[str, Any], auth_token: Optional[str] = None):
        """Update UI state for a session"""
        try:
            self._ui_states[session_id] = {
                **ui_state,
                "last_updated": datetime.now().isoformat(),
                "session_id": session_id
            }
            
            if auth_token:
                self._auth_tokens[session_id] = auth_token
            
            logger.info(f"📂 UI state updated for session {session_id}: {len(ui_state.get('loadedSessions', []))} sessions loaded")
            
        except Exception as e:
            logger.error(f"Error updating UI state for session {session_id}: {e}")
    
    def get_state(self, session_id: str) -> Dict[str, Any]:
        """Get UI state for a session"""
        return self._ui_states.get(session_id, {})
    
    def get_loaded_sessions(self, session_id: str) -> List[Dict[str, Any]]:
        """Get loaded sessions for a session"""
        ui_state = self.get_state(session_id)
        return ui_state.get("loadedSessions", [])
    
    def get_current_client(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get currently selected client for a session"""
        ui_state = self.get_state(session_id)
        return ui_state.get("currentClient")
    
    def get_active_tab(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get currently active tab for a session"""
        ui_state = self.get_state(session_id)
        return ui_state.get("activeTab")
    
    def get_selected_template(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get currently selected template for a session"""
        ui_state = self.get_state(session_id)
        return ui_state.get("selectedTemplate")
    
    def get_generated_documents(self, session_id: str) -> List[Dict[str, Any]]:
        """Get generated documents for a session"""
        ui_state = self.get_state(session_id)
        return ui_state.get("generatedDocuments", [])
    
    def get_session_count(self, session_id: str) -> int:
        """Get number of loaded sessions for a session"""
        ui_state = self.get_state(session_id)
        return ui_state.get("sessionCount", 0)
    
    def get_auth_token(self, session_id: str) -> Optional[str]:
        """Get auth token for a session"""
        return self._auth_tokens.get(session_id)
    
    def get_session_content(self, session_id: str, target_session_id: str) -> Optional[str]:
        """Get content of a specific loaded session"""
        loaded_sessions = self.get_loaded_sessions(session_id)
        for session in loaded_sessions:
            if session.get("sessionId") == target_session_id:
                return session.get("content", "")
        return None
    
    def find_sessions_by_client(self, session_id: str, client_name: str) -> List[Dict[str, Any]]:
        """Find loaded sessions by client name"""
        loaded_sessions = self.get_loaded_sessions(session_id)
        matching_sessions = []
        for session in loaded_sessions:
            if session.get("clientName", "").lower() == client_name.lower():
                matching_sessions.append(session)
        return matching_sessions
    
    def cleanup_session(self, session_id: str):
        """Clean up UI state for a disconnected session"""
        if session_id in self._ui_states:
            del self._ui_states[session_id]
        if session_id in self._auth_tokens:
            del self._auth_tokens[session_id]
        logger.info(f"🧹 Cleaned up UI state for session {session_id}")
    
    def get_all_sessions_summary(self) -> Dict[str, Any]:
        """Get summary of all active sessions (for debugging)"""
        summary = {}
        for session_id, ui_state in self._ui_states.items():
            # Safely get current_client name
            current_client = ui_state.get("currentClient")
            current_client_name = "None"
            if current_client and isinstance(current_client, dict):
                current_client_name = current_client.get("clientName", "None")
            
            # Safely get active tab ID
            active_tab = ui_state.get("activeTab")
            active_tab_id = "None"
            if active_tab and isinstance(active_tab, dict):
                active_tab_id = active_tab.get("activeTabId", "None")
            
            # Safely get selected template name
            selected_template = ui_state.get("selectedTemplate")
            selected_template_name = "None"
            if selected_template and isinstance(selected_template, dict) and selected_template.get("templateId"):
                selected_template_name = selected_template.get("templateName", "None")
            
            # Safely get generated documents count
            generated_documents = ui_state.get("generatedDocuments", [])
            document_count = len(generated_documents) if isinstance(generated_documents, list) else 0
            
            summary[session_id] = {
                "session_count": ui_state.get("sessionCount", 0),
                "document_count": document_count,
                "current_client": current_client_name,
                "active_tab": active_tab_id,
                "selected_template": selected_template_name,
                "last_updated": ui_state.get("last_updated", "Unknown")
            }
        return summary

# Global instance
ui_state_manager = UIStateManager()