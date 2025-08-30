import asyncio
import json
from typing import Dict, List, Optional, Any, AsyncGenerator
import logging
from datetime import datetime
from openai import AsyncOpenAI

from config import settings
from personas import PersonaType, persona_manager
from session_manager import session_manager, ChatMessage
from tools import tool_manager

logger = logging.getLogger(__name__)

class PipelineManager:
    def __init__(self):
        self.openai_client = None
        self.active_requests: Dict[str, asyncio.Task] = {}
        # Remove global semaphore bottleneck - use per-user rate limiting instead
        self.user_semaphores: Dict[str, asyncio.Semaphore] = {}
        self.max_requests_per_user = settings.max_requests_per_user
        self._initialized = False
    
    def get_user_semaphore(self, user_id: str) -> asyncio.Semaphore:
        """Get or create per-user semaphore to prevent spam from individual users"""
        if user_id not in self.user_semaphores:
            self.user_semaphores[user_id] = asyncio.Semaphore(self.max_requests_per_user)
        return self.user_semaphores[user_id]
    
    def cleanup_user_semaphores(self):
        """Clean up unused user semaphores periodically"""
        # Keep only semaphores that are currently in use
        active_users = set()
        for task_id, task in self.active_requests.items():
            if not task.done():
                user_id = task_id.split('_')[0] if '_' in task_id else 'anonymous'
                active_users.add(user_id)
        
        # Remove semaphores for inactive users
        inactive_users = set(self.user_semaphores.keys()) - active_users
        for user_id in inactive_users:
            if self.user_semaphores[user_id].locked() == False:
                del self.user_semaphores[user_id]
    
    async def initialize(self):
        """Initialize OpenAI client"""
        if self._initialized:
            return
        
        try:
            self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
            self._initialized = True
            logger.info("✅ OpenAI (new SDK) configured successfully")
        except Exception as e:
            logger.error(f"❌ Failed to configure OpenAI: {e}")
            raise
    
    async def generate_response(
        self,
        session_id: str,
        persona_type: PersonaType,
        user_message: str,
        context: Optional[Dict[str, Any]] = None,
        auth_token: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Generate a streaming response using OpenAI"""
        # Get user ID from context for per-user rate limiting
        user_id = context.get('user_id', 'anonymous') if context else 'anonymous'
        user_semaphore = self.get_user_semaphore(user_id)
        
        # Use per-user semaphore instead of global bottleneck
        async with user_semaphore:
            try:
                # Get session and add user message
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
                
                # Check if this is the first user message for jaimee_therapist (auto-preload context)
                is_first_jaimee_message = False
                if persona_type == PersonaType.JAIMEE_THERAPIST:
                    # Count user messages (excluding the just-added one)
                    user_message_count = sum(1 for msg in messages[:-1] if msg.role == "user")
                    is_first_jaimee_message = user_message_count == 0
                    if is_first_jaimee_message:
                        logger.info(f"🌟 First interaction with jAImee - will preload user context")
                
                # Get system prompt with context
                system_prompt = persona_manager.get_system_prompt(
                    persona_type, 
                    context or session.context
                )
                
                # Get persona config
                persona_config = persona_manager.get_persona(persona_type)
                
                # Set auth token for tool manager from session or parameter
                if auth_token:
                    tool_manager.set_auth_token(auth_token, session.profile_id)
                elif session.auth_token:
                    tool_manager.set_auth_token(session.auth_token, session.profile_id)
                
                # Set page context for tool manager if available
                if context and (context.get('page_context') or context.get('page_url')):
                    page_type = context.get('page_context', 'unknown')  # Frontend sends as 'page_context'
                    
                    # Add human-readable page name
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
                    logger.info(f"📄 Pipeline: Set page context - {page_display_name} ({page_type}) with capabilities: {page_context.get('capabilities', [])}")
                
                # Build messages for OpenAI API
                openai_messages = [{"role": "system", "content": system_prompt}]
                
                # Add conversation history (excluding the just-added user message)
                for msg in messages[:-1]:
                    openai_messages.append({
                        "role": msg.role,
                        "content": msg.content
                    })
                
                # Add the current user message
                openai_messages.append({"role": "user", "content": user_message})
                
                # Auto-preload context for jAImee's first interaction
                if is_first_jaimee_message and persona_config.tools:
                    logger.info(f"🌟 Auto-preloading jAImee context with mood and profile data")
                    try:
                        # Preload mood and profile context
                        mood_profile_result = await tool_manager.execute_tool("get_client_mood_profile", {
                            "include_mood_history": True,
                            "include_profile_details": True
                        })
                        
                        if mood_profile_result.get("success"):
                            # Add the preloaded context as a hidden assistant message for context
                            context_summary = self._create_context_summary(mood_profile_result.get("result", {}))
                            
                            # Add a system-style message with the context (invisible to user)
                            openai_messages.append({
                                "role": "assistant", 
                                "content": f"[Internal Context] {context_summary}"
                            })
                            logger.info(f"✅ Successfully preloaded jAImee context")
                        else:
                            logger.warning(f"⚠️ Failed to preload jAImee context: {mood_profile_result.get('error', 'Unknown error')}")
                    except Exception as e:
                        logger.error(f"❌ Error preloading jAImee context: {e}")
                
                # Agent loop with tool-use: let the model plan tool calls, execute, and iterate
                full_response = ""
                max_iterations = 6
                iterations = 0

                # Include tools if persona has them
                base_params = {
                    "model": persona_config.model,
                    "temperature": persona_config.temperature,
                    "max_tokens": persona_config.max_tokens,
                }
                if persona_config.tools:
                    base_params["tools"] = persona_config.tools
                    base_params["tool_choice"] = "auto"

                # Seed from session context
                session_last_client_id = (session.context or {}).get("last_client_id") if session and session.context else None
                session_last_client_name = (session.context or {}).get("last_client_name") if session and session.context else None
                session_last_assignment_id = (session.context or {}).get("last_assignment_id") if session and session.context else None

                last_tool_signature = None
                last_found_client_id = session_last_client_id
                last_client_name = session_last_client_name
                last_assignment_id = session_last_assignment_id
                while iterations < max_iterations:
                    iterations += 1
                    
                    # Stream the response from OpenAI 1.0+
                    stream = await self.openai_client.chat.completions.create(
                        messages=openai_messages,
                        stream=True,
                        **base_params
                    )

                    # Collect streaming response
                    message_content = ""
                    tool_calls = []
                    
                    async for chunk in stream:
                        if not chunk.choices:
                            continue
                            
                        delta = chunk.choices[0].delta
                        
                        # Handle content streaming
                        if delta.content:
                            message_content += delta.content
                            # Yield each chunk as it arrives
                            yield delta.content
                        
                        # Handle tool calls
                        if delta.tool_calls:
                            # Add tool calls (this is more complex for streaming, but simplified here)
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

                    # Create message object from streamed content
                    class MockMessage:
                        def __init__(self, content, tool_calls):
                            self.content = content
                            self.tool_calls = [type('ToolCall', (), {
                                'id': tc["id"],
                                'function': type('Function', (), {
                                    'name': tc["function"]["name"],
                                    'arguments': tc["function"]["arguments"]
                                })()
                            }) for tc in (tool_calls or [])]
                    
                    message = MockMessage(message_content, tool_calls if any(tool_calls) else None)

                    # If the model requested tool calls, execute them and loop
                    if getattr(message, "tool_calls", None):
                        # Append the assistant message that contains the tool_calls
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

                        # Execute each tool call and push the results back as tool messages
                        for tc in message.tool_calls:
                            tool_name = tc.function.name
                            try:
                                args_text = tc.function.arguments or "{}"
                                try:
                                    arguments = json.loads(args_text)
                                except Exception:
                                    arguments = {}
                                # If user gave immediate style guidance (e.g., slang, tone) in the last user_message, pass it to doc generation tools
                                if tool_name in {"generate_document_auto", "generate_document_from_loaded"}:
                                    # Always pass the user's latest message as generation instructions, unless already provided
                                    if isinstance(user_message, str) and not arguments.get("generation_instructions"):
                                        logger.info(f"🎨 [DEBUG] Injecting generation_instructions for {tool_name}: '{user_message}'")
                                        arguments["generation_instructions"] = user_message
                                    else:
                                        logger.info(f"🎨 [DEBUG] NOT injecting generation_instructions for {tool_name} - already provided: {arguments.get('generation_instructions', 'N/A')}")


                                # If the model supplied a short/missing client_id for convo tools, patch it using the last found full client_id
                                if tool_name in {"get_latest_conversation", "get_conversations", "get_conversation_messages", "get_client_summary"}:
                                    # Always prefer the resolved client UUID for consistency
                                    if last_found_client_id:
                                        arguments["client_id"] = last_found_client_id
                                    else:
                                        cid = arguments.get("client_id")
                                        if (not cid or (isinstance(cid, str) and len(cid) < 30)) and last_client_name:
                                            # Resolve via a quick lookup using last_client_name
                                            try:
                                                lookup = await tool_manager.execute_tool("search_clients", {"query": last_client_name, "limit": 1})
                                                if lookup.get("success") and isinstance(lookup.get("result"), list) and len(lookup.get("result")) > 0:
                                                    resolved = lookup["result"][0].get("client_id")
                                                    if isinstance(resolved, str) and len(resolved) >= 30:
                                                        last_found_client_id = resolved
                                                        arguments["client_id"] = resolved
                                                        try:
                                                            await session_manager.update_session_context(session_id, {
                                                                "last_client_id": resolved,
                                                                "last_client_name": last_client_name
                                                            })
                                                        except Exception:
                                                            pass
                                            except Exception:
                                                pass

                                # Auto-resolve assignment_id for get_conversation_messages
                                if tool_name == "get_conversation_messages":
                                    assignment_id = arguments.get("assignment_id")
                                    def _is_valid_assignment_id(val: Any) -> bool:
                                        return isinstance(val, str) and len(val) >= 30
                                    if not _is_valid_assignment_id(assignment_id):
                                        # Use cached last assignment id if valid
                                        if _is_valid_assignment_id(last_assignment_id):
                                            arguments["assignment_id"] = last_assignment_id
                                        else:
                                            # Attempt to fetch latest conversation to get a valid assignment id
                                            try:
                                                cid_for_latest = arguments.get("client_id") or last_found_client_id
                                                if cid_for_latest:
                                                    latest = await tool_manager.execute_tool("get_latest_conversation", {"client_id": cid_for_latest, "message_limit": 50})
                                                    if latest.get("success") and isinstance(latest.get("result"), dict):
                                                        candidate = latest["result"].get("latest_assignment_id")
                                                        if _is_valid_assignment_id(candidate):
                                                            arguments["assignment_id"] = candidate
                                                            last_assignment_id = candidate
                                                            try:
                                                                await session_manager.update_session_context(session_id, {"last_assignment_id": candidate})
                                                            except Exception:
                                                                pass
                                            except Exception:
                                                pass

                                # De-dup guard: skip if repeating same tool with identical args
                                tool_signature = json.dumps({"name": tool_name, "args": arguments}, sort_keys=True)
                                if tool_signature == last_tool_signature:
                                    logger.info(f"⏭️ Skipping duplicate tool call: {tool_signature}")
                                    continue

                                # If arguments already include a valid full client_id, remember and persist it
                                try:
                                    existing_cid = arguments.get("client_id")
                                    if isinstance(existing_cid, str) and len(existing_cid) >= 30:
                                        last_found_client_id = existing_cid
                                        try:
                                            await session_manager.update_session_context(session_id, {
                                                "last_client_id": existing_cid
                                            })
                                        except Exception:
                                            pass
                                except Exception:
                                    pass

                                # Only show tool execution messages for web_assistant, not jaimee_therapist
                                if persona_type == PersonaType.WEB_ASSISTANT:
                                    executing_msg = f"\n\n[tool] {tool_name} executing...\n\n"
                                    full_response += executing_msg
                                    yield executing_msg

                                tool_result = await tool_manager.execute_tool(tool_name, arguments)
                                last_tool_signature = tool_signature

                                # Debug logging for templates issue
                                if tool_name == "get_templates":
                                    logger.info(f"🔍 DEBUG get_templates tool_result: {tool_result}")

                                result_data = tool_result.get("result") if tool_result.get("success") else None
                                has_embedded_error = isinstance(result_data, dict) and bool(result_data.get("error"))
                                
                                if tool_name == "get_templates":
                                    logger.info(f"🔍 DEBUG get_templates result_data: {result_data}")
                                    logger.info(f"🔍 DEBUG get_templates success: {tool_result.get('success')}")
                                    logger.info(f"🔍 DEBUG get_templates has_embedded_error: {has_embedded_error}")
                                if tool_result.get("success") and not has_embedded_error:
                                    # Check for UI actions in tool result
                                    if isinstance(result_data, dict) and result_data.get("ui_action"):
                                        ui_action_msg = result_data.get('user_message', 'Performing UI action...')
                                        # Only show UI action messages for web_assistant, not jaimee_therapist  
                                        if persona_type == PersonaType.WEB_ASSISTANT:
                                            yield f"\n[ui] {ui_action_msg}\n"
                                        # Store UI action(s) for WebSocket layer to handle
                                        if not hasattr(self, '_ui_actions'):
                                            self._ui_actions = []
                                            print(f"🔍 DEBUG: Created _ui_actions list in pipeline_manager")
                                        
                                        # Handle both single UI action and array of UI actions
                                        ui_action_data = result_data["ui_action"]
                                        if isinstance(ui_action_data, list):
                                            # Multiple UI actions (e.g., from load_multiple_sessions)
                                            for action in ui_action_data:
                                                self._ui_actions.append(action)
                                                print(f"🔍 DEBUG: Added UI action to pipeline_manager: {action}")
                                            print(f"🔍 DEBUG: Added {len(ui_action_data)} UI actions, total now: {len(self._ui_actions)}")
                                        else:
                                            # Single UI action (e.g., from load_session_direct)
                                            self._ui_actions.append(ui_action_data)
                                            print(f"🔍 DEBUG: Added UI action to pipeline_manager: {ui_action_data}")
                                            print(f"🔍 DEBUG: Total UI actions now: {len(self._ui_actions)}")
                                    
                                    quick_feedback = ""
                                    if tool_name == "search_clients" and isinstance(result_data, list) and len(result_data) > 0:
                                        client = result_data[0]
                                        client_name = client.get('name', 'Client')
                                        # Capture full client_id for subsequent calls and persist to session context
                                        cid = client.get('client_id')
                                        if isinstance(cid, str) and len(cid) >= 30:
                                            last_found_client_id = cid
                                            try:
                                                await session_manager.update_session_context(session_id, {
                                                    "last_client_id": cid,
                                                    "last_client_name": client_name
                                                })
                                            except Exception:
                                                pass
                                        quick_feedback = f" - Found {client_name}"
                                    elif tool_name == "get_client_summary" and isinstance(result_data, dict):
                                        client_name = result_data.get('name', 'Client')
                                        quick_feedback = f" - Retrieved summary for {client_name}"
                                    elif tool_name == "get_latest_conversation" and isinstance(result_data, dict):
                                        # Cache latest assignment id
                                        candidate = result_data.get('latest_assignment_id')
                                        if isinstance(candidate, str) and len(candidate) >= 30:
                                            last_assignment_id = candidate
                                            try:
                                                await session_manager.update_session_context(session_id, {"last_assignment_id": candidate})
                                            except Exception:
                                                pass
                                        quick_feedback = f" - Completed successfully"
                                    elif tool_name == "get_conversations" and isinstance(result_data, dict):
                                        # Cache most recent conversation's assignment id if available
                                        convos = result_data.get('conversations') or []
                                        if isinstance(convos, list) and len(convos) > 0 and isinstance(convos[0], dict):
                                            cand = convos[0].get('assignment_id')
                                            if isinstance(cand, str) and len(cand) >= 30:
                                                last_assignment_id = cand
                                                try:
                                                    await session_manager.update_session_context(session_id, {"last_assignment_id": cand})
                                                except Exception:
                                                    pass
                                        quick_feedback = f" - Completed successfully"
                                    elif tool_name == "get_templates" and isinstance(result_data, dict):
                                        # Handle templates response
                                        template_count = result_data.get('count', 0)
                                        if template_count > 0:
                                            quick_feedback = f" - Found {template_count} templates"
                                        else:
                                            quick_feedback = f" - No templates found"
                                    else:
                                        quick_feedback = f" - Completed successfully"

                                    # Only show tool completion messages for web_assistant, not jaimee_therapist
                                    if persona_type == PersonaType.WEB_ASSISTANT:
                                        executed_msg = f"\n[tool] {tool_name} executed{quick_feedback}\n\n"
                                        full_response += executed_msg
                                        yield executed_msg

                                    # Do not override last_found_client_id from generic result payloads to avoid drift

                                    tool_content = json.dumps(result_data, ensure_ascii=False)
                                else:
                                    embedded_error = result_data.get('error') if isinstance(result_data, dict) else None
                                    error_text = tool_result.get('error') or embedded_error or 'Failed'
                                    # Only show tool error messages for web_assistant, not jaimee_therapist
                                    if persona_type == PersonaType.WEB_ASSISTANT:
                                        error_msg = f"\n[tool] {tool_name} executed [error] {error_text}\n\n"
                                        full_response += error_msg
                                        yield error_msg
                                    tool_content = json.dumps({"error": tool_result.get("error", "Failed")}, ensure_ascii=False)

                                # Feed tool result back to the model
                                openai_messages.append({
                                    "role": "tool",
                                    "tool_call_id": tc.id,
                                    "content": tool_content,
                                })
                            except Exception as e:
                                error_msg = f"\n\n[error] Tool execution error: {str(e)}"
                                full_response += error_msg
                                yield error_msg
                        # Continue the loop so the model can use tool outputs
                        continue

                    # No tool calls requested: finalize (content already streamed)
                    final_text = message.content or ""
                    if final_text:
                        full_response += final_text
                        # NOTE: Don't yield final_text here - content was already streamed chunk by chunk above
                    break

                # Add assistant message to session
                await session_manager.add_message(session_id, "assistant", full_response)
                    
            except Exception as e:
                logger.error(f"Error generating response: {e}")
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
    
    async def generate_non_streaming_response(
        self,
        session_id: str,
        persona_type: PersonaType,
        user_message: str,
        context: Optional[Dict[str, Any]] = None,
        auth_token: Optional[str] = None
    ) -> str:
        """Generate a complete response without streaming"""
        response_parts = []
        async for chunk in self.generate_response(session_id, persona_type, user_message, context, auth_token):
            response_parts.append(chunk)
        
        return " ".join(response_parts)
    
    async def health_check(self) -> Dict[str, Any]:
        """Check the health of the OpenAI client"""
        # Clean up old user semaphores periodically
        self.cleanup_user_semaphores()
        
        status = {
            "initialized": self._initialized,
            "active_requests": len(self.active_requests),
            "active_users": len(self.user_semaphores),
            "max_requests_per_user": self.max_requests_per_user,
            "scaling_mode": "per_user_rate_limiting",
            "theoretical_max_concurrent": len(self.user_semaphores) * self.max_requests_per_user,
            "personas": {}
        }
        
        for persona_type in PersonaType:
            status["personas"][persona_type.value] = {
                "available": True,
                "persona_config": persona_manager.get_persona(persona_type).dict()
            }
        
        return status

    def _create_context_summary(self, mood_profile_data: Dict[str, Any]) -> str:
        """Create a concise context summary for jAImee from mood and profile data"""
        try:
            summary_parts = []
            
            # Profile information
            profile = mood_profile_data.get("profile", {})
            if profile and not profile.get("error"):
                name = profile.get("name", "the user")
                if name != "Unknown Client":
                    summary_parts.append(f"Client name: {name}")
                
                # Add comprehensive profile details
                personal_details = []
                if profile.get("age"):
                    personal_details.append(f"age {profile['age']}")
                if profile.get("gender"):
                    personal_details.append(f"gender: {profile['gender']}")
                if profile.get("occupation"):
                    personal_details.append(f"occupation: {profile['occupation']}")
                
                if personal_details:
                    summary_parts.append(f"Personal details: {', '.join(personal_details)}")
                
                # Add status and role info
                status_details = []
                if profile.get("role"):
                    status_details.append(f"role: {profile['role']}")
                if profile.get("status"):
                    status_details.append(f"status: {profile['status']}")
                
                if status_details:
                    summary_parts.append(f"Account: {', '.join(status_details)}")
                
                # Add clinic context if available
                clinic_info = profile.get("clinic_info", {})
                if clinic_info and clinic_info.get("name"):
                    clinic_name = clinic_info["name"]
                    clinic_timezone = clinic_info.get("timezone", "")
                    if clinic_timezone:
                        summary_parts.append(f"Clinic: {clinic_name} ({clinic_timezone})")
                    else:
                        summary_parts.append(f"Clinic: {clinic_name}")
            
            # Mood data information
            mood_data = mood_profile_data.get("mood_data", {})
            if mood_data and not mood_data.get("error"):
                mood_summary = mood_data.get("mood_summary", "")
                if mood_summary and mood_summary != "No recent mood tracking data found for this user":
                    summary_parts.append(f"Mood status: {mood_summary}")
                
                # Recent mood entry
                last_entry = mood_data.get("last_mood_entry", {})
                if last_entry and last_entry.get("mood_label"):
                    mood_label = last_entry["mood_label"]
                    created_at = last_entry.get("createdAt", "")
                    if created_at:
                        try:
                            from datetime import datetime
                            created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            time_str = created_time.strftime("%B %d")
                            summary_parts.append(f"Most recent mood: {mood_label} on {time_str}")
                        except:
                            summary_parts.append(f"Most recent mood: {mood_label}")
                    else:
                        summary_parts.append(f"Most recent mood: {mood_label}")
                
                # Total mood entries
                total_entries = mood_data.get("total_entries", 0)
                if total_entries > 0:
                    summary_parts.append(f"Total mood entries: {total_entries}")
            
            # Therapeutic insights
            insights = mood_profile_data.get("therapeutic_insights", {})
            if insights:
                focus_areas = insights.get("therapeutic_focus_areas", [])
                if focus_areas:
                    summary_parts.append(f"Focus areas: {', '.join(focus_areas)}")
                
                suggested_approaches = insights.get("suggested_approaches", [])
                if suggested_approaches:
                    # Only include first 2 suggestions to keep summary concise
                    approaches = suggested_approaches[:2]
                    summary_parts.append(f"Suggested approaches: {'; '.join(approaches)}")
            
            # Create final summary
            if summary_parts:
                return ". ".join(summary_parts) + "."
            else:
                return "User context loaded but no specific data available."
                
        except Exception as e:
            logger.error(f"Error creating context summary: {e}")
            return "User context partially loaded."
    
    async def shutdown(self):
        """Shutdown OpenAI client and cancel active requests"""
        # Cancel all active requests
        for request_id, task in self.active_requests.items():
            if not task.done():
                task.cancel()
        
        # Wait for all tasks to complete
        if self.active_requests:
            await asyncio.gather(*self.active_requests.values(), return_exceptions=True)
        
        self.active_requests.clear()
        
        # No explicit close for openai 0.28
        
        self._initialized = False
        
        logger.info("✅ Pipeline manager shutdown complete")

# Global pipeline manager instance
pipeline_manager = PipelineManager()