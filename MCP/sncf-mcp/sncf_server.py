"""Minimal SNCF MCP server — direct SNCF Open Data API client.

Replaces `Kryzo/mcp-sncf` (whose CSV-based station lookup was broken: it
used CSV row numbers as SNCF station IDs, and the 11-station hardcoded
fallback had several swapped/wrong IDs — see git history for details).

This server queries SNCF's `/places` and `/journeys` endpoints directly,
so any city or station SNCF knows about (~3000+ French stations plus
cross-border destinations like Barcelona, Brussels, Geneva, Frankfurt)
just works without any local data file or hardcoded ID list.

Setup:
    pip install mcp httpx
    export SNCF_API_TOKEN=...    # free key: https://numerique.sncf.com/startup/api

Run as standalone (for debugging):
    python MCP/sncf_server.py

Run as part of the agent: auto-launched by MCP/mcp_servers.py when
SNCF_API_TOKEN is set.
"""
from __future__ import annotations

import os
from datetime import date as _date, datetime as _dt
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

API_BASE = "https://api.sncf.com/v1"
TIMEOUT = 20

server = FastMCP("sncf")

# Cache resolved place IDs across tool calls — /places is the slowest leg.
_id_cache: dict[str, Optional[str]] = {}


def _token() -> str:
    t = os.environ.get("SNCF_API_TOKEN")
    if not t:
        raise RuntimeError("SNCF_API_TOKEN not set in environment.")
    return t


