"""LangSmith-backed eval runner.

Takes `cases.json` (same format as `run_eval_lc.py`), uploads it to
LangSmith as a dataset (or reuses the existing one), then runs the
agent on every case and logs scores via LangSmith evaluators.

After the run, traces + scores show up at
https://smith.langchain.com/projects/<LANGSMITH_PROJECT>

Usage:
    # 1. Make sure .env has:
    #      LANGSMITH_API_KEY=lsv2_...
    #      LANGSMITH_PROJECT=travel-agent
    #      ANTHROPIC_API_KEY=...   (or run with --provider ollama)

    py eval/langsmith_eval.py                            # default: Claude
    py eval/langsmith_eval.py --provider ollama
    py eval/langsmith_eval.py --provider ollama --model gpt-oss:20b-cloud
    py eval/langsmith_eval.py --filter transport         # only travel cases
    py eval/langsmith_eval.py --dataset-name my-suite-2  # custom dataset name
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Force UTF-8 stdout on Windows so emoji-bearing tool outputs don't crash.
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from agent import load_dotenv  # noqa: E402

load_dotenv()

# LangSmith picks these up automatically when the SDK is imported.
if not os.environ.get("LANGSMITH_API_KEY"):
    sys.stderr.write(
        "LANGSMITH_API_KEY not set. Sign up at https://smith.langchain.com, "
        "create an API key, and put it in .env as LANGSMITH_API_KEY.\n"
    )
    sys.exit(1)
os.environ.setdefault("LANGSMITH_TRACING", "true")
os.environ.setdefault("LANGSMITH_PROJECT", "travel-agent")

import warnings  # noqa: E402
warnings.filterwarnings("ignore")

from langchain_core.messages import AIMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langsmith import Client  # noqa: E402

from CLI.cli import build_agent  # noqa: E402
from configuration.langchain_system_prompt import SYSTEM_PROMPT  # noqa: E402
from MCP.Tools import TOOLS  # noqa: E402


# ---------- agent factory ----------

def _make_agent(provider: str, model: str):
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        chat = ChatAnthropic(model=model, temperature=0.0, max_tokens=4096)
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        chat = ChatOllama(
            model=model,
            temperature=0.0,
            num_predict=8192,
            base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        )
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        chat = ChatGoogleGenerativeAI(model=model, temperature=0.0)
    else:
        raise ValueError(f"unknown provider {provider!r}")
    return build_agent(chat, SYSTEM_PROMPT, TOOLS, checkpointer=InMemorySaver())


# ---------- target: what gets evaluated ----------

def _make_target(agent):
    """Return a function that LangSmith will call with each example.

    Pulls out: final assistant text + the list of tool names called
    during the run. Both are needed by the evaluators below.
    """
    def target(inputs: dict) -> dict:
        thread_id = f"eval-{os.getpid()}-{id(inputs)}"
        result = agent.invoke(
            {"messages": [{"role": "user", "content": inputs["prompt"]}]},
            config={"configurable": {"thread_id": thread_id}},
        )
        messages = result.get("messages", [])
        final_text = ""
        tool_names: list[str] = []
        for msg in messages:
            if not isinstance(msg, AIMessage):
                continue
            for tc in msg.tool_calls:
                tool_names.append(tc["name"])
            if isinstance(msg.content, str):
                final_text = msg.content
            elif isinstance(msg.content, list):
                final_text = "".join(
                    b.get("text", "") for b in msg.content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
        return {"answer": final_text, "tools_called": tool_names}
    return target


# ---------- evaluators ----------
#
# One composite evaluator that emits ONLY the applicable feedback per
# case (returning a list, which langsmith accepts as "multiple results
# from one evaluator"). Splitting into 4 separate evaluators tripped
# `ValueError: Got None` because the SDK rejects None returns even for
# non-applicable cases.

def _eval_all(run, example):
    expected_outputs = example.outputs or {}
    run_outputs = (run.outputs or {}) if run else {}
    tools = run_outputs.get("tools_called", []) or []
    answer = run_outputs.get("answer", "") or ""

    results: list[dict] = []

    expected = expected_outputs.get("expect_tool")
    if expected:
        results.append({
            "key": "expected_tool",
            "score": int(expected in tools),
            "comment": f"expected {expected!r}, got {tools}",
        })

    expected_any = expected_outputs.get("expect_tools_any")
    if expected_any:
        hit = bool(set(expected_any) & set(tools))
        results.append({
            "key": "expected_tools_any",
            "score": int(hit),
            "comment": f"any of {expected_any} in {tools}: {hit}",
        })

    if expected_outputs.get("expect_no_tool"):
        results.append({
            "key": "no_tool",
            "score": int(len(tools) == 0),
            "comment": f"tools_called={tools}",
        })

    pattern = expected_outputs.get("expect_answer_regex")
    if pattern:
        ok = bool(re.search(pattern, answer, re.IGNORECASE))
        results.append({
            "key": "answer_regex",
            "score": int(ok),
            "comment": f"pattern={pattern!r}, matched={ok}",
        })

    # Always include an overall PASS flag = AND of all applicable checks.
    if results:
        overall = all(r["score"] == 1 for r in results)
        results.append({"key": "pass", "score": int(overall)})

    return {"results": results} if results else {"key": "no_checks", "score": 1}


EVALUATORS = [_eval_all]


# ---------- dataset upload ----------

def _ensure_dataset(client: Client, name: str, cases: list[dict]) -> str:
    """Create the dataset if missing; upsert examples to match `cases`.

    Returns the dataset name (which is what `client.evaluate` wants).
    """
    try:
        ds = client.read_dataset(dataset_name=name)
        print(f"[dataset] reusing existing {name!r} (id={ds.id})")
    except Exception:
        ds = client.create_dataset(
            dataset_name=name,
            description="Generated by eval/langsmith_eval.py from cases.json",
        )
        print(f"[dataset] created {name!r} (id={ds.id})")

    # Compare existing examples by their `name` (we encode it in metadata)
    existing = {e.metadata.get("name"): e for e in client.list_examples(dataset_id=ds.id)}
    for case in cases:
        case_name = case["name"]
        if case_name in existing:
            continue
        client.create_example(
            inputs={"prompt": case["prompt"]},
            outputs={
                "expect_tool":         case.get("expect_tool"),
                "expect_tools_any":    case.get("expect_tools_any"),
                "expect_no_tool":      case.get("expect_no_tool"),
                "expect_answer_regex": case.get("expect_answer_regex"),
            },
            metadata={"name": case_name},
            dataset_id=ds.id,
        )
        print(f"[dataset] added example {case_name!r}")
    return name


# ---------- CLI ----------

def main() -> int:
    parser = argparse.ArgumentParser(description="LangSmith eval runner")
    parser.add_argument("--provider", default="anthropic",
                        choices=["anthropic", "ollama", "gemini"])
    parser.add_argument("--model", default=None,
                        help="Override model. Defaults: anthropic→claude-sonnet-4-5, "
                             "ollama→gpt-oss:20b-cloud, gemini→gemini-2.5-flash")
    parser.add_argument("--filter", default="",
                        help="Substring filter on case name (e.g. 'transport').")
    parser.add_argument("--dataset-name", default=None,
                        help="LangSmith dataset name (default: travel-agent-cases).")
    parser.add_argument("--cases", type=Path, default=ROOT / "eval" / "cases.json")
    args = parser.parse_args()

    if args.model is None:
        args.model = {
            "anthropic": "claude-sonnet-4-5",
            "ollama":    "gpt-oss:20b-cloud",
            "gemini":    "gemini-2.5-flash",
        }[args.provider]

    dataset_name = args.dataset_name or f"travel-agent-cases-{args.provider}"

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if args.filter:
        cases = [c for c in cases if args.filter.lower() in c["name"].lower()]
    if not cases:
        print(f"No cases match filter {args.filter!r}.")
        return 1
    print(f"[run] {len(cases)} case(s), provider={args.provider}, model={args.model}")

    client = Client()
    _ensure_dataset(client, dataset_name, cases)

    print(f"[run] building agent...")
    agent = _make_agent(args.provider, args.model)
    target = _make_target(agent)

    print(f"[run] launching LangSmith evaluate() — traces + scores will appear at:")
    print(f"      https://smith.langchain.com/projects/p/{os.environ.get('LANGSMITH_PROJECT')}")
    print()

    results = client.evaluate(
        target,
        data=dataset_name,
        evaluators=EVALUATORS,
        experiment_prefix=f"{args.provider}-{args.model}",
        max_concurrency=1,  # MCP tool calls aren't thread-safe in our wrapper
    )

    # Local summary (LangSmith UI is the canonical view)
    print()
    print("=" * 60)
    print("Local summary (full details in LangSmith UI):")
    print("=" * 60)
    df = results.to_pandas() if hasattr(results, "to_pandas") else None
    if df is not None:
        score_cols = [c for c in df.columns if c.startswith("feedback.")]
        for col in score_cols:
            avg = df[col].mean()
            print(f"  {col[9:]:25s}  avg score: {avg:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
