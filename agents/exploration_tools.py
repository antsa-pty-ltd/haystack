"""
Exploration tools for the document generation agent.

These tools allow the agent to explore therapy sessions iteratively,
making decisions about how to retrieve and analyze content.
"""

import os
import httpx
import logging
from typing import Dict, Any, List, Optional, Annotated
from utils.session_utils import estimate_tokens_from_segments

logger = logging.getLogger(__name__)


class ExplorationContext:
    """Shared context for exploration tools"""
    def __init__(self):
        self.accumulated_segments: List[Dict[str, Any]] = []
        self.tokens_used: int = 0
        self.token_budget: int = 60000
        self.sessions_explored: List[str] = []
        self.authorization: Optional[str] = None
        self.generation_id: Optional[str] = None
        
    def add_segments(self, segments: List[Dict[str, Any]]):
        """Add segments and update token count"""
        self.accumulated_segments.extend(segments)
        # Rough estimate: 1 segment ≈ 75 tokens
        self.tokens_used += len(segments) * 75
        
    def has_budget(self, estimated_tokens: int) -> bool:
        """Check if there's budget for more tokens"""
        return (self.tokens_used + estimated_tokens) <= self.token_budget


# Global context instance (will be reset for each document generation)
_exploration_context = ExplorationContext()


def get_exploration_context() -> ExplorationContext:
    """Get the current exploration context"""
    return _exploration_context


def reset_exploration_context(authorization: str = None, generation_id: str = None):
    """Reset exploration context for a new document generation"""
    global _exploration_context
    _exploration_context = ExplorationContext()
    _exploration_context.authorization = authorization
    _exploration_context.generation_id = generation_id


async def peek_session(
    session_id: Annotated[str, "The ID of the session to peek at"],
    num_segments: Annotated[int, "Number of segments to retrieve from the start"] = 100
) -> Dict[str, Any]:
    """
    Peek at the first N segments of a session to understand its size and content.
    
    Use this to quickly assess a session before deciding whether to pull it fully
    or search it semantically.
    
    Args:
        session_id: The session/transcript ID to peek at
        num_segments: Number of initial segments to retrieve (default: 100)
        
    Returns:
        Dict with segments, total_segments, estimated_tokens, and preview_text
    """
    context = get_exploration_context()
    api_url = os.getenv("API_URL", "http://localhost:8080")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Use semantic search with threshold 0.0 and limit to get first segments
            response = await client.post(
                f"{api_url}/api/v1/ai/semantic-search",
                json={
                    "query": "session conversation",
                    "transcript_ids": [session_id],
                    "limit": num_segments,
                    "similarity_threshold": 0.0
                },
                headers={"Authorization": context.authorization} if context.authorization else {}
            )
            response.raise_for_status()
            response_data = response.json()
            
            segments = response_data.get('segments', []) if isinstance(response_data, dict) else response_data
            
            # Build preview text from first few segments
            preview_texts = []
            for seg in segments[:10]:
                speaker = seg.get('speaker', 'Speaker')
                text = seg.get('text', '')
                preview_texts.append(f"{speaker}: {text}")
            preview_text = "\n".join(preview_texts)
            
            total_segments = len(segments)
            estimated_tokens = estimate_tokens_from_segments(total_segments)
            
            # Add to context
            context.add_segments(segments)
            if session_id not in context.sessions_explored:
                context.sessions_explored.append(session_id)
            
            logger.info(f"Agent peeked at session {session_id}: {total_segments} segments, ~{estimated_tokens} tokens")
            
            return {
                "success": True,
                "session_id": session_id,
                "segments_retrieved": total_segments,
                "estimated_total_segments": total_segments,  # This is just what we got
                "estimated_tokens": estimated_tokens,
                "preview_text": preview_text,
                "message": f"Retrieved {total_segments} segments from session. Preview shows initial conversation content."
            }
            
    except Exception as e:
        logger.error(f"Error peeking session {session_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to peek session: {str(e)}"
        }


async def search_session(
    session_id: Annotated[str, "The ID of the session to search"],
    query: Annotated[str, "Natural language query describing what to search for"],
    max_results: Annotated[int, "Maximum number of results to return"] = 20
) -> Dict[str, Any]:
    """
    Semantically search within a specific session for relevant content.
    
    Use this when you know what themes or topics to look for in a large session.
    
    Args:
        session_id: The session/transcript ID to search
        query: Natural language search query
        max_results: Maximum number of matching segments to return
        
    Returns:
        Dict with matching segments and relevance scores
    """
    context = get_exploration_context()
    api_url = os.getenv("API_URL", "http://localhost:8080")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_url}/api/v1/ai/semantic-search",
                json={
                    "query": query,
                    "transcript_ids": [session_id],
                    "limit": max_results,
                    "similarity_threshold": 0.3  # Lower threshold for better results
                },
                headers={"Authorization": context.authorization} if context.authorization else {}
            )
            response.raise_for_status()
            response_data = response.json()
            
            segments = response_data.get('segments', []) if isinstance(response_data, dict) else response_data
            
            # Add to context
            context.add_segments(segments)
            if session_id not in context.sessions_explored:
                context.sessions_explored.append(session_id)
            
            # Build preview
            preview_texts = []
            for seg in segments[:5]:
                speaker = seg.get('speaker', 'Speaker')
                text = seg.get('text', '')
                score = seg.get('similarity_score', 0)
                preview_texts.append(f"[Score: {score:.2f}] {speaker}: {text[:100]}...")
            preview = "\n".join(preview_texts)
            
            logger.info(f"Agent searched session {session_id} for '{query}': {len(segments)} results")
            
            return {
                "success": True,
                "session_id": session_id,
                "query": query,
                "segments_found": len(segments),
                "segments_preview": preview,
                "message": f"Found {len(segments)} relevant segments matching '{query}'"
            }
            
    except Exception as e:
        logger.error(f"Error searching session {session_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to search session: {str(e)}"
        }


