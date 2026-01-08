#!/usr/bin/env python3
"""
Integration tests for AI-UI Integration Redesign
Tests WebSocket state updates, Redis persistence, and tool capabilities
"""

import asyncio
import websockets
import json
import requests
import os
from datetime import datetime
from uuid import uuid4
import sys

# Configuration
TEST_TOKEN = os.getenv("TEST_TOKEN")
TEST_PROFILE_ID = os.getenv("TEST_PROFILE_ID", "test-profile-id")
BASE_URL = "http://localhost:8001"
WS_URL = "ws://localhost:8001"

def print_test(msg: str):
    """Print test message"""
    print(f"\n{'='*60}")
    print(f"TEST: {msg}")
    print(f"{'='*60}")

def print_success(msg: str):
    """Print success message"""
    print(f"✅ {msg}")

def print_error(msg: str):
    """Print error message"""
    print(f"❌ {msg}")

async def test_1_websocket_connection():
    """Test 1: WebSocket connection and basic messaging"""
    print_test("WebSocket Connection & Hello Message")
    
    session_id = f"test-connection-{uuid4()}"
    uri = f"{WS_URL}/ws/{session_id}"
    
    try:
        async with websockets.connect(uri) as ws:
            # Wait for connection_established message
            response = json.loads(await ws.recv())
            assert response["type"] == "connection_established", f"Expected connection_established, got {response['type']}"
            assert response["session_id"] == session_id, f"Session ID mismatch"
            print_success(f"Connected to WebSocket: {session_id}")
            
            # Test heartbeat
            await ws.send(json.dumps({"type": "heartbeat"}))
            response = json.loads(await ws.recv())
            assert response["type"] == "heartbeat_ack", "Heartbeat failed"
            print_success("Heartbeat acknowledged")
            
            return True
    except Exception as e:
        print_error(f"WebSocket connection test failed: {e}")
        return False

async def test_2_state_update_incremental():
    """Test 2: Incremental state updates with acknowledgment"""
    print_test("Incremental State Updates")
    
    session_id = f"test-state-{uuid4()}"
    uri = f"{WS_URL}/ws/{session_id}"
    
    try:
        async with websockets.connect(uri) as ws:
            # Skip connection_established
            await ws.recv()
            
            # Send incremental state update
            state_update = {
                "type": "ui_state_update",
                "changeType": "page_changed",
                "payload": {},
                "timestamp": datetime.utcnow().isoformat(),
                "page_type": "transcribe_page",
                "page_url": "/sessions?tab=transcribe",
                "sequence": 1
            }
            
            await ws.send(json.dumps(state_update))
            print_success("Sent state update")
            
            # Wait for acknowledgment
            response = json.loads(await ws.recv())
            assert response["type"] == "ui_state_ack", f"Expected ui_state_ack, got {response['type']}"
            assert response["success"] == True, "State update failed"
            print_success(f"State update acknowledged: {response}")
            
            # Verify via debug endpoint
            debug_response = requests.get(
                f"{BASE_URL}/debug/sessions/{session_id}/state",
                headers={"Authorization": f"Bearer {TEST_TOKEN}"}
            )
            
            if debug_response.status_code == 200:
                state = debug_response.json()
                assert state["ui_state"].get("page_type") == "transcribe_page", "Page type mismatch"
                print_success(f"State verified via debug endpoint: page_type={state['ui_state']['page_type']}")
                return True
            else:
                print_error(f"Debug endpoint failed: {debug_response.status_code}")
                return False
                
    except Exception as e:
        print_error(f"State update test failed: {e}")
        return False

async def test_3_page_type_detection():
    """Test 3: Page type detection for /sessions?tab=transcribe"""
    print_test("Page Type Detection")
    
    session_id = f"test-pagetype-{uuid4()}"
    uri = f"{WS_URL}/ws/{session_id}"
    
    try:
        async with websockets.connect(uri) as ws:
            await ws.recv()  # Skip connection_established
            
            # Send state update with query param URL
            state_update = {
                "type": "ui_state_update",
                "changeType": "page_changed",
                "payload": {},
                "timestamp": datetime.utcnow().isoformat(),
                "page_type": "transcribe_page",  # Frontend should detect this
                "page_url": "/sessions?tab=transcribe",
                "sequence": 1
            }
            
            await ws.send(json.dumps(state_update))
            response = json.loads(await ws.recv())
            assert response["success"] == True
            
            # Verify
            debug_response = requests.get(
                f"{BASE_URL}/debug/sessions/{session_id}/state",
                headers={"Authorization": f"Bearer {TEST_TOKEN}"}
            )
            
            state = debug_response.json()
            detected_type = state["ui_state"].get("page_type")
            
            if detected_type == "transcribe_page":
                print_success(f"✅ Page type correctly detected as 'transcribe_page' for /sessions?tab=transcribe")
                return True
            else:
                print_error(f"Page type incorrectly detected as '{detected_type}' (expected 'transcribe_page')")
                return False
                
    except Exception as e:
        print_error(f"Page type detection test failed: {e}")
        return False

