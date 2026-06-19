import os
import json
import requests
from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

DATA_DIR = os.path.join(os.getcwd(), "mock_data")

def load_json(filename: str) -> Any:
    path = os.path.join(DATA_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def classify_carbon(kgco2e: float) -> str:
    if kgco2e <= 30:
        return "green"
    if kgco2e <= 100:
        return "amber"
    return "red"

def safe_slot(tracker: Tracker, name: str, default: str = "") -> str:
    value = tracker.get_slot(name)
    return value if value else default

class ActionCollectMissingSlots(Action):
    def name(self) -> Text:
        return "action_collect_missing_slots"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        if not tracker.get_slot("origin"):
            dispatcher.utter_message(response="utter_ask_origin")
            return []
        if not tracker.get_slot("destination"):
            dispatcher.utter_message(response="utter_ask_destination")
            return []
        if not tracker.get_slot("travel_date"):
            dispatcher.utter_message(response="utter_ask_dates")
            return []
        if not tracker.get_slot("budget"):
            dispatcher.utter_message(response="utter_ask_budget")
            return []
        if not tracker.get_slot("sustainability_level"):
            dispatcher.utter_message(response="utter_ask_sustainability_preference")
            return []
        dispatcher.utter_message(text="Great. I have enough details to prepare sustainable travel options.")
        return []

class ActionCalculateCarbon(Action):
    def name(self) -> Text:
        return "action_calculate_carbon"

    def climatiq_estimate(self, mode: str, distance_km: float = 650) -> Optional[float]:
        api_key = os.getenv("CLIMATIQ_API_KEY")
        if not api_key:
            return None
        url = "https://api.climatiq.io/data/v1/estimate"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        activity_map = {
            "train": "passenger_train-route_type_na-distance_na",
            "bus": "passenger_vehicle-vehicle_type_bus-fuel_source_na-distance_na",
            "flight": "passenger_flight-route_type_domestic-aircraft_type_na-distance_na-class_na-rf_included",
            "car": "passenger_vehicle-vehicle_type_car-fuel_source_petrol-engine_size_na-distance_na",
        }
        payload = {
            "emission_factor": {"activity_id": activity_map.get(mode, activity_map["train"]), "data_version": "^21"},
            "parameters": {"distance": distance_km, "distance_unit": "km"}
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=8)
            response.raise_for_status()
            data = response.json()
            return float(data.get("co2e", 0))
        except Exception:
            return None

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        transport_mode = safe_slot(tracker, "transport_mode", "train")
        transport_data = load_json("transport_options.json")
        api_value = self.climatiq_estimate(transport_mode)
        if api_value is not None:
            kgco2e = api_value
            source = "live Climatiq API estimate"
        else:
            match = next((x for x in transport_data if x["mode"] == transport_mode), transport_data[0])
            kgco2e = float(match["kgco2e"])
            source = "mock estimate because live API is not configured"
        colour = classify_carbon(kgco2e)
        dispatcher.utter_message(text=f"Estimated carbon impact for {transport_mode}: {kgco2e:.1f} kg CO2e ({colour}). Source: {source}.")
        return [SlotSet("carbon_score", kgco2e)]

class ActionFetchTravelOptions(Action):
    def name(self) -> Text:
        return "action_fetch_travel_options"

    def amadeus_fetch_hotels(self, destination: str) -> Optional[List[Dict[str, Any]]]:
        api_key = os.getenv("AMADEUS_API_KEY")
        api_secret = os.getenv("AMADEUS_API_SECRET")
        if not api_key or not api_secret:
            return None
        # Placeholder for production OAuth + hotel endpoint call.
        return None

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        destination = safe_slot(tracker, "destination", "Amsterdam")
        hotels = self.amadeus_fetch_hotels(destination)
        if hotels is None:
            all_hotels = load_json("eco_hotels.json")
            hotels = [h for h in all_hotels if h["city"].lower() == destination.lower()]
            if not hotels:
                hotels = all_hotels[:2]
        transport_options = load_json("transport_options.json")
        dispatcher.utter_message(text=f"I found {len(hotels)} accommodation option(s) and {len(transport_options)} transport option(s) for {destination}.")
        return [SlotSet("hotel_options", hotels), SlotSet("transport_options", transport_options)]

class ActionRankEcoOptions(Action):
    def name(self) -> Text:
        return "action_rank_eco_options"

    def score_transport(self, option: Dict[str, Any], preference: str) -> float:
        carbon_score = min(option["kgco2e"] / 200, 1.0)
        price_score = min(option["price"] / 150, 1.0)
        if preference == "low carbon":
            carbon_weight, price_weight, preference_weight = 0.65, 0.25, 0.10
        elif preference == "budget friendly":
            carbon_weight, price_weight, preference_weight = 0.35, 0.55, 0.10
        else:
            carbon_weight, price_weight, preference_weight = 0.50, 0.35, 0.15
        preference_match = 0.0 if option["mode"] in ["train", "bus"] else 0.5
        return (carbon_weight * carbon_score) + (price_weight * price_score) + (preference_weight * preference_match)

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        preference = safe_slot(tracker, "sustainability_level", "balanced")
        hotels = tracker.get_slot("hotel_options") or []
        transport_options = tracker.get_slot("transport_options") or load_json("transport_options.json")
        ranked_transport = sorted(transport_options, key=lambda x: self.score_transport(x, preference))
        best = ranked_transport[0]
        colour = classify_carbon(float(best["kgco2e"]))
        dispatcher.utter_message(text=f"Recommended transport: {best['mode'].title()} | Price: €{best['price']} | Carbon: {best['kgco2e']} kg CO2e | Duration: {best['duration']} | Card colour: {colour}.")
        if hotels:
            hotel_lines = []
            for h in hotels[:3]:
                verified = "verified eco-certified" if h.get("eco_certified") else "sustainability not fully verified"
                hotel_lines.append(f"- {h['name']} (€{h['price']}/night): {verified}. {h['note']}")
            dispatcher.utter_message(text="Eco accommodation options:\n" + "\n".join(hotel_lines))
        dispatcher.utter_message(text="Note: Carbon values are estimates for decision support, not exact scientific certification.")
        return []

class ActionHandoverToHuman(Action):
    def name(self) -> Text:
        return "action_handover_to_human"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        context = {
            "origin": tracker.get_slot("origin"),
            "destination": tracker.get_slot("destination"),
            "travel_date": tracker.get_slot("travel_date"),
            "return_date": tracker.get_slot("return_date"),
            "budget": tracker.get_slot("budget"),
            "transport_mode": tracker.get_slot("transport_mode"),
            "sustainability_level": tracker.get_slot("sustainability_level"),
            "carbon_score": tracker.get_slot("carbon_score"),
            "latest_user_message": tracker.latest_message.get("text"),
        }
        dispatcher.utter_message(text="Human handover has been prepared. A travel advisor will receive this context:\n" + json.dumps(context, indent=2))
        return [SlotSet("handover_required", True)]

class ActionTwoStageClarification(Action):
    def name(self) -> Text:
        return "action_two_stage_clarification"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(
            text="I am not fully sure what you mean. Please choose one option:",
            buttons=[
                {"title": "Plan eco trip", "payload": "/plan_trip"},
                {"title": "Carbon impact", "payload": "/ask_carbon_impact"},
                {"title": "Eco hotels", "payload": "/ask_hotel_options"},
                {"title": "Human advisor", "payload": "/request_handover"}
            ]
        )
        return []
