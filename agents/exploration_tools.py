"""
Exploration tools for the document generation agent.

These tools allow the agent to explore therapy sessions iteratively,
making decisions about how to retrieve and analyze content.
"""

import logging
import math
import os
import threading

import httpx
from contextvars import ContextVar
from typing import Dict, Any, List, Optional, Annotated
from utils.session_utils import estimate_tokens_from_segments

logger = logging.getLogger(__name__)

DOCUMENT_CONTEXT_TOKEN_BUDGET = 45_000


def _estimate_segment_tokens(segment: Dict[str, Any]) -> int:
    """Conservatively estimate rendered transcript tokens from its text."""
    rendered = f'{segment.get("speaker", "")}: {segment.get("text", "")}'
    return max(1, math.ceil((len(rendered.encode("utf-8")) + 32) / 4))


class ExplorationContext:
    """Shared context for exploration tools"""
    def __init__(self, target_session_count: int = 1):
        self.accumulated_segments: List[Dict[str, Any]] = []
        self.tokens_used: int = 0
        # The Foundry draft deployment has a 100k TPM allocation. Leave more
        # than half of that capacity for the template, notes, instructions,
        # output, and concurrent document-policy/language calls. A production
        # request with 1,313 segments previously reached ~98k input tokens,
        # retried until Azure closed the request, and surfaced as HTTP 499.
        self.token_budget: int = DOCUMENT_CONTEXT_TOKEN_BUDGET
        self.target_session_count = max(1, target_session_count)
        self.sessions_explored: List[str] = []
        self.authorization: Optional[str] = None
        # The caller's `profileid` HTTP header. Required when calling back to
        # the API: `ExtractProfileMiddleware` only populates `req.profile`
        # when this header is present, and several agent-tool endpoints
        # (segments-by-sessions, semantic-search) use `req.profile.id` as
        # the tenancy key. Without this forwarded header the API's filter
        # short-circuits to `[]` and the agent collects zero segments.
        self.profileid: Optional[str] = None
        self.generation_id: Optional[str] = None
        self._segment_ids: set = set()  # Track segment IDs for deduplication
        self._lock = threading.Lock()
        
    def add_segments(self, segments: List[Dict[str, Any]]) -> int:
        """Add deduplicated segments without exceeding the draft budget."""
        with self._lock:
            initial_count = len(self.accumulated_segments)
            duplicates_found = 0
            budget_limited = 0

            for segment in segments:
                # Create a unique identifier for each segment
                # Use combination of session_id, start_time, and text to identify duplicates
                segment_id = self._create_segment_id(segment)

                if segment_id in self._segment_ids:
                    duplicates_found += 1
                    continue

                estimated_tokens = _estimate_segment_tokens(segment)
                if self.tokens_used + estimated_tokens > self.token_budget:
                    budget_limited += 1
                    continue

                self._segment_ids.add(segment_id)
                self.accumulated_segments.append(segment)
                self.tokens_used += estimated_tokens

            new_segments_added = len(self.accumulated_segments) - initial_count

        # Log deduplication stats if duplicates were found
        if duplicates_found > 0:
            logger.info(f"🔍 Deduplication: Filtered {duplicates_found} duplicate segments, added {new_segments_added} new segments")
        if budget_limited > 0:
            logger.info(
                "Document context budget reached: retained %s estimated tokens and skipped %s additional segments",
                self.tokens_used,
                budget_limited,
            )
        return new_segments_added
    
    def _create_segment_id(self, segment: Dict[str, Any]) -> str:
        """Create a unique identifier for a segment to enable deduplication"""
        # Use multiple fields to create a robust unique identifier
        transcript_id = segment.get('transcript_id', segment.get('transcriptId', ''))
        start_time = segment.get('start_time', segment.get('startTime', 0))
        text = segment.get('text', '')
        
        # Create a hash of the key fields
        import hashlib
        unique_string = f"{transcript_id}_{start_time}_{text[:100]}"  # Use first 100 chars of text
        return hashlib.md5(unique_string.encode()).hexdigest()
        
    def has_budget(self, estimated_tokens: int) -> bool:
        """Check if there's budget for more tokens"""
        return (self.tokens_used + estimated_tokens) <= self.token_budget

    def remaining_token_capacity(self) -> int:
        return max(0, self.token_budget - self.tokens_used)

    def full_session_token_limit(self) -> int:
        """Reserve room for representative sessions across the therapy arc."""
        if self.target_session_count <= 3:
            planned_full_sessions = self.target_session_count
        elif self.target_session_count <= 10:
            planned_full_sessions = 4
        else:
            planned_full_sessions = 5
        return max(1, self.token_budget // planned_full_sessions)


# The service handles document generations concurrently. A module-global
# accumulator lets one request overwrite another request's clinical segments
# and credentials, so each task gets an independent context.
_exploration_context: ContextVar[Optional[ExplorationContext]] = ContextVar(
    "document_exploration_context", default=None
)


def get_exploration_context() -> ExplorationContext:
    """Get the current exploration context"""
    context = _exploration_context.get()
    if context is None:
        context = ExplorationContext()
        _exploration_context.set(context)
    return context


def reset_exploration_context(
    authorization: str = None,
    generation_id: str = None,
    profileid: str = None,
    target_session_count: int = 1,
):
    """Reset exploration context for a new document generation"""
    context = ExplorationContext(target_session_count=target_session_count)
    context.authorization = authorization
    context.profileid = profileid
    context.generation_id = generation_id
    _exploration_context.set(context)


def _evenly_sample_segments(segments: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """Retain beginning, middle, and end when a session exceeds its share."""
    if limit <= 0:
        return []
    if len(segments) <= limit:
        return segments
    if limit == 1:
        return [segments[0]]
    last_index = len(segments) - 1
    return [segments[round(position * last_index / (limit - 1))] for position in range(limit)]


def _sample_segments_within_token_budget(
    segments: List[Dict[str, Any]],
    token_budget: int,
) -> List[Dict[str, Any]]:
    """Evenly sample a session, then enforce its actual estimated token share."""
    if token_budget <= 0 or not segments:
        return []
    total_tokens = sum(_estimate_segment_tokens(segment) for segment in segments)
    if total_tokens <= token_budget:
        return segments
    average_tokens = max(1, math.ceil(total_tokens / len(segments)))
    target_count = max(1, min(len(segments), token_budget // average_tokens))
    sampled = _evenly_sample_segments(segments, target_count)
    retained: List[Dict[str, Any]] = []
    used_tokens = 0
    for segment in sampled:
        segment_tokens = _estimate_segment_tokens(segment)
        if used_tokens + segment_tokens <= token_budget:
            retained.append(segment)
            used_tokens += segment_tokens
    return retained


def _api_headers(context: "ExplorationContext") -> Dict[str, str]:
    """Build the header dict forwarded on every API tool callback.

    Both `Authorization` and `profileid` are required:
      - `Authorization` (JWT) passes the API's `IsUserGuard`.
      - `profileid` is consumed by `ExtractProfileMiddleware`, which sets
        `req.profile`. Without it, `req.profile.id` is undefined on the
        API side and the tenancy filter returns `[]`.
    """
    headers: Dict[str, str] = {}
    if context.authorization:
        headers["Authorization"] = context.authorization
    if context.profileid:
        headers["profileid"] = context.profileid
    return headers


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
    api_url = os.getenv("NESTJS_API_URL", "http://localhost:8080")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Use segments-by-sessions endpoint to get segments directly
            # (not semantic-search, which requires embeddings and may return 0 results)
            response = await client.post(
                f"{api_url}/api/v1/ai/transcripts/segments-by-sessions",
                json={
                    "session_ids": [session_id],
                    "limit_per_session": num_segments
                },
                headers=_api_headers(context)
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
    api_url = os.getenv("NESTJS_API_URL", "http://localhost:8080")
    
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
                headers=_api_headers(context)
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
            
            logger.info(f"Agent semantic search returned {len(segments)} results")
            
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
    api_url = os.getenv("NESTJS_API_URL", "http://localhost:8080")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Use the correct endpoint for fetching all segments (not semantic search!)
            response = await client.post(
                f"{api_url}/api/v1/ai/transcripts/segments-by-sessions",
                json={
                    "session_ids": [session_id],
                    "limit_per_session": 1000  # High limit to get all segments
                },
                headers=_api_headers(context)
            )
            response.raise_for_status()
            response_data = response.json()
            
            segments = response_data.get('segments', []) if isinstance(response_data, dict) else response_data
            
            estimated_tokens = estimate_tokens_from_segments(len(segments))
            remaining_tokens = context.remaining_token_capacity()
            if remaining_tokens <= 0:
                return {
                    "success": False,
                    "error": "Token budget exceeded",
                    "message": "The document context budget is full; use the collected context and generate the document",
                }

            retained_segments = _sample_segments_within_token_budget(
                segments,
                min(context.full_session_token_limit(), remaining_tokens),
            )

            # Add to context
            segments_added = context.add_segments(retained_segments)
            if segments_added and session_id not in context.sessions_explored:
                context.sessions_explored.append(session_id)
            
            logger.info(
                "Agent pulled session %s: retained %s/%s segments within document context budget",
                session_id,
                segments_added,
                len(segments),
            )
            
            return {
                "success": True,
                "session_id": session_id,
                "total_segments": len(segments),
                "segments_retained": segments_added,
                "estimated_source_tokens": estimated_tokens,
                "budget_limited": segments_added < len(segments),
                "message": (
                    f"Retrieved {len(segments)} segments and retained {segments_added} representative segments "
                    "for document generation"
                ),
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
    unique_segments = len(context._segment_ids)  # Track unique segments
    tokens_used = context.tokens_used
    token_budget_remaining = context.token_budget - tokens_used
    budget_used_pct = (tokens_used / context.token_budget) * 100
    sessions_explored = len(context.sessions_explored)
    
    # Simple sufficiency heuristic
    is_sufficient = (
        total_segments >= 50 and  # At least 50 segments
        budget_used_pct >= 20  # Used at least 20% of budget
    )
    
    logger.info(f"Context check: {total_segments} segments ({unique_segments} unique), {tokens_used}/{context.token_budget} tokens ({budget_used_pct:.1f}%), {sessions_explored} sessions")
    
    return {
        "total_segments_collected": total_segments,
        "unique_segments": unique_segments,
        "duplicate_segments_filtered": total_segments - unique_segments,
        "tokens_used": tokens_used,
        "token_budget": context.token_budget,
        "token_budget_remaining": token_budget_remaining,
        "budget_used_percentage": round(budget_used_pct, 1),
        "sessions_explored": sessions_explored,
        "is_sufficient": is_sufficient,
        "recommendation": "You have sufficient context to generate the document" if is_sufficient else "Continue exploring to gather more context",
        "message": f"Collected {total_segments} segments ({unique_segments} unique) using {tokens_used}/{context.token_budget} tokens ({budget_used_pct:.1f}%) from {sessions_explored} sessions"
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
