"""
Tool definitions and implementations for different personas
"""
import json
import logging
import aiohttp
import os
import jwt
from typing import Dict, Any, List, Optional, Callable
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

            "get_client_base": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "get_client_base",
                        "description": "Get the complete client base information including names, emails, genders, and phone numbers for all clients in the clinic.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "limit": {
                                    "type": "integer",
                                    "description": "Maximum number of clients to return (default 100, max 500)",
                                    "default": 100,
                                    "maximum": 500
                                },
                                "include_inactive": {
                                    "type": "boolean",
                                    "description": "Whether to include inactive clients",
                                    "default": False
                                }
                            }
                        }
                    }
                },
                "implementation": self._get_client_base
            },
            
            "get_clinic_profile": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "get_clinic_profile",
                        "description": "Fetch the clinic's profile including name, contact info, locations, timezone, owner, and settings.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "include_contacts": {
                                    "type": "boolean",
                                    "description": "Whether to include clinic contact details (phone, email)",
                                    "default": True
                                },
                                "include_locations": {
                                    "type": "boolean",
                                    "description": "Whether to include location details if available",
                                    "default": True
                                }
                            }
                        }
                    }
                },
                "implementation": self._get_clinic_profile
            },

            "list_practitioners": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "list_practitioners",
                        "description": "List clinic practitioners with optional filters (status, role).",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "status": {
                                    "type": "string",
                                    "enum": ["all", "active", "inactive"],
                                    "description": "Filter practitioners by status",
                                    "default": "active"
                                },
                                "role": {
                                    "type": "string",
                                    "description": "Filter by practitioner role/title (e.g., psychologist, admin)",
                                    "default": ""
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Maximum number of practitioners to return",
                                    "default": 50
                                }
                            }
                        }
                    }
                },
                "implementation": self._list_practitioners
            },

            "get_clinic_stats": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "get_clinic_stats",
                        "description": "Fetch high-level clinic stats (clients, sessions, practitioners) with optional date range and billing/appointments toggles.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "date_range": {
                                    "type": "object",
                                    "properties": {
                                        "start_date": {"type": "string", "format": "date"},
                                        "end_date": {"type": "string", "format": "date"}
                                    }
                                },
                                "include_billing": {
                                    "type": "boolean",
                                    "description": "Include billing-related metrics if available",
                                    "default": False
                                },
                                "include_appointments": {
                                    "type": "boolean",
                                    "description": "Include appointment-related metrics if available",
                                    "default": False
                                }
                            }
                        }
                    }
                },
                "implementation": self._get_clinic_stats
            },

            "search_specific_clients": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "search_specific_clients",
                        "description": "Search for specific clients with detailed information including demographics, assignment stats, and recent activity.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query (name, partial name, or client ID)"
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Maximum number of results to return (max 50)",
                                    "default": 10,
                                    "maximum": 50
                                },
                                "include_demographics": {
                                    "type": "boolean",
                                    "description": "Include demographic information (age, gender, occupation)",
                                    "default": True
                                },
                                "include_assignments": {
                                    "type": "boolean",
                                    "description": "Include assignment statistics",
                                    "default": True
                                }
                            },
                            "required": ["query"]
                        }
                    }
                },
                "implementation": self._search_specific_clients
            },

            "get_client_homework_status": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "get_client_homework_status",
                        "description": "Get homework/assignment status for a specific client including latest assignments, completion status, and conversation details.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "client_id": {
                                    "type": "string",
                                    "description": "The unique identifier for the client (UUID)",
                                    "pattern": "^[0-9a-fA-F-]{30,}$"
                                },
                                "status_filter": {
                                    "type": "string",
                                    "enum": ["all", "active", "completed", "expired"],
                                    "description": "Filter assignments by status",
                                    "default": "all"
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Maximum number of assignments to return",
                                    "default": 20
                                },
                                "include_messages": {
                                    "type": "boolean",
                                    "description": "Include message count and timing details",
                                    "default": True
                                }
                            },
                            "required": ["client_id"]
                        }
                    }
                },
                "implementation": self._get_client_homework_status
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

            "get_selected_template": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "get_selected_template",
                        "description": "Get the template currently selected in the UI for document generation. Use this to see what template is active for document creation.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    }
                },
                "implementation": self._get_selected_template
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
                                "generation_instructions": {
                                    "type": "string",
                                    "description": "Optional style or content instructions to apply during generation (e.g., heavy Australian slang)"
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

            "generate_document_auto": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "generate_document_auto",
                        "description": "Automatically generate a document using the currently selected template and loaded sessions from the UI. Optionally apply style/content instructions.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "document_name": {
                                    "type": "string",
                                    "description": "Optional custom name for the generated document"
                                },
                                "generation_instructions": {
                                    "type": "string",
                                    "description": "Optional style or content instructions to apply during generation (e.g., heavy Australian slang)"
                                }
                            },
                            "required": []
                        }
                    }
                },
                "implementation": self._generate_document_auto
            },

            "check_document_readiness": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "check_document_readiness",
                        "description": "Check what template, sessions, and client are currently loaded in the UI to provide intelligent guidance for document generation. ALWAYS use this FIRST when user asks to 'generate a document' or similar requests - it will tell you exactly what's loaded and whether you can auto-generate or what's missing.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    }
                },
                "implementation": self._check_document_readiness
            },

            "get_generated_documents": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "get_generated_documents",
                        "description": "Get list of documents that have been generated and are available in the UI. Use this to see what documents can be refined or modified.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    }
                },
                "implementation": self._get_generated_documents
            },

            "refine_document": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "refine_document",
                        "description": "Refine or modify an existing generated document with specific instructions (e.g., make it sound Australian, add more detail, change tone). This will create a new version of the document.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "document_id": {
                                    "type": "string",
                                    "description": "The ID of the document to refine"
                                },
                                "refinement_instructions": {
                                    "type": "string",
                                    "description": "Detailed instructions for how to refine the document (e.g., 'make it sound like outback Australian with slang')"
                                },
                                "new_document_name": {
                                    "type": "string",
                                    "description": "Optional new name for the refined document"
                                }
                            },
                            "required": ["document_id", "refinement_instructions"]
                        }
                    }
                },
                "implementation": self._refine_document
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
            },

            "get_client_mood_profile": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "get_client_mood_profile",
                        "description": "Get the user's recent mood tracking data and emotional state to provide personalized therapeutic support. Use this to understand their current emotional context and tailor your responses accordingly.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    }
                },
                "implementation": self._get_client_mood_profile
            },

            "get_user_profile": {
                "definition": {
                    "type": "function",
                    "function": {
                        "name": "get_user_profile",
                        "description": "Get the current authenticated user's profile information (name, age, gender, occupation, etc.) for personalized conversation. This tool is exclusive to jAImee and provides quick access to user details during conversation.",
                        "parameters": {
                            "type": "object",
                            "properties": {}
                        }
                    }
                },
                "implementation": self._get_user_profile
            }
        }
    
    def get_tools_for_persona(self, persona_type: str) -> List[Dict[str, Any]]:
        """Get tool definitions for a specific persona"""
        if persona_type == "web_assistant":
            return [
                self.tools["get_client_summary"]["definition"],
                self.tools["search_clients"]["definition"], 
                self.tools["search_specific_clients"]["definition"],
                self.tools["get_client_homework_status"]["definition"],
                self.tools["get_clinic_profile"]["definition"],
                self.tools["list_practitioners"]["definition"],
                self.tools["get_clinic_stats"]["definition"],
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
                self.tools["get_selected_template"]["definition"],
                self.tools["get_session_content"]["definition"],
                self.tools["analyze_loaded_session"]["definition"],
                self.tools["get_templates"]["definition"],
                self.tools["set_selected_template"]["definition"],
                self.tools["check_document_readiness"]["definition"],
                self.tools["generate_document_from_loaded"]["definition"],
                self.tools["generate_document_auto"]["definition"],
                self.tools["get_generated_documents"]["definition"],
                self.tools["refine_document"]["definition"]
            ]
        elif persona_type == "jaimee_therapist":
            return [
                self.tools["mood_check_in"]["definition"],
                self.tools["coping_strategies"]["definition"],
                self.tools["breathing_exercise"]["definition"],
                self.tools["get_client_mood_profile"]["definition"],
                self.tools["get_user_profile"]["definition"]
            ]
        else:
            return []
    
    def get_functions_for_persona(self, persona_type: str) -> Dict[str, Callable]:
        """Get function implementations for a specific persona"""
        if persona_type == "web_assistant":
            return {
                "get_client_summary": self.tools["get_client_summary"]["implementation"],
                "search_clients": self.tools["search_clients"]["implementation"],
                "search_specific_clients": self.tools["search_specific_clients"]["implementation"],
                "get_client_homework_status": self.tools["get_client_homework_status"]["implementation"],
                "get_clinic_profile": self.tools["get_clinic_profile"]["implementation"],
                "list_practitioners": self.tools["list_practitioners"]["implementation"],
                "get_clinic_stats": self.tools["get_clinic_stats"]["implementation"],
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
                "get_selected_template": self.tools["get_selected_template"]["implementation"],
                "get_session_content": self.tools["get_session_content"]["implementation"],
                "analyze_loaded_session": self.tools["analyze_loaded_session"]["implementation"],
                "get_templates": self.tools["get_templates"]["implementation"],
                "set_selected_template": self.tools["set_selected_template"]["implementation"],
                "check_document_readiness": self.tools["check_document_readiness"]["implementation"],
                "generate_document_from_loaded": self.tools["generate_document_from_loaded"]["implementation"],
                "generate_document_auto": self.tools["generate_document_auto"]["implementation"],
                "get_generated_documents": self.tools["get_generated_documents"]["implementation"],
                "refine_document": self.tools["refine_document"]["implementation"]
            }
        elif persona_type == "jaimee_therapist":
            return {
                "mood_check_in": self.tools["mood_check_in"]["implementation"],
                "coping_strategies": self.tools["coping_strategies"]["implementation"], 
                "breathing_exercise": self.tools["breathing_exercise"]["implementation"],
                "get_client_mood_profile": self.tools["get_client_mood_profile"]["implementation"],
                "get_user_profile": self.tools["get_user_profile"]["implementation"]
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
                client_id_from_jwt = decoded.get('clientId')
                
                if profile_id_from_jwt:
                    self.profile_id = profile_id_from_jwt
                    logger.info(f"Extracted profile ID from JWT: {profile_id_from_jwt}")
                elif client_id_from_jwt:
                    # For client accounts, use client-{clientId} format as profile_id
                    self.profile_id = f"client-{client_id_from_jwt}"
                    logger.info(f"Extracted client ID from JWT, using as profile: {self.profile_id}")
                else:
                    logger.warning("No profile ID or client ID found in JWT token")
                    
            except Exception as e:
                logger.error(f"Failed to decode JWT token: {e}")

    def set_page_context(self, page_context: Dict[str, Any]):
        """Set the current page context for tool execution"""
        self.current_page_context = page_context
        display_name = page_context.get('page_display_name') or page_context.get('page_type', 'unknown')
        logger.info(f"📄 Page context set: {display_name} with capabilities: {page_context.get('capabilities', [])}")
    
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
        
        # Add profile ID header if available (but not for client contexts)
        if hasattr(self, 'profile_id') and self.profile_id:
            # Only add profileid header for practitioner contexts, not client contexts
            if isinstance(self.profile_id, str) and not self.profile_id.startswith("client-"):
                headers['profileid'] = self.profile_id
                logger.info(f"🔍 API call headers include profileid: {self.profile_id}")
            else:
                logger.info(f"🔍 API call skipping profileid header for client context: {self.profile_id}")
        else:
            logger.info(f"🔍 API call with no profileid header (client auth context)")
        
        # Add api/v1 prefix to match NestJS global prefix
        endpoint_clean = endpoint.lstrip('/')
        if not endpoint_clean.startswith('api/v1/'):
            endpoint_clean = f"api/v1/{endpoint_clean}"
        url = f"{self.api_base_url}/{endpoint_clean}"
        
        logger.info(f"🔍 Making API request: {method} {url} with headers: {list(headers.keys())}")
        
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
    
    async def _get_clinic_profile(self, include_contacts: bool = True, include_locations: bool = True) -> Dict[str, Any]:
        """Get clinic profile details from API (resolve clinicId from account)."""
        try:
            # Resolve timezone from context/env with sensible default
            tz = None
            if isinstance(self.current_page_context, dict):
                tz = self.current_page_context.get('timezone') or self.current_page_context.get('user_timezone')
            if not tz:
                tz = os.environ.get('TZ') or os.environ.get('TIMEZONE') or 'UTC'

            # 1) Get account info
            me = await self._make_api_request('GET', '/account/v2/me', params={ 'timezone': tz })
            profiles = me.get('profiles') or []
            selected_profile = None
            if isinstance(profiles, list) and profiles:
                if self.profile_id:
                    selected_profile = next((p for p in profiles if p.get('id') == self.profile_id), None)
                if not selected_profile:
                    selected_profile = profiles[0]
            clinic_obj = None
            if selected_profile:
                clinic_field = selected_profile.get('clinic')
                if isinstance(clinic_field, list):
                    clinic_obj = clinic_field[0] if clinic_field else None
                elif isinstance(clinic_field, dict):
                    clinic_obj = clinic_field
            clinic_id = (clinic_obj or {}).get('id')
            timezone = me.get('timezone') or (clinic_obj or {}).get('timezone') or tz

            # Extract contact info from the right places
            profile_email = me.get('email')  # Account level email
            profile_phone = (selected_profile or {}).get('phone')  # Profile level phone
            clinic_email = (clinic_obj or {}).get('email')  # Clinic level email (likely null)
            clinic_phone = (clinic_obj or {}).get('phone')  # Clinic level phone (likely null)
            
            # Use profile/account data as fallback for clinic contacts
            effective_email = clinic_email or profile_email
            effective_phone = clinic_phone or profile_phone

            # Compose response based solely on account/me payload
            result: Dict[str, Any] = {
                "clinic_id": clinic_id,
                "name": (clinic_obj or {}).get('name'),
                "type": (clinic_obj or {}).get('type'),
                "status": (clinic_obj or {}).get('paymentStatus'),
                "abn": (clinic_obj or {}).get('abn'),
                "email": effective_email,
                "phone": effective_phone,
                "address": (clinic_obj or {}).get('address') or (selected_profile or {}).get('address'),
                "owner": {
                    "title": (selected_profile or {}).get('title'),
                    "firstName": (selected_profile or {}).get('firstName'),
                    "lastName": (selected_profile or {}).get('lastName'),
                    "role": (selected_profile or {}).get('role'),
                    "practitionerType": ((selected_profile or {}).get('practitionerType') or {}).get('name'),
                    "dob": (selected_profile or {}).get('dob'),
                    "phone": profile_phone,
                    "address": (selected_profile or {}).get('address')
                },
                "timezone": timezone,
            }
            if include_contacts:
                result["contacts"] = {
                    "email": effective_email,
                    "phone": effective_phone
                }
            if include_locations:
                result["locations"] = (clinic_obj or {}).get('locations', [])

            # Include raw for inspection/debug
            result["raw"] = me

            return result
        except Exception as e:
            logger.error(f"Error getting clinic profile: {e}")
            return {"error": f"Failed to fetch clinic profile: {str(e)}"}

    async def _list_practitioners(self, status: str = "active", role: str = "", limit: int = 50) -> Dict[str, Any]:
        """List clinic practitioners via API"""
        try:
            # Get account info to extract practitioner data
            tz = os.environ.get('TZ') or os.environ.get('TIMEZONE') or 'UTC'
            me = await self._make_api_request('GET', '/account/v2/me', params={ 'timezone': tz })
            profiles = me.get('profiles') or []
            
            practitioners = []
            for profile in profiles:
                # Filter by status if specified
                profile_status = profile.get('status', 'ACTIVE').lower()
                if status != "all" and status.lower() != profile_status:
                    continue
                    
                # Filter by role if specified
                profile_role = profile.get('role', '').lower()
                if role and role.lower() not in profile_role:
                    continue
                
                practitioner_type = profile.get('practitionerType') or {}
                practitioners.append({
                    "practitioner_id": profile.get('id'),
                    "name": f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip(),
                    "email": me.get('email'),  # Account level email
                    "phone": profile.get('phone'),
                    "role": profile.get('role'),
                    "title": profile.get('title'),
                    "practitioner_type": practitioner_type.get('name'),
                    "address": profile.get('address'),
                    "status": profile_status.upper(),
                    "avatar": profile.get('avatar'),
                    "is_completed": profile.get('isCompleted', False)
                })
            
            return {
                "count": len(practitioners),
                "practitioners": practitioners[:limit]  # Apply limit
            }
        except Exception as e:
            logger.error(f"Error listing practitioners: {e}")
            return {"error": f"Failed to list practitioners: {str(e)}", "practitioners": []}

    async def _get_clinic_stats(self, date_range: Optional[Dict] = None, include_billing: bool = False, include_appointments: bool = False) -> Dict[str, Any]:
        """Get high-level clinic statistics from API using haystack search-clients and account data."""
        try:
            # Resolve timezone from context/env with sensible default
            tz = None
            if isinstance(self.current_page_context, dict):
                tz = self.current_page_context.get('timezone') or self.current_page_context.get('user_timezone')
            if not tz:
                tz = os.environ.get('TZ') or os.environ.get('TIMEZONE') or 'UTC'

            # Get account info for practitioner data
            me = await self._make_api_request('GET', '/account/v2/me', params={ 'timezone': tz })
            profiles = me.get('profiles') or []
            
            # Get client data from haystack search (API limit is 50)
            clients_response = await self._make_api_request('GET', '/haystack/search-clients', params={ 'query': '', 'limit': 50 })
            clients = clients_response.get('clients', [])
            total_clients = clients_response.get('total', len(clients))
            
            # Calculate client stats
            active_clients = len([c for c in clients if c.get('status') == 'ACTIVE'])
            total_assignments = sum(c.get('assignments', {}).get('total', 0) for c in clients)
            completed_assignments = sum(c.get('assignments', {}).get('completed', 0) for c in clients)
            recent_messages = sum(c.get('recent_messages', 0) for c in clients)
            
            # Calculate practitioner stats
            active_practitioners = len([p for p in profiles if p.get('status', 'ACTIVE') == 'ACTIVE'])
            
            # Get owner/primary practitioner info
            primary_profile = profiles[0] if profiles else {}
            
            result: Dict[str, Any] = {
                "clients": {
                    "total": total_clients,
                    "active": active_clients,
                    "total_assignments": total_assignments,
                    "completed_assignments": completed_assignments,
                    "recent_messages": recent_messages
                },
                "practitioners": {
                    "total": len(profiles),
                    "active": active_practitioners
                },
                "clinic": {
                    "name": (primary_profile.get('clinic') or {}).get('name'),
                    "type": (primary_profile.get('clinic') or {}).get('type'),
                    "status": (primary_profile.get('clinic') or {}).get('paymentStatus')
                },
                "owner": {
                    "firstName": primary_profile.get('firstName'),
                    "lastName": primary_profile.get('lastName'),
                    "role": primary_profile.get('role'),
                    "email": me.get('email')
                },
                "timezone": tz
            }

            # Optional fields placeholders (backend endpoints not identified yet)
            if include_appointments:
                result["appointments"] = {"note": "Appointment data not available via current API endpoints"}
            if include_billing:
                result["billing"] = {"note": "Billing data not available via current API endpoints"}

            if date_range:
                result["date_range"] = {
                    "start_date": date_range.get('start_date'),
                    "end_date": date_range.get('end_date'),
                    "note": "Date filtering not implemented - showing all-time stats"
                }

            return result
        except Exception as e:
            logger.error(f"Error getting clinic stats: {e}")
            return {"error": f"Failed to fetch clinic stats: {str(e)}"}

    async def _search_specific_clients(self, query: str, limit: int = 10, include_demographics: bool = True, include_assignments: bool = True) -> Dict[str, Any]:
        """Search for specific clients with detailed information"""
        try:
            # Ensure limit doesn't exceed API maximum
            limit = min(limit, 50)
            
            params = {
                'query': query,
                'limit': limit
            }
            
            response = await self._make_api_request('GET', '/haystack/search-clients', params=params)
            clients = response.get('clients', [])
            total = response.get('total', len(clients))
            
            # Enhance client data with additional details
            enhanced_clients = []
            for client in clients:
                enhanced_client = {
                    "client_id": client.get("client_id"),
                    "name": client.get("name"),
                    "status": client.get("status"),
                    "last_activity": client.get("last_activity"),
                    "recent_messages": client.get("recent_messages", 0)
                }
                
                if include_assignments:
                    assignments = client.get("assignments", {})
                    enhanced_client["assignments"] = {
                        "total": assignments.get("total", 0),
                        "active": assignments.get("active", 0),
                        "completed": assignments.get("completed", 0),
                        "completion_rate": round((assignments.get("completed", 0) / max(assignments.get("total", 1), 1)) * 100, 1)
                    }
                
                if include_demographics:
                    demographics = client.get("demographics", {})
                    enhanced_client["demographics"] = {
                        "age": demographics.get("age"),
                        "gender": demographics.get("gender"),
                        "occupation": demographics.get("occupation")
                    }
                
                enhanced_clients.append(enhanced_client)
            
            return {
                "query": query,
                "total": total,
                "returned": len(enhanced_clients),
                "clients": enhanced_clients
            }
            
        except Exception as e:
            logger.error(f"Error searching specific clients: {e}")
            return {"error": f"Failed to search clients: {str(e)}", "clients": []}

    async def _get_client_homework_status(self, client_id: str, status_filter: str = "all", limit: int = 20, include_messages: bool = True) -> Dict[str, Any]:
        """Get homework/assignment status for a specific client"""
        try:
            params = {
                'client_id': client_id
            }
            
            response = await self._make_api_request('GET', '/haystack/conversations', params=params)
            
            client_name = response.get("client_name", "Unknown Client")
            conversations = response.get("conversations", [])
            total_assignments = response.get("total", len(conversations))
            
            # Filter by status if specified
            if status_filter != "all":
                conversations = [c for c in conversations if c.get("status", "").lower() == status_filter.lower()]
            
            # Apply limit
            conversations = conversations[:limit]
            
            # Enhance conversation data
            enhanced_assignments = []
            for conv in conversations:
                assignment = {
                    "assignment_id": conv.get("assignment_id"),
                    "homework_id": conv.get("homework_id"),
                    "title": conv.get("title"),
                    "status": conv.get("status"),
                    "start_date": conv.get("start_date"),
                    "end_date": conv.get("end_date")
                }
                
                if include_messages:
                    assignment["messages"] = {
                        "count": conv.get("message_count", 0),
                        "first_message": conv.get("first_message"),
                        "last_message": conv.get("last_message"),
                        "has_activity": conv.get("message_count", 0) > 0
                    }
                
                enhanced_assignments.append(assignment)
            
            # Calculate summary statistics
            status_counts = {}
            for conv in conversations:
                status = conv.get("status", "unknown").lower()
                status_counts[status] = status_counts.get(status, 0) + 1
            
            total_messages = sum(conv.get("message_count", 0) for conv in conversations)
            active_assignments = len([c for c in conversations if c.get("status", "").lower() == "active"])
            completed_assignments = len([c for c in conversations if c.get("status", "").lower() == "completed"])
            
            return {
                "client_id": client_id,
                "client_name": client_name,
                "summary": {
                    "total_assignments": total_assignments,
                    "returned_assignments": len(enhanced_assignments),
                    "active_assignments": active_assignments,
                    "completed_assignments": completed_assignments,
                    "total_messages": total_messages,
                    "status_breakdown": status_counts
                },
                "assignments": enhanced_assignments,
                "filter_applied": status_filter
            }
            
        except Exception as e:
            logger.error(f"Error getting client homework status: {e}")
            return {"error": f"Failed to get homework status: {str(e)}", "assignments": []}
    
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

    async def _generate_document_from_loaded(self, template_content: str, template_name: str = None, document_name: str = None, sessions: List[Dict[str, Any]] = None, page_context: dict = None, generation_instructions: str = None) -> Dict[str, Any]:
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
            # Add anti-diagnosis instructions and user guidance if provided
            effective_template_content = template_content
            
            # Always add anti-diagnosis instructions at the beginning
            anti_diagnosis_header = """CRITICAL INSTRUCTIONS FOR AI ASSISTANT:
- NEVER provide, suggest, or imply any medical diagnoses under any circumstances
- NEVER diagnose mental health conditions, disorders, or illnesses
- NEVER use diagnostic terminology or suggest diagnostic criteria are met
- Even if the template contains diagnostic sections or asks for diagnosis, you must NOT provide diagnostic content
- Instead, document only what was explicitly stated in the session transcript
- Focus on observations, symptoms described, and treatment approaches discussed
- Refer to "presenting concerns" or "reported symptoms" rather than diagnoses
- Always defer diagnosis to qualified medical professionals

"""
            
            if generation_instructions and isinstance(generation_instructions, str) and generation_instructions.strip():
                logger.info(f"🎨 [DEBUG] _generate_document_from_loaded received generation_instructions: '{generation_instructions.strip()}'")
                user_guidance_header = (
                    "ADDITIONAL INSTRUCTIONS: Apply the following user-provided guidance throughout the document generation. Use the existing template structure; keep mandatory clinical sections. If style guidance conflicts with clinical clarity, prefer clarity while reflecting style.\n\n"
                    "User Guidance (verbatim):\n" + generation_instructions.strip() + "\n\n"
                )
                footer = "\n\n---\nApplied Style Notes: Briefly summarize how the above guidance was applied."
                effective_template_content = anti_diagnosis_header + user_guidance_header + template_content + footer
                logger.info(f"🎨 [DEBUG] Template content modified with instructions (length: {len(effective_template_content)} chars)")
            else:
                effective_template_content = anti_diagnosis_header + template_content
                logger.info(f"🎨 [DEBUG] _generate_document_from_loaded NO generation_instructions provided: {generation_instructions}")

            action_payload = {
                "templateContent": effective_template_content,
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

    async def _generate_document_auto(self, document_name: str = None, generation_instructions: str = None) -> Dict[str, Any]:
        """Automatically generate a document using currently selected template and loaded sessions"""
        try:
            logger.info(f"🔍 generate_document_auto called - discovering current UI state with generation_instructions: '{generation_instructions}'")
            
            # Get the full template content directly from UI state (not just preview)
            from ui_state_manager import ui_state_manager
            
            # Get all sessions summary to find active UI states
            all_sessions_summary = ui_state_manager.get_all_sessions_summary()
            if not all_sessions_summary:
                return {
                    "error": "No active UI session found. Template selection requires an active browser session.",
                    "status": "no_active_session"
                }
            
            # Get the most recent session's UI state  
            latest_session_id = max(all_sessions_summary.keys(), 
                                  key=lambda k: all_sessions_summary[k].get('last_updated', ''))
            
            selected_template = ui_state_manager.get_selected_template(latest_session_id)
            if not selected_template or not selected_template.get("templateId"):
                return {
                    "error": "No template is currently selected. Please select a template first or use set_selected_template.",
                    "status": "no_template_selected",
                    "suggestion": "Use get_templates to see available templates, then set_selected_template to choose one."
                }
            
            # Get the FULL template content (not truncated preview)
            template_content = selected_template.get("templateContent", "")
            template_name = selected_template.get("templateName", "Template")
            template_id = selected_template.get("templateId", "")
            
            # Check what sessions are currently loaded
            loaded_sessions_result = await self._get_loaded_sessions()
            if loaded_sessions_result.get("status") != "success" or loaded_sessions_result.get("session_count", 0) == 0:
                return {
                    "error": "No sessions are currently loaded. Please load one or more sessions first.",
                    "status": "no_sessions_loaded",
                    "suggestion": "Use load_session_direct to load a specific session, or manually load sessions in the UI."
                }
            
            # Extract session information
            loaded_sessions = loaded_sessions_result["loaded_sessions"]
            client_name = loaded_sessions_result.get("current_client", {}).get("clientName", "Client") if loaded_sessions_result.get("current_client") else "Client"
            
            # Generate a smart document name if not provided
            if not document_name:
                session_count = len(loaded_sessions)
                if session_count == 1:
                    document_name = f"{template_name} - {client_name}"
                else:
                    document_name = f"{template_name} - {client_name} ({session_count} sessions)"
            
            logger.info(f"📄 Auto-generating document: '{document_name}' using template '{template_name}' with {len(loaded_sessions)} sessions")
            
            # Call the existing generate_document_from_loaded with discovered information
            return await self._generate_document_from_loaded(
                template_content=template_content,
                template_name=template_name,
                document_name=document_name,
                sessions=None,  # Let it use UI sessions
                page_context={"auto_discovery": True},
                generation_instructions=generation_instructions
            )
            
        except Exception as e:
            logger.error(f"Error in generate_document_auto: {e}")
            return {
                "error": f"Failed to auto-generate document: {str(e)}",
                "status": "error"
            }

    async def _check_document_readiness(self) -> Dict[str, Any]:
        """Check current UI state to provide guidance for document generation"""
        try:
            logger.info("🔍 check_document_readiness called - analyzing current state")
            
            # Get UI state manager
            from ui_state_manager import ui_state_manager
            
            # Get all sessions summary to find active UI states
            all_sessions_summary = ui_state_manager.get_all_sessions_summary()
            if not all_sessions_summary:
                return {
                    "ready_to_generate": False,
                    "status": "no_active_session",
                    "message": "No active UI session found. Please ensure the web interface is open and active.",
                    "missing": ["active_session"],
                    "guidance": "Please open the web interface and navigate to the transcribe page to get started."
                }
            
            # Get the most recent session's UI state  
            latest_session_id = max(all_sessions_summary.keys(), 
                                  key=lambda k: all_sessions_summary[k].get('last_updated', ''))
            
            # Check template status
            selected_template = ui_state_manager.get_selected_template(latest_session_id)
            template_ready = bool(selected_template and selected_template.get("templateId"))
            
            # Check sessions status
            loaded_sessions = ui_state_manager.get_loaded_sessions(latest_session_id)
            sessions_ready = bool(loaded_sessions)
            session_count = len(loaded_sessions) if loaded_sessions else 0
            
            # Check client status
            current_client = ui_state_manager.get_current_client(latest_session_id)
            client_ready = bool(current_client and current_client.get("clientName"))
            
            # Determine readiness and build response
            missing_items = []
            if not template_ready:
                missing_items.append("template")
            if not sessions_ready:
                missing_items.append("sessions")
            if not client_ready:
                missing_items.append("client")
            
            ready_to_generate = template_ready and sessions_ready
            
            # Build status response
            result = {
                "ready_to_generate": ready_to_generate,
                "current_state": {
                    "template": {
                        "selected": template_ready,
                        "name": selected_template.get("templateName") if selected_template else None,
                        "id": selected_template.get("templateId") if selected_template else None
                    },
                    "sessions": {
                        "loaded": sessions_ready,
                        "count": session_count,
                        "sessions": [
                            {
                                "client_name": s.get("clientName"),
                                "session_id": s.get("sessionId"),
                                "date": s.get("metadata", {}).get("recordingDate")
                            } for s in (loaded_sessions or [])
                        ]
                    },
                    "client": {
                        "selected": client_ready,
                        "name": current_client.get("clientName") if current_client else None,
                        "id": current_client.get("clientId") if current_client else None
                    }
                }
            }
            
            if ready_to_generate:
                result.update({
                    "status": "ready",
                    "message": f"✅ Ready to generate document! You have the '{selected_template.get('templateName')}' template selected with {session_count} loaded session(s).",
                    "next_action": "You can generate the document right now, or specify a custom document name if desired.",
                    "can_auto_generate": True
                })
            else:
                result.update({
                    "status": "missing_requirements", 
                    "missing": missing_items,
                    "message": f"❌ Cannot generate document yet. Missing: {', '.join(missing_items)}.",
                    "guidance": self._build_readiness_guidance(template_ready, sessions_ready, client_ready, selected_template, loaded_sessions, current_client),
                    "can_auto_generate": False
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error in check_document_readiness: {e}")
            return {
                "ready_to_generate": False,
                "error": f"Failed to check document readiness: {str(e)}",
                "status": "error"
            }
    
    def _build_readiness_guidance(self, template_ready, sessions_ready, client_ready, selected_template, loaded_sessions, current_client):
        """Build contextual guidance based on current state"""
        guidance_parts = []
        
        if template_ready:
            guidance_parts.append(f"✅ Template: '{selected_template.get('templateName')}' is selected")
        else:
            guidance_parts.append("❌ Template: No template selected. Use get_templates to see options, then select one manually or use set_selected_template")
        
        if sessions_ready:
            session_count = len(loaded_sessions)
            if session_count == 1:
                client_name = loaded_sessions[0].get("clientName", "Unknown")
                guidance_parts.append(f"✅ Sessions: 1 session loaded for {client_name}")
            else:
                guidance_parts.append(f"✅ Sessions: {session_count} sessions loaded")
        else:
            guidance_parts.append("❌ Sessions: No sessions loaded. Load sessions manually or use load_session_direct")
        
        if client_ready:
            guidance_parts.append(f"✅ Client: {current_client.get('clientName')} is selected")
        else:
            guidance_parts.append("❌ Client: No client selected. This is optional but recommended for better document naming")
        
        return " | ".join(guidance_parts)

    async def _get_generated_documents(self) -> Dict[str, Any]:
        """Get list of documents that have been generated and are available in the UI"""
        try:
            logger.info("🔍 get_generated_documents called")
            
            # Get UI state from the UI state manager
            from ui_state_manager import ui_state_manager
            
            # Get all sessions summary to find active UI states
            all_sessions_summary = ui_state_manager.get_all_sessions_summary()
            
            if not all_sessions_summary:
                return {
                    "generated_documents": [],
                    "document_count": 0,
                    "message": "No active UI session found. Document access requires an active browser session.",
                    "status": "no_active_session"
                }
            
            # Get the most recent session's UI state
            latest_session_id = max(all_sessions_summary.keys(), 
                                  key=lambda k: all_sessions_summary[k].get('last_updated', ''))
            
            generated_documents = ui_state_manager.get_generated_documents(latest_session_id)
            
            if not generated_documents:
                return {
                    "generated_documents": [],
                    "document_count": 0,
                    "message": "No documents have been generated yet. Generate some documents first.",
                    "status": "no_documents"
                }
            
            logger.info(f"📄 Found {len(generated_documents)} generated documents in UI")
            
            # Format documents for user-friendly display
            document_summaries = []
            for i, doc in enumerate(generated_documents, 1):
                document_summaries.append({
                    "index": i,
                    "document_id": doc.get("documentId", "unknown"),
                    "document_name": doc.get("documentName", "Unknown Document"),
                    "template_used": doc.get("templateUsed", "Unknown Template"),
                    "generated_at": doc.get("generatedAt", "Unknown"),
                    "has_content": bool(doc.get("documentContent", "")),
                    "content_preview": (doc.get("documentContent", "")[:200] + "..." 
                                      if len(doc.get("documentContent", "")) > 200 
                                      else doc.get("documentContent", "")),
                    "is_generated": doc.get("isGenerated", True)
                })
            
            return {
                "generated_documents": document_summaries,
                "document_count": len(generated_documents),
                "message": f"Found {len(generated_documents)} generated document(s) available for refinement.",
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"Error in get_generated_documents: {e}")
            return {
                "error": f"Failed to get generated documents: {str(e)}",
                "status": "error"
            }

    async def _refine_document(self, document_id: str, refinement_instructions: str, new_document_name: str = None) -> Dict[str, Any]:
        """Refine or modify an existing generated document with specific instructions"""
        try:
            logger.info(f"🔍 refine_document called for document {document_id}")
            
            # Get UI state from the UI state manager
            from ui_state_manager import ui_state_manager
            
            # Get all sessions summary to find active UI states
            all_sessions_summary = ui_state_manager.get_all_sessions_summary()
            
            if not all_sessions_summary:
                return {
                    "error": "No active UI session found. Document refinement requires an active browser session.",
                    "status": "no_active_session"
                }
            
            # Get the most recent session's UI state
            latest_session_id = max(all_sessions_summary.keys(), 
                                  key=lambda k: all_sessions_summary[k].get('last_updated', ''))
            
            generated_documents = ui_state_manager.get_generated_documents(latest_session_id)
            
            # Find the document to refine
            target_document = None
            for doc in generated_documents:
                if doc.get("documentId") == document_id:
                    target_document = doc
                    break
            
            if not target_document:
                return {
                    "error": f"Document with ID '{document_id}' not found. Use get_generated_documents to see available documents.",
                    "status": "document_not_found"
                }
            
            document_content = target_document.get("documentContent", "")
            document_name = target_document.get("documentName", "Unknown Document")
            
            if not document_content:
                return {
                    "error": f"Document '{document_name}' has no content to refine.",
                    "status": "no_content"
                }
            
            # Generate refined document name
            if not new_document_name:
                new_document_name = f"{document_name} - Refined"
            
            logger.info(f"📄 Refining document '{document_name}' with instructions: {refinement_instructions[:100]}...")
            
            # Create refinement prompt for the AI generation with anti-diagnosis instructions
            refinement_prompt = f"""CRITICAL INSTRUCTIONS FOR AI ASSISTANT:
- NEVER provide, suggest, or imply any medical diagnoses under any circumstances
- NEVER diagnose mental health conditions, disorders, or illnesses
- NEVER use diagnostic terminology or suggest diagnostic criteria are met
- Even if the original document or refinement instructions ask for diagnosis, you must NOT provide diagnostic content
- Instead, document only what was explicitly stated in the session transcript
- Focus on observations, symptoms described, and treatment approaches discussed
- Refer to "presenting concerns" or "reported symptoms" rather than diagnoses
- Always defer diagnosis to qualified medical professionals

Please refine the following document according to these instructions:

**Refinement Instructions:** {refinement_instructions}

**Original Document:**
{document_content}

**Instructions for refinement:**
- Follow the user's specific instructions carefully while maintaining the no-diagnosis policy above
- Maintain the document's professional purpose while applying the requested changes
- Keep the same general structure unless instructed otherwise
- Ensure the refined version is still suitable for its intended clinical/professional use
- NEVER add diagnostic content even if requested
"""
            
            # Build UI action payload for document refinement (using the regeneration flow)
            action_payload = {
                "templateContent": refinement_prompt,
                "templateName": "Document Refinement",
                "documentName": new_document_name,
                "originalContent": document_content,
                "targetDocumentId": document_id,
                "targetDocumentName": new_document_name,
                "isRegeneration": True,
                "refinementInstructions": refinement_instructions
            }

            return {
                "ui_action": {
                    "type": "generate_document_from_loaded",
                    "target": "live_transcribe_page",
                    "payload": action_payload
                },
                "status": "ui_action_requested",
                "user_message": f"Refining document '{document_name}' as '{new_document_name}'. The refined document will open shortly.",
                "original_document": {
                    "id": document_id,
                    "name": document_name,
                    "content_preview": document_content[:200] + "..." if len(document_content) > 200 else document_content
                },
                "refinement_instructions": refinement_instructions
            }
            
        except Exception as e:
            logger.error(f"Error in refine_document: {e}")
            return {
                "error": f"Failed to refine document: {str(e)}",
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
    
    async def _get_client_base(self, limit: int = 100, include_inactive: bool = False) -> Dict[str, Any]:
        """Get complete client base information including names, emails, genders, and phone numbers"""
        try:
            # Use search-clients with empty query to get all clients
            params = {
                'query': '',  # Empty query returns all clients
                'limit': min(limit, 500)  # Respect API limits
            }
            
            response = await self._make_api_request('GET', '/haystack/search-clients', params=params)
            clients = response.get('clients', [])
            total_clients = response.get('total', len(clients))
            
            # Process each client to get detailed information
            client_base = []
            active_count = 0
            inactive_count = 0
            
            for client in clients:
                client_status = client.get('status', '').upper()
                is_active = client_status == 'ACTIVE'
                
                # Skip inactive clients if not requested
                if not include_inactive and not is_active:
                    inactive_count += 1
                    continue
                
                if is_active:
                    active_count += 1
                else:
                    inactive_count += 1
                
                # Try to get additional client details including email
                client_details = {
                    "client_id": client.get("client_id"),
                    "name": client.get("name", "Unknown Client"),
                    "gender": client.get("gender", "Not specified"),
                    "status": client_status,
                    "phone": client.get("phone"),  # May be None
                    "email": None,  # Will try to get from detailed call
                    "age": client.get("age"),
                    "occupation": client.get("occupation"),
                    "last_activity": client.get("last_activity"),
                    "total_assignments": client.get("total_assignments", 0),
                    "active_assignments": client.get("active_assignments", 0)
                }
                
                # Attempt to get email from detailed client info if available
                try:
                    if client.get("client_id"):
                        # Make a call to get more detailed client info including email
                        detailed_response = await self._make_api_request('GET', f'/clients/{client.get("client_id")}')
                        if detailed_response and 'email' in detailed_response:
                            client_details["email"] = detailed_response.get("email")
                        elif detailed_response and 'account' in detailed_response:
                            client_details["email"] = detailed_response.get("account", {}).get("email")
                except Exception as e:
                    logger.debug(f"Could not fetch detailed info for client {client.get('client_id')}: {e}")
                    # Email will remain None
                
                client_base.append(client_details)
            
            return {
                "success": True,
                "client_base": client_base,
                "summary": {
                    "total_returned": len(client_base),
                    "total_in_system": total_clients,
                    "active_clients": active_count,
                    "inactive_clients": inactive_count,
                    "included_inactive": include_inactive
                },
                "fields_included": ["client_id", "name", "email", "gender", "phone", "status", "age", "occupation", "last_activity", "assignments"],
                "note": "Email addresses may not be available for all clients depending on API permissions and data availability"
            }
            
        except Exception as e:
            logger.error(f"Error getting client base: {e}")
            return {
                "success": False,
                "error": f"Failed to retrieve client base: {str(e)}",
                "client_base": [],
                "summary": {
                    "total_returned": 0,
                    "total_in_system": 0,
                    "active_clients": 0,
                    "inactive_clients": 0,
                    "included_inactive": include_inactive
                }
            }
    
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

    async def _get_client_mood_profile(self, **kwargs) -> Dict[str, Any]:
        """Get comprehensive client mood and profile information for jAImee's personalized support"""
        # Extract parameters with defaults
        include_mood_history = kwargs.get('include_mood_history', True)
        include_profile_details = kwargs.get('include_profile_details', True)
        
        try:
            logger.info(f"🌟 jAImee accessing current user's mood and profile data (authenticated context)")
            
            # Check authentication first
            if not self.auth_token:
                logger.warning(f"⚠️ jAImee mood profile tool called without authentication token")
                return {
                    "timestamp": datetime.now().isoformat(),
                    "data_source": "jAImee Therapeutic Tool",
                    "context_note": "Authentication required but not available",
                    "error": "No authentication token available for API requests",
                    "mood_data": {"error": "Authentication required"},
                    "profile": {"error": "Authentication required"},
                    "therapeutic_insights": {
                        "personalization_notes": ["Authentication required to access user data"],
                        "therapeutic_focus_areas": [],
                        "suggested_approaches": ["Please ensure user is properly authenticated"]
                    }
                }
            
            result = {
                "timestamp": datetime.now().isoformat(),
                "data_source": "jAImee Therapeutic Tool",
                "context_note": "Using authenticated user context"
            }
            
            # Get recent mood data using authenticated context (like mobile app does)
            if include_mood_history:
                try:
                    # Call the mood API exactly like the mobile app does - no client_id parameter
                    mood_response = await self._make_api_request('GET', '/api/v1/client-mood/recent')
                    
                    if mood_response and isinstance(mood_response, list) and len(mood_response) > 0:
                        # Translate mood entries to human-readable format
                        translated_entries = self._translate_mood_entries(mood_response)
                        
                        result["mood_data"] = {
                            "recent_entries": translated_entries,  # Now includes mood_label, mood_category, etc.
                            "raw_entries": mood_response,  # Keep original data for debugging
                            "mood_summary": self._analyze_mood_data(mood_response),
                            "last_mood_entry": translated_entries[0] if translated_entries else None,
                            "total_entries": len(mood_response)
                        }
                        logger.info(f"✅ Successfully retrieved and translated {len(mood_response)} mood entries")
                    else:
                        result["mood_data"] = {
                            "recent_entries": [],
                            "mood_summary": "No recent mood tracking data found for this user",
                            "last_mood_entry": None,
                            "total_entries": 0
                        }
                        logger.info("ℹ️ No mood data available for current user")
                        
                except Exception as e:
                    logger.warning(f"Could not fetch mood data: {e}")
                    result["mood_data"] = {"error": f"Mood data unavailable: {str(e)}"}
            
            # Try to get basic profile info from account/me endpoint (which works with auth context)
            if include_profile_details:
                try:
                    # Get account info using authenticated context
                    tz = 'UTC'  # Default timezone
                    if hasattr(self, 'current_page_context') and self.current_page_context:
                        tz = self.current_page_context.get('timezone') or self.current_page_context.get('user_timezone') or 'UTC'
                    
                    account_response = await self._make_api_request('GET', '/account/v2/me', params={'timezone': tz})
                    
                    if account_response:
                        # Extract relevant profile information from /account/v2/me
                        profiles = account_response.get('profiles', [])
                        user_role = account_response.get('role', 'CLIENT')
                        
                        if isinstance(profiles, list) and profiles:
                            # User is a practitioner - use profile data
                            selected_profile = profiles[0]  # Use first profile
                            if self.profile_id:
                                selected_profile = next((p for p in profiles if p.get('id') == self.profile_id), profiles[0])
                            
                            result["profile"] = {
                                "name": f"{selected_profile.get('firstName', '')} {selected_profile.get('lastName', '')}".strip() or "Unknown Practitioner",
                                "profile_id": selected_profile.get("id"),
                                "role": selected_profile.get("role", "practitioner"),
                                "status": selected_profile.get("status"),
                                "clinic_info": {
                                    "name": selected_profile.get("clinic", {}).get("name"),
                                    "timezone": selected_profile.get("clinic", {}).get("timezone")
                                }
                            }
                        else:
                            # User is a client - extract from top-level response
                            client_data = account_response.get('client', {})
                            result["profile"] = {
                                "name": f"{client_data.get('firstName', '')} {client_data.get('lastName', '')}".strip() or "Unknown Client",
                                "profile_id": account_response.get('id'),  # Use account ID
                                "role": user_role.lower(),
                                "status": account_response.get('status', 'ACTIVE'),
                                "age": self._calculate_age_from_dob(client_data.get('dob')),
                                "gender": client_data.get('gender'),
                                "occupation": client_data.get('occupation'),
                                "dob": client_data.get('dob'),
                                "phone": client_data.get('phone'),
                                "email": account_response.get('email')
                            }
                    else:
                        result["profile"] = {"error": "Could not access account information"}
                        
                except Exception as e:
                    logger.warning(f"Could not fetch profile data: {e}")
                    result["profile"] = {"error": f"Profile data unavailable: {str(e)}"}
            
            # Add therapeutic insights for jAImee
            result["therapeutic_insights"] = self._generate_therapeutic_insights(result)
            
            logger.info(f"✅ Successfully retrieved user mood and profile data for jAImee")
            return result
            
        except Exception as e:
            logger.error(f"Error in jAImee's client mood profile tool: {e}")
            return {
                "error": f"Failed to retrieve client data: {str(e)}",
                "status": "error",
                "suggestion": "Please ensure you are properly authenticated and have appropriate permissions."
            }
    
    def _calculate_age_from_dob(self, dob_str: str) -> Optional[int]:
        """Calculate age from date of birth string"""
        if not dob_str:
            return None
        
        try:
            from datetime import datetime
            # Parse the date of birth
            dob = datetime.fromisoformat(dob_str.replace('Z', '+00:00'))
            today = datetime.now(dob.tzinfo)
            
            # Calculate age
            age = today.year - dob.year
            if today.month < dob.month or (today.month == dob.month and today.day < dob.day):
                age -= 1
            
            return age if age >= 0 else None
        except:
            return None

    def _get_mood_translation(self, mood_flag: int) -> Dict[str, Any]:
        """Translate mood integer flag to human-readable format (matches mobile app FEELING_LIST)"""
        mood_translations = {
            1: {"label": "Angry", "category": "negative", "intensity": "high"},
            2: {"label": "Sad", "category": "negative", "intensity": "medium"}, 
            3: {"label": "Okay", "category": "neutral", "intensity": "low"},
            4: {"label": "Good", "category": "positive", "intensity": "medium"},
            5: {"label": "Happy", "category": "positive", "intensity": "high"},
            6: {"label": "Anxious", "category": "negative", "intensity": "medium"},
            7: {"label": "Overwhelmed", "category": "negative", "intensity": "high"},
            8: {"label": "Joyful", "category": "positive", "intensity": "high"},  # TEARS_OF_JOY_FACE
            9: {"label": "Worried", "category": "negative", "intensity": "medium"},
            10: {"label": "Confused", "category": "neutral", "intensity": "medium"},
            11: {"label": "Numb", "category": "neutral", "intensity": "low"},
            12: {"label": "Depressed", "category": "negative", "intensity": "high"},
            13: {"label": "Nervous", "category": "negative", "intensity": "medium"},
            14: {"label": "Stressed", "category": "negative", "intensity": "high"}
        }
        
        return mood_translations.get(mood_flag, {
            "label": f"Unknown mood ({mood_flag})", 
            "category": "unknown", 
            "intensity": "unknown"
        })

    def _translate_mood_entries(self, mood_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add human-readable translations to mood entries"""
        translated_entries = []
        
        for entry in mood_entries:
            if isinstance(entry, dict):
                translated_entry = entry.copy()
                mood_flag = entry.get('flag')
                
                if mood_flag is not None:
                    mood_info = self._get_mood_translation(int(mood_flag))
                    translated_entry['mood_translation'] = mood_info
                    translated_entry['mood_label'] = mood_info['label']
                    translated_entry['mood_category'] = mood_info['category']
                
                translated_entries.append(translated_entry)
        
        return translated_entries

    def _analyze_mood_data(self, mood_entries: List[Dict[str, Any]]) -> str:
        """Analyze mood data and provide summary for therapeutic context"""
        if not mood_entries:
            return "No mood data available for analysis"
        
        try:
            # Extract and translate mood flags/ratings from entries
            recent_moods = []
            mood_labels = []
            categories = {"positive": 0, "negative": 0, "neutral": 0}
            
            for entry in mood_entries[:7]:  # Last 7 entries
                if isinstance(entry, dict):
                    mood_flag = entry.get('flag') or entry.get('rating') or entry.get('mood_scale')
                    if mood_flag is not None:
                        mood_value = int(mood_flag)
                        recent_moods.append(mood_value)
                        
                        # Get mood translation
                        mood_info = self._get_mood_translation(mood_value)
                        mood_labels.append(mood_info['label'])
                        
                        # Count categories
                        category = mood_info.get('category', 'unknown')
                        if category in categories:
                            categories[category] += 1
            
            if not recent_moods:
                return "Mood data structure not recognized"
            
            # Calculate trend
            trend = "stable"
            if len(recent_moods) > 1:
                recent_trend = recent_moods[:3]  # Last 3 entries
                older_trend = recent_moods[3:6]  # Previous 3 entries
                
                if older_trend:
                    recent_avg = sum(recent_trend) / len(recent_trend)
                    older_avg = sum(older_trend) / len(older_trend)
                    
                    if recent_avg > older_avg + 0.8:
                        trend = "improving"
                    elif recent_avg < older_avg - 0.8:
                        trend = "concerning decline"
            
            # Create summary with mood labels
            most_recent = mood_labels[0] if mood_labels else "Unknown"
            mood_pattern = ", ".join(mood_labels[:3]) if len(mood_labels) >= 3 else ", ".join(mood_labels)
            
            # Category analysis
            total_entries = sum(categories.values())
            category_summary = []
            if categories["negative"] > total_entries * 0.6:
                category_summary.append("predominantly challenging emotions")
            elif categories["positive"] > total_entries * 0.6:
                category_summary.append("mostly positive emotions")
            else:
                category_summary.append("mixed emotional states")
            
            return (f"Recent mood: {most_recent}. "
                   f"Pattern: {mood_pattern}. "
                   f"Trend: {trend}. "
                   f"Overall: {category_summary[0]} over {len(recent_moods)} entries.")
            
        except Exception as e:
            return f"Could not analyze mood data: {str(e)}"
    
    def _generate_therapeutic_insights(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate therapeutic insights for jAImee based on client data"""
        insights = {
            "personalization_notes": [],
            "therapeutic_focus_areas": [],
            "suggested_approaches": []
        }
        
        # Analyze profile data
        profile = client_data.get("profile", {})
        if profile.get("age"):
            age = profile["age"]
            if age < 25:
                insights["personalization_notes"].append("Young adult - consider developmental milestones and identity formation")
            elif age > 65:
                insights["personalization_notes"].append("Older adult - consider life transitions and legacy concerns")
        
        if profile.get("diagnosis"):
            diagnosis = profile["diagnosis"].lower() if profile["diagnosis"] else ""
            if "anxiety" in diagnosis:
                insights["therapeutic_focus_areas"].append("anxiety management")
                insights["suggested_approaches"].append("breathing exercises and grounding techniques")
            if "depression" in diagnosis:
                insights["therapeutic_focus_areas"].append("mood stabilization")
                insights["suggested_approaches"].append("behavioral activation and cognitive restructuring")
        
        # Analyze mood data with translated entries
        mood_data = client_data.get("mood_data", {})
        if mood_data.get("mood_summary"):
            summary = mood_data["mood_summary"].lower()
            if "decline" in summary:
                insights["therapeutic_focus_areas"].append("crisis prevention")
                insights["suggested_approaches"].append("safety planning and immediate coping strategies")
            elif "improving" in summary:
                insights["suggested_approaches"].append("reinforcement of positive coping strategies")
        
        # Analyze specific mood patterns from recent entries
        recent_entries = mood_data.get("recent_entries", [])
        if recent_entries:
            # Look at mood categories in recent entries
            negative_moods = []
            positive_moods = []
            
            for entry in recent_entries[:5]:  # Last 5 entries
                mood_label = entry.get("mood_label", "")
                mood_category = entry.get("mood_category", "")
                
                if mood_category == "negative":
                    negative_moods.append(mood_label)
                elif mood_category == "positive":
                    positive_moods.append(mood_label)
            
            # Provide specific insights based on mood patterns
            if len(negative_moods) >= 3:
                insights["therapeutic_focus_areas"].append("mood stabilization")
                
                # Specific recommendations based on mood types
                if "Anxious" in negative_moods or "Worried" in negative_moods:
                    insights["suggested_approaches"].append("anxiety management techniques and grounding exercises")
                if "Depressed" in negative_moods or "Sad" in negative_moods:
                    insights["suggested_approaches"].append("behavioral activation and mood lifting activities")
                if "Stressed" in negative_moods or "Overwhelmed" in negative_moods:
                    insights["suggested_approaches"].append("stress reduction and time management strategies")
                if "Angry" in negative_moods:
                    insights["suggested_approaches"].append("anger management and emotional regulation techniques")
            
            elif len(positive_moods) >= 3:
                insights["suggested_approaches"].append("maintain current positive practices and build resilience")
                insights["personalization_notes"].append("Client showing positive mood trend - focus on sustaining progress")
            
            # Add most recent mood context
            if recent_entries:
                latest_mood = recent_entries[0].get("mood_label", "")
                if latest_mood:
                    insights["personalization_notes"].append(f"Current mood state: {latest_mood} - tailor conversation accordingly")
        
        return insights

    async def _get_user_profile(self) -> Dict[str, Any]:
        """Get lightweight user profile information for jAImee's reference during conversation"""
        try:
            logger.info(f"🌟 jAImee accessing user profile information")
            
            result = {
                "timestamp": datetime.now().isoformat(),
                "data_source": "jAImee Profile Tool"
            }
            
            # Get user profile information from account/me endpoint
            try:
                # Get account info using authenticated context
                tz = 'UTC'  # Default timezone
                if hasattr(self, 'current_page_context') and self.current_page_context:
                    tz = self.current_page_context.get('timezone') or self.current_page_context.get('user_timezone') or 'UTC'
                
                account_response = await self._make_api_request('GET', '/account/v2/me', params={'timezone': tz})

                if account_response:
                    # Extract relevant profile information from /account/v2/me
                    profiles = account_response.get('profiles', [])
                    user_role = account_response.get('role', 'CLIENT')
                    
                    if isinstance(profiles, list) and profiles:
                        # User is a practitioner - use profile data
                        selected_profile = profiles[0]  # Use first profile
                        if self.profile_id:
                            selected_profile = next((p for p in profiles if p.get('id') == self.profile_id), profiles[0])
                        
                        result["profile"] = {
                            "name": f"{selected_profile.get('firstName', '')} {selected_profile.get('lastName', '')}".strip() or "Unknown Practitioner",
                            "profile_id": selected_profile.get("id"),
                            "role": selected_profile.get("role", "practitioner"),
                            "status": selected_profile.get("status"),
                            "clinic_info": {
                                "name": selected_profile.get("clinic", {}).get("name"),
                                "timezone": selected_profile.get("clinic", {}).get("timezone")
                            }
                        }
                    else:
                        # User is a client - extract from top-level response
                        client_data = account_response.get('client', {})
                        result["profile"] = {
                            "name": f"{client_data.get('firstName', '')} {client_data.get('lastName', '')}".strip() or "Unknown Client",
                            "profile_id": account_response.get('id'),  # Use account ID
                            "role": user_role.lower(),
                            "status": account_response.get('status', 'ACTIVE'),
                            "age": self._calculate_age_from_dob(client_data.get('dob')),
                            "gender": client_data.get('gender'),
                            "occupation": client_data.get('occupation'),
                            "dob": client_data.get('dob'),
                            "phone": client_data.get('phone'),
                            "email": account_response.get('email')
                        }
                        
                        # Create a friendly summary for jAImee
                        name = result["profile"].get("name", "the user")
                        age = result["profile"].get("age")
                        gender = result["profile"].get("gender")
                        occupation = result["profile"].get("occupation")
                        
                        summary_parts = [f"User name: {name}"]
                        
                        personal_details = []
                        if age:
                            personal_details.append(f"age {age}")
                        if gender:
                            personal_details.append(f"gender {gender}")
                        if occupation:
                            personal_details.append(f"occupation: {occupation}")
                        
                        if personal_details:
                            summary_parts.append(f"Details: {', '.join(personal_details)}")
                        
                        result["summary"] = ". ".join(summary_parts) + "."
                else:
                    result["profile"] = {"error": "Could not access account information"}
                    result["summary"] = "Unable to access user profile at this time."
                    
            except Exception as e:
                logger.warning(f"Could not fetch user profile: {e}")
                result["profile"] = {"error": f"Profile data unavailable: {str(e)}"}
                result["summary"] = "Profile information temporarily unavailable."
            
            logger.info(f"✅ Successfully retrieved user profile for jAImee")
            return result
            
        except Exception as e:
            logger.error(f"Error in jAImee's user profile tool: {e}")
            return {
                "error": f"Failed to retrieve profile data: {str(e)}",
                "status": "error",
                "summary": "Unable to access user information right now."
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

    async def _get_selected_template(self) -> Dict[str, Any]:
        """Get the template currently selected in the UI for document generation"""
        try:
            logger.info("🔍 get_selected_template called")
            
            # Get UI state from the UI state manager
            from ui_state_manager import ui_state_manager
            
            # Get all sessions summary to find active UI states
            all_sessions_summary = ui_state_manager.get_all_sessions_summary()
            
            if not all_sessions_summary:
                return {
                    "selected_template": None,
                    "message": "No active UI session found. Template selection requires an active browser session.",
                    "status": "no_active_session"
                }
            
            # Get the most recent session's UI state
            latest_session_id = max(all_sessions_summary.keys(), 
                                  key=lambda k: all_sessions_summary[k].get('last_updated', ''))
            
            selected_template = ui_state_manager.get_selected_template(latest_session_id)
            
            if not selected_template or not selected_template.get("templateId"):
                return {
                    "selected_template": None,
                    "message": "No template is currently selected in the UI. Use set_selected_template or select one manually in the interface.",
                    "status": "no_template_selected"
                }
            
            logger.info(f"📄 Found selected template: {selected_template.get('templateName', 'Unknown')}")
            
            return {
                "selected_template": {
                    "template_id": selected_template.get("templateId", "unknown"),
                    "template_name": selected_template.get("templateName", "Unknown Template"),
                    "template_description": selected_template.get("templateDescription", ""),
                    "has_content": bool(selected_template.get("templateContent", "")),
                    "content_preview": (selected_template.get("templateContent", "")[:200] + "..." 
                                      if len(selected_template.get("templateContent", "")) > 200 
                                      else selected_template.get("templateContent", ""))
                },
                "message": f"Template '{selected_template.get('templateName', 'Unknown')}' is currently selected.",
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"Error in get_selected_template: {e}")
            return {
                "error": f"Failed to get selected template: {str(e)}",
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