# Travel skill

Detailed routing rules for the three transport MCP servers. Load this
skill when the user's query mentions flights, trains, buses, or asks
to "plan" / "get from X to Y".

## The three transport tools

### ✈ FLIGHTS — `search_flights` (Duffel-backed)
```
search_flights(type='one_way', origin=<IATA>, destination=<IATA>,
                departure_date='YYYY-MM-DD')
```
- `origin` / `destination`: **3-letter IATA codes**, never city names.
- `departure_date`: ISO `YYYY-MM-DD`. **Must use the year from
  `current_time`** — don't emit `2024-…` or `2025-…` after current_time
  returned 2026.
- `type`: `one_way` | `round_trip` | `multi_city`. Default `one_way`.

### 🚆 TRAINS — `plan_train_journey` (SNCF Open Data)
```
plan_train_journey(from_city=<city>, to_city=<city>,
                    departure_date='YYYY-MM-DD')
```
- City names in plain English/French. SNCF picks the right departure
  station automatically (`Paris → Bordeaux` uses Montparnasse,
  `Paris → Lyon` uses Gare de Lyon, etc.).
- Coverage: all ~3000 French stations + cross-border services
  (`Paris ↔ Barcelona / Brussels / Geneva / Frankfurt`).
- SNCF Open Data has a ~3-week forward window — beyond that the tool
  returns "dataset doesn't extend that far". Don't retry with a different
  year; just tell the user trains for that date aren't yet bookable.
- Use `find_train_station(query)` to disambiguate a station name first
  if the user gave something ambiguous.

### 🚌 BUSES — FlixBus (RapidAPI)
Two-step call:
```
1. search_locations(query=<origin city>)         → list of stops
2. search_locations(query=<destination city>)    → list of stops
3. search_trips(from_id=<id>, to_id=<id>,
                date='YYYY-MM-DD', adult=1)
```
- From each `search_locations` result list, pick the **highest-
  `importance` non-airport** stop whose `city` matches the requested
  city. Skip entries whose `name` contains "Airport".
- Pass `date` as ISO `YYYY-MM-DD`. The adapter rewrites it to FlixBus's
  required `DD.MM.YYYY` format automatically.

## Mode detection

Decide which of the four modes to run based on the user's keywords:

| Keyword in query | Mode |
|---|---|
| `flight`, `flights`, `fly`, `plane`, `airline` | **FLIGHTS-ONLY** |
| `train`, `trains`, `tgv`, `rail`, `sncf`, `ouigo`, `intercités` | **TRAINS-ONLY** |
| `bus`, `buses`, `coach`, `flixbus` | **BUSES-ONLY** |
| `plan`, `trip`, `options`, `best way`, bare "X to Y" | **ALL MODES** |
| Multiple modes mentioned | **ALL MODES** |

## ALL MODES — call pattern

For the default "plan / trip / X to Y" case, batch the independent
lookups in parallel:

```
TURN 1 — date resolution (1 call):
  • current_time(timezone_name='Europe/Paris')

TURN 2 — fan out (4 PARALLEL calls in one response):
  • search_flights(type='one_way', origin=<IATA>, destination=<IATA>,
                    departure_date='YYYY-MM-DD')
  • plan_train_journey(from_city=<city>, to_city=<city>,
                        departure_date='YYYY-MM-DD')
  • search_locations(query=<origin>)
  • search_locations(query=<destination>)

TURN 3 — bus depends on TURN 2's IDs (1 call):
  • search_trips(from_id=<id>, to_id=<id>, date='YYYY-MM-DD', adult=1)

TURN 4 — compose ONE reply with three sections:
  ### ✈ Flights
  <output of search_flights>
  ### 🚆 Trains
  <output of plan_train_journey>
  ### 🚌 Buses
  <output of search_trips>
```

⛔ Don't stop after one mode succeeded. Even if trains looks great, the
user asked for a plan — show flights and buses too.
⛔ Don't bail on the whole plan because one mode returned an error.
Skip just that section with a one-line note and keep the other two.

## IATA codes (for `search_flights`)

```
Paris=CDG (also ORY), Lyon=LYS, Marseille=MRS, Toulouse=TLS, Nice=NCE,
Bordeaux=BOD, Nantes=NTE, Strasbourg=SXB,
Berlin=BER, Madrid=MAD, Barcelona=BCN, Rome=FCO, Milan=MXP, Naples=NAP,
London=LHR (also LGW, STN), Amsterdam=AMS, Frankfurt=FRA, Munich=MUC,
Brussels=BRU, Vienna=VIE, Zurich=ZRH, Geneva=GVA, Lisbon=LIS, Athens=ATH,
Copenhagen=CPH, Stockholm=ARN, Oslo=OSL, Helsinki=HEL, Dublin=DUB,
Warsaw=WAW, Prague=PRG, Budapest=BUD, Istanbul=IST.
```

For a city not listed: make a best-guess 3-letter code; if
`search_flights` returns an error, report that the city isn't covered.

## Phantom-failure ban

If a tool returned content (a line starting with `Found N flight
offer(s):`, a JSON with `journeys`, a station list, etc.), that tool
**succeeded** — use its data in your reply.

NEVER produce replies like:
- "It seems I cannot directly search for flights at the moment"
- "I recommend checking airline websites instead"

…unless the tool literally returned a line starting with `Error:` or
`error:`. Otherwise paste the data under the appropriate heading.

## Date inference — extract from `current_time`

After calling `current_time`, read its year and use that year for every
`departure_date` argument that follows. If today is `2026-05-12`:

- "May 20" → `2026-05-20`
- "tomorrow" → `2026-05-13`
- "next Monday" → next Monday's date
- "January 5" → `2027-01-05` (already passed this year → bump to next)

Never use a year that didn't come from `current_time`.
