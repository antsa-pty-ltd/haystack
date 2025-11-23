"""
Document Exploration Agent

Uses Haystack's Agent with tool-calling to autonomously explore therapy sessions
and build context for document generation.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from haystack.components.agents import Agent
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage, ChatRole
from haystack.tools import Tool
from haystack.utils import Secret
from agents.exploration_tools import (
    peek_session,
    search_session,
    pull_full_session,
    check_context_sufficiency,
    generate_document,
    reset_exploration_context,
    get_exploration_context
)

logger = logging.getLogger(__name__)


# System prompt for the document generation agent
AGENT_SYSTEM_PROMPT = """You are an intelligent document generation agent. Your goal is to explore therapy sessions efficiently and build sufficient context to generate a comprehensive clinical document.

CORE PRINCIPLE: Be DECISIVE, not EXHAUSTIVE. Once you have the content, GENERATE.

EXPLORATION FLOW:

**Step 1: Count Sessions**
- How many sessions do I have?

**If 1-3 sessions (SIMPLE PATH):**
1. Pull each session fully, one by one
2. Read and understand the content
3. Once you've read all sessions → GENERATE IMMEDIATELY
4. DON'T search after pulling - you already have everything!

**If 4+ sessions (SMART PATH):**
1. Pull the OLDEST session first (usually has presenting problems)
2. Read and understand it thoroughly  
3. Based on what the CLIENT discussed, generate 3-5 targeted search queries
   - Use natural language as if the client is speaking
   - Focus on their main concerns, symptoms, or presenting issues
4. Search OTHER sessions for those specific themes
5. Once you have good coverage → GENERATE

CRITICAL RULES:
- DON'T peek then pull then search the same session - that's redundant!
- DON'T do 30+ searches - you're creating duplicates!
- If you pulled a session fully, you already have it - move on!
- For 1-3 sessions: PULL → READ → GENERATE (no searching needed!)
- Quality over quantity: targeted context beats exhaustive searching

TOKEN BUDGET: 60,000 tokens max
- check_context_sufficiency() to monitor usage
- Once you understand the sessions, GENERATE

TOOLS:
1. peek_session(session_id, num_segments) - Quick preview (optional)
2. pull_full_session(session_id) - Get complete session
3. search_session(session_id, query, max_results) - Find specific content in OTHER sessions
4. check_context_sufficiency() - Check progress  
5. generate_document() - You're done! (Call this when ready)

EXAMPLE (1 session):
1. pull_full_session("session-1") → Got 43 segments
2. check_context_sufficiency() → 43 segments, 3225 tokens
3. generate_document() → DONE!

EXAMPLE (5 sessions):
1. pull_full_session("session-1") → Read oldest, understand presenting problems
2. search_session("session-2", "anxiety attacks") → Client mentioned this
3. search_session("session-3", "work stress") → Another key theme
4. check_context_sufficiency() → Good coverage
5. generate_document() → DONE!

Remember: Be SMART, not EXHAUSTIVE. Once you have the content, GENERATE."""


class DocumentExplorationAgent:
    """
    Autonomous agent for exploring therapy sessions and generating clinical documents.
    """
    
    def __init__(self, openai_api_key: str, model: str = "gpt-4o"):
        """
        Initialize the document exploration agent.
        
        Args:
            openai_api_key: OpenAI API key
            model: Model to use (default: gpt-4o)
        """
        self.openai_api_key = openai_api_key
        self.model = model
        
        # Create sync wrappers for async tools (Haystack Agent requires sync functions)
        def sync_peek_session(session_id: str, num_segments: int = 100) -> str:
            """Peek at first segments of a session"""
            import json
            result = asyncio.run(peek_session(session_id, num_segments))
            return json.dumps(result, ensure_ascii=False)
        
        def sync_search_session(session_id: str, query: str, max_results: int = 20) -> str:
            """Search within a session"""
            import json
            result = asyncio.run(search_session(session_id, query, max_results))
            return json.dumps(result, ensure_ascii=False)
        
        def sync_pull_full_session(session_id: str) -> str:
            """Pull complete session"""
            import json
            result = asyncio.run(pull_full_session(session_id))
            return json.dumps(result, ensure_ascii=False)
        
        def sync_check_context_sufficiency() -> str:
            """Check if context is sufficient"""
            import json
            result = check_context_sufficiency()
            return json.dumps(result, ensure_ascii=False)
        
        def sync_generate_document() -> str:
            """Signal ready to generate"""
            import json
            result = generate_document()
            return json.dumps(result, ensure_ascii=False)
        
        # Create Haystack Tool objects manually
        self.tools = [
            Tool(
                name="peek_session",
                description="Peek at the first N segments of a session to understand its size and content. Use this to quickly assess a session before deciding whether to pull it fully or search it semantically.",
                parameters={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "The ID of the session to peek at"},
                        "num_segments": {"type": "integer", "description": "Number of segments to retrieve from the start", "default": 100}
                    },
                    "required": ["session_id"]
                },
                function=sync_peek_session
            ),
            Tool(
                name="search_session",
                description="Semantically search within a specific session for relevant content. Use this when you know what themes or topics to look for in a large session.",
                parameters={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "The ID of the session to search"},
                        "query": {"type": "string", "description": "Natural language query describing what to search for"},
                        "max_results": {"type": "integer", "description": "Maximum number of results to return", "default": 20}
                    },
                    "required": ["session_id", "query"]
                },
                function=sync_search_session
            ),
            Tool(
                name="pull_full_session",
                description="Retrieve all segments from a session. Use this for small sessions or when you need complete context.",
                parameters={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "The ID of the session to pull completely"}
                    },
                    "required": ["session_id"]
                },
                function=sync_pull_full_session
            ),
            Tool(
                name="check_context_sufficiency",
                description="Check if you have gathered sufficient context to generate a quality document. Returns information about accumulated segments, token usage, and coverage. Use this periodically to decide if you should continue exploring or generate the document.",
                parameters={"type": "object", "properties": {}},
                function=sync_check_context_sufficiency
            ),
            Tool(
                name="generate_document",
                description="Signal that you're ready to generate the document with the accumulated context. This is the final tool call that ends the exploration phase. Call this only when you're confident you have sufficient context.",
                parameters={"type": "object", "properties": {}},
                function=sync_generate_document
            )
        ]
        
        # Create the Haystack agent
        self.agent = Agent(
            chat_generator=OpenAIChatGenerator(
                api_key=Secret.from_token(openai_api_key),
                model=model,
                generation_kwargs={"temperature": 0.3}  # Lower temp for more consistent reasoning
            ),
            tools=self.tools,
            system_prompt=AGENT_SYSTEM_PROMPT,
            exit_conditions=["generate_document"],  # Agent stops when it calls generate_document
            max_agent_steps=50,  # Safety limit
            raise_on_tool_invocation_failure=False  # Continue on tool errors
        )
        
        logger.info(f"✅ DocumentExplorationAgent initialized with {len(self.tools)} tools")
    
    async def explore_and_decide(
        self,
        session_ids: List[str],
        template_name: str,
        template_content: str,
        authorization: Optional[str] = None,
        generation_id: Optional[str] = None,
        emit_progress_func = None
    ) -> Dict[str, Any]:
        """
        Let the agent autonomously explore sessions and decide when to generate.
        
        Args:
            session_ids: List of session IDs to explore
            template_name: Name of the document template
            template_content: Content of the template
            authorization: Authorization header for API calls
            generation_id: Generation ID for progress tracking
            emit_progress_func: Function to emit progress updates (optional)
            
        Returns:
            Dict with accumulated segments and agent's decision trail
        """
        # Reset exploration context for this generation
        reset_exploration_context(authorization, generation_id)
        
        # Build initial message for the agent
        session_list = ", ".join(session_ids)
        initial_message = f"""Generate a clinical document using the template "{template_name}".

