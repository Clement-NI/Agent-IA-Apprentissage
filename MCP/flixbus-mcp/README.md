# FlixBus MCP Server

A Model Context Protocol (MCP) server that provides access to the FlixBus API for searching bus routes, schedules, and station information across Europe.

## Features

- **Location Search**: Find FlixBus stations and cities by name
- **Trip Search**: Search for bus trips between locations with prices and schedules
- **Station Timetables**: Get departure/arrival information for specific stations

## Setup

### 1. Get API Access

1. **Sign up for RapidAPI** at [https://rapidapi.com](https://rapidapi.com)
2. **Subscribe to the FlixBus API** at [https://rapidapi.com/3b-data-3b-data-default/api/flixbus2](https://rapidapi.com/3b-data-3b-data-default/api/flixbus2)
3. **Get your RapidAPI Key** from your dashboard

### 2. Install the MCP Server

1. Clone or download this repository to your local machine
2. Set up your RapidAPI key in `.env`:
```
RAPID_API_KEY=your_rapidapi_key_here
```

### 3. Test the Server (Optional)

Run the server directly to test:
```bash
uv run python server.py
```

## Claude Desktop Configuration

### 4. Configure Claude Desktop

Add this to your Claude Desktop `claude_desktop_config.json` file:

```json
{
  "mcpServers": {
    "flixbus": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/your/flixbus-mcp",
        "python",
        "server.py"
      ],
      "env": {
        "RAPID_API_KEY": "your_rapidapi_key_here"
      }
    }
  }
}
```

**Important:** 
- Replace `/path/to/your/flixbus-mcp` with the actual path to where you downloaded this repository
- Replace `your_rapidapi_key_here` with your actual RapidAPI key
- Restart Claude Desktop after making changes

## Available Tools

### search_locations(query: str, locale: str)
Search for FlixBus stations or cities by name.
- **query**: Search term (e.g., "Berlin", "Paris", "London")
- **locale**: Language locale (optional, default: "en")

### search_trips(from_id, to_id, date, ...)
Search for trips between two locations.
- **from_id**: Origin station/city ID
- **to_id**: Destination station/city ID  
- **date**: Travel date in DD.MM.YYYY format
- **adult**: Number of adults (optional, default: 1)
- **children**: Number of children (optional, default: 0)
- **bikes**: Number of bikes (optional, default: 0)
- **currency**: Price currency (optional, default: "EUR")
- **search_by**: Search by "cities" or "stations" (optional, default: "cities")
- **locale**: Language locale (optional, default: "en")

### get_station_timetable(station_id: str, date: str)
Get timetable for a specific station.
- **station_id**: Station ID from search_locations
- **date**: Date in DD.MM.YYYY format


## Usage Example

1. First, search for locations:
```
search_locations("Berlin")
```

2. Then search for trips using the location IDs:
```
search_trips("location_id_1", "location_id_2", "25.12.2024")
```

## API Source

This server uses the FlixBus API available on RapidAPI:
https://rapidapi.com/3b-data-3b-data-default/api/flixbus2/