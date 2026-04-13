# A2A Stock Market Analyzer

A multi-agent stock analysis app built with **Agent-to-Agent (A2A)** protocol and **Model Context Protocol (MCP)**. Uses coordinated AI agents to fetch real-time stock prices and search for latest news.

## Architecture

```
Streamlit UI (:3000)
    |
Host Agent (:12000)  -- orchestrator, delegates to child agents
    |
    +-- Stock Agent (:10000) --> Stocks MCP (:8181) --> FinnHub + Yahoo Finance
    |
    +-- Search Agent (:11000) --> Search MCP (:8090) --> SerperDev Google Search
```

- **Host Agent** receives user queries, delegates to the right child agent(s), and synthesizes results
- **Stock Agent** fetches live stock prices via MCP tools connected to FinnHub/Yahoo Finance APIs
- **Search Agent** searches the web via MCP tools connected to SerperDev API
- All agents use **OpenAI GPT-4o-mini** via LiteLLM for reasoning and tool calling

## Tech Stack

- **Google ADK** - Agent Development Kit for building LLM agents
- **MCP (Model Context Protocol)** - Anthropic's protocol for exposing tools to agents
- **A2A (Agent-to-Agent)** - Google's protocol for inter-agent communication
- **LiteLLM** - Unified LLM API (OpenAI, Groq, Gemini, etc.)
- **Streamlit** - Web UI
- **Docker Compose** - Container orchestration

## Setup

### 1. Environment Variables

Create a `.env` file in the project root:

```env
SERPER_DEV_API_KEY="your_serper_dev_api_key"
FINNHUB_API_KEY="your_finnhub_api_key"
GOOGLE_API_KEY="your_google_api_key"
OPENAI_API_KEY="your_openai_api_key"
```

Get API keys from:
- [SerperDev](https://serper.dev/) - Google search API
- [FinnHub](https://finnhub.io/) - Stock data API
- [OpenAI](https://platform.openai.com/) - LLM API

### 2. Run with Docker Compose

```bash
docker compose up --build -d
```

This starts all 6 services. The UI will be available at **http://localhost:3000**.

### 3. Run Locally (without Docker)

```bash
# Install dependencies
uv sync

# Start MCP servers
PYTHONPATH=. uv run python mcp_server/sse/stocks_server.py &
PYTHONPATH=. uv run python mcp_server/sse/search_server.py &

# Start A2A agents
PYTHONPATH=. uv run python a2a_servers/agent_servers/stock_report_agent_server.py &
PYTHONPATH=. uv run python a2a_servers/agent_servers/gsearch_report_agent_server.py &
PYTHONPATH=. uv run python a2a_servers/agent_servers/host_agent_server.py &

# Start UI
PYTHONPATH=. uv run streamlit run a2a_servers/stock_report_expert.py --server.port 3000
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| Search MCP Server | 8090 | MCP server wrapping SerperDev search API |
| Stocks MCP Server | 8181 | MCP server wrapping FinnHub + Yahoo Finance |
| Stock Agent | 10000 | A2A agent for stock price queries |
| Search Agent | 11000 | A2A agent for web search queries |
| Host Agent | 12000 | A2A orchestrator that delegates to child agents |
| Streamlit UI | 3000 | Web frontend |

## Switching LLM Providers

The agents use LiteLLM, so you can switch providers by changing the model string in the agent server files:

```python
# OpenAI (default)
MODEL = LiteLlm(model="openai/gpt-4o-mini")

# Groq (free, but rate limited)
MODEL = LiteLlm(model="groq/llama-3.3-70b-versatile")

# Gemini
MODEL = LiteLlm(model="gemini/gemini-2.5-flash")
```

Set the corresponding API key in `.env` (`OPENAI_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`).

## Project Structure

```
a2a_servers/
  agents/           # ADK agent core logic
  agent_servers/     # A2A server wrappers for each agent
  common/            # A2A protocol types, server, client, task manager
  stock_report_expert.py  # Streamlit UI
mcp_server/
  sse/               # MCP servers (search + stocks) with SSE transport
services/
  search_engine_service/  # SerperDev API wrapper
  stocks_service/         # FinnHub + Yahoo Finance wrappers
adk_agents_testing/       # MCP tool loaders and test examples
```
