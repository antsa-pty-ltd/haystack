
# Haystack Agentic AI Guide

This document covers the Haystack service's agentic AI capabilities - how the pipeline works, tool execution, personas, and UI action collection.

## Overview

Haystack uses a declarative pipeline architecture with OpenAI's function calling to create an agentic AI that can:
- Execute tools to fetch data (clients, sessions, templates)
- Trigger UI actions (load sessions, generate documents)
- Maintain conversation context with tool results
- Stream responses in real-time

---

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Haystack Declarative Pipeline                        │
│                                                                          │
│  ┌──────────────┐    ┌─────────────────┐    ┌──────────────────────┐   │
│  │   Generator   │───►│ ConditionalRouter│───►│    ToolInvoker       │   │
│  │ (OpenAI GPT)  │    │                 │    │ (executes tools)     │   │
│  └──────────────┘    └─────────────────┘    └──────────┬───────────┘   │
│         ▲                    │                          │               │
│         │                    │ no tool calls            ▼               │
│         │                    ▼                 ┌──────────────────┐    │
│         │            ┌──────────────┐         │ UIActionCollector │    │
│         │            │Final Response│         │ (extracts actions)│    │
│         │            └──────────────┘         └──────────┬───────┘    │
│         │                                                │              │
│         │              ┌──────────────────┐              │              │
│         └──────────────│ MessageCollector │◄─────────────┘              │
│                        │(accumulates msgs)│                             │
│                        └──────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────┘
```

### Pipeline Loop

1. **Generator** sends messages to OpenAI, which may return tool calls
2. **ConditionalRouter** checks if there are tool calls
3. If tool calls exist → **ToolInvoker** executes them
4. **UIActionCollector** extracts any `ui_action` from tool results
5. **MessageCollector** accumulates all messages
6. Loop back to Generator with updated context
7. When no more tool calls → return final response

---

## Key Files

| File | Purpose |
|------|---------|
| `haystack_pipeline.py` | Pipeline definition, streaming, UI action collection |
| `tools.py` | ToolManager with all tool implementations |
| `personas.py` | Persona configurations and system prompts |
| `ui_state_manager.py` | Redis-backed UI state tracking |
| `components/ui_actions.py` | UIActionCollector component |
| `main.py` | WebSocket endpoint, message handling |

---

## Personas

Each persona has different capabilities and system prompts.

### WEB_ASSISTANT
- **Purpose**: General help, session/document management
- **Tools**: Full access to all tools
- **System Prompt**: Professional assistant for ANTSA platform

### JAIMEE_THERAPIST  
- **Purpose**: Therapeutic conversation
- **Tools**: Limited (no client data access)
- **System Prompt**: Empathetic, therapeutic communication style

### TRANSCRIBER_AGENT
- **Purpose**: Document generation from transcripts
- **Tools**: Document-focused tools
- **System Prompt**: Focused on converting transcripts to documents

### Persona Configuration

```python
# personas.py
@dataclass
class PersonaConfig:
    name: str
    description: str
    system_prompt: str
    model: str = "gpt-5.2"
    temperature: float = 0.7
    max_completion_tokens: int = 1000
    has_db_access: bool = False
    tools: List[Dict[str, Any]] = []
    available_functions: Dict[str, Callable] = {}
```

---

## Tool System

### Tool Definition Structure

```python
# tools.py
"search_clients": {
    "definition": {
        "type": "function",
        "function": {
            "name": "search_clients",
            "description": "Search for clients by name...",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query..."
                    }
                },
                "required": ["query"]
            }
        }
    },
    "implementation": self._search_clients
}
```

### Tool Execution Flow

```
OpenAI returns tool_call
        │
        ▼
ToolInvoker calls Haystack Tool wrapper
        │
        ▼
Wrapper calls execute_tool(tool_name, arguments)
        │
        ▼
execute_tool wraps result:
{
    "success": True,
    "result": <actual_tool_result>,
    "tool": "tool_name",
    "timestamp": "..."
}
        │
        ▼
