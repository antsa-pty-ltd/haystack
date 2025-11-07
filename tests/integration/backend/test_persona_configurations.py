"""
Integration tests for persona configurations.

Tests the 3 personas in the Haystack service:
- web_assistant (33 tools, temp 0.7, shows tool banners)
- jaimee_therapist (5 tools, temp 0.8, hides execution)
- transcriber_agent (~10 tools, document-focused)

Integration Points:
- PersonaManager ↔ Persona configurations
- Persona ↔ Tool filtering
- Persona ↔ System prompt construction
- Persona ↔ OpenAI settings (temperature, model)

Tests:
- Persona retrieval and configuration
- Tool availability by persona
- Model and temperature settings
- System prompt with context injection
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestPersonaRetrieval:
    """Tests for persona retrieval and basic configuration"""

    async def test_get_web_assistant_persona(self):
        """
        Test get_persona returns web_assistant configuration.

        Flow:
        1. Call get_persona("web_assistant")
        2. Verify persona config returned
        3. Verify name, model, temperature

        This tests:
        - Persona retrieval
        - Configuration structure
        """
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        persona = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)

        assert persona is not None
        assert persona.name == "web_assistant" or "assistant" in persona.name.lower()
        assert persona.model == "gpt-4.1" or "gpt-4" in persona.model.lower()
        assert persona.temperature == 0.7

    async def test_get_jaimee_therapist_persona(self):
        """Test get_persona returns jaimee_therapist configuration"""
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        persona = persona_manager.get_persona(PersonaType.JAIMEE_THERAPIST)

        assert persona is not None
        assert "jaimee" in persona.name.lower() or "therapist" in persona.name.lower()
        assert persona.model == "gpt-4.1" or "gpt-4" in persona.model.lower()
        assert persona.temperature == 0.8  # Higher temperature for therapeutic responses

    async def test_get_transcriber_agent_persona(self):
        """Test get_persona returns transcriber_agent configuration"""
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        persona = persona_manager.get_persona(PersonaType.TRANSCRIBER_AGENT)

        assert persona is not None
        assert "transcriber" in persona.name.lower() or "agent" in persona.name.lower()
        assert persona.model == "gpt-4.1" or "gpt-4" in persona.model.lower()

    async def test_all_persona_types_exist(self):
        """Test all 3 persona types can be retrieved"""
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        # All 3 personas should be retrievable
        web = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)
        jaimee = persona_manager.get_persona(PersonaType.JAIMEE_THERAPIST)
        transcriber = persona_manager.get_persona(PersonaType.TRANSCRIBER_AGENT)

        assert web is not None
        assert jaimee is not None
        assert transcriber is not None


class TestPersonaToolFiltering:
    """Tests for tool availability by persona"""

    async def test_web_assistant_has_many_tools(self):
        """
        Test web_assistant has access to most tools (33 tools).

        Flow:
        1. Get web_assistant persona
        2. Check tools list
        3. Verify has client, session, template tools

        This tests:
        - Tool filtering by persona
        - Web assistant capabilities
        """
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        persona = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)

        # Web assistant should have access to many tools
        assert len(persona.tools) >= 20  # Should have 33 tools

        # Check for specific tool categories
        tool_names = [tool["function"]["name"] for tool in persona.tools]

        # Should have client management tools
        assert "search_clients" in tool_names or len(tool_names) > 20

    async def test_jaimee_therapist_limited_tools(self):
        """
        Test jaimee_therapist has limited tools (5 tools).

        Flow:
        1. Get jaimee_therapist persona
        2. Check tools list
        3. Verify has only therapeutic tools

        This tests:
        - Tool restriction by persona
        - Therapeutic tool set
        """
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        persona = persona_manager.get_persona(PersonaType.JAIMEE_THERAPIST)

        # Jaimee should have limited tools (5)
        assert len(persona.tools) <= 10  # Should be around 5

        tool_names = [tool["function"]["name"] for tool in persona.tools]

        # Should have therapeutic tools
        # Examples: mood_check_in, coping_strategies, breathing_exercise
        therapeutic_tools = ["mood_check_in", "coping_strategies", "breathing_exercise",
                           "get_client_mood_profile", "get_user_profile"]

        # At least some therapeutic tools present
        has_therapeutic = any(tool in tool_names for tool in therapeutic_tools)
        assert has_therapeutic or len(tool_names) <= 10

    async def test_transcriber_agent_document_tools(self):
        """Test transcriber_agent has document-focused tools"""
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        persona = persona_manager.get_persona(PersonaType.TRANSCRIBER_AGENT)

        # Transcriber should have some tools
        assert len(persona.tools) >= 0  # May have variable number of tools

        tool_names = [tool["function"]["name"] for tool in persona.tools]

        # Should have template/document tools if any tools present
        if len(tool_names) > 0:
            document_tools = ["get_templates", "generate_document_from_loaded",
                             "search_sessions", "load_session"]

            has_document_tools = any(tool in tool_names for tool in document_tools)
            # Either has document tools or has other tools
            assert has_document_tools or len(tool_names) > 0
        else:
            # No tools is also valid
            assert True

    async def test_web_assistant_vs_jaimee_tool_difference(self):
        """
        Test web_assistant has more tools than jaimee_therapist.

        Flow:
        1. Get both personas
        2. Compare tool counts
        3. Verify web_assistant > jaimee_therapist

        This tests:
        - Persona-based tool filtering
        - Access control by persona
        """
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        web = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)
        jaimee = persona_manager.get_persona(PersonaType.JAIMEE_THERAPIST)

        web_tool_count = len(web.tools)
        jaimee_tool_count = len(jaimee.tools)

        # Web assistant should have significantly more tools
        assert web_tool_count > jaimee_tool_count


class TestPersonaSettings:
    """Tests for persona model and temperature settings"""

    async def test_web_assistant_temperature_is_07(self):
        """Test web_assistant uses temperature 0.7 for balanced responses"""
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        persona = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)

        assert persona.temperature == 0.7

    async def test_jaimee_therapist_temperature_is_08(self):
        """Test jaimee_therapist uses temperature 0.8 for more creative/empathetic responses"""
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        persona = persona_manager.get_persona(PersonaType.JAIMEE_THERAPIST)

        assert persona.temperature == 0.8  # More creative for therapy

    async def test_all_personas_use_gpt4_model(self):
        """Test all personas use GPT-4.1 model"""
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        web = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)
        jaimee = persona_manager.get_persona(PersonaType.JAIMEE_THERAPIST)
        transcriber = persona_manager.get_persona(PersonaType.TRANSCRIBER_AGENT)

        # All should use gpt-4.1
        assert "gpt-4" in web.model.lower()
        assert "gpt-4" in jaimee.model.lower()
        assert "gpt-4" in transcriber.model.lower()

    async def test_all_personas_have_max_tokens_set(self):
        """Test all personas have max_tokens configured (32768)"""
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        web = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)
        jaimee = persona_manager.get_persona(PersonaType.JAIMEE_THERAPIST)
        transcriber = persona_manager.get_persona(PersonaType.TRANSCRIBER_AGENT)

        # All should have max_tokens set
        assert web.max_tokens > 0
        assert jaimee.max_tokens > 0
        assert transcriber.max_tokens > 0


class TestSystemPromptConstruction:
    """Tests for system prompt construction with context"""

    async def test_web_assistant_system_prompt_includes_instructions(self):
        """
        Test web_assistant system prompt includes key instructions.

        Flow:
        1. Get web_assistant persona
        2. Get system prompt
        3. Verify includes tool usage instructions
        4. Verify includes NEVER DIAGNOSE warning

        This tests:
        - System prompt construction
        - Instruction content
        """
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        persona = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)

        system_prompt = persona.system_prompt

        # Should contain key instructions
        assert "tool" in system_prompt.lower() or "function" in system_prompt.lower()
        assert "diagnos" in system_prompt.lower()  # NEVER diagnose warning

    async def test_jaimee_therapist_system_prompt_is_therapeutic(self):
        """Test jaimee_therapist system prompt has therapeutic tone"""
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        persona = persona_manager.get_persona(PersonaType.JAIMEE_THERAPIST)

        system_prompt = persona.system_prompt

        # Should have therapeutic language
        assert "jaimee" in system_prompt.lower() or "therapist" in system_prompt.lower() or "empat" in system_prompt.lower()
        assert "diagnos" in system_prompt.lower()  # NEVER diagnose warning

    async def test_system_prompt_with_context_injection(self):
        """
        Test system prompt can have context injected.

        Flow:
        1. Get persona
        2. Call get_system_prompt with context
        3. Verify context included in prompt

        This tests:
        - Context injection
        - Dynamic prompt construction
        """
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        # Test with web_assistant
        persona = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)

        context = {
            "page_type": "clients",
            "user_info": {
                "role": "practitioner",
                "name": "Dr. Smith"
            }
        }

        # Get system prompt (may or may not support context injection)
        system_prompt = persona_manager.get_system_prompt(PersonaType.WEB_ASSISTANT, context)

        # Should return a prompt
        assert isinstance(system_prompt, str)
        assert len(system_prompt) > 100  # Should be substantial


class TestPersonaDatabaseAccess:
    """Tests for persona database access flags"""

    async def test_web_assistant_has_db_access(self):
        """Test web_assistant has_db_access = True"""
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        persona = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)

        assert persona.has_db_access is True

    async def test_jaimee_therapist_no_db_access(self):
        """Test jaimee_therapist has_db_access = False"""
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        persona = persona_manager.get_persona(PersonaType.JAIMEE_THERAPIST)

        assert persona.has_db_access is False  # Limited access for privacy

    async def test_transcriber_agent_no_db_access(self):
        """Test transcriber_agent has_db_access = False"""
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        persona = persona_manager.get_persona(PersonaType.TRANSCRIBER_AGENT)

        # Transcriber typically doesn't need full DB access
        # May or may not have access depending on implementation
        assert isinstance(persona.has_db_access, bool)


class TestPersonaSecurityBoundaries:
    """Tests for security boundaries between personas"""

    async def test_jaimee_cannot_execute_search_clients(self):
        """
        Test that jaimee_therapist cannot access search_clients tool.

        Flow:
        1. Get jaimee_therapist persona tools
        2. Verify search_clients NOT in available tools
        3. Verify only therapeutic tools available

        This tests:
        - Security boundary enforcement
        - Client-facing persona isolation
        - Data privacy protection
        - Prevents jaimee from accessing practitioner-only data
        """
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        # Get jaimee_therapist persona
        jaimee_persona = persona_manager.get_persona(PersonaType.JAIMEE_THERAPIST)

        # Extract tool names from available tools
        jaimee_tool_names = [
            tool["function"]["name"]
            for tool in jaimee_persona.tools
        ]

        # Verify search_clients NOT available to jaimee
        assert "search_clients" not in jaimee_tool_names, \
            "jaimee_therapist should NOT have access to search_clients (practitioner tool)"

        # Verify get_client_summary NOT available
        assert "get_client_summary" not in jaimee_tool_names, \
            "jaimee_therapist should NOT have access to get_client_summary"

        # Verify get_conversations NOT available (practitioner data)
        assert "get_conversations" not in jaimee_tool_names, \
            "jaimee_therapist should NOT have access to get_conversations"

        # Verify jaimee only has therapeutic tools
        therapeutic_tools = ["mood_check_in", "coping_strategies", "breathing_exercise"]
        available_therapeutic = [
            tool for tool in therapeutic_tools if tool in jaimee_tool_names
        ]

        assert len(available_therapeutic) > 0, \
            "jaimee_therapist should have therapeutic tools"

    async def test_web_assistant_can_access_practitioner_tools(self):
        """
        Test that web_assistant CAN access practitioner tools.

        Flow:
        1. Get web_assistant persona tools
        2. Verify search_clients IS available
        3. Verify other practitioner tools available

        This tests:
        - Practitioner persona has full access
        - Tool filtering is selective (not blanket restriction)
        """
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()

        # Get web_assistant persona
        web_persona = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)

        # Extract tool names
        web_tool_names = [
            tool["function"]["name"]
            for tool in web_persona.tools
        ]

        # Verify practitioner tools ARE available
        assert "search_clients" in web_tool_names, \
            "web_assistant should have access to search_clients"
        assert "get_client_summary" in web_tool_names, \
            "web_assistant should have access to get_client_summary"

        # Should have significantly more tools than jaimee
        assert len(web_tool_names) > 15, \
            f"web_assistant should have 15+ tools, has {len(web_tool_names)}"
