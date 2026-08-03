"""An Agent Framework agent whose entire catalog comes from a Hub endpoint.

The agent's instructions are one sentence. Everything it knows about which skills exist, what they
are for, and how to read them arrives from the team's MCP endpoint at run time, which is the claim
the Hub exists to make: changing what an agent knows is a subscription change, not a deploy.

Nothing here is Hub-specific. `AgentSkillsMcpContextProvider` is the SDK's, over a plain MCP
session; the Hub is simply the server on the other end. Point `HUB_MCP_URL` at any Agent Skills
MCP server and this script still runs.

Requirements:
    pip install agent-framework --pre
    pip install "agentskills-mcp-server[agentframework]"
    python scripts/seed.py          # prints the endpoint and the key used below

    export HUB_MCP_URL=http://127.0.0.1:8000/mcp/checkout-squad
    export HUB_API_KEY=ashub_...
    export AZURE_OPENAI_API_KEY=...
    export AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com
    export AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
    export AZURE_OPENAI_API_VERSION=2024-12-01-preview

Usage:
    python examples/agent/agent_framework_hub.py
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

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
        from agent_framework import Agent, MCPStreamableHTTPTool
        from agent_framework.azure import AzureOpenAIChatClient
    except ImportError:
        print("[SKIP] agent-framework not installed")
        print("  pip install agent-framework --pre")
        return

    try:
        from agentskills_mcp_server import AgentSkillsMcpContextProvider
    except ImportError:
        print("[SKIP] agentskills-mcp-server[agentframework] not installed")
        print('  pip install "agentskills-mcp-server[agentframework]"')
        return

    skills = MCPStreamableHTTPTool(
        name="skills",
        url=url,
        description="The team's subscribed skills, served by the Agent Skills Hub.",
        # The Hub authenticates the team, not the user: one key per team environment.
        header_provider=lambda _: {"Authorization": f"Bearer {key}"},
    )

    async with skills:
        print(f"=== Endpoint ===\n{url}\n")
        print(f"=== Tools ({len(skills.functions)}) ===")
        for function in skills.functions:
            print(f"  - {function.name}")
        print()

        try:
            client = AzureOpenAIChatClient(
                deployment_name=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            )
        except Exception as exc:  # any misconfiguration here means "no model available"
            print(f"[SKIP] LLM not available ({exc})")
            return

        agent = Agent(
            client=client,
            name="SREAssistant",
            # One sentence on purpose. The catalog is not in the prompt; it is a subscription.
            instructions="You are an SRE assistant. Cite the reference document you used.",
            tools=skills,
            context_providers=[AgentSkillsMcpContextProvider(session=skills.session)],
        )

        print(f"=== Question ===\n{QUESTION}\n")
        print("=== Agent Response ===\n")
        await _stream(agent, QUESTION)


async def _stream(agent: Any, question: str) -> None:
    pending: dict[str, Any] = {}
    last_call_id: str | None = None
    async for update in agent.run(question, stream=True):
        for content in update.contents:
            if content.type == "function_call":
                call_id = getattr(content, "call_id", None) or last_call_id
                last_call_id = call_id or last_call_id
                if call_id:
                    pending[call_id] = pending[call_id] + content if call_id in pending else content
            elif content.type == "function_result":
                call = pending.pop(getattr(content, "call_id", None) or "", None)
                if call is not None:
                    print(f"[tool_call] {call.name}({call.arguments})")
                print(f"[tool_result] {_preview(content.result)}\n")
            elif content.type == "text":
                print(content.text, end="", flush=True)
    for call in pending.values():
        print(f"[tool_call] {call.name}({call.arguments})")
    print("\n")


def _preview(result: Any, limit: int = 200) -> str:
    if isinstance(result, list):
        result = "\n".join(getattr(item, "text", str(item)) for item in result)
    text = str(result)
    return text[:limit] + "..." if len(text) > limit else text


if __name__ == "__main__":
    asyncio.run(main())
