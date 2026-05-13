from __future__ import annotations

import ast
import operator as op
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from langchain_core.tools import tool



_BIN_OPS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
            ast.Div: op.truediv, ast.FloorDiv: op.floordiv,
            ast.Mod: op.mod, ast.Pow: op.pow}
_UNARY_OPS = {ast.UAdd: op.pos, ast.USub: op.neg}


def _safe_eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Only arithmetic on numeric literals is allowed.")


@tool
def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression. Supports + - * / // % ** and parentheses. No variables or function calls."""
    return str(_safe_eval(ast.parse(expression, mode="eval").body))


@tool
def current_time(timezone_name: str = "UTC") -> str:
    """Get the current date and time in an IANA timezone (default UTC)."""
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        return f"Unknown timezone: {timezone_name!r}."
    return datetime.now(tz).isoformat(timespec="seconds")


@tool
def file_read(path: str, max_bytes: int = 20000) -> str:
    """Read a UTF-8 text file from the local filesystem (truncated to ~20KB)."""
    p = Path(path).expanduser()
    if not p.exists():
        return f"File not found: {p}"
    if not p.is_file():
        return f"Not a regular file: {p}"
    return p.read_bytes()[:max_bytes].decode("utf-8", errors="replace")


@tool
def web_search(query: str, max_results: int = 5, region: str = "wt-wt") -> str:
    """Search the web via DuckDuckGo. Returns title, URL, snippet for each result.

    🛑 DO NOT USE FOR TRANSPORT QUERIES. Flights, trains, and buses have
    dedicated tools that return REAL live data:
      • Flights → use `search_flights` (Duffel-backed, real prices + times)
      • Trains  → use `plan_journey_by_city_names` (SNCF/Navitia, French stations)
      • Buses   → use `search_locations` + `search_trips` (FlixBus, real schedules)
    Calling web_search for those questions returns vague summaries when
    the real tool would return an actual offer list with prices.

    USE THIS ONLY FOR: hotels, attractions, restaurants, visa info, weather,
    news, and other non-transport questions.

    Args:
        query: search keywords
        max_results: how many results to return (default 5, max ~10 useful)
        region: DDG region code, e.g. 'wt-wt' (worldwide), 'us-en', 'cn-zh'
    """
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

    last_error = None
    for attempt in range(3):
        try:
            with DDGS(timeout=15) as ddgs:
                results = list(ddgs.text(query, region=region, max_results=max_results))
            if not results:
                return f"No results for {query!r}. Try different keywords or check spelling."
            rows = []
            for i, r in enumerate(results, 1):
                rows.append(
                    f"{i}. {r.get('title') or '(untitled)'}\n"
                    f"   URL: {r.get('href') or '(no url)'}\n"
                    f"   {r.get('body') or '(no snippet)'}"
                )
            return "\n\n".join(rows)
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)  # 1s, 2s

    return (
        f"web_search failed after 3 attempts: {type(last_error).__name__}: {last_error}. "
        "DuckDuckGo may be rate-limiting your IP — wait a minute and retry, "
        "or rephrase the query."
    )


@tool
def web_fetch(url: str, max_chars: int = 8000) -> str:
    """Fetch a web page and return its main text content (cleaned and truncated).

    🛑 DO NOT USE FOR FLIGHTS / TRAINS / BUSES — same rule as web_search above.
    Those have dedicated tools (`search_flights`, `plan_journey_by_city_names`,
    `search_trips`). Use this for hotel/attraction/visa/news pages only.

    Use after web_search when you need the actual content of a page (article
    text, documentation, README), not just a search snippet. Strips
    navigation, ads, scripts — returns just the article body.

    Limitations:
    - SPAs (sites that need JavaScript) return little or no content
    - Paywalled / login-required pages return their landing/teaser only
    - Very large pages are truncated; pass a smaller `max_chars` if you need the head only

    Args:
        url: full URL starting with http:// or https://
        max_chars: maximum characters to return (default 8000)
    """
    if not url.startswith(("http://", "https://")):
        return f"Invalid URL {url!r}: must start with http:// or https://"

    try:
        import trafilatura
    except ImportError:
        return (
            "web_fetch requires the 'trafilatura' package. "
            "Install it with: pip install trafilatura"
        )

    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return (
                f"Could not fetch {url} — likely network error, DNS failure, or "
                "the server blocked the request (403/robots)."
            )
        text = trafilatura.extract(
            downloaded,
            include_links=False,
            include_images=False,
            include_tables=True,
            output_format="txt",
        )
        if not text or not text.strip():
            return (
                f"Fetched {url} but extracted no text. The page is likely a "
                "JavaScript SPA, paywall, or has no main article content."
            )
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[...truncated at {max_chars} chars; total was {len(text)}]"
        return text
    except Exception as exc:
        return f"web_fetch error for {url}: {type(exc).__name__}: {exc}"

@tool
def load_skill(name: str) -> str:
    """Load a skill — a focused instruction pack for a specific domain.

    Skills live as Markdown files in the project's `skills/` folder and
    are loaded on demand instead of being baked into the base system
    prompt. Call this when a query enters a skill's domain.

    Currently available skills:
      • `travel` — flights / trains / buses routing rules, IATA codes,
                   multi-mode "plan" call patterns. Load whenever the
                   user asks about flights, trains, buses, "plan",
                   "trip", "from X to Y", "how to get to Y".

    Args:
        name: skill identifier (filename without `.md`).

    Returns:
        The skill file's full markdown content as a string. The model
        should treat the returned text as authoritative instructions
        for the duration of the relevant conversation.
    """
    from pathlib import Path
    skills_dir = Path(__file__).parent.parent / "skills"
    skill_file = skills_dir / f"{name}.md"
    if not skill_file.exists():
        available = sorted(f.stem for f in skills_dir.glob("*.md") if f.stem != "README")
        return (f"Error: skill {name!r} not found. "
                f"Available skills: {available}")
    return skill_file.read_text(encoding="utf-8")


from MCP.mcp_servers import get_mcp_tools  # noqa: E402


def mcp_tools():
    """Return tools coming from external MCP servers.

    Travel stack: flights-mcp (Duffel), mcp-sncf (Navitia trains),
    flixbus-mcp (FlixBus buses). Plus optional Brave Search / Google Maps.
    All configured in MCP/mcp_servers.py — each server is included only if
    its env vars are present, so missing keys just skip cleanly.
    """
    return get_mcp_tools()


# Generic tools live in this file; transport tools come from the external
# MCP servers via `mcp_tools()`. The splat flattens the returned list so
# individual MCP tools land in TOOLS by their own names (search_flights,
# plan_journey_by_city_names, search_trips, etc.).
TOOLS = [
    calculator,
    current_time,
    file_read,
    web_search,
    web_fetch,
    load_skill,
    *mcp_tools(),
]