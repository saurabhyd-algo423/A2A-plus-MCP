# A2A Stock Market Analyzer

A multi-agent stock analysis application built with **Agent-to-Agent (A2A)** protocol and **Model Context Protocol (MCP)**. This system uses coordinated AI agents to fetch real-time stock prices, perform web searches for news, and generate comprehensive stock reports.

## Overview

The A2A Stock Market Analyzer is a sophisticated pipeline that leverages multiple AI agents communicating via Google's Agent-to-Agent protocol. Each agent specializes in a specific task and uses MCP to access external tools and data sources. The system provides a user-friendly Streamlit interface for querying stock information and receiving synthesized reports.

## Architecture

The pipeline consists of the following components:

```
Streamlit UI (:3000)
    |
Host Agent (:12000)  -- Orchestrator: decomposes queries and delegates tasks
    |
    +-- Stock Agent (:10000) --> Stocks MCP Server (:8181) --> FinnHub API + Yahoo Finance
    |
    +-- Search Agent (:11000) --> Search MCP Server (:8090) --> SerperDev Google Search API
```

### Component Descriptions

- **Streamlit UI**: Web-based frontend for user interaction. Allows users to input stock symbols or queries and displays generated reports.

- **Host Agent**: The main orchestrator agent that receives user queries, analyzes them, and delegates subtasks to specialized child agents. It synthesizes responses from multiple agents into a coherent report.

- **Stock Agent**: Specialized agent for financial data retrieval. Uses MCP tools to query stock prices, market data, and financial metrics from FinnHub and Yahoo Finance APIs.

- **Search Agent**: Specialized agent for web search and news aggregation. Uses MCP tools to perform Google searches via SerperDev API to gather relevant news and market insights.

- **Stocks MCP Server**: MCP server that exposes tools for stock data retrieval, wrapping FinnHub and Yahoo Finance APIs.

- **Search MCP Server**: MCP server that exposes tools for web search, wrapping the SerperDev Google Search API.

## Pipeline Flow

1. **User Input**: User enters a query (e.g., "Analyze AAPL stock") in the Streamlit UI.

2. **Query Processing**: UI sends the query to the Host Agent via A2A protocol.

3. **Task Decomposition**: Host Agent analyzes the query and breaks it into subtasks (e.g., get stock prices, search for news).

4. **Delegation**: Host Agent delegates subtasks to appropriate child agents:
   - Stock-related tasks → Stock Agent
   - Search/news tasks → Search Agent

5. **Data Retrieval**: Child agents use MCP to call their respective MCP servers, which fetch data from external APIs.

6. **Synthesis**: Host Agent receives results from child agents and combines them into a comprehensive report.

7. **Response**: Final report is sent back to the UI for display.

## Tech Stack

- **Google ADK (Agent Development Kit)**: Framework for building LLM-powered agents
- **MCP (Model Context Protocol)**: Anthropic's protocol for tool exposure to agents
- **A2A (Agent-to-Agent)**: Google's protocol for inter-agent communication
- **LiteLLM**: Unified API for multiple LLM providers (OpenAI, Groq, Gemini, etc.)
- **Streamlit**: Web UI framework
- **Docker Compose**: Container orchestration
- **Python 3.12+**: Programming language
- **uv**: Fast Python package manager

## Prerequisites

- Python 3.12 or higher
- Docker and Docker Compose
- API keys for external services (see Setup section)

## Setup

### 1. Environment Variables

Create a `.env` file in the project root with the following variables:

```env
SERPER_DEV_API_KEY="your_serper_dev_api_key"
FINNHUB_API_KEY="your_finnhub_api_key"
OPENAI_API_KEY="your_openai_api_key"
```

