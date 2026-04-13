"""
Bottom-up integration tests for the A2A + MCP pipeline.

Layer 1: Raw services (FinnHub, Yahoo Finance, SerperDev)
Layer 2: MCP servers (SSE endpoints)
Layer 3: A2A agent servers (agent card, task send)
Layer 4: Host agent orchestration (end-to-end)
"""

import asyncio
import json
import sys
import os
import time
import subprocess
import signal
import traceback

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

import httpx

# ─── Helpers ───────────────────────────────────────────────────────

PASS = 0
FAIL = 0

def report(name, ok, detail=""):
    global PASS, FAIL
    status = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))


# ─── Layer 1: Raw Services ────────────────────────────────────────

def test_layer1_services():
    print("\n=== Layer 1: Raw Services ===")

    # Test FinnHub
    try:
        from services.stocks_service.finhub_service import FinHubService
        svc = FinHubService()
        result = svc.get_price_of_stock("AAPL")
        ok = isinstance(result, dict) and "current_price" in result and result["current_price"] > 0
        report("FinnHub get_price_of_stock(AAPL)", ok, f"price={result.get('current_price')}")
    except Exception as e:
        report("FinnHub get_price_of_stock(AAPL)", False, str(e))

    try:
        result = svc.get_symbol_from_query("Apple")
        ok = isinstance(result, dict) and "result" in result
        report("FinnHub get_symbol_from_query(Apple)", ok, f"count={result.get('count', 0)}")
    except Exception as e:
        report("FinnHub get_symbol_from_query(Apple)", False, str(e))

    # Test Yahoo Finance
    try:
        from services.stocks_service.yahoo_fin_stock import YahooFinanceService
        svc = YahooFinanceService()
        result = svc.get_stock_info("AAPL")
        ok = isinstance(result, dict) and "current_price" in result and result["current_price"] > 0
        report("YahooFinance get_stock_info(AAPL)", ok, f"price={result.get('current_price')}")
    except Exception as e:
        report("YahooFinance get_stock_info(AAPL)", False, str(e))

    # Test SerperDev
    try:
        from services.search_engine_service.serper_dev_service import SerperDevService
        svc = SerperDevService()
        result = svc.search_google("Apple stock news", n_results=3)
        ok = isinstance(result, list) and len(result) > 0
        report("SerperDev search_google('Apple stock news')", ok, f"results={len(result) if isinstance(result, list) else result}")
    except Exception as e:
        report("SerperDev search_google", False, str(e))


# ─── Layer 2: MCP Servers ─────────────────────────────────────────

def start_process(cmd, name):
    """Start a background process and return it."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    return proc


def wait_for_server(url, timeout=30):
    """Wait until a server is responding."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=3)
            return True
        except Exception:
            time.sleep(1)
    return False


def test_layer2_mcp_servers(search_port=8080, stocks_port=8181):
    print(f"\n=== Layer 2: MCP Servers (ports {search_port}, {stocks_port}) ===")

    # Test SSE endpoints exist
    try:
        r = httpx.get(f"http://localhost:{search_port}/sse", timeout=5)
        # SSE endpoint returns a streaming response, any non-404 is good
        ok = r.status_code != 404
        report(f"Search MCP /sse endpoint", ok, f"status={r.status_code}")
    except Exception as e:
        report("Search MCP /sse endpoint", False, str(e))

    try:
        r = httpx.get(f"http://localhost:{stocks_port}/sse", timeout=5)
        ok = r.status_code != 404
        report(f"Stocks MCP /sse endpoint", ok, f"status={r.status_code}")
    except Exception as e:
        report("Stocks MCP /sse endpoint", False, str(e))


# ─── Layer 3: A2A Agent Servers ───────────────────────────────────

def test_layer3_agent_cards(stock_port=10000, search_port=11000, host_port=12000):
    print(f"\n=== Layer 3: A2A Agent Cards ===")

    for name, port in [("stock_agent", stock_port), ("search_agent", search_port), ("host_agent", host_port)]:
        try:
            r = httpx.get(f"http://localhost:{port}/.well-known/agent.json", timeout=5)
            ok = r.status_code == 200
            if ok:
                card = r.json()
                report(f"{name} agent card", True, f"name={card.get('name')}, skills={len(card.get('skills', []))}")
            else:
                report(f"{name} agent card", False, f"status={r.status_code}")
        except Exception as e:
            report(f"{name} agent card", False, str(e))


