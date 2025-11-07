"""
Session management testing utilities

Provides helpers for creating and managing test sessions.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime


class SessionFactory:
    """
    Factory for creating test sessions with automatic cleanup

    Usage:
        factory = SessionFactory()
        session_id1 = await factory.create_session(persona_type="web_assistant")
        session_id2 = await factory.create_session(persona_type="jaimee_therapist")

        # Automatic cleanup at end of test
        await factory.cleanup()

    Or use as async context manager:
        async with SessionFactory() as factory:
            session_id = await factory.create_session()
            # ... test code ...
        # Automatic cleanup
    """

    def __init__(self):
        """Initialize session factory"""
        self.sessions: List[str] = []
        self.session_manager = None

    async def __aenter__(self):
        """Async context manager entry"""
        # Lazy import to avoid circular dependencies
        from session_manager import session_manager
        self.session_manager = session_manager
        await self.session_manager.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup"""
        await self.cleanup()

    async def create_session(
        self,
        persona_type: str = "web_assistant",
        context: Optional[Dict[str, Any]] = None,
        auth_token: Optional[str] = None,
        profile_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> str:
        """
        Create a test session with automatic cleanup tracking

        Args:
            persona_type: Type of persona
            context: Session context
            auth_token: Authentication token
            profile_id: Profile ID
            session_id: Specific session ID (optional)

        Returns:
            Created session ID
        """
        if self.session_manager is None:
            from session_manager import session_manager
            self.session_manager = session_manager

        created_session_id = await self.session_manager.create_session(
            persona_type=persona_type,
            context=context or {},
            auth_token=auth_token,
            profile_id=profile_id,
            session_id=session_id
        )

        self.sessions.append(created_session_id)
        return created_session_id

    async def cleanup(self):
        """Clean up all created sessions"""
        if self.session_manager is None:
            from session_manager import session_manager
            self.session_manager = session_manager

        for session_id in self.sessions:
            try:
                await self.session_manager.delete_session(session_id)
            except Exception:
                # Session may already be deleted or not exist
                pass

        self.sessions.clear()

    def get_session_count(self) -> int:
        """Get number of tracked sessions"""
        return len(self.sessions)


def create_test_session_data(
    session_id: str = "test-session-123",
    persona_type: str = "web_assistant",
    messages: Optional[List[Dict[str, Any]]] = None,
    auth_token: Optional[str] = None,
    profile_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create test session data structure

    Args:
        session_id: Session ID
        persona_type: Persona type
        messages: List of messages
        auth_token: Auth token
        profile_id: Profile ID

    Returns:
        Session data dictionary
    """
    return {
        "session_id": session_id,
        "persona_type": persona_type,
        "messages": messages or [],
        "context": {},
        "created_at": datetime.utcnow().isoformat(),
        "last_activity": datetime.utcnow().isoformat(),
        "auth_token": auth_token,
        "profile_id": profile_id
    }


def create_test_message(
    role: str = "user",
    content: str = "Test message",
    timestamp: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Create a test message structure

    Args:
        role: Message role (user, assistant, system, tool)
        content: Message content
        timestamp: Message timestamp

    Returns:
        Message dictionary
    """
    return {
        "role": role,
        "content": content,
        "timestamp": (timestamp or datetime.utcnow()).isoformat()
    }


async def create_session_with_history(
    session_factory: SessionFactory,
    message_count: int = 5,
    persona_type: str = "web_assistant"
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Create a session with message history

    Args:
        session_factory: Session factory instance
        message_count: Number of messages to add
        persona_type: Persona type

    Returns:
        Tuple of (session_id, messages)
    """
    session_id = await session_factory.create_session(persona_type=persona_type)

    # Add messages to session
    messages = []
    for i in range(message_count):
        role = "user" if i % 2 == 0 else "assistant"
        message = create_test_message(
            role=role,
            content=f"Test message {i + 1}"
        )
        messages.append(message)

    return session_id, messages
