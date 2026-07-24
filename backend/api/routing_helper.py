import math
import time
import requests
import logging

logger = logging.getLogger(__name__)

# Robust local coordinate fallback database for major US cities
US_CITIES_COORDS = {
    "new york": (40.7128, -74.0060),
    "los angeles": (34.0522, -118.2437),
    "chicago": (41.8781, -87.6298),
    "houston": (29.7604, -95.3698),
    "phoenix": (33.4484, -112.0740),
    "philadelphia": (39.9526, -75.1652),
    "san antonio": (29.4241, -98.4936),
    "san diego": (32.7157, -117.1611),
    "dallas": (32.7767, -96.7970),
    "fort worth": (32.7555, -97.3308),
    "arlington": (32.7357, -97.1081),
    "san jose": (37.3382, -121.8863),
    "austin": (30.2672, -97.7431),
    "jacksonville": (30.3322, -81.6557),
    "columbus": (39.9612, -82.9988),
    "san francisco": (37.7749, -122.4194),
    "charlotte": (35.2271, -80.8431),
    "indianapolis": (39.7684, -86.1581),
    "seattle": (47.6062, -122.3321),
    "denver": (39.7392, -104.9903),
    "washington": (38.9072, -77.0369),
    "boston": (42.3601, -71.0589),
    "el paso": (31.7619, -106.4850),
    "nashville": (36.1627, -86.7816),
    "detroit": (42.3314, -83.0458),
    "portland": (45.5152, -122.6784),
    "las vegas": (36.1716, -115.1398),
    "oklahoma city": (35.4676, -97.5164),
    "memphis": (35.1495, -90.0490),
    "louisville": (38.2527, -85.7585),
    "baltimore": (39.2904, -76.6122),
    "milwaukee": (43.0389, -87.9065),
    "albuquerque": (35.0844, -106.6511),
    "tucson": (32.2226, -110.9747),
    "fresno": (36.7378, -119.7871),
    "sacramento": (38.5816, -121.4944),
    "kansas city": (39.0997, -94.5786),
    "atlanta": (33.7490, -84.3880),
    "miami": (25.7617, -80.1918),
}

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two points on the Earth in miles.
    """
    R = 3958.8  # Earth radius in miles
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def geocode_location(location_name):
    """
    Resolve a location name to (latitude, longitude) using Nominatim,
    with a fallback to local coordinates for major US cities.
    """
    if not location_name or not isinstance(location_name, str):
        raise ValueError("Location name cannot be empty.")

    clean_name = location_name.strip().lower()
    if not clean_name:
        raise ValueError("Location name cannot be empty.")
    if len(clean_name) > 200:
        raise ValueError("Location name is too long.")
    
    # 1. Try local exact match or substring match
    for city, coords in US_CITIES_COORDS.items():
        if city in clean_name or clean_name in city:
            logger.info(f"Geocoded '{location_name}' using local database: {coords}")
            return coords[0], coords[1], city.title()

    # 2. Try Nominatim API
    try:
        url = "https://nominatim.openstreetmap.org/search"
        headers = {
            "User-Agent": "SpotterHOSPlanner/1.0 (fatik@example.com)"
        }
        params = {
            "q": location_name,
            "format": "json",
            "limit": 1
        }
        response = requests.get(url, params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                display_name = data[0]["display_name"].split(",")[0]
                logger.info(f"Geocoded '{location_name}' using Nominatim: {lat}, {lon}")
                return lat, lon, display_name
    except Exception as e:
        logger.warning(f"Nominatim geocoding failed for '{location_name}': {e}")
        
    # 3. Fallback to center of US if geocoding completely fails
    logger.error(f"Failed to geocode '{location_name}'. Using default location.")
    return 39.8283, -98.5795, location_name.strip().title()

def get_route_details(lat1, lon1, lat2, lon2, speed_mph=55.0):
    """
    Retrieve routing details (distance in miles, duration in hours, route geometry)
    using the OSRM routing API, with a fallback to Haversine calculation.
    """
    try:
        url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
        params = {
            "overview": "full",
            "geometries": "geojson"
        }
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and data.get("routes"):
                route = data["routes"][0]
                distance_meters = route["distance"]
                distance_miles = distance_meters * 0.000621371
                
                # We want driving duration based on our speed (or OSRM duration as fallback)
                # OSRM gives duration in seconds, which we convert to hours.
                osrm_duration_hours = route["duration"] / 3600.0
                
                # To be consistent with truck speeds, we calculate driving time using the custom speed_mph
                driving_time_hours = distance_miles / speed_mph
                
                # Extract coordinate path
                coordinates = route["geometry"]["coordinates"]
                # OSRM returns coordinates as [lon, lat], let's convert to [lat, lon] for Leaflet
                route_path = [[coord[1], coord[0]] for coord in coordinates]
                
                logger.info(f"Calculated route using OSRM: {distance_miles:.1f} miles, {driving_time_hours:.2f} hours")
                return {
                    "distance_miles": distance_miles,
                    "driving_time_hours": driving_time_hours,
                    "route_path": route_path
                }
    except Exception as e:
        logger.warning(f"OSRM routing failed: {e}. Falling back to Haversine calculation.")
        
    # Fallback: calculate Haversine distance
    distance_miles = haversine_distance(lat1, lon1, lat2, lon2)
    # Apply a routing factor (typically 1.2) to simulate actual road winding
    estimated_distance_miles = distance_miles * 1.2
    driving_time_hours = estimated_distance_miles / speed_mph
    route_path = [[lat1, lon1], [lat2, lon2]]
    
    return {
        "distance_miles": estimated_distance_miles,
        "driving_time_hours": driving_time_hours,
        "route_path": route_path
    }


_STATE_ABBREVIATIONS = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}


def _state_abbreviation(state_name):
    """Best-effort full state name -> USPS abbreviation; falls back to the input."""
    if not state_name:
        return state_name
    return _STATE_ABBREVIATIONS.get(state_name.strip().lower(), state_name)


_last_nominatim_call = 0.0


def _nominatim_rate_limit():
    """Nominatim's usage policy asks for at most ~1 request/second."""
    global _last_nominatim_call
    elapsed = time.monotonic() - _last_nominatim_call
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    _last_nominatim_call = time.monotonic()