**API Key Sources:**
- [SerperDev](https://serper.dev/): Google search API (free tier available)
- [FinnHub](https://finnhub.io/): Stock data API (free tier available)
- [OpenAI](https://platform.openai.com/): LLM API (paid)provider

### 2. Installation

#### Option A: Docker Compose (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd A2A-stock-analyzer

# Build and start all services
docker compose up --build -d
```

The application will be available at **http://localhost:3000**.

#### Option B: Local Development

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

## Services and Ports

| Service | Port | Description | Dependencies |
|---------|------|-------------|--------------|
| Search MCP Server | 8090 | MCP server for Google search via SerperDev | SERPER_DEV_API_KEY |
| Stocks MCP Server | 8181 | MCP server for stock data via FinnHub/Yahoo | FINNHUB_API_KEY |
| Stock Agent | 10000 | A2A agent for stock price queries | Stocks MCP Server |
| Search Agent | 11000 | A2A agent for web search queries | Search MCP Server |
| Host Agent | 12000 | A2A orchestrator agent | Stock Agent, Search Agent |
| Streamlit UI | 3000 | Web frontend | Host Agent |

## Configuration

### Switching LLM Providers

The agents use LiteLLM for unified LLM access. You can switch providers by modifying the `MODEL` variable in agent server files:

```python
# OpenAI (default - requires OPENAI_API_KEY)
MODEL = LiteLlm(model="openai/gpt-4o-mini")
```

### Environment Variables

Additional environment variables can be set:

- `HOST_AGENT_URL`: URL for the host agent (default: http://localhost:12000/host_agent)
- `STOCKS_MCP_URL`: URL for stocks MCP server (default: http://localhost:8181/sse)
- `SEARCH_MCP_URL`: URL for search MCP server (default: http://localhost:8090/sse)
- `GSEARCH_AGENT_URL`: URL for search agent (default: http://localhost:11000/google_search_agent)
- `STOCK_AGENT_URL`: URL for stock agent (default: http://localhost:10000/stock_agent)

## Usage

1. Open http://localhost:3000 in your browser
2. Enter a stock symbol (e.g., "AAPL") or a query (e.g., "Analyze TSLA stock performance")
3. Click "Analyze" to generate a report
4. View the comprehensive report including stock data and relevant news

## Project Structure

```
A2A-stock-analyzer/
├── a2a_servers/                 # A2A server implementations
│   ├── agent_servers/           # Individual agent servers
│   │   ├── host_agent_server.py      # Main orchestrator
│   │   ├── stock_report_agent_server.py  # Stock data agent
│   │   └── gsearch_report_agent_server.py # Search agent
│   └── stock_report_expert.py   # Streamlit UI
├── agents/                      # Agent implementations
│   └── adk_agent.py             # Base ADK agent class
├── common/                      # Shared utilities
│   ├── client/                  # A2A client
│   ├── server/                  # A2A server base
│   └── types.py                 # Type definitions
├── mcp_server/                 # MCP server implementations
│   └── sse/                     # Server-Sent Events MCP servers
│       ├── search_server.py    # Search MCP server
│       └── stocks_server.py    # Stocks MCP server
├── services/                    # External service integrations
│   ├── search_engine_service/   # SerperDev integration
│   └── stocks_service/          # FinnHub/Yahoo integration
├── tests/                       # Test suites
├── adk_agents_testing/          # Agent testing utilities
├── docker-compose.yml           # Docker orchestration
├── dockerfile                   # Docker image definition
├── pyproject.toml               # Python project configuration
├── requirements.txt             # Dependencies
└── README.md                    # This file
```

## Testing

The project includes comprehensive tests:

```bash
# Run all tests
uv run python -m pytest tests/

# Run specific test files
uv run python -m pytest tests/test_pipeline.py
uv run python -m pytest tests/test_integration.py
```

Test categories:
- **test_pipeline.py**: End-to-end pipeline tests
- **test_integration.py**: Integration tests between components
- **test_all_layers.py**: Unit tests for individual components

## Development

### Adding New Agents

1. Create a new agent server in `a2a_servers/agent_servers/`
2. Implement the agent logic using Google ADK
3. Add MCP tool integrations if needed
4. Update the Host Agent to delegate tasks to the new agent
5. Add the new service to `docker-compose.yml`

### Extending MCP Servers

1. Create new tools in the MCP server files
2. Implement tool handlers that call external APIs
3. Update agent configurations to use new tools

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## Troubleshooting

### Common Issues

1. **API Key Errors**: Ensure all required API keys are set in `.env`
2. **Port Conflicts**: Check if ports 3000, 8090, 8181, 10000, 11000, 12000 are available
3. **Docker Issues**: Ensure Docker Desktop is running and has sufficient resources
4. **LLM Rate Limits**: Switch to a different LLM provider if hitting rate limits

### Logs

Check logs for individual services:

```bash
# Docker Compose logs
docker compose logs [service-name]

# Local development logs
# Check terminal output for each running process
```

## License

[Add license information here]

## Acknowledgments

- Google ADK for agent development framework
- Anthropic for Model Context Protocol
- Google for Agent-to-Agent protocol
- LiteLLM for unified LLM API
- Streamlit for web UI framework

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
