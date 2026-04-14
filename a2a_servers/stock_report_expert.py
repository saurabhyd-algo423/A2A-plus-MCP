import streamlit as st
import asyncio
import traceback
import logging
from uuid import uuid4
import sys, os

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from common.client import A2AClient, A2ACardResolver
from common.types import Message, TextPart

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SERVER_URL = os.environ.get("HOST_AGENT_URL", "http://localhost:12000/host_agent")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Market Analyzer",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    html, body, [class*="css"] { font-family: 'JetBrains Mono', monospace; }

    .ticker-wrap {
        overflow: hidden; white-space: nowrap;
        background: #0d1117; border: 1px solid #21262d;
        border-radius: 8px; padding: 8px 0; margin-bottom: 1.5rem;
    }
    .ticker-inner {
        display: inline-flex; gap: 2rem;
        animation: ticker-scroll 25s linear infinite;
    }
    .ticker-inner:hover { animation-play-state: paused; }
    @keyframes ticker-scroll {
        0%   { transform: translateX(0); }
        100% { transform: translateX(-50%); }
    }
    .tick-item { font-size: 0.78rem; color: #8b949e; }
    .tick-sym  { color: #e6edf3; font-weight: 600; margin-right: 4px; }
    .tick-up   { color: #3fb950; }
    .tick-down { color: #f85149; }

    .result-card {
        background: #161b22; border: 1px solid #21262d;
        border-left: 4px solid #3fb950; border-radius: 8px;
        padding: 1.25rem 1.5rem; font-size: 0.9rem;
        color: #e6edf3; line-height: 1.75;
    }
    .result-meta {
        font-size: 0.72rem; color: #6e7681;
        margin-bottom: 0.6rem; display: flex; align-items: center; gap: 6px;
    }
    .pulse {
        width: 7px; height: 7px; border-radius: 50%;
        background: #3fb950; display: inline-block;
        animation: pulse 1.8s ease-in-out infinite;
    }
    @keyframes pulse {
        0%,100% { opacity: 1; transform: scale(1); }
        50%      { opacity: 0.4; transform: scale(0.8); }
    }

    .history-card {
        background: #161b22; border: 1px solid #21262d;
        border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 0.75rem;
    }
    .history-q {
        font-size: 0.82rem; color: #8b949e; margin-bottom: 0.4rem;
    }
    .history-a {
        font-size: 0.85rem; color: #e6edf3; line-height: 1.65;
        border-top: 1px solid #21262d; padding-top: 0.5rem; margin-top: 0.4rem;
    }

    #MainMenu, footer { visibility: hidden; }
    .stDeployButton { display: none; }
</style>
""", unsafe_allow_html=True)

# # ── Ticker bar ────────────────────────────────────────────────────────────────
# TICKERS = [
#     ("AAPL","$213.49","+1.20%",True), ("TSLA","$248.12","-0.83%",False),
#     ("MSFT","$415.20","+0.41%",True), ("NVDA","$875.30","+2.14%",True),
#     ("GOOGL","$175.89","-0.30%",False),("AMZN","$196.54","+0.92%",True),
#     ("META","$572.11","+1.05%",True), ("JPM","$234.77","-0.18%",False),
# ]

# def ticker_html(items):
#     ticks = "".join(
#         f'<span class="tick-item">'
#         f'<span class="tick-sym">{s}</span>'
#         f'<span class="{"tick-up" if up else "tick-down"}">{p} {c}</span>'
#         f'</span>'
#         for s, p, c, up in items
#     )
#     return f'<div class="ticker-wrap"><div class="ticker-inner">{ticks * 2}</div></div>'

# st.markdown(ticker_html(TICKERS), unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown("## ◈ Market Intelligence")
    st.caption("Real-time stock data and news · powered by A2A + MCP agents")
with col_h2:
    st.markdown(
        '<div style="text-align:right;font-size:0.75rem;color:#3fb950;padding-top:12px">'
        '● Agent connected</div>',
        unsafe_allow_html=True,
    )

st.divider()

# ── Helpers ───────────────────────────────────────────────────────────────────
def detect_sub_agents(response_text: str) -> str:
    """
    Infer which sub-agents were involved based on keywords in the response.
    Adjust the keyword heuristics to match your actual agent output if needed.
    """
    text_lower = response_text.lower()

    used_stock  = any(k in text_lower for k in ["price", "market cap", "p/e", "volume", "52w", "trading at", "$"])
    used_search = any(k in text_lower for k in ["news", "according to", "reported", "announced", "article", "source"])

    if used_stock and used_search:
        return "Stock Report Agent, Google Search Agent"
    elif used_search:
        return "Google Search Agent"
    else:
        return "Stock Report Agent"


def call_agent(user_text: str):
    task_id    = f"task-{uuid4().hex}"
    session_id = f"session-{uuid4().hex}"
    payload = {
        "id": task_id,
        "sessionId": session_id,
        "message": Message(role="user", parts=[TextPart(text=user_text)]).model_dump(),
    }
    logger.info(f"Dispatching {task_id} → {SERVER_URL}")
    return asyncio.run(A2AClient(url=SERVER_URL).send_task(payload=payload)), task_id, session_id


def render_result(response, session_id: str, agent_name: str) -> str | None:
    """Renders the agent response and returns the answer text (or None on error)."""
    if response.error:
        st.error(f"Agent error — {response.error.message} (code {response.error.code})")
        return None

    if not response.result:
        st.error("Unexpected empty response from agent.")
        return None

    parts = response.result.status.message and response.result.status.message.parts
    if not parts:
        st.warning("Agent returned no message content.")
        return None

    answer_text = None
    for part in parts:
        if hasattr(part, "text") and part.text:
            answer_text = part.text
            meta = (
                f'<div class="result-meta">'
                f'<span class="pulse"></span>'
                f'{agent_name} · {session_id[:20]}…'
                f'</div>'
            )
            st.markdown(
                f'{meta}<div class="result-card">{answer_text}</div>',
                unsafe_allow_html=True,
            )

    if answer_text:
        sub_agents = detect_sub_agents(answer_text)
        st.markdown(
            f"""
            <div style="
                display: flex; gap: 0; margin-top: 0.75rem;
                border: 1px solid #21262d; border-radius: 8px; overflow: hidden;
            ">
                <div style="flex:1; padding: 0.6rem 1rem; border-right: 1px solid #21262d; background: #161b22;">
                    <div style="font-size: 0.68rem; color: #6e7681; margin-bottom: 3px;">Agent</div>
                    <div style="font-size: 0.82rem; color: #e6edf3; font-weight: 500;">{agent_name}</div>
                </div>
                <div style="flex:2; padding: 0.6rem 1rem; border-right: 1px solid #21262d; background: #161b22;">
                    <div style="font-size: 0.68rem; color: #6e7681; margin-bottom: 3px;">Sub-Agent(s)</div>
                    <div style="font-size: 0.82rem; color: #3fb950; font-weight: 500;">{sub_agents}</div>
                </div>
                <div style="flex:1; padding: 0.6rem 1rem; background: #161b22;">
                    <div style="font-size: 0.68rem; color: #6e7681; margin-bottom: 3px;">Status</div>
                    <div style="font-size: 0.82rem; color: #3fb950; font-weight: 500;">✓ success</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return answer_text


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_query, tab_history = st.tabs(["🔍  Ask the Market", "🕒  Session History"])

# ── Ask the Market tab ────────────────────────────────────────────────────────
with tab_query:
    st.caption("Ask anything — stock prices, latest news, comparisons, or summaries.")

    col_q, col_btn = st.columns([5, 1])
    with col_q:
        user_text = st.text_input(
            "query", label_visibility="collapsed",
            placeholder="e.g. What is the price of TSLA? or Get me the latest news on NVDA.",
            key="main_query",
        )
    with col_btn:
        submitted = st.button("Analyze ↗", use_container_width=True, key="main_btn")

    if submitted and user_text.strip():
        with st.spinner("Routing to host agent…"):
            try:
                response, task_id, session_id = call_agent(user_text)
                agent_card = A2ACardResolver(base_url=SERVER_URL).get_agent_card()
                answer = render_result(response, session_id, agent_card.name)

                # Persist to session history
                if "history" not in st.session_state:
                    st.session_state.history = []
                sub_agents = detect_sub_agents(answer) if answer else "Unknown"
                st.session_state.history.append({
                    "q": user_text,
                    "a": answer or "No response text.",
                    "agent": agent_card.name,
                    "sub_agents": sub_agents,
                    "ok": not response.error,
                })

            except Exception:
                logger.error(traceback.format_exc())
                st.error("Could not reach the agent. Is the host agent running?")

    elif submitted:
        st.warning("Please enter a query before submitting.")

# ── Session History tab ───────────────────────────────────────────────────────
with tab_history:
    history = st.session_state.get("history", [])
    if not history:
        st.info("No queries yet this session.")
    else:
        for item in reversed(history):
            status_icon  = "✓" if item["ok"] else "✗"
            status_color = "#3fb950" if item["ok"] else "#f85149"
            sub_agents   = item.get("sub_agents", "Unknown")
            st.markdown(
                f'<div class="history-card">'
                f'<div class="history-q">'
                f'<span style="color:{status_color}">{status_icon}</span> '
                f'<strong style="color:#e6edf3">{item["q"]}</strong>'
                f'<span style="float:right; color:#6e7681; font-size:0.72rem;">'
                f'{item["agent"]} '
                f'<span style="color:#3fb950">({sub_agents})</span>'
                f'</span>'
                f'</div>'
                f'<div class="history-a">{item["a"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ◈ Stock Analyzer")
    st.caption("v1.0 · A2A + MCP protocol")
    st.divider()

    st.markdown("**About**")
    st.markdown(
        "Uses agent-to-agent (A2A) and Model Context Protocol (MCP) "
        "to retrieve live stock prices and financial news."
    )

    st.divider()
    st.markdown("**Disclaimer**")
    st.caption(
        "This is a demo application. Information provided is for informational "
        "purposes only and does not constitute financial advice."
    )