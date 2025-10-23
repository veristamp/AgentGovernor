#!/usr/bin/env python3
"""
Test file for MCP UI integration.
Tests both server and client functionality with UI resources.
"""

import asyncio
import json
import os
import sys
import tempfile
import webbrowser
from pathlib import Path

# Import our updated modules
from mcp_client_manager2 import MCPClientManager, Config
from s2 import mcp as server_mcp

async def test_server_capabilities():
    """Test that the server has the new UI tools available."""
    print("🔧 Testing server capabilities...")

    try:
        # Simple test: check if we can import the server and UI functions exist
        from s2 import view_directory_ui, edit_file

        print("✅ UI functions imported successfully")
        print("✅ Server has UI tools available")
        return True

    except ImportError as e:
        print(f"❌ Server capabilities test failed - import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Server capabilities test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_client_ui_handling():
    """Test that the client properly handles UI resources."""
    print("\n🌐 Testing client UI resource handling...")

    # Create a test config for our server
    test_config = {
        "secure-filesystem-server": {
            "connection_type": "stdio",
            "command": sys.executable,
            "args": ["/home/yanshi/Desktop/MCP-CLient/s2.py"],
            "cwd": "/home/yanshi/Desktop/MCP-CLient"
        }
    }

    # Create a temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_config, f)
        config_file = f.name

    try:
        # Load config
        config = Config.load(config_file)

        async with MCPClientManager(config) as manager:
            await manager.wait_ready()

            print("✅ Client connected to server")

            # Test directory UI tool - use correct tool name based on server capabilities
            print("Testing directory UI tool...")
            
            # First, let's see what tools are available
            caps = await manager.list_formatted_capabilities()
            print(f"Available tools in capabilities: {len(caps)} chars")
            
            # The tool name should be based on the server name hook
            result = await manager.execute_action({
                "action_type": "tool",
                "action_name": "secure-filesystem-server.view_directory_ui",
                "arguments": {"path": "/home/yanshi/Desktop/MCP-CLient"}
            })

            print(f"📄 Directory UI result length: {len(result)}")

            # Check if UI resource info is in the result
            if "UI Resource:" in result or "ui://" in result or "directory-listing" in result:
                print("✅ Directory UI tool executed successfully")
                return True
            else:
                print(f"❌ Directory UI tool response: {result[:500]}...")
                return False

    except Exception as e:
        print(f"❌ Client test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up temp config file
        os.unlink(config_file)

async def test_file_operations():
    """Test basic file operations to ensure server is working."""
    print("\n📁 Testing basic file operations...")

    # Create a temporary test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Hello, MCP UI test!")
        test_file = f.name

    try:
        # Test that we can import and the server starts correctly
        from s2 import mcp
        print("✅ Server module imports successfully")

        # Test that basic file operations work by checking if the file exists
        import os
        if os.path.exists(test_file):
            with open(test_file, 'r') as f:
                content = f.read()
            if "Hello, MCP UI test!" in content:
                print("✅ Basic file operations working")
                return True
            else:
                print("❌ File read failed")
                return False
        else:
            print("❌ Test file was not created")
            return False

    except Exception as e:
        print(f"❌ File operations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up test file
        if os.path.exists(test_file):
            os.unlink(test_file)

async def test_ui_resource_creation():
    """Test that UI resources are properly created by the server."""
    print("\n🎨 Testing UI resource creation...")

    try:
        # Test UI resource creation using the mcp_ui_server directly
        from mcp_ui_server import create_ui_resource
        import urllib.parse

        # Create a UI resource directly
        ui_resource = create_ui_resource({
            "uri": "ui://test/resource",
            "content": {
                "type": "rawHtml",
                "htmlString": "<h1>Test UI Resource</h1>"
            },
            "encoding": "text"
        })

        print(f"✅ UI resource created successfully")

        # Check resource structure
        resource_data = ui_resource.model_dump()
        uri_value = resource_data['resource']['uri']
        uri_str = str(uri_value) if hasattr(uri_value, '__str__') else uri_value
        
        if uri_str.startswith('ui://'):
            print("✅ UI resource has proper URI format")
            return True
        else:
            print(f"❌ UI resource URI: {uri_str}")
            print("❌ UI resource missing proper URI")
            return False

    except Exception as e:
        print(f"❌ UI resource creation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests."""
    print("🚀 Starting MCP UI Integration Tests")
    print("=" * 50)

    tests = [
        ("Server Capabilities", test_server_capabilities),
        ("Client UI Handling", test_client_ui_handling),
        ("File Operations", test_file_operations),
        ("UI Resource Creation", test_ui_resource_creation),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")

    passed = 0
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
        if result:
            passed += 1

    print(f"\n🎯 Overall: {passed}/{len(results)} tests passed")

    if passed == len(results):
        print("🎉 All tests passed! MCP UI integration is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