You have {len(session_ids)} therapy session(s) to explore:
Session IDs: {session_list}

Template Overview:
{template_content[:500]}...
[Full template will be provided during generation]

Your task:
1. Explore these sessions intelligently to understand their content
2. Build sufficient context to generate a comprehensive document
3. When confident you have enough information, call generate_document()

Start exploring!"""
        
        logger.info(f"🤖 Agent starting exploration of {len(session_ids)} sessions")
        
        # Run the agent
        try:
            result = self.agent.run(
                messages=[ChatMessage.from_user(initial_message)]
            )
            
            # Get the exploration context
            context = get_exploration_context()
            
            # Extract conversation history
            messages = result.get("messages", [])
            
            # Stream agent reasoning to UI if callback provided
            if emit_progress_func and authorization:
                for msg in messages:
                    if msg.role == ChatRole.ASSISTANT and msg.text:
                        # Extract the thinking text (before tool calls)
                        thinking_text = msg.text.strip()
                        if thinking_text and not thinking_text.startswith('{'):
                            # Emit the agent's reasoning
                            try:
                                await emit_progress_func(generation_id, {
                                    "type": "agent_thinking",
                                    "stage": "agentic_exploration",
                                    "message": thinking_text
                                }, authorization)
                            except Exception as e:
                                logger.warning(f"Failed to emit agent reasoning: {e}")
            
            # Log agent's decision process
            logger.info(f"📊 Agent completed exploration:")
            logger.info(f"   - Total segments collected: {len(context.accumulated_segments)}")
            logger.info(f"   - Tokens used: {context.tokens_used}/{context.token_budget}")
            logger.info(f"   - Sessions explored: {len(context.sessions_explored)}")
            logger.info(f"   - Agent steps: {len([m for m in messages if m.role == 'assistant'])}")
            
            return {
                "success": True,
                "segments": context.accumulated_segments,
                "tokens_used": context.tokens_used,
                "sessions_explored": context.sessions_explored,
                "agent_messages": messages,
                "decision_trail": self._extract_decision_trail(messages)
            }
            
        except Exception as e:
            logger.error(f"❌ Agent exploration failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "segments": get_exploration_context().accumulated_segments,
                "tokens_used": get_exploration_context().tokens_used
            }
    
    def _extract_decision_trail(self, messages: List[ChatMessage]) -> List[Dict[str, Any]]:
        """
        Extract the agent's decision-making trail from conversation history.
        
        Args:
            messages: List of chat messages
            
        Returns:
            List of decision points with reasoning
        """
        decisions = []
        
        for msg in messages:
            if msg.role == "assistant":
                # Check if message contains tool calls
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        decisions.append({
                            "action": "tool_call",
                            "tool": tool_call.tool_name if hasattr(tool_call, 'tool_name') else "unknown",
                            "reasoning": msg.text if hasattr(msg, 'text') else ""
                        })
                elif msg.text:
                    # Agent reasoning without tool call
                    decisions.append({
                        "action": "reasoning",
                        "content": msg.text
                    })
        
        return decisions


# Global agent instance (will be initialized on startup)
_document_agent: Optional[DocumentExplorationAgent] = None


def initialize_agent(openai_api_key: str, model: str = "gpt-4o"):
    """Initialize the global document agent instance."""
    global _document_agent
    _document_agent = DocumentExplorationAgent(openai_api_key, model)
    logger.info("✅ Global DocumentExplorationAgent initialized")


def get_document_agent() -> Optional[DocumentExplorationAgent]:
    """Get the global document agent instance."""
    return _document_agent

