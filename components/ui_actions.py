"""Custom Haystack components for UI action collection and message management"""
import json
import logging
from typing import Any, Dict, List
from haystack import component
from haystack.dataclasses import ChatMessage, ChatRole
from haystack.core.component.types import Variadic

logger = logging.getLogger(__name__)


@component
class UIActionCollector:
    """
    Custom Haystack component to extract UI actions from tool results.
    
    UI actions are special metadata in tool responses that trigger frontend
    actions like loading sessions, selecting templates, or generating documents.
    """
    
    @component.output_types(messages=List[ChatMessage], ui_actions=List[Dict[str, Any]])
    def run(self, messages: List[ChatMessage]) -> Dict[str, Any]:
        """
        Extract UI actions from tool messages.
        
        Args:
            messages: List of ChatMessage objects, typically from ToolInvoker
            
        Returns:
            Dictionary with:
                - messages: Pass-through of input messages
                - ui_actions: List of extracted UI action dictionaries
        """
        ui_actions = []
        
        logger.info(f"🔍 UIActionCollector: Processing {len(messages)} total messages")
        tool_message_count = 0
        
        for msg in messages:
            logger.debug(f"🔍 UIActionCollector: Message role={msg.role}, type={type(msg)}")
            
            # Only process tool messages
            if msg.role != ChatRole.TOOL:
                continue
            
            tool_message_count += 1
            logger.info(f"🔍 UIActionCollector: Processing tool message #{tool_message_count}")
                
            try:
                # Get content from the message - Haystack tool messages use tool_call_result
                raw_content = None
                if hasattr(msg, 'tool_call_result') and msg.tool_call_result:
                    raw_content = msg.tool_call_result.result
                    logger.info(f"🔍 UIActionCollector: Got result from tool_call_result.result")
                elif hasattr(msg, 'text') and msg.text:
                    raw_content = msg.text
                    logger.info(f"🔍 UIActionCollector: Got result from text property")
                
                if not raw_content:
                    logger.warning(f"⚠️ UIActionCollector: Tool message has no content in tool_call_result or text")
                    continue
                
                # Log raw content preview
                raw_content_preview = str(raw_content)[:300]
                logger.info(f"🔍 UIActionCollector: Raw content preview: {raw_content_preview}...")
                
                # Parse the tool result content
                content = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
                
                logger.info(f"🔍 UIActionCollector: Parsed content type: {type(content)}")
                if isinstance(content, dict):
                    logger.info(f"🔍 UIActionCollector: Content keys: {list(content.keys())}")
                    logger.info(f"🔍 UIActionCollector: Content structure: success={content.get('success')}, has_result={bool(content.get('result'))}")
                    if content.get("result") and isinstance(content["result"], dict):
                        logger.info(f"🔍 UIActionCollector: Result keys: {list(content['result'].keys())}")
                
                if not isinstance(content, dict):
                    logger.warning(f"⚠️ UIActionCollector: Content is not a dict, skipping")
                    continue
                
                # Check for ui_action directly in content
                ui_action_data = content.get("ui_action")
                logger.info(f"🔍 UIActionCollector: Direct ui_action check: {ui_action_data is not None}")
                
                # Also check for ui_action nested in result (from tool_manager wrapper)
                if not ui_action_data and content.get("result") and isinstance(content["result"], dict):
                    ui_action_data = content["result"].get("ui_action")
                    logger.info(f"🔍 UIActionCollector: Nested ui_action check: {ui_action_data is not None}")
                
                if ui_action_data:
                    # Handle both single UI action and array of UI actions
                    if isinstance(ui_action_data, list):
                        ui_actions.extend(ui_action_data)
                        logger.info(f"✅ Extracted {len(ui_action_data)} UI actions from tool message")
                    else:
                        ui_actions.append(ui_action_data)
                        logger.info(f"✅ Extracted UI action: {ui_action_data.get('type', 'unknown')}")
                else:
                    logger.warning(f"⚠️ UIActionCollector: No ui_action found in tool message")
                        
            except (json.JSONDecodeError, AttributeError, TypeError) as e:
                logger.warning(f"⚠️ UIActionCollector: Exception parsing tool message: {e}")
                continue
        
        if ui_actions:
            logger.info(f"✅ Collected {len(ui_actions)} UI actions total")
        else:
            logger.info(f"ℹ️ No UI actions collected from {len(messages)} tool messages")
        
        return {"messages": messages, "ui_actions": ui_actions}


@component
class MessageCollector:
    """
    Helper component to accumulate messages across pipeline iterations.
    
    This is used in the agent loop to maintain conversation history as
    the pipeline iteratively calls tools and generates responses.
    """
    
    def __init__(self):
        self._messages: List[ChatMessage] = []

    @component.output_types(messages=List[ChatMessage])
    def run(self, messages: Variadic[List[ChatMessage]]) -> Dict[str, Any]:
        """
        Accumulate messages from multiple sources.
        
        Args:
            messages: Variable number of message lists to accumulate
            
        Returns:
            Dictionary with accumulated messages
        """
        # Flatten all incoming message lists and add to our collection
        for msg_list in messages:
            if isinstance(msg_list, list):
                self._messages.extend(msg_list)
        
        return {"messages": self._messages}

    def clear(self):
        """Clear accumulated messages (useful between conversations)"""
        self._messages = []