Result converted to JSON string
        │
        ▼
Stored in ChatMessage.tool_call_result.result
```

---

## Available Tools

### Client Tools

| Tool | Purpose | Returns |
|------|---------|---------|
| `search_clients` | Find clients by name | List of matching clients |
| `get_client_summary` | Get client details | Client info, recent sessions |
| `get_client_sessions` | List client's sessions | Session summaries |
| `get_client_homework_status` | Check homework assignments | Assignment status |

### Session Tools

| Tool | Purpose | Returns |
|------|---------|---------|
| `load_session_direct` | Load session into UI | UI action to load |
| `load_multiple_sessions` | Load multiple sessions | UI action (array) |
| `get_loaded_sessions` | Get currently loaded sessions | Session list from UI state |
| `get_session_content` | Get transcript content | Full transcript text |
| `analyze_loaded_session` | Analyze transcript | Themes, sentiment, summary |

### Template Tools

| Tool | Purpose | Returns |
|------|---------|---------|
| `get_templates` | List available templates | Template list |
| `set_selected_template` | Select template in UI | UI action |
| `select_template_by_name` | Select by name search | UI action |

### Document Tools

| Tool | Purpose | Returns |
|------|---------|---------|
| `check_document_readiness` | Check if ready to generate | Status, missing items |
| `generate_document_auto` | Generate from loaded sessions | UI action to generate |
| `generate_document_from_loaded` | Generate with specific params | UI action |
| `get_generated_documents` | List generated docs | Document summaries |
| `refine_document` | Modify existing document | UI action to regenerate |

### Navigation Tools

| Tool | Purpose | Returns |
|------|---------|---------|
| `suggest_navigation` | Suggest page navigation | Navigation suggestion |
| `navigate_to_page` | Navigate directly | Navigation action |

---

## UI Action Tools

Tools that trigger UI changes return a special structure:

```python
async def _refine_document(self, document_id: str, refinement_instructions: str, ...):
    # ... process refinement ...
    
    return {
        "ui_action": {
            "type": "generate_document_from_loaded",
            "target": "live_transcribe_page",
            "payload": {
                "templateContent": refinement_prompt,
                "documentName": new_document_name,
                "isRegeneration": True,
                "targetDocumentId": document_id,
                "originalContent": document_content,
                "refinementInstructions": refinement_instructions
            }
        },
        "status": "ui_action_requested",
        "user_message": "Refining document..."
    }
```

### UI Action Extraction

The `UIActionCollector` component extracts these:

```python
# components/ui_actions.py
class UIActionCollector:
    def run(self, messages: List[ChatMessage]) -> Dict[str, Any]:
        ui_actions = []
        
        for msg in messages:
            if msg.role != ChatRole.TOOL:
                continue
            
            raw_content = msg.tool_call_result.result
            content = json.loads(raw_content)
            
            # Check direct ui_action
            ui_action_data = content.get("ui_action")
            
            # Check nested in result (from execute_tool wrapper)
            if not ui_action_data and content.get("result"):
                ui_action_data = content["result"].get("ui_action")
            
            if ui_action_data:
                ui_actions.append(ui_action_data)
        
        return {"messages": messages, "ui_actions": ui_actions}
```

---

## UI State Manager

Tracks what's happening in the frontend UI.

### State Structure

```python
class UIState(TypedDict, total=False):
    last_updated: str
    page_type: str
    page_url: str
    loadedSessions: List[LoadedSessionData]
    currentClient: Optional[CurrentClientData]
    selectedTemplate: Optional[TemplateData]
    generatedDocuments: List[DocumentData]
