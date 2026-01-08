"""
Session utilities for fetching and estimating session metadata.
"""

import os
import httpx
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


async def fetch_session_metadata(session_id: str, authorization: str = None) -> Optional[Dict[str, Any]]:
    """
    Fetch metadata for a session including duration, segment count, and dates.
    
    Args:
        session_id: The transcript/session ID
        authorization: Authorization header for API requests
        
    Returns:
        Dict with keys: totalSegments, duration, recordingDate, createdAt, sessionId
        Returns None if fetch fails
    """
    try:
        api_url = os.getenv("API_URL", "http://localhost:8080")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {}
            if authorization:
                headers["Authorization"] = authorization
            
            response = await client.get(
                f"{api_url}/api/v1/ai/transcriptions/{session_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "sessionId": session_id,
                    "totalSegments": data.get("totalSegments", 0),
                    "duration": data.get("duration", 0),
                    "recordingDate": data.get("recordingDate"),
                    "createdAt": data.get("createdAt"),
                }
            else:
                logger.warning(f"Failed to fetch metadata for session {session_id}: HTTP {response.status_code}")
                return None
                
    except Exception as e:
        logger.error(f"Error fetching session metadata for {session_id}: {e}")
        return None


def estimate_tokens_from_segments(segment_count: int, avg_tokens_per_segment: int = 75) -> int:
    """
    Estimate token count from segment count.
    
    Uses conservative estimate of avg_tokens_per_segment.
    
    Args:
        segment_count: Number of segments in the session
        avg_tokens_per_segment: Average tokens per segment (default: 75)
        
    Returns:
        Estimated token count
    """
    return segment_count * avg_tokens_per_segment

