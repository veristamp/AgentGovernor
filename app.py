import asyncio
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from mcp_client.manager import MCPClientManager
from mcp_client.config import Config

app = FastAPI(title="Memory MCP Client", description="Simple app to test memory server with UI visualization")

# Config for the memory server
config = Config.load()

@app.get("/")
async def index():
    return {"message": "Memory MCP Client", "endpoints": ["/visualize"]}

@app.get("/test")
async def test():
    return {"message": "Test endpoint works"}

@app.get("/visualize", response_class=HTMLResponse)
async def visualize_graph():
    print("Endpoint /visualize called")
    try:
        async with MCPClientManager(config) as manager:
            print("MCPClientManager created")
            response = await manager.execute_action({
                "action_type": "tool",
                "action_name": "visualize_graph",
                "arguments": {}
            })
            print(f"Response: {response}")
            
            # Extract UI resource from response
            ui_html = ""
            if "blocks" in response:
                for block in response["blocks"]:
                    block_type = (block.get("type") if hasattr(block, "get") else getattr(block, "type", None))
                    if block_type == "resource":
                        ui_data = (block.get("resource") if hasattr(block, "get") else getattr(block, "resource", None))
                        if ui_data and ui_data.get("mimeType") == "text/html":
                            ui_html = ui_data.get("text", "")
                            break
            
            # Simple HTML page with the visualization
            html_content = f"""
            <html>
            <head>
                <title>Knowledge Graph Visualization</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    iframe {{ border: 1px solid #ccc; width: 100%; height: 500px; }}
                </style>
            </head>
            <body>
                <h1>Knowledge Graph Visualization</h1>
                {ui_html if ui_html else '<p>No visualization available.</p>'}
            </body>
            </html>
            """
            print(f"Returning HTML: {len(html_content)} chars")
            return HTMLResponse(content=html_content)
    except Exception as e:
        print(f"Exception: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
