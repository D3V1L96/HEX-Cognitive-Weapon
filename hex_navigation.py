import requests
import webbrowser
import urllib.parse
import logging
import re
import time
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

logging.basicConfig(level=logging.INFO, format='[Nav] %(message)s')
logger = logging.getLogger(__name__)


class HexNavigation:
    """
    Fully Dynamic Navigation Engine.
    No predefined categories. Any query → Navigate.
    OSRM routing + Nominatim geocoding. 100% Free.
    """

    OSRM_ROUTE_URL = "https://router.project-osrm.org/route/v1/driving/"
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

    # Words to strip from voice commands to extract pure destination
    NAV_TRIGGERS = [
        "navigate to", "go to", "route to", "take me to",
        "directions to", "find route to", "drive to",
        "navigate from", "route from", "fly to",
        "walk to", "ride to", "head to",
    ]

    NEARBY_TRIGGERS = [
        "nearest", "closest", "nearby", "near me",
        "find nearest", "find closest", "find nearby",
    ]

    NOISE_WORDS = [
        "please", "can you", "could you", "will you",
        "i want to go to", "i need to go to", "let's go to",
        "show me", "help me find", "search for",
        "the", "a", "an", "my", "our",
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "HEX-Supersense/2.0 (DarkDevil; tilak@hex.local)"
        })
        self.geolocator = Nominatim(user_agent="hex-supersense-nav")
        self._user_location_cache = None
        logger.info("HEX Navigation Ready | Dynamic Query | OSRM + Nominatim")

    # ==================== GEOCODING ====================

    def _geocode(self, query):
        """Convert any place name/address to coordinates."""
        try:
            location = self.geolocator.geocode(query, timeout=10)
            if location:
                logger.info(f"Geocoded '{query}' → {location.latitude:.4f}, {location.longitude:.4f}")
                return {
                    "lat": location.latitude,
                    "lon": location.longitude,
                    "display_name": location.address
                }
        except GeocoderTimedOut:
            logger.warning(f"Geocoding timeout: {query}")
        except GeocoderServiceError as e:
            logger.warning(f"Geocoding service error: {e}")
        except Exception as e:
            logger.error(f"Geocoding failed: {e}")
        return None

    # ==================== USER LOCATION ====================

    def _get_user_location(self):
        """Get user location via IP or cached value."""
        if self._user_location_cache:
            return self._user_location_cache

        try:
            resp = self.session.get("https://ipapi.co/json/", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                loc = {
                    "lat": float(data.get("latitude", 28.6139)),
                    "lon": float(data.get("longitude", 77.2090)),
                    "city": data.get("city", "Unknown"),
                    "source": "ip"
                }
                self._user_location_cache = loc
                logger.info(f"Location via IP: {loc['city']}")
                return loc
        except Exception as e:
            logger.debug(f"IP geolocation failed: {e}")

        fallback = {"lat": 28.6139, "lon": 77.2090, "city": "Delhi", "source": "default"}
        self._user_location_cache = fallback
        return fallback

    def set_user_location(self, lat, lon):
        """Manually override user location."""
        self._user_location_cache = {
            "lat": lat, "lon": lon, "city": "Manual", "source": "manual"
        }

    # ==================== ROUTE CALCULATION ====================

    def _calculate_route(self, start_lon, start_lat, end_lon, end_lat):
        """Calculate best driving route via OSRM."""
        try:
            url = f"{self.OSRM_ROUTE_URL}{start_lon},{start_lat};{end_lon},{end_lat}"
            params = {"overview": "false", "geometries": "polyline", "steps": "true"}
            resp = self.session.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return None

            data = resp.json()
            routes = data.get("routes", [])
            if not routes:
                return None

            route = routes[0]
            distance_m = route.get("distance", 0)
            duration_s = route.get("duration", 0)

            return {
                "distance_km": round(distance_m / 1000, 1),
                "duration_min": round(duration_s / 60, 1),
                "duration_hr_min": f"{int(duration_s // 3600)}h {int((duration_s % 3600) // 60)}m",
            }
        except Exception as e:
            logger.error(f"Route calculation failed: {e}")
            return None

    # ==================== MAP LAUNCHER ====================

    def _open_in_maps(self, dest_lat, dest_lon, src_lat=None, src_lon=None):
        """Open turn-by-turn navigation in Google Maps."""
        try:
            if src_lat and src_lon:
                url = f"https://www.google.com/maps/dir/{src_lat},{src_lon}/{dest_lat},{dest_lon}"
            else:
                url = f"https://www.google.com/maps/dir/{dest_lat},{dest_lon}"
            webbrowser.open(url)
            return True
        except Exception as e:
            logger.error(f"Failed to open maps: {e}")
            return False

    # ==================== DYNAMIC QUERY PARSER ====================

    def parse_command(self, text):
        """
        Extract destination from ANY voice command dynamically.
        No predefined categories. Pure NLP extraction.
        Returns: dict with action, destination, source or None
        """
        if not text or not text.strip():
            return None

        t = text.lower().strip()

        # Detect action type
        is_nearby = any(trig in t for trig in self.NEARBY_TRIGGERS)
        is_navigate = any(trig in t for trig in self.NAV_TRIGGERS)

        if not is_nearby and not is_navigate:
            return None

        # Extract source (from X)
        source = None
        if "from" in t:
            from_parts = t.split("from")
            if len(from_parts) >= 2:
                source_raw = from_parts[-1].strip()
                # Remove trailing triggers
                for trig in self.NAV_TRIGGERS + self.NEARBY_TRIGGERS:
                    source_raw = source_raw.replace(trig, "")
                source = source_raw.strip()
                if source:
                    t = from_parts[0].strip()

        # Extract destination by removing all trigger/noise words
        dest = t
        for trig in self.NAV_TRIGGERS + self.NEARBY_TRIGGERS:
            dest = dest.replace(trig, " ")
        for noise in self.NOISE_WORDS:
            dest = re.sub(r'\b' + re.escape(noise) + r'\b', ' ', dest)

        # Clean up
        dest = re.sub(r'\s+', ' ', dest).strip()
        # Remove trailing punctuation
        dest = dest.rstrip('.,!?;:')

        if not dest:
            return None

        return {
            "action": "nearby" if is_nearby else "navigate",
            "destination": dest,
            "source": source,
        }

    # ==================== NAVIGATE TO ANYTHING ====================

    def navigate_to(self, destination_query, from_location=None):
        """Navigate to any destination. Fully dynamic."""
        if not destination_query or not destination_query.strip():
            return "Where do you want to go, Sir?"

        # Geocode destination
        dest = self._geocode(destination_query)
        if not dest:
            return f"Could not locate '{destination_query}', Sir. Try a more specific name or address."

        # Get source
        if from_location:
            src = self._geocode(from_location)
            if not src:
                src = self._get_user_location()
        else:
            src = self._get_user_location()

        # Calculate route
        route = self._calculate_route(
            src["lon"], src["lat"],
            dest["lon"], dest["lat"]
        )

        # Open maps
        self._open_in_maps(
            dest["lat"], dest["lon"],
            src.get("lat"), src.get("lon")
        )

        # Build response
        place_name = dest["display_name"].split(",")[0].strip()
        if route:
            return (
                f"Route to {place_name}, Sir. "
                f"{route['distance_km']} kilometers, approximately {route['duration_hr_min']}. "
                f"Navigation opened, Sir."
            )
        return f"Navigating to {place_name}, Sir. Maps opened with directions."

    # ==================== FIND NEAREST ANYTHING ====================

    def find_nearest(self, query):
        """Find nearest of ANYTHING. No predefined list."""
        if not query or not query.strip():
            return "Nearest what, Sir?"

        user_loc = self._get_user_location()

        try:
            params = {
                "q": query,
                "lat": user_loc["lat"],
                "lon": user_loc["lon"],
                "limit": 5,
                "format": "json",
                "addressdetails": 1,
            }
            resp = self.session.get(self.NOMINATIM_URL, params=params, timeout=10)
            if resp.status_code != 200:
                return f"Search failed for '{query}', Sir."

            results = resp.json()
            if not results:
                return f"No '{query}' found near your location, Sir."

            # Pick best result (first = most relevant)
            nearest = results[0]
            name = nearest.get("name", nearest.get("display_name", query))
            display_name = name.split(",")[0].strip()

            # Calculate distance from user
            dest_lat = float(nearest.get("lat", 0))
            dest_lon = float(nearest.get("lon", 0))

            # Simple haversine distance
            dist_km = self._haversine(
                user_loc["lat"], user_loc["lon"],
                dest_lat, dest_lon
            )

            # Navigate to it
            route = self._calculate_route(
                user_loc["lon"], user_loc["lat"],
                dest_lon, dest_lat
            )

            self._open_in_maps(dest_lat, dest_lon, user_loc["lat"], user_loc["lon"])

            if route:
                return (
                    f"Nearest {display_name} is {dist_km:.1f} kilometers away, Sir. "
                    f"Estimated travel time: {route['duration_hr_min']}. "
                    f"Navigation opened, Sir."
                )
            return f"Nearest {display_name} found {dist_km:.1f} km away. Navigation opened, Sir."

        except Exception as e:
            logger.error(f"Nearest search failed: {e}")
            return f"Could not find nearest {query}, Sir."

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2):
        """Calculate distance between two points in km."""
        import math
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return round(R * c, 1)

    # ==================== MASTER DISPATCH ====================

    def handle(self, voice_text):
        """Single entry point. Parse → Execute → Return response."""
        parsed = self.parse_command(voice_text)
        if not parsed:
            return None  # Not a navigation command

        if parsed["action"] == "nearby":
            return self.find_nearest(parsed["destination"])
        else:
            return self.navigate_to(parsed["destination"], parsed.get("source"))


# Singleton
hex_nav = HexNavigation()