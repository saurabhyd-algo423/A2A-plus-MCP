"""
Practical pipeline test: start servers via subprocess, test via HTTP.
"""
import asyncio
import subprocess
import sys
import os
import time
import json
import traceback
import signal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PYTHONPATH"] = "."

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0
PROCS = []


def report(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def start_server(script, port, env_extra=None):
    env = {**os.environ, "PYTHONPATH": ROOT}
    if env_extra:
        env.update(env_extra)
    proc = subprocess.Popen(
        [sys.executable, script],
        cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    # Wait for port to open
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=2) as c:
                c.get(f"http://127.0.0.1:{port}/.well-known/agent.json")
                PROCS.append(proc)
                return proc
        except Exception:
            if proc.poll() is not None:
                out = proc.stdout.read().decode(errors="replace")
                print(f"  SERVER CRASHED ({script}):\n{out[-1000:]}")
                return None
            time.sleep(1)
    out = proc.stdout.read(4096).decode(errors="replace") if proc.stdout else ""
    print(f"  TIMEOUT waiting for {script} on port {port}\n{out[-500:]}")
    proc.kill()
    return None


def wait_for_port(port, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=2) as c:
                c.get(f"http://127.0.0.1:{port}/sse")
                return True
        except httpx.ConnectError:
            time.sleep(1)
        except Exception:
            return True  # server is up, just not a GET endpoint
    return False


def start_mcp_server(script, port):
    env = {**os.environ, "PYTHONPATH": ROOT}
    proc = subprocess.Popen(
        [sys.executable, script],
        cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=2) as c:
                c.get(f"http://127.0.0.1:{port}/sse")
                PROCS.append(proc)
                return proc
        except httpx.ConnectError:
            if proc.poll() is not None:
                out = proc.stdout.read().decode(errors="replace")
                print(f"  MCP SERVER CRASHED ({script}):\n{out[-1000:]}")
                return None
            time.sleep(1)
        except Exception:
            # Any response (even error) means server is up
            PROCS.append(proc)
            return proc
    out = proc.stdout.read(4096).decode(errors="replace") if proc.stdout else ""
    print(f"  TIMEOUT waiting for MCP {script} on port {port}\n{out[-500:]}")
    proc.kill()
    return None


def cleanup():
    for p in PROCS:
        try:
            if sys.platform == "win32":
                p.kill()
            else:
                p.send_signal(signal.SIGTERM)
            p.wait(timeout=5)
        except Exception:
            pass


# ─── Tests ────────────────────────────────────────────────────────

def test_layer1():
    print("\n=== Layer 1: Raw Services ===")
    from services.stocks_service.finhub_service import FinHubService
    try:
        r = FinHubService().get_price_of_stock("AAPL")
        report("FinnHub AAPL", r and r["current_price"] > 0, f"price={r['current_price']}")
    except Exception as e:
        report("FinnHub AAPL", False, str(e))

    from services.stocks_service.yahoo_fin_stock import YahooFinanceService
    try:
        r = YahooFinanceService().get_stock_info("AAPL")
        report("Yahoo AAPL", r and r["current_price"] > 0, f"price={r['current_price']}")
    except Exception as e:
        report("Yahoo AAPL", False, str(e))

    from services.search_engine_service.serper_dev_service import SerperDevService
    try:
        r = SerperDevService().search_google("AAPL stock", 2)
        report("SerperDev search", isinstance(r, list) and len(r) > 0, f"count={len(r)}")
    except Exception as e:
        report("SerperDev", False, str(e))


def test_layer2():
    print("\n=== Layer 2: MCP Servers ===")
    p1 = start_mcp_server("mcp_server/sse/search_server.py", 8090)
    report("Search MCP started (:8090)", p1 is not None)
    p2 = start_mcp_server("mcp_server/sse/stocks_server.py", 8181)
    report("Stocks MCP started (:8181)", p2 is not None)
    return p1 is not None and p2 is not None


def test_layer3():
    print("\n=== Layer 3: A2A Agent Servers ===")

    # Stock agent
    p1 = start_server("a2a_servers/agent_servers/stock_report_agent_server.py", 10000)
    report("Stock agent started (:10000)", p1 is not None)

    # Search agent
    p2 = start_server("a2a_servers/agent_servers/gsearch_report_agent_server.py", 11000)
    report("Search agent started (:11000)", p2 is not None)

    if not p1 or not p2:
        return False

    # Test stock agent task
    payload = {
        "jsonrpc": "2.0", "id": "t1", "method": "tasks/send",
        "params": {
            "id": "task-stock-1", "sessionId": "s1",
            "message": {"role": "user", "parts": [{"type": "text", "text": "What is the current price of AAPL?"}]}
        }
    }
    print("  Sending task to stock agent...")
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post("http://127.0.0.1:10000/stock_agent", json=payload)
            report("Stock agent POST", r.status_code == 200, f"status={r.status_code}")
            if r.status_code == 200:
                data = r.json()
                state = data.get("result", {}).get("status", {}).get("state")
                parts = data.get("result", {}).get("status", {}).get("message", {}).get("parts", [])
                text = parts[0].get("text", "") if parts else ""
                report("Stock task state=completed", state == "completed", f"state={state}")
                report("Stock response has content", len(text) > 10, f"len={len(text)}")
                if text:
                    print(f"    >> {text[:300]}")
            else:
                print(f"    Error: {r.text[:500]}")
    except Exception as e:
        report("Stock agent task", False, str(e))

    # Test search agent task
    payload2 = {
        "jsonrpc": "2.0", "id": "t2", "method": "tasks/send",
        "params": {
            "id": "task-search-1", "sessionId": "s2",
            "message": {"role": "user", "parts": [{"type": "text", "text": "Latest news about Apple Inc"}]}
        }
    }
    print("  Sending task to search agent...")
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post("http://127.0.0.1:11000/google_search_agent", json=payload2)
            report("Search agent POST", r.status_code == 200, f"status={r.status_code}")
            if r.status_code == 200:
                data = r.json()
                state = data.get("result", {}).get("status", {}).get("state")
                parts = data.get("result", {}).get("status", {}).get("message", {}).get("parts", [])
                text = parts[0].get("text", "") if parts else ""
                report("Search task state=completed", state == "completed", f"state={state}")
                report("Search response has content", len(text) > 10, f"len={len(text)}")
                if text:
                    print(f"    >> {text[:300]}")
            else:
                print(f"    Error: {r.text[:500]}")
    except Exception as e:
        report("Search agent task", False, str(e))

    return True


def test_layer4():
    print("\n=== Layer 4: Host Agent (full orchestration) ===")

    p = start_server("a2a_servers/agent_servers/host_agent_server.py", 12000)
    report("Host agent started (:12000)", p is not None)
    if not p:
        return

    payload = {
        "jsonrpc": "2.0", "id": "t-host", "method": "tasks/send",
        "params": {
            "id": "task-host-1", "sessionId": "s-host",
            "message": {"role": "user", "parts": [{"type": "text", "text": "What is the current price of AAPL stock?"}]}
        }
    }
    print("  Sending task to host agent...")
    try:
        with httpx.Client(timeout=180) as c:
            r = c.post("http://127.0.0.1:12000/host_agent", json=payload)
            report("Host POST", r.status_code == 200, f"status={r.status_code}")
            if r.status_code == 200:
                data = r.json()
                state = data.get("result", {}).get("status", {}).get("state")
                parts = data.get("result", {}).get("status", {}).get("message", {}).get("parts", [])
                text = parts[0].get("text", "") if parts else ""
                report("Host task completed", state == "completed", f"state={state}")
                report("Host response has content", len(text) > 10, f"len={len(text)}")
                if text:
                    print(f"    >> {text[:400]}")
            else:
                print(f"    Error: {r.text[:500]}")
    except Exception as e:
        report("Host agent task", False, str(e))


if __name__ == "__main__":
    try:
        test_layer1()
        if test_layer2():
            if test_layer3():
                test_layer4()
    finally:
        cleanup()
        print(f"\n{'='*50}")
        print(f"Results: {PASS} passed, {FAIL} failed")
        if FAIL > 0:
            sys.exit(1)
