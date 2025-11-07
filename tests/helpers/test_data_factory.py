"""
Test Data Factory

Provides factory methods for creating test data with sensible defaults.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional


class TestDataFactory:
    """Factory for creating test data"""

    @staticmethod
    def create_template(
        id: str = "test_template_1",
        name: str = "Test Template",
        content: str = "Test template content"
    ) -> Dict[str, Any]:
        """
        Create a template object.

        Args:
            id: Template ID
            name: Template name
            content: Template content

        Returns:
            Template dict
        """
        return {
            "id": id,
            "name": name,
            "content": content
        }

    @staticmethod
    def create_violating_template(
        id: str = "violating_template_1",
        name: str = "Diagnostic Assessment Template"
    ) -> Dict[str, Any]:
        """
        Create a template that violates policy (requests DSM-5 diagnosis).

        Args:
            id: Template ID
            name: Template name

        Returns:
            Violating template dict
        """
        return TestDataFactory.create_template(
            id=id,
            name=name,
            content="Provide a comprehensive DSM-5 diagnosis based on the client's symptoms and behaviors."
        )

    @staticmethod
    def create_safe_template(
        id: str = "safe_template_1",
        name: str = "Progress Note Template"
    ) -> Dict[str, Any]:
        """
        Create a safe template (no policy violations).

        Args:
            id: Template ID
            name: Template name

        Returns:
            Safe template dict
        """
        return TestDataFactory.create_template(
            id=id,
            name=name,
            content="Document the session progress, interventions used, and client's response to treatment."
        )

    @staticmethod
    def create_transcript(
        speaker_count: int = 2,
        segment_count: int = 5,
        speakers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a realistic transcript.

        Args:
            speaker_count: Number of different speakers
            segment_count: Number of segments
            speakers: Optional list of speaker names

        Returns:
            Transcript dict with segments
        """
        if speakers is None:
            speakers = ["Practitioner", "Client"]

        segments = []
        for i in range(segment_count):
            segments.append({
                "speaker": speakers[i % len(speakers)],
                "text": f"This is segment {i + 1} of the conversation.",
                "startTime": i * 30
            })

        return {"segments": segments}

    @staticmethod
    def create_large_transcript(segment_count: int = 100) -> Dict[str, Any]:
        """
        Create a large transcript for testing payload limits.

        Args:
            segment_count: Number of segments (default 100)

        Returns:
            Large transcript dict
        """
        segments = []
        for i in range(segment_count):
            # Each segment ~200 words
            text = f"Segment {i}. " + "This is a longer piece of text for testing large payloads. " * 25
            segments.append({
                "speaker": "Practitioner" if i % 2 == 0 else "Client",
                "text": text,
                "startTime": i * 60
            })

        return {"segments": segments}

    @staticmethod
    def create_client_info(
        id: str = "client_123",
        name: str = "John Doe",
        email: str = "john.doe@example.com",
        age: int = 35,
        gender: str = "Male"
    ) -> Dict[str, Any]:
        """
        Create client info object.

        Args:
            id: Client ID
            name: Client name
            email: Client email
            age: Client age
            gender: Client gender

        Returns:
            Client info dict
        """
        return {
            "id": id,
            "name": name,
            "email": email,
            "age": age,
            "gender": gender
        }

    @staticmethod
    def create_practitioner_info(
        id: str = "prac_123",
        name: str = "Dr. Jane Smith",
        credentials: str = "PhD, LCSW",
        email: str = "jane.smith@clinic.com"
    ) -> Dict[str, Any]:
        """
        Create practitioner info object.

        Args:
            id: Practitioner ID
            name: Practitioner name
            credentials: Professional credentials
            email: Practitioner email

        Returns:
            Practitioner info dict
        """
        return {
            "id": id,
            "name": name,
            "credentials": credentials,
            "email": email
        }

    @staticmethod
    def create_document_request(
        template: Optional[Dict[str, Any]] = None,
        transcript: Optional[Dict[str, Any]] = None,
        client_info: Optional[Dict[str, Any]] = None,
        practitioner_info: Optional[Dict[str, Any]] = None,
        generation_instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a complete document generation request.

        Args:
            template: Template dict (uses default if None)
            transcript: Transcript dict (uses default if None)
            client_info: Client info dict (uses default if None)
            practitioner_info: Practitioner info dict (uses default if None)
            generation_instructions: Optional generation instructions

        Returns:
            Complete document request dict
        """
        return {
            "template": template or TestDataFactory.create_safe_template(),
            "transcript": transcript or TestDataFactory.create_transcript(),
            "clientInfo": client_info or TestDataFactory.create_client_info(),
            "practitionerInfo": practitioner_info or TestDataFactory.create_practitioner_info(),
            "generationInstructions": generation_instructions
        }

    @staticmethod
    def create_websocket_message(
        message_type: str = "chat_message",
        message: Optional[str] = None,
        auth_token: str = "test_token_123",
        profile_id: str = "profile_123",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a WebSocket message.

        Args:
            message_type: Type of message (chat_message, ui_state_update, heartbeat)
            message: Message content (for chat_message type)
            auth_token: JWT auth token
            profile_id: Profile ID
            **kwargs: Additional message fields

        Returns:
            WebSocket message dict
        """
        base_message = {
            "type": message_type,
            "auth_token": auth_token,
            "profile_id": profile_id
        }

        if message_type == "chat_message":
            base_message["message"] = message or "Test message"

        base_message.update(kwargs)
        return base_message

    @staticmethod
    def create_ui_state(
        session_id: str = "session_123",
        page_type: str = "transcribe_page",
        page_url: str = "/transcribe",
        loaded_sessions: Optional[List[Dict]] = None,
        current_client: Optional[Dict] = None,
        selected_template: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create a UI state object.

        Args:
            session_id: Session ID
            page_type: Page type identifier
            page_url: Current page URL
            loaded_sessions: List of loaded sessions
            current_client: Currently selected client
            selected_template: Currently selected template

        Returns:
            UI state dict
        """
        return {
            "session_id": session_id,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "page_type": page_type,
            "page_url": page_url,
            "loadedSessions": loaded_sessions or [],
            "currentClient": current_client,
            "selectedTemplate": selected_template,
            "generatedDocuments": [],
            "sessionCount": len(loaded_sessions) if loaded_sessions else 0,
            "documentCount": 0
        }

    @staticmethod
    def create_unicode_test_data() -> Dict[str, List[str]]:
        """
        Create test data with various Unicode characters.

        Returns:
            Dict with different Unicode test cases
        """
        return {
            "names": [
                "José García",
                "李明",
                "Müller Schmidt",
                "O'Brien",
                "Françoise Dubois",
                "Владимир Петров",
                "محمد علي",
                "Σωκράτης",
                "Test 💡 Emoji",
                "Test\nNewline"
            ],
            "special_chars": [
                "Test with 'quotes'",
                'Test with "double quotes"',
                "Test with <brackets>",
                "Test with {braces}",
                "Test with [square]",
                "Test & ampersand",
                "Test @ symbol",
                "Test # hashtag"
            ],
            "edge_cases": [
                "",  # Empty string
                " ",  # Single space
                "   ",  # Multiple spaces
                "\t",  # Tab
                "\n",  # Newline
                "A" * 1000,  # Very long string
                "🔥" * 100  # Many emojis
            ]
        }

    @staticmethod
    def create_headers(
        auth_token: str = "test_token_123",
        profile_id: str = "profile_123",
        user_agent: str = "TestClient/1.0",
        **kwargs
    ) -> Dict[str, str]:
        """
        Create HTTP headers for requests.

        Args:
            auth_token: JWT auth token
            profile_id: Profile ID
            user_agent: User agent string
            **kwargs: Additional headers

        Returns:
            Headers dict
        """
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "ProfileID": profile_id,
            "User-Agent": user_agent
        }
        headers.update(kwargs)
        return headers

    @staticmethod
    def create_session_data(
        session_id: str = "session_123",
        persona_type: str = "web_assistant",
        context: Optional[Dict] = None,
        auth_token: str = "test_token_123",
        profile_id: str = "profile_123"
    ) -> Dict[str, Any]:
        """
        Create session data for session manager.

        Args:
            session_id: Session ID
            persona_type: Persona type
            context: Session context
            auth_token: JWT token
            profile_id: Profile ID

        Returns:
            Session data dict
        """
        return {
            "session_id": session_id,
            "persona_type": persona_type,
            "context": context or {},
            "auth_token": auth_token,
            "profile_id": profile_id
        }
