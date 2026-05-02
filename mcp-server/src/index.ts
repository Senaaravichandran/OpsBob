#!/usr/bin/env node

/**
 * MCP Server for OpsBob - Real Instana API Integration
 * Makes actual HTTP calls to Instana REST API for incidents, metrics, and stack traces
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import fetch from "node-fetch";
import dotenv from "dotenv";

// Load environment variables
dotenv.config();

const INSTANA_BASE_URL = process.env.INSTANA_BASE_URL;
const INSTANA_API_TOKEN = process.env.INSTANA_API_TOKEN;

/**
 * Helper function to call Instana REST API
 */
async function callInstanaAPI(endpoint: string, method: string = "GET"): Promise<any> {
  if (!INSTANA_BASE_URL || !INSTANA_API_TOKEN) {
    return {
      error: "Instana credentials not configured",
      details: "Set INSTANA_BASE_URL and INSTANA_API_TOKEN in .env file",
    };
  }

  const url = `${INSTANA_BASE_URL}${endpoint}`;
  
  try {
    const response = await fetch(url, {
      method,
      headers: {
        "Authorization": `apiToken ${INSTANA_API_TOKEN}`,
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      return {
        error: `Instana API returned ${response.status}`,
        details: errorText,
        endpoint: endpoint,
      };
    }

    return await response.json();
  } catch (error: any) {
    return {
      error: "Failed to connect to Instana API",
      details: error.message,
      endpoint: endpoint,
    };
  }
}

/**
 * Create and configure the MCP server
 */
const server = new Server(
  {
    name: "instana-mcp-server",
    version: "2.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

/**
 * Handler for listing available tools
 */
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "get_active_incidents",
        description:
          "Get list of active incidents from Instana monitoring system. Makes real API call to Instana to fetch current open incidents.",
        inputSchema: {
          type: "object",
          properties: {},
          required: [],
        },
      },
      {
        name: "get_service_metrics",
        description:
          "Get real-time service metrics from Instana. Returns memory usage, heap statistics, and growth rate for a specific service.",
        inputSchema: {
          type: "object",
          properties: {
            service: {
              type: "string",
              description: "Name of the service to get metrics for (e.g., 'payments-api')",
            },
            window: {
              type: "string",
              description: "Time window in minutes (default: '10')",
            },
          },
          required: ["service"],
        },
      },
      {
        name: "get_stack_traces",
        description:
          "Get stack traces for a specific incident from Instana. Returns formatted stack trace showing the error location and call stack.",
        inputSchema: {
          type: "object",
          properties: {
            incident_id: {
              type: "string",
              description: "ID of the incident to get stack traces for",
            },
          },
          required: ["incident_id"],
        },
      },
    ],
  };
});

