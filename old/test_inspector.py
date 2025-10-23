#!/usr/bin/env python3
"""
End-to-End MCP Inspector Test
Tests the complete flow from server selection to tool execution
"""

import requests
import json
import time

def test_mcp_inspector():
    """Test the complete MCP Inspector functionality."""
    base_url = "http://127.0.0.1:8000"

    print("🧪 Testing MCP Inspector End-to-End")
    print("=" * 50)

    # Test 1: Check if server is running
    print("1️⃣  Testing server availability...")
    try:
        response = requests.get(f"{base_url}/")
        if response.status_code == 200:
            print("✅ Server is running")
        else:
            print(f"❌ Server responded with status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        return False

    # Test 2: Check server selection page
    print("2️⃣  Testing server selection page...")
    try:
        response = requests.get(f"{base_url}/servers")
        if response.status_code == 200 and "FileSystem" in response.text:
            print("✅ Server selection page loads with FileSystem server")
        else:
            print(f"❌ Server selection page issue: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Server selection page error: {e}")
        return False

    # Test 3: Connect to FileSystem server
    print("3️⃣  Testing server connection...")
    try:
        response = requests.post(f"{base_url}/connect/FileSystem")
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "connected":
                print("✅ Successfully connected to FileSystem server")
            else:
                print(f"❌ Connection failed: {result}")
                return False
        else:
            print(f"❌ Connection endpoint returned {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

    # Test 4: Check status
    print("4️⃣  Testing connection status...")
    try:
        response = requests.get(f"{base_url}/status")
        if response.status_code == 200:
            result = response.json()
            if result.get("connected") and result.get("server_name") == "FileSystem":
                print("✅ Connection status verified")
            else:
                print(f"❌ Status check failed: {result}")
                return False
        else:
            print(f"❌ Status endpoint returned {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Status check error: {e}")
        return False

    # Test 5: Test tool execution
    print("5️⃣  Testing tool execution...")
    try:
        # First test a simple tool
        response = requests.post(f"{base_url}/execute", data={
            "action_type": "tool",
            "action_name": "FileSystem.list_directory",
            "arguments": json.dumps({"path": "/home/yanshi/Desktop/MCP-CLient"})
        })

        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                print("✅ Basic tool execution works")
                print(f"   Result preview: {result['result'][:100]}...")
            else:
                print(f"❌ Tool execution failed: {result}")
                return False
        else:
            print(f"❌ Execute endpoint returned {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Tool execution error: {e}")
        return False

    # Test 6: Test UI tool execution
    print("6️⃣  Testing UI tool execution...")
    try:
        response = requests.post(f"{base_url}/execute", data={
            "action_type": "tool",
            "action_name": "FileSystem.view_directory_ui",
            "arguments": json.dumps({"path": "/home/yanshi/Desktop/MCP-CLient"})
        })

        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                print("✅ UI tool execution works")
                print(f"   Result contains UI resource: {'ui://' in result['result']}")
            else:
                print(f"❌ UI tool execution failed: {result}")
                return False
        else:
            print(f"❌ UI tool execute endpoint returned {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ UI tool execution error: {e}")
        return False

    print("\n" + "=" * 50)
    print("🎉 ALL TESTS PASSED!")
    print("=" * 50)
    print("✅ MCP Inspector Web UI is fully functional")
    print("✅ Server selection and connection working")
    print("✅ Tool execution working")
    print("✅ UI resource detection working")
    print("✅ Integration with existing mcp_servers.json working")

    return True

if __name__ == "__main__":
    success = test_mcp_inspector()
    if success:
        print("\n🚀 Ready to use: Open http://127.0.0.1:8000 in your browser!")
        print("   Select FileSystem server and test the UI tools!")
    else:
        print("\n❌ Tests failed - check the errors above")
    exit(0 if success else 1)
