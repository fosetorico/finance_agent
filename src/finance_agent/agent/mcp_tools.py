from pathlib import Path
from mcp_use import MCPClient, MCPAgent
from langchain_openai import ChatOpenAI


def create_mcp_agent():
    """
    Creates an MCP-enabled agent that can:
    - Browse the web
    - Fetch live information
    """

    # LLM used by MCP agent (OpenAI)
    llm = ChatOpenAI(model="gpt-4.1")

    # Always load mcp.json from project root (absolute path)
    project_root = Path(__file__).resolve().parents[3] 
    config_path = project_root / "mcp.json"

    client = MCPClient.from_config_file(str(config_path))

    # MCP agent wraps LLM + tools
    agent = MCPAgent(
        llm=llm,
        client=client,
        max_steps=10,
        memory_enabled=False,
    )

    return agent
