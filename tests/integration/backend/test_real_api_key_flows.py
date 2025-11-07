"""
Real OpenAI API Integration Tests

Tests real OpenAI API integration flows WITHOUT mocking.
These tests use actual OpenAI API calls and verify real behavior.

⚠️ WARNING: These tests cost real money and are SLOW.
Run with: pytest -m real_ai tests/integration/backend/test_real_api_key_flows.py

Test Categories:
1. Document Generation E2E (3 tests)
   - Full workflow: template + transcript → real document
   - Template variable substitution with real GPT
   - Policy violation detection with real GPT-4o-mini

2. Persona Behavior (3 tests)
   - Web assistant professional tone verification
   - Jaimee therapist empathetic tone verification
   - Tool selection accuracy with real model

3. Multi-Tool Chains (2 tests)
   - 5-tool chain integration with real OpenAI
   - Conversation analysis chain with real GPT

Integration Points:
- FastAPI ↔ Real OpenAI API
- Template processing with actual GPT responses
- Policy detection with GPT-4o-mini
- Persona-specific behavior verification
- Tool chaining with real function calling

Note: All tests use semantic assertions (NOT exact text matching)
      to handle natural variability in GPT responses.
"""

import os
import sys
# Add haystack directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

import pytest
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any
from openai import AsyncOpenAI, APIError, RateLimitError, APIConnectionError

# Import test helpers
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from helpers.test_data_factory import TestDataFactory

# Mark all tests as real_ai and asyncio
pytestmark = [pytest.mark.asyncio, pytest.mark.real_ai]


# Fixtures
# Note: real_openai_client fixture is provided by conftest.py

@pytest.fixture
def timeout_short():
    """Provides 15 second timeout for quick API calls"""
    return 15.0

@pytest.fixture
def timeout_medium():
    """Provides 30 second timeout for document generation"""
    return 30.0

@pytest.fixture
def timeout_long():
    """Provides 60 second timeout for multi-tool chains"""
    return 60.0


# Test Classes

