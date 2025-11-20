"""
Haystack-based Pipeline Manager using Declarative Pipeline Architecture
Following official Haystack recommendations with automatic agent loops
"""
import asyncio
import json
import logging
from typing import Dict, List, Optional, Any, AsyncGenerator, Callable
from datetime import datetime

# Haystack imports
from haystack import Pipeline
from haystack.components.routers import ConditionalRouter
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.components.tools import ToolInvoker
from haystack.dataclasses import ChatMessage, ChatRole, StreamingChunk
from haystack.utils import Secret

from config import settings
from personas import PersonaType, persona_manager
from session_manager import session_manager
from tools import tool_manager
from components.ui_actions import UIActionCollector, MessageCollector

logger = logging.getLogger(__name__)


class HaystackPipelineManager:
    """
    Declarative Pipeline Manager using Haystack's official Pipeline architecture.
    
    This implementation follows Haystack's recommended pattern:
    - Declarative pipeline construction with components and connections
    - Automatic agent loop iteration (no manual while loops)
    - Proper streaming support via callbacks
    - Persona-specific pipelines for different use cases
    """
    
    def __init__(self):
        self.pipelines: Dict[PersonaType, Pipeline] = {}
        self._initialized = False
        self._streaming_callback: Optional[Callable] = None
        self._ui_actions: List[Dict[str, Any]] = []
    
    async def initialize(self):
        """Initialize Haystack pipelines for different personas"""
        if self._initialized:
            return
        
        try:
            # Create persona-specific pipelines
            self._create_web_assistant_pipeline()
            self._create_jaimee_therapist_pipeline()
            self._create_transcriber_agent_pipeline()
            
            self._initialized = True
            logger.info("✅ Haystack declarative pipelines initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Haystack pipelines: {e}")
            raise
    
    def _create_web_assistant_pipeline(self):
        """
        Create WEB_ASSISTANT pipeline with multi-tool support and UI actions.
        
        This is a declarative pipeline that automatically handles tool calling loops:
        - Generator creates responses and tool calls
        - Router checks if tools were called
        - ToolInvoker executes tools
        - UIActionCollector extracts UI actions
        - MessageCollector accumulates messages
        - Loop continues until no more tool calls
        """
        persona_config = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)
        tools = tool_manager.get_haystack_component_tools("web_assistant")
        
        # Define routing conditions
        routes = [
            {
                "condition": "{{replies and replies[0].tool_calls | length > 0}}",
                "output": "{{replies}}",
                "output_name": "has_tool_calls",
                "output_type": List[ChatMessage],
            },
            {
                "condition": "{{not replies or replies[0].tool_calls | length == 0}}",
                "output": "{{replies}}",
                "output_name": "final_response",
                "output_type": List[ChatMessage],
            },
        ]
        
        # Create the pipeline
        pipeline = Pipeline(max_runs_per_component=25)  # High limit for complex workflows
        
        # Add components
        pipeline.add_component("message_collector", MessageCollector())
        pipeline.add_component("generator", OpenAIChatGenerator(
            model=persona_config.model,
            api_key=Secret.from_token(settings.openai_api_key),
            tools=tools,  # Pass tools to the generator so it knows what's available
            generation_kwargs={
                "temperature": persona_config.temperature,
                "max_tokens": persona_config.max_tokens
            }
        ))
        pipeline.add_component("router", ConditionalRouter(routes, unsafe=True))
        pipeline.add_component("tool_invoker", ToolInvoker(tools=tools, raise_on_failure=False))
        pipeline.add_component("ui_collector", UIActionCollector())
        
        # Connect components - Haystack automatically loops
        pipeline.connect("generator.replies", "router")
        pipeline.connect("router.has_tool_calls", "tool_invoker")
        pipeline.connect("tool_invoker.tool_messages", "ui_collector")
        pipeline.connect("ui_collector.messages", "message_collector")
        pipeline.connect("message_collector", "generator.messages")
        
        self.pipelines[PersonaType.WEB_ASSISTANT] = pipeline
        logger.info("✅ Created WEB_ASSISTANT declarative pipeline with auto-loop")
    
    def _create_jaimee_therapist_pipeline(self):
        """
        Create JAIMEE_THERAPIST pipeline with therapeutic tools.
        
        Similar to web_assistant but:
        - Fewer tools (mood check-in, coping strategies, breathing exercises)
        - No UI actions needed
        - More empathetic tone (higher temperature)
        """
        persona_config = persona_manager.get_persona(PersonaType.JAIMEE_THERAPIST)
        tools = tool_manager.get_haystack_component_tools("jaimee_therapist")
        
        routes = [
            {
                "condition": "{{replies and replies[0].tool_calls | length > 0}}",
                "output": "{{replies}}",
                "output_name": "has_tool_calls",
                "output_type": List[ChatMessage],
            },
            {
                "condition": "{{not replies or replies[0].tool_calls | length == 0}}",
                "output": "{{replies}}",
                "output_name": "final_response",
                "output_type": List[ChatMessage],
            },
        ]
        
        pipeline = Pipeline(max_runs_per_component=15)  # Fewer iterations needed
        
        pipeline.add_component("message_collector", MessageCollector())
        pipeline.add_component("generator", OpenAIChatGenerator(
            model=persona_config.model,
            api_key=Secret.from_token(settings.openai_api_key),
            tools=tools,  # Pass tools to the generator so it knows what's available
            generation_kwargs={
                "temperature": persona_config.temperature,
                "max_tokens": persona_config.max_tokens
            }
        ))
        pipeline.add_component("router", ConditionalRouter(routes, unsafe=True))
        pipeline.add_component("tool_invoker", ToolInvoker(tools=tools, raise_on_failure=False))
        
        # Connections - simpler than web_assistant (no UI collector)
        pipeline.connect("generator.replies", "router")
        pipeline.connect("router.has_tool_calls", "tool_invoker")
        pipeline.connect("tool_invoker.tool_messages", "message_collector")
        pipeline.connect("message_collector", "generator.messages")
        
        self.pipelines[PersonaType.JAIMEE_THERAPIST] = pipeline
        logger.info("✅ Created JAIMEE_THERAPIST declarative pipeline")
    
    def _create_transcriber_agent_pipeline(self):
        """
        Create TRANSCRIBER_AGENT pipeline for document generation.
        
        Minimal pipeline with just document generation tools.
        """
        persona_config = persona_manager.get_persona(PersonaType.TRANSCRIBER_AGENT)
        tools = tool_manager.get_haystack_component_tools("transcriber_agent")
        
        routes = [
            {
                "condition": "{{replies and replies[0].tool_calls | length > 0}}",
                "output": "{{replies}}",
                "output_name": "has_tool_calls",
                "output_type": List[ChatMessage],
            },
            {
                "condition": "{{not replies or replies[0].tool_calls | length == 0}}",
                "output": "{{replies}}",
                "output_name": "final_response",
                "output_type": List[ChatMessage],
            },
        ]
        
        pipeline = Pipeline(max_runs_per_component=10)
        
        pipeline.add_component("message_collector", MessageCollector())
        pipeline.add_component("generator", OpenAIChatGenerator(
            model=persona_config.model,
            api_key=Secret.from_token(settings.openai_api_key),
            tools=tools,  # Pass tools to the generator so it knows what's available
            generation_kwargs={
                "temperature": persona_config.temperature,
                "max_tokens": persona_config.max_tokens
            }
        ))
        pipeline.add_component("router", ConditionalRouter(routes, unsafe=True))
        pipeline.add_component("tool_invoker", ToolInvoker(tools=tools, raise_on_failure=False))
        pipeline.add_component("ui_collector", UIActionCollector())
        
        pipeline.connect("generator.replies", "router")
        pipeline.connect("router.has_tool_calls", "tool_invoker")
        pipeline.connect("tool_invoker.tool_messages", "ui_collector")
        pipeline.connect("ui_collector.messages", "message_collector")
        pipeline.connect("message_collector", "generator.messages")
        
        self.pipelines[PersonaType.TRANSCRIBER_AGENT] = pipeline
        logger.info("✅ Created TRANSCRIBER_AGENT declarative pipeline")
    
    def _convert_to_haystack_messages(
        self, 
        messages: List[Any], 
        system_prompt: str
    ) -> List[ChatMessage]:
        """Convert session messages to Haystack ChatMessage format"""
        haystack_messages = []
        
        # Add system message first
        if system_prompt:
            haystack_messages.append(ChatMessage.from_system(system_prompt))
        
        # Convert conversation history
        for msg in messages:
            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                role = msg.role
                content = msg.content
            elif isinstance(msg, dict):
                role = msg.get('role', 'user')
                content = msg.get('content', '')
            else:
                continue
                
            if role == 'user':
                haystack_messages.append(ChatMessage.from_user(content))
            elif role == 'assistant':
                haystack_messages.append(ChatMessage.from_assistant(content))
            # Skip system messages to avoid conflicts
        
        return haystack_messages
    
    def _extract_text_from_message(self, message: ChatMessage) -> Optional[str]:
        """Extract text content from Haystack ChatMessage"""
        try:
            if hasattr(message, "content"):
                content = message.content
                if isinstance(content, str):
                    return content.strip() if content else None
            
            if hasattr(message, "text"):
                text = message.text
                if isinstance(text, str):
                    return text.strip() if text else None
        except Exception as e:
            logger.debug(f"Error extracting text from message: {e}")
        
        return None
    
    async def generate_response_with_chaining(
        self,
        session_id: str,
        persona_type: PersonaType,
        user_message: str,
        context: Optional[Dict[str, Any]] = None,
        auth_token: Optional[str] = None,
        pipeline_type: str = "multi_tool"  # For backwards compatibility
    ) -> AsyncGenerator[str, None]:
        """
        Generate response using Haystack's declarative pipeline.
        
        This method:
        1. Prepares messages and context
        2. Runs the pipeline (which automatically handles tool loops)
        3. Streams the response in real-time
        4. Collects UI actions for frontend
        """
        try:
            if not self._initialized:
                await self.initialize()
            
            # Get or create session
            session = await session_manager.get_session(session_id)
            if not session:
                logger.info(f"Session {session_id} not found, creating replacement")
                profile_id = context.get('profile_id') or context.get('profileId') if context else None
                await session_manager.create_session(
                    persona_type=persona_type.value,
                    context=context or {},
                    auth_token=auth_token,
                    profile_id=profile_id,
                    session_id=session_id
                )
                session = await session_manager.get_session(session_id)
            
            # Add user message
            await session_manager.add_message(session_id, "user", user_message)
            messages = await session_manager.get_messages(session_id, limit=40)
            
            # Get persona config and system prompt
            persona_config = persona_manager.get_persona(persona_type)
            system_prompt = persona_manager.get_system_prompt(persona_type, context or session.context)
            
            # Set auth token for tool manager
            if auth_token:
                tool_manager.set_auth_token(auth_token, session.profile_id)
            elif session.auth_token:
                tool_manager.set_auth_token(session.auth_token, session.profile_id)
            
            # Set page context if available
            if context and (context.get('page_context') or context.get('page_url')):
                page_type = context.get('page_context', 'unknown')
                page_context = {
                    'page_type': page_type,
                    'page_display_name': page_type.replace('_', ' ').title(),
                    'page_url': context.get('page_url', ''),
                    'capabilities': context.get('ui_capabilities', []),
                    'client_id': context.get('client_id'),
                    'active_tab': context.get('active_tab')
                }
                tool_manager.set_page_context(page_context)
            
            # Convert to Haystack messages
            haystack_messages = self._convert_to_haystack_messages(messages, system_prompt)
            
            # Get the appropriate pipeline
            pipeline = self.pipelines.get(persona_type)
            if not pipeline:
                logger.error(f"No pipeline found for {persona_type}")
                raise Exception(f"Pipeline not available for {persona_type}")
            
            logger.info(f"🤖 Running Haystack declarative pipeline for {persona_type.value}")
            
            # Reset UI actions for this run
            self._ui_actions = []
            
            # Run the pipeline - Haystack handles the loop automatically
            # We'll use a custom approach to enable streaming
            full_response = ""
            
            # Since Pipeline.run() doesn't support streaming well, we manually iterate
            # but let Haystack handle tool invocation logic
            current_messages = haystack_messages.copy()
            message_collector = pipeline.get_component("message_collector")
            generator = pipeline.get_component("generator")
            router = pipeline.get_component("router")
            tool_invoker = pipeline.get_component("tool_invoker")
            ui_collector = pipeline.get_component("ui_collector") if "ui_collector" in pipeline.graph.nodes else None
            
            max_iterations = 25
            for iteration in range(max_iterations):
                logger.info(f"🔄 Pipeline iteration {iteration + 1}/{max_iterations}")
                
                # Generate response
                gen_result = generator.run(messages=current_messages)
                replies = gen_result.get("replies", [])
                
                if not replies:
                    break
                
                # Route based on tool calls
                router_result = router.run(replies=replies)
                
                # Check if we have tool calls
                if "has_tool_calls" in router_result:
                    # Execute tools
                    if persona_type == PersonaType.WEB_ASSISTANT:
                        tool_msg = f"\n\n[tools] Executing {len(replies[0].tool_calls)} tool call(s)...\n\n"
                        full_response += tool_msg
                        yield tool_msg
                    
                    tool_result = tool_invoker.run(messages=replies)
                    tool_messages = tool_result.get("tool_messages", [])
                    
                    # Collect UI actions if component exists
                    if ui_collector:
                        ui_result = ui_collector.run(messages=tool_messages)
                        self._ui_actions.extend(ui_result.get("ui_actions", []))
                    
                    # Add to message history
                    current_messages.extend(replies)
                    current_messages.extend(tool_messages)
                    
                    if persona_type == PersonaType.WEB_ASSISTANT:
                        done_msg = f"[tools] Completed\n\n"
                        full_response += done_msg
                        yield done_msg
                    
                    continue
                
                # Final response - stream it
                final_message = replies[-1]
                content = self._extract_text_from_message(final_message)
                
                if content:
                    # Stream word by word for better UX
                    words = content.split(" ")
                    for i, word in enumerate(words):
                        chunk = word if i == 0 else f" {word}"
                        full_response += chunk
                        yield chunk
                        await asyncio.sleep(0.01)
                
                break
            
            # Save assistant message
            if full_response.strip():
                await session_manager.add_message(session_id, "assistant", full_response)
            
        except Exception as e:
            logger.error(f"Error in pipeline response generation: {e}")
            error_msg = "I apologize, but I encountered an error. Please try again."
            await session_manager.add_message(session_id, "assistant", error_msg)
            yield error_msg
    
    def pop_ui_actions(self) -> List[Dict[str, Any]]:
        """Return and clear accumulated UI actions"""
        actions = self._ui_actions.copy()
        self._ui_actions = []
        return actions
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for pipelines"""
        return {
            "initialized": self._initialized,
            "available_pipelines": [p.value for p in self.pipelines.keys()],
            "pipeline_count": len(self.pipelines),
            "architecture": "declarative",
            "features": [
                "automatic_tool_loops",
                "persona_specific_pipelines",
                "ui_action_collection",
                "streaming_support"
            ]
        }


# Global pipeline manager instance
haystack_pipeline_manager = HaystackPipelineManager()
