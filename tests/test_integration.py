"""
Integration tests for A2A + MCP pipeline.
Tests each layer bottom-up, then validates the full pipeline.
"""
import asyncio
import json
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PYTHONPATH"] = "."

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

import httpx
import uvicorn

# Use ports not blocked by Windows Hyper-V
SEARCH_MCP_PORT = 8090
STOCKS_MCP_PORT = 8181
STOCK_AGENT_PORT = 10000
SEARCH_AGENT_PORT = 10001
HOST_AGENT_PORT = 10002

PASS = 0
FAIL = 0


def report(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))


async def start_uvicorn(app, port):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.1)
    return server, task


# ─── Layer 1: Raw Services ────────────────────────────────────────

def test_layer1():
    print("\n=== Layer 1: Raw Services ===")

    from services.stocks_service.finhub_service import FinHubService
    svc = FinHubService()
    try:
        r = svc.get_price_of_stock("AAPL")
        report("FinnHub AAPL price", r and r.get("current_price", 0) > 0, f"price={r.get('current_price')}")
    except Exception as e:
        report("FinnHub AAPL price", False, str(e))

    from services.stocks_service.yahoo_fin_stock import YahooFinanceService
    svc2 = YahooFinanceService()
    try:
        r = svc2.get_stock_info("AAPL")
        report("Yahoo AAPL price", r and r.get("current_price", 0) > 0, f"price={r.get('current_price')}")
    except Exception as e:
        report("Yahoo AAPL price", False, str(e))

    from services.search_engine_service.serper_dev_service import SerperDevService
    svc3 = SerperDevService()
    try:
        r = svc3.search_google("AAPL stock", n_results=2)
        report("SerperDev search", isinstance(r, list) and len(r) > 0, f"results={len(r) if isinstance(r, list) else 'N/A'}")
    except Exception as e:
        report("SerperDev search", False, str(e))


# ─── Layer 2: MCP Servers ─────────────────────────────────────────

async def start_mcp_servers():
    from mcp_server.sse.search_server import create_starlette_app as create_search_app
    from mcp_server.sse.search_server import mcp as search_mcp
    from mcp_server.sse.stocks_server import create_starlette_app as create_stocks_app
    from mcp_server.sse.stocks_server import mcp as stocks_mcp

    search_app = create_search_app(search_mcp._mcp_server, debug=True)
    stocks_app = create_stocks_app(stocks_mcp._mcp_server, debug=True)

    s1, t1 = await start_uvicorn(search_app, SEARCH_MCP_PORT)
    s2, t2 = await start_uvicorn(stocks_app, STOCKS_MCP_PORT)
    return [(s1, t1), (s2, t2)]


async def test_layer2():
    print(f"\n=== Layer 2: MCP Servers (:{SEARCH_MCP_PORT}, :{STOCKS_MCP_PORT}) ===")

    servers = await start_mcp_servers()

    try:
        from google.adk.tools.mcp_tool.mcp_toolset import SseServerParams
        from google.adk.tools.mcp_tool import MCPToolset

        # Stocks
        params = SseServerParams(url=f"http://127.0.0.1:{STOCKS_MCP_PORT}/sse")
        tools, es = await MCPToolset.from_server(connection_params=params)
        report("Stocks MCP tools", len(tools) > 0, f"tools={[t.name for t in tools]}")
        await es.aclose()

        # Search
        params2 = SseServerParams(url=f"http://127.0.0.1:{SEARCH_MCP_PORT}/sse")
        tools2, es2 = await MCPToolset.from_server(connection_params=params2)
        report("Search MCP tools", len(tools2) > 0, f"tools={[t.name for t in tools2]}")
        await es2.aclose()
    except Exception as e:
        report("MCP Toolset", False, f"{e}\n{traceback.format_exc()}")

    for s, t in servers:
        s.should_exit = True
    await asyncio.gather(*[t for _, t in servers], return_exceptions=True)


