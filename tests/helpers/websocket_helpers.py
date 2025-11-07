"""
WebSocket testing utilities

Provides reusable mocks and helpers for testing WebSocket functionality.
"""
import json
from typing import List, Dict, Any, Optional
from unittest.mock import AsyncMock
from fastapi import WebSocket


class MockWebSocket:
    """
    Enhanced mock WebSocket that captures sent messages and simplifies testing

    Usage:
        ws = MockWebSocket(incoming_messages=[
            json.dumps({"type": "chat_message", "message": "Hello"}),
            Exception("Done")  # Trigger disconnect
        ])

        await websocket_endpoint(ws.mock, session_id)

        # Check sent messages
        connection_msgs = ws.get_messages_by_type("connection_established")
        chunk_msgs = ws.get_messages_by_type("message_chunk")
    """

    def __init__(self, incoming_messages: List = None):
        """
        Create a mock WebSocket

        Args:
            incoming_messages: List of messages to return from receive_text()
                              Can include Exception objects to simulate errors
        """
        self.mock = AsyncMock(spec=WebSocket)
        self.mock.accept = AsyncMock()
        self.mock.send_text = AsyncMock(side_effect=self._capture_send)
        self.sent_messages: List[Dict[str, Any]] = []
        self.sent_raw: List[str] = []

        # Set up incoming messages
        if incoming_messages:
            self.mock.receive_text = AsyncMock(side_effect=incoming_messages)
        else:
            # Default: immediate disconnect
            self.mock.receive_text = AsyncMock(side_effect=Exception("Client disconnected"))

    async def _capture_send(self, message: str):
        """Capture messages sent through WebSocket"""
        self.sent_raw.append(message)
        try:
            parsed = json.loads(message)
            self.sent_messages.append(parsed)
        except json.JSONDecodeError:
            # Non-JSON message, store as-is
            self.sent_messages.append({"_raw": message})

    def get_messages_by_type(self, message_type: str) -> List[Dict[str, Any]]:
        """Get all sent messages of a specific type"""
        return [msg for msg in self.sent_messages if msg.get("type") == message_type]

    def get_all_messages(self) -> List[Dict[str, Any]]:
        """Get all sent messages"""
        return self.sent_messages

    def get_message_types(self) -> List[str]:
        """Get list of all message types sent"""
        return [msg.get("type") for msg in self.sent_messages if "type" in msg]

    def assert_message_type_sent(self, message_type: str, count: Optional[int] = None):
        """
        Assert that a message type was sent

        Args:
            message_type: Type of message to check
            count: If provided, assert exact count. Otherwise just check > 0

        Raises:
            AssertionError: If assertion fails
        """
        messages = self.get_messages_by_type(message_type)
        if count is not None:
            assert len(messages) == count, \
                f"Expected {count} '{message_type}' messages, got {len(messages)}"
        else:
            assert len(messages) > 0, \
                f"Expected at least one '{message_type}' message, got none. " \
                f"Sent types: {self.get_message_types()}"

    def assert_message_sequence(self, expected_types: List[str], allow_extras: bool = True):
        """
        Assert that messages were sent in expected order

        Args:
            expected_types: List of message types in expected order
            allow_extras: If True, allows extra messages between expected ones

        Raises:
            AssertionError: If order doesn't match
        """
        actual_types = self.get_message_types()

        if not allow_extras:
            assert actual_types == expected_types, \
                f"Expected exact sequence {expected_types}, got {actual_types}"
        else:
            # Check that expected types appear in order (with possible extras)
            expected_idx = 0
            for actual_type in actual_types:
                if expected_idx < len(expected_types) and actual_type == expected_types[expected_idx]:
                    expected_idx += 1

            assert expected_idx == len(expected_types), \
                f"Expected sequence {expected_types} not found in order. " \
                f"Got: {actual_types}, matched {expected_idx}/{len(expected_types)}"


def extract_messages_by_type(sent_messages: List[str], message_type: str) -> List[Dict[str, Any]]:
    """
    Extract messages of a specific type from raw sent messages

    Args:
        sent_messages: List of raw JSON string messages
        message_type: Type to filter by

    Returns:
        List of parsed message dictionaries
    """
    result = []
    for msg_str in sent_messages:
        try:
            msg = json.loads(msg_str)
            if msg.get("type") == message_type:
                result.append(msg)
        except json.JSONDecodeError:
            continue
    return result


def create_chat_message(message: str, auth_token: str = "test_token", profile_id: str = "test_profile") -> str:
    """
    Create a properly formatted chat message JSON string

    Args:
        message: The chat message content
        auth_token: Authentication token
        profile_id: Profile ID

    Returns:
        JSON string ready to send via WebSocket
    """
    return json.dumps({
        "type": "chat_message",
        "message": message,
        "auth_token": auth_token,
        "profile_id": profile_id
    })


def create_ui_state_update(state: Dict[str, Any]) -> str:
    """
    Create a UI state update message

    Args:
        state: UI state dictionary

    Returns:
        JSON string ready to send via WebSocket
    """
    return json.dumps({
        "type": "ui_state_update",
        "state": state
    })


def create_heartbeat() -> str:
    """Create a heartbeat message"""
    return json.dumps({"type": "heartbeat"})