```

### Redis Storage

State is persisted in Redis with 24-hour TTL:
```python
key = f"ui_state:{session_id}"
redis_client.setex(key, 86400, json.dumps(state))
```

### Accessing State in Tools

```python
async def _get_loaded_sessions(self) -> Dict[str, Any]:
    from ui_state_manager import ui_state_manager
    
    # Get all active sessions
    all_sessions_summary = ui_state_manager.get_all_sessions_summary_sync()
    
    # Find most recent
    latest_session_id = max(all_sessions_summary.keys(), 
                          key=lambda k: all_sessions_summary[k].get('last_updated', ''))
    
    # Get loaded sessions from that UI state
    loaded_sessions = ui_state_manager.get_loaded_sessions_sync(latest_session_id)
    
    return {
        "loaded_sessions": loaded_sessions,
        "session_count": len(loaded_sessions),
        "status": "success"
    }
```

---

## Streaming Implementation

### Generator Streaming

```python
# haystack_pipeline.py
async def generate_response_stream(self, session_id: str, message: str, ...):
    # ... setup ...
    
    for iteration in range(max_iterations):
        # Run generator
        gen_result = generator.run(messages=current_messages)
        replies = gen_result.get("replies", [])
        
        if not replies:
            break
        
        reply = replies[0]
        
        # Stream text content
        if reply.text:
            yield reply.text
            full_response += reply.text
        
        # Check for tool calls
        if not reply.tool_calls:
            break  # No more tools, done
        
        # Execute tools
        yield "

[tools] Executing...

"
        tool_result = tool_invoker.run(messages=replies)
        
        # Collect UI actions
        if ui_collector:
            ui_result = ui_collector.run(messages=tool_result["tool_messages"])
            self._ui_actions.extend(ui_result.get("ui_actions", []))
        
        # Continue loop with tool results
        current_messages.extend(replies)
        current_messages.extend(tool_result["tool_messages"])
```

### WebSocket Delivery

```python
# main.py
async for chunk in pipeline_manager.generate_response_stream(...):
    await websocket.send_text(json.dumps({
        "type": "message_chunk",
        "content": chunk,
        "session_id": session_id
    }))

# After streaming complete, send UI actions
ui_actions = pipeline_manager.pop_ui_actions()
for action in ui_actions:
    await websocket.send_text(json.dumps({
        "type": "ui_action",
        "action": action,
        "session_id": session_id
    }))

await websocket.send_text(json.dumps({
    "type": "message_complete",
    "session_id": session_id
}))
```

---

## Tool Context Injection

Tools receive context about the current page and user:

```python
async def _ensure_tools_context(session_id: str, message_data: Dict[str, Any]):
    auth_token = message_data.get("auth_token")
    profile_id = message_data.get("profile_id")
    
    if auth_token:
        tool_manager.set_auth_token(auth_token, profile_id)
    
    # Page context from UI state
    ui_state = await ui_state_manager.get_state(session_id)
    page_context = _build_page_context_from_ui_state(ui_state)
    
    tool_manager.set_page_context(page_context)
```

### Auth Token Flow

```
Frontend sends auth token in message
        │
        ▼
_ensure_tools_context() extracts it
        │
        ▼
tool_manager.set_auth_token(token)
        │
        ▼
Tools use token for API calls:
self._make_api_request('GET', 'clients', headers={'Authorization': f'Bearer {self.auth_token}'})
```

---

## System Prompt Enhancement

The system prompt is dynamically enhanced with UI state:

```python
def get_enhanced_system_prompt(persona_type: str, ui_state: Dict[str, Any]) -> str:
    base_prompt = persona_manager.get_persona(persona_type).system_prompt
    
    # Add current context
    context_parts = []
    
    if ui_state.get('currentClient'):
        client = ui_state['currentClient']
        context_parts.append(f"Current Client: {client.get('clientName')}")
    
    if ui_state.get('loadedSessions'):
        count = len(ui_state['loadedSessions'])
        context_parts.append(f"Loaded Sessions: {count}")
    
    if ui_state.get('selectedTemplate'):
        template = ui_state['selectedTemplate']
        context_parts.append(f"Selected Template: {template.get('templateName')}")
    
    if context_parts:
        return f"{base_prompt}

## Current Context
" + "
".join(context_parts)
    
    return base_prompt