# ─── Layer 3: Single ADK Agent (stock) ───────────────────────────

async def test_layer3():
    print(f"\n=== Layer 3: ADK Agent invoke (Gemini + MCP tools) ===")

    servers = await start_mcp_servers()

    try:
        from google.adk.tools.mcp_tool.mcp_toolset import SseServerParams
        from google.adk.tools.mcp_tool import MCPToolset
        from a2a_servers.agents.adk_agent import ADKAgent

        params = SseServerParams(url=f"http://127.0.0.1:{STOCKS_MCP_PORT}/sse")
        tools, es = await MCPToolset.from_server(connection_params=params)

        agent = ADKAgent(
            model="gemini-2.0-flash",
            name="test_stock_agent",
            description="Test stock agent",
            instructions="Get stock prices when asked. Use the tools available.",
            tools=tools,
        )
        report("ADK Agent created", True, "model=gemini-2.0-flash")

        print("  Invoking: 'What is the current price of AAPL?'")
        result = await agent.invoke("What is the current price of AAPL?", "test-sess-1")
        has_content = isinstance(result, str) and len(result) > 10
        report("Agent returned content", has_content, f"len={len(result) if result else 0}")
        if result:
            print(f"    Response: {result[:300]}")
            report("Response relevant", any(kw in result.lower() for kw in ["price", "aapl", "$", "260", "stock"]))
        await es.aclose()
    except Exception as e:
        report("ADK Agent invoke", False, f"{e}\n{traceback.format_exc()}")

    for s, t in servers:
        s.should_exit = True
    await asyncio.gather(*[t for _, t in servers], return_exceptions=True)


# ─── Layer 4: A2A stock agent server (JSON-RPC) ──────────────────

async def test_layer4():
    print(f"\n=== Layer 4: A2A Stock Agent Server (JSON-RPC on :{STOCK_AGENT_PORT}) ===")

    servers = await start_mcp_servers()

    try:
        from google.adk.tools.mcp_tool.mcp_toolset import SseServerParams
        from google.adk.tools.mcp_tool import MCPToolset
        from a2a_servers.agents.adk_agent import ADKAgent
        from a2a_servers.agent_servers.utils import generate_agent_card, generate_agent_task_manager
        from a2a_servers.common.server.server import A2AServer
        from a2a_servers.common.types import AgentSkill

        params = SseServerParams(url=f"http://127.0.0.1:{STOCKS_MCP_PORT}/sse")
        tools, es = await MCPToolset.from_server(connection_params=params)

        agent = ADKAgent(
            model="gemini-2.0-flash",
            name="stock_analysis_agent",
            description="Stock price agent",
            instructions="Analyze stock data. Get latest stock prices when asked.",
            tools=tools,
        )

        card = generate_agent_card(
            agent_name="stock_agent",
            agent_description="Stock agent",
            agent_url=f"http://127.0.0.1:{STOCK_AGENT_PORT}",
            agent_version="1.0.0",
            can_stream=False, can_push_notifications=False,
            can_state_transition_history=False,
            default_input_modes=["text"], default_output_modes=["text"],
            skills=[AgentSkill(id="stock", name="stock", description="Stock prices")],
        )

        tm = generate_agent_task_manager(agent=agent)
        a2a = A2AServer(
            host="127.0.0.1", port=STOCK_AGENT_PORT, endpoint="/stock_agent",
            agent_card=card, task_manager=tm,
        )
        a2a_srv, a2a_task = await start_uvicorn(a2a.app, STOCK_AGENT_PORT)

        # Test card
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"http://127.0.0.1:{STOCK_AGENT_PORT}/.well-known/agent.json")
            report("Agent card", r.status_code == 200)

        # Test task
        payload = {
            "jsonrpc": "2.0", "id": "t1", "method": "tasks/send",
            "params": {
                "id": "task-1", "sessionId": "s1",
                "message": {"role": "user", "parts": [{"type": "text", "text": "Price of AAPL?"}]}
            }
        }
        print("  Sending A2A task...")
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(f"http://127.0.0.1:{STOCK_AGENT_PORT}/stock_agent", json=payload)
            report("A2A POST 200", r.status_code == 200, f"status={r.status_code}")
            if r.status_code == 200:
                data = r.json()
                state = data.get("result", {}).get("status", {}).get("state")
                parts = data.get("result", {}).get("status", {}).get("message", {}).get("parts", [])
                text = parts[0].get("text", "") if parts else ""
                report("Task completed", state == "completed", f"state={state}")
                report("Has response text", len(text) > 10, f"len={len(text)}")
                if text:
                    print(f"    Response: {text[:300]}")
            else:
                report("A2A response", False, r.text[:500])

        a2a_srv.should_exit = True
        await a2a_task
        await es.aclose()
    except Exception as e:
        report("A2A server", False, f"{e}\n{traceback.format_exc()}")

    for s, t in servers:
        s.should_exit = True
    await asyncio.gather(*[t for _, t in servers], return_exceptions=True)


