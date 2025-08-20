#!/usr/bin/env python3
"""
Debug WebSocket streaming for Haystack AI Service
"""
import asyncio
import websockets
import json

async def debug_websocket():
    # First create a session
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.post('http://localhost:8001/sessions', 
                               json={'persona_type': 'web_assistant', 'context': {'test': True}}) as resp:
            session_data = await resp.json()
            session_id = session_data['session_id']
            print(f"✅ Created session: {session_id}")
    
    # Connect to WebSocket
    uri = f"ws://localhost:8001/ws/{session_id}"
    print(f"🔗 Connecting to: {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket connected!")
            
            # Wait for connection confirmation
            response = await websocket.recv()
            data = json.loads(response)
            print(f"📨 Connection confirmed: {data}")
            
            # Send a test message
            test_message = {
                "type": "chat_message",
                "message": "Hello! Can you tell me about the weather?",
                "persona_type": "web_assistant",
                "context": {"page_context": "debug_test"}
            }
            
            await websocket.send(json.dumps(test_message))
            print("📤 Sent test message")
            
            # Listen for ALL responses with detailed logging
            message_count = 0
            while True:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=30)
                    message_count += 1
                    
                    try:
                        data = json.loads(response)
                        print(f"📥 Message #{message_count}: {data}")
                        
                        if data.get('type') == 'message_complete':
                            print("✅ Streaming complete!")
                            break
                            
                    except json.JSONDecodeError:
                        print(f"📥 Raw message #{message_count}: {response}")
                    
                except asyncio.TimeoutError:
                    print("⏰ Timeout waiting for response")
                    break
                    
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_websocket())