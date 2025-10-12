#!/usr/bin/env python3
"""
Final MCP Inspector Integration Test
Tests the complete flow from server connection to UI tool execution
"""

import asyncio
import json
import os
from mcp_client_manager2 import MCPClientManager, Config

async def test_full_integration():
    """Test the complete MCP UI integration."""
    print("🔬 Testing Complete MCP UI Integration")
    print("=" * 50)

    # Test 1: Server connection
    print("1️⃣  Testing server connection...")
    config_data = {
        'FileSystem': {
            'connection_type': 'stdio',
            'command': 'python3',
            'args': ['-u', 's2.py'],
            'cwd': '/home/yanshi/Desktop/MCP-CLient',
            'timeout': 5.0,
            'disabled': False
        }
    }

    config = Config(mcp_servers=config_data)

    async with MCPClientManager(config) as manager:
        await manager.wait_ready()
        print("✅ Server connection successful")

        # Test 2: Get capabilities
        print("2️⃣  Testing capabilities...")
        caps = await manager.list_formatted_capabilities()
        print(f"✅ Got capabilities: {len(caps)} chars")

        # Check for UI tools
        if 'view_directory_ui' in caps and 'edit_file' in caps:
            print("✅ UI tools found in capabilities")
        else:
            print("❌ UI tools not found in capabilities")
            return False

        # Test 3: Test UI directory tool
        print("3️⃣  Testing UI directory tool...")
        result = await manager.execute_action({
            'action_type': 'tool',
            'action_name': 'FileSystem.view_directory_ui',
            'arguments': {'path': '.'}  # Use current directory instead
        })

        print(f"📄 UI tool result: {result[:200]}...")

        # Check for UI resource in response
        if 'UI Resource:' in result or 'ui://' in result:
            print("✅ UI resource detected in response")
        else:
            print("❌ No UI resource found in response")
            return False

        # Test 4: Test enhanced edit tool
        print("4️⃣  Testing enhanced edit tool...")
        test_file = "/tmp/ui_test.txt"
        with open(test_file, 'w') as f:
            f.write("Test content\nLine to edit\nMore content")

        result = await manager.execute_action({
            'action_type': 'tool',
            'action_name': 'FileSystem.edit_file',
            'arguments': {
                'path': test_file,
                'edits': [{'oldText': 'Line to edit', 'newText': 'EDITED LINE'}],
                'dry_run': True
            }
        })

        print(f"🔧 Edit tool result: {result[:200]}...")

        # Check for UI preview in response
        if 'UI Preview:' in result or 'ui://' in result:
            print("✅ UI preview detected in edit response")
        else:
            print("❌ No UI preview found in edit response")
            return False

        print("\n" + "=" * 50)
        print("🎉 ALL INTEGRATION TESTS PASSED!")
        print("=" * 50)
        print("✅ Server connection working")
        print("✅ UI tools available")
        print("✅ UI resources generated correctly")
        print("✅ Enhanced tools with UI previews working")
        print("✅ Complete MCP UI integration functional")

        return True

if __name__ == "__main__":
    success = asyncio.run(test_full_integration())
    if success:
        print("\n🚀 MCP UI Integration is COMPLETE and READY!")
        print("🌐 Web Inspector: http://127.0.0.1:8000")
        print("📁 Test your UI tools by selecting FileSystem server!")
    else:
        print("\n❌ Integration test failed")
    exit(0 if success else 1)
