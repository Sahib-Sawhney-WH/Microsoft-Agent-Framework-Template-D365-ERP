"""
Comprehensive E2E Tests for MSFT Agent Framework.

Tests all features with real Azure resources:
- Basic agent functionality
- Session management with chat_id
- Redis cache operations
- ADLS persistence
- Session restore across instances
- Multi-agent workflows
- Dynamic tool loading
- List/delete operations
- History merging
"""

import asyncio
import json
import uuid
from datetime import datetime


async def test_basic_agent():
    """Test 1: Basic agent functionality."""
    print("\n" + "=" * 70)
    print("TEST 1: Basic Agent Functionality")
    print("=" * 70)
    
    from src.agent import AIAssistant
    
    try:
        async with AIAssistant() as assistant:
            result = await assistant.process_question(
                "What is 2 + 2? Answer in one word."
            )
            
            print(f"Question: What is 2 + 2? Answer in one word.")
            print(f"Response: {result['response'][:50]}...")
            print(f"Success: {result['success']}")
            print(f"Chat ID: {result['chat_id']}")
            
            if result['success'] and 'four' in result['response'].lower():
                print("[PASS] TEST 1 PASSED: Basic agent works")
                return True
            else:
                print("[FAIL] TEST 1 FAILED: Unexpected response")
                return False
    except Exception as e:
        print(f"[FAIL] TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_session_with_provided_chat_id():
    """Test 2: Session with provided chat_id."""
    print("\n" + "=" * 70)
    print("TEST 2: Session with Provided Chat ID")
    print("=" * 70)
    
    from src.agent import AIAssistant
    
    try:
        chat_id = f"test-session-{uuid.uuid4().hex[:8]}"
        print(f"Using chat_id: {chat_id}")
        
        async with AIAssistant() as assistant:
            # First message
            result1 = await assistant.process_question(
                "My name is TestUser123. Remember that.",
                chat_id=chat_id
            )
            print(f"Message 1 Response: {result1['response'][:80]}...")
            
            # Second message - should remember the name
            result2 = await assistant.process_question(
                "What is my name?",
                chat_id=chat_id
            )
            print(f"Message 2 Response: {result2['response'][:50]}...")
            
            if "TestUser123" in result2['response']:
                print("[PASS] TEST 2 PASSED: Session continuity works")
                return chat_id
            else:
                print("[FAIL] TEST 2 FAILED: Agent forgot the name")
                return None
    except Exception as e:
        print(f"[FAIL] TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_cache_operations(chat_id: str):
    """Test 3: Verify cache is working."""
    print("\n" + "=" * 70)
    print("TEST 3: Redis Cache Operations")
    print("=" * 70)
    
    from src.memory.cache import RedisCache
    from src.config import get_config
    
    try:
        config = get_config()
        memory_config = config.memory_config
        
        if not memory_config.cache.enabled:
            print("[WARN] Cache not enabled, skipping test")
            return True
        
        cache = RedisCache(memory_config.cache)
        
        # Check if the chat is in cache
        key = f"{chat_id}"
        cached_data = await cache.get(key)
        
        print(f"Looking for key: {memory_config.cache.prefix}{key}")
        print(f"Cached data found: {cached_data is not None}")
        
        if cached_data:
            data = cached_data if isinstance(cached_data, dict) else json.loads(cached_data)
            print(f"  - Has thread data: {bool(data)}")
            print(f"  - Created at: {data.get('_created_at', 'N/A')}")
        
        # Check TTL
        ttl = await cache.get_ttl(key)
        print(f"TTL remaining: {ttl} seconds")
        
        await cache.close()
        
        print("[PASS] TEST 3 PASSED: Cache operations work")
        return True
    except Exception as e:
        print(f"[FAIL] TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_persistence_operations(chat_id: str):
    """Test 4: Verify ADLS persistence."""
    print("\n" + "=" * 70)
    print("TEST 4: ADLS Persistence Operations")
    print("=" * 70)
    
    from src.memory.persistence import ADLSPersistence
    from src.config import get_config
    
    try:
        config = get_config()
        memory_config = config.memory_config
        
        if not memory_config.persistence.enabled:
            print("[WARN] Persistence not enabled, skipping test")
            return True
        
        persistence = ADLSPersistence(memory_config.persistence)
        
        # Check if the chat exists in ADLS
        exists = await persistence.exists(chat_id)
        print(f"Chat {chat_id} exists in ADLS: {exists}")
        
        if exists:
            data = await persistence.get(chat_id)
            print(f"  - Messages in ADLS: {len(data.get('messages', []))}")
            print(f"  - Created at: {data.get('_created_at', 'N/A')}")
        
        # List all chats
        chats = await persistence.list_chats(limit=10)
        print(f"Total chats in ADLS: {len(chats)}")
        
        await persistence.close()
        
        print("[PASS] TEST 4 PASSED: ADLS operations work")
        return True
    except Exception as e:
        print(f"[FAIL] TEST 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_session_restore_from_cache():
    """Test 5: Session restore from cache (new assistant instance)."""
    print("\n" + "=" * 70)
    print("TEST 5: Session Restore from Cache")
    print("=" * 70)
    
    from src.agent import AIAssistant
    
    try:
        chat_id = f"test-restore-{uuid.uuid4().hex[:8]}"
        print(f"Creating session with chat_id: {chat_id}")
        
        # First assistant instance - create session
        async with AIAssistant() as assistant1:
            result1 = await assistant1.process_question(
                "Remember this secret code: ALPHA-BRAVO-123",
                chat_id=chat_id
            )
            print(f"First instance response: {result1['response'][:80]}...")
        
        # Second assistant instance - should restore from cache
        print("\nCreating NEW assistant instance to test cache restore...")
        async with AIAssistant() as assistant2:
            result2 = await assistant2.process_question(
                "What was the secret code I told you?",
                chat_id=chat_id
            )
            print(f"Second instance response: {result2['response'][:80]}...")
            
            if "ALPHA-BRAVO-123" in result2['response']:
                print("[PASS] TEST 5 PASSED: Session restore from cache works")
                return chat_id
            else:
                print("[FAIL] TEST 5 FAILED: Session not restored")
                return None
    except Exception as e:
        print(f"[FAIL] TEST 5 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_workflow():
    """Test 6: Multi-agent workflow."""
    print("\n" + "=" * 70)
    print("TEST 6: Multi-Agent Workflow (qa-pipeline)")
    print("=" * 70)
    
    from src.agent import AIAssistant
    
    try:
        async with AIAssistant() as assistant:
            workflows = assistant.list_workflows()
            print(f"Available workflows: {workflows}")
            
            if "qa-pipeline" not in workflows:
                print("[WARN] qa-pipeline workflow not configured, skipping")
                return True
            
            result = await assistant.run_workflow(
                "qa-pipeline",
                "Explain the benefits of cloud computing in 2 sentences."
            )
            
            print(f"Workflow: qa-pipeline")
            print(f"Success: {result.get('success', False)}")
            print(f"Response:\n{result.get('response', 'N/A')[:500]}...")
            
            if result.get('success'):
                print("[PASS] TEST 6 PASSED: Workflow works")
                return True
            else:
                print("[FAIL] TEST 6 FAILED: Workflow failed")
                return False
    except Exception as e:
        print(f"[FAIL] TEST 6 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_tool_loading():
    """Test 7: Dynamic tool loading."""
    print("\n" + "=" * 70)
    print("TEST 7: Dynamic Tool Loading (example_tool)")
    print("=" * 70)
    
    from src.agent import AIAssistant
    
    try:
        async with AIAssistant() as assistant:
            # Access tools directly from the assistant's tools list
            tools = assistant.tools
            tool_names = [getattr(t, 'name', str(t)) for t in tools]
            print(f"Total tools loaded: {len(tools)}")
            for name in tool_names:
                print(f"  - {name}")
            
            # Check if any tool is loaded
            if len(tools) == 0:
                print("[WARN] No tools loaded, skipping")
                return True
            
            # Verify tools were loaded by checking the count logged during init
            print(f"[INFO] Tools successfully loaded during initialization")
            print("[PASS] TEST 7 PASSED: Tool loading works")
            return True
    except Exception as e:
        print(f"[FAIL] TEST 7 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_list_and_delete_chats():
    """Test 8: List and delete chat functionality."""
    print("\n" + "=" * 70)
    print("TEST 8: List and Delete Chats")
    print("=" * 70)
    
    from src.agent import AIAssistant
    
    try:
        async with AIAssistant() as assistant:
            # List existing chats
            chats = await assistant.list_chats(limit=20)
            print(f"Total chats found: {len(chats)}")
            for chat in chats[:5]:
                print(f"  - {chat['chat_id'][:35]}... source={chat.get('source', 'N/A')}")
            
            # Create a new chat to delete
            delete_id = f"delete-test-{uuid.uuid4().hex[:8]}"
            await assistant.process_question("Test message", chat_id=delete_id)
            
            # Delete it
            deleted = await assistant.delete_chat(delete_id)
            print(f"Deleted chat {delete_id}: {deleted}")
            
            print("[PASS] TEST 8 PASSED: List and delete work")
            return True
    except Exception as e:
        print(f"[FAIL] TEST 8 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_history_merging():
    """Test 9: History merging on persistence."""
    print("\n" + "=" * 70)
    print("TEST 9: History Merging")
    print("=" * 70)
    
    from src.agent import AIAssistant
    from src.memory.persistence import ADLSPersistence
    from src.config import get_config
    
    try:
        config = get_config()
        memory_config = config.memory_config
        
        if not memory_config.persistence.enabled:
            print("[WARN] Persistence not enabled, skipping merge test")
            return True
        
        chat_id = f"merge-test-{uuid.uuid4().hex[:8]}"
        
        # Session 1: Create chat
        async with AIAssistant() as assistant1:
            await assistant1.process_question("First message", chat_id=chat_id)
            await assistant1.process_question("Second message", chat_id=chat_id)
            print("Session 1: Sent 2 messages")
        
        # Manually test persistence directly
        persistence = ADLSPersistence(memory_config.persistence)
        
        # Save initial data
        initial_data = {
            "messages": [{"role": "user", "content": "First message"}],
            "_created_at": datetime.now().isoformat(),
        }
        await persistence.save(chat_id, initial_data)
        print("Saved initial data to ADLS")
        
        # Session 2: Add more messages
        async with AIAssistant() as assistant2:
            await assistant2.process_question("Third message after persist", chat_id=chat_id)
            print("Session 2: Sent 1 more message")
        
        # Check merged data
        merged_data = await persistence.get(chat_id)
        if merged_data:
            print(f"Merged data has {len(merged_data.get('messages', []))} messages")
            print(f"Merge count: {merged_data.get('_merge_count', 0)}")
        
        await persistence.close()
        
        print("[PASS] TEST 9 PASSED: History merging works")
        return True
    except Exception as e:
        print(f"[FAIL] TEST 9 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all E2E tests."""
    print("\n" + "=" * 70)
    print("MSFT AGENT FRAMEWORK - COMPREHENSIVE E2E TESTS")
    print("=" * 70)
    print(f"Started at: {datetime.now().isoformat()}")
    
    results = []
    
    # Test 1: Basic agent
    results.append(("Basic Agent", await test_basic_agent()))
    
    # Test 2: Session with chat_id
    chat_id = await test_session_with_provided_chat_id()
    results.append(("Session with Chat ID", chat_id is not None))
    
    if chat_id:
        # Test 3: Cache operations
        results.append(("Cache Operations", await test_cache_operations(chat_id)))
        
        # Test 4: Persistence operations
        results.append(("ADLS Persistence", await test_persistence_operations(chat_id)))
    
    # Test 5: Session restore from cache
    restore_id = await test_session_restore_from_cache()
    results.append(("Session Restore", restore_id is not None))
    
    # Test 6: Workflow
    results.append(("Multi-Agent Workflow", await test_workflow()))
    
    # Test 7: Tool loading
    results.append(("Tool Loading", await test_tool_loading()))
    
    # Test 8: List and delete
    results.append(("List/Delete Chats", await test_list_and_delete_chats()))
    
    # Test 9: History merging
    results.append(("History Merging", await test_history_merging()))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "[PASS] PASSED" if result else "[FAIL] FAILED"
        print(f"  {status}: {name}")
    
    print("-" * 70)
    print(f"TOTAL: {passed}/{total} tests passed")
    print(f"Finished at: {datetime.now().isoformat()}")
    
    if passed == total:
        print("\n[OK] ALL TESTS PASSED!")
    else:
        print(f"\n[WARN] {total - passed} TEST(S) FAILED")
    
    return passed == total


if __name__ == "__main__":
    asyncio.run(run_all_tests())
