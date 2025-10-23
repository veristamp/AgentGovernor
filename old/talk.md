## The **MCP UI** acts as a bridge between your **MCP server** and **MCP client**, enabling dynamic UI components to be defined on the server and securely rendered on the client. Here's how it fits into your architecture:
### **1. Server-Side Integration**
Use the **MCP-UI Server SDK** to define UI resources (e.g., HTML, iframes, or Remote DOM components) that your server sends to the client.

**Key Function**: createUIResource (TypeScript/Node.js) or McpUiServer.create_ui_resource (Ruby).
**Purpose**: Generate UIResource objects that encapsulate UI definitions (e.g., external URLs, HTML snippets, or interactive components).
**Example (TypeScript)**:

tsimport { createUIResource } from '@mcp-ui/server';
const resource = createUIResource({
  uri: 'ui://user-form/1',
  content: {
    type: 'externalUrl',
    iframeUrl: 'https://yourapp.com',
  },
  encoding: 'text',
});

**Install**: Add @mcp-ui/server (Node.js) or mcp_ui_server (Ruby) to your server project.
**Integration**: Embed UIResource objects in your server's responses to the client (e.g., via MCP tool responses).


### **2. Client-Side Integration**
Use the **MCP-UI Client SDK** to render UI resources received from the server.

**Key Component**: <UIResourceRenderer /> (React) or <ui-resource-renderer> (Web Component).
**Purpose**: Dynamically render server-defined UIs, handle user interactions (e.g., button clicks), and communicate with iframes or Remote DOM components.
**Example (React)**:

tsximport { UIResourceRenderer } from '@mcp-ui/client';
function App({ mcpResource }) {
  return (
    <UIResourceRenderer
      resource={mcpResource.resource}
      onUIAction={(action) => {
        console.log('User action:', action);
      }}
    />
  );
}

**Install**: Add @mcp-ui/client to your client project.
**Security**: UIs are sandboxed (e.g., iframes with restricted permissions) to prevent security risks.


### **3. Communication Protocol**

