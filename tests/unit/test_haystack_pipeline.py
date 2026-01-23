"""Unit tests for Haystack Pipeline Manager."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
sys.path.insert(0, '.')


@pytest.fixture
def mock_settings():
    """Mock settings with test values."""
    mock = MagicMock()
    mock.openai_api_key = "sk-test-key"
    return mock


@pytest.fixture
def mock_tool_manager():
    """Mock tool manager with a mock tool."""
    mock = MagicMock()
    mock_tool = MagicMock()
    mock_tool.name = "mock_tool"
    mock_tool.description = "A mock tool for testing"
    mock.get_haystack_component_tools = MagicMock(return_value=[mock_tool])
    return mock


@pytest.fixture
def mock_persona_manager():
    """Mock persona manager."""
    mock = MagicMock()
    persona_config = MagicMock()
    persona_config.model = "gpt-4o"
    persona_config.temperature = 0.7
    persona_config.max_completion_tokens = 4096
    mock.get_persona = MagicMock(return_value=persona_config)
    return mock


@pytest.mark.unit
class TestToolDisplayNames:
    """Test tool display name mapping."""

    def test_returns_friendly_name_for_known_tools(self):
        from haystack_pipeline import get_friendly_tool_name
        assert get_friendly_tool_name("search_clients") == "Searching for clients"
        assert get_friendly_tool_name("get_client_summary") == "Getting client details"
        assert get_friendly_tool_name("load_session_direct") == "Loading session"

    def test_converts_unknown_tools_to_title_case(self):
        from haystack_pipeline import get_friendly_tool_name
        assert get_friendly_tool_name("some_unknown_tool") == "Some Unknown Tool"

    def test_all_display_names_are_nonempty_strings(self):
        from haystack_pipeline import TOOL_DISPLAY_NAMES
        for tool, display_name in TOOL_DISPLAY_NAMES.items():
            assert isinstance(tool, str) and isinstance(display_name, str)
            assert len(display_name) > 0


@pytest.mark.unit
class TestPipelineManagerInit:
    """Test HaystackPipelineManager initialization."""

    def test_starts_uninitialized(self):
        from haystack_pipeline import HaystackPipelineManager
        manager = HaystackPipelineManager()
        assert manager._initialized is False
        assert manager.pipelines == {}
        assert manager._streaming_callback is None
        assert manager._ui_actions == []

    @pytest.mark.asyncio
    async def test_initialize_sets_flag(self, mock_settings, mock_tool_manager, mock_persona_manager):
        with patch('haystack_pipeline.settings', mock_settings), \
             patch('haystack_pipeline.tool_manager', mock_tool_manager), \
             patch('haystack_pipeline.persona_manager', mock_persona_manager), \
             patch('haystack_pipeline.Pipeline', return_value=MagicMock()):
            from haystack_pipeline import HaystackPipelineManager
            manager = HaystackPipelineManager()
            await manager.initialize()
            assert manager._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self, mock_settings, mock_tool_manager, mock_persona_manager):
        with patch('haystack_pipeline.settings', mock_settings), \
             patch('haystack_pipeline.tool_manager', mock_tool_manager), \
             patch('haystack_pipeline.persona_manager', mock_persona_manager), \
             patch('haystack_pipeline.Pipeline', return_value=MagicMock()):
            from haystack_pipeline import HaystackPipelineManager
            manager = HaystackPipelineManager()
            await manager.initialize()
            await manager.initialize()  # Second call should be no-op


@pytest.mark.unit
class TestPipelineCreation:
    """Test individual pipeline creation."""

    def test_creates_web_assistant_pipeline(self, mock_settings, mock_tool_manager, mock_persona_manager):
        with patch('haystack_pipeline.settings', mock_settings), \
             patch('haystack_pipeline.tool_manager', mock_tool_manager), \
             patch('haystack_pipeline.persona_manager', mock_persona_manager), \
             patch('haystack_pipeline.Pipeline', return_value=MagicMock()), \
             patch('haystack_pipeline.OpenAIChatGenerator'), \
             patch('haystack_pipeline.ConditionalRouter'), \
             patch('haystack_pipeline.ToolInvoker'), \
             patch('haystack_pipeline.PersonaType') as mock_persona_type:
            mock_persona_type.WEB_ASSISTANT = "web_assistant"
            from haystack_pipeline import HaystackPipelineManager
            manager = HaystackPipelineManager()
            manager._create_web_assistant_pipeline()
            assert len(manager.pipelines) > 0

    def test_pipeline_has_required_components(self, mock_settings, mock_tool_manager, mock_persona_manager):
        with patch('haystack_pipeline.settings', mock_settings), \
             patch('haystack_pipeline.tool_manager', mock_tool_manager), \
             patch('haystack_pipeline.persona_manager', mock_persona_manager), \
             patch('haystack_pipeline.Pipeline') as mock_pipeline, \
             patch('haystack_pipeline.OpenAIChatGenerator'), \
             patch('haystack_pipeline.ConditionalRouter'), \
             patch('haystack_pipeline.ToolInvoker'):
            mock_pipeline_instance = MagicMock()
            mock_pipeline.return_value = mock_pipeline_instance
            from haystack_pipeline import HaystackPipelineManager
            manager = HaystackPipelineManager()
            manager._create_web_assistant_pipeline()
            component_names = [call[0][0] for call in mock_pipeline_instance.add_component.call_args_list]
            for required in ["message_collector", "generator", "router", "tool_invoker"]:
                assert required in component_names


@pytest.mark.unit
class TestPersonaTypes:
    """Test persona-specific pipeline configurations."""

    def test_persona_type_enum_has_expected_values(self):
        from personas import PersonaType
        assert hasattr(PersonaType, 'WEB_ASSISTANT')
        assert hasattr(PersonaType, 'JAIMEE_THERAPIST')

    def test_creates_different_pipelines_for_personas(self, mock_settings, mock_tool_manager, mock_persona_manager):
        with patch('haystack_pipeline.settings', mock_settings), \
             patch('haystack_pipeline.tool_manager', mock_tool_manager), \
             patch('haystack_pipeline.persona_manager', mock_persona_manager), \
             patch('haystack_pipeline.Pipeline', side_effect=[MagicMock(), MagicMock(), MagicMock()]), \
             patch('haystack_pipeline.OpenAIChatGenerator'), \
             patch('haystack_pipeline.ConditionalRouter'), \
             patch('haystack_pipeline.ToolInvoker'):
            from haystack_pipeline import HaystackPipelineManager
            manager = HaystackPipelineManager()
            manager._create_web_assistant_pipeline()
            manager._create_jaimee_therapist_pipeline()
            assert len(manager.pipelines) >= 2


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling in pipeline manager."""

    @pytest.mark.asyncio
    async def test_initialize_handles_config_errors(self):
        with patch('haystack_pipeline.settings') as mock_settings, \
             patch('haystack_pipeline.persona_manager') as mock_pm:
            mock_settings.openai_api_key = "test-key"
            mock_pm.get_persona.side_effect = Exception("Config error")
            from haystack_pipeline import HaystackPipelineManager
            manager = HaystackPipelineManager()
            with pytest.raises(Exception):
                await manager.initialize()
            assert manager._initialized is False


@pytest.mark.unit
class TestRouteConfiguration:
    """Test pipeline route configuration."""

    def test_routes_have_tool_calls_and_final_response(self, mock_settings, mock_tool_manager, mock_persona_manager):
        with patch('haystack_pipeline.settings', mock_settings), \
             patch('haystack_pipeline.tool_manager', mock_tool_manager), \
             patch('haystack_pipeline.persona_manager', mock_persona_manager), \
             patch('haystack_pipeline.Pipeline'), \
             patch('haystack_pipeline.OpenAIChatGenerator'), \
             patch('haystack_pipeline.ConditionalRouter') as mock_router, \
             patch('haystack_pipeline.ToolInvoker'):
            from haystack_pipeline import HaystackPipelineManager
            manager = HaystackPipelineManager()
            manager._create_web_assistant_pipeline()
            mock_router.assert_called()
            routes = mock_router.call_args[0][0]
            route_names = [r["output_name"] for r in routes]
            assert "has_tool_calls" in route_names
            assert "final_response" in route_names