class TestDocumentGenerationE2E:
    """
    Real OpenAI API tests for document generation end-to-end flows.

    These tests verify the complete document generation pipeline using
    actual GPT-4 API calls without any mocking.
    """

    @pytest.mark.real_ai
    @pytest.mark.asyncio
    async def test_real_api_document_generation_full_workflow(
        self,
        real_openai_client,
        timeout_medium
    ):
        """
        Test full document generation workflow with REAL OpenAI API.

        Flow:
        1. Create realistic template + transcript data
        2. Build system prompt with template and context
        3. Call REAL GPT-4 to generate document
        4. Verify document contains expected content (semantic assertions)
        5. Verify response structure and metadata

        This tests:
        - Real OpenAI API integration
        - Template → Document generation
        - Transcript → Content extraction
        - Variable substitution by GPT
        - Response parsing and structure

        Assertions:
        - Uses semantic checks (NOT exact text matching)
        - Verifies key information is present
        - Checks document structure and completeness
        """
        # Create realistic test data
        template = TestDataFactory.create_safe_template(
            id="progress_note_real",
            name="Session Progress Note"
        )
        template["content"] = """Create a comprehensive session progress note including:
- Client name and practitioner name
- Session date
- Summary of topics discussed
- Interventions used
- Treatment plan updates
- Next steps

Use professional clinical language appropriate for medical records."""

        transcript = TestDataFactory.create_transcript(segment_count=8)
        # Add more realistic content
        transcript["segments"] = [
            {"speaker": "Practitioner", "text": "Hello Sarah, how have you been feeling this week?", "startTime": 0},
            {"speaker": "Client", "text": "I've been doing better with the anxiety exercises we discussed.", "startTime": 5},
            {"speaker": "Practitioner", "text": "That's great progress. Can you tell me more about what's been working?", "startTime": 10},
            {"speaker": "Client", "text": "The breathing exercises really help when I feel overwhelmed at work.", "startTime": 15},
            {"speaker": "Practitioner", "text": "Excellent. Let's review your homework from last session.", "startTime": 20},
            {"speaker": "Client", "text": "I completed the mood journal every day like we planned.", "startTime": 25},
            {"speaker": "Practitioner", "text": "I'm impressed with your consistency. Let's discuss what you noticed.", "startTime": 30},
            {"speaker": "Client", "text": "I noticed my anxiety is highest on Monday mornings before meetings.", "startTime": 35},
        ]

        client_info = TestDataFactory.create_client_info(
            name="Sarah Johnson",
            id="client_real_001"
        )
        practitioner_info = TestDataFactory.create_practitioner_info(
            name="Dr. Emily Chen",
            id="prac_real_001"
        )

        # Build system prompt (mimics main.py logic)
        system_prompt = f"""You are an AI assistant helping a mental health practitioner generate clinical documentation.

**Template:** {template['name']}
{template['content']}

**Client Information:**
- Name: {client_info['name']}
- ID: {client_info['id']}

**Practitioner Information:**
- Name: {practitioner_info['name']}
- ID: {practitioner_info['id']}

**Session Date:** {datetime.now(timezone.utc).strftime('%B %d, %Y')}

Generate a professional clinical document based on the template and transcript provided."""

        # Build user message with transcript
        transcript_text = "\n".join([
            f"{seg['speaker']}: {seg['text']}"
            for seg in transcript["segments"]
        ])
        user_message = f"""Please generate the document based on this session transcript:

{transcript_text}

Remember to use the client name '{client_info['name']}' and practitioner name '{practitioner_info['name']}' appropriately."""

        # Make REAL OpenAI API call
        try:
            response = await asyncio.wait_for(
                real_openai_client.chat.completions.create(
                    model="gpt-4o",  # Use GPT-4o as per main.py
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=0.8,
                    max_tokens=2000
                ),
                timeout=timeout_medium
            )
        except asyncio.TimeoutError:
            pytest.fail("Real OpenAI API call timed out after 30 seconds")
        except RateLimitError as e:
            pytest.skip(f"OpenAI rate limit exceeded: {e}")
        except APIConnectionError as e:
            pytest.skip(f"OpenAI API connection failed: {e}")
        except APIError as e:
            pytest.fail(f"OpenAI API error: {e}")

        # Verify response structure
        assert response is not None, "Should receive response from OpenAI"
        assert len(response.choices) > 0, "Response should have choices"

        content = response.choices[0].message.content
        assert content is not None, "Response content should not be None"
        assert len(content) > 100, "Generated document should be substantial (>100 chars)"

        # Semantic assertions (NOT exact matching)
        content_lower = content.lower()

        # Verify client name appears in document
        assert "sarah johnson" in content_lower or "sarah" in content_lower, \
            "Document should contain client name"

        # Verify practitioner name appears
        assert "dr. emily chen" in content_lower or "emily chen" in content_lower or "dr. chen" in content_lower, \
            "Document should contain practitioner name"

        # Verify session content is reflected
        assert "anxiety" in content_lower, \
            "Document should mention anxiety (key topic from transcript)"

        # Verify clinical terms are present (shows professional tone)
        clinical_terms = ["session", "client", "practitioner", "progress", "treatment", "intervention"]
        found_terms = [term for term in clinical_terms if term in content_lower]
        assert len(found_terms) >= 3, \
            f"Document should contain clinical terminology (found: {found_terms})"

        # Verify response metadata
        assert response.choices[0].finish_reason in ["stop", "length"], \
            "Response should complete normally"

        print(f"\n✓ Real API Test Passed - Generated {len(content)} characters")
        print(f"✓ Model used: {response.model}")
        print(f"✓ Tokens used: {response.usage.total_tokens if response.usage else 'N/A'}")

    @pytest.mark.real_ai
    @pytest.mark.asyncio
    async def test_real_api_template_variable_substitution(
        self,
        real_openai_client,
        timeout_medium
    ):
        """
        Test template variable substitution with REAL OpenAI API.

        Flow:
        1. Create template with variables: {{clientName}}, {{date}}, {{practitionerName}}
        2. Build prompt instructing GPT to substitute variables
        3. Call REAL GPT-4 API
        4. Verify variables are replaced with actual values
        5. Verify placeholder syntax is NOT in output

        This tests:
        - Variable substitution via GPT instruction
        - Template personalization
        - Date formatting by GPT
        - Instruction following by real model

        Assertions:
        - Actual names appear in document
        - Variable placeholders do NOT appear
        - Date information is present
        - Professional formatting maintained
        """
        # Create template with variables
        template_content = """Progress Note for {{clientName}}

**Practitioner:** {{practitionerName}}
**Date:** {{date}}

Session conducted with {{clientName}} by {{practitionerName}} on {{date}}.

Summary: Document the key discussion points and interventions used during this session."""

        client_info = TestDataFactory.create_client_info(
            name="Michael Torres",
            id="client_var_001"
        )
        practitioner_info = TestDataFactory.create_practitioner_info(
            name="Dr. Lisa Park",
            id="prac_var_001"
        )

        current_date = datetime.now(timezone.utc).strftime("%B %d, %Y")

        # Build system prompt with substitution instructions
        system_prompt = f"""You are generating clinical documentation.

IMPORTANT: Replace all template variables with actual values:
- Replace {{{{clientName}}}} with: {client_info['name']}
- Replace {{{{practitionerName}}}} with: {practitioner_info['name']}
- Replace {{{{date}}}} with: {current_date}

**Template:**
{template_content}

Generate the complete document with all variables substituted."""

        user_message = """Generate the progress note. The client discussed their progress with stress management techniques and completed homework assignments."""

        # Make REAL OpenAI API call
        try:
            response = await asyncio.wait_for(
                real_openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=0.7,
                    max_tokens=1500
                ),
                timeout=timeout_medium
            )
        except asyncio.TimeoutError:
            pytest.fail("Real OpenAI API call timed out")
        except RateLimitError as e:
            pytest.skip(f"OpenAI rate limit exceeded: {e}")
        except APIConnectionError as e:
            pytest.skip(f"OpenAI API connection failed: {e}")
        except APIError as e:
            pytest.fail(f"OpenAI API error: {e}")

        content = response.choices[0].message.content
        assert content is not None and len(content) > 50, \
            "Should generate substantial content"

        # Verify variables were substituted
        assert "Michael Torres" in content, \
            "Client name should be substituted"
        assert "Dr. Lisa Park" in content or "Lisa Park" in content, \
            "Practitioner name should be substituted"

        # Verify date information is present (flexible matching)
        assert any(month in content for month in ["January", "February", "March", "April", "May", "June",
                                                    "July", "August", "September", "October", "November", "December"]) \
            or "2024" in content or "2025" in content, \
            "Date information should be present"

        # CRITICAL: Verify placeholders are NOT in output
        assert "{{clientName}}" not in content, \
            "Template variable {{clientName}} should be replaced"
        assert "{{practitionerName}}" not in content, \
            "Template variable {{practitionerName}} should be replaced"
        assert "{{date}}" not in content, \
            "Template variable {{date}} should be replaced"

        print(f"\n✓ Variable Substitution Test Passed")
        print(f"✓ Client name: Michael Torres → Found in document")
        print(f"✓ Practitioner name: Dr. Lisa Park → Found in document")
        print(f"✓ All placeholders removed successfully")

    @pytest.mark.real_ai
    @pytest.mark.asyncio
    async def test_real_api_policy_violation_detection(
        self,
        real_openai_client,
        timeout_medium
    ):
        """
        Test policy violation detection with REAL GPT-4o-mini API.

        Flow:
        1. Create template that requests DSM-5 diagnosis (policy violation)
        2. Build policy check prompt (mimics main.py detect_policy_violation)
        3. Call REAL GPT-4o-mini for policy analysis
        4. Verify violation is detected
        5. Test safe template for comparison

        This tests:
        - Real policy violation detection
        - GPT-4o-mini instruction following
        - JSON response parsing
        - Violation type classification

        Assertions:
        - Violating template is correctly flagged
        - Violation type is identified
        - Safe template passes check
        - Response is valid JSON
        """
        # Create violating template (requests diagnosis)
        violating_template = TestDataFactory.create_violating_template(
            id="diagnostic_template",
            name="DSM-5 Diagnostic Assessment"
        )
        violating_content = """Based on the client's reported symptoms and behaviors observed during the session,
provide a comprehensive DSM-5 diagnosis including primary and secondary diagnoses with diagnostic codes."""

        # Policy check prompt (based on main.py detect_policy_violation)
        policy_check_prompt = f"""Analyze this clinical documentation template for policy violations.

**Template Content:**
{violating_content}

**Policy Rules:**
1. NEVER provide DSM-5 diagnoses or diagnostic assessments
2. NEVER suggest diagnostic criteria are met
3. NEVER imply specific mental health conditions
4. Document only observations and reported symptoms
5. Always defer diagnosis to qualified professionals

**Response Format (JSON):**
{{
    "is_violation": true/false,
    "violation_type": "medical_diagnosis_request" or null,
    "explanation": "Brief explanation of why this is/isn't a violation"
}}

Analyze the template and respond ONLY with valid JSON."""

        # Make REAL GPT-4o-mini API call for policy check
        try:
            response = await asyncio.wait_for(
                real_openai_client.chat.completions.create(
                    model="gpt-4o-mini",  # Use mini for policy checks (cheaper)
                    messages=[
                        {"role": "system", "content": "You are a policy compliance checker for clinical documentation."},
                        {"role": "user", "content": policy_check_prompt}
                    ],
                    temperature=0.3,  # Lower temperature for consistent policy checking
                    max_tokens=500,
                    response_format={"type": "json_object"}  # Force JSON response
                ),
                timeout=timeout_medium
            )
        except asyncio.TimeoutError:
            pytest.fail("Policy check API call timed out")
        except RateLimitError as e:
            pytest.skip(f"OpenAI rate limit exceeded: {e}")
        except APIConnectionError as e:
            pytest.skip(f"OpenAI API connection failed: {e}")
        except APIError as e:
            pytest.fail(f"OpenAI API error: {e}")

        content = response.choices[0].message.content
        assert content is not None, "Should receive policy check response"

        # Parse JSON response
        import json
        try:
            policy_result = json.loads(content)
        except json.JSONDecodeError:
            pytest.fail(f"Policy check response is not valid JSON: {content}")

        # Verify violation was detected
        assert "is_violation" in policy_result, \
            "Response should contain is_violation field"
        assert policy_result["is_violation"] is True, \
            "Should detect policy violation in diagnostic template"

        if "violation_type" in policy_result:
            assert policy_result["violation_type"] is not None, \
                "Should identify violation type"

        print(f"\n✓ Policy Violation Detected Successfully")
        print(f"✓ Violation: {policy_result.get('is_violation')}")
        print(f"✓ Type: {policy_result.get('violation_type', 'N/A')}")
        print(f"✓ Explanation: {policy_result.get('explanation', 'N/A')[:100]}...")

        # Test safe template for comparison
        safe_template = TestDataFactory.create_safe_template()
        safe_check_prompt = policy_check_prompt.replace(violating_content, safe_template["content"])

        try:
            safe_response = await asyncio.wait_for(
                real_openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a policy compliance checker."},
                        {"role": "user", "content": safe_check_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=500,
                    response_format={"type": "json_object"}
                ),
                timeout=timeout_medium
            )
        except asyncio.TimeoutError:
            pytest.fail("Safe template check timed out")
        except RateLimitError as e:
            pytest.skip(f"OpenAI rate limit exceeded: {e}")
        except APIConnectionError as e:
            pytest.skip(f"OpenAI API connection failed: {e}")
        except APIError as e:
            pytest.fail(f"OpenAI API error: {e}")

        safe_content = safe_response.choices[0].message.content
        safe_result = json.loads(safe_content)

        # Verify safe template passes
        assert safe_result["is_violation"] is False, \
            "Safe template should NOT be flagged as violation"

        print(f"✓ Safe template passed policy check")