async def pull_full_session(
    session_id: Annotated[str, "The ID of the session to pull completely"]
) -> Dict[str, Any]:
    """
    Retrieve all segments from a session.
    
    Use this for small sessions or when you need complete context.
    
    Args:
        session_id: The session/transcript ID to retrieve fully
        
    Returns:
        Dict with all segments from the session
    """
    context = get_exploration_context()
    api_url = os.getenv("API_URL", "http://localhost:8080")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Use the correct endpoint for fetching all segments (not semantic search!)
            response = await client.post(
                f"{api_url}/api/v1/ai/transcripts/segments-by-sessions",
                json={
                    "session_ids": [session_id],
                    "limit_per_session": 1000  # High limit to get all segments
                },
                headers={"Authorization": context.authorization} if context.authorization else {}
            )
            response.raise_for_status()
            response_data = response.json()
            
            segments = response_data.get('segments', []) if isinstance(response_data, dict) else response_data
            
            estimated_tokens = estimate_tokens_from_segments(len(segments))
            
            # Check budget
            if not context.has_budget(estimated_tokens):
                return {
                    "success": False,
                    "error": "Token budget exceeded",
                    "message": f"Pulling full session would exceed token budget ({context.tokens_used + estimated_tokens} > {context.token_budget})"
                }
            
            # Add to context
            context.add_segments(segments)
            if session_id not in context.sessions_explored:
                context.sessions_explored.append(session_id)
            
            logger.info(f"Agent pulled full session {session_id}: {len(segments)} segments, ~{estimated_tokens} tokens")
            
            return {
                "success": True,
                "session_id": session_id,
                "total_segments": len(segments),
                "estimated_tokens": estimated_tokens,
                "message": f"Successfully retrieved all {len(segments)} segments from session"
            }
            
    except Exception as e:
        logger.error(f"Error pulling full session {session_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to pull full session: {str(e)}"
        }


def check_context_sufficiency() -> Dict[str, Any]:
    """
    Check if you have gathered sufficient context to generate a quality document.
    
    Returns information about accumulated segments, token usage, and coverage.
    Use this periodically to decide if you should continue exploring or generate the document.
    
    Returns:
        Dict with context metrics and sufficiency assessment
    """
    context = get_exploration_context()
    
    total_segments = len(context.accumulated_segments)
    tokens_used = context.tokens_used
    token_budget_remaining = context.token_budget - tokens_used
    budget_used_pct = (tokens_used / context.token_budget) * 100
    sessions_explored = len(context.sessions_explored)
    
    # Simple sufficiency heuristic
    is_sufficient = (
        total_segments >= 50 and  # At least 50 segments
        budget_used_pct >= 20  # Used at least 20% of budget
    )
    
    logger.info(f"Context check: {total_segments} segments, {tokens_used}/{context.token_budget} tokens ({budget_used_pct:.1f}%), {sessions_explored} sessions")
    
    return {
        "total_segments_collected": total_segments,
        "tokens_used": tokens_used,
        "token_budget": context.token_budget,
        "token_budget_remaining": token_budget_remaining,
        "budget_used_percentage": round(budget_used_pct, 1),
        "sessions_explored": sessions_explored,
        "is_sufficient": is_sufficient,
        "recommendation": "You have sufficient context to generate the document" if is_sufficient else "Continue exploring to gather more context",
        "message": f"Collected {total_segments} segments using {tokens_used}/{context.token_budget} tokens ({budget_used_pct:.1f}%) from {sessions_explored} sessions"
    }


def generate_document() -> Dict[str, Any]:
    """
    Signal that you're ready to generate the document with the accumulated context.
    
    This is the final tool call that ends the exploration phase.
    Call this only when you're confident you have sufficient context.
    
    Returns:
        Dict confirming readiness to generate
    """
    context = get_exploration_context()
    
    logger.info(f"Agent ready to generate document with {len(context.accumulated_segments)} segments")
    
    return {
        "ready_to_generate": True,
        "total_segments": len(context.accumulated_segments),
        "tokens_used": context.tokens_used,
        "sessions_explored": context.sessions_explored,
        "message": "Ready to generate document with accumulated context"
    }

