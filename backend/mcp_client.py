"""
MCP Client - Calls Instana MCP Server for enrichment data
Executes the Node.js MCP server as a subprocess and communicates via stdio
"""

import json
import subprocess
import os
from typing import Dict, Any, Optional


class MCPClient:
    """Client for calling the Instana MCP server"""
    
    def __init__(self):
        """Initialize MCP client with path to the built MCP server"""
        self.mcp_server_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "mcp-server",
            "dist",
            "index.js"
        )
        
        if not os.path.exists(self.mcp_server_path):
            raise FileNotFoundError(f"MCP server not found at {self.mcp_server_path}")
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an MCP tool and return the result
        
        Args:
            tool_name: Name of the tool (get_active_incidents, get_service_metrics, get_stack_traces)
            arguments: Tool arguments as a dictionary
            
        Returns:
            Tool result as a dictionary
        """
        try:
            # Prepare MCP request
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            # Call MCP server via subprocess
            result = subprocess.run(
                ["node", self.mcp_server_path],
                input=json.dumps(request),
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return {
                    "error": True,
                    "message": f"MCP server error: {result.stderr}"
                }
            
            # Parse response
            response = json.loads(result.stdout)
            
            if "error" in response:
                return {
                    "error": True,
                    "message": response["error"].get("message", "Unknown error")
                }
            
            return response.get("result", {})
            
        except subprocess.TimeoutExpired:
            return {
                "error": True,
                "message": "MCP server timeout"
            }
        except json.JSONDecodeError as e:
            return {
                "error": True,
                "message": f"Invalid JSON response: {str(e)}"
            }
        except Exception as e:
            return {
                "error": True,
                "message": f"MCP client error: {str(e)}"
            }
    
    def get_stack_traces(self, incident_id: str) -> Dict[str, Any]:
        """Get stack traces for an incident"""
        return self.call_tool("get_stack_traces", {"incident_id": incident_id})
    
    def get_service_metrics(self, service: str, window: str = "10m") -> Dict[str, Any]:
        """Get service metrics for a time window"""
        return self.call_tool("get_service_metrics", {
            "service": service,
            "window": window
        })
    
    def get_active_incidents(self) -> Dict[str, Any]:
        """Get all active incidents"""
        return self.call_tool("get_active_incidents", {})


# Singleton instance
_mcp_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    """Get or create the MCP client singleton"""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client


# Made with Bob