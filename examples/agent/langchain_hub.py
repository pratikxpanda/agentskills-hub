"""The same Hub endpoint, consumed by LangChain instead.

This file exists to make one point: the Hub serves MCP, so consuming it is not framework-specific.
Nothing below imports anything from the Hub, and the endpoint has no idea which framework is
calling it.

Requirements:
    pip install langchain langchain-openai langchain-mcp-adapters
    python scripts/seed.py          # prints the endpoint and the key used below

    export HUB_MCP_URL=http://127.0.0.1:8000/mcp/checkout-squad
    export HUB_API_KEY=ashub_...
    export AZURE_OPENAI_API_KEY=...
    export AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com
    export AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
    export AZURE_OPENAI_API_VERSION=2024-12-01-preview

Usage:
    python examples/agent/langchain_hub.py
"""

from __future__ import annotations

import asyncio
import os

QUESTION = (
    "We have a production outage affecting all users — the main database is down. "
    "What severity is this, what is the expected response time, and who should I page first?"
)


async def main() -> None:
    url = os.environ.get("HUB_MCP_URL")
    key = os.environ.get("HUB_API_KEY")
    if not url or not key:
        print("[SKIP] Set HUB_MCP_URL and HUB_API_KEY. `python scripts/seed.py` prints both.")
        return

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        print("[SKIP] langchain-mcp-adapters not installed")
        print("  pip install langchain-mcp-adapters")
        return

    client = MultiServerMCPClient(
        {
            "skills": {
                "transport": "streamable_http",
                "url": url,
                "headers": {"Authorization": f"Bearer {key}"},
            }
        }
    )

    tools = await client.get_tools()
    print(f"=== Endpoint ===\n{url}\n")
    print(f"=== Tools ({len(tools)}) ===")
    for tool in tools:
        print(f"  - {tool.name}")
    print()

    # The catalog and the usage instructions are resources, not tools: the agent is told what
    # exists before it is asked anything, and reads bodies only when it decides to.
    async with client.session("skills") as session:
        catalog = (await session.read_resource("skills://catalog/xml")).contents[0].text
        usage = (await session.read_resource("skills://tools-usage-instructions")).contents[0].text

    print(f"=== Catalog ===\n{catalog}\n")

    try:
        from langchain.agents import create_agent
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
        from langchain_openai import AzureChatOpenAI

        llm = AzureChatOpenAI(
            azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            temperature=0,
        )
    except Exception as exc:  # any misconfiguration here means "no model available"
        print(f"[SKIP] LLM not available ({exc})")
        return

    agent = create_agent(
        llm,
        tools,
        system_prompt=(
            "You are an SRE assistant. Cite the reference document you used.\n\n"
            f"{catalog}\n\n{usage}"
        ),
    )

    print(f"=== Question ===\n{QUESTION}\n")
    print("=== Agent Response ===\n")
    async for chunk in agent.astream(
        {"messages": [HumanMessage(content=QUESTION)]}, stream_mode="updates"
    ):
        for _node, updates in chunk.items():
            for message in updates.get("messages", []):
                if isinstance(message, AIMessage) and message.tool_calls:
                    for call in message.tool_calls:
                        print(f"[tool_call] {call['name']}({call['args']})")
                elif isinstance(message, ToolMessage):
                    text = str(message.content)
                    preview = text[:200] + "..." if len(text) > 200 else text
                    print(f"[tool_result] {message.name} -> {preview}\n")
                elif isinstance(message, AIMessage) and message.content:
                    print(message.content)
    print()


if __name__ == "__main__":
    asyncio.run(main())
