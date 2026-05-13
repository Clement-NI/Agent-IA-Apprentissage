"""Shared helpers for the LangChain agent entrypoints.

Used by `ask.py`, `chat.py`, and `eval/langsmith_eval.py`. The history
behind this file: it used to also host CLI-flag wiring (`add_common_args`,
`resolve_system_prompt`, `require_env`) and a `run_chat_loop` REPL — those
existed for the now-removed `langchain_agent_{anthropic,ollama,gemini}.py`
entry points. The REPL also turned out to have a reproducible
phantom-failure bug across all three providers (final AIMessage came back
as "I apologize, I cannot access the flight tool" even though the prior
tool call returned real data); we replaced it with `chat.py`, which does
its own `while True: agent.invoke(...)` at module level. This file is now
just the three primitives `ask.py`/`chat.py`/`eval` actually import.
"""
from __future__ import annotations

from typing import Sequence

from langchain.agents import create_agent
from langchain_core.messages import AIMessage


def _fmt_args(args: dict) -> str:
    """Render a tool-call args dict for trace-style printing."""
    return ", ".join(f"{k}={v!r}" for k, v in args.items())


def _extract_text(msg: AIMessage) -> str:
    """Pull plain text out of an AIMessage, regardless of content shape.

    AIMessage.content is either a string or a list of content blocks
    (the second shape comes from providers that emit interleaved
    text/tool_use blocks, e.g. Anthropic's tool-call output format).
    """
    if isinstance(msg.content, str):
        return msg.content
    return "".join(
        b.get("text", "")
        for b in msg.content
        if isinstance(b, dict) and b.get("type") == "text"
    )


def build_agent(model, system_prompt: str, tools: Sequence, checkpointer=None):
    """Wrap a chat model into a tool-calling LangGraph agent.

    Provider-agnostic: pass any LangChain BaseChatModel
    (`ChatAnthropic`, `ChatOllama`, `ChatGoogleGenerativeAI`, ...) and
    you get a `CompiledStateGraph` that runs the standard tool-use loop.

    Args:
        model: an instantiated LangChain chat model
        system_prompt: the system message string
        tools: list of LangChain @tool-decorated callables
        checkpointer: pass `None` for langgraph-dev (platform manages
                      persistence); pass `InMemorySaver()` for CLI
                      multi-turn memory keyed by `thread_id`.
    """
    return create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
    )
