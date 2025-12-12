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

    # MCP client loads tools from mcp.json
    client = MCPClient.from_config_file("mcp.json")

    # MCP agent wraps LLM + tools
    agent = MCPAgent(
        llm=llm,
        client=client,
        max_steps=10,
        memory_enabled=False,
    )

    return agent
