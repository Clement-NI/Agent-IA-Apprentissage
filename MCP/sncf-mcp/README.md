# sncf-mcp

A minimal MCP server that talks directly to SNCF's Open Data API
(`api.sncf.com`). One file, no local database, no static station list.

## Why this exists

Built as a replacement for [`Kryzo/mcp-sncf`](https://github.com/Kryzo/mcp-sncf),
which had two compounding bugs:

1. Its CSV-based station lookup used the CSV row number as the SNCF
   stop_area ID, producing nonsense like `stop_area:SNCF:827` for
   Bordeaux. SNCF API rejected those with HTTP 404.
2. The 11-station hardcoded fallback that masked bug #1 had several
   swapped/wrong IDs — Lyon Part-Dieu / Perrache reversed, Toulouse
   pointing to Montpellier, Aix-en-Provence TGV pointing to Avignon TGV,
   Versailles Rive Droite pointing to Sainte-Geneviève-des-Bois.

Result: working routes were limited to ~5 cities; the rest silently
returned wrong data or "no journey found".

This server instead **resolves every city name dynamically through SNCF's
`/places` endpoint**. Any of the ~3000+ stations SNCF knows about,
including cross-border services (Paris ↔ Barcelona / Brussels / Geneva /
Frankfurt / Milan / Turin), just works — zero config, zero data files.

## Tools exposed

| Tool | Purpose |
|------|---------|
| `plan_train_journey(from_city, to_city, departure_date='', count=6)` | Resolve both cities → call `/journeys` → return up to N options with departure/arrival times, duration, transfer count, and train brand (TGV INOUI / OUIGO / Intercités / TER / BreizhGo / …). |
| `find_train_station(query, count=5)` | Free-text search of SNCF station names. Useful for disambiguating before booking. |

## Setup

```bash
pip install -r requirements.txt
export SNCF_API_TOKEN=...        # free key: https://numerique.sncf.com/startup/api
python sncf_server.py            # speaks MCP over stdio
```

## Claude Desktop config

```json
{
  "sncf": {
    "command": "py",
    "args": ["D:\\MCP-servers\\sncf-mcp\\sncf_server.py"],
    "env": { "SNCF_API_TOKEN": "<your-token>" }
  }
}
```

## Known limitations

- **Forward data window** — the SNCF Open Data API exposes only ~3 weeks
  of forward schedules. Beyond that, `plan_train_journey` returns
  "dataset doesn't extend that far". Not a bug in this server.
- **No prices** — SNCF Open Data doesn't include fares. Use a web
  search tool for fare estimates.
