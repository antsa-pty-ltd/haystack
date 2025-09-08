"""
Haystack-based pipeline for multi-tool chaining
Following official Haystack recommendations for agent workflows
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
from haystack.dataclasses import ChatMessage, ChatRole
from haystack.tools import Tool
from haystack.utils import Secret

from config import settings
from personas import PersonaType, persona_manager
from session_manager import session_manager
from tools import tool_manager

logger = logging.getLogger(__name__)

class HaystackPipelineManager:
    """
    Advanced pipeline manager using Haystack's official Pipeline architecture
    for multi-tool chaining and agentic workflows
    """
    
    def __init__(self):
        self.pipelines: Dict[str, Pipeline] = {}
        self._initialized = False
    
    async def initialize(self):
        """Initialize Haystack pipelines for different workflows"""
        if self._initialized:
            return
        
        try:
            # Create different pipeline types
            self._create_basic_pipeline()
            self._create_multi_tool_pipeline()
            # Skip evaluator_optimizer for now - too complex for initial implementation
            # self._create_evaluator_optimizer_pipeline()
            
            self._initialized = True
            logger.info("✅ Haystack pipelines initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Haystack pipelines: {e}")
            raise
    
    def _create_basic_pipeline(self):
        """Create a basic pipeline for single-tool workflows"""
        # Define conditional routes for tool handling
        routes = [
            {
                "condition": "{{replies[0].tool_calls | length > 0}}",
                "output": "{{replies}}",
                "output_name": "tool_calls_present",
                "output_type": List[ChatMessage],
            },
            {
                "condition": "{{replies[0].tool_calls | length == 0}}",
                "output": "{{replies}}",
                "output_name": "final_response",
                "output_type": List[ChatMessage],
            },
        ]
        
        # Create pipeline
        basic_pipeline = Pipeline()
        basic_pipeline.add_component("generator", OpenAIChatGenerator(
            model="gpt-4o-mini",
            api_key=Secret.from_token(settings.openai_api_key)
        ))
        basic_pipeline.add_component("router", ConditionalRouter(routes, unsafe=True))
        basic_pipeline.add_component("tool_invoker", ToolInvoker(
            tools=self._convert_tools_to_haystack(),
            raise_on_failure=False
        ))
        
        # Connect components
        basic_pipeline.connect("generator.replies", "router")
        basic_pipeline.connect("router.tool_calls_present", "tool_invoker")
        
        self.pipelines["basic"] = basic_pipeline
    
    def _create_multi_tool_pipeline(self):
        """Create a simplified multi-tool pipeline"""
        # For now, use the basic pipeline approach but allow multiple iterations
        # This is simpler and more reliable than complex routing
        routes = [
            {
                "condition": "{{replies[0].tool_calls | length > 0}}",
                "output": "{{replies}}",
                "output_name": "tool_calls_present",
                "output_type": List[ChatMessage],
            },
            {
                "condition": "{{replies[0].tool_calls | length == 0}}",
                "output": "{{replies}}",
                "output_name": "final_response",
                "output_type": List[ChatMessage],
            },
        ]
        
        multi_pipeline = Pipeline()
        multi_pipeline.add_component("generator", OpenAIChatGenerator(
            model="gpt-4o-mini",
            api_key=Secret.from_token(settings.openai_api_key)
        ))
        multi_pipeline.add_component("router", ConditionalRouter(routes, unsafe=True))
        multi_pipeline.add_component("tool_invoker", ToolInvoker(
            tools=self._convert_tools_to_haystack(),
            raise_on_failure=False
        ))
        
        # Simple connection: generator -> router -> tool_invoker
        multi_pipeline.connect("generator.replies", "router")
        multi_pipeline.connect("router.tool_calls_present", "tool_invoker")
        
        self.pipelines["multi_tool"] = multi_pipeline
    
    def _get_openai_tools(self) -> List[Dict[str, Any]]:
        """Get OpenAI function definitions from tool manager"""
        # Get tools from persona manager for WEB_ASSISTANT persona
        from personas import persona_manager
        persona_config = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)
        return persona_config.tools if persona_config.tools else []

    def _convert_tools_to_haystack(self) -> List[Tool]:
        """Convert tool_manager tools into Haystack Tool objects (sync wrappers)."""
        haystack_tools: List[Tool] = []

        try:
            # Limit exposed tools to those declared on the WEB_ASSISTANT persona
            allowed_tools: List[str] = []
            try:
                allowed_tools = [t.get("function", {}).get("name") for t in (self._get_openai_tools() or [])]
                allowed_tools = [t for t in allowed_tools if isinstance(t, str)]
            except Exception:
                allowed_tools = []

            for tool_name, tool_cfg in getattr(tool_manager, "tools", {}).items():
                if allowed_tools and tool_name not in allowed_tools:
                    continue

                try:
                    description = tool_cfg["definition"]["function"].get("description", tool_name)
                    parameters = tool_cfg["definition"]["function"].get("parameters", {})
                except Exception:
                    description = tool_name
                    parameters = {}

                def _make_sync(tool_name: str):
                    def _sync_tool(**kwargs):
                        import asyncio as _asyncio
                        try:
                            return _asyncio.run(tool_manager.execute_tool(tool_name, kwargs))
                        except RuntimeError:
                            # If we're already in an event loop, run in a new thread loop
                            return _asyncio.get_event_loop().run_until_complete(tool_manager.execute_tool(tool_name, kwargs))
                        except Exception as e:
                            return {"success": False, "error": str(e)}
                    return _sync_tool

                haystack_tools.append(
                    Tool(
                        name=tool_name,
                        description=description,
                        parameters=parameters,
                        function=_make_sync(tool_name),
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to convert tools to Haystack format: {e}")

        return haystack_tools
    
    async def generate_response_with_chaining(
        self,
        session_id: str,
        persona_type: PersonaType,
        user_message: str,
        context: Optional[Dict[str, Any]] = None,
        auth_token: Optional[str] = None,
        pipeline_type: str = "multi_tool"
    ) -> AsyncGenerator[str, None]:
        """
        Generate response using Haystack for chat generation with manual tool chaining
        """
        try:
            # Get session and prepare messages
            session = await session_manager.get_session(session_id)
            if not session:
                # Session not found - create a new one instead of failing
                logger.info(f"Session {session_id} not found, creating replacement session with same ID")
                
                # Extract profile_id from context if available
                profile_id = None
                if context:
                    profile_id = context.get('profile_id') or context.get('profileId')
                
                # Create a new session with the SAME session_id to maintain frontend consistency
                recovered_session_id = await session_manager.create_session(
                    persona_type=persona_type.value,
                    context=context or {},
                    auth_token=auth_token,
                    profile_id=profile_id,
                    session_id=session_id  # Use original session_id, not a new UUID
                )
                
                logger.info(f"Created replacement session {recovered_session_id} (should match original {session_id})")
                
                # Get the newly created session
                session = await session_manager.get_session(session_id)
            
            # Add user message to session
            await session_manager.add_message(session_id, "user", user_message)
            
            # Get conversation history
            messages = await session_manager.get_messages(session_id, limit=20)
            
            # Get persona config and system prompt
            persona_config = persona_manager.get_persona(persona_type)
            system_prompt = persona_manager.get_system_prompt(
                persona_type, 
                context or session.context
            )
            
            # Set auth token for tool manager
            if auth_token:
                tool_manager.set_auth_token(auth_token, session.profile_id)
            elif session.auth_token:
                tool_manager.set_auth_token(session.auth_token, session.profile_id)
            
            # Set page context for tool manager if available
            if context and (context.get('page_context') or context.get('page_url')):
                page_type = context.get('page_context', 'unknown')
                page_name_map = {
                    'dashboard': 'Dashboard',
                    'clients_list': 'Clients',
                    'client_details': 'Client Details', 
                    'messages_page': 'Messages',
                    'homework_page': 'Homework',
                    'files_page': 'Files',
                    'profile_page': 'Profile',
                    'practitioners_page': 'Practitioners',
                    'transcribe_page': 'Live Transcribe',
                    'session_viewer': 'Session Viewer',
                    'sessions_list': 'Sessions',
                    'settings': 'Settings',
                    'reports': 'Reports',
                    'unknown': 'Unknown Page'
                }
                page_display_name = page_name_map.get(page_type, page_type.replace('_', ' ').title())
                
                page_context = {
                    'page_type': page_type,
                    'page_display_name': page_display_name,
                    'page_url': context.get('page_url', ''),
                    'capabilities': context.get('ui_capabilities', []),
                    'client_id': context.get('client_id'),
                    'active_tab': context.get('active_tab')
                }
                tool_manager.set_page_context(page_context)
                logger.info(f"📄 Haystack Pipeline: Set page context - {page_display_name} ({page_type})")
            
            # Build OpenAI messages for streaming with tool support
            from openai import AsyncOpenAI
            openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

            openai_messages = [{"role": "system", "content": system_prompt}]
            for msg in messages[:-1]:
                openai_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
            openai_messages.append({"role": "user", "content": user_message})

            # Inject lightweight internal context memory to help resolve pronouns like "them" or "those"
            try:
                sess_ctx = session.context or {}
                memory_parts: List[str] = []
                sel_t = sess_ctx.get("last_selected_template")
                if isinstance(sel_t, str) and sel_t:
                    memory_parts.append(f"Selected template: {sel_t}")
                loaded = sess_ctx.get("last_loaded_sessions")
                if isinstance(loaded, list) and len(loaded) > 0:
                    try:
                        labels = [s.get('label') or s.get('title') or s.get('session_id') for s in loaded]
                        labels = [str(x) for x in labels if x]
                        if labels:
                            memory_parts.append("Loaded sessions: " + ", ".join(labels[:6]) + ("…" if len(labels) > 6 else ""))
                    except Exception:
                        pass
                docs = sess_ctx.get("last_generated_documents")
                if isinstance(docs, list) and len(docs) > 0:
                    try:
                        titles = [d.get('title') or d.get('name') or d.get('document_id') for d in docs]
                        titles = [str(t) for t in titles if t]
                        if titles:
                            memory_parts.append("Generated documents: " + ", ".join(titles[:6]) + ("…" if len(titles) > 6 else ""))
                    except Exception:
                        pass
                if memory_parts:
                    openai_messages.append({"role": "assistant", "content": "[Internal Context] " + " | ".join(memory_parts)})
            except Exception:
                pass

            # Stream with tool-use support; yield chunks as they arrive
            full_response = ""
            max_iterations = 6
            iterations = 0

            base_params = {
                "model": persona_config.model,
                "temperature": persona_config.temperature,
                "max_tokens": persona_config.max_tokens,
            }
            if persona_config.tools:
                base_params["tools"] = persona_config.tools
                base_params["tool_choice"] = "auto"

            while iterations < max_iterations:
                iterations += 1
                stream = await openai_client.chat.completions.create(
                    messages=openai_messages,
                    stream=True,
                    **base_params
                )

                message_content = ""
                tool_calls = []

                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        message_content += delta.content
                        yield delta.content
                    if delta.tool_calls:
                        for tool_call in delta.tool_calls:
                            if len(tool_calls) <= tool_call.index:
                                tool_calls.extend([None] * (tool_call.index + 1 - len(tool_calls)))
                            if tool_calls[tool_call.index] is None:
                                tool_calls[tool_call.index] = {
                                    "id": tool_call.id,
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""}
                                }
                            if tool_call.function.name:
                                tool_calls[tool_call.index]["function"]["name"] = tool_call.function.name
                            if tool_call.function.arguments:
                                tool_calls[tool_call.index]["function"]["arguments"] += tool_call.function.arguments

                # Create message-like object from streamed content
                class _Msg:
                    def __init__(self, content, tool_calls):
                        self.content = content
                        self.tool_calls = [type('TC', (), {
                            'id': tc["id"],
                            'function': type('FN', (), {
                                'name': tc["function"]["name"],
                                'arguments': tc["function"]["arguments"]
                            })()
                        }) for tc in (tool_calls or [])]

                message = _Msg(message_content, tool_calls if any(tool_calls) else None)

                if getattr(message, "tool_calls", None):
                    # Append assistant with tool_calls
                    openai_messages.append({
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments or "{}",
                                },
                            }
                            for tc in message.tool_calls
                        ],
                    })

                    # Execute tools and feed results back
                    for tc in message.tool_calls:
                        tool_name = tc.function.name
                        try:
                            args_text = tc.function.arguments or "{}"
                            try:
                                arguments = json.loads(args_text)
                            except Exception:
                                arguments = {}

                            if persona_type == PersonaType.WEB_ASSISTANT:
                                executing_msg = f"\n\n[tool] {tool_name} executing...\n\n"
                                full_response += executing_msg
                                yield executing_msg

                            # Inject generation_instructions from the user's last message when creating docs
                            if tool_name in {"generate_document_auto", "generate_document_from_loaded"}:
                                if isinstance(user_message, str) and not arguments.get("generation_instructions"):
                                    arguments["generation_instructions"] = user_message

                            tool_result = await tool_manager.execute_tool(tool_name, arguments)
                            result_data = tool_result.get("result") if tool_result.get("success") else None
                            has_embedded_error = isinstance(result_data, dict) and bool(result_data.get("error"))

                            if tool_result.get("success") and not has_embedded_error:
                                if isinstance(result_data, dict) and result_data.get("ui_action"):
                                    ui_action_msg = result_data.get('user_message', 'Performing UI action...')
                                    if persona_type == PersonaType.WEB_ASSISTANT:
                                        yield f"\n[ui] {ui_action_msg}\n"
                                    if not hasattr(self, '_ui_actions'):
                                        self._ui_actions = []
                                    ui_action_data = result_data["ui_action"]
                                    if isinstance(ui_action_data, list):
                                        for action in ui_action_data:
                                            self._ui_actions.append(action)
                                    else:
                                        self._ui_actions.append(ui_action_data)

                                if persona_type == PersonaType.WEB_ASSISTANT:
                                    executed_msg = f"\n[tool] {tool_name} executed - Completed successfully\n\n"
                                    full_response += executed_msg
                                    yield executed_msg

                                tool_content = json.dumps(result_data, ensure_ascii=False)
                                # Persist key tool outputs into session context for cross-turn memory
                                try:
                                    if tool_name == "select_template_by_name":
                                        selected = result_data.get("template_name") or arguments.get("template_name")
                                        if isinstance(selected, str) and selected:
                                            await session_manager.update_session_context(session_id, {"last_selected_template": selected})
                                    elif tool_name in {"load_multiple_sessions", "get_loaded_sessions"}:
                                        loaded_sessions = result_data.get("loaded_sessions") or result_data.get("sessions")
                                        if isinstance(loaded_sessions, list) and loaded_sessions:
                                            await session_manager.update_session_context(session_id, {"last_loaded_sessions": loaded_sessions})
                                    elif tool_name == "get_generated_documents":
                                        documents = result_data.get("documents") or result_data.get("generated_documents") or result_data
                                        if isinstance(documents, list) and documents:
                                            await session_manager.update_session_context(session_id, {"last_generated_documents": documents})
                                except Exception:
                                    pass
                            else:
                                embedded_error = result_data.get('error') if isinstance(result_data, dict) else None
                                error_text = tool_result.get('error') or embedded_error or 'Failed'
                                if persona_type == PersonaType.WEB_ASSISTANT:
                                    error_msg = f"\n[tool] {tool_name} executed [error] {error_text}\n\n"
                                    full_response += error_msg
                                    yield error_msg
                                tool_content = json.dumps({"error": tool_result.get("error", "Failed")}, ensure_ascii=False)

                            openai_messages.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": tool_content,
                            })
                        except Exception as e:
                            error_msg = f"\n\n[error] Tool execution error: {str(e)}"
                            full_response += error_msg
                            yield error_msg
                    continue

                # No tool calls: finalize
                if message.content:
                    full_response += message.content
                break

            # Save assistant message
            if full_response.strip():
                await session_manager.add_message(session_id, "assistant", full_response)
                    
        except Exception as e:
            logger.error(f"Error in Haystack pipeline response generation: {e}")
            error_msg = "I apologize, but I encountered an error processing your request. Please try again."
            await session_manager.add_message(session_id, "assistant", error_msg)
            yield error_msg
    
    def pop_ui_actions(self) -> List[Dict[str, Any]]:
        """Return and clear any accumulated UI actions from the last run."""
        actions: List[Dict[str, Any]] = []
        try:
            actions = getattr(self, '_ui_actions', []) or []
        except Exception:
            actions = []
        # Clear after reading to avoid repeating
        try:
            self._ui_actions = []
        except Exception:
            pass
        return actions
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for Haystack pipelines"""
        return {
            "initialized": self._initialized,
            "available_pipelines": list(self.pipelines.keys()),
            "pipeline_count": len(self.pipelines),
            "haystack_version": "2.9.0+",
            "features": [
                "multi_tool_chaining",
                "conditional_routing", 
                "evaluation_loops",
                "tool_invoker_integration"
            ]
        }

# Global Haystack pipeline manager instance
haystack_pipeline_manager = HaystackPipelineManager()
