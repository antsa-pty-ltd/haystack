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
        """Create a simplified tool-enabled pipeline for iterative execution"""
        # Single pipeline that we'll run iteratively for tool chaining
        multi_pipeline = Pipeline()
        
        # Chat generator with tool support
        multi_pipeline.add_component("generator", OpenAIChatGenerator(
            model="gpt-4o-mini",
            api_key=Secret.from_token(settings.openai_api_key),
        ))
        
        # Tool invoker for when tools are called
        multi_pipeline.add_component("tool_invoker", ToolInvoker(
            tools=self._convert_tools_to_haystack(),
            raise_on_failure=False
        ))
        
        # Simple routing: if generator has tool calls, invoke them
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
                "output_name": "no_tool_calls",
                "output_type": List[ChatMessage],
            },
        ]
        
        multi_pipeline.add_component("router", ConditionalRouter(routes, unsafe=True))
        
        # Connect components
        multi_pipeline.connect("generator.replies", "router")
        multi_pipeline.connect("router.has_tool_calls", "tool_invoker")
        
        self.pipelines["multi_tool"] = multi_pipeline
        logger.info("Created simplified multi-tool pipeline")
    
    def _get_openai_tools(self) -> List[Dict[str, Any]]:
        """Get OpenAI function definitions from tool manager"""
        # Get tools from persona manager for WEB_ASSISTANT persona
        from personas import persona_manager
        persona_config = persona_manager.get_persona(PersonaType.WEB_ASSISTANT)
        return persona_config.tools if persona_config.tools else []

    def _convert_tools_to_haystack(self) -> List[Tool]:
        """Convert tool_manager tools into Haystack Tool objects with proper async handling."""
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
                        import asyncio
                        import concurrent.futures
                        import json
                        try:
                            # Simple approach: always use thread pool to avoid event loop issues
                            with concurrent.futures.ThreadPoolExecutor() as executor:
                                future = executor.submit(
                                    lambda: asyncio.run(tool_manager.execute_tool(tool_name, kwargs))
                                )
                                result = future.result(timeout=30)
                                
                                # CRITICAL: Haystack ToolInvoker expects the tool function to return a string
                                # that will be used as the ChatMessage content. We need to return JSON string.
                                if isinstance(result, dict):
                                    return json.dumps(result, ensure_ascii=False)
                                else:
                                    return str(result)
                        except Exception as e:
                            logger.error(f"Tool execution error for {tool_name}: {e}")
                            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
                    return _sync_tool

                haystack_tools.append(
                    Tool(
                        name=tool_name,
                        description=description,
                        parameters=parameters,
                        function=_make_sync(tool_name),
                    )
                )
                logger.debug(f"Converted tool {tool_name} to Haystack format")
        except Exception as e:
            logger.warning(f"Failed to convert tools to Haystack format: {e}")

        return haystack_tools
    
    def _convert_to_haystack_messages(self, messages: List[Any], system_prompt: str) -> List[ChatMessage]:
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
            elif role == 'system':
                # Skip additional system messages to avoid conflicts
                continue
        
        return haystack_messages
    
    def _extract_text_from_message(self, message: Any) -> Optional[str]:
        """Best-effort extraction of text from a Haystack ChatMessage."""
        try:
            # 1) Direct string content
            if hasattr(message, "content"):
                content = getattr(message, "content")
                if isinstance(content, str):
                    text = content.strip()
                    return text if text else None

            # 2) content as list of blocks
            if hasattr(message, "content") and isinstance(getattr(message, "content"), list):
                parts = []
                for block in getattr(message, "content"):
                    if hasattr(block, "text") and isinstance(block.text, str):
                        parts.append(block.text)
                    elif isinstance(block, str):
                        parts.append(block)
                joined = "\n".join([p for p in parts if isinstance(p, str) and p.strip()])
                return joined.strip() if joined else None

            # 3) private _content list (Haystack ToolCallResult handling)
            if hasattr(message, "_content"):
                _content = getattr(message, "_content")
                if isinstance(_content, list):
                    parts = []
                    for block in _content:
                        # Handle ToolCallResult objects from Haystack
                        if hasattr(block, "result") and isinstance(block.result, str):
                            return block.result  # This is the JSON string we need
                        elif hasattr(block, "text") and isinstance(block.text, str):
                            parts.append(block.text)
                        elif isinstance(block, str):
                            parts.append(block)
                    
                    # If we found text parts, join them
                    if parts:
                        joined = "\n".join([p for p in parts if isinstance(p, str) and p.strip()])
                        return joined.strip() if joined else None

            # 4) direct .text attribute
            if hasattr(message, "text"):
                text_attr = getattr(message, "text")
                if isinstance(text_attr, str):
                    text = text_attr.strip()
                    return text if text else None
                        
        except Exception as e:
            logger.warning(f"Error extracting text from message: {e}")
        return None

    def _collect_ui_actions(self, pipeline_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract UI actions from pipeline results"""
        ui_actions = []
        
        # Check tool invoker results for UI actions
        if "tool_invoker" in pipeline_result:
            tool_results = pipeline_result["tool_invoker"].get("tool_messages", [])
            for i, tool_msg in enumerate(tool_results):
                # Use the existing _extract_text_from_message method to get content from Haystack ChatMessage
                content_text = self._extract_text_from_message(tool_msg)
                
                if content_text:
                    try:
                        content = json.loads(content_text)
                        
                        if isinstance(content, dict):
                            # Check for ui_action directly in content
                            ui_action_data = content.get("ui_action")
                            
                            # Also check for ui_action nested in result (from tool_manager wrapper)
                            if not ui_action_data and content.get("result") and isinstance(content["result"], dict):
                                ui_action_data = content["result"].get("ui_action")
                            
                            if ui_action_data:
                                if isinstance(ui_action_data, list):
                                    ui_actions.extend(ui_action_data)
                                else:
                                    ui_actions.append(ui_action_data)
                    except (json.JSONDecodeError, AttributeError) as e:
                        logger.warning(f"Error parsing tool message {i}: {e}")
                        continue
                # No need to log when content_text is None - this is expected for non-tool messages
        return ui_actions
    
    async def _update_session_context_from_tools(self, session_id: str, tool_messages: List[Any]) -> None:
        """Update session context based on tool execution results"""
        try:
            for tool_msg in tool_messages:
                if not hasattr(tool_msg, 'content'):
                    continue
                    
                try:
                    content = json.loads(tool_msg.content) if isinstance(tool_msg.content, str) else tool_msg.content
                    if not isinstance(content, dict):
                        continue
                    
                    # Extract context updates based on tool results
                    if content.get("template_name"):
                        await session_manager.update_session_context(session_id, {
                            "last_selected_template": content["template_name"]
                        })
                    
                    if content.get("loaded_sessions"):
                        await session_manager.update_session_context(session_id, {
                            "last_loaded_sessions": content["loaded_sessions"]
                        })
                    
                    if content.get("documents") or content.get("generated_documents"):
                        documents = content.get("documents") or content.get("generated_documents")
                        await session_manager.update_session_context(session_id, {
                            "last_generated_documents": documents
                        })
                        
                except (json.JSONDecodeError, AttributeError):
                    continue
                    
        except Exception as e:
            logger.warning(f"Failed to update session context from tools: {e}")
    
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
        Generate response using Haystack pipeline for proper agent behavior with tool chaining
        """
        try:
            # Initialize pipeline if needed
            if not self._initialized:
                await self.initialize()
            
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
            
            # Add context memory for session continuity
            enhanced_system_prompt = system_prompt
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
                    enhanced_system_prompt += f"\n\n[Session Context] {' | '.join(memory_parts)}"
            except Exception:
                pass

            # Convert to Haystack messages
            haystack_messages = self._convert_to_haystack_messages(messages, enhanced_system_prompt)
            
            # Get the appropriate pipeline
            pipeline = self.pipelines.get(pipeline_type, self.pipelines.get("multi_tool"))
            if not pipeline:
                logger.error(f"Pipeline {pipeline_type} not found, falling back to basic pipeline")
                pipeline = self.pipelines.get("basic")
            
            if not pipeline:
                raise Exception("No pipelines available")
            
            logger.info(f"🤖 Using Haystack pipeline: {pipeline_type}")
            
            # Initialize response tracking
            full_response = ""
            self._ui_actions = []  # Reset UI actions for this run
            
            # Doc-aligned agent loop: OpenAIChatGenerator + ToolInvoker
            max_iterations = 4
            current_messages = haystack_messages.copy()
            
            # Prepare Haystack tools and components
            haystack_tools = self._convert_tools_to_haystack()
            chat_generator = OpenAIChatGenerator(
                model=persona_config.model,
                tools=haystack_tools
            ) if haystack_tools else OpenAIChatGenerator(model=persona_config.model)
            tool_invoker = ToolInvoker(tools=haystack_tools) if haystack_tools else ToolInvoker(tools=[])

            for iteration in range(max_iterations):
                logger.info(f"🔄 Agent loop iteration {iteration + 1}/{max_iterations}")
                try:
                    gen_out = chat_generator.run(messages=current_messages)
                    replies = gen_out.get("replies") or []
                    if not replies:
                        logger.warning("Generator returned no replies")
                        break

                    # If tool calls are present, execute tools and continue
                    if getattr(replies[0], "tool_calls", None):
                        if persona_type == PersonaType.WEB_ASSISTANT:
                            msg = f"\n\n[tools] Detected {len(replies[0].tool_calls)} tool call(s)...\n\n"
                            full_response += msg
                            yield msg

                        # Execute tools
                        inv_out = tool_invoker.run(messages=replies)
                        tool_messages = inv_out.get("tool_messages") or []
                        

                        # Collect UI actions if any
                        try:
                            fake_pipeline_result = {"tool_invoker": {"tool_messages": tool_messages}}
                            ui_actions = self._collect_ui_actions(fake_pipeline_result)
                            if ui_actions:
                                if not hasattr(self, '_ui_actions'):
                                    self._ui_actions = []
                                self._ui_actions.extend(ui_actions)
                                if persona_type == PersonaType.WEB_ASSISTANT:
                                    ui_msg = f"\n[ui] Found {len(ui_actions)} UI action(s)\n"
                                    full_response += ui_msg
                                    yield ui_msg
                        except Exception as e:
                            logger.error(f"Error collecting UI actions: {e}")

                        # Update session context based on tool results
                        await self._update_session_context_from_tools(session_id, tool_messages)

                        # Add replies and tool messages back to the conversation and iterate again
                        current_messages.extend(replies)
                        current_messages.extend(tool_messages)
                        if persona_type == PersonaType.WEB_ASSISTANT:
                            done_msg = f"\n[tools] Completed tool execution\n\n"
                            full_response += done_msg
                            yield done_msg
                        continue

                    # No tools requested: stream final reply
                    final_message = replies[-1]
                    content = self._extract_text_from_message(final_message)
                    if content:
                        for i, word in enumerate(content.split(" ")):
                            chunk = word if i == 0 else f" {word}"
                            full_response += chunk
                            yield chunk
                            await asyncio.sleep(0.01)
                    break
                except Exception as e:
                    logger.error(f"Error in agent loop iteration {iteration + 1}: {e}")
                    error_msg = f"\n\n[error] Agent loop failed: {str(e)}"
                    full_response += error_msg
                    yield error_msg
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
