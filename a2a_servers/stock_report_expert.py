import streamlit as st
import asyncio
import traceback
import logging
from uuid import uuid4

# Assuming common types and client are importable
from common.client import A2AClient, A2ACardResolver # card_resolver might be needed
from common.types import Message, TextPart, AgentCard # Import AgentCard if needed directly

import sys
import os

# Get the path to the 'a2a-mcp-tutorial' directory
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Add it to the top of the search path
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SERVER_URL = os.environ.get("HOST_AGENT_URL", "http://localhost:12000/host_agent")

# App title and header
st.title("Stock Market Analyzer")
st.header("Get the current stock details of any stock or the news.")

# Input field for user query
st.subheader("Ask a question about the stock market")
user_text = st.text_input("Enter your query:", placeholder="e.g. What is the current price of AAPL (provide symbol) Or Get me the latest news of Apple Inc.?")

# Button to send query to agent
if st.button("Get Answer"):
    task_id = f"echo-task-{uuid4().hex}"
    session_id = f"session-{uuid4().hex}"

    user_message = Message(
        role="user",
        parts=[TextPart(text=user_text)]
    )

    send_params = {
        "id": task_id,
        "sessionId": session_id,
        "message": user_message.model_dump(),
    }

    try:
        logger.info(f"Sending task {task_id} to {SERVER_URL}...")
        response = asyncio.run(A2AClient(url=SERVER_URL).send_task(payload=send_params))
        agent_card = A2ACardResolver(base_url=SERVER_URL).get_agent_card()
        agent_card_path = A2ACardResolver(base_url=SERVER_URL).__subclasshook__
        # print(f"------------------------------------------------------\n {agent_card}")
        # print(f"------------------------------------------------------\n {response}")
        if response.error:
            st.error(f"Task {task_id} failed: {response.error.message} (Code: {response.error.code})")
        elif response.result:
            task_result = response.result
            if task_result.status.message and task_result.status.message.parts:
                st.subheader("Task Details:")
                
                st.caption("Processed directly by Host Agent")
                st.write(f"**Primary Agent:** {agent_card.name}")

                st.subheader("Generated Answer:")
                for part in task_result.status.message.parts:
                    if hasattr(part, 'text') and part.text:
                        st.success(part.text)
            else:
                st.warning("No message part in agent response status")
        else:
            st.error(f"Received unexpected response for task {task_id}: {response}")

    except Exception as e:
        logger.error(traceback.format_exc())
        st.error(f"An error occurred while communicating with the agent: {e}")

# Additional UI elements
st.sidebar.title("About")
st.sidebar.write("This app uses an A2A + MCP protocol to provide current stock prices and news.")
st.sidebar.write("Please note that this is a demo app and the advice provided is for informational purposes only.")

st.sidebar.title("Disclaimer")
st.sidebar.write("The app is not responsible for any losses or gains incurred based on the advice provided.")