# ─── Layer 5: Host Agent (full orchestration) ────────────────────

async def test_layer5():
    print(f"\n=== Layer 5: Host Agent Full Orchestration ===")

    servers = await start_mcp_servers()

    try:
        from google.adk.tools.mcp_tool.mcp_toolset import SseServerParams
        from google.adk.tools.mcp_tool import MCPToolset
        from a2a_servers.agents.adk_agent import ADKAgent
        from a2a_servers.agent_servers.utils import generate_agent_card, generate_agent_task_manager
        from a2a_servers.common.server.server import A2AServer
        from a2a_servers.common.types import AgentSkill

        # --- Start stock agent ---
        stock_params = SseServerParams(url=f"http://127.0.0.1:{STOCKS_MCP_PORT}/sse")
        stock_tools, stock_es = await MCPToolset.from_server(connection_params=stock_params)

        stock_agent = ADKAgent(
            model="gemini-2.0-flash",
            name="stock_analysis_agent",
            description="Stock price agent. Gets stock prices.",
            instructions="Get latest stock prices when asked.",
            tools=stock_tools,
        )
        stock_card = generate_agent_card(
            agent_name="stock_report_agent",
            agent_description="Provides stock prices.",
            agent_url=f"http://127.0.0.1:{STOCK_AGENT_PORT}",
            agent_version="1.0.0",
            can_stream=False, can_push_notifications=False,
            can_state_transition_history=False,
            default_input_modes=["text"], default_output_modes=["text"],
            skills=[AgentSkill(id="stock", name="stock_report", description="Stock prices")],
        )
        stock_tm = generate_agent_task_manager(agent=stock_agent)
        stock_a2a = A2AServer(
            host="127.0.0.1", port=STOCK_AGENT_PORT, endpoint="/stock_agent",
            agent_card=stock_card, task_manager=stock_tm,
        )
        stock_srv, stock_task = await start_uvicorn(stock_a2a.app, STOCK_AGENT_PORT)
        report("Stock agent started", True, f"port={STOCK_AGENT_PORT}")

        # --- Start search agent ---
        search_params = SseServerParams(url=f"http://127.0.0.1:{SEARCH_MCP_PORT}/sse")
        search_tools, search_es = await MCPToolset.from_server(connection_params=search_params)

        search_agent = ADKAgent(
            model="gemini-2.0-flash",
            name="google_search_agent",
            description="Search agent. Searches the web.",
            instructions="Search the web when asked.",
            tools=search_tools,
        )
        search_card = generate_agent_card(
            agent_name="google_search_agent",
            agent_description="Handles search queries.",
            agent_url=f"http://127.0.0.1:{SEARCH_AGENT_PORT}",
            agent_version="1.0.0",
            can_stream=False, can_push_notifications=False,
            can_state_transition_history=True,
            default_input_modes=["text"], default_output_modes=["text"],
            skills=[AgentSkill(id="search", name="google_search", description="Web search")],
        )
        search_tm = generate_agent_task_manager(agent=search_agent)
        search_a2a = A2AServer(
            host="127.0.0.1", port=SEARCH_AGENT_PORT, endpoint="/google_search_agent",
            agent_card=search_card, task_manager=search_tm,
        )
        search_srv, search_task = await start_uvicorn(search_a2a.app, SEARCH_AGENT_PORT)
        report("Search agent started", True, f"port={SEARCH_AGENT_PORT}")

        # --- Start host agent ---
        host_agent = ADKAgent(
            model="gemini-2.0-flash",
            name="host_agent",
            description="Orchestrator agent",
            instructions="Coordinate tasks between agents",
            tools=[],
            is_host_agent=True,
            remote_agent_addresses=[
                f"http://127.0.0.1:{SEARCH_AGENT_PORT}/google_search_agent",
                f"http://127.0.0.1:{STOCK_AGENT_PORT}/stock_agent",
            ],
        )
        host_card = generate_agent_card(
            agent_name="host_agent",
            agent_description="Orchestrator",
            agent_url=f"http://127.0.0.1:{HOST_AGENT_PORT}",
            agent_version="1.0.0",
            can_stream=False, can_push_notifications=False,
            can_state_transition_history=True,
            default_input_modes=["text"], default_output_modes=["text"],
            skills=[AgentSkill(id="coord", name="coordinate", description="Coordinate agents")],
        )
        host_tm = generate_agent_task_manager(agent=host_agent)
        host_a2a = A2AServer(
            host="127.0.0.1", port=HOST_AGENT_PORT, endpoint="/host_agent",
            agent_card=host_card, task_manager=host_tm,
        )
        host_srv, host_task = await start_uvicorn(host_a2a.app, HOST_AGENT_PORT)
        report("Host agent started", True, f"port={HOST_AGENT_PORT}")

        # --- Test host agent ---
        payload = {
            "jsonrpc": "2.0", "id": "t-host-1", "method": "tasks/send",
            "params": {
                "id": "task-host-1", "sessionId": "s-host-1",
                "message": {"role": "user", "parts": [{"type": "text", "text": "What is the current price of AAPL stock?"}]}
            }
        }
        print("  Sending task to host agent...")
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(f"http://127.0.0.1:{HOST_AGENT_PORT}/host_agent", json=payload)
            report("Host POST 200", r.status_code == 200, f"status={r.status_code}")
            if r.status_code == 200:
                data = r.json()
                state = data.get("result", {}).get("status", {}).get("state")
                parts = data.get("result", {}).get("status", {}).get("message", {}).get("parts", [])
                text = parts[0].get("text", "") if parts else ""
                report("Host task completed", state == "completed", f"state={state}")
                report("Host has response", len(text) > 10, f"len={len(text)}")
                if text:
                    print(f"    Response: {text[:400]}")
            else:
                error_body = r.text[:500]
                report("Host response", False, error_body)

        # Cleanup
        for srv in [host_srv, stock_srv, search_srv]:
            srv.should_exit = True
        await asyncio.gather(host_task, stock_task, search_task, return_exceptions=True)
        await stock_es.aclose()
        await search_es.aclose()

    except Exception as e:
        report("Host agent test", False, f"{e}\n{traceback.format_exc()}")

    for s, t in servers:
        s.should_exit = True
    await asyncio.gather(*[t for _, t in servers], return_exceptions=True)


# ─── Main ─────────────────────────────────────────────────────────

async def main():
    layer = sys.argv[1] if len(sys.argv) > 1 else "all"

    if layer in ("1", "all"):
        test_layer1()
    if layer in ("2", "all"):
        await test_layer2()
    if layer in ("3", "all"):
        await test_layer3()
    if layer in ("4", "all"):
        await test_layer4()
    if layer in ("5", "all"):
        await test_layer5()

    print(f"\n{'='*50}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
