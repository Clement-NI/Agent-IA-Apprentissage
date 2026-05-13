"""One-shot CLI: ask a question, get an answer, exit.

Usage:
    py ask.py "From Paris to Lyon on 20 May. Flight"
    py ask.py --model claude-haiku-4-5 "Trains from Paris to Marseille tomorrow"
    py ask.py --ollama "Bus from Paris to Berlin"           # free, Qwen Cloud
    py ask.py --ollama --model qwen3-coder:480b-cloud "..."

Skips the interactive chat loop entirely — that's where the phantom-failure
bug lives. This script builds the agent once, calls `invoke()` once, prints
the result, exits.

Default provider: Anthropic Claude Sonnet 4.5 (most reliable at the
strict multi-MCP routing rules). Pass `--ollama` to switch to a free
Ollama Cloud model (qwen3-coder:480b-cloud by default) — costs nothing
but occasionally gives a phantom-failure response; just rerun if so.
"""
from __future__ import annotations

import io
import os
import sys

# Force UTF-8 stdout on Windows so ✈ / 🚆 / 🚌 don't crash the terminal.
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from agent import load_dotenv

load_dotenv()

# Parse argv by hand — minimal, no argparse (full argparse correlated with
# the chat-loop's phantom-failure bug, so we keep this script as
# structurally simple as possible).
_args = list(sys.argv[1:])
_use_ollama = False
if "--ollama" in _args:
    _use_ollama = True
    _args.remove("--ollama")

_model = "qwen3-coder:480b-cloud" if _use_ollama else "claude-sonnet-4-5"
if "--model" in _args:
    i = _args.index("--model")
    if i + 1 < len(_args):
        _model = _args[i + 1]
        del _args[i:i + 2]
for j, a in enumerate(_args):
    if a.startswith("--model="):
        _model = a.split("=", 1)[1]
        del _args[j]
        break

if not _args:
    sys.stderr.write(
        "Usage: py ask.py [--ollama] [--model MODEL] \"your question\"\n"
        "Examples:\n"
        "  py ask.py \"From Paris to Lyon on 20 May. Flight\"\n"
        "  py ask.py --ollama \"Trains from Paris to Marseille tomorrow\"\n"
    )
    sys.exit(2)

question = " ".join(_args).strip()
if not question:
    sys.stderr.write("Empty question.\n")
    sys.exit(2)

if not _use_ollama and not os.environ.get("ANTHROPIC_API_KEY"):
    sys.stderr.write(
        "Set ANTHROPIC_API_KEY in .env. Get one at "
        "https://console.anthropic.com/settings/keys\n"
        "(or pass --ollama to use a free Ollama Cloud model instead)\n"
    )
    sys.exit(1)

import warnings
warnings.filterwarnings("ignore")

from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import AIMessage

from CLI.cli import build_agent, _extract_text, _fmt_args
from configuration.langchain_system_prompt import SYSTEM_PROMPT
from MCP.Tools import TOOLS  # noqa: F401  — side-effect: spawns MCP servers
from MCP import skills

# ---------- skills fast path ----------
# Try a deterministic regex → MCP-tool route first. Skips the LLM entirely
# for queries that match a known shape (90% of "from X to Y on DATE" cases).
# Cuts response time from ~30-50s (LLM agent loop) to ~5-10s (MCP only).
import time as _time
_t0 = _time.time()
skill_result = skills.handle(question)
if skill_result is not None:
    print(skill_result)
    print(f"\n[skill answered in {_time.time() - _t0:.1f}s — no LLM used]",
          file=sys.stderr)
    sys.exit(0)

print(f"[no skill matched; falling back to LLM] {question!r}\n", file=sys.stderr)
print(f"\n[asking {_model}: {question!r}]\n", file=sys.stderr)

if _use_ollama:
    from langchain_ollama import ChatOllama
    # Lift num_predict from Ollama's tiny default — "plan" queries need
    # to produce flights+trains+buses sections, easily 3-4K tokens output.
    _model_obj = ChatOllama(
        model=_model,
        temperature=0.0,
        num_predict=8192,
        base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
    )
else:
    from langchain_anthropic import ChatAnthropic
    _model_obj = ChatAnthropic(model=_model, temperature=0.0, max_tokens=4096)
agent = build_agent(_model_obj, SYSTEM_PROMPT, TOOLS, checkpointer=InMemorySaver())

result = agent.invoke(
    {"messages": [{"role": "user", "content": question}]},
    config={"configurable": {"thread_id": "ask"}},
)

messages = result.get("messages", [])
seen_tc_ids: set = set()
for msg in messages:
    if not isinstance(msg, AIMessage):
        continue
    text = _extract_text(msg)
    if text:
        print(text)
    for tc in msg.tool_calls:
        tc_id = tc.get("id", id(tc))
        if tc_id in seen_tc_ids:
            continue
        seen_tc_ids.add(tc_id)
        print(f"  · {tc['name']}({_fmt_args(tc['args'])})")