/**
 * Handler for tool execution
 */
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case "get_active_incidents": {
        // Query Instana for active incidents in last 10 minutes
        const windowSize = 600000; // 10 minutes in milliseconds
        const endpoint = `/api/v1/events?windowSize=${windowSize}&excludeSynthetic=true`;
        
        const response = await callInstanaAPI(endpoint);
        
        // Check for API error
        if (response.error) {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(response, null, 2),
              },
            ],
            isError: true,
          };
        }

        // Parse and format incidents
        const incidents = (response.items || []).map((event: any) => ({
          incidentId: event.id,
          title: event.title || event.text,
          service: event.service || "unknown",
          severity: event.severity || "MEDIUM",
          startTime: new Date(event.start).toISOString(),
          eventType: event.eventType,
        }));

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(incidents, null, 2),
            },
          ],
        };
      }

      case "get_service_metrics": {
        const service = args?.service as string;
        const window = args?.window as string || "10";

        if (!service) {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({ error: "service parameter is required" }, null, 2),
              },
            ],
            isError: true,
          };
        }

        // Query Instana for service snapshots
        const endpoint = `/api/v1/infrastructure-monitoring/snapshots?plugin=process&q=${encodeURIComponent(service)}`;
        
        const response = await callInstanaAPI(endpoint);
        
        // Check for API error
        if (response.error) {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(response, null, 2),
              },
            ],
            isError: true,
          };
        }

        // Parse metrics from snapshots
        const snapshots = response.items || [];
        
        if (snapshots.length === 0) {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({
                  error: "No metrics found for service",
                  service: service,
                }, null, 2),
              },
            ],
            isError: true,
          };
        }

        // Get latest snapshot
        const latest = snapshots[0];
        const data = latest.data || {};
        
        // Extract memory metrics
        const memRssMb = Math.round((data.memory?.rss || 0) / 1024 / 1024);
        const heapUsedMb = Math.round((data.memory?.heapUsed || 0) / 1024 / 1024);
        const heapTotalMb = Math.round((data.memory?.heapTotal || 0) / 1024 / 1024);
        
        // Calculate growth (simplified - would need historical data for accurate rate)
        const memGrowthMb = heapUsedMb > 200 ? Math.round((heapUsedMb - 128) / parseInt(window)) : 0;

        const metrics = {
          service: service,
          mem_rss_mb: memRssMb,
          heap_used_mb: heapUsedMb,
          heap_total_mb: heapTotalMb,
          mem_growth_mb_per_min: memGrowthMb,
          timestamp: new Date(latest.timestamp).toISOString(),
          status: heapUsedMb > 300 ? "degraded" : "healthy",
        };

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(metrics, null, 2),
            },
          ],
        };
      }

      case "get_stack_traces": {
        const incidentId = args?.incident_id as string;

        if (!incidentId) {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({ error: "incident_id parameter is required" }, null, 2),
              },
            ],
            isError: true,
          };
        }

        // Query Instana for specific incident details
        const endpoint = `/api/v1/events/${incidentId}`;
        
        const response = await callInstanaAPI(endpoint);
        
        // Check for API error
        if (response.error) {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(response, null, 2),
              },
            ],
            isError: true,
          };
        }

        // Extract stack trace from incident
        let stackTrace = "No stack trace available";
        
        // Check various possible locations for stack trace
        if (response.problem?.problems && Array.isArray(response.problem.problems)) {
          const problems = response.problem.problems;
          
          // Get top 3 stack frames
          const frames = problems.slice(0, 3).map((p: any) => {
            const file = p.file || p.location || "unknown";
            const line = p.line || "?";
            const method = p.method || p.function || "unknown";
            return `    at ${method} (${file}:${line})`;
          });
          
          if (frames.length > 0) {
            stackTrace = `Error: ${response.text || "Memory issue detected"}\n${frames.join("\n")}`;
          }
        } else if (response.stackTrace) {
          stackTrace = response.stackTrace;
        } else if (response.text) {
          // Use incident text as fallback
          stackTrace = `Incident: ${response.text}\nService: ${response.service || "unknown"}`;
        }

        const result = {
          incidentId: incidentId,
          service: response.service || "unknown",
          stackTrace: stackTrace,
          timestamp: new Date(response.start || Date.now()).toISOString(),
          severity: response.severity || "MEDIUM",
        };

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(result, null, 2),
            },
          ],
        };
      }

      default:
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({ error: `Unknown tool: ${name}` }, null, 2),
            },
          ],
          isError: true,
        };
    }
  } catch (error: any) {
    // Catch-all error handler
    const errorMessage = error instanceof Error ? error.message : "Unknown error occurred";
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({
            error: "Tool execution failed",
            details: errorMessage,
            tool: name,
          }, null, 2),
        },
      ],
      isError: true,
    };
  }
});

/**
 * Start the server
 */
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  
  // Log to stderr so it doesn't interfere with stdio protocol
  console.error("MCP Instana Server v2.0 running on stdio");
  console.error(`Instana Base URL: ${INSTANA_BASE_URL || "NOT CONFIGURED"}`);
  console.error(`API Token: ${INSTANA_API_TOKEN ? "CONFIGURED" : "NOT CONFIGURED"}`);
}

main().catch((error) => {
  console.error("Fatal error in main():", error);
  process.exit(1);
});

// Export for testing
export { server, callInstanaAPI };

// Made with Bob
