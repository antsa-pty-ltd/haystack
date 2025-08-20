import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import redis.asyncio as redis
from config import settings

@dataclass
class ChatMessage:
    role: str  # 'user' | 'assistant' | 'system'
    content: str
    timestamp: datetime
    message_id: str = None
    
    def __post_init__(self):
        if self.message_id is None:
            self.message_id = str(uuid.uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'message_id': self.message_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatMessage':
        return cls(
            role=data['role'],
            content=data['content'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            message_id=data.get('message_id')
        )

@dataclass
class ChatSession:
    session_id: str
    persona_type: str
    messages: List[ChatMessage]
    created_at: datetime
    last_activity: datetime
    context: Dict[str, Any]
    auth_token: Optional[str] = None  # Store JWT token with session
    profile_id: Optional[str] = None  # Store profile ID with session
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'session_id': self.session_id,
            'persona_type': self.persona_type,
            'messages': [msg.to_dict() for msg in self.messages],
            'created_at': self.created_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'context': self.context,
            'auth_token': self.auth_token,
            'profile_id': self.profile_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatSession':
        return cls(
            session_id=data['session_id'],
            persona_type=data['persona_type'],
            messages=[ChatMessage.from_dict(msg) for msg in data['messages']],
            created_at=datetime.fromisoformat(data['created_at']),
            last_activity=datetime.fromisoformat(data['last_activity']),
            context=data.get('context', {}),
            auth_token=data.get('auth_token'),
            profile_id=data.get('profile_id')
        )

class SessionManager:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.local_sessions: Dict[str, ChatSession] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def initialize(self):
        """Initialize Redis connection and start cleanup task"""
        try:
            self.redis_client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            await self.redis_client.ping()
            print("✅ Connected to Redis for session management")
        except Exception as e:
            print(f"⚠️ Redis connection failed, using in-memory sessions: {e}")
            self.redis_client = None
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
    
    async def close(self):
        """Close Redis connection and cleanup task"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        if self.redis_client:
            await self.redis_client.close()
    
    async def create_session(
        self, 
        persona_type: str, 
        context: Optional[Dict[str, Any]] = None,
        auth_token: Optional[str] = None,
        profile_id: Optional[str] = None
    ) -> str:
        """Create a new chat session"""
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        session = ChatSession(
            session_id=session_id,
            persona_type=persona_type,
            messages=[],
            created_at=now,
            last_activity=now,
            context=context or {},
            auth_token=auth_token,
            profile_id=profile_id
        )
        
        await self._save_session(session)
        return session_id
    
    async def update_session_auth_token(self, session_id: str, auth_token: str) -> bool:
        """Update the auth token for a session"""
        session = await self.get_session(session_id)
        if not session:
            return False
        
        session.auth_token = auth_token
        session.last_activity = datetime.utcnow()
        await self._save_session(session)
        return True
    
    async def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Get a chat session by ID"""
        # Try Redis first
        if self.redis_client:
            try:
                session_data = await self.redis_client.get(f"session:{session_id}")
                if session_data:
                    return ChatSession.from_dict(json.loads(session_data))
            except Exception as e:
                print(f"Error getting session from Redis: {e}")
        
        # Fallback to local storage
        return self.local_sessions.get(session_id)
    
    async def add_message(
        self, 
        session_id: str, 
        role: str, 
        content: str
    ) -> Optional[ChatMessage]:
        """Add a message to a session"""
        session = await self.get_session(session_id)
        if not session:
            return None
        
        message = ChatMessage(
            role=role,
            content=content,
            timestamp=datetime.utcnow()
        )
        
        session.messages.append(message)
        session.last_activity = datetime.utcnow()
        
        await self._save_session(session)
        return message
    
    async def get_messages(
        self, 
        session_id: str, 
        limit: Optional[int] = None
    ) -> List[ChatMessage]:
        """Get messages from a session"""
        session = await self.get_session(session_id)
        if not session:
            return []
        
        messages = session.messages
        if limit:
            messages = messages[-limit:]
        
        return messages
    
    async def update_session_context(
        self, 
        session_id: str, 
        context: Dict[str, Any]
    ) -> bool:
        """Update session context"""
        session = await self.get_session(session_id)
        if not session:
            return False
        
        session.context.update(context)
        session.last_activity = datetime.utcnow()
        
        await self._save_session(session)
        return True
    
    async def update_session_activity(self, session_id: str) -> bool:
        """Update session activity timestamp to prevent timeout"""
        session = await self.get_session(session_id)
        if not session:
            return False
        
        session.last_activity = datetime.utcnow()
        await self._save_session(session)
        return True
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        # Remove from Redis
        if self.redis_client:
            try:
                await self.redis_client.delete(f"session:{session_id}")
            except Exception as e:
                print(f"Error deleting session from Redis: {e}")
        
        # Remove from local storage
        if session_id in self.local_sessions:
            del self.local_sessions[session_id]
            return True
        
        return False
    
    async def get_active_sessions_count(self) -> int:
        """Get count of active sessions"""
        if self.redis_client:
            try:
                keys = await self.redis_client.keys("session:*")
                return len(keys)
            except Exception as e:
                print(f"Error counting Redis sessions: {e}")
        
        return len(self.local_sessions)
    
    async def _save_session(self, session: ChatSession):
        """Save session to storage"""
        # Save to Redis with TTL
        if self.redis_client:
            try:
                session_data = json.dumps(session.to_dict())
                ttl_seconds = settings.session_timeout_minutes * 60
                await self.redis_client.setex(
                    f"session:{session.session_id}",
                    ttl_seconds,
                    session_data
                )
            except Exception as e:
                print(f"Error saving session to Redis: {e}")
        
        # Also save to local storage as backup
        self.local_sessions[session.session_id] = session
    
    async def _periodic_cleanup(self):
        """Periodically cleanup expired local sessions"""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in periodic cleanup: {e}")
    
    async def _cleanup_expired_sessions(self):
        """Remove expired sessions from local storage"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=settings.session_timeout_minutes)
        expired_sessions = [
            session_id for session_id, session in self.local_sessions.items()
            if session.last_activity < cutoff_time
        ]
        
        for session_id in expired_sessions:
            del self.local_sessions[session_id]
        
        if expired_sessions:
            print(f"Cleaned up {len(expired_sessions)} expired sessions")

# Global session manager instance
session_manager = SessionManager()