def _resolve_place(name: str) -> Optional[str]:
    """Resolve a city/station name to a SNCF stop_area or admin_region ID.

    Disambiguation order:
      1. stop_area whose "(City)" parenthetical exactly matches the query
         — handles "Lyon Perrache (Lyon)" vs "Paris - Gare de Lyon"
      2. stop_area whose name starts with the query
      3. administrative_region matching the query (city-level — preferred
         for routing, SNCF picks the right departure station per route)
      4. any stop_area (last-resort fallback)

    Empty/unresolvable names return None.
    """
    key = name.strip().lower()
    if not key:
        return None
    if key in _id_cache:
        return _id_cache[key]

    try:
        r = httpx.get(
            f"{API_BASE}/coverage/sncf/places",
            auth=(_token(), ""),
            params={"q": name, "count": 10},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
    except httpx.HTTPError:
        _id_cache[key] = None
        return None

    places = r.json().get("places", [])

    def _save(pid: Optional[str]) -> Optional[str]:
        _id_cache[key] = pid
        return pid

    # Pass 1 — stop_area with matching (City) parenthetical
    for p in places:
        if p.get("embedded_type") != "stop_area":
            continue
        n = p.get("name", "")
        if "(" in n and n.rstrip().endswith(")"):
            city = n[n.rfind("(") + 1 : n.rfind(")")].strip().lower()
            if city == key:
                return _save(p["id"])

    # Pass 2 — stop_area whose name starts with the query
    for p in places:
        if p.get("embedded_type") == "stop_area" and p.get("name", "").lower().startswith(key):
            return _save(p["id"])

    # Pass 3 — administrative_region (city-level, SNCF auto-routes)
    for p in places:
        if p.get("embedded_type") in {"administrative_region", "address"}:
            return _save(p["id"])

    # Pass 4 — any stop_area
    for p in places:
        if p.get("embedded_type") == "stop_area":
            return _save(p["id"])

    return _save(None)


def _parse_date(s: str) -> Optional[_date]:
    if not s or not s.strip():
        return _date.today()
    try:
        return _date.fromisoformat(s.strip())
    except ValueError:
        return None


def _format_journey(j: dict) -> str:
    """Compact one-line summary of one journey for the agent's response."""
    dep_dt = j.get("departure_date_time", "")
    arr_dt = j.get("arrival_date_time", "")
    dep_t = f"{dep_dt[9:11]}:{dep_dt[11:13]}" if len(dep_dt) >= 13 else "?"
    arr_t = f"{arr_dt[9:11]}:{arr_dt[11:13]}" if len(arr_dt) >= 13 else "?"

    dur_min = j.get("duration", 0) // 60
    h, m = divmod(dur_min, 60)

    n_transfers = j.get("nb_transfers", 0)
    transfer_label = "direct" if n_transfers == 0 else f"{n_transfers} transfer(s)"

    # Identify primary train brand (TGV INOUI / OUIGO / Intercités / TER / ...)
    train_label = ""
    for sec in j.get("sections", []):
        if sec.get("type") == "public_transport":
            train_label = sec.get("display_informations", {}).get("commercial_mode", "")
            break
    if not train_label:
        train_label = "Train"

    return f"  🚆 {train_label:14s} {dep_t} → {arr_t}  {h}h{m:02d}m  ({transfer_label})"


@server.tool()
def plan_train_journey(
    from_city: str,
    to_city: str,
    departure_date: str = "",
    count: int = 6,
) -> str:
    """Plan train journeys between two cities via SNCF Open Data.

    Args:
        from_city: Origin city or station in plain text — "Paris", "Bordeaux",
                   "Lyon", "Lille Europe", "Barcelona", etc. SNCF resolves
                   city names to the appropriate departure station for the
                   route (Paris→Bordeaux auto-picks Montparnasse,
                   Paris→Lyon auto-picks Gare de Lyon, etc.).
        to_city:   Destination, same format.
        departure_date: ISO date YYYY-MM-DD. Empty means today. The SNCF
                        Open Data API has a ~3-week forward window — beyond
                        that, you'll get a "date_out_of_bounds" message.
        count:     Max journeys to return (default 6).

    Returns:
        Formatted list of journeys with train brand, departure/arrival
        times, duration, and transfer count. Or an explicit error line if
        either city can't be resolved or the date is out of range.

    Coverage:
        All ~3000 French stations + cross-border services to Barcelona,
        Brussels, Geneva, Frankfurt, Milan, Turin. No local data files —
        if SNCF's API knows about it, this tool finds it.
    """
    parsed = _parse_date(departure_date)
    if parsed is None:
        return (f"Error: departure_date {departure_date!r} is not in "
                f"YYYY-MM-DD format. Retry with e.g. '{_date.today().isoformat()}'.")

    today = _date.today()
    if parsed < today:
        return (f"Error: departure_date {parsed.isoformat()} is in the past. "
                f"Today is {today.isoformat()}. Use a date today or later.")

    origin_id = _resolve_place(from_city)
    if not origin_id:
        return f"Error: origin {from_city!r} not found in SNCF places."
    dest_id = _resolve_place(to_city)
    if not dest_id:
        return f"Error: destination {to_city!r} not found in SNCF places."

    # SNCF datetime format: YYYYMMDDTHHMMSS — anchor at 06:00 to catch a
    # full day of departures.
    dt = parsed.strftime("%Y%m%dT060000")

    try:
        r = httpx.get(
            f"{API_BASE}/coverage/sncf/journeys",
            auth=(_token(), ""),
            params={"from": origin_id, "to": dest_id, "datetime": dt,
                    "count": max(1, min(count, 15))},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as exc:
        return f"SNCF network error: {type(exc).__name__}: {exc}"

    if r.status_code == 404:
        try:
            err_id = (r.json().get("error") or {}).get("id", "")
        except Exception:
            err_id = ""
        if err_id == "date_out_of_bounds":
            return (f"SNCF dataset doesn't extend to {parsed.isoformat()} — "
                    f"the Open Data API only has ~3 weeks of forward data.")
        return (f"No journeys found from {from_city} to {to_city} "
                f"on {parsed.isoformat()}.")

    if r.status_code != 200:
        return f"SNCF HTTP {r.status_code}: {r.text[:300]}"

    journeys = r.json().get("journeys", [])
    if not journeys:
        return (f"No journeys found from {from_city} to {to_city} "
                f"on {parsed.isoformat()}.")

    header = (f"🚆 {from_city.title()} → {to_city.title()} on "
              f"{parsed.isoformat()} — {len(journeys)} train option(s):")
    lines = [_format_journey(j) for j in journeys]
    note = ("\n\nNote: SNCF Open Data doesn't return ticket prices — use "
            "web_search for fare estimates if needed.")
    return header + "\n" + "\n".join(lines) + note


@server.tool()
def find_train_station(query: str, count: int = 5) -> str:
    """Free-text search of SNCF station names.

    Useful when the user isn't sure of the exact station name, or wants
    to see what stations a city has. Returns up to `count` matches with
    name + SNCF stop_area ID + parent administrative_region.

    Args:
        query: search text — e.g. "Lyon", "Paris Montparnasse", "Gare du Nord"
        count: max results (default 5)
    """
    if not query.strip():
        return "Error: empty query."

    try:
        r = httpx.get(
            f"{API_BASE}/coverage/sncf/places",
            auth=(_token(), ""),
            params={"q": query, "count": max(1, min(count, 15))},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        return f"SNCF network error: {type(exc).__name__}: {exc}"

    places = r.json().get("places", [])
    if not places:
        return f"No SNCF places matched {query!r}."

    rows = [f"Top {len(places)} match(es) for {query!r}:"]
    for p in places:
        kind = p.get("embedded_type", "?")
        name = p.get("name", "?")
        pid = p.get("id", "?")
        rows.append(f"  [{kind:18s}] {name:50s}  id={pid}")
    return "\n".join(rows)


if __name__ == "__main__":
    # stdio transport: read MCP requests from stdin, write responses to stdout.
    server.run()