```

---

## Error Handling

### Tool Execution Errors

```python
async def execute_tool(self, tool_name: str, arguments: Dict[str, Any], ...):
    try:
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
```

### Pipeline Errors

```python
async def generate_response_stream(self, ...):
    try:
        # ... pipeline logic ...
    except Exception as e:
        logger.error(f"Error in pipeline: {e}")
        error_msg = "I apologize, but I encountered an error. Please try again."
        await session_manager.add_message(session_id, "assistant", error_msg)
        yield error_msg
```

---

## Adding New Tools

### 1. Define the Tool

```python
# In tools.py __init__
"my_new_tool": {
    "definition": {
        "type": "function",
        "function": {
            "name": "my_new_tool",
            "description": "What this tool does",
            "parameters": {
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "string",
                        "description": "Parameter description"
                    }
                },
                "required": ["param1"]
            }
        }
    },
    "implementation": self._my_new_tool
}
```

### 2. Implement the Tool

```python
async def _my_new_tool(self, param1: str) -> Dict[str, Any]:
    try:
        # Do something
        result = await self._make_api_request('GET', f'endpoint/{param1}')
        
        return {
            "data": result,
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Error in my_new_tool: {e}")
        return {
            "error": str(e),
            "status": "error"
        }
```

### 3. Add to Persona

```python
# In get_tools_for_persona()
if persona_type == "web_assistant":
    return [
        # ... existing tools ...
        self.tools["my_new_tool"]["definition"],
    ]
```

### 4. Add to Functions Map

```python
# In get_functions_for_persona()
if persona_type == "web_assistant":
    return {
        # ... existing functions ...
        "my_new_tool": self.tools["my_new_tool"]["implementation"],
    }
```

---

## Debugging Tools

### Logging

All tools log extensively:
```python
logger.info(f"🔍 get_loaded_sessions called")
logger.info(f"📂 Found {session_count} loaded sessions")
logger.error(f"❌ Error in get_loaded_sessions: {e}")
```

### Check Tool Results

```python
# In UIActionCollector
logger.info(f"🔍 UIActionCollector: Content keys: {list(content.keys())}")
logger.info(f"🔍 UIActionCollector: Result keys: {list(content['result'].keys())}")
```

### Azure Logs

```bash
az webapp log tail --name antsa-haystack-au --resource-group antsa-au
```

---

## Model Configuration

### GPT-5.2 Compatibility

GPT-5.2 requires `max_completion_tokens` (not `max_tokens`):

```python
# personas.py
@dataclass
class PersonaConfig:
    model: str = "gpt-5.2"
    max_completion_tokens: int = 32768  # NOT max_tokens!

# haystack_pipeline.py
pipeline.add_component("generator", OpenAIChatGenerator(
    model=persona_config.model,
    generation_kwargs={
        "temperature": persona_config.temperature,
        "max_completion_tokens": persona_config.max_completion_tokens  # Correct!
    }
))
```

### GPT-4o-mini for Lightweight Tasks

Some tasks use `gpt-4o-mini` which still supports `max_tokens`:
```python
response = await openai_client.chat.completions.create(
    model="gpt-4o-mini",
    messages=messages,
    stream=True,
    max_tokens=1000  # OK for gpt-4o-mini
)
```

---

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "I encountered an error" | Model parameter mismatch | Use `max_completion_tokens` for gpt-5.2 |
| UI action not extracted | Wrong nesting level | Check `content["result"]["ui_action"]` |
| Tool not called | Not in persona tools | Add to `get_tools_for_persona()` |
| Auth errors | Token not propagated | Check `_ensure_tools_context()` |
| State not found | Redis TTL expired | State expires after 24h |

---


# Haystack & Transcribe System Architecture Guide

This document provides comprehensive context for working on the ANTSA AI Assistant, Haystack service, and Live Transcribe features.

## System Overview

The AI Assistant ecosystem consists of three main projects:

| Project | Tech Stack | Purpose |
|---------|------------|---------|
| `web` | React/TypeScript | Frontend app with AI sidebar and Live Transcribe page |
| `api` | NestJS/TypeScript | Backend API that proxies to Haystack |
| `haystack-service` | Python/FastAPI | AI service with OpenAI integration and tool execution |

---

## Architecture Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              WEB (React)                                 │
│  ┌─────────────────┐    ┌──────────────────┐    ┌───────────────────┐   │
│  │ AIAssistantSidebar│◄──│ ai-ui-integration │◄──│ LiveTranscribePage│   │
│  │   (WebSocket)    │    │    service        │    │  (sessions/docs)  │   │
│  └────────┬─────────┘    └──────────────────┘    └───────────────────┘   │
└───────────┼──────────────────────────────────────────────────────────────┘
            │ WebSocket (streaming)
            ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                              API (NestJS)                                  │
│  ┌─────────────────┐    ┌──────────────────┐                              │
│  │ socket.gateway  │───►│ haystack.service │  (proxies WS to Haystack)   │
│  └─────────────────┘    └────────┬─────────┘                              │
└──────────────────────────────────┼────────────────────────────────────────┘
                                   │ WebSocket
                                   ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                         HAYSTACK (Python/FastAPI)                          │
│  ┌─────────────┐    ┌──────────────────┐    ┌─────────────────────────┐   │
│  │   main.py   │───►│haystack_pipeline │───►│   tools.py (ToolManager)│   │
│  │ (WebSocket) │    │   (OpenAI loop)  │    │   - UI actions          │   │
│  └─────────────┘    └──────────────────┘    │   - API calls           │   │
│                                              │   - Document generation │   │
│  ┌─────────────────┐    ┌────────────────┐  └─────────────────────────┘   │
│  │ui_state_manager │    │   personas.py  │                                │
│  │(Redis-backed)   │    │ (system prompts)│                               │
│  └─────────────────┘    └────────────────┘                                │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## Key Files Reference

### Web (`/Users/alec/Projects/web`)

| File | Purpose |
|------|---------|
| `src/components/ai-assistant/AIAssistantSidebar.tsx` | AI chat UI, WebSocket message handling, UI action execution |
| `src/services/ai-ui-integration.ts` | Capability system, page validation, action routing between AI and UI |
| `src/services/haystack-service.ts` | WebSocket connection to API, session management |
| `src/pages/live-transcribe/LiveTranscribePage.tsx` | Main transcription page, document generation, session loading |
| `src/pages/clients/.../LiveTranscribeTab.tsx` | Recording UI, audio upload, transcript display |

### Haystack Service (`/Users/alec/Projects/haystack-service`)

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, WebSocket endpoint `/ws/{session_id}`, message handling |
| `haystack_pipeline.py` | Declarative pipeline with OpenAI, tool invocation, UI action collection |
| `tools.py` | ToolManager with 20+ tools for clients, sessions, documents, templates |
| `ui_state_manager.py` | Redis-backed UI state tracking (loaded sessions, documents, templates) |
| `personas.py` | AI persona configurations (web_assistant, jaimee_therapist, transcriber_agent) |
| `components/ui_actions.py` | UIActionCollector - extracts `ui_action` from tool results |

### API (`/Users/alec/Projects/api`)

| File | Purpose |
|------|---------|
| `src/libs/socket/socket.gateway.ts` | Socket.IO gateway, proxies to Haystack WebSocket |
| `src/apps/haystack/haystack.service.ts` | HTTP/WS client for Haystack service |

---

## UI State Flow

The AI needs to know what's happening in the UI. State flows like this:

```
LiveTranscribePage                 ai-ui-integration              Haystack
       │                                  │                          │
       │ sendStateUpdate({               │                          │
       │   type: 'session_loaded',       │                          │
       │   payload: {...}                │                          │
       │ })                              │                          │
       ├─────────────────────────────────►│                          │
       │                                  │ sendUIStateToAI()        │
       │                                  ├─────────────────────────►│
       │                                  │ (WebSocket: ui_state_    │
       │                                  │  update message)         │
       │                                  │                          │
       │                                  │                          │ ui_state_manager
       │                                  │                          │ stores in Redis
```

### State Update Types

| Type | Triggered By | Stored In |
|------|--------------|-----------|
| `session_loaded` | Loading a session transcript | `loadedSessions` |
| `document_generated` | Creating a new document | `generatedDocuments` |
| `template_selected` | Selecting a template | `selectedTemplate` |
| `client_selected` | Selecting a client | `currentClient` |

**Important**: `generatedDocs` in the web contains BOTH loaded sessions (`isGenerated: false`) and actual documents (`isGenerated: true`). When sending to AI, they must be separated.

---

## UI Action Flow

When AI wants to trigger UI changes (load session, generate document):

```
Haystack Tool                    WebSocket                    Web Frontend
      │                              │                              │
      │ return {                     │                              │
      │   "ui_action": {             │                              │
      │     "type": "generate_doc",  │                              │
      │     "payload": {...}         │                              │
      │   }                          │                              │
      │ }                            │                              │
      │                              │                              │
      ▼                              │                              │
UIActionCollector extracts ──────────►│                              │
                                     │ {"type": "ui_action",        │
                                     │  "action": {...}}            │
                                     ├─────────────────────────────►│
                                     │                              │
                                     │              AIAssistantSidebar
                                     │              receives & calls
                                     │              executeCapability()
                                     │                              │
                                     │                              ▼
                                     │              ai-ui-integration
                                     │              validates page &
                                     │              routes to component
                                     │                              │
                                     │                              ▼
                                     │              LiveTranscribePage
                                     │              handleAIAction()
```

### Page Capability Validation

UI actions are validated against current page. Key mappings:

| URL Pattern | Page Type | Capabilities |
|-------------|-----------|--------------|
| `/sessions` (root) | `transcribe_page` | All document/session capabilities |
| `/sessions/xxx/view` | `session_viewer` | `load_session_direct` |
| `/live-transcribe` | `transcribe_page` | All document/session capabilities |
| `/clients/xxx` | `client_details` | Client selection, session loading |

**Common Issue**: If `/sessions` is incorrectly detected as `sessions_list`, document generation actions will fail silently.

---

## Document Generation Flow

### Via Generate Button
```
User clicks Generate
        │
        ▼
LiveTranscribePage.handleGenerateDocument()
        │
        ├── getAvailableSessionIds() - collects session IDs from:
        │   - currentSessionId (active recording)
        │   - sessions array (loaded sessions)  
        │   - generatedDocs with sessionId
        │
        ├── Check hasValidSession
        │
        └── Dispatch generateDocumentFromTemplateHaystackAction()
```

### Via AI (refine_document tool)
```
User: "regen the doc to use first name only"
        │
        ▼
AI calls refine_document tool
        │
        ▼
_refine_document() returns ui_action:
{
  "type": "generate_document_from_loaded",
  "payload": {
    "templateContent": "...",
    "isRegeneration": true,
    "targetDocumentId": "...",
    "originalContent": "..."
  }
}
        │
        ▼
UIActionCollector extracts → WebSocket sends → Frontend executes
        │
        ▼
handleAIGenerateDocument() with regeneration context
```

---

## Common Issues & Debugging

### 1. AI Assistant Error Message
**Symptom**: "I apologize, but I encountered an error"

**Check**:
- Haystack logs for OpenAI errors
- Model compatibility (gpt-5.2 requires `max_completion_tokens`, not `max_tokens`)
- API key validity

### 2. UI Action Not Triggering
**Symptom**: AI says it did something but UI doesn't change

**Check**:
1. Browser console for `[AI UI Action]` logs
2. Page capability validation - is the action allowed on current page?
3. UIActionCollector logs in Haystack - is `ui_action` being extracted?
4. WebSocket messages - is `type: "ui_action"` being sent?

### 3. Session/Document Confusion
**Symptom**: AI lists sessions as documents

**Check**:
- `isGenerated` flag in generatedDocs
- `sendGeneratedDocumentsState()` - should separate sessions from documents
- `get_generated_documents` tool - should filter by `isGenerated == True`

### 4. "No session data available"
**Symptom**: Generate button shows error despite loaded sessions

**Check**:
- `getAvailableSessionIds()` - is it returning session IDs?
- `hasValidSession` memo - conditions for validity
- Active tab detection logic

---

## Haystack Tools Reference

### Session/Client Tools
| Tool | Purpose |
|------|---------|
| `search_clients` | Find clients by name |
| `get_client_sessions` | List sessions for a client |
| `load_session_direct` | Load a session into UI |
| `get_loaded_sessions` | Get currently loaded sessions |
| `get_session_content` | Get transcript content |

### Document Tools
| Tool | Purpose |
|------|---------|
| `get_templates` | List available templates |
| `set_selected_template` | Select a template in UI |
| `generate_document_auto` | Generate doc from loaded sessions |
| `get_generated_documents` | List generated documents |
| `refine_document` | Modify existing document |

### UI Action Tools
Tools that trigger UI changes return:
```python
{
    "ui_action": {
        "type": "...",           # Action type
        "target": "...",         # Target component
        "payload": {...}         # Action data
    },
    "status": "ui_action_requested",
    "user_message": "..."       # What to tell user
}
```

---

## Environment Configuration

### Haystack Service
```
OPENAI_API_KEY=sk-...
NESTJS_API_URL=http://localhost:8080  # API service URL (default port 8080)
REDIS_URL=redis://localhost:6379
HAYSTACK_WEBHOOK_SECRET=...           # Shared secret with the API for the
                                      # doc-gen progress callback (see below)
```

### Doc-gen progress callback auth (2026-05-23)

`emit_progress` in `main.py` POSTs to `/api/v1/ai/websocket/document-progress`
on the API. That endpoint is authenticated as a Haystack→API webhook using a
shared secret in `HAYSTACK_WEBHOOK_SECRET`, presented as the `X-Haystack-Secret`
header. **The matching env on the API app service must hold the same value**
or every progress callback 401s and the scribe will spin forever in the SPA.

Set on all four AU app services (api+haystack × staging+production); rotate
together. Do NOT roll out a value change to only one side. Matching API guard:
`api/src/commons/guards/haystack-webhook.guard.ts`. Same pattern as the
existing `JibriWebhookGuard`.

User-identity auth (forwarding the practitioner's JWT) was removed from this
route — it was wrong for a service-to-service callback. See the
**2026-05-23 scribe outage retro** in the root `CLAUDE.md` for the full story.

### Key Defaults
- API runs on port **8080** (not 3000)
- Haystack runs on port **8000**
- Models: `gpt-5.2` for main, `gpt-4o-mini` for streaming/lightweight

---

## Deployment

### GitHub Workflows
- **Web**: `Deploy React Web App to Azure (Multi-Country)` - deploys to AU, UK, US
- **Haystack**: `Deploy Haystack to Azure AU` - single region
- **API**: Separate workflow

### Git Flow
1. Changes go to `develop` branch
2. Create PR from `develop` → `master`
3. Merge triggers deployment workflow
4. Use `gh pr merge --admin` to bypass checks if needed

### Checking Deployments
```bash
# Web
cd /Users/alec/Projects/web && gh run list --limit 3

# Haystack  
cd /Users/alec/Projects/haystack-service && gh run list --limit 3
```

---

## Australian Spelling

The codebase uses Australian English:
- colour (not color)
- behaviour (not behavior)
- analyse (not analyze)
- organisation (not organization)

---

## Quick Commands

### Check logs in Azure
```bash
az webapp log tail --name antsa-haystack-au --resource-group antsa-au
```

### Test WebSocket locally
The haystack service WebSocket is at: `ws://localhost:8000/ws/{session_id}`

### Check UI state in Redis
```python
# In Haystack service
from ui_state_manager import ui_state_manager
state = ui_state_manager.get_state_sync(session_id)
```
