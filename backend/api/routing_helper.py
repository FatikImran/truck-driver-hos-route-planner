import math
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
    if not location_name:
        raise ValueError("Location name cannot be empty.")
    
    clean_name = location_name.strip().lower()
    
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
