"""
MCP Client - Calls Instana MCP Server for enrichment data
Executes the Node.js MCP server as a subprocess and communicates via stdio
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional


class MCPClient:
    """Client for calling the Instana MCP server"""
    
    def __init__(self):
        """Initialize MCP client with path to the built MCP server"""
        self.repo_root = Path(os.path.dirname(os.path.dirname(__file__))).resolve()
        self.mcp_server_path = self.repo_root / "mcp-server" / "dist" / "index.js"
        self.protocol_version = "2024-11-05"
        
        if not self.mcp_server_path.exists():
            raise FileNotFoundError(f"MCP server not found at {self.mcp_server_path}")

    def _window_to_minutes(self, window: str) -> int:
        normalized = (window or "10m").strip().lower()
        if normalized.endswith("m"):
            normalized = normalized[:-1]
        try:
            return max(int(normalized), 1)
        except ValueError:
            return 10
    
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
            initialize_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "opsbob-backend",
                        "version": "2.0.0"
                    }
                }
            }
            initialized_notification = {
                "jsonrpc": "2.0",
                "method": "initialized",
                "params": {}
            }
            list_tools_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {}
            }
            tool_request = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            payload = "\n".join(
                json.dumps(item)
                for item in [initialize_request, initialized_notification, list_tools_request, tool_request]
            ) + "\n"
            
            # Call MCP server via subprocess
            result = subprocess.run(
                ["node", str(self.mcp_server_path)],
                input=payload,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.repo_root)
            )
            
            if result.returncode != 0:
                return {
                    "error": True,
                    "message": f"MCP server error: {result.stderr.strip() or result.stdout.strip()}"
                }
            
            responses = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    responses.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

            response = next((item for item in responses if item.get("id") == 3), None)
            if not response:
                return {
                    "error": True,
                    "message": f"No tools/call response received from MCP server. Raw stdout: {result.stdout.strip()}"
                }

            if "error" in response:
                return {
                    "error": True,
                    "message": response["error"].get("message", "Unknown error")
                }

            rpc_result = response.get("result", {})
            content = rpc_result.get("content", [])
            text_payload = "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ).strip()

            if not text_payload:
                return {"error": False, "raw": rpc_result}

            parsed = json.loads(text_payload)
            if rpc_result.get("isError") or (isinstance(parsed, dict) and parsed.get("error")):
                return {
                    "error": True,
                    "message": parsed.get("details") or parsed.get("error") or "MCP tool returned an error",
                    "raw": parsed
                }

            return parsed
            
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
        result = self.call_tool("get_stack_traces", {"incident_id": incident_id})
        if result.get("error"):
            return result

        return {
            "error": False,
            "incident_id": result.get("incidentId", incident_id),
            "service": result.get("service", "unknown"),
            "stack_trace": result.get("stackTrace", "No stack trace available"),
            "timestamp": result.get("timestamp")
        }
    
    def get_service_metrics(self, service: str, window: str = "10m") -> Dict[str, Any]:
        """Get service metrics for a time window"""
        result = self.call_tool("get_service_metrics", {
            "service": service,
            "window": window
        })
        if result.get("error"):
            return result

        window_minutes = self._window_to_minutes(window)
        current_memory_mb = result.get("heap_used_mb", 0)
        growth_per_minute = result.get("mem_growth_mb_per_min", 0)
        baseline_memory_mb = max(current_memory_mb - (growth_per_minute * window_minutes), 0)

        return {
            "error": False,
            "service": service,
            "current_memory_mb": current_memory_mb,
            "baseline_memory_mb": baseline_memory_mb,
            "mem_growth_mb_per_min": growth_per_minute,
            "heap_total_mb": result.get("heap_total_mb", 0),
            "rss_mb": result.get("mem_rss_mb", 0),
            "timestamp": result.get("timestamp")
        }
    
    def get_active_incidents(self) -> Dict[str, Any]:
        """Get all active incidents"""
        result = self.call_tool("get_active_incidents", {})
        if isinstance(result, dict) and result.get("error"):
            return result
        return {"error": False, "incidents": result}


# Singleton instance
_mcp_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    """Get or create the MCP client singleton"""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client


# Made with Bob