def reverse_geocode(lat, lon):
    """
    Resolve (latitude, longitude) to a human-readable "City, ST" name using
    Nominatim's reverse endpoint, with a fallback to the nearest city in our
    local database if the API is unavailable or the request fails.
    """
    try:
        _nominatim_rate_limit()
        url = "https://nominatim.openstreetmap.org/reverse"
        headers = {
            "User-Agent": "SpotterHOSPlanner/1.0 (fatik@example.com)"
        }
        params = {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "zoom": 12,
        }
        response = requests.get(url, params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            address = data.get("address", {})
            city = (
                address.get("city") or address.get("town")
                or address.get("village") or address.get("hamlet")
                or address.get("county")
            )
            state = address.get("state")
            if city and state:
                result = f"{city}, {_state_abbreviation(state)}"
                logger.info(f"Reverse geocoded ({lat}, {lon}) -> {result}")
                return result
            if city:
                logger.info(f"Reverse geocoded ({lat}, {lon}) -> {city}")
                return city
    except Exception as e:
        logger.warning(f"Reverse geocoding failed for ({lat}, {lon}): {e}")

    # Fallback: nearest city in our local database
    nearest_city, nearest_dist = None, float("inf")
    for city, (city_lat, city_lon) in US_CITIES_COORDS.items():
        dist = haversine_distance(lat, lon, city_lat, city_lon)
        if dist < nearest_dist:
            nearest_city, nearest_dist = city, dist
    if nearest_city:
        logger.info(f"Reverse geocode fallback: nearest known city to ({lat}, {lon}) is {nearest_city}")
        return f"Near {nearest_city.title()}"

    return "En Route"


def search_location_suggestions(query, limit=5):
    """
    Return up to `limit` autocomplete suggestions for a partial location
    string, for use in a search-as-you-type UI.

    Suggestions are assembled from two sources:
      1. The local US_CITIES_COORDS database (instant, no network call) —
         any city whose name starts with or contains the query.
      2. Nominatim's search endpoint, to fill in remaining slots with
         addresses/cities beyond the local list (respecting Nominatim's
         ~1 req/sec usage policy via `_nominatim_rate_limit`).

    Returns a list of dicts: {"display_name": str, "lat": float, "lon": float}.
    Returns an empty list (never raises) if the query is too short or if
    both lookups fail — callers should treat "no suggestions" as normal,
    not an error condition.
    """
    if not query or not isinstance(query, str):
        return []

    clean_query = query.strip()
    if len(clean_query) < 2:
        return []
    if len(clean_query) > 200:
        clean_query = clean_query[:200]

    limit = max(1, min(int(limit), 10)) if isinstance(limit, (int, float)) else 5

    suggestions = []
    seen_names = set()

    # 1. Local database — instant results, prioritize names that start with
    #    the query over ones that merely contain it.
    lower_query = clean_query.lower()
    starts_with = []
    contains = []
    for city, coords in US_CITIES_COORDS.items():
        if city.startswith(lower_query):
            starts_with.append((city, coords))
        elif lower_query in city:
            contains.append((city, coords))

    for city, (lat, lon) in starts_with + contains:
        if len(suggestions) >= limit:
            break
        display_name = city.title()
        if display_name.lower() not in seen_names:
            suggestions.append({"display_name": display_name, "lat": lat, "lon": lon})
            seen_names.add(display_name.lower())

    # 2. Nominatim — fill any remaining slots.
    if len(suggestions) < limit:
        try:
            _nominatim_rate_limit()
            url = "https://nominatim.openstreetmap.org/search"
            headers = {
                "User-Agent": "SpotterHOSPlanner/1.0 (fatik@example.com)"
            }
            params = {
                "q": clean_query,
                "format": "json",
                "limit": limit,
                "countrycodes": "us",
                "addressdetails": 1,
            }
            response = requests.get(url, params=params, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                for item in data:
                    if len(suggestions) >= limit:
                        break
                    try:
                        lat = float(item["lat"])
                        lon = float(item["lon"])
                    except (KeyError, ValueError, TypeError):
                        continue
                    address = item.get("address", {})
                    city = (
                        address.get("city") or address.get("town")
                        or address.get("village") or address.get("hamlet")
                        or address.get("county")
                    )
                    state = address.get("state")
                    if city and state:
                        display_name = f"{city}, {_state_abbreviation(state)}"
                    else:
                        display_name = item.get("display_name", clean_query).split(",")[0]
                    if display_name.lower() not in seen_names:
                        suggestions.append({"display_name": display_name, "lat": lat, "lon": lon})
                        seen_names.add(display_name.lower())
            else:
                logger.warning(f"Nominatim suggestion lookup returned status {response.status_code} for '{clean_query}'")
        except Exception as e:
            logger.warning(f"Nominatim suggestion lookup failed for '{clean_query}': {e}")

    return suggestions


def interpolate_position_along_path(path, target_distance_miles):
    """
    Walk a route_path (list of [lat, lon] points, in travel order) and return
    the (lat, lon) that sits `target_distance_miles` along it, linearly
    interpolating between whichever two points straddle that distance.

    Returns None if `path` is empty. Clamps to the first/last point if
    `target_distance_miles` is outside the path's range.
    """
    if not path:
        return None
    if len(path) == 1 or target_distance_miles <= 0:
        return path[0][0], path[0][1]

    covered = 0.0
    for i in range(1, len(path)):
        lat1, lon1 = path[i - 1]
        lat2, lon2 = path[i]
        seg_dist = haversine_distance(lat1, lon1, lat2, lon2)

        if covered + seg_dist >= target_distance_miles:
            remaining = target_distance_miles - covered
            frac = (remaining / seg_dist) if seg_dist > 0 else 0.0
            lat = lat1 + (lat2 - lat1) * frac
            lon = lon1 + (lon2 - lon1) * frac
            return lat, lon

        covered += seg_dist

    # Requested distance is beyond the path's total length — clamp to the end.
    return path[-1][0], path[-1][1]