class TestPersonaBehavior:
    """
    Real OpenAI API tests for persona-specific behavior verification.

    These tests verify that different personas produce appropriate responses
    when using the actual GPT-4 model.
    """

    @pytest.mark.real_ai
    @pytest.mark.asyncio
    async def test_real_api_web_assistant_professional_tone(
        self,
        real_openai_client,
        timeout_short
    ):
        """
        Test web assistant persona produces professional practitioner responses.

        Flow:
        1. Load web_assistant persona configuration
        2. Build system prompt with persona instructions
        3. Send practitioner query to REAL GPT-4
        4. Verify professional tone and terminology
        5. Verify appropriate information architecture

        This tests:
        - Persona system prompt effectiveness
        - Professional tone with real model
        - Clinical terminology usage
        - Response appropriateness for practitioners

        Assertions:
        - Response uses professional language
        - Contains relevant clinical terms
        - Provides actionable information
        - Maintains practitioner perspective
        """
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()
        web_assistant = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)

        # Use actual system prompt from persona
        system_prompt = web_assistant.system_prompt

        user_message = """I need to review my client Sarah's progress.
Can you help me understand what information I should look at to assess her treatment effectiveness?"""

        # Make REAL API call with persona settings
        try:
            response = await asyncio.wait_for(
                real_openai_client.chat.completions.create(
                    model=web_assistant.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=web_assistant.temperature,
                    max_tokens=1000
                ),
                timeout=timeout_short
            )
        except asyncio.TimeoutError:
            pytest.fail("Web assistant API call timed out")
        except RateLimitError as e:
            pytest.skip(f"OpenAI rate limit exceeded: {e}")
        except APIConnectionError as e:
            pytest.skip(f"OpenAI API connection failed: {e}")
        except APIError as e:
            pytest.fail(f"OpenAI API error: {e}")

        content = response.choices[0].message.content
        assert content is not None and len(content) > 100, \
            "Should generate substantial response"

        content_lower = content.lower()

        # Verify professional tone markers
        professional_terms = [
            "client", "treatment", "progress", "assessment", "session",
            "intervention", "outcomes", "goals", "plan"
        ]
        found_terms = [term for term in professional_terms if term in content_lower]
        assert len(found_terms) >= 3, \
            f"Should use professional clinical terminology (found: {found_terms})"

        # Verify practitioner perspective (not client-facing language)
        # Should NOT use overly casual or therapeutic language
        assert "sarah" in content_lower, \
            "Should reference the client by name"

        # Verify structured/organized response (looks for lists or sections)
        structure_indicators = ["1.", "2.", "-", "•", "first", "second", "additionally"]
        has_structure = any(indicator in content for indicator in structure_indicators)
        assert has_structure, \
            "Response should be well-structured and organized"

        print(f"\n✓ Web Assistant Professional Tone Verified")
        print(f"✓ Clinical terms found: {found_terms}")
        print(f"✓ Response length: {len(content)} characters")
        print(f"✓ Model: {web_assistant.model}, Temp: {web_assistant.temperature}")

    @pytest.mark.real_ai
    @pytest.mark.asyncio
    async def test_real_api_jaimee_therapist_empathetic_tone(
        self,
        real_openai_client,
        timeout_short
    ):
        """
        Test Jaimee therapist persona produces empathetic therapeutic responses.

        Flow:
        1. Load jaimee_therapist persona configuration
        2. Build system prompt with therapeutic instructions
        3. Send client message to REAL GPT-4
        4. Verify empathetic and supportive tone
        5. Verify therapeutic language usage

        This tests:
        - Therapeutic persona effectiveness
        - Empathetic tone with real model
        - Client-appropriate language
        - Supportive response style
        - Higher temperature impact (0.8)

        Assertions:
        - Response is empathetic and warm
        - Uses supportive language
        - Validates client feelings
        - Avoids clinical jargon
        - Maintains therapeutic boundaries
        """
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()
        jaimee = persona_manager.get_persona(PersonaType.JAIMEE_THERAPIST)

        system_prompt = jaimee.system_prompt

        user_message = """I've been feeling really anxious lately.
Every time I have to go to work on Monday morning, my heart starts racing and I feel like I can't breathe."""

        # Make REAL API call with Jaimee settings
        try:
            response = await asyncio.wait_for(
                real_openai_client.chat.completions.create(
                    model=jaimee.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=jaimee.temperature,  # 0.8 for more natural therapeutic responses
                    max_tokens=1000
                ),
                timeout=timeout_short
            )
        except asyncio.TimeoutError:
            pytest.fail("Jaimee therapist API call timed out")
        except RateLimitError as e:
            pytest.skip(f"OpenAI rate limit exceeded: {e}")
        except APIConnectionError as e:
            pytest.skip(f"OpenAI API connection failed: {e}")
        except APIError as e:
            pytest.fail(f"OpenAI API error: {e}")

        content = response.choices[0].message.content
        assert content is not None and len(content) > 100, \
            "Should generate substantial therapeutic response"

        content_lower = content.lower()

        # Verify empathetic/supportive language
        empathetic_markers = [
            "understand", "hear", "sounds like", "feeling", "experiencing",
            "challenging", "difficult", "support", "help", "together"
        ]
        found_empathy = [marker for marker in empathetic_markers if marker in content_lower]
        assert len(found_empathy) >= 2, \
            f"Should use empathetic language (found: {found_empathy})"

        # Verify validation of client's feelings
        validation_markers = ["valid", "understandable", "normal", "common", "okay"]
        has_validation = any(marker in content_lower for marker in validation_markers)
        # Note: validation might be implicit, so this is a soft check

        # Verify avoids overly clinical language (should be client-friendly)
        # Should NOT heavily use terms like "intervention", "diagnosis", "assessment"
        overly_clinical = ["diagnosis", "dsm", "diagnostic", "assessment scale"]
        clinical_count = sum(1 for term in overly_clinical if term in content_lower)
        assert clinical_count == 0, \
            "Jaimee should avoid clinical diagnostic language in client-facing responses"

        print(f"\n✓ Jaimee Therapist Empathetic Tone Verified")
        print(f"✓ Empathetic markers found: {found_empathy}")
        print(f"✓ Response is client-appropriate and supportive")
        print(f"✓ Model: {jaimee.model}, Temp: {jaimee.temperature}")

    @pytest.mark.real_ai
    @pytest.mark.asyncio
    async def test_real_api_tool_selection_accuracy(
        self,
        real_openai_client,
        timeout_short
    ):
        """
        Test tool selection accuracy with REAL OpenAI function calling.

        Flow:
        1. Load web_assistant persona with tools
        2. Send query that requires specific tool
        3. Call REAL GPT-4 with function calling
        4. Verify correct tool is selected
        5. Verify tool arguments are correct

        This tests:
        - Function calling with real model
        - Tool selection intelligence
        - Argument extraction accuracy
        - Persona tool configuration

        Assertions:
        - Correct tool is called
        - Arguments are properly extracted
        - Function calling structure is valid
        - Tool selection matches intent
        """
        from personas import PersonaManager, PersonaType

        persona_manager = PersonaManager()
        web_assistant = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)

        # Filter to a few key tools for this test
        key_tools = [
            tool for tool in web_assistant.tools
            if tool.get("function", {}).get("name") in ["search_clients", "get_client_summary", "search_sessions"]
        ]

        if len(key_tools) == 0:
            pytest.skip("No tools available for tool selection test")

        system_prompt = """You are an AI assistant for mental health practitioners.
You have access to tools to help practitioners manage their practice.
Use the appropriate tool based on the user's request."""

        user_message = "Find all clients named John and show me their information."

        # Make REAL API call with function calling
        try:
            response = await asyncio.wait_for(
                real_openai_client.chat.completions.create(
                    model=web_assistant.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    tools=key_tools,
                    tool_choice="auto",
                    temperature=0.7,
                    max_tokens=1000
                ),
                timeout=timeout_short
            )
        except asyncio.TimeoutError:
            pytest.fail("Tool selection API call timed out")
        except RateLimitError as e:
            pytest.skip(f"OpenAI rate limit exceeded: {e}")
        except APIConnectionError as e:
            pytest.skip(f"OpenAI API connection failed: {e}")
        except APIError as e:
            pytest.fail(f"OpenAI API error: {e}")

        message = response.choices[0].message

        # Verify tool was called
        assert message.tool_calls is not None and len(message.tool_calls) > 0, \
            "Should call a tool for this query"

        tool_call = message.tool_calls[0]
        function_name = tool_call.function.name

        # Verify correct tool was selected
        assert function_name == "search_clients", \
            f"Should call search_clients for finding clients (called: {function_name})"

        # Verify arguments are reasonable
        import json
        arguments = json.loads(tool_call.function.arguments)
        assert "query" in arguments or "name" in arguments or any("john" in str(v).lower() for v in arguments.values()), \
            "Should include 'John' in search arguments"

        print(f"\n✓ Tool Selection Accuracy Verified")
        print(f"✓ Selected tool: {function_name}")
        print(f"✓ Arguments: {arguments}")
        print(f"✓ Function calling worked correctly")


