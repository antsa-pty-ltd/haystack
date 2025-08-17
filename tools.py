"""
Tool definitions and implementations for different personas
"""
import json
import logging
import aiohttp
import os
import jwt
from typing import Dict, Any, List, Callable, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class ToolManager:
    """Manages tools for different personas"""
    
    def __init__(self):
        from config import settings
        self.tools = self._initialize_tools()
        self.api_base_url = settings.nestjs_api_url
        self.auth_token = None  # Will be set per request
        self.profile_id = None  # Will be set per request
        self.current_page_context = None  # Current page context for tool execution
    
    def _initialize_tools(self) -> Dict[str, Dict[str, Any]]:
        """Initialize all available tools"""
        return {
            # Database/Admin Tools (for WEB_ASSISTANT)
            "get_client_summary": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "get_client_summary",
                        "description": "Get a detailed non-conversation summary of client information including recent sessions, notes, and treatment progress. Requires a client_id. If you only have a client name, use search_clients first to get the client_id. Do NOT use this for conversations or chat transcripts — for those use get_latest_conversation, get_conversations, or get_conversation_messages.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "client_id": {
                                    "type": "string",
                                    "description": "The unique identifier for the client (required). Must be a UUID returned by search_clients/get_conversations.",
                                    "pattern": "^[0-9a-fA-F-]{30,}$"
                                },
                                "include_recent_sessions": {
                                    "type": "boolean",
                                    "description": "Whether to include recent session data",
                                    "default": True
                                }
                            },
                            "required": ["client_id"]
                        }
                    }
                },
                "implementation": self._get_client_summary
            },
            
            "search_clients": {
                "definition": {
                    "type": "function", 
                    "function": {
                        "name": "search_clients",
                        "description": "Search for clients by name or ID to obtain a client_id for subsequent calls (e.g., get_client_summary or conversation tools).",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query (name, ID, etc.)"
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Maximum number of results to return",
                                    "default": 10
                                }
                            },
                            "required": ["query"]
                        }
                    }
                },
                "implementation": self._search_clients
            },
            
            "generate_report": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "generate_report",
                        "description": "Generate various types of reports (session summaries, treatment progress, etc.)",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "report_type": {
                                    "type": "string",
                                    "enum": ["session_summary", "treatment_progress", "billing_summary"],
                                    "description": "Type of report to generate"
                                },
                                "client_id": {
                                    "type": "string",
                                    "description": "Client ID for the report"
                                },
                                "date_range": {
                                    "type": "object",
                                    "properties": {
                                        "start_date": {"type": "string", "format": "date"},
                                        "end_date": {"type": "string", "format": "date"}
                                    }
                                }
                            },
                            "required": ["report_type", "client_id"]
                        }
                    }
                },
                "implementation": self._generate_report
            },

            "get_conversations": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "get_conversations",
                        "description": "Get all conversation threads (homework assignments) for a client. Use when the user asks to see all chats/threads with Jaimee.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "client_id": {
                                    "type": "string",
                                    "description": "Client ID to get conversations for (UUID returned by search_clients)",
                                    "pattern": "^[0-9a-fA-F-]{30,}$"
                                }
                            },
                            "required": ["client_id"]
                        }
                    }
                },
                "implementation": self._get_conversations
            },

            "get_conversation_messages": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "get_conversation_messages",
                        "description": "Get messages from a specific conversation thread with Jaimee (requires assignment_id). Use after listing conversations if the user wants a particular thread.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "client_id": {
                                    "type": "string",
                                    "description": "Client ID (UUID returned by search_clients)",
                                    "pattern": "^[0-9a-fA-F-]{30,}$"
                                },
                                "assignment_id": {
                                    "type": "string",
                                    "description": "Assignment ID (conversation thread ID, UUID returned by get_conversations/get_latest_conversation)",
                                    "pattern": "^[0-9a-fA-F-]{30,}$"
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Maximum number of messages to return",
                                    "default": 100
                                },
                                "offset": {
                                    "type": "integer",
                                    "description": "Number of messages to skip (for pagination)",
                                    "default": 0
                                }
                            },
                            "required": ["client_id", "assignment_id"]
                        }
                    }
                },
                "implementation": self._get_conversation_messages
            },

            "get_latest_conversation": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "get_latest_conversation",
                        "description": "Get the latest conversation between a client and Jaimee AI assistant (recent chat/messages). Use for queries like 'latest chat', 'recent messages', 'what did they talk about'.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "client_id": {
                                    "type": "string",
                                    "description": "Client ID to get latest conversation for (UUID returned by search_clients)",
                                    "pattern": "^[0-9a-fA-F-]{30,}$"
                                },
                                "message_limit": {
                                    "type": "integer",
                                    "description": "Maximum number of recent messages to return",
                                    "default": 50
                                }
                            },
                            "required": ["client_id"]
                        }
                    }
                },
                "implementation": self._get_latest_conversation
            },

            # Session Management Tools (for WEB_ASSISTANT)
            "search_sessions": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "search_sessions",
                        "description": "Search for transcription sessions by client name, date range, or keywords. Use for queries like 'John's latest session', 'sessions from last week', 'find sessions about anxiety'.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "client_name": {
                                    "type": "string",
                                    "description": "Name of the client to search sessions for"
                                },
                                "client_id": {
                                    "type": "string",
                                    "description": "Client ID to search sessions for (UUID)"
                                },
                                "date_from": {
                                    "type": "string",
                                    "format": "date",
                                    "description": "Start date for date range filter (YYYY-MM-DD)"
                                },
                                "date_to": {
                                    "type": "string", 
                                    "format": "date",
                                    "description": "End date for date range filter (YYYY-MM-DD)"
                                },
                                "keywords": {
                                    "type": "string",
                                    "description": "Keywords to search for in session content"
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Maximum number of sessions to return",
                                    "default": 10
                                }
                            }
                        }
                    }
                },
                "implementation": self._search_sessions
            },

            "load_session": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "load_session",
                        "description": "Load a specific session with its transcript segments. Returns session details and transcript content for analysis.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "session_id": {
                                    "type": "string",
                                    "description": "Session ID to load (returned by search_sessions)"
                                },
                                "client_id": {
                                    "type": "string", 
                                    "description": "Client ID that owns this session"
                                },
                                "include_segments": {
                                    "type": "boolean",
                                    "description": "Whether to include detailed transcript segments",
                                    "default": True
                                }
                            },
                            "required": ["session_id", "client_id"]
                        }
                    }
                },
                "implementation": self._load_session
            },

            "validate_sessions": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "validate_sessions",
                        "description": "Validate that sessions have available transcript content before loading. Use this before load_session_direct or load_multiple_sessions to avoid 404 errors.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "sessions": {
                                    "type": "array",
                                    "description": "Array of session objects to validate",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "session_id": {
                                                "type": "string",
                                                "description": "Session ID to validate"
                                            },
                                            "client_id": {
                                                "type": "string",
                                                "description": "Client ID that owns this session"
                                            }
                                        },
                                        "required": ["session_id", "client_id"]
                                    }
                                }
                            },
                            "required": ["sessions"]
                        }
                    }
                },
                "implementation": self._validate_sessions
            },

            "get_loaded_sessions": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "get_loaded_sessions",
                        "description": "Get list of sessions currently loaded in the UI that user can ask questions about. Use this to see what session content is available for analysis.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    }
                },
                "implementation": self._get_loaded_sessions
            },

            "get_session_content": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "get_session_content",
                        "description": "Get the full transcript content of a specific loaded session for analysis. Use this to access session content for answering user questions.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "session_id": {
                                    "type": "string",
                                    "description": "Session ID to get content for (must be currently loaded in UI)"
                                }
                            },
                            "required": ["session_id"]
                        }
                    }
                },
                "implementation": self._get_session_content
            },

            "analyze_loaded_session": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "analyze_loaded_session",
                        "description": "Analyze a currently loaded session for themes, topics, sentiment, key quotes, or summaries. Use this to answer user questions about session content.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "session_id": {
                                    "type": "string",
                                    "description": "Session ID to analyze (must be currently loaded in UI)"
                                },
                                "analysis_type": {
                                    "type": "string",
                                    "enum": ["summary", "themes", "topics", "sentiment", "key_quotes", "comprehensive"],
                                    "description": "Type of analysis to perform"
                                },
                                "specific_question": {
                                    "type": "string",
                                    "description": "Optional: Specific question to answer about the session (e.g., 'What coping strategies were discussed?')"
                                }
                            },
                            "required": ["session_id", "analysis_type"]
                        }
                    }
                },
                "implementation": self._analyze_loaded_session
            },

            "analyze_session_content": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "analyze_session_content",
                        "description": "Analyze session content for themes, sentiment, key topics, and insights. Use after loading a session.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "session_id": {
                                    "type": "string",
                                    "description": "Session ID to analyze"
                                },
                                "client_id": {
                                    "type": "string",
                                    "description": "Client ID that owns this session"
                                },
                                "analysis_type": {
                                    "type": "string",
                                    "enum": ["summary", "sentiment", "topics", "themes", "comprehensive"],
                                    "description": "Type of analysis to perform",
                                    "default": "comprehensive"
                                }
                            },
                            "required": ["session_id", "client_id"]
                        }
                    }
                },
                "implementation": self._analyze_session_content
            },



            # Simplified UI Integration Tools (for WEB_ASSISTANT) - mimic manual UI interactions
            "set_client_selection": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "set_client_selection",
                        "description": "Set the client selection in the UI (like selecting from AutoComplete). Call this FIRST before loading any sessions.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "client_name": {
                                    "type": "string",
                                    "description": "Client name to select in the UI"
                                },
                                "client_id": {
                                    "type": "string",
                                    "description": "Client ID to select in the UI"
                                }
                            },
                            "required": ["client_name", "client_id"]
                        }
                    }
                },
                "implementation": self._set_client_selection
            },

            "load_session_direct": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "load_session_direct",
                        "description": "Load a session directly using existing UI logic (like clicking Load Session button). Call AFTER setting client selection.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "session_id": {
                                    "type": "string",
                                    "description": "Session ID to load"
                                },
                                "client_id": {
                                    "type": "string",
                                    "description": "Client ID that owns this session"
                                },
                                "client_name": {
                                    "type": "string",
                                    "description": "Client name for the session"
                                },
                                "recording_date": {
                                    "type": "string",
                                    "description": "ISO date string of when the session was recorded"
                                },
                                "duration": {
                                    "type": "number",
                                    "description": "Duration of the session in seconds"
                                },
                                "total_segments": {
                                    "type": "integer",
                                    "description": "Total number of transcript segments"
                                },
                                "average_confidence": {
                                    "type": "number",
                                    "description": "Average confidence score of the transcript"
                                }
                            },
                            "required": ["session_id", "client_id", "client_name", "recording_date", "duration", "total_segments", "average_confidence"]
                        }
                    }
                },
                "implementation": self._load_session_direct
            },

            "load_multiple_sessions": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "load_multiple_sessions",
                        "description": "Load multiple sessions as separate tabs in the UI. Use when user requests to load several sessions at once (e.g. 'load session 1 and 3'). Call AFTER setting client selection.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "sessions": {
                                    "type": "array",
                                    "description": "Array of session objects to load",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "session_id": {
                                                "type": "string",
                                                "description": "Session ID to load"
                                            },
                                            "client_id": {
                                                "type": "string",
                                                "description": "Client ID that owns this session"
                                            },
                                            "client_name": {
                                                "type": "string",
                                                "description": "Client name for the session"
                                            },
                                            "recording_date": {
                                                "type": "string",
                                                "description": "ISO date string of when the session was recorded"
                                            },
                                            "duration": {
                                                "type": "number",
                                                "description": "Duration of the session in seconds"
                                            },
                                            "total_segments": {
                                                "type": "integer",
                                                "description": "Total number of transcript segments"
                                            },
                                            "average_confidence": {
                                                "type": "number",
                                                "description": "Average confidence score of the transcript"
                                            }
                                        },
                                        "required": ["session_id", "client_id", "client_name", "recording_date", "duration", "total_segments", "average_confidence"]
                                    }
                                }
                            },
                            "required": ["sessions"]
                        }
                    }
                },
                "implementation": self._load_multiple_sessions
            },

            # Template tools
            "get_templates": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "get_templates",
                        "description": "Get all available document templates from the API for template selection and document generation",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "template_type": {
                                    "type": "string",
                                    "enum": ["all", "private", "clinic", "public"],
                                    "description": "Filter templates by type",
                                    "default": "all"
                                },
                                "search_query": {
                                    "type": "string",
                                    "description": "Optional search query to filter templates by name or description"
                                }
                            },
                            "required": []
                        }
                    }
                },
                "implementation": self._get_templates
            },
            "set_selected_template": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "set_selected_template",
                        "description": "Set the active template in the UI for document generation (like clicking on a template in the templates modal)",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "template_id": {
                                    "type": "string",
                                    "description": "The unique identifier for the template"
                                },
                                "template_name": {
                                    "type": "string",
                                    "description": "The name of the template"
                                },
                                "template_content": {
                                    "type": "string",
                                    "description": "The template content/body text"
                                },
                                "template_description": {
                                    "type": "string",
                                    "description": "Description of the template",
                                    "default": ""
                                }
                            },
                            "required": ["template_id", "template_name", "template_content"]
                        }
                    }
                },
                "implementation": self._set_selected_template
            },

            # Generate document from loaded sessions and a template
            "generate_document_from_loaded": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "generate_document_from_loaded",
                        "description": "Generate a document in the UI using the provided template content and sessions currently loaded in the interface.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "template_content": {
                                    "type": "string",
                                    "description": "The full template text to use for generation"
                                },
                                "template_name": {
                                    "type": "string",
                                    "description": "Optional template name for display"
                                },
                                "document_name": {
                                    "type": "string",
                                    "description": "Optional target document name"
                                },
                                "sessions": {
                                    "type": "array",
                                    "description": "Optional array of sessions. If omitted, the tool will use sessions currently loaded in the UI",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "session_id": {"type": "string"},
                                            "client_id": {"type": "string"},
                                            "client_name": {"type": "string"},
                                            "metadata": {"type": "object"}
                                        }
                                    }
                                }
                            },
                            "required": ["template_content"]
                        }
                    }
                },
                "implementation": self._generate_document_from_loaded
            },

            # Navigation Tools
            "suggest_navigation": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "suggest_navigation",
                        "description": "Suggest navigation to user when current page doesn't support requested action. Use when page validation fails.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "current_page": {
                                    "type": "string",
                                    "description": "Current page type the user is on"
                                },
                                "suggested_page": {
                                    "type": "string",
                                    "description": "Page type that supports the requested action"
                                },
                                "reason": {
                                    "type": "string",
                                    "description": "Why navigation is needed"
                                },
                                "required_for_action": {
                                    "type": "string",
                                    "description": "What action requires this navigation"
                                }
                            },
                            "required": ["current_page", "suggested_page", "reason", "required_for_action"]
                        }
                    }
                },
                "implementation": self._suggest_navigation
            },

            "navigate_to_page": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "navigate_to_page",
                        "description": "Navigate user to a specific page (use sparingly, prefer suggesting navigation). Only use when user explicitly requests navigation.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "page_url": {
                                    "type": "string",
                                    "description": "Target page URL path"
                                },
                                "page_type": {
                                    "type": "string",
                                    "description": "Type of page to navigate to"
                                },
                                "params": {
                                    "type": "object",
                                    "description": "URL parameters to include",
                                    "additionalProperties": {"type": "string"}
                                },
                                "reason": {
                                    "type": "string",
                                    "description": "Why navigation is needed"
                                }
                            },
                            "required": ["page_url", "page_type", "reason"]
                        }
                    }
                },
                "implementation": self._navigate_to_page
            },


            
            # Therapeutic Tools (for JAIMEE_THERAPIST)
            "mood_check_in": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "mood_check_in",
                        "description": "Guide user through a mood assessment and provide insights",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "current_mood": {
                                    "type": "string",
                                    "description": "User's current mood description"
                                },
                                "mood_scale": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 10,
                                    "description": "Mood rating on 1-10 scale"
                                }
                            },
                            "required": ["current_mood", "mood_scale"]
                        }
                    }
                },
                "implementation": self._mood_check_in
            },
            
            "coping_strategies": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "coping_strategies",
                        "description": "Provide personalized coping strategies based on user's current situation",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "situation": {
                                    "type": "string",
                                    "description": "Description of the current situation or challenge"
                                },
                                "preferred_techniques": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "User's preferred coping techniques (if any)"
                                }
                            },
                            "required": ["situation"]
                        }
                    }
                },
                "implementation": self._coping_strategies
            },
            
            "breathing_exercise": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "breathing_exercise",
                        "description": "Guide user through a breathing exercise for relaxation",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "exercise_type": {
                                    "type": "string",
                                    "enum": ["box_breathing", "4_7_8", "belly_breathing"],
                                    "description": "Type of breathing exercise",
                                    "default": "box_breathing"
                                },
                                "duration_minutes": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 15,
                                    "description": "Duration of exercise in minutes",
                                    "default": 5
                                }
                            }
                        }
                    }
                },
                "implementation": self._breathing_exercise
            }
        }
    
    def get_tools_for_persona(self, persona_type: str) -> List[Dict[str, Any]]:
        """Get tool definitions for a specific persona"""
        if persona_type == "web_assistant":
            return [
                self.tools["get_client_summary"]["definition"],
                self.tools["search_clients"]["definition"], 
                self.tools["generate_report"]["definition"],
                self.tools["get_conversations"]["definition"],
                self.tools["get_conversation_messages"]["definition"],
                self.tools["get_latest_conversation"]["definition"],
                self.tools["search_sessions"]["definition"],
                self.tools["validate_sessions"]["definition"],
                self.tools["load_session"]["definition"],
                self.tools["analyze_session_content"]["definition"],
                self.tools["set_client_selection"]["definition"],
                self.tools["load_session_direct"]["definition"],
                self.tools["load_multiple_sessions"]["definition"],
                self.tools["suggest_navigation"]["definition"],
                self.tools["navigate_to_page"]["definition"],
                self.tools["get_loaded_sessions"]["definition"],
                self.tools["get_session_content"]["definition"],
                self.tools["analyze_loaded_session"]["definition"],
                self.tools["get_templates"]["definition"],
                self.tools["set_selected_template"]["definition"],
                self.tools["generate_document_from_loaded"]["definition"]
            ]
        elif persona_type == "jaimee_therapist":
            return [
                self.tools["mood_check_in"]["definition"],
                self.tools["coping_strategies"]["definition"],
                self.tools["breathing_exercise"]["definition"]
            ]
        else:
            return []
    
    def get_functions_for_persona(self, persona_type: str) -> Dict[str, Callable]:
        """Get function implementations for a specific persona"""
        if persona_type == "web_assistant":
            return {
                "get_client_summary": self.tools["get_client_summary"]["implementation"],
                "search_clients": self.tools["search_clients"]["implementation"],
                "generate_report": self.tools["generate_report"]["implementation"],
                "get_conversations": self.tools["get_conversations"]["implementation"],
                "get_conversation_messages": self.tools["get_conversation_messages"]["implementation"],
                "get_latest_conversation": self.tools["get_latest_conversation"]["implementation"],
                "search_sessions": self.tools["search_sessions"]["implementation"],
                "validate_sessions": self.tools["validate_sessions"]["implementation"],
                "load_session": self.tools["load_session"]["implementation"],
                "analyze_session_content": self.tools["analyze_session_content"]["implementation"],
                "set_client_selection": self.tools["set_client_selection"]["implementation"],
                "load_session_direct": self.tools["load_session_direct"]["implementation"],
                "load_multiple_sessions": self.tools["load_multiple_sessions"]["implementation"],
                "suggest_navigation": self.tools["suggest_navigation"]["implementation"],
                "navigate_to_page": self.tools["navigate_to_page"]["implementation"],
                "get_loaded_sessions": self.tools["get_loaded_sessions"]["implementation"],
                "get_session_content": self.tools["get_session_content"]["implementation"],
                "analyze_loaded_session": self.tools["analyze_loaded_session"]["implementation"],
                "get_templates": self.tools["get_templates"]["implementation"],
                "set_selected_template": self.tools["set_selected_template"]["implementation"],
                "generate_document_from_loaded": self.tools["generate_document_from_loaded"]["implementation"]
            }
        elif persona_type == "jaimee_therapist":
            return {
                "mood_check_in": self.tools["mood_check_in"]["implementation"],
                "coping_strategies": self.tools["coping_strategies"]["implementation"], 
                "breathing_exercise": self.tools["breathing_exercise"]["implementation"]
            }
        else:
            return {}
    
    def set_auth_token(self, token: str, profile_id: Optional[str] = None):
        """Set the JWT token for API calls and optionally set profile ID"""
        self.auth_token = token
        
        # Set profile ID if provided
        if profile_id:
            self.profile_id = profile_id
            logger.info(f"Profile ID set explicitly: {profile_id}")
        else:
            # Try to extract profile ID from JWT token as fallback
            try:
                # Decode JWT without verification (we just need the payload)
                # In production, you'd want to verify the token properly
                decoded = jwt.decode(token, options={"verify_signature": False})
                
                # Try different possible profile ID fields in the JWT
                profile_id_from_jwt = decoded.get('profileId') or decoded.get('profile_id') or decoded.get('sub')
                
                if profile_id_from_jwt:
                    self.profile_id = profile_id_from_jwt
                    logger.info(f"Extracted profile ID from JWT: {profile_id_from_jwt}")
                else:
                    logger.warning("No profile ID found in JWT token")
                    
            except Exception as e:
                logger.error(f"Failed to decode JWT token: {e}")

    def set_page_context(self, page_context: Dict[str, Any]):
        """Set the current page context for tool execution"""
        self.current_page_context = page_context
        logger.info(f"📄 Page context set: {page_context.get('page_type', 'unknown')} with capabilities: {page_context.get('capabilities', [])}")
    
    def set_profile_id(self, profile_id: str):
        """Set the profile ID for API calls"""
        self.profile_id = profile_id
    
    async def _make_api_request(self, method: str, endpoint: str, data: Dict = None, params: Dict = None) -> Dict[str, Any]:
        """Make authenticated API request to NestJS backend"""
        if not self.auth_token:
            raise ValueError("No auth token set for API requests")
        
        headers = {
            'Authorization': f'Bearer {self.auth_token}',
            'Content-Type': 'application/json'
        }
        
        # Add profile ID header if available
        if hasattr(self, 'profile_id') and self.profile_id:
            headers['profileid'] = self.profile_id
        
        # Add api/v1 prefix to match NestJS global prefix
        endpoint_clean = endpoint.lstrip('/')
        if not endpoint_clean.startswith('api/v1/'):
            endpoint_clean = f"api/v1/{endpoint_clean}"
        url = f"{self.api_base_url}/{endpoint_clean}"
        
        try:
            async with aiohttp.ClientSession() as session:
                if method.upper() == 'GET':
                    async with session.get(url, headers=headers, params=params) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            error_text = await response.text()
                            raise Exception(f"API request failed: {response.status} - {error_text}")
                elif method.upper() == 'POST':
                    async with session.post(url, headers=headers, json=data) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            error_text = await response.text()
                            raise Exception(f"API request failed: {response.status} - {error_text}")
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
        except aiohttp.ClientError as e:
            logger.error(f"Network error making API request to {url}: {e}")
            raise Exception(f"Network error: {e}")
        except Exception as e:
            logger.error(f"Error making API request to {url}: {e}")
            raise
    
    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool function"""
        try:
            if tool_name not in self.tools:
                raise ValueError(f"Unknown tool: {tool_name}")
            
            implementation = self.tools[tool_name]["implementation"]
            
            # For UI-related tools, inject page context if available and tool supports it
            ui_tools_with_context = ['set_client_selection', 'load_session_direct', 'load_multiple_sessions', 'set_selected_template']
            
            if tool_name in ui_tools_with_context and self.current_page_context:
                # Add page_context to arguments if the tool function signature supports it
                import inspect
                sig = inspect.signature(implementation)
                if 'page_context' in sig.parameters:
                    arguments['page_context'] = self.current_page_context
                    logger.info(f"🔄 Injecting page context into {tool_name}: {self.current_page_context.get('page_type', 'unknown')}")
            elif tool_name in ui_tools_with_context:
                logger.warning(f"⚠️ Tool {tool_name} is UI-related but no page context available")
            
            result = await implementation(**arguments)
            
            return {
                "success": True,
                "result": result,
                "tool": tool_name,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return {
                "success": False,
                "error": str(e),
                "tool": tool_name,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    # Tool implementations
    async def _get_templates(self, template_type: str = "all", search_query: Optional[str] = None) -> Dict[str, Any]:
        """Get all available templates from the API"""
        try:
            logger.info("🔧 get_templates called - fetching templates from API")
            # Optional filters (currently not enforced server-side, but accepted to avoid arg errors)
            params: Dict[str, Any] = {}
            if template_type and template_type in ["all", "private", "clinic", "public"]:
                params["type"] = template_type
            if search_query:
                params["q"] = search_query

            response = await self._make_api_request('GET', 'templates', params=params)
            if not response:
                return {
                    "templates": [],
                    "count": 0,
                    "status": "no_templates_found"
                }
            templates = response.get('data', response) if isinstance(response, dict) else response
            formatted_templates = []
            for template in templates:
                formatted_template = {
                    "id": template.get('id'),
                    "name": template.get('name'),
                    "description": template.get('description', ''),
                    "content": template.get('content', ''),
                    "tags": template.get('tags', []),
                    "isPrivate": template.get('isPrivate', False),
                    "clinicId": template.get('clinicId'),
                    "createdBy": template.get('createdBy'),
                    "usageCount": template.get('usageCount', 0)
                }
                formatted_templates.append(formatted_template)
            logger.info(f"📋 Retrieved {len(formatted_templates)} templates from API")
            return {
                "templates": formatted_templates,
                "count": len(formatted_templates),
                "status": "success"
            }
        except Exception as e:
            logger.error(f"Error in get_templates: {e}")
            return {
                "templates": [],
                "count": 0,
                "error": f"Failed to get templates: {str(e)}",
                "status": "error"
            }

    async def _set_selected_template(self, template_id: str, template_name: str, template_content: str, template_description: str = "", page_context: dict = None) -> Dict[str, Any]:
        """Set the active template in the UI for document generation"""
        try:
            logger.info(f"📋 set_selected_template called: {template_name} (ID: {template_id})")
            if page_context:
                page_type = page_context.get('page_type', 'unknown')
                available_capabilities = page_context.get('capabilities', [])
                if 'set_selected_template' not in available_capabilities and page_type != 'unknown':
                    logger.info(f"🚫 Blocking set_selected_template on page '{page_type}', suggesting navigation instead")
                    sessions_url = "/live-transcribe"
                    return {
                        "template_id": template_id,
                        "template_name": template_name,
                        "status": "navigation_required",
                        "user_message": f"To select the '{template_name}' template, you need to be on the Sessions page. Please click the link below:",
                        "navigation_link": {
                            "text": "Go to Sessions Page",
                            "url": sessions_url,
                            "page_type": "transcribe_page"
                        },
                        "instructions": f"Once you're on the Sessions page, ask me again to select the {template_name} template and I'll be able to help!"
                    }
            return {
                "template_id": template_id,
                "template_name": template_name,
                "ui_action": {
                    "type": "set_selected_template",
                    "target": "live_transcribe_page",
                    "payload": {
                        "templateId": template_id,
                        "templateName": template_name,
                        "templateContent": template_content,
                        "templateDescription": template_description
                    }
                },
                "status": "ui_action_requested",
                "user_message": f"Selected template '{template_name}' for document generation. You can now generate documents using this template."
            }
        except Exception as e:
            logger.error(f"Error in set_selected_template: {e}")
            return {
                "template_id": template_id,
                "template_name": template_name,
                "error": f"Failed to set selected template: {str(e)}",
                "status": "error"
            }

    async def _generate_document_from_loaded(self, template_content: str, template_name: str = None, document_name: str = None, sessions: List[Dict[str, Any]] = None, page_context: dict = None) -> Dict[str, Any]:
        """Generate a document in the UI using template content and loaded sessions"""
        try:
            # If sessions not provided, read from UI state
            from ui_state_manager import ui_state_manager
            ui_sessions = []
            if page_context:
                # Use the most recent UI state
                all_summary = ui_state_manager.get_all_sessions_summary()
                if all_summary:
                    latest_session_id = max(all_summary.keys(), key=lambda k: all_summary[k].get('last_updated', ''))
                    ui_sessions = ui_state_manager.get_loaded_sessions(latest_session_id)
            
            selected_sessions = sessions or [
                {
                    "session_id": s.get("sessionId"),
                    "client_id": s.get("clientId"),
                    "client_name": s.get("clientName"),
                    "metadata": s.get("metadata", {})
                }
                for s in ui_sessions if s.get("sessionId")
            ]

            # Build UI action payload
            action_payload = {
                "templateContent": template_content,
                "templateName": template_name or "Template",
                "documentName": document_name or template_name or "Generated Document",
                "sessions": selected_sessions
            }

            return {
                "ui_action": {
                    "type": "generate_document_from_loaded",
                    "target": "live_transcribe_page",
                    "payload": action_payload
                },
                "status": "ui_action_requested",
                "user_message": f"Generating document '{action_payload['documentName']}' using {len(selected_sessions)} loaded session(s). It will open as a new tab shortly."
            }
        except Exception as e:
            logger.error(f"Error in generate_document_from_loaded: {e}")
            return {
                "error": f"Failed to generate document: {str(e)}",
                "status": "error"
            }
    async def _get_client_summary(self, client_id: str, include_recent_sessions: bool = True) -> Dict[str, Any]:
        """Get client summary from API"""
        try:
            # Debug logging to see what parameters we're getting
            logger.info(f"🔍 get_client_summary called with: client_id={client_id}")
            
            if not client_id:
                return {
                    "error": "client_id is required",
                    "status": "Invalid Request"
                }
            
            params = {
                'client_id': client_id,
                'include_recent_sessions': str(include_recent_sessions).lower()
            }
            
            response = await self._make_api_request('GET', '/haystack/client-summary', params=params)
            
            # Transform API response to expected format
            result = {
                "client_id": response.get("client_id", client_id),
                "name": response.get("name", "Unknown Client"),
                "status": response.get("status", "Unknown"),
                "last_session": response.get("last_session"),
                "treatment_progress": response.get("treatment_progress", "No progress data available"),
                "recent_sessions": response.get("recent_sessions"),
                "notes": response.get("notes", "No additional notes"),
                "age": response.get("age"),
                "gender": response.get("gender"),
                "occupation": response.get("occupation"),
                "diagnosis": response.get("diagnosis"),
                "medication": response.get("medication"),
                "assignment_stats": response.get("assignment_stats", {}),
                "last_activity": response.get("last_activity")
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting client summary: {e}")
            return {
                "client_id": client_id,
                "name": "Client (API Error)",
                "status": "Unknown",
                "error": f"Failed to fetch client data: {str(e)}",
                "last_session": None,
                "treatment_progress": "Unable to retrieve progress data",
                "recent_sessions": None,
                "notes": "Error accessing client information"
            }
    
    async def _search_clients(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search clients via API"""
        try:

            params = {
                'query': query,
                'limit': limit
            }
            
            response = await self._make_api_request('GET', '/haystack/search-clients', params=params)
            clients = response.get('clients', [])
            
            # Transform API response to expected format
            return [
                {
                    "client_id": client.get("client_id"),
                    "name": client.get("name", "Unknown Client"),
                    "status": client.get("status", "Unknown"),
                    "last_session": client.get("last_session"),
                    "last_activity": client.get("last_activity"),
                    "active_assignments": client.get("active_assignments", 0),
                    "total_assignments": client.get("total_assignments", 0),
                    "recent_messages": client.get("recent_messages", 0),
                    "age": client.get("age"),
                    "gender": client.get("gender"),
                    "occupation": client.get("occupation")
                }
                for client in clients
            ]
            
        except Exception as e:
            logger.error(f"Error searching clients: {e}")
            # Fallback response
            return [
                {
                    "client_id": "error",
                    "name": f"Search Error for '{query}'",
                    "status": "Error",
                    "error": f"Failed to search: {str(e)}",
                    "last_session": None
                }
            ]
    
    async def _generate_report(self, report_type: str, client_id: str, date_range: Optional[Dict] = None) -> Dict[str, Any]:
        """Generate report via API"""
        try:
            data = {
                'report_type': report_type,
                'client_id': client_id
            }
            
            if date_range:
                data['date_range'] = date_range
            
            response = await self._make_api_request('POST', '/haystack/generate-report', data=data)
            
            # Transform API response to expected format
            return {
                "report_type": response.get("report_type", report_type),
                "client_id": response.get("client_id", client_id),
                "generated_at": response.get("generated_at", datetime.utcnow().isoformat()),
                "summary": response.get("summary", f"{report_type} report generated successfully"),
                "data": response.get("data", {}),
                "date_range": response.get("date_range", date_range)
            }
            
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            # Fallback response
            return {
                "report_type": report_type,
                "client_id": client_id,
                "generated_at": datetime.utcnow().isoformat(),
                "summary": f"Error generating {report_type} report for client {client_id}",
                "error": f"Failed to generate report: {str(e)}",
                "data": {"error": "Report generation failed"}
            }
    
    async def _get_conversations(self, client_id: str) -> Dict[str, Any]:
        """Get all conversation threads for a client"""
        try:
            logger.info(f"🔍 get_conversations called with: client_id={client_id}")
            
            if not client_id:
                return {
                    "error": "client_id is required",
                    "status": "Invalid Request"
                }
            
            params = {'client_id': client_id}
            response = await self._make_api_request('GET', '/haystack/conversations', params=params)
            
            return {
                "client_id": response.get("client_id", client_id),
                "client_name": response.get("client_name", "Unknown Client"),
                "conversations": response.get("conversations", []),
                "total": response.get("total", 0)
            }
            
        except Exception as e:
            logger.error(f"Error getting conversations: {e}")
            return {
                "client_id": client_id,
                "client_name": "Unknown Client",
                "error": f"Failed to get conversations: {str(e)}",
                "conversations": [],
                "total": 0
            }
    
    async def _get_conversation_messages(self, client_id: str, assignment_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get messages from a specific conversation thread"""
        try:
            logger.info(f"🔍 get_conversation_messages called with: client_id={client_id}, assignment_id={assignment_id}")
            
            if not client_id or not assignment_id:
                return {
                    "error": "client_id and assignment_id are required",
                    "status": "Invalid Request"
                }
            
            params = {
                'client_id': client_id,
                'assignment_id': assignment_id,
                'limit': str(limit),
                'offset': str(offset)
            }
            
            response = await self._make_api_request('GET', '/haystack/conversation-messages', params=params)
            
            return {
                "assignment_id": response.get("assignment_id", assignment_id),
                "client_id": response.get("client_id", client_id),
                "client_name": response.get("client_name", "Unknown Client"),
                "homework_title": response.get("homework_title", "Unknown Assignment"),
                "messages": response.get("messages", []),
                "total_messages": response.get("total_messages", 0),
                "first_message_date": response.get("first_message_date"),
                "last_message_date": response.get("last_message_date")
            }
            
        except Exception as e:
            logger.error(f"Error getting conversation messages: {e}")
            return {
                "assignment_id": assignment_id,
                "client_id": client_id,
                "client_name": "Unknown Client", 
                "homework_title": "Unknown Assignment",
                "error": f"Failed to get conversation messages: {str(e)}",
                "messages": [],
                "total_messages": 0
            }
    
    async def _get_latest_conversation(self, client_id: str, message_limit: int = 50) -> Dict[str, Any]:
        """Get the latest conversation for a client"""
        try:
            logger.info(f"🔍 get_latest_conversation called with: client_id={client_id}, message_limit={message_limit}")
            
            if not client_id:
                return {
                    "error": "client_id is required",
                    "status": "Invalid Request"
                }
            
            params = {
                'client_id': client_id,
                'message_limit': str(message_limit)
            }
            
            response = await self._make_api_request('GET', '/haystack/latest-conversation', params=params)
            
            return {
                "client_id": response.get("client_id", client_id),
                "client_name": response.get("client_name", "Unknown Client"),
                "latest_assignment_id": response.get("latest_assignment_id"),
                "homework_title": response.get("homework_title"),
                "recent_messages": response.get("recent_messages", []),
                "message_count": response.get("message_count", 0),
                "last_activity": response.get("last_activity")
            }
            
        except Exception as e:
            logger.error(f"Error getting latest conversation: {e}")
            return {
                "client_id": client_id,
                "client_name": "Unknown Client",
                "error": f"Failed to get latest conversation: {str(e)}",
                "recent_messages": [],
                "message_count": 0
            }
    
    async def _mood_check_in(self, current_mood: str, mood_scale: int) -> Dict[str, Any]:
        """Process mood check-in"""
        insights = []
        
        if mood_scale <= 3:
            insights.append("I notice you're having a difficult time. That takes courage to share.")
            insights.append("Remember that difficult emotions are temporary and valid.")
        elif mood_scale <= 6:
            insights.append("It sounds like you're experiencing some challenges today.")
            insights.append("Let's explore what might help you feel more balanced.")
        else:
            insights.append("I'm glad to hear you're feeling relatively well today.")
            insights.append("What's contributing to this positive mood?")
        
        return {
            "mood": current_mood,
            "scale": mood_scale,
            "insights": insights,
            "suggestions": ["Consider journaling about this mood", "Practice gratitude", "Connect with supportive people"]
        }
    
    async def _coping_strategies(self, situation: str, preferred_techniques: List[str] = None) -> Dict[str, Any]:
        """Provide coping strategies"""
        strategies = {
            "immediate": [
                "Take three deep breaths",
                "Ground yourself using the 5-4-3-2-1 technique",
                "Practice progressive muscle relaxation"
            ],
            "short_term": [
                "Go for a walk or light exercise",
                "Call a trusted friend or family member",
                "Engage in a creative activity"
            ],
            "long_term": [
                "Establish a regular sleep schedule",
                "Practice mindfulness meditation",
                "Consider journaling regularly"
            ]
        }
        
        return {
            "situation_acknowledged": situation,
            "strategies": strategies,
            "personalized_note": "These strategies are tailored to help you navigate this situation. Try what feels right for you.",
            "reminder": "Remember, it's okay to ask for professional help if you need additional support."
        }
    
    async def _breathing_exercise(self, exercise_type: str = "box_breathing", duration_minutes: int = 5) -> Dict[str, Any]:
        """Guide breathing exercise"""
        exercises = {
            "box_breathing": {
                "name": "Box Breathing",
                "pattern": "Inhale for 4, hold for 4, exhale for 4, hold for 4",
                "description": "Breathe in a square pattern to promote calm and focus"
            },
            "4_7_8": {
                "name": "4-7-8 Breathing", 
                "pattern": "Inhale for 4, hold for 7, exhale for 8",
                "description": "This technique helps activate your body's relaxation response"
            },
            "belly_breathing": {
                "name": "Belly Breathing",
                "pattern": "Slow, deep breaths expanding your belly",
                "description": "Focus on breathing deeply into your diaphragm"
            }
        }
        
        exercise = exercises.get(exercise_type, exercises["box_breathing"])
        
        return {
            "exercise": exercise,
            "duration": duration_minutes,
            "instructions": [
                "Find a comfortable position, sitting or lying down",
                "Close your eyes or soften your gaze",
                f"Follow this pattern: {exercise['pattern']}",
                "Continue for the recommended duration",
                "Notice how you feel afterward"
            ],
            "benefits": "This exercise can help reduce stress, anxiety, and promote relaxation"
        }

    # Session Management Tool Implementations
    async def _search_sessions(self, client_name: str = None, client_id: str = None, date_from: str = None, 
                             date_to: str = None, keywords: str = None, limit: int = 10) -> Dict[str, Any]:
        """Search for transcription sessions"""
        try:
            logger.info(f"🔍 search_sessions called with: client_name={client_name}, client_id={client_id}, keywords={keywords}")
            
            params = {'limit': str(limit)}
            
            if client_name:
                params['client_name'] = client_name
            if client_id:
                params['client_id'] = client_id
            if date_from:
                params['date_from'] = date_from
            if date_to:
                params['date_to'] = date_to
            if keywords:
                params['keywords'] = keywords
            
            response = await self._make_api_request('GET', '/haystack/search-sessions', params=params)
            
            return {
                "sessions": response.get("sessions", []),
                "total": response.get("total", 0),
                "search_criteria": {
                    "client_name": client_name,
                    "client_id": client_id,
                    "date_range": f"{date_from} to {date_to}" if date_from and date_to else None,
                    "keywords": keywords
                }
            }
            
        except Exception as e:
            logger.error(f"Error searching sessions: {e}")
            return {
                "sessions": [],
                "total": 0,
                "error": f"Failed to search sessions: {str(e)}",
                "search_criteria": {
                    "client_name": client_name,
                    "client_id": client_id,
                    "keywords": keywords
                }
            }

    async def _load_session(self, session_id: str, client_id: str, include_segments: bool = True) -> Dict[str, Any]:
        """Load a specific session with transcript details"""
        try:
            logger.info(f"🔍 load_session called with: session_id={session_id}, client_id={client_id}")
            
            if not session_id or not client_id:
                return {
                    "error": "session_id and client_id are required",
                    "status": "Invalid Request"
                }
            
            params = {
                'client_id': client_id,
                'include_segments': str(include_segments).lower()
            }
            
            response = await self._make_api_request('GET', f'/haystack/sessions/{session_id}', params=params)
            
            return {
                "session_id": response.get("session_id", session_id),
                "client_id": response.get("client_id", client_id),
                "client_name": response.get("client_name", "Unknown Client"),
                "recording_date": response.get("recording_date"),
                "duration": response.get("duration"),
                "total_segments": response.get("total_segments", 0),
                "average_confidence": response.get("average_confidence"),
                "segments": response.get("segments", []) if include_segments else [],
                "metadata": response.get("metadata", {}),
                "status": "loaded"
            }
            
        except Exception as e:
            logger.error(f"Error loading session: {e}")
            return {
                "session_id": session_id,
                "client_id": client_id,
                "error": f"Failed to load session: {str(e)}",
                "status": "error"
            }

    async def _analyze_session_content(self, session_id: str, client_id: str, analysis_type: str = "comprehensive") -> Dict[str, Any]:
        """Analyze session content for insights"""
        try:
            logger.info(f"🔍 analyze_session_content called with: session_id={session_id}, analysis_type={analysis_type}")
            
            if not session_id or not client_id:
                return {
                    "error": "session_id and client_id are required",
                    "status": "Invalid Request"
                }
            
            params = {
                'client_id': client_id,
                'analysis_type': analysis_type
            }
            
            response = await self._make_api_request('POST', f'/haystack/sessions/{session_id}/analyze', data=params)
            
            return {
                "session_id": response.get("session_id", session_id),
                "analysis_type": analysis_type,
                "summary": response.get("summary", ""),
                "key_topics": response.get("key_topics", []),
                "sentiment_analysis": response.get("sentiment_analysis", {}),
                "themes": response.get("themes", []),
                "insights": response.get("insights", []),
                "recommendations": response.get("recommendations", []),
                "word_count": response.get("word_count", 0),
                "speaker_breakdown": response.get("speaker_breakdown", {}),
                "confidence_score": response.get("confidence_score", 0.0),
                "status": "analyzed"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing session content: {e}")
            return {
                "session_id": session_id,
                "analysis_type": analysis_type,
                "error": f"Failed to analyze session: {str(e)}",
                "status": "error"
            }

    # Simplified UI Integration Tools that mimic manual UI interactions
    async def _set_client_selection(self, client_name: str, client_id: str, page_context: dict = None) -> Dict[str, Any]:
        """Set the client selection in the UI (like selecting from AutoComplete)"""
        try:
            logger.info(f"👤 set_client_selection called with: client_name={client_name}, client_id={client_id}")
            
            if not client_name or not client_id:
                return {
                    "error": "client_name and client_id are required",
                    "status": "Invalid Request"
                }

            # Check if user is on the correct page for this action
            if page_context:
                page_type = page_context.get('page_type', 'unknown')
                available_capabilities = page_context.get('capabilities', [])
                
                # Block execution if not on appropriate page
                if 'set_client_selection' not in available_capabilities and page_type != 'unknown':
                    logger.info(f"🚫 Blocking set_client_selection on page '{page_type}', suggesting navigation instead")
                    
                    # Generate clickable link to Sessions page (live-transcribe)
                    sessions_url = "/live-transcribe"
                    
                    return {
                        "client_name": client_name,
                        "client_id": client_id,
                        "status": "navigation_required",
                        "user_message": f"To select '{client_name}' and load their sessions, you need to be on the Sessions page. Please click the link below:",
                        "navigation_link": {
                            "text": "Go to Sessions Page",
                            "url": sessions_url,
                            "page_type": "transcribe_page"
                        },
                        "instructions": f"Once you're on the Sessions page, ask me again to load {client_name}'s sessions and I'll be able to help!"
                    }

            return {
                "client_name": client_name,
                "client_id": client_id,
                "ui_action": {
                    "type": "set_client_selection",
                    "target": "live_transcribe_page",
                    "payload": {
                        "clientName": client_name,
                        "clientId": client_id
                    }
                },
                "status": "ui_action_requested",
                "user_message": f"Selected client '{client_name}' in the interface."
            }
            
        except Exception as e:
            logger.error(f"Error in set_client_selection: {e}")
            return {
                "client_name": client_name,
                "client_id": client_id,
                "error": f"Failed to set client selection: {str(e)}",
                "status": "error"
            }

    async def _load_session_direct(self, session_id: str, client_id: str, client_name: str, recording_date: str, duration: float, total_segments: int, average_confidence: float, page_context: dict = None) -> Dict[str, Any]:
        """Load a session directly using existing UI logic (like clicking Load Session button)"""
        try:
            logger.info(f"📂 load_session_direct called with: session_id={session_id}, client_name={client_name}")
            
            if not session_id or not client_id or not client_name:
                return {
                    "error": "session_id, client_id, and client_name are required",
                    "status": "Invalid Request"
                }

            # Check if user is on the correct page for this action
            if page_context:
                page_type = page_context.get('page_type', 'unknown')
                available_capabilities = page_context.get('capabilities', [])
                
                # Block execution if not on appropriate page
                if 'load_session_direct' not in available_capabilities and page_type != 'unknown':
                    logger.info(f"🚫 Blocking load_session_direct on page '{page_type}', suggesting navigation instead")
                    
                    # Generate clickable link to Sessions page (live-transcribe)
                    sessions_url = "/live-transcribe"
                    
                    return {
                        "session_id": session_id,
                        "client_id": client_id,
                        "status": "navigation_required",
                        "user_message": f"To load sessions for '{client_name}', you need to be on the Sessions page. Please click the link below:",
                        "navigation_link": {
                            "text": "Go to Sessions Page",
                            "url": sessions_url,
                            "page_type": "transcribe_page"
                        },
                        "instructions": f"Once you're on the Sessions page, ask me again to load {client_name}'s sessions and I'll be able to help!"
                    }

            return {
                "session_id": session_id,
                "client_id": client_id,
                "ui_action": {
                    "type": "load_session_direct",
                    "target": "live_transcribe_page",
                    "payload": {
                        "sessionId": session_id,
                        "clientId": client_id,
                        "clientName": client_name,
                        "recordingDate": recording_date,
                        "duration": duration,
                        "totalSegments": total_segments,
                        "averageConfidence": average_confidence
                    }
                },
                "status": "ui_action_requested",
                "user_message": f"Loading session for '{client_name}' into a new tab. The session will appear shortly."
            }
            
        except Exception as e:
            logger.error(f"Error in load_session_direct: {e}")
            return {
                "session_id": session_id,
                "client_id": client_id,
                "error": f"Failed to load session directly: {str(e)}",
                "status": "error"
            }

    async def _load_multiple_sessions(self, sessions: List[Dict[str, Any]], page_context: dict = None) -> Dict[str, Any]:
        """Load multiple sessions as separate tabs in the UI"""
        try:
            if not sessions or len(sessions) == 0:
                return {
                    "error": "At least one session is required",
                    "status": "Invalid Request"
                }
            
            logger.info(f"📂 load_multiple_sessions called with {len(sessions)} sessions")
            
            # Check if user is on the correct page for this action
            if page_context and sessions:
                page_type = page_context.get('page_type', 'unknown')
                available_capabilities = page_context.get('capabilities', [])
                
                # Block execution if not on appropriate page
                if 'load_session_direct' not in available_capabilities and page_type != 'unknown':
                    logger.info(f"🚫 Blocking load_multiple_sessions on page '{page_type}', suggesting navigation instead")
                    
                    # Get client info from first session
                    first_session = sessions[0]
                    client_id = first_session.get('client_id')
                    client_name = first_session.get('client_name')
                    
                    # Generate clickable link to Sessions page (live-transcribe)
                    sessions_url = "/live-transcribe"
                    
                    return {
                        "sessions_count": len(sessions),
                        "status": "navigation_required",
                        "user_message": f"To load sessions for '{client_name}', you need to be on the Sessions page. Please click the link below:",
                        "navigation_link": {
                            "text": "Go to Sessions Page",
                            "url": sessions_url,
                            "page_type": "transcribe_page"
                        },
                        "instructions": f"Once you're on the Sessions page, ask me again to load {client_name}'s sessions and I'll be able to help!"
                    }
            
            # Generate UI actions for each session
            ui_actions = []
            session_names = []
            
            for session in sessions:
                session_id = session.get('session_id')
                client_id = session.get('client_id') 
                client_name = session.get('client_name')
                recording_date = session.get('recording_date')
                duration = session.get('duration', 0)
                total_segments = session.get('total_segments', 0)
                average_confidence = session.get('average_confidence', 0.0)
                
                if not all([session_id, client_id, client_name]):
                    continue  # Skip invalid sessions
                
                ui_actions.append({
                    "type": "load_session_direct",
                    "target": "live_transcribe_page",
                    "payload": {
                        "sessionId": session_id,
                        "clientId": client_id,
                        "clientName": client_name,
                        "recordingDate": recording_date,
                        "duration": duration,
                        "totalSegments": total_segments,
                        "averageConfidence": average_confidence
                    }
                })
                
                # Format session for user message
                date_str = recording_date.split('T')[0] if recording_date else "unknown date"
                session_names.append(f"{client_name} ({date_str})")
            
            if not ui_actions:
                return {
                    "error": "No valid sessions found to load",
                    "status": "Invalid Request"
                }
            
            return {
                "sessions_count": len(ui_actions),
                "ui_action": ui_actions,  # Multiple UI actions
                "status": "ui_action_requested", 
                "user_message": f"Loading {len(ui_actions)} sessions into new tabs: {', '.join(session_names)}. The sessions will appear shortly."
            }
            
        except Exception as e:
            logger.error(f"Error in load_multiple_sessions: {e}")
            return {
                "error": f"Failed to load multiple sessions: {str(e)}",
                "status": "error"
            }

    async def _validate_sessions(self, sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate that sessions have available transcript content before loading"""
        try:
            if not sessions or len(sessions) == 0:
                return {
                    "error": "At least one session is required",
                    "status": "Invalid Request"
                }
            
            logger.info(f"🔍 validate_sessions called with {len(sessions)} sessions")
            
            valid_sessions = []
            invalid_sessions = []
            
            for session in sessions:
                session_id = session.get('session_id')
                client_id = session.get('client_id')
                
                if not session_id or not client_id:
                    invalid_sessions.append({
                        "session_id": session_id,
                        "error": "Missing session_id or client_id"
                    })
                    continue
                
                try:
                    # Try to fetch the transcript to see if it exists
                    # Note: _make_api_request automatically adds api/v1/ prefix
                    response = await self._make_api_request(
                        'GET', 
                        f'ai/transcriptions/{session_id}',
                        params={'clientId': client_id}
                    )
                    
                    if response:
                        valid_sessions.append(session)
                        logger.info(f"✅ Session {session_id} has valid transcript")
                    else:
                        invalid_sessions.append({
                            "session_id": session_id,
                            "error": "No transcript data found"
                        })
                        
                except Exception as e:
                    logger.warning(f"❌ Session {session_id} validation failed: {e}")
                    invalid_sessions.append({
                        "session_id": session_id,  
                        "error": f"Transcript not accessible: {str(e)}"
                    })
            
            return {
                "valid_sessions": valid_sessions,
                "invalid_sessions": invalid_sessions,
                "total_checked": len(sessions),
                "valid_count": len(valid_sessions),
                "invalid_count": len(invalid_sessions),
                "all_valid": len(invalid_sessions) == 0,
                "status": "validation_complete"
            }
            
        except Exception as e:
            logger.error(f"Error in validate_sessions: {e}")
            return {
                "error": f"Failed to validate sessions: {str(e)}",
                "status": "error"
            }

    async def _get_loaded_sessions(self) -> Dict[str, Any]:
        """Get list of sessions currently loaded in the UI"""
        try:
            logger.info("🔍 get_loaded_sessions called")
            
            # Get UI state from the UI state manager
            from ui_state_manager import ui_state_manager
            
            # Get all sessions summary to find active UI states
            all_sessions_summary = ui_state_manager.get_all_sessions_summary()
            
            if not all_sessions_summary:
                return {
                    "loaded_sessions": [],
                    "session_count": 0,
                    "message": "No sessions currently loaded in the UI interface.",
                    "status": "no_sessions_loaded"
                }
            
            # Get the most recent session's UI state
            latest_session_id = max(all_sessions_summary.keys(), 
                                  key=lambda k: all_sessions_summary[k].get('last_updated', ''))
            
            loaded_sessions = ui_state_manager.get_loaded_sessions(latest_session_id)
            session_count = ui_state_manager.get_session_count(latest_session_id)
            current_client = ui_state_manager.get_current_client(latest_session_id)
            
            logger.info(f"📂 Found {session_count} loaded sessions in UI context")
            
            # Format sessions for user-friendly display
            session_summaries = []
            for i, session in enumerate(loaded_sessions, 1):
                session_summaries.append({
                    "index": i,
                    "session_id": session.get("sessionId", "unknown"),
                    "client_name": session.get("clientName", "Unknown Client"),
                    "client_id": session.get("clientId", "unknown"),
                    "has_content": bool(session.get("content", "")),
                    "content_preview": (session.get("content", "")[:100] + "..." 
                                      if len(session.get("content", "")) > 100 
                                      else session.get("content", "")),
                    "metadata": session.get("metadata", {})
                })
            
            return {
                "loaded_sessions": session_summaries,
                "session_count": session_count,
                "current_client": current_client,
                "message": f"Found {session_count} session(s) currently loaded in the UI.",
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"Error in get_loaded_sessions: {e}")
            return {
                "error": f"Failed to get loaded sessions: {str(e)}",
                "status": "error"
            }

    async def _get_session_content(self, session_id: str) -> Dict[str, Any]:
        """Get the full transcript content of a specific loaded session"""
        try:
            logger.info(f"🔍 get_session_content called with session_id: {session_id}")
            
            # Get UI state from the UI state manager
            from ui_state_manager import ui_state_manager
            
            # Get all sessions summary to find active UI states
            all_sessions_summary = ui_state_manager.get_all_sessions_summary()
            
            if not all_sessions_summary:
                return {
                    "session_id": session_id,
                    "content": "",
                    "message": "No sessions currently loaded in the UI interface.",
                    "status": "no_sessions_loaded"
                }
            
            # Search across all session states for the specific session
            session_content = None
            found_session = None
            
            for ws_session_id in all_sessions_summary.keys():
                content = ui_state_manager.get_session_content(ws_session_id, session_id)
                if content:
                    session_content = content
                    
                    # Get the full session metadata
                    loaded_sessions = ui_state_manager.get_loaded_sessions(ws_session_id)
                    for session in loaded_sessions:
                        if session.get("sessionId") == session_id:
                            found_session = session
                            break
                    break
            
            if not session_content:
                return {
                    "session_id": session_id,
                    "content": "",
                    "message": f"Session {session_id} is not currently loaded in the UI or has no content.",
                    "status": "session_not_found"
                }
            
            logger.info(f"📄 Found content for session {session_id}: {len(session_content)} characters")
            
            return {
                "session_id": session_id,
                "content": session_content,
                "client_name": found_session.get("clientName", "Unknown") if found_session else "Unknown",
                "client_id": found_session.get("clientId", "unknown") if found_session else "unknown",
                "metadata": found_session.get("metadata", {}) if found_session else {},
                "content_length": len(session_content),
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"Error in get_session_content: {e}")
            return {
                "error": f"Failed to get session content: {str(e)}",
                "status": "error"
            }

    async def _analyze_loaded_session(self, session_id: str, analysis_type: str, specific_question: str = None) -> Dict[str, Any]:
        """Analyze a currently loaded session for themes, topics, sentiment, etc."""
        try:
            logger.info(f"🔍 analyze_loaded_session called with session_id: {session_id}, analysis_type: {analysis_type}")
            
            # Debug: Check what sessions are available in UI state
            from ui_state_manager import ui_state_manager
            all_sessions_summary = ui_state_manager.get_all_sessions_summary()
            logger.info(f"🔍 DEBUG: All UI sessions: {all_sessions_summary}")
            
            # Get the actual loaded session IDs
            actual_loaded_sessions = []
            if all_sessions_summary:
                for ws_session_id in all_sessions_summary.keys():
                    loaded_sessions = ui_state_manager.get_loaded_sessions(ws_session_id)
                    session_ids = [s.get('sessionId') for s in loaded_sessions if s.get('sessionId')]
                    logger.info(f"🔍 DEBUG: Loaded sessions for {ws_session_id}: {session_ids}")
                    actual_loaded_sessions.extend(session_ids)
            
            logger.info(f"🔍 DEBUG: analyze_loaded_session called with session_id='{session_id}', available sessions: {actual_loaded_sessions}")
            
            # AUTO-FIX: If the provided session_id doesn't match any loaded sessions, try to find the best match
            target_session_id = session_id
            if session_id not in actual_loaded_sessions:
                if len(actual_loaded_sessions) == 1:
                    # Single session: use it
                    target_session_id = actual_loaded_sessions[0]
                    logger.info(f"🔧 AUTO-CORRECTING: Using actual loaded session {target_session_id} instead of {session_id}")
                elif len(actual_loaded_sessions) > 1:
                    # Multiple sessions: check if the session_id is a partial match or similar
                    # For now, return an error asking the AI to use specific session IDs
                    logger.warning(f"⚠️ Session {session_id} not found in loaded sessions {actual_loaded_sessions}")
                    return {
                        "session_id": session_id,
                        "analysis_type": analysis_type,
                        "analysis_results": f"Session ID '{session_id}' not found. Please use one of the loaded session IDs: {', '.join(actual_loaded_sessions)}",
                        "status": "session_id_not_found",
                        "available_sessions": actual_loaded_sessions
                    }
                else:
                    logger.warning(f"⚠️ No loaded sessions found")
            
            # First, get the session content using the corrected session ID
            content_result = await self._get_session_content(target_session_id)
            
            if content_result.get("status") != "success":
                return {
                    "session_id": target_session_id,
                    "analysis_type": analysis_type,
                    "analysis_results": f"Cannot analyze session: {content_result.get('message', 'Unknown error')}",
                    "status": "session_not_available"
                }
            
            content = content_result.get("content", "")
            client_name = content_result.get("client_name", "Unknown")
            
            if not content.strip():
                return {
                    "session_id": target_session_id,
                    "analysis_type": analysis_type,
                    "analysis_results": "Session content is empty - cannot perform analysis.",
                    "status": "no_content"
                }
            
            # Perform basic analysis based on type
            analysis_results = {}
            
            # Basic content statistics
            words = content.split()
            sentences = content.split('.')
            
            analysis_results["basic_stats"] = {
                "total_characters": len(content),
                "total_words": len(words),
                "estimated_sentences": len([s for s in sentences if s.strip()]),
                "client_name": client_name
            }
            
            # Simple keyword extraction (basic implementation)
            # Remove common words and extract frequent terms
            common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'i', 'you', 'we', 'they', 'he', 'she', 'it', 'that', 'this', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should'}
            words_lower = [word.lower().strip('.,!?;:"()[]') for word in words if word.lower() not in common_words and len(word) > 2]
            
            from collections import Counter
            word_freq = Counter(words_lower)
            top_keywords = word_freq.most_common(10)
            
            analysis_results["keywords"] = [{"word": word, "frequency": freq} for word, freq in top_keywords]
            
            # Analysis type specific results
            if analysis_type.lower() in ["summary", "overview"]:
                # Simple summary (first and last parts of transcript)
                summary_parts = []
                if len(content) > 200:
                    summary_parts.append(f"Session beginning: {content[:100]}...")
                    summary_parts.append(f"Session ending: ...{content[-100:]}")
                else:
                    summary_parts.append(content)
                
                analysis_results["summary"] = " ".join(summary_parts)
                
            elif analysis_type.lower() in ["themes", "topics"]:
                # Extract potential themes from keywords
                themes = [word for word, freq in top_keywords[:5] if freq > 1]
                analysis_results["potential_themes"] = themes
                
            # Handle specific questions
            if specific_question:
                # Simple keyword matching for specific questions
                question_lower = specific_question.lower()
                relevant_parts = []
                
                # Split content into sentences and find those containing question keywords
                question_words = [word.strip('.,!?;:"()[]') for word in question_lower.split() if len(word) > 2]
                sentences = [s.strip() for s in content.split('.') if s.strip()]
                
                for sentence in sentences[:20]:  # Limit to first 20 sentences
                    sentence_lower = sentence.lower()
                    if any(qword in sentence_lower for qword in question_words):
                        relevant_parts.append(sentence.strip())
                
                analysis_results["question_response"] = {
                    "question": specific_question,
                    "relevant_content": relevant_parts[:5],  # Top 5 relevant sentences
                    "found_matches": len(relevant_parts)
                }
            
            return {
                "session_id": target_session_id,
                "analysis_type": analysis_type,
                "specific_question": specific_question,
                "client_name": client_name,
                "analysis_results": analysis_results,
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"Error in analyze_loaded_session: {e}")
            return {
                "error": f"Failed to analyze session: {str(e)}",
                "status": "error"
            }

    async def _suggest_navigation(self, current_page: str, suggested_page: str, reason: str, required_for_action: str) -> Dict[str, Any]:
        """Suggest navigation to user without automatically navigating"""
        try:
            logger.info(f"🧭 suggest_navigation called: {current_page} -> {suggested_page} for {required_for_action}")
            
            return {
                "current_page": current_page,
                "suggested_page": suggested_page,
                "reason": reason,
                "required_for_action": required_for_action,
                "ui_action": {
                    "type": "suggest_navigation",
                    "payload": {
                        "current_page": current_page,
                        "suggested_page": suggested_page,
                        "reason": reason,
                        "required_for_action": required_for_action
                    }
                },
                "status": "ui_action_requested",
                "user_message": f"To {required_for_action}, you'll need to navigate from {current_page} to {suggested_page}. {reason}"
            }
            
        except Exception as e:
            logger.error(f"Error in suggest_navigation: {e}")
            return {
                "error": f"Failed to suggest navigation: {str(e)}",
                "status": "error"
            }

    async def _navigate_to_page(self, page_url: str, page_type: str, reason: str, params: dict = None) -> Dict[str, Any]:
        """Navigate user to a specific page (controlled navigation)"""
        try:
            logger.info(f"🚀 navigate_to_page called: {page_url} ({page_type}) - {reason}")
            
            if not page_url or not page_type:
                return {
                    "error": "page_url and page_type are required",
                    "status": "Invalid Request"
                }

            return {
                "page_url": page_url,
                "page_type": page_type,
                "reason": reason,
                "params": params or {},
                "ui_action": {
                    "type": "navigate_to_page",
                    "payload": {
                        "page_url": page_url,
                        "page_type": page_type,
                        "params": params or {},
                        "reason": reason
                    }
                },
                "status": "ui_action_requested",
                "user_message": f"Navigating to {page_type}. {reason}"
            }
            
        except Exception as e:
            logger.error(f"Error in navigate_to_page: {e}")
            return {
                "error": f"Failed to navigate: {str(e)}",
                "status": "error"
            }



# Global tool manager instance
tool_manager = ToolManager()