**Embeddable UIs**: Use postMessage for communication between iframes and the parent window (e.g., sending user actions or requesting data).
**Example**: An iframe sends an intent message to the parent client:
  ```ts:disable-run
window.parent.postMessage(
{ type: 'intent', payload: { intent: 'create-task', params: { title: 'Buy groceries' } } },
'*'
);




### **4. Workflow Summary**

**Server**: Define UI resources using the server SDK.
**Client**: Render resources using the client SDK.
**Interaction**: Handle user actions via onUIAction or postMessage.


### **Supported Environments**

**Servers**: Node.js (TypeScript), Ruby.
**Clients**: React, Web Components, or frameworks like Vue/Svelte (via Web Components).
**Hosts**: Works with MCP-compatible hosts (e.g., Postman, VSCode, custom apps).


### **Next Steps**

For **TypeScript/Node.js**: Follow the server walkthrough.
For **Ruby**: Use the Ruby server examples.
For **React clients**: Check the React usage guide.
Let me know if you need help with specific integration steps!
 
 
 
read about this and tell me how do we integrate this in our mcp? right now we have a simple fastapi sever..
i have given you a sample mcp server and mcp client.

mcp_client_manager2.pys2.pyThought for 1m 51sTo integrate MCP UI into your existing MCP setup (based on the provided Python server in s2.py using FastMCP and the client manager in mcp_client_manager2.py), you'll need to add support for defining and serving UI resources on the server side, and then handle rendering on the client side. MCP UI extends the MCP protocol to allow servers to send dynamic UI components (e.g., HTML snippets, external iframes, or Remote DOM elements) as "UIResources" with URIs prefixed by ui://. These are sandboxed for security when rendered.
From the provided MCP UI description and additional research (via the repo and docs), here's how it fits: MCP UI has Python support on the server side via the mcp-ui-server package, but client-side rendering is primarily for JavaScript-based environments (React or Web Components). Your current Python client isn't designed for UI rendering (it's more for backend/scripted execution), so you'll likely need a separate UI-capable client (e.g., a web app or MCP-compatible host like Goose or LibreChat) to fully utilize it. If your "simple FastAPI server" is a separate HTTP-based MCP server (e.g., using FastMCP, which is built on FastAPI), the integration is similar—add endpoints or tools that return UI resources.
I'll break it down step-by-step, focusing on your provided code. Note that MCP UI is experimental, so test thoroughly.
1. Prerequisites

Install the Python Server SDK: Run pip install mcp-ui-server (or uv add mcp-ui-server if using uv). This provides utilities like create_ui_resource for generating UIResource objects.
MCP Protocol Compatibility: Your setup uses the official MCP Python library (mcp), which supports embedded resources (via types.EmbeddedResource or similar). UIResources can be returned as part of tool responses or resources.
No Native Python Client Rendering: The SDK doesn't provide a Python renderer for UIs (e.g., no built-in iframe handling in console apps). Use a JS-based client for rendering. If you must stick to Python, you could parse the UIResource JSON and open it in a browser (e.g., via webbrowser module), but that's limited.

2. Server-Side Integration (Modify s2.py)
Your server uses FastMCP to define tools, resources, and prompts. MCP UI integrates by having tools or resources return a UIResource (a dict-like object) instead of (or in addition to) plain text. FastMCP/FastAPI handles this because MCP responses can include embedded content (e.g., types.ToolResponse with content as a list mixing text and embedded resources).
Key steps:

Import the SDK.
Create UIResources using create_ui_resource (supports types like rawHtml, externalUrl, or Remote DOM).
In a tool or resource, return the UIResource directly (FastMCP will serialize it to JSON for the protocol) or embed it in a response (e.g., via types.EmbeddedResource if needed for complex responses).
Use ui:// URIs for naming to signal it's a UI resource.

Example modifications to s2.py:
python# Add these imports at the top
from mcp_ui_server import create_ui_resource
from mcp import types  # Already imported, but ensure for EmbeddedResource

# Add a new tool that returns a simple UI (e.g., an iframe or HTML form)
@mcp.tool()
@handle_errors
async def render_user_form(ctx: Context) -> types.ToolResponse:
    """Render a dynamic user form UI as an MCP UI resource."""
    # Create a UIResource (example: external iframe)
    ui_resource = create_ui_resource({
        "uri": "ui://user-form/1",
        "content": {
            "type": "externalUrl",
            "iframeUrl": "https://yourapp.com/form",  # Or your hosted form URL
        },
        "encoding": "text",
    })
    
    # Return as embedded content in the tool response
    # This mixes text instructions with the UI
    return types.ToolResponse(
        content=[
            types.TextContent(text="Here's a form for user input:"),
            types.EmbeddedContent(resource=ui_resource)  # Embed the UI
        ]
    )

# Alternatively, add a UI as a resource (e.g., for read-only access)
@mcp.resource("ui://greeting/{name}")
def get_greeting_ui(name: str) -> str:
    """Expose a simple HTML greeting as a UI resource."""
    ui_resource = create_ui_resource({
        "uri": f"ui://greeting/{name}",
        "content": {
            "type": "rawHtml",
            "htmlString": f"<h1>Hello, {name}!</h1><button onclick=\"window.parent.postMessage({{type: 'intent', payload: {{intent: 'greet'}}}}, '*')\">Greet</button>",
        },
        "encoding": "text",
    })
    # Resources typically return str/bytes; serialize to JSON
    return json.dumps(ui_resource)

# For more complex UIs, handle postMessage events (as described in the MCP UI docs)
# e.g., The button above sends an 'intent' message to the client for handling

How This Works with FastMCP/FastAPI:

FastMCP uses FastAPI under the hood for HTTP transports (e.g., if you switch to mcp.run(transport="http") or SSE). The above will expose the tool/resource via the MCP endpoint (e.g., /mcp/tools/render_user_form).
If returning a types.ToolResponse or JSON dict, MCP serializes it automatically.
For security, validate inputs as you do with validate_path—UIResources are sandboxed on the client, but avoid injecting untrusted content.
Test: Run your server, then use a client to call the tool (e.g., render_user_form) and inspect the response for the embedded UIResource.


Communication: UIs can send events back to the client via postMessage (e.g., button clicks trigger intents or tool calls). Your server doesn't handle this directly—the client does.

3. Client-Side Integration (Modify mcp_client_manager2.py or Use a New Client)
Your current client uses ClientSessionGroup to connect and execute actions, but it's Python-based and focused on text output (e.g., execute_action returns str). To render UIs:

Parse the response for embedded UIResources (look for ui:// URIs or types.EmbeddedContent).
Since Python isn't great for rendering iframes/HTML, this client can only log or save the UI content. For actual rendering, switch to/use a JS-based MCP client.

Example modifications to handle UI in mcp_client_manager2.py (limited to extraction/logging):
python# In execute_action, enhance to handle embedded content
async def execute_action(self, action: Dict[str, Any]) -> str:
    # ... (existing code)
    try:
        if typ == "tool":
            result = await self.group.call_tool(name, args=args)
            outputs = []
            for content in result.content:
                if hasattr(content, 'text'):
                    outputs.append(content.text)
                elif hasattr(content, 'resource') and 'ui://' in content.resource.get('uri', ''):
                    # Handle UIResource (e.g., log or save to file)
                    ui_data = content.resource
                    outputs.append(f"UI Resource: {ui_data['uri']} - Content: {ui_data['content']}")
                    # Optional: Open in browser for basic rendering
                    import webbrowser
                    if ui_data['content']['type'] == 'rawHtml':
                        with open('temp_ui.html', 'w') as f:
                            f.write(ui_data['content']['htmlString'])
                        webbrowser.open('temp_ui.html')
            return "\n".join(outputs) if outputs else "No output."
        # ... (handle resources/prompts similarly, parsing for embedded UI)
    # ... (existing exceptions)

For Full Rendering, Use a JS-Based Client:

Install @mcp-ui/client via npm.
Build a React/Web app that connects to your MCP server (using MCP JS SDK for sessions, similar to your Python ClientSessionGroup).
Render with <UIResourceRenderer resource={uiResource} onUIAction={(action) => { /* Handle intents/tool calls */ }} />.
Example (React):
tsximport { ClientSessionGroup } from 'mcp';  // MCP JS SDK
import { UIResourceRenderer } from '@mcp-ui/client';

// Connect similar to your Python client (e.g., via StreamableHttpParameters)
const group = new ClientSessionGroup();
// ... connect to your server

// When reading a resource or tool result with UI
const result = await group.callTool('render_user_form');
const uiResource = result.content.find(c => c.resource && c.resource.uri.startsWith('ui://')).resource;

// Render
<UIResourceRenderer
  resource={uiResource}
  onUIAction={(action) => {
    console.log('UI Event:', action);  // e.g., { type: 'intent', payload: { intent: 'create-task' } }
    // Optionally, call back to MCP server (e.g., trigger another tool)
  }}
/>

Compatible Hosts: Use tools like Goose, LibreChat, or Postman (as mentioned in MCP UI docs) that support MCP and UI rendering out-of-the-box.



4. Workflow and Testing

Server: Start with python s2.py (stdio) or switch to HTTP for easier testing.
Client: Call the new tool/resource (e.g., via execute_action with {"action_type": "tool", "action_name": "render_user_form"}).
Interaction: UIs send events via postMessage; handle in onUIAction (e.g., map to MCP tool calls).
Security/Edge Cases: UIs are sandboxed, but validate paths/inputs. Test with ui-inspector tool from the MCP UI repo.
Limitations: If your FastAPI server is separate, add MCP UI to its endpoints similarly. For advanced Remote DOM, ensure your client supports it.

If this doesn't match your exact FastAPI setup or you need code for a specific UI example, provide more details! For full docs, check https://mcpui.dev.
7 web pages5.2sPython Server Walkthrough
This guide provides a step-by-step walkthrough for creating an MCP server with UI resources using mcp-ui-server and FastMCP.
For a complete, runnable example, see the python-server-demo.

Set up Your Python Environment
First, create a new Python project and set up your dependencies:

text# Create a new directory
mkdir my-mcp-server
cd my-mcp-server

# Initialize with uv (recommended) or pip
uv init
# or: python -m venv venv && source venv/bin/activate

2. Install Dependencies
Install the necessary packages:
textuv add mcp mcp-ui-server
1
Or with pip:
textpip install mcp mcp-ui-server
1
The mcp package provides FastMCP and core MCP functionality, while mcp-ui-server includes helpers for creating UI resources.
3. Create Your MCP Server
Create a file called server.py:
textimport argparse
from mcp.server.fastmcp import FastMCP
from mcp_ui_server import create_ui_resource
from mcp_ui_server.core import UIResource

# Create FastMCP instance
mcp = FastMCP("my-mcp-server")

@mcp.tool()
def greet() -> list[UIResource]:
    """A simple greeting tool that returns a UI resource."""
    ui_resource = create_ui_resource({
        "uri": "ui://greeting/simple",
        "content": {
            "type": "rawHtml",
            "htmlString": """
                <div style="padding: 20px; text-align: center; font-family: Arial, sans-serif;">
                    <h1 style="color: #2563eb;">Hello from Python MCP Server!</h1>
                    <p>This UI resource was generated server-side using mcp-ui-server.</p>
                </div>
            """
        },
        "encoding": "text"
    })
    return [ui_resource]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="My MCP Server")
    parser.add_argument("--http", action="store_true", help="Use HTTP transport instead of stdio")
    parser.add_argument("--port", type=int, default=3000, help="Port for HTTP transport (default: 3000)")
    args = parser.parse_args()

    if args.http:
        print("🚀 Starting MCP server on HTTP (SSE transport)")
        mcp.settings.port = args.port
        mcp.run(transport="sse")
    else:
        print("🚀 Starting MCP server with stdio transport")
        mcp.run()

4. Add More UI Tools
Let's add more sophisticated tools with different types of UI resources:
text@mcp.tool()
def show_dashboard() -> list[UIResource]:
    """Display a sample dashboard with metrics."""
    dashboard_html = """
    <div style="padding: 20px; font-family: Arial, sans-serif;">
        <h1>Server Dashboard</h1>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-top: 20px;">
            <div style="background: #f0f9ff; border: 1px solid #0ea5e9; border-radius: 8px; padding: 16px;">
                <h3 style="margin-top: 0; color: #0369a1;">Active Connections</h3>
                <p style="font-size: 24px; font-weight: bold; margin: 0; color: #0c4a6e;">42</p>
            </div>
            <div style="background: #f0fdf4; border: 1px solid #22c55e; border-radius: 8px; padding: 16px;">
                <h3 style="margin-top: 0; color: #15803d;">CPU Usage</h3>
                <p style="font-size: 24px; font-weight: bold; margin: 0; color: #14532d;">23%</p>
            </div>
            <div style="background: #fefce8; border: 1px solid #eab308; border-radius: 8px; padding: 16px;">
                <h3 style="margin-top: 0; color: #a16207;">Memory Usage</h3>
                <p style="font-size: 24px; font-weight: bold; margin: 0; color: #713f12;">67%</p>
            </div>
        </div>
    </div>
    """
    
    ui_resource = create_ui_resource({
        "uri": "ui://dashboard/main",
        "content": {
            "type": "rawHtml",
            "htmlString": dashboard_html
        },
        "encoding": "text"
    })
    return [ui_resource]

@mcp.tool()
def show_external_site() -> list[UIResource]:
    """Display an external website in an iframe."""
    ui_resource = create_ui_resource({
        "uri": "ui://external/example",
        "content": {
            "type": "externalUrl",
            "iframeUrl": "https://example.com"
        },
        "encoding": "text"
    })
    return [ui_resource]

@mcp.tool()
def show_interactive_demo() -> list[UIResource]:
    """Show an interactive demo with buttons that send intents."""
    interactive_html = """
    <div style="padding: 20px; font-family: Arial, sans-serif;">
        <h2>Interactive Demo</h2>
        <p>Click the buttons below to send different types of actions back to the parent:</p>
        
        <div style="margin: 10px 0;">
            <button onclick="sendIntent('user_action', {type: 'button_click', id: 'demo'})" 
                    style="background: #2563eb; color: white; padding: 8px 16px; border: none; border-radius: 4px; margin: 5px; cursor: pointer;">
                Send Intent
            </button>
            <button onclick="sendToolCall('get_data', {source: 'ui'})" 
                    style="background: #059669; color: white; padding: 8px 16px; border: none; border-radius: 4px; margin: 5px; cursor: pointer;">
                Call Tool
            </button>
        </div>
        
        <div id="status" style="margin-top: 20px; padding: 10px; background: #f3f4f6; border-radius: 4px;">
            Ready - click a button to see the action
        </div>
    </div>
    
    <script>
        function sendIntent(intent, params) {
            const status = document.getElementById('status');
            status.innerHTML = `<strong>Intent sent:</strong> ${intent}<br><strong>Params:</strong> ${JSON.stringify(params)}`;
            
            if (window.parent) {
                window.parent.postMessage({
                    type: 'intent',
                    payload: { intent: intent, params: params }
                }, '*');
            }
        }
        
        function sendToolCall(toolName, params) {
            const status = document.getElementById('status');
            status.innerHTML = `<strong>Tool call:</strong> ${toolName}<br><strong>Params:</strong> ${JSON.stringify(params)}`;
            
            if (window.parent) {
                window.parent.postMessage({
                    type: 'tool',
                    payload: { toolName: toolName, params: params }
                }, '*');
            }
        }
    </script>
    """
    
    ui_resource = create_ui_resource({
        "uri": "ui://demo/interactive",
        "content": {
            "type": "rawHtml",
            "htmlString": interactive_html
        },
        "encoding": "text"
    })
    return [ui_resource]

@mcp.tool()
def show_remote_dom() -> list[UIResource]:
    """Show a Remote DOM component with dynamic elements."""
    remote_dom_script = """
    const container = document.createElement('div');
    container.style.padding = '20px';
    container.style.fontFamily = 'Arial, sans-serif';
    
    const title = document.createElement('ui-text');
    title.textContent = 'Remote DOM Component';
    title.style.fontSize = '18px';
    title.style.fontWeight = 'bold';
    title.style.marginBottom = '10px';
    
    const description = document.createElement('ui-text');
    description.textContent = 'This component was created using Remote DOM scripting.';
    description.style.marginBottom = '15px';
    
    const button = document.createElement('ui-button');
    button.setAttribute('label', 'Click for Tool Call');
    button.addEventListener('press', () => {
        window.parent.postMessage({
            type: 'tool',
            payload: {
                toolName: 'handle_remote_dom_action',
                params: { source: 'remote-dom', timestamp: Date.now() }
            }
        }, '*');
    });
    
    container.appendChild(title);
    container.appendChild(description);
    container.appendChild(button);
    root.appendChild(container);
    """
    
    ui_resource = create_ui_resource({
        "uri": "ui://remote-dom/demo",
        "content": {
            "type": "remoteDom",
            "script": remote_dom_script.strip(),
            "framework": "react"
        },
        "encoding": "text"
    })
    return [ui_resource]

5. Complete Server Example
Here's your complete server.py file:
textimport argparse
from mcp.server.fastmcp import FastMCP
from mcp_ui_server import create_ui_resource
from mcp_ui_server.core import UIResource

# Create FastMCP instance
mcp = FastMCP("my-mcp-server")

@mcp.tool()
def greet() -> list[UIResource]:
    """A simple greeting tool that returns a UI resource."""
    ui_resource = create_ui_resource({
        "uri": "ui://greeting/simple",
        "content": {
            "type": "rawHtml",
            "htmlString": """
                <div style="padding: 20px; text-align: center; font-family: Arial, sans-serif;">
                    <h1 style="color: #2563eb;">Hello from Python MCP Server!</h1>
                    <p>This UI resource was generated server-side using mcp-ui-server.</p>
                </div>
            """
        },
        "encoding": "text"
    })
    return [ui_resource]

@mcp.tool()
def show_dashboard() -> list[UIResource]:
    """Display a sample dashboard with metrics."""
    dashboard_html = """
    <div style="padding: 20px; font-family: Arial, sans-serif;">
        <h1>Server Dashboard</h1>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-top: 20px;">
            <div style="background: #f0f9ff; border: 1px solid #0ea5e9; border-radius: 8px; padding: 16px;">
                <h3 style="margin-top: 0; color: #0369a1;">Active Connections</h3>
                <p style="font-size: 24px; font-weight: bold; margin: 0; color: #0c4a6e;">42</p>
            </div>
            <div style="background: #f0fdf4; border: 1px solid #22c55e; border-radius: 8px; padding: 16px;">
                <h3 style="margin-top: 0; color: #15803d;">CPU Usage</h3>
                <p style="font-size: 24px; font-weight: bold; margin: 0; color: #14532d;">23%</p>
            </div>
        </div>
    </div>
    """
    
    ui_resource = create_ui_resource({
        "uri": "ui://dashboard/main",
        "content": {
            "type": "rawHtml",
            "htmlString": dashboard_html
        },
        "encoding": "text"
    })
    return [ui_resource]

@mcp.tool()
def show_external_site() -> list[UIResource]:
    """Display an external website in an iframe."""
    ui_resource = create_ui_resource({
        "uri": "ui://external/example",
        "content": {
            "type": "externalUrl",
            "iframeUrl": "https://example.com"
        },
        "encoding": "text"
    })
    return [ui_resource]

@mcp.tool()
def show_interactive_demo() -> list[UIResource]:
    """Show an interactive demo with buttons that send intents."""
    interactive_html = """
    <div style="padding: 20px; font-family: Arial, sans-serif;">
        <h2>Interactive Demo</h2>
        <p>Click the button below to send an intent back to the parent:</p>
        
        <button onclick="sendIntent()" 
                style="background: #2563eb; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer;">
            Send Intent
        </button>
        
        <div id="status" style="margin-top: 20px; padding: 10px; background: #f3f4f6; border-radius: 4px;">
            Ready
        </div>
    </div>
    
    <script>
        function sendIntent() {
            const status = document.getElementById('status');
            status.innerHTML = 'Intent sent!';
            
            if (window.parent) {
                window.parent.postMessage({
                    type: 'intent',
                    payload: {
                        intent: 'demo_interaction',
                        params: { source: 'python-server', timestamp: new Date().toISOString() }
                    }
                }, '*');
            }
        }
    </script>
    """
    
    ui_resource = create_ui_resource({
        "uri": "ui://demo/interactive",
        "content": {
            "type": "rawHtml",
            "htmlString": interactive_html
        },
        "encoding": "text"
    })
    return [ui_resource]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="My MCP Server")
    parser.add_argument("--http", action="store_true", help="Use HTTP transport instead of stdio")
    parser.add_argument("--port", type=int, default=3000, help="Port for HTTP transport (default: 3000)")
    args = parser.parse_args()

    if args.http:
        print("🚀 Starting MCP server on HTTP (SSE transport)")
        print("📡 Server will use SSE transport settings")
        mcp.settings.port = args.port
        mcp.run(transport="sse")
    else:
        print("🚀 Starting MCP server with stdio transport")
        mcp.run()

6. Run Your Server
You can run your server in two modes:
Stdio Mode (for command-line clients):
textpython server.py
1
HTTP Mode (for web clients):
textpython server.py --http --port 3000
1
7. Test with UI Inspector
To test your server with a visual interface:

Go to the ui-inspector repository and run it locally
Open the inspector in your browser (usually http://localhost:6274)
Configure the connection:

   * Transport Type: "SSE" (for HTTP mode) or "Stdio" (for stdio mode)
   * Server URL: http://localhost:3000/mcp (for HTTP mode)

Click "Connect"

The inspector will show your tools:

greet: Simple HTML greeting
show_dashboard: Dashboard with metrics
show_external_site: External website iframe
show_interactive_demo: Interactive buttons with intents

When you call these tools, the UI resources will be rendered in the inspector's Tool Results panel.
8. Next Steps
Now that you have a working MCP server with UI resources, you can:

Add more tools with different types of content
Handle user interactions by implementing tools that respond to intents
Create dynamic content based on tool parameters
Integrate with external APIs to display live data
Use blob encoding for larger or binary content

For more examples and advanced usage, see the Usage Examples documentation.
Tips for Development

Use encoding: "text" for simple HTML content
Use encoding: "blob" for larger content or when you need Base64 encoding
Always prefix URIs with ui:// followed by your component identifier
Test both stdio and HTTP transports depending on your use case
Use the ui-inspector for visual testing and debugging

You've successfully created a Python MCP server with UI resources! The FastMCP framework makes it easy to create tools that return rich, interactive UI content to MCP clients.
mcp-ui-server Usage & Examples
This page provides practical examples for using the mcp-ui-server package.
For a complete example, see the python-server-demo.
Basic Setup
First, ensure you have mcp-ui-server available in your project:
textpip install mcp-ui-server
1
Or with uv:
textuv add mcp-ui-server
1
Basic Usage
The core function is create_ui_resource.
textfrom mcp_ui_server import create_ui_resource

# Example 1: Direct HTML, delivered as text
resource1 = create_ui_resource({
    "uri": "ui://my-component/instance-1",
    "content": {
        "type": "rawHtml", 
        "htmlString": "<p>Hello World</p>"
    },
    "encoding": "text"
})

print("Resource 1:", resource1.model_dump_json(indent=2))
# Output for Resource 1:
# {
#   "type": "resource",
#   "resource": {
#     "uri": "ui://my-component/instance-1",
#     "mimeType": "text/html",
#     "text": "<p>Hello World</p>"
#   }
# }

# Example 2: Direct HTML, delivered as a Base64 blob
resource2 = create_ui_resource({
    "uri": "ui://my-component/instance-2",
    "content": {
        "type": "rawHtml", 
        "htmlString": "<h1>Complex HTML</h1>"
    },
    "encoding": "blob"
})

print("Resource 2 (blob will be Base64):", resource2.model_dump_json(indent=2))
# Output for Resource 2:
# {
#   "type": "resource",
#   "resource": {
#     "uri": "ui://my-component/instance-2",
#     "mimeType": "text/html",
#     "blob": "PGgxPkNvbXBsZXggSFRNTDwvaDE+"
#   }
# }

# Example 3: External URL, text encoding
dashboard_url = "https://my.analytics.com/dashboard/123"
resource3 = create_ui_resource({
    "uri": "ui://analytics-dashboard/main",
    "content": {
        "type": "externalUrl", 
        "iframeUrl": dashboard_url
    },
    "encoding": "text"
})

print("Resource 3:", resource3.model_dump_json(indent=2))
# Output for Resource 3:
# {
#   "type": "resource",
#   "resource": {
#     "uri": "ui://analytics-dashboard/main",
#     "mimeType": "text/uri-list",
#     "text": "https://my.analytics.com/dashboard/123"
#   }
# }

# Example 4: External URL, blob encoding (URL is Base64 encoded)
chart_api_url = "https://charts.example.com/api?type=pie&data=1,2,3"
resource4 = create_ui_resource({
    "uri": "ui://live-chart/session-xyz",
    "content": {
        "type": "externalUrl", 
        "iframeUrl": chart_api_url
    },
    "encoding": "blob"
})

print("Resource 4 (blob will be Base64 of URL):", resource4.model_dump_json(indent=2))
# Output for Resource 4:
# {
#   "type": "resource",
#   "resource": {
#     "uri": "ui://live-chart/session-xyz",
#     "mimeType": "text/uri-list",
#     "blob": "aHR0cHM6Ly9jaGFydHMuZXhhbXBsZS5jb20vYXBpP3R5cGU9cGllJmRhdGE9MSwyLDM="
#   }
# }

# Example 5: Remote DOM script, text encoding
remote_dom_script = """
const button = document.createElement('ui-button');
button.setAttribute('label', 'Click me for a tool call!');
button.addEventListener('press', () => {
    window.parent.postMessage({ 
        type: 'tool', 
        payload: { 
            toolName: 'uiInteraction', 
            params: { action: 'button-click', from: 'remote-dom' } 
        } 
    }, '*');
});
root.appendChild(button);
"""

resource5 = create_ui_resource({
    "uri": "ui://remote-component/action-button",
    "content": {
        "type": "remoteDom",
        "script": remote_dom_script.strip(),
        "framework": "react"  # or "webcomponents"
    },
    "encoding": "text"
})

print("Resource 5:", resource5.model_dump_json(indent=2))
# Output for Resource 5:
# {
#   "type": "resource",
#   "resource": {
#     "uri": "ui://remote-component/action-button",
#     "mimeType": "application/vnd.mcp-ui.remote-dom+javascript; framework=react",
#     "text": "\\nconst button = document.createElement('ui-button');\\n..."
#   }
# }

# These resource objects would then be included in the 'content' array
# of a toolResult in an MCP interaction.

Using with FastMCP
Here's how to use create_ui_resource with the FastMCP framework:
textimport argparse
from mcp.server.fastmcp import FastMCP
from mcp_ui_server import create_ui_resource
from mcp_ui_server.core import UIResource

# Create FastMCP instance
mcp = FastMCP("my-server")

@mcp.tool()
def show_dashboard() -> list[UIResource]:
    """Display an analytics dashboard."""
    ui_resource = create_ui_resource({
        "uri": "ui://dashboard/analytics",
        "content": {
            "type": "externalUrl",
            "iframeUrl": "https://my.analytics.com/dashboard"
        },
        "encoding": "text"
    })
    return [ui_resource]

@mcp.tool()
def show_welcome() -> list[UIResource]:
    """Display a welcome message."""
    ui_resource = create_ui_resource({
        "uri": "ui://welcome/main",
        "content": {
            "type": "rawHtml",
            "htmlString": "<h1>Welcome to My MCP Server!</h1><p>How can I help you today?</p>"
        },
        "encoding": "text"
    })
    return [ui_resource]

if __name__ == "__main__":
    mcp.run()

Advanced URI List Example
You can provide multiple URLs in the text/uri-list format for fallback purposes. However, MCP-UI requires a single URL and will only use the first valid URL found:
text# Example 6: Multiple URLs with fallbacks (MCP-UI uses only the first)
multi_url_content = """# Primary dashboard
https://dashboard.example.com/main

# Backup dashboard (will be logged but not used)
https://backup.dashboard.example.com/main

# Emergency fallback (will be logged but not used)  
https://emergency.dashboard.example.com/main"""

resource6 = create_ui_resource({
    "uri": "ui://dashboard-with-fallbacks/session-123",
    "content": {
        "type": "externalUrl", 
        "iframeUrl": multi_url_content
    },
    "encoding": "text"
})

# The client will:
# 1. Use https://dashboard.example.com/main for rendering
# 2. Log a warning about the ignored backup URLs
# This allows you to specify fallback URLs in the standard format 
# while MCP-UI focuses on the primary URL

Error Handling
The create_ui_resource function will raise exceptions if invalid combinations are provided, for example:

URI not starting with ui:// for any content type
Invalid content type specified

textfrom mcp_ui_server.exceptions import InvalidURIError

try:
    create_ui_resource({
        "uri": "invalid://should-be-ui",
        "content": {
            "type": "externalUrl", 
            "iframeUrl": "https://example.com"
        },
        "encoding": "text"
    })
except InvalidURIError as e:
    print(f"Caught expected error: {e}")
    # URI must start with 'ui://' but got: invalid://should-be-ui
 
 
 
 
read these and tell me how do we upgrade our client and server both properly.
right now there is no LLM and i dont want to integrate LLM right away..
tell me how do we do this.Thought for 14sUpgrading Your MCP Server and Client to Support MCP UI
Based on the provided guides (Python Server Walkthrough, mcp-ui-server Usage & Examples), upgrading your setup to support MCP UI involves adding the ability to define and serve UI resources (e.g., raw HTML, external iframes, or Remote DOM components) on the server side, and handling/parsing them on the client side. Since your current server (s2.py) is a secure filesystem MCP server using FastMCP, and your client (mcp_client_manager2.py) is a Python-based manager for connecting and executing actions, the upgrade focuses on:

Server: Installing mcp-ui-server and modifying/adding tools or resources to return UIResource objects created via create_ui_resource. This fits seamlessly with FastMCP as tools can return list[UIResource] or embed them in types.ToolResponse for mixed text/UI responses.
Client: Enhancing the response parsing in execute_action (and possibly list_formatted_capabilities) to detect and handle UIResources. Since your client is Python-based (not JS/React), full interactive rendering (e.g., iframes with postMessage events) is limited—focus on basic handling like saving HTML to a file and opening it in a browser, or directly opening external URLs. For advanced interactivity, the guides recommend testing with tools like ui-inspector (a separate web-based inspector).

No LLM integration is needed here— we're keeping the setup as a direct MCP tool/resource executor. I'll provide step-by-step instructions, including code modifications to your existing files. Test in stages: start with stdio transport, then try HTTP/SSE if needed.
Prerequisites

Install Dependencies:

On both server and client projects (if separate), run:
textpip install mcp-ui-server  # Or uv add mcp-ui-server if using uv

This adds create_ui_resource and UIResource models. Your existing mcp package is already compatible.


Testing Tool: Clone and run the ui-inspector from its repo (as mentioned in the walkthrough). It's a web app for connecting to your MCP server and visually rendering UI resources. Use it to verify server upgrades before client changes.

Run: npm install && npm start (or similar, per repo instructions).
Connect to your server (e.g., stdio or HTTP at http://localhost:3000/mcp).



1. Upgrading the Server (s2.py)
Your server defines filesystem tools/resources/prompts. We'll add MCP UI support by:

Importing from mcp-ui-server.
Adding new tools that return UIResources (e.g., a file viewer UI or interactive editor).
Optionally modifying existing tools to return mixed responses (text + UI).
Ensure URIs start with ui:// for UI resources.
For interactivity, add JavaScript in rawHtml to send postMessage events (e.g., intents or tool calls). These events would be handled by a capable client (like ui-inspector), but your Python client can log them for now.

Modified s2.py (Key Changes):
Add the imports and new tools at the end of your existing code (before if __name__ == "__main__":). I've integrated with your secure filesystem theme—e.g., a UI for browsing files or confirming edits.
python# ... (Your existing imports and code remain unchanged)

from mcp_ui_server import create_ui_resource
from mcp import types  # For ToolResponse if mixing content

# New Tool: Render a simple UI for file listing (raw HTML example)
@mcp.tool()
@handle_errors
async def render_file_list_ui(path: str, ctx: Context) -> list:
    """Render a UI showing directory contents as an interactive list."""
    parsed = ListDirectoryArgs(path=path)
    valid_path = await validate_path(parsed.path)
    entries = os.listdir(valid_path)
    
    # Build HTML for the UI
    html_content = """
    <div style="padding: 20px; font-family: Arial, sans-serif;">
        <h2>Directory Listing: {path}</h2>
        <ul>
    """.format(path=parsed.path)
    for entry in entries:
        entry_type = "[DIR]" if os.path.isdir(os.path.join(valid_path, entry)) else "[FILE]"
        html_content += f"<li>{entry_type} {entry}</li>"
    html_content += """
        </ul>
        <button onclick="sendIntent('refresh_list')" style="background: #2563eb; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer;">
            Refresh
        </button>
        <div id="status" style="margin-top: 10px;"></div>
    </div>
    <script>
        function sendIntent(intent) {
            document.getElementById('status').textContent = 'Intent sent: ' + intent;
            if (window.parent) {
                window.parent.postMessage({ type: 'intent', payload: { intent: intent, params: { path: '{path}' } } }, '*');
            }
        }
    </script>
    """.format(path=parsed.path)
    
    ui_resource = create_ui_resource({
        "uri": f"ui://file-list/{os.path.basename(valid_path)}",
        "content": {
            "type": "rawHtml",
            "htmlString": html_content
        },
        "encoding": "text"  # Use "blob" for larger content (Base64-encoded)
    })
    logger.info(f"Rendered UI for path: {valid_path}")
    return [ui_resource]

# New Tool: Render an external iframe (e.g., for previewing a web-based file viewer)
@mcp.tool()
@handle_errors
async def render_external_preview(path: str, ctx: Context) -> list:
    """Render an external URL preview in an iframe (e.g., for file content)."""
    parsed = GetFileInfoArgs(path=path)
    valid_path = await validate_path(parsed.path)
    
    # Example: Assume an external service; in practice, use a real URL or generate one
    preview_url = "https://example.com/preview?file=" + urllib.parse.quote(valid_path)  # Import urllib if needed
    
    ui_resource = create_ui_resource({
        "uri": f"ui://preview/{os.path.basename(valid_path)}",
        "content": {
            "type": "externalUrl",
            "iframeUrl": preview_url
        },
        "encoding": "text"
    })
    return [ui_resource]

# Optional: Modify an existing tool to return mixed text + UI (e.g., edit_file)
@mcp.tool()
@handle_errors
async def edit_file(path: str, edits: List[Dict[str, str]], ctx: Context, dry_run: bool = False) -> types.ToolResponse:
    # ... (Your existing code for editing and generating diff)
    
    # After generating diff, create a UI for preview/confirmation
    ui_html = f"""
    <div style="padding: 20px;">
        <h2>Edit Preview for {path}</h2>
        <pre><code>{diff}</code></pre>
        <button onclick="sendToolCall('apply_edit', {{dry_run: false}})">Apply Changes</button>
    </div>
    <script>
        function sendToolCall(toolName, params) {{
            window.parent.postMessage({{ type: 'tool', payload: {{ toolName: toolName, params: params }} }}, '*');
        }}
    </script>
    """
    ui_resource = create_ui_resource({
        "uri": f"ui://edit-preview/{os.path.basename(path)}",
        "content": {"type": "rawHtml", "htmlString": ui_html},
        "encoding": "text"
    })
    
    # Return mixed response: text instructions + embedded UI
    return types.ToolResponse(
        content=[
            types.TextContent(text="Here's a preview of the edits:"),
            types.EmbeddedContent(resource=ui_resource)
        ]
    )

# ... (Your existing main block remains; add --http flag support if needed, as in the guide)

Changes Explained:

New tools return list[UIResource] directly (as per examples).
Modified tool uses types.ToolResponse for embedding UI in responses.
Encoding: "text" for simple cases; switch to "blob" for large HTML (auto-Base64).
Interactivity: Added basic postMessage for intents/tool calls (e.g., to trigger refreshes or applies). These won't work in your Python client yet but can be tested in ui-inspector.
Security: Keep using validate_path to ensure UIs only expose allowed paths.


Running the Upgraded Server:

Stdio: python s2.py
HTTP/SSE: Add argparse as in the guide (e.g., --http --port 3000), then python s2.py --http.
Test: Use ui-inspector to call render_file_list_ui with a path arg; it should render the HTML list interactively.



2. Upgrading the Client (mcp_client_manager2.py)
Your client connects via ClientSessionGroup and executes actions, returning str outputs. Upgrade by:

Parsing responses for embedded UIResources (dicts with 'type': 'resource', 'uri' starting with 'ui://').
Basic handling: For "rawHtml", save to temp HTML file and open in browser. For "externalUrl", open the URL directly. Log others.
Use Python's webbrowser module for opening (no external deps needed).
Update list_formatted_capabilities to include UI-capable tools.

Modified mcp_client_manager2.py (Key Changes):
Add imports and enhance execute_action. I've kept it non-disruptive.
python# ... (Your existing imports)

import webbrowser
import tempfile
from mcp import types  # Ensure for response types

# ... (Your existing code)

class MCPClientManager:
    # ... (init, enter/exit, connect_all unchanged)

    async def execute_action(self, action: Dict[str, Any]) -> str:
        """Execute tool/resource/prompt from JSON plan. Returns str output, handles UIResources."""
        await self.wait_ready()
        typ = action.get("action_type")
        name = action.get("action_name")
        args = action.get("arguments", {})

        if typ not in ("tool", "resource", "prompt") or not self.group:
            return f"Error: Invalid '{typ}' or no group."

        try:
            result = None
            if typ == "tool":
                result = await self.group.call_tool(name, args=args)
            elif typ == "resource":
                result = await self.group.read_resource(name)
            elif typ == "prompt":
                result = await self.group.get_prompt(name, args=args)

            # Parse and handle the result (handle mixed content)
            outputs = []
            if hasattr(result, 'content'):
                for content_item in result.content:
                    if hasattr(content_item, 'text'):
                        outputs.append(content_item.text)
                    elif hasattr(content_item, 'resource'):
                        resource = content_item.resource
                        if isinstance(resource, dict) and resource.get('uri', '').startswith('ui://'):
                            # Handle UIResource
                            mime_type = resource.get('mimeType', '')
                            if 'text/html' in mime_type:  # rawHtml
                                html = resource.get('text') or base64.b64decode(resource.get('blob', '')).decode('utf-8')
                                with tempfile.NamedTemporaryFile(delete=False, suffix='.html') as tmp:
                                    tmp.write(html.encode('utf-8'))
                                webbrowser.open(f'file://{tmp.name}')
                                outputs.append(f"Opened UI in browser: {resource['uri']}")
                            elif 'text/uri-list' in mime_type:  # externalUrl
                                url = resource.get('text') or base64.b64decode(resource.get('blob', '')).decode('utf-8')
                                # MCP UI may have multi-URLs; take the first non-comment line
                                url = next((line.strip() for line in url.splitlines() if line.strip() and not line.startswith('#')), '')
                                if url:
                                    webbrowser.open(url)
                                    outputs.append(f"Opened external UI: {url}")
                                else:
                                    outputs.append(f"No valid URL in UIResource: {resource['uri']}")
                            else:
                                outputs.append(f"Unsupported UIResource type: {mime_type} ({resource['uri']})")
            elif typ == "resource" and result.content:  # For direct resource reads
                # Similar parsing if resource is UI
                content = result.content.decode('utf-8')
                try:
                    resource = json.loads(content)
                    if resource.get('uri', '').startswith('ui://'):
                        # Handle as above (e.g., for @mcp.resource returning JSON UI)
                        # ... (repeat UI handling logic)
                except json.JSONDecodeError:
                    outputs.append(content[:500] + "..." if len(content) > 500 else content)
            elif typ == "prompt":
                # ... (existing prompt handling)

            return "\n".join(outputs) or "No output."
        except McpError as e:
            return f"Error: {e.data.message}"
        except Exception as e:
            logger.error(f"Execute failed: {e}")
            return f"Error: {str(e)}"

    async def list_formatted_capabilities(self) -> str:
        # ... (existing code)
        # Optionally append note for UI-capable items
        for name, item in items.items():
            desc = getattr(item, 'description', '') or ''
            if 'ui://' in desc.lower():  # Simple flag for UI tools
                desc += " [Supports UI rendering]"
            # ... (rest unchanged)

# ... (rest of file unchanged)

Changes Explained:

In execute_action, check for embedded resources in result.content.
Handle "text" or "blob" encoding; decode Base64 if needed.
Use tempfile + webbrowser for basic rendering (opens in default browser).
For Remote DOM: Log as unsupported in Python; test in ui-inspector.
Capabilities: Add a note for UI tools.


Using the Upgraded Client:

Connect as before (e.g., async with MCPClientManager(config) as mgr:).
Call: await mgr.execute_action({"action_type": "tool", "action_name": "render_file_list_ui", "arguments": {"path": "/allowed/dir"}})
It should open a browser tab with the UI.



Next Steps and Tips

Testing: Run server in HTTP mode, connect ui-inspector to verify UIs render and interact (e.g., button clicks log events). Then test client calls.
Limitations: Python client can't handle postMessage events (e.g., intents from buttons)—for that, consider a JS client later. Use "text" encoding for simplicity.
Expansion: Add more UI tools (e.g., Remote DOM as in examples) once basic works.
Error Handling: Catch InvalidURIError on server if URIs are wrong.
No LLM: This keeps everything direct—client calls tools, server responds with UI, client "renders" basically.

If issues arise (e.g., with specific tools), provide error logs for tweaks!