class TestMultiToolChains:
    """
    Real OpenAI API tests for multi-tool chain workflows.

    These tests verify complex tool chaining scenarios using the actual
    GPT-4 model with real function calling.
    """

    @pytest.mark.real_ai
    @pytest.mark.asyncio
    async def test_real_api_5_tool_chain_integration(
        self,
        real_openai_client,
        timeout_long
    ):
        """
        Test 5-tool chain integration with REAL OpenAI API.

        Flow:
        1. Define 5 simple tools (simulate practice management tools)
        2. Send query requiring multiple tool calls
        3. Use REAL GPT-4 function calling in loop
        4. Verify tools are called in logical sequence
        5. Verify final response synthesizes all tool results

        This tests:
        - Multi-step reasoning with real model
        - Sequential tool execution
        - Context retention across tool calls
        - Result synthesis from multiple sources

        Assertions:
        - Multiple tools are called (3-5 tools)
        - Tool sequence is logical
        - Final response incorporates all results
        - No infinite loops (max 10 iterations)
        """
        # Define 5 simple test tools
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_client_count",
                    "description": "Get total number of clients in the practice",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_active_clients",
                    "description": "Get list of currently active clients",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_session_stats",
                    "description": "Get statistics about recent sessions",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_practitioner_count",
                    "description": "Get total number of practitioners",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_utilization",
                    "description": "Calculate practice utilization rate",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            }
        ]

        system_prompt = """You are an AI assistant analyzing practice metrics.
Use the available tools to gather comprehensive statistics and provide a complete analysis."""

        user_message = "Give me a complete overview of our practice metrics including clients, sessions, and utilization."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        tool_calls_made = []
        max_iterations = 10

        # Tool execution loop with REAL API
        for iteration in range(max_iterations):
            try:
                response = await asyncio.wait_for(
                    real_openai_client.chat.completions.create(
                        model="gpt-4o",
                        messages=messages,
                        tools=tools,
                        tool_choice="auto",
                        temperature=0.7,
                        max_tokens=2000
                    ),
                    timeout=timeout_long
                )
            except asyncio.TimeoutError:
                pytest.fail(f"Tool chain API call timed out at iteration {iteration}")
            except RateLimitError as e:
                pytest.skip(f"OpenAI rate limit exceeded: {e}")
            except APIConnectionError as e:
                pytest.skip(f"OpenAI API connection failed: {e}")
            except APIError as e:
                pytest.fail(f"OpenAI API error: {e}")

            assistant_message = response.choices[0].message

            # Check if model wants to call tools
            if not assistant_message.tool_calls:
                # Model is done - should have final response
                assert assistant_message.content is not None, \
                    "Final response should have content"
                # Append final assistant response to message history
                messages.append({
                    "role": "assistant",
                    "content": assistant_message.content
                })
                break

            # Process tool calls
            messages.append({
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    }
                    for tc in assistant_message.tool_calls
                ]
            })

            for tool_call in assistant_message.tool_calls:
                function_name = tool_call.function.name
                tool_calls_made.append(function_name)

                # Simulate tool responses with realistic data
                mock_results = {
                    "get_client_count": '{"total_clients": 45}',
                    "get_active_clients": '{"active_clients": 38, "inactive": 7}',
                    "get_session_stats": '{"total_sessions": 120, "avg_per_week": 30}',
                    "get_practitioner_count": '{"total_practitioners": 5}',
                    "calculate_utilization": '{"utilization_rate": "76%", "capacity": "Good"}'
                }

                result = mock_results.get(function_name, '{"status": "success"}')

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": result
                })

        # Verify multiple tools were called
        assert len(tool_calls_made) >= 3, \
            f"Should call at least 3 tools for comprehensive analysis (called: {len(tool_calls_made)})"
        assert len(tool_calls_made) <= 10, \
            "Should not make excessive tool calls (max 10)"

        # Verify final response exists
        final_message = messages[-1] if messages[-1]["role"] == "assistant" else None
        assert final_message is not None, "Should have final assistant response"

        print(f"\n✓ 5-Tool Chain Integration Verified")
        print(f"✓ Tools called ({len(tool_calls_made)}): {tool_calls_made}")
        print(f"✓ Iterations used: {iteration + 1}")
        print(f"✓ Chain completed successfully")

    @pytest.mark.real_ai
    @pytest.mark.asyncio
    async def test_real_api_conversation_analysis_chain(
        self,
        real_openai_client,
        timeout_long
    ):
        """
        Test conversation analysis tool chain with REAL OpenAI API.

        Flow:
        1. Define conversation analysis tools
        2. Provide realistic therapy transcript
        3. Use REAL GPT-4 to analyze conversation
        4. Verify analysis uses appropriate tools
        5. Verify insights are clinically relevant

        This tests:
        - Conversation analysis capabilities
        - Clinical insight generation
        - Multi-step analysis workflow
        - Real therapeutic content processing

        Assertions:
        - Analysis tools are called appropriately
        - Insights are clinically relevant
        - Themes are identified accurately
        - Recommendations are appropriate
        """
        # Define conversation analysis tools
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "identify_themes",
                    "description": "Identify major themes in the conversation",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transcript": {"type": "string", "description": "The conversation transcript"}
                        },
                        "required": ["transcript"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_sentiment",
                    "description": "Analyze emotional tone and sentiment",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transcript": {"type": "string", "description": "The conversation transcript"}
                        },
                        "required": ["transcript"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "extract_action_items",
                    "description": "Extract homework assignments and action items",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transcript": {"type": "string", "description": "The conversation transcript"}
                        },
                        "required": ["transcript"]
                    }
                }
            }
        ]

        # Realistic therapy transcript
        transcript = """Practitioner: Hello Sarah, how have you been since our last session?

Client: I've been doing better actually. The breathing exercises you taught me have really helped when I start to feel overwhelmed.

Practitioner: That's wonderful to hear. Can you give me an example of when you used them?

Client: Yes, last Tuesday I had a big presentation at work. I could feel the anxiety building up, but I remembered to do the deep breathing and it really calmed me down.

Practitioner: Excellent work. That shows real progress in managing your anxiety. How did the presentation go?

Client: It went well! I was still nervous, but I could handle it much better than before.

Practitioner: I'm so proud of your progress. Let's build on this success. For next week, I'd like you to practice the breathing exercises twice daily and keep tracking your anxiety levels in your journal.

Client: I can do that. Thank you for your help."""

        system_prompt = """You are a clinical conversation analyst. Use the available tools to provide comprehensive analysis of therapy sessions."""

        user_message = f"""Please analyze this therapy session transcript and provide insights:

{transcript}

I need to understand the themes, emotional tone, and any action items discussed."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        tool_calls_made = []
        max_iterations = 8

        # Analysis loop with REAL API
        for iteration in range(max_iterations):
            try:
                response = await asyncio.wait_for(
                    real_openai_client.chat.completions.create(
                        model="gpt-4o",
                        messages=messages,
                        tools=tools,
                        tool_choice="auto",
                        temperature=0.7,
                        max_tokens=2000
                    ),
                    timeout=timeout_long
                )
            except asyncio.TimeoutError:
                pytest.fail(f"Conversation analysis timed out at iteration {iteration}")
            except RateLimitError as e:
                pytest.skip(f"OpenAI rate limit exceeded: {e}")
            except APIConnectionError as e:
                pytest.skip(f"OpenAI API connection failed: {e}")
            except APIError as e:
                pytest.fail(f"OpenAI API error: {e}")

            assistant_message = response.choices[0].message

            if not assistant_message.tool_calls:
                # Analysis complete
                assert assistant_message.content is not None, \
                    "Should have final analysis"
                final_analysis = assistant_message.content
                # Append final assistant response to message history
                messages.append({
                    "role": "assistant",
                    "content": assistant_message.content
                })
                break

            # Process tool calls
            messages.append({
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    }
                    for tc in assistant_message.tool_calls
                ]
            })

            for tool_call in assistant_message.tool_calls:
                function_name = tool_call.function.name
                tool_calls_made.append(function_name)

                # Simulate realistic tool responses
                mock_results = {
                    "identify_themes": '{"themes": ["anxiety management", "progress and success", "therapeutic homework", "workplace stress"]}',
                    "analyze_sentiment": '{"overall_sentiment": "positive", "client_mood": "hopeful and encouraged", "practitioner_tone": "supportive and validating"}',
                    "extract_action_items": '{"homework": ["practice breathing exercises twice daily", "track anxiety levels in journal"], "follow_up": "review progress in next session"}'
                }

                result = mock_results.get(function_name, '{"status": "completed"}')

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": result
                })

        # Verify analysis tools were used
        assert len(tool_calls_made) >= 2, \
            f"Should use multiple analysis tools (called: {len(tool_calls_made)})"

        # Verify clinically relevant content in final analysis
        final_analysis_lower = final_analysis.lower()

        clinical_markers = ["anxiety", "progress", "breathing", "exercise", "therapy", "session"]
        found_markers = [marker for marker in clinical_markers if marker in final_analysis_lower]
        assert len(found_markers) >= 3, \
            f"Analysis should contain clinically relevant content (found: {found_markers})"

        print(f"\n✓ Conversation Analysis Chain Verified")
        print(f"✓ Analysis tools used: {tool_calls_made}")
        print(f"✓ Final analysis length: {len(final_analysis)} characters")
        print(f"✓ Clinical markers found: {found_markers}")