async def test_4_redis_persistence():
    """Test 4: Redis persistence"""
    print_test("Redis Persistence")
    
    session_id = f"test-persist-{uuid4()}"
    uri = f"{WS_URL}/ws/{session_id}"
    
    try:
        # Create state
        async with websockets.connect(uri) as ws:
            await ws.recv()
            
            state_update = {
                "type": "ui_state_update",
                "changeType": "session_loaded",
                "payload": {"sessionId": "abc123", "clientName": "Test Client"},
                "timestamp": datetime.utcnow().isoformat(),
                "page_type": "transcribe_page",
                "page_url": "/transcribe",
                "sequence": 1
            }
            
            await ws.send(json.dumps(state_update))
            response = json.loads(await ws.recv())
            assert response["success"] == True
            print_success("State created in Redis")
        
        # Verify state persists after WebSocket disconnect
        await asyncio.sleep(1)
        
        debug_response = requests.get(
            f"{BASE_URL}/debug/sessions/{session_id}/state",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"}
        )
        
        if debug_response.status_code == 200:
            state = debug_response.json()
            if state["ui_state"].get("session_loaded"):
                print_success("State persisted in Redis after WebSocket disconnect")
                return True
            else:
                print_error("State not found after disconnect")
                return False
        else:
            print_error(f"Failed to retrieve state: {debug_response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Redis persistence test failed: {e}")
        return False

async def test_5_capabilities():
    """Test 5: Page capabilities detection"""
    print_test("Page Capabilities")
    
    session_id = f"test-caps-{uuid4()}"
    uri = f"{WS_URL}/ws/{session_id}"
    
    try:
        async with websockets.connect(uri) as ws:
            await ws.recv()
            
            state_update = {
                "type": "ui_state_update",
                "changeType": "page_changed",
                "payload": {},
                "timestamp": datetime.utcnow().isoformat(),
                "page_type": "transcribe_page",
                "page_url": "/transcribe",
                "sequence": 1
            }
            
            await ws.send(json.dumps(state_update))
            await ws.recv()
            
            # Check capabilities
            debug_response = requests.get(
                f"{BASE_URL}/debug/sessions/{session_id}/state",
                headers={"Authorization": f"Bearer {TEST_TOKEN}"}
            )
            
            state = debug_response.json()
            capabilities = state.get("available_capabilities", [])
            
            expected_caps = ["load_session_direct", "set_client_selection"]
            missing = [cap for cap in expected_caps if cap not in capabilities]
            
            if not missing:
                print_success(f"All expected capabilities present: {len(capabilities)} tools available")
                print(f"   Capabilities: {', '.join(capabilities[:5])}...")
                return True
            else:
                print_error(f"Missing capabilities: {missing}")
                return False
                
    except Exception as e:
        print_error(f"Capabilities test failed: {e}")
        return False

async def test_6_timestamp_ordering():
    """Test 6: Timestamp-based update ordering"""
    print_test("Timestamp Ordering")
    
    session_id = f"test-order-{uuid4()}"
    uri = f"{WS_URL}/ws/{session_id}"
    
    try:
        async with websockets.connect(uri) as ws:
            await ws.recv()
            
            # Send newer update first
            newer_update = {
                "type": "ui_state_update",
                "changeType": "page_changed",
                "payload": {},
                "timestamp": "2025-11-04T12:00:00Z",
                "page_type": "transcribe_page",
                "page_url": "/transcribe",
                "sequence": 2
            }
            
            await ws.send(json.dumps(newer_update))
            response1 = json.loads(await ws.recv())
            assert response1["success"] == True
            
            # Send older update (should be rejected)
            older_update = {
                "type": "ui_state_update",
                "changeType": "page_changed",
                "payload": {},
                "timestamp": "2025-11-04T11:00:00Z",
                "page_type": "sessions_list",
                "page_url": "/sessions",
                "sequence": 1
            }
            
            await ws.send(json.dumps(older_update))
            response2 = json.loads(await ws.recv())
            
            # Even if accepted, verify the state didn't change
            debug_response = requests.get(
                f"{BASE_URL}/debug/sessions/{session_id}/state",
                headers={"Authorization": f"Bearer {TEST_TOKEN}"}
            )
            
            state = debug_response.json()
            page_type = state["ui_state"].get("page_type")
            
            if page_type == "transcribe_page":
                print_success("Timestamp ordering works: stale update rejected")
                return True
            else:
                print_error(f"Timestamp ordering failed: state changed to {page_type}")
                return False
                
    except Exception as e:
        print_error(f"Timestamp ordering test failed: {e}")
        return False

async def main():
    """Run all integration tests"""
    print("\n" + "="*60)
    print("AI-UI INTEGRATION TEST SUITE")
    print("="*60)
    
    if not TEST_TOKEN:
        print_error("TEST_TOKEN environment variable not set")
        print("Run: export TEST_TOKEN=<your-token>")
        sys.exit(1)
    
    # Test Redis health first
    try:
        response = requests.get(
            f"{BASE_URL}/debug/redis/health",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"}
        )
        health = response.json()
        if not health.get("redis_connected"):
            print_error("Redis is not connected!")
            sys.exit(1)
        print_success("Redis connection healthy")
    except Exception as e:
        print_error(f"Failed to check Redis health: {e}")
        sys.exit(1)
    
    # Run tests
    results = []
    
    results.append(("WebSocket Connection", await test_1_websocket_connection()))
    results.append(("Incremental State Updates", await test_2_state_update_incremental()))
    results.append(("Page Type Detection", await test_3_page_type_detection()))
    results.append(("Redis Persistence", await test_4_redis_persistence()))
    results.append(("Page Capabilities", await test_5_capabilities()))
    results.append(("Timestamp Ordering", await test_6_timestamp_ordering()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

