# Agent-IA-Apprentissage

> Un projet pour approfondir mes connaissances en LLM, Agent IA, RAG, MCP…

A French-Europe **travel CLI/web agent**: real-time flights (Duffel),
trains (SNCF Open Data), and buses (FlixBus) wired into a LangChain
agent with three transport MCP servers, a regex fast-path that
bypasses the LLM for common shapes (~5× speedup), an on-demand skill
markdown for complex reasoning, a Streamlit chat UI, and a LangSmith
eval suite.

## Quick start

```powershell
# install
cd "Agent-IA-Apprentissage"
py -m pip install -r requirements-langchain.txt
cd MCP\flights-mcp  ; py -m uv sync ; cd ..\..
cd MCP\flixbus-mcp  ; py -m uv sync ; cd ..\..

# configure
copy .env.example .env       # then edit .env with your API keys

# run (any one)
py ask.py "TGV from Paris to Bordeaux on 2026-05-25"     # one-shot CLI
py chat.py                                                # multi-turn REPL
py -m streamlit run app.py                                # browser UI
```

## Full documentation

See **[USAGE.md](USAGE.md)** for:
- Detailed architecture diagram
- Configuration reference (all env vars)
- Evaluation suite (`eval/langsmith_eval.py`)
- Known issues + troubleshooting
- How to add new MCPs / skills

## What it looks like

```
you> Plan a trip from Paris to Lyon on 2026-05-25

[skill: plan]  Paris → Lyon on 2026-05-25
### ✈ Flights
    EUR44.01  CDG→LYS  14:42 → 15:49  (1h07m)  Iberia  [Non-stop]
    EUR44.69  CDG→LYS  14:42 → 15:49  (1h07m)  British Airways  [Non-stop]
    ...
### 🚆 Trains
  🚆 TGV INOUI  06:20 → 08:34  2h14m  (direct)
  🚆 TGV INOUI  07:00 → 09:10  2h10m  (direct)
  ...
### 🚌 Buses
  Direct FlixBus options ...

[skill answered in 4.5s — no LLM used]
```

Three modes fired in parallel through the regex fast-path,
no LLM round-trip. For free-text queries the LLM takes over with the
travel skill loaded on demand.

## License

Our code: MIT. Vendor MCPs under `MCP/flights-mcp/` and `MCP/flixbus-mcp/`
retain their upstream licenses.