async def test_layer3_stock_agent_task(port=10000):
    print(f"\n=== Layer 3: Stock Agent Task (port {port}) ===")

    payload = {
        "jsonrpc": "2.0",
        "id": "test-stock-1",
        "method": "tasks/send",
        "params": {
            "id": "test-task-stock-1",
            "sessionId": "test-session-1",
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "What is the current price of AAPL?"}]
            }
        }
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"http://localhost:{port}/stock_agent", json=payload)
            report(f"Stock agent POST status", r.status_code == 200, f"status={r.status_code}")
            if r.status_code != 200:
                report(f"Stock agent response body", False, r.text[:500])
                return
            data = r.json()
            result = data.get("result", {})
            status = result.get("status", {})
            state = status.get("state")
            msg_parts = status.get("message", {}).get("parts", [])
            text = msg_parts[0].get("text", "") if msg_parts else ""
            ok = state == "completed" and len(text) > 0
            report(f"Stock agent task completed", ok, f"state={state}, response_len={len(text)}")
            if text:
                report(f"Stock agent mentions price", "price" in text.lower() or "260" in text or "aapl" in text.lower(), f"excerpt={text[:200]}")
    except Exception as e:
        report(f"Stock agent task", False, f"{e}\n{traceback.format_exc()}")


async def test_layer3_search_agent_task(port=11000):
    print(f"\n=== Layer 3: Search Agent Task (port {port}) ===")

    payload = {
        "jsonrpc": "2.0",
        "id": "test-search-1",
        "method": "tasks/send",
        "params": {
            "id": "test-task-search-1",
            "sessionId": "test-session-2",
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Latest news about Apple Inc"}]
            }
        }
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"http://localhost:{port}/google_search_agent", json=payload)
            report(f"Search agent POST status", r.status_code == 200, f"status={r.status_code}")
            if r.status_code != 200:
                report(f"Search agent response body", False, r.text[:500])
                return
            data = r.json()
            result = data.get("result", {})
            status = result.get("status", {})
            state = status.get("state")
            msg_parts = status.get("message", {}).get("parts", [])
            text = msg_parts[0].get("text", "") if msg_parts else ""
            ok = state == "completed" and len(text) > 0
            report(f"Search agent task completed", ok, f"state={state}, response_len={len(text)}")
    except Exception as e:
        report(f"Search agent task", False, f"{e}\n{traceback.format_exc()}")


# ─── Layer 4: Host Agent (end-to-end) ────────────────────────────

async def test_layer4_host_agent(port=12000):
    print(f"\n=== Layer 4: Host Agent End-to-End (port {port}) ===")

    payload = {
        "jsonrpc": "2.0",
        "id": "test-host-1",
        "method": "tasks/send",
        "params": {
            "id": "test-task-host-1",
            "sessionId": "test-session-host-1",
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "What is the current price of AAPL stock?"}]
            }
        }
    }
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(f"http://localhost:{port}/host_agent", json=payload)
            report(f"Host agent POST status", r.status_code == 200, f"status={r.status_code}")
            if r.status_code != 200:
                report(f"Host agent response body", False, r.text[:500])
                return
            data = r.json()
            result = data.get("result", {})
            status = result.get("status", {})
            state = status.get("state")
            msg_parts = status.get("message", {}).get("parts", [])
            text = msg_parts[0].get("text", "") if msg_parts else ""
            ok = state == "completed" and len(text) > 0
            report(f"Host agent task completed", ok, f"state={state}, response_len={len(text)}")
            if text:
                print(f"    Response: {text[:300]}")
    except Exception as e:
        report(f"Host agent task", False, f"{e}\n{traceback.format_exc()}")


# ─── Main ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    layer = sys.argv[1] if len(sys.argv) > 1 else "all"

    if layer in ("1", "all"):
        test_layer1_services()

    if layer in ("2", "all"):
        test_layer2_mcp_servers()

    if layer in ("3", "all"):
        test_layer3_agent_cards()

    if layer in ("3a", "all", "3"):
        asyncio.run(test_layer3_stock_agent_task())

    if layer in ("3b", "all", "3"):
        asyncio.run(test_layer3_search_agent_task())

    if layer in ("4", "all"):
        asyncio.run(test_layer4_host_agent())

    print(f"\n{'='*50}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        sys.exit(1)
