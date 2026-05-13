# skills/

Markdown files in this folder are **on-demand skills** — focused
instruction packs the LLM loads via the `load_skill` tool when it
detects a relevant query, instead of carrying everything in the
base system prompt.

## Why

The base system prompt only needs ~600 bytes of generic guardrails. The
detailed routing rules (IATA tables, mode-specific tool sequences,
worked examples) used to live there too, costing ~6 KB on every turn.
Now they live here and are loaded only when needed.

Net effect:
- Non-travel queries (calculator, time, web_search, file_read…) pay no
  travel-prompt cost at all.
- Travel queries pay the cost once — when the LLM calls
  `load_skill(name='travel')` — instead of every turn.

## Adding a skill

Drop a `<name>.md` file here. The first call to
`load_skill(name='<name>')` will return its contents. Skill files can
reference each other (e.g., a smaller `flights.md` could be loaded
independently when only flights are needed).

Currently available:
- **`travel.md`** — full routing rules for the 3 transport MCPs
  (flights / trains / buses / "plan" multi-mode).
