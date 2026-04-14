import asyncio
import os
from dotenv import load_dotenv, find_dotenv

from google.adk.models.lite_llm import LiteLlm
from a2a_servers.agent_servers.utils import generate_agent_card, generate_agent_task_manager
from a2a_servers.agents.adk_agent import ADKAgent
from a2a_servers.common.server.server import A2AServer
from a2a_servers.common.types import AgentSkill
from adk_agents_testing.mcp_tools.mcp_tool_search import return_sse_mcp_tools_search

load_dotenv(find_dotenv())

MODEL = LiteLlm(model="openai/gpt-4o-mini")

async def run_agent():
    AGENT_NAME = "google_search_agent"
    AGENT_DESCRIPTION = "An agent that handles search queries and can read pages online."
    HOST = "0.0.0.0"
    PORT = 11000
    AGENT_URL = f"http://{HOST}:{PORT}"
    AGENT_VERSION = "1.0.0"

    AGENT_SKILLS = [
        AgentSkill(
            id="GOOGLE_SEARCH",
            name="google_search",
            description="Handles search queries and can read pages online.",
        ),
    ]

    AGENT_CARD = generate_agent_card(
        agent_name=AGENT_NAME,
        agent_description=AGENT_DESCRIPTION,
        agent_url=AGENT_URL,
        agent_version=AGENT_VERSION,
        can_stream=False,
        can_push_notifications=False,
        can_state_transition_history=True,
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=AGENT_SKILLS,
    )

    # Initialize MCP tools
    gsearch_tools, g_search_exit_stack = await return_sse_mcp_tools_search()

    google_search_agent = ADKAgent(
        model=MODEL,
        name="google_search_agent",
        description="Handles search queries and can read pages online.",
        tools=gsearch_tools,
        instructions=(
            "CRITICAL: You must NEVER call multiple tools in the same response. Call only ONE tool at a time. Wait for the result before calling the next tool. If asked about multiple news articles, look them up one by one sequentially."
            "You are an expert googler. Can search anything on google and read pages online."
        ),
    )

    task_manager = generate_agent_task_manager(
        agent=google_search_agent,
    )

    server = A2AServer(
        host=HOST,
        port=PORT,
        endpoint="/google_search_agent",
        agent_card=AGENT_CARD,
        task_manager=task_manager
    )

    print(f"Starting {AGENT_NAME} A2A Server on {AGENT_URL}")
    try:
        await server.astart()
    finally:
        if g_search_exit_stack:
            await g_search_exit_stack.aclose()


if __name__ == "__main__":
    asyncio.run(run_agent())
