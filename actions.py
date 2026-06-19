from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher


CLIMATIQ_KEY = os.getenv("CLIMATIQ_API_KEY")
ORS_KEY = os.getenv("OPENROUTESERVICE_API_KEY")
OPENCAGE_KEY = os.getenv("OPENCAGE_API_KEY")
AVIATIONSTACK_KEY = os.getenv("AVIATIONSTACK_API_KEY")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

MOCK_DATA_PATH = "/content/mock_data.json"


# --- Data loader ---

def load_mock_data():
    try:
        with open(MOCK_DATA_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


# --- API helpers ---

def geocode_city_ors(city):
    # Converts a city name to coordinates using OpenRouteService geocoding API
    try:
        r = requests.get(
            "https://api.openrouteservice.org/geocode/search",
            params={"api_key": ORS_KEY, "text": city, "size": 1},
            timeout=8
        )
        coords = r.json()["features"][0]["geometry"]["coordinates"]
        return coords
    except Exception:
        return None

def geocode_city_opencage(city):
    # Fallback geocoder using OpenCage if ORS fails
    try:
        r = requests.get(
            "https://api.opencagedata.com/geocode/v1/json",
            params={"q": city, "key": OPENCAGE_KEY, "limit": 1},
            timeout=8
        )
        result = r.json()["results"][0]["geometry"]
        return [result["lng"], result["lat"]]
    except Exception:
        return None

def geocode_city(city):
    # Two-layer geocoding: ORS first, OpenCage as fallback
    coords = geocode_city_ors(city)
    if coords:
        return coords, "OpenRouteService"
    coords = geocode_city_opencage(city)
    if coords:
        return coords, "OpenCage"
    return None, None

def get_road_distance(origin, destination):
    # Returns (distance_km, duration_hrs, source) for a driving route between two cities
    try:
        origin_coords, src1 = geocode_city(origin)
        dest_coords, src2 = geocode_city(destination)
        if not origin_coords or not dest_coords:
            return None, None, None
        r = requests.post(
            "https://api.openrouteservice.org/v2/directions/driving-car",
            headers={"Authorization": ORS_KEY, "Content-Type": "application/json"},
            json={"coordinates": [origin_coords, dest_coords]},
            timeout=10
        )
        data = r.json()
        distance_km = round(data["routes"][0]["summary"]["distance"] / 1000, 1)
        duration_hrs = round(data["routes"][0]["summary"]["duration"] / 3600, 1)
        return distance_km, duration_hrs, src1
    except Exception:
        return None, None, None

def get_climatiq_carbon(distance_km, mode, passengers=1):
    # Calls Climatiq API to calculate CO2 emissions for a given transport mode and distance
    try:
        activity_ids = {
            "plane":        "passenger_flight-route_type_international-aircraft_type_na-distance_short_haul_lt_3700km-class_economy-rf_included-distance_uplift_included",
            "train":        "passenger_train-route_type_na-fuel_source_na",
            "bus":          "passenger_vehicle-vehicle_type_bus-fuel_source_na-distance_na-engine_size_na",
            "car":          "passenger_vehicle-vehicle_type_car-fuel_source_petrol-distance_na-engine_size_na",
            "electric_car": "passenger_vehicle-vehicle_type_car-fuel_source_bev-distance_na-engine_size_na",
        }
        activity_id = activity_ids.get(mode)
        if not activity_id:
            return None
        r = requests.post(
            "https://api.climatiq.io/data/v1/estimate",
            headers={"Authorization": f"Bearer {CLIMATIQ_KEY}"},
            json={
                "emission_factor": {"activity_id": activity_id, "data_version": "^6"},
                "parameters": {
                    "passengers": passengers,
                    "distance": distance_km,
                    "distance_unit": "km"
                }
            },
            timeout=10
        )
        if r.status_code == 200:
            return round(r.json()["co2e"], 2)
        return None
    except Exception:
        return None

def get_booking_hotels(city, adults=2, nights=3):
    # Searches Booking.com API (via RapidAPI) for hotels in a given city
    try:
        r1 = requests.get(
            "https://booking-com15.p.rapidapi.com/api/v1/hotels/searchDestination",
            headers={
                "X-RapidAPI-Key": RAPIDAPI_KEY,
                "X-RapidAPI-Host": "booking-com15.p.rapidapi.com"
            },
            params={"query": city},
            timeout=10
        )
        data1 = r1.json()
        if not data1.get("status") or not data1.get("data"):
            return None
        dest_id = data1["data"][0]["dest_id"]
        search_type = data1["data"][0]["search_type"]
        checkin = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        checkout = (datetime.now() + timedelta(days=1 + nights)).strftime("%Y-%m-%d")
        r2 = requests.get(
            "https://booking-com15.p.rapidapi.com/api/v1/hotels/searchHotels",
            headers={
                "X-RapidAPI-Key": RAPIDAPI_KEY,
                "X-RapidAPI-Host": "booking-com15.p.rapidapi.com"
            },
            params={
                "dest_id": dest_id,
                "search_type": search_type,
                "arrival_date": checkin,
                "departure_date": checkout,
                "adults": str(adults),
                "room_qty": "1",
                "page_number": "1",
                "units": "metric",
                "temperature_unit": "c",
                "languagecode": "en-us",
                "currency_code": "EUR"
            },
            timeout=15
        )
        data2 = r2.json()
        if data2.get("status") and data2.get("data", {}).get("hotels"):
            return data2["data"]["hotels"][:4]
        return None
    except Exception:
        return None


# --- City lookup + timezone map ---
# Used by ValidateTripForm to validate city names and infer timezones
# Duplicate sao paulo key removed; accented variant added

KNOWN_CITIES = {
    "berlin": "CET", "paris": "CET", "rome": "CET", "madrid": "CET",
    "amsterdam": "CET", "brussels": "CET", "vienna": "CET", "warsaw": "CET",
    "prague": "CET", "budapest": "CET", "milan": "CET", "barcelona": "CET",
    "munich": "CET", "zurich": "CET", "basel": "CET", "bern": "CET",
    "geneva": "CET", "lausanne": "CET", "oslo": "CET", "stockholm": "CET",
    "copenhagen": "CET", "helsinki": "CET", "athens": "CET",
    "zagreb": "CET", "sarajevo": "CET", "belgrade": "CET", "sofia": "CET",
    "bucharest": "CET", "riga": "CET", "tallinn": "CET", "vilnius": "CET",
    "bratislava": "CET", "ljubljana": "CET", "tunis": "CET",
    "algiers": "CET", "lisbon": "CET",
    "london": "GMT", "dublin": "GMT", "edinburgh": "GMT",
    "cardiff": "GMT", "belfast": "GMT",
    "tehran": "IST", "dubai": "GST", "abu dhabi": "GST", "doha": "GST",
    "riyadh": "AST", "kuwait city": "AST", "muscat": "GST",
    "beirut": "EET", "amman": "EET", "jerusalem": "EET", "tel aviv": "EET",
    "baghdad": "AST", "ankara": "TRT", "istanbul": "TRT",
    "tokyo": "JST", "osaka": "JST", "kyoto": "JST", "hiroshima": "JST",
    "beijing": "CST", "shanghai": "CST", "guangzhou": "CST", "shenzhen": "CST",
    "hong kong": "HKT", "taipei": "CST", "seoul": "KST", "busan": "KST",
    "mumbai": "IST_IN", "delhi": "IST_IN", "bangalore": "IST_IN",
    "kolkata": "IST_IN", "chennai": "IST_IN", "hyderabad": "IST_IN",
    "singapore": "SGT", "kuala lumpur": "MYT", "jakarta": "WIB",
    "bangkok": "ICT", "ho chi minh city": "ICT", "hanoi": "ICT",
    "manila": "PHT", "bali": "WITA", "kathmandu": "NPT",
    "colombo": "SLST", "dhaka": "BST",
    "sydney": "AEST", "melbourne": "AEST", "brisbane": "AEST",
    "perth": "AWST", "adelaide": "ACST", "auckland": "NZST",
    "new york": "EST", "toronto": "EST", "miami": "EST", "boston": "EST",
    "montreal": "EST", "washington": "EST", "philadelphia": "EST",
    "atlanta": "EST", "detroit": "EST", "ottawa": "EST",
    "chicago": "CST_US", "houston": "CST_US", "dallas": "CST_US",
    "mexico city": "CST_US", "winnipeg": "CST_US",
    "denver": "MST", "phoenix": "MST", "calgary": "MST",
    "los angeles": "PST", "san francisco": "PST", "seattle": "PST",
    "vancouver": "PST", "las vegas": "PST", "portland": "PST",
    "buenos aires": "ART", "sao paulo": "BRT", "sao paulo": "BRT",
    "rio de janeiro": "BRT", "bogota": "COT", "lima": "PET",
    "santiago": "CLT", "caracas": "VET",
    "cairo": "EET", "nairobi": "EAT", "lagos": "WAT",
    "johannesburg": "SAST", "cape town": "SAST", "casablanca": "WET",
    "accra": "GMT", "dakar": "GMT", "addis ababa": "EAT",
    "dar es salaam": "EAT", "kampala": "EAT", "kigali": "CAT",
    "luanda": "WAT", "kinshasa": "WAT", "khartoum": "EAT",
    "tripoli": "EET",
}

def infer_timezone(city):
    # Returns timezone abbreviation for a city, or "local time" if not found
    if city:
        tz = KNOWN_CITIES.get(city.lower().strip())
        return tz if tz else "local time"
    return "local time"


# --- Slot extraction helpers ---
# These mirror the lecturer pattern: get_location() / get_schedule()
# applied to our trip planning slots

def get_destination(tracker):
    # Checks slot first, then falls back to entity extraction from latest message
    destination = tracker.get_slot("destination")
    if not destination:
        for entity in tracker.latest_message.get("entities", []):
            if entity.get("entity") in ("destination", "GPE", "LOC"):
                destination = entity.get("value")
    return destination

def get_origin(tracker):
    # Checks slot first, then falls back to entity extraction from latest message
    origin = tracker.get_slot("origin")
    if not origin:
        for entity in tracker.latest_message.get("entities", []):
            if entity.get("entity") in ("origin", "GPE", "LOC"):
                origin = entity.get("value")
    return origin

def get_budget(tracker):
    # Extracts budget from slot or CARDINAL/MONEY entities, stripping currency words
    budget = tracker.get_slot("budget")
    if not budget:
        for entity in tracker.latest_message.get("entities", []):
            if entity.get("entity") in ("budget", "CARDINAL", "MONEY"):
                try:
                    budget = float(
                        str(entity.get("value"))
                        .replace("euros", "").replace("euro", "")
                        .replace("dollars", "").replace("dollar", "")
                        .strip()
                    )
                except (ValueError, TypeError):
                    pass
    return budget


# --- Form validation ---
# ValidateHotelForm, ValidateTransportForm, ValidateActivitiesForm removed
# because hotel_form, transport_form, activities_form no longer exist in domain.yml

class ValidateTripForm(FormValidationAction):

    def name(self) -> Text:
        return "validate_trip_form"

    def validate_destination(self, slot_value, dispatcher, tracker, domain):
        # Three-layer fallback: slot value -> entity -> raw text
        if not slot_value:
            for entity in tracker.latest_message.get("entities", []):
                if entity.get("entity") in ("destination", "origin", "GPE", "LOC", "user_location"):
                    slot_value = entity.get("value")
                    break
        if not slot_value:
            text = tracker.latest_message.get("text", "").strip()
            if text and 1 < len(text) < 60 and not text.replace(".", "").isdigit():
                slot_value = text
        if slot_value:
            city_key = str(slot_value).lower().strip()
            if city_key in KNOWN_CITIES:
                return {"destination": slot_value, "timezone": KNOWN_CITIES[city_key]}
            if len(city_key) > 1:
                return {"destination": slot_value, "timezone": "local time"}
        dispatcher.utter_message(text="Please enter a valid destination city.")
        return {"destination": None}

    def validate_origin(self, slot_value, dispatcher, tracker, domain):
        # Three-layer fallback: slot value -> entity -> raw text
        if not slot_value:
            for entity in tracker.latest_message.get("entities", []):
                if entity.get("entity") in ("origin", "destination", "GPE", "LOC", "user_location"):
                    slot_value = entity.get("value")
                    break
        if not slot_value:
            text = tracker.latest_message.get("text", "").strip()
            if text and 1 < len(text) < 60 and not text.replace(".", "").isdigit():
                slot_value = text
        if slot_value and len(str(slot_value).strip()) > 1:
            return {"origin": slot_value}
        dispatcher.utter_message(text="Please enter a valid departure city.")
        return {"origin": None}

    def validate_travel_date(self, slot_value, dispatcher, tracker, domain):
        # Rejects city names accidentally entered as dates; checks for date keywords/digits
        if not slot_value:
            dispatcher.utter_message(text="Please enter a valid travel date, e.g. June 25 or next Monday.")
            return {"travel_date": None}
        value = str(slot_value).lower().strip()
        if value in KNOWN_CITIES:
            dispatcher.utter_message(
                text=f"It looks like {slot_value} is a city, not a date. Please enter a travel date, e.g. June 25 or next Monday."
            )
            return {"travel_date": None}
        date_keywords = [
            "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
            "today", "tomorrow", "next", "weekend", "week", "month"
        ]
        has_digit = any(c.isdigit() for c in value)
        has_keyword = any(kw in value for kw in date_keywords)
        if not has_digit and not has_keyword:
            dispatcher.utter_message(
                text=f"{slot_value} does not look like a date. Please enter a travel date, e.g. June 25, July 10, or next Monday."
            )
            return {"travel_date": None}
        return {"travel_date": slot_value}

    def validate_travelers_number(self, slot_value, dispatcher, tracker, domain):
        # Strips word "people" or "person" then validates as positive integer
        try:
            travelers = float(str(slot_value).replace("people", "").replace("person", "").strip())
            if travelers > 0:
                return {"travelers_number": str(int(travelers))}
        except (ValueError, TypeError):
            pass
        dispatcher.utter_message(text="Please enter a valid number of travelers, e.g. 2.")
        return {"travelers_number": None}

    def validate_budget(self, slot_value, dispatcher, tracker, domain):
        # Strips currency words and validates as positive number
        try:
            budget = float(
                str(slot_value)
                .replace("euros", "").replace("euro", "")
                .replace("dollars", "").replace("dollar", "")
                .strip()
            )
            if budget > 0:
                return {"budget": str(budget)}
        except (ValueError, TypeError):
            pass
        dispatcher.utter_message(text="Please enter a valid budget amount in euros, e.g. 1500.")
        return {"budget": None}


# --- Custom actions ---

class ActionCompareTransport(Action):
    # Compares CO2 emissions across 5 transport modes using Climatiq API
    # Falls back to hardcoded emission factors if API is unavailable

    def name(self) -> Text:
        return "action_compare_transport"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        destination = get_destination(tracker)
        origin = get_origin(tracker)
        travelers = int(tracker.get_slot("travelers_number") or 1)

        print(f"DEBUG: Transport comparison - origin={origin}, destination={destination}, travelers={travelers}")

        if not destination or not origin:
            dispatcher.utter_message(text="Please tell me your origin and destination city first!")
            return []

        distance_km, duration_hrs, geo_source = get_road_distance(origin, destination)
        if distance_km:
            api_source = f"Live route data via OpenRouteService (geocoding: {geo_source})"
        else:
            distance_km = 900
            duration_hrs = 9.0
            api_source = "Estimated distance (offline fallback)"

        lines = [
            f"Transport options from {origin} to {destination}",
            f"Distance: {distance_km} km | Drive time: {duration_hrs}h",
            f"Source: {api_source}",
            ""
        ]

        modes = [
            ("plane",        "Flight",      255),
            ("train",        "Train",        41),
            ("bus",          "Bus",          89),
            ("electric_car", "Electric Car", 53),
            ("car",          "Petrol Car",  171),
        ]
        eco_labels = {
            "plane": "HIGH", "train": "LOW", "bus": "MEDIUM",
            "electric_car": "LOW", "car": "HIGH"
        }

        for mode_key, label, fallback_g_per_km in modes:
            co2 = get_climatiq_carbon(distance_km, mode_key, travelers)
            source_tag = "Climatiq API"
            if co2 is None:
                co2 = round((fallback_g_per_km * distance_km * travelers) / 1000, 1)
                source_tag = "estimated"
            eco = eco_labels.get(mode_key, "MEDIUM")
            lines.append(f"{label}: {co2} kg CO2 | Impact: {eco} ({source_tag})")

        lines.append("")
        lines.append("Tip: Train or bus are the most sustainable choices for European routes!")
        dispatcher.utter_message(text="\n".join(lines))
        return []


class ActionCompareAccommodation(Action):
    # Fetches live hotel data from Booking.com API via RapidAPI
    # Falls back to mock_data.json if API is unavailable

    def name(self) -> Text:
        return "action_compare_accommodation"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        destination = get_destination(tracker)
        budget = get_budget(tracker)
        travelers_number = tracker.get_slot("travelers_number")

        print(f"DEBUG: Accommodation - destination={destination}, budget={budget}, travelers={travelers_number}")

        if not destination:
            dispatcher.utter_message(text="Please tell me your destination city first!")
            return []

        adults = int(travelers_number) if travelers_number else 2
        budget_str = f"EUR {int(float(budget))}" if budget else "your budget"
        travelers_str = f"{adults} traveler(s)"

        lines = [
            f"Accommodation in {destination} for {travelers_str} (budget: {budget_str})",
            ""
        ]

        hotels = get_booking_hotels(destination, adults=adults)

        if hotels:
            lines.append("Source: Live data via Booking.com API")
            lines.append("")
            for h in hotels:
                prop = h.get("property", {})
                name = prop.get("name", "Unknown")
                price = prop.get("priceBreakdown", {}).get("grossPrice", {}).get("value")
                rating = prop.get("reviewScore", "N/A")
                review_word = prop.get("reviewScoreWord", "")
                price_str = f"EUR {round(price, 0):.0f}/stay" if price else "Price N/A"
                rating_str = f"{rating} {review_word}".strip()
                lines.append(f"{name} | {price_str} | Rating: {rating_str}")
        else:
            lines.append("Source: Curated eco-certified database (offline fallback)")
            lines.append("")
            mock = load_mock_data()
            hotels_mock = mock.get("hotels", {})
            city_hotels = hotels_mock.get(
                destination.title(),
                hotels_mock.get(destination, hotels_mock.get("default", []))
            )
            for hotel in city_hotels:
                cert = hotel.get("certification") or "No certification"
                price = hotel.get("price_per_night", "N/A")
                features = ", ".join(hotel.get("features", [])[:2])
                lines.append(f"{hotel['name']} | EUR {price}/night | {cert}")
                lines.append(f"   Features: {features}")

        lines.append("")
        lines.append("Tip: Look for Green Key or EarthCheck certified properties for lowest eco-impact!")
        dispatcher.utter_message(text="\n".join(lines))
        return []


class ActionCompareActivities(Action):
    # Returns sustainable activities for the destination from mock_data.json
    # Filters by eco_activity slot if the user named a specific activity type

    def name(self) -> Text:
        return "action_compare_activities"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        destination = get_destination(tracker)
        preferred_activity = tracker.get_slot("eco_activity")

        print(f"DEBUG: Activities - destination={destination}, preferred={preferred_activity}")

        if not destination:
            dispatcher.utter_message(text="Please tell me your destination city first!")
            return []

        mock = load_mock_data()
        activities = mock.get("activities", {})
        city_activities = activities.get(
            destination.title(),
            activities.get(destination, activities.get("default", []))
        )

        lines = [
            f"Sustainable activities in {destination}",
            "Source: Curated eco-activity database",
            ""
        ]

        if preferred_activity:
            lines.append(f"Filtering for: {preferred_activity}")
            lines.append("")
            filtered = [
                a for a in city_activities
                if preferred_activity.lower() in a.get("name", "").lower()
            ]
            if filtered:
                city_activities = filtered

        for act in city_activities:
            impact = {"green": "Low impact", "amber": "Medium impact", "red": "High impact"}.get(
                act.get("eco_score", "green"), "Low impact"
            )
            carbon = act.get("carbon_kg", 0)
            price = act.get("price", 0)
            carbon_str = f"{carbon} kg CO2" if carbon > 0 else "Zero emissions"
            price_str = f"EUR {price}" if price > 0 else "Free"
            lines.append(f"{act['name']} | {carbon_str} | {price_str} | {impact}")

        lines.append("")
        lines.append("Tip: Choosing local guides keeps money in the local economy!")
        dispatcher.utter_message(text="\n".join(lines))
        return []


class ActionCarbonOffset(Action):
    # Calculates trip CO2 using Climatiq API then shows offset options from mock_data.json
    # Falls back to hardcoded emission rates if API fails

    def name(self) -> Text:
        return "action_carbon_offset"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        destination = get_destination(tracker)
        origin = get_origin(tracker)
        transport_type = tracker.get_slot("transport_type")
        travelers_number = tracker.get_slot("travelers_number")

        print(f"DEBUG: Carbon offset - origin={origin}, destination={destination}, mode={transport_type}")

        if not destination or not origin:
            dispatcher.utter_message(text="Please tell me your origin and destination first!")
            return []

        travelers = int(travelers_number) if travelers_number else 1
        mode_key = str(transport_type).lower() if transport_type else "plane"

        distance_km, _, geo_source = get_road_distance(origin, destination)
        if not distance_km:
            distance_km = 900

        co2_kg = get_climatiq_carbon(distance_km, mode_key, travelers)
        data_source = "Climatiq API (2025 BEIS factors)"
        if co2_kg is None:
            fallback_rates = {
                "plane": 255, "train": 41, "bus": 89,
                "car": 171, "electric_car": 53, "ferry": 19
            }
            rate = fallback_rates.get(mode_key, 171)
            co2_kg = round((rate * distance_km * travelers) / 1000, 1)
            data_source = "Estimated (offline fallback)"

        mock = load_mock_data()
        offsets = mock.get("carbon_offsets", [])

        lines = [
            "Carbon Offset Calculator",
            f"Route: {origin} to {destination} ({distance_km} km)",
            f"Transport: {transport_type or 'plane'} | Travelers: {travelers}",
            f"Total CO2: {co2_kg} kg | Source: {data_source}",
            "",
            "Offset options:"
        ]

        for offset in offsets:
            cost = round(co2_kg * offset["price_per_tonne"] / 1000, 2)
            lines.append(
                f"{offset['name']} | EUR {cost} | {offset['project_type']} - {offset['location']}"
            )

        lines.append("")
        lines.append("Tip: Gold Standard offsets are independently verified and highest quality!")
        dispatcher.utter_message(text="\n".join(lines))
        return []


class ActionFinalItinerary(Action):
    # Assembles a full trip summary from all collected slots
    # Enriches with live distance, CO2, and hotel data where available

    def name(self) -> Text:
        return "action_final_itinerary"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        destination = get_destination(tracker)
        origin = get_origin(tracker)
        travel_date = tracker.get_slot("travel_date")
        travelers_number = tracker.get_slot("travelers_number")
        budget = get_budget(tracker)
        transport_type = tracker.get_slot("transport_type")
        hotel_type = tracker.get_slot("hotel_type")
        timezone = tracker.get_slot("timezone")

        destination_str = destination or "your destination"
        origin_str = origin or "your origin"
        date_str = travel_date or "your travel date"
        travelers_str = str(int(travelers_number)) if travelers_number else "N/A"
        budget_str = f"EUR {int(float(budget))}" if budget else "N/A"
        transport_str = transport_type or "not specified"
        hotel_str = hotel_type or "not specified"
        tz_str = timezone if timezone else infer_timezone(destination)
        travelers = int(travelers_number) if travelers_number else 1

        print(f"DEBUG: Itinerary - {origin_str} to {destination_str}, {date_str}, {travelers_str} travelers")

        distance_km, duration_hrs, _ = get_road_distance(origin_str, destination_str)
        mode_key = str(transport_type).lower() if transport_type else "plane"
        co2_kg = None
        if distance_km:
            co2_kg = get_climatiq_carbon(distance_km, mode_key, travelers)

        hotels = get_booking_hotels(destination_str, adults=travelers)

        lines = [
            "Your Eco-Travel Itinerary",
            "-" * 38,
            f"From:          {origin_str}",
            f"To:            {destination_str}",
            f"Date:          {date_str}",
            f"Travelers:     {travelers_str}",
            f"Budget:        {budget_str}",
            f"Transport:     {transport_str}",
            f"Accommodation: {hotel_str}",
            f"Timezone:      {tz_str}",
        ]

        if distance_km:
            lines.append(f"Distance:      {distance_km} km (~{duration_hrs}h drive)")
        if co2_kg:
            lines.append(f"Trip CO2:      {co2_kg} kg (Climatiq 2025)")

        lines.append("-" * 38)

        if hotels:
            lines.append("")
            lines.append("Top hotels from Booking.com (live prices):")
            for h in hotels[:3]:
                prop = h.get("property", {})
                name = prop.get("name", "Unknown")
                price = prop.get("priceBreakdown", {}).get("grossPrice", {}).get("value")
                rating = prop.get("reviewScore", "N/A")
                price_str = f"EUR {round(price, 0):.0f}" if price else "N/A"
                lines.append(f"  - {name} | {price_str}/stay | Rating: {rating}")

        lines += [
            "",
            "Sustainability tips:",
            "  - Pack light: less weight means less fuel",
            "  - Use reusable water bottles and bags",
            "  - Choose local restaurants and markets",
            "  - Offset your carbon footprint",
            "  - Support eco-certified accommodation",
            "",
            "Thank you for choosing sustainable travel!"
        ]

        dispatcher.utter_message(text="\n".join(lines))
        return []


class ActionHumanHandover(Action):
    # Passes collected trip context to a human agent when the user requests it

    def name(self) -> Text:
        return "action_human_handover"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        destination = get_destination(tracker)
        origin = get_origin(tracker)

        context = []
        if origin:
            context.append(f"Origin: {origin}")
        if destination:
            context.append(f"Destination: {destination}")
        if tracker.get_slot("travel_date"):
            context.append(f"Date: {tracker.get_slot('travel_date')}")
        if tracker.get_slot("budget"):
            context.append(f"Budget: EUR {int(float(tracker.get_slot('budget')))}")
        if tracker.get_slot("travelers_number"):
            context.append(f"Travelers: {int(tracker.get_slot('travelers_number'))}")

        context_str = " | ".join(context) if context else "No trip details collected yet"
        dispatcher.utter_message(
            text=f"Connecting you to a human agent.\n\nYour trip context:\n{context_str}\n\nPlease wait - an agent will be with you shortly."
        )
        return []


class ActionCustomFallback(Action):
    # Counts consecutive misunderstood messages; escalates to human after 3 failures
    # Requires fallback_count slot in domain.yml

    def name(self) -> Text:
        return "action_custom_fallback"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        fallback_count = float(tracker.get_slot("fallback_count") or 0) + 1

        print(f"DEBUG: Fallback triggered - count={fallback_count}")

        if fallback_count >= 3:
            dispatcher.utter_message(
                text="I have had trouble understanding you a few times. Let me connect you to a human agent."
            )
            return [SlotSet("fallback_count", 0)]

        dispatcher.utter_message(
            text="I am sorry, I did not quite understand that. I can help you with:\n"
                 "- Planning a trip (just tell me your destination)\n"
                 "- Comparing eco-friendly transport options\n"
                 "- Finding green accommodation\n"
                 "- Suggesting sustainable activities\n"
                 "- Calculating your carbon offset\n\n"
                 "What would you like to do?"
        )
        return [SlotSet("fallback_count", fallback_count)]
'''

with open("/content/actions.py", "w") as f:
    f.write(actions_content)

print("actions.py written successfully"
