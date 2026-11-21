"""Purpose: Drive mcp-grafana over stdio the way Claude Code does, to prove read-only investigation works.

Scope: Grafana POC test 8. Starts the mcp-grafana container with the Viewer token from Terraform,
    lists its tools, then runs the tool calls given as JSON on the command line.
Usage: python3 monitoring/scripts/mcp-smoke.py '[["tool_name", {"arg": "value"}], ...]'
"""
import json, os, subprocess, sys

calls = json.loads(sys.argv[1]) if len(sys.argv) > 1 else []
env = dict(os.environ, GRAFANA_SERVICE_ACCOUNT_TOKEN=os.environ["MCP_TOKEN"])
proc = subprocess.Popen(
    ["podman", "run", "-i", "--rm", "-e", "GRAFANA_URL", "-e", "GRAFANA_SERVICE_ACCOUNT_TOKEN",
     "docker.io/grafana/mcp-grafana:latest", "-t", "stdio"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)

def rpc(i, method, params=None):
    msg = {"jsonrpc": "2.0", "id": i, "method": method}
    if params is not None:
        msg["params"] = params
    proc.stdin.write(json.dumps(msg) + "\n"); proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            sys.exit("mcp-grafana exited")
        resp = json.loads(line)
        if resp.get("id") == i:
            return resp

rpc(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                      "clientInfo": {"name": "homelab-mcp-smoke", "version": "0"}})
proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"); proc.stdin.flush()
tools = [t["name"] for t in rpc(2, "tools/list")["result"]["tools"]]
print(f"{len(tools)} tools:", ", ".join(sorted(tools)))
for n, (name, args) in enumerate(calls, start=3):
    r = rpc(n, "tools/call", {"name": name, "arguments": args})
    body = r.get("result", {}).get("content", [{}])[0].get("text", "") if "result" in r else json.dumps(r.get("error"))
    print(f"\n>>> {name} {json.dumps(args)}\n{body[:1200]}")
proc.terminate()
