from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import webbrowser
import logging
import urllib.parse
import platform
import re
import time
from datetime import datetime, timedelta
from dateutil import parser as date_parser

logging.basicConfig(level=logging.INFO, format='[Travel] %(message)s')
logger = logging.getLogger(__name__)


class HexTravelAgent:
    """Hybrid National & International Travel Intelligence Module."""

    def __init__(self):
        # Global Geolocator
        self.geolocator = Nominatim(user_agent="HEX_Cognitive_Weapon")

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def _get_city_name(self, text):
        """Use NLP/Geopy to find cities globally, prioritizing India if ambiguous."""
        normalized_text = text.title()
        potential_cities = re.findall(r'\b[A-Z][a-z]+\b', normalized_text)
        verified_cities = []

        ignore_words = [
            "I", "Am", "To", "From", "The", "And", "Book", "Find", "Next",
            "Tomorrow", "Today", "Flight", "Train", "Bus", "Car", "Hotel",
            "Stay", "Room", "Ticket", "Price", "Cheapest", "Fastest", "Search",
            "Show", "Open", "Plan", "Trip", "Travel", "Reach", "Go", "Visit",
            "Hex", "Please", "Want", "Need", "Sir", "Ok", "Yes", "No", "For"
        ]

        for city in potential_cities:
            if city in ignore_words:
                continue
            try:
                # Try India first for better local accuracy using country_codes in geocode
                location = self.geolocator.geocode(city, country_codes=['in'])

                # If not found in India, try Global
                if not location:
                    location = self.geolocator.geocode(city)

                if location:
                    clean_city = location.address.split(',')[0].strip()
                    # Filter out generic terms
                    if "Airport" not in clean_city and "Station" not in clean_city and len(clean_city) > 2:
                        if clean_city not in verified_cities:
                            verified_cities.append(clean_city)
            except Exception as e:
                logger.debug(f"Geopy error for {city}: {e}")
        return verified_cities

    def _is_international(self, origin, destination):
        """Check if the trip crosses borders."""
        try:
            loc1 = self.geolocator.geocode(origin)
            loc2 = self.geolocator.geocode(destination)
            if loc1 and loc2:
                country1 = loc1.raw.get('address', {}).get('country_code', '').upper()
                country2 = loc2.raw.get('address', {}).get('country_code', '').upper()
                return country1 != country2
        except:
            pass
        return False

    def _parse_natural_date(self, text):
        """Convert natural language dates to multiple formats."""
        try:
            parsed_date = date_parser.parse(text, fuzzy=True)
            current_year = datetime.now().year
            if parsed_date.year < current_year:
                parsed_date = parsed_date.replace(year=current_year)

            iso_date = parsed_date.strftime("%Y-%m-%d")  # For Ixigo/Google/Skyscanner
            dmy_date = parsed_date.strftime("%d-%b-%Y")  # For RedBus
            dmy_numeric = parsed_date.strftime("%d-%m-%Y")  # For ConfirmTkt

            return iso_date, dmy_date, dmy_numeric
        except:
            return None, None, None

    def _calculate_distance(self, origin, destination):
        """Calculate Real-Time Geodesic Distance."""
        coord1 = self.geolocator.geocode(origin)
        coord2 = self.geolocator.geocode(destination)
        if coord1 and coord2:
            return geodesic((coord1.latitude, coord1.longitude), (coord2.latitude, coord2.longitude)).km
        return 0

    def _open_and_focus(self, url):
        """Open URL and bring browser to foreground."""
        webbrowser.open(url)
        time.sleep(1.0)
        if platform.system() == "Windows":
            try:
                import win32gui
                import win32con
                hwnd = win32gui.GetForegroundWindow()
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
            except:
                pass

    def extract_travel_details(self, text):
        """Extract Origin, Destination, Date, and Mode from natural language globally."""
        found_cities = self._get_city_name(text)
        origin = None
        destination = None

        if len(found_cities) >= 2:
            origin = found_cities[0]
            destination = found_cities[1]
        elif len(found_cities) == 1:
            destination = found_cities[0]
            try:
                from hex_brain import hex_brain
                user_home = hex_brain.user_profile.get("location", "Delhi")
                origin = user_home
            except:
                origin = "Delhi"
        else:
            return None, None, None, None, None, None, None

        iso_date, dmy_date, dmy_numeric = self._parse_natural_date(text)

        mode = "all"
        text_lower = text.lower()
        if "flight" in text_lower or "plane" in text_lower:
            mode = "flight"
        elif "train" in text_lower or "rail" in text_lower:
            mode = "train"
        elif "bus" in text_lower:
            mode = "bus"
        elif "car" in text_lower or "drive" in text_lower or "cab" in text_lower:
            mode = "car"
        elif "hotel" in text_lower or "stay" in text_lower or "room" in text_lower:
            mode = "hotel"

        is_intl = self._is_international(origin, destination)

        return origin, destination, iso_date, dmy_date, dmy_numeric, mode, is_intl

    # ==================== HYBRID SEARCH FUNCTIONS ====================

    def search_flights_hybrid(self, origin, destination, iso_date=None, dmy_date=None, dmy_numeric=None, is_intl=False):
        """Opens Flight Search Pages (Domestic vs International)."""
        report = f"FLIGHT INTELLIGENCE: Opening sources for {origin} to {destination}...\n"

        org_q = urllib.parse.quote(origin)
        dest_q = urllib.parse.quote(destination)

        # 1. Google Flights (Best for both)
        url_google = f"https://www.google.com/travel/flights?q=Flights+from+{org_q}+to+{dest_q}&curr=INR"
        if iso_date: url_google += f"&dd={iso_date}"

        # 2. Ixigo (Best for Domestic)
        url_ixigo = f"https://www.ixigo.com/flights/search?source={org_q}&destination={dest_q}"
        if iso_date: url_ixigo += f"&travelDate={iso_date}"

        # 3. Skyscanner (Best for International)
        url_skyscanner = f"https://www.skyscanner.co.in/transport/flights/{org_q}/{dest_q}/"

        self._open_and_focus(url_google)
        if not is_intl:
            self._open_and_focus(url_ixigo)
        else:
            self._open_and_focus(url_skyscanner)

        return report + "Opened: Google Flights, " + ("Ixigo" if not is_intl else "Skyscanner") + "."

    @staticmethod
    def _route_slug(city):
        """Normalize a city/station label for train-provider route URLs."""
        city = str(city or "").strip().lower()
        city = re.sub(r"\b(?:railway station|junction|jn|station)\b", "", city)
        city = re.sub(r"[^a-z0-9]+", "-", city)
        return city.strip("-")

    def search_trains_hybrid(self, origin, destination, iso_date=None, dmy_date=None, dmy_numeric=None, is_intl=False):
        """Open current, route-specific train search pages without legacy 404 endpoints."""
        report = f"TRAIN INTELLIGENCE: Opening sources for {origin} to {destination}...\n"

        if is_intl:
            query = f"train from {origin} to {destination}"
            url_google = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            self._open_and_focus(url_google)
            return report + "Opened: Google Search (International Rail)."

        origin_slug = self._route_slug(origin)
        destination_slug = self._route_slug(destination)

        # Current provider route formats. The old train-result.php and
        # /trains/search endpoints are legacy URLs and can return HTTP 404.
        url_redrail = (
            f"https://www.redbus.in/train-tickets/"
            f"{origin_slug}-to-{destination_slug}-trains"
        )
        url_confirm = (
            f"https://www.confirmtkt.com/trains/"
            f"{origin_slug}-to-{destination_slug}-train-tickets"
        )
        url_ixigo_train = (
            f"https://www.ixigo.com/by-train-rail/"
            f"{origin_slug}-to-{destination_slug}-by-train"
        )

        # These route pages open successfully using the provider's current
        # URL structure. Date filters are intentionally not appended with the
        # old undocumented query parameters; choose the journey date on-site.
        self._open_and_focus(url_redrail)
        self._open_and_focus(url_confirm)
        self._open_and_focus(url_ixigo_train)

        return report + "Opened: redRail, ConfirmTkt, Ixigo Trains."

    def search_buses_hybrid(self, origin, destination, iso_date=None, dmy_date=None, dmy_numeric=None, is_intl=False):
        """Opens Bus Search Pages."""
        report = f"BUS INTELLIGENCE: Opening sources for {origin} to {destination}...\n"

        if is_intl:
            # International buses are complex, use Google
            query = f"bus from {origin} to {destination}"
            url_google = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            self._open_and_focus(url_google)
            return report + "Opened: Google Search (International Bus)."

        org_q = urllib.parse.quote(origin)
        dest_q = urllib.parse.quote(destination)

        # 1. RedBus
        url_redbus = f"https://www.redbus.in/bus-tickets/{org_q}-to-{dest_q}"
        if dmy_date: url_redbus += f"?onward={dmy_date}&doj={dmy_date}"

        # 2. AbhiBus
        url_abhi = f"https://www.abhibus.com/bus-tickets/{org_q}-to-{dest_q}"

        self._open_and_focus(url_redbus)
        self._open_and_focus(url_abhi)

        return report + "Opened: RedBus, AbhiBus."

    def search_hotels_hybrid(self, destination, iso_date=None, dmy_date=None, dmy_numeric=None, is_intl=False):
        """Opens Hotel Search Pages."""
        report = f"HOTEL INTELLIGENCE: Opening sources for {destination}...\n"

        dest_q = urllib.parse.quote(destination)

        # 1. Google Hotels (Global Best)
        url_google = f"https://www.google.com/travel/hotels?q=Hotels+in+{dest_q}"
        if iso_date: url_google += f"&checkin={iso_date}"

        # 2. Booking.com (Global Best) or MMT (Domestic Best)
        if is_intl:
            url_booking = f"https://www.booking.com/searchresults.html?ss={dest_q}&checkin={iso_date}"
            self._open_and_focus(url_booking)
        else:
            url_mmt = f"https://www.makemytrip.com/hotels/search?city={dest_q}"
            if iso_date: url_mmt += f"&checkin={iso_date}"
            self._open_and_focus(url_mmt)

        self._open_and_focus(url_google)

        return report + "Opened: Google Hotels, " + ("Booking.com" if is_intl else "MakeMyTrip") + "."

    def search_car_hybrid(self, origin, destination, is_intl=False):
        """Opens Google Maps Navigation."""
        url = f"https://www.google.com/maps/dir/?api=1&travelmode=driving&dir_action=navigate&origin={urllib.parse.quote(origin)}&destination={urllib.parse.quote(destination)}"
        distance = self._calculate_distance(origin, destination)
        report = f"CAR NAVIGATION: {origin} to {destination}\nEstimated Distance: {distance:.0f} km\n"
        self._open_and_focus(url)
        return report + "Opened: Google Maps."

    def strategic_compare_all(self, origin, dest, iso_date=None, dmy_date=None, dmy_numeric=None, is_intl=False):
        """Compare All Modes via Hybrid Sources."""
        distance = self._calculate_distance(origin, dest)
        recommendation = "\nHEX GLOBAL STRATEGIC ANALYSIS:\n"

        if is_intl:
            recommendation += f"Route: International ({origin} -> {dest}). Verdict: Flight recommended.\n"
        else:
            if distance < 400:
                recommendation += f"Distance: {distance:.0f} km (Short Haul). Verdict: Car/Train recommended.\n"
            elif distance < 1200:
                recommendation += f"Distance: {distance:.0f} km (Medium Haul). Verdict: Competitive zone.\n"
            else:
                recommendation += f"Distance: {distance:.0f} km (Long Haul). Verdict: Flight recommended.\n"

        recommendation += "\nAction: Opening official dashboards for all modes...\n"

        self.search_flights_hybrid(origin, dest, iso_date, dmy_date, dmy_numeric, is_intl)
        time.sleep(0.5)
        self.search_trains_hybrid(origin, dest, iso_date, dmy_date, dmy_numeric, is_intl)
        time.sleep(0.5)
        self.search_buses_hybrid(origin, dest, iso_date, dmy_date, dmy_numeric, is_intl)
        time.sleep(0.5)
        self.search_car_hybrid(origin, dest, is_intl)

        return recommendation + "Opened: Hybrid Sources for Flights, Trains, Buses & Maps."

    def interactive_search(self, user_input):
        """Main Entry Point: Extracts details and executes hybrid search."""
        origin, destination, iso_date, dmy_date, dmy_numeric, mode, is_intl = self.extract_travel_details(user_input)

        if not origin or not destination:
            return "I need both origin and destination to plan your travel, Sir. Please specify."

        logger.info(
            f"Global Travel Request: {origin} -> {destination} | Intl: {is_intl} | Date: {iso_date} | Mode: {mode}")

        if mode == "flight":
            return self.search_flights_hybrid(origin, destination, iso_date, dmy_date, dmy_numeric, is_intl)
        elif mode == "train":
            return self.search_trains_hybrid(origin, destination, iso_date, dmy_date, dmy_numeric, is_intl)
        elif mode == "bus":
            return self.search_buses_hybrid(origin, destination, iso_date, dmy_date, dmy_numeric, is_intl)
        elif mode == "car":
            return self.search_car_hybrid(origin, destination, is_intl)
        elif mode == "hotel":
            return self.search_hotels_hybrid(destination, iso_date, dmy_date, dmy_numeric, is_intl)
        else:
            return self.strategic_compare_all(origin, destination, iso_date, dmy_date, dmy_numeric, is_intl)


# Singleton
hex_travel = HexTravelAgent()
