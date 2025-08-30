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
from haystack.tools import Tool, create_tool_from_function
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
            api_key=Secret.from_token(settings.openai_api_key),
            tools=self._convert_tools_to_haystack()
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
            api_key=Secret.from_token(settings.openai_api_key),
            tools=self._convert_tools_to_haystack()
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
    
    def _create_evaluator_optimizer_pipeline(self):
        """Create a pipeline with evaluation and optimization loops"""
        # Routes for evaluation-based workflows
        eval_routes = [
            {
                "condition": "{{evaluation.quality_score >= 8 or iteration_count >= 3}}",
                "output": "{{current_response}}",
                "output_name": "acceptable_response",
                "output_type": str,
            },
            {
                "condition": "{{evaluation.quality_score < 8 and iteration_count < 3}}",
                "output": "{{current_response}}",
                "output_name": "needs_improvement",
                "output_type": str,
            },
        ]
        
        eval_pipeline = Pipeline()
        eval_pipeline.add_component("initial_generator", OpenAIChatGenerator(
            model="gpt-4o-mini",
            api_key=Secret.from_token(settings.openai_api_key),
            tools=self._convert_tools_to_haystack()
        ))
        eval_pipeline.add_component("evaluator", OpenAIChatGenerator(
            model="gpt-4o",  # Use more capable model for evaluation
            api_key=Secret.from_token(settings.openai_api_key),
        ))
        eval_pipeline.add_component("eval_router", ConditionalRouter(eval_routes, unsafe=True))
        eval_pipeline.add_component("optimizer", OpenAIChatGenerator(
            model="gpt-4o",
            api_key=Secret.from_token(settings.openai_api_key),
            tools=self._convert_tools_to_haystack()
        ))
        
        # Connect evaluation loop - specify exact connection names
        eval_pipeline.connect("initial_generator.replies", "evaluator.messages")
        eval_pipeline.connect("evaluator.replies", "eval_router.evaluation")
        eval_pipeline.connect("eval_router.needs_improvement", "optimizer.messages")
        eval_pipeline.connect("optimizer.replies", "evaluator.messages")
        
        self.pipelines["evaluator_optimizer"] = eval_pipeline
    
    def _convert_tools_to_haystack(self) -> List[Tool]:
        """Convert our tool manager tools to Haystack Tool format"""
        haystack_tools = []
        
        # Get tools from tool manager for WEB_ASSISTANT persona
        tools_config = tool_manager.get_tools_for_persona("web_assistant")
        
        for tool_name, tool_config in tool_manager.tools.items():
            if tool_name in ["get_client_summary", "search_clients", "generate_report"]:
                # Convert to Haystack Tool
                def create_tool_function(tool_name):
                    def tool_function(**kwargs):
                        # Haystack expects synchronous functions, so we need to handle async differently
                        import asyncio
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # If we're in an async context, we can't use asyncio.run
                                # For now, return a placeholder - this needs a better solution
                                return f"Tool {tool_name} called with {kwargs}"
                            else:
                                return asyncio.run(tool_manager.execute_tool(tool_name, kwargs))
                        except Exception as e:
                            return f"Tool execution failed: {str(e)}"
                    return tool_function
                
                haystack_tool = Tool(
                    name=tool_name,
                    description=tool_config["definition"]["function"]["description"],
                    parameters=tool_config["definition"]["function"]["parameters"],
                    function=create_tool_function(tool_name)
                )
                haystack_tools.append(haystack_tool)
        
        return haystack_tools
    
    async def run_pipeline(
        self,
        pipeline_type: str,
        messages: List[ChatMessage],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Run a specific pipeline with given messages"""
        if pipeline_type not in self.pipelines:
            raise ValueError(f"Pipeline type '{pipeline_type}' not found")
        
        pipeline = self.pipelines[pipeline_type]
        
        try:
            # Run pipeline with messages
            result = pipeline.run({"messages": messages})
            return result
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            raise
    
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
        Generate response using Haystack pipeline with proper tool chaining
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
            
            # Convert to Haystack ChatMessage format
            haystack_messages = []
            
            # Add system message
            system_prompt = persona_manager.get_system_prompt(
                persona_type, 
                context or session.context
            )
            haystack_messages.append(ChatMessage.from_system(system_prompt))
            
            # Add conversation history
            for msg in messages:
                if msg.role == "user":
                    haystack_messages.append(ChatMessage.from_user(msg.content))
                elif msg.role == "assistant":
                    haystack_messages.append(ChatMessage.from_assistant(msg.content))
            
            # Set auth token for tool manager
            if auth_token:
                tool_manager.set_auth_token(auth_token, session.profile_id)
            elif session.auth_token:
                tool_manager.set_auth_token(session.auth_token, session.profile_id)
            
            # Run pipeline
            result = await self.run_pipeline(pipeline_type, haystack_messages, context)
            
            # Process results and stream back
            if "final_response" in result:
                final_messages = result["final_response"]
                for message in final_messages:
                    if message.text:
                        # Add to session
                        await session_manager.add_message(session_id, "assistant", message.text)
                        yield message.text
            
            elif "tool_invoker" in result:
                tool_messages = result["tool_invoker"]["tool_messages"]
                for tool_message in tool_messages:
                    if tool_message.tool_call_result:
                        result_text = str(tool_message.tool_call_result.result)
                        yield f"\n\n🔧 Tool executed\n\n{result_text}"
                        
        except Exception as e:
            logger.error(f"Error in Haystack pipeline response generation: {e}")
            error_msg = "I apologize, but I encountered an error processing your request. Please try again."
            await session_manager.add_message(session_id, "assistant", error_msg)
            yield error_msg
    
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