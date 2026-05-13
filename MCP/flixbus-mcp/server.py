#!/usr/bin/env python3

import os
import requests
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

mcp = FastMCP("FlixBus Travel Assistant")

RAPIDAPI_KEY = os.getenv("RAPID_API_KEY")
BASE_URL = "https://flixbus2.p.rapidapi.com"

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "flixbus2.p.rapidapi.com"
}

@mcp.tool
def search_locations(query: str, locale: str = "en") -> List[Dict[str, Any]]:
    """
    Search for FlixBus stations or cities by name.
    
    Args:
        query: Search term (e.g., "Berlin", "Paris", "London")
        locale: Language locale (default: "en")
    
    Returns:
        List of matching locations with station IDs in the 'id' field.
        Use these station IDs with the search_trips function.
    """
    try:
        url = f"{BASE_URL}/autocomplete"
        params = {"query": query, "locale": locale}
        
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        
        locations = response.json()
        
        # Format the response for better readability
        formatted_locations = []
        for loc in locations:
            formatted_locations.append({
                "id": loc.get("id"),
                "name": loc.get("name"),
                "city": loc.get("city", {}).get("name"),
                "country": loc.get("country", {}).get("name"),
                "country_code": loc.get("country", {}).get("code"),
                "coordinates": {
                    "lat": loc.get("location", {}).get("lat"),
                    "lon": loc.get("location", {}).get("lon")
                },
                "address": loc.get("address"),
                "is_train": loc.get("is_train", False),
                "importance": loc.get("importance_order", 0)
            })
        
        return formatted_locations
        
    except requests.RequestException as e:
        return [{"error": f"API request failed: {str(e)}"}]
    except Exception as e:
        return [{"error": f"Unexpected error: {str(e)}"}]

@mcp.tool
def search_trips(
    from_id: str,
    to_id: str,
    date: str,
    adult: int = 1,
    children: int = 0,
    bikes: int = 0,
    currency: str = "EUR",
    search_by: str = "stations",
    locale: str = "en"
) -> Dict[str, Any]:
    """
    Search for FlixBus trips between two locations.
    
    Note: Station-based searches are more reliable than city-based searches. 
    Use search_by: 'stations' with station IDs from search_locations for best results.
    
    Args:
        from_id: Origin station ID (get from search_locations)
        to_id: Destination station ID (get from search_locations)
        date: Travel date in DD.MM.YYYY format (e.g., "25.12.2024")
        adult: Number of adult passengers (default: 1)
        children: Number of children (default: 0)
        bikes: Number of bikes (default: 0)
        currency: Price currency (default: "EUR")
        search_by: Search by "cities" or "stations" (default: "stations")
        locale: Language locale (default: "en")
    
    Returns:
        Dictionary containing trip options with prices, duration, and booking links.
        
        RECOMMENDED APPROACH:
        - Use search_by: 'stations' with the 'id' field from search_locations results
        - This provides reliable, direct route information from specific departure points
        
        ALTERNATIVE APPROACH:
        - search_by: 'cities' can be attempted but may return null/empty journey data
        - Still use station IDs from search_locations - the API attempts city-level interpretation
    """
    try:
        url = f"{BASE_URL}/trips"
        params = {
            "from_id": from_id,
            "to_id": to_id,
            "date": date,
            "adult": adult,
            "children": children,
            "bikes": bikes,
            "currency": currency,
            "search_by": search_by,
            "locale": locale
        }
        
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        # Format the response for better readability
        if "journeys" in data:
            formatted_journeys = []
            for journey in data["journeys"]:
                formatted_journeys.append({
                    "departure_time": journey.get("dep_offset"),
                    "arrival_time": journey.get("arr_offset"),
                    "departure_station": journey.get("dep_name"),
                    "arrival_station": journey.get("arr_name"),
                    "duration": journey.get("duration"),
                    "changeovers": journey.get("changeovers", 0),
                    "price": journey.get("fares", [{}])[0].get("price") if journey.get("fares") else None,
                    "currency": journey.get("fares", [{}])[0].get("currency") if journey.get("fares") else currency,
                    "booking_link": journey.get("deeplink"),
                    "segments": journey.get("segments", [])
                })
            
            return {
                "search_info": {
                    "response_time_ms": data.get("headers", {}).get("response_time"),
                    "timestamp": data.get("headers", {}).get("response_timestamp")
                },
                "journeys": formatted_journeys,
                "total_results": len(formatted_journeys)
            }
        else:
            return {"error": "No journeys found", "raw_response": data}
            
    except requests.RequestException as e:
        return {"error": f"API request failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}

@mcp.tool
def get_station_timetable(station_id: str, date: str) -> Dict[str, Any]:
    """
    Get the timetable for a specific FlixBus station.
    
    Args:
        station_id: Station ID (get from search_locations)
        date: Date in DD.MM.YYYY format (e.g., "25.12.2024")
    
    Returns:
        Dictionary containing departures and arrivals for the station on the given date
    """
    try:
        url = f"{BASE_URL}/schedule"
        params = {
            "station_id": station_id,
            "date": date
        }
        
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        if "schedule" in data:
            station_info = data["schedule"].get("station", {})
            departures = data["schedule"].get("departures", [])
            arrivals = data["schedule"].get("arrivals", [])
            
            # Format departures
            formatted_departures = []
            for dep in departures:
                formatted_departures.append({
                    "time": dep.get("time"),
                    "delay": dep.get("delay", 0),
                    "cancelled": dep.get("is_cancelled", False),
                    "line_code": dep.get("line_code"),
                    "destination": dep.get("direction"),
                    "stops": [stop.get("name") for stop in dep.get("stops", [])]
                })
            
            # Format arrivals
            formatted_arrivals = []
            for arr in arrivals:
                formatted_arrivals.append({
                    "time": arr.get("time"),
                    "delay": arr.get("delay", 0),
                    "cancelled": arr.get("is_cancelled", False),
                    "line_code": arr.get("line_code"),
                    "origin": arr.get("direction"),
                    "stops": [stop.get("name") for stop in arr.get("stops", [])]
                })
            
            return {
                "station": {
                    "name": station_info.get("name"),
                    "description": station_info.get("description"),
                    "coordinates": {
                        "lat": station_info.get("latitude"),
                        "lon": station_info.get("longitude")
                    },
                    "timezone": station_info.get("timezone")
                },
                "departures": formatted_departures,
                "arrivals": formatted_arrivals,
                "search_info": {
                    "response_time_ms": data.get("headers", {}).get("response_time"),
                    "timestamp": data.get("headers", {}).get("response_timestamp")
                }
            }
        else:
            return {"error": "No timetable data found", "raw_response": data}
            
    except requests.RequestException as e:
        return {"error": f"API request failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


if __name__ == "__main__":
    import sys
    if not RAPIDAPI_KEY:
        print("Error: RAPID_API_KEY not found in environment variables", file=sys.stderr)
        print("Please set your RapidAPI key in the .env file", file=sys.stderr)
        exit(1)

    # Banner goes to stderr — MCP uses stdout exclusively for JSON-RPC,
    # any non-JSON line there makes the client throw `ValidationError`.
    print("FlixBus MCP Server starting...", file=sys.stderr)
    print("Available tools:", file=sys.stderr)
    print("- search_locations: Find FlixBus stations and cities", file=sys.stderr)
    print("- search_trips: Search for trips between locations", file=sys.stderr)
    print("- get_station_timetable: Get timetable for a specific station", file=sys.stderr)

    mcp.run()