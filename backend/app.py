# Backend Flask application
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# Define API constants at the global scope
PRAAMID_API_BASE_URL = "https://www.praamid.ee/online/events"
PRAAMID_ITEM_MAPPINGS_URL = "https://www.praamid.ee/online/item-mappings"
PRAAMID_PRICES_URL_TEMPLATE = "https://www.praamid.ee/online/prices?pricelist={pricelist_code}&date={date}"
PRAAMID_BOOKINGS_URL = "https://www.praamid.ee/online/bookings"

def format_time_from_iso(iso_string):
    if not iso_string: return "N/A"
    try:
        normalized_iso_string = iso_string
        if '+' in iso_string and iso_string[-3] == ':':
            normalized_iso_string = iso_string[:-3] + iso_string[-2:]
        elif '-' in iso_string and iso_string[-3] == ':':
            normalized_iso_string = iso_string[:-3] + iso_string[-2:]

        if 'Z' in normalized_iso_string:
            fmt = "%Y-%m-%dT%H:%M:%S.%f%z" if '.' in normalized_iso_string else "%Y-%m-%dT%H:%M:%S%z"
            dt_object = datetime.strptime(normalized_iso_string.replace('Z', '+0000'), fmt)
        elif '+' in normalized_iso_string or '-' in normalized_iso_string[19:]:
            fmt = "%Y-%m-%dT%H:%M:%S.%f%z" if '.' in normalized_iso_string else "%Y-%m-%dT%H:%M:%S%z"
            dt_object = datetime.strptime(normalized_iso_string, fmt)
        else:
            dt_object = datetime.fromisoformat(normalized_iso_string)
            if dt_object.tzinfo is None:
                 dt_object = dt_object.replace(tzinfo=timezone.utc)

        return dt_object.astimezone(timezone.utc).strftime("%H:%M")
    except ValueError as e:
        print(f"Could not parse date string '{iso_string}' (normalized to '{normalized_iso_string}'): {e}")
        parts = iso_string.split('T')
        if len(parts) > 1 and len(parts[1]) >= 5:
            return parts[1][:5]
        return iso_string


@app.route('/api/get_schedule', methods=['GET'])
def get_schedule():
    direction = request.args.get('direction')
    departure_date_str = request.args.get('date')
    if not direction or not departure_date_str:
        return jsonify({"error": "Missing direction or date parameter"}), 400
    try:
        datetime.strptime(departure_date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    target_url = f"{PRAAMID_API_BASE_URL}?direction={direction}&departure-date={departure_date_str}&time-shift=300"
    headers = {'Accept': 'application/json'}
    response_obj = None
    try:
        response_obj = requests.get(target_url, headers=headers, timeout=10)
        response_obj.raise_for_status()
        praamid_data = response_obj.json()
        processed_items = []
        if praamid_data and 'items' in praamid_data:
            for item in praamid_data['items']:
                pricelist_info = item.get("pricelist", {})
                processed_items.append({
                    "dtstart_utc_iso": item.get("dtstart"),
                    "dtend_utc_iso": item.get("dtend"),
                    "startTimeLocal": format_time_from_iso(item.get("dtstart")),
                    "endTimeLocal": format_time_from_iso(item.get("dtend")),
                    "capacities": item.get("capacities", {}),
                    "ship": item.get("ship", {}),
                    "pricelist": pricelist_info,
                    "event_uid": item.get("uid"),
                    "original_event_data": item
                })
        return jsonify(processed_items)
    except requests.exceptions.HTTPError as http_err:
        status_code = getattr(response_obj, 'status_code', 500)
        details = response_obj.text if response_obj is not None else "No response object"
        return jsonify({"error": f"HTTP error occurred while fetching schedule: {http_err}", "details": details}), status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Request exception while fetching schedule: {str(e)}"}), 503
    except ValueError as e:
        return jsonify({"error": f"Failed to decode JSON schedule response: {str(e)}"}), 500

def get_ticket_item_details_from_praamid(session, pricelist_code, departure_date, num_cars, num_adults, vehicle_reg_nr_from_user=None):
    item_details_for_payload = []
    common_headers = {'Accept': 'application/json'}
    try:
        mappings_response = session.get(PRAAMID_ITEM_MAPPINGS_URL, headers=common_headers, timeout=7)
        mappings_response.raise_for_status()
        mappings = mappings_response.json().get("items", [])
    except Exception as e:
        return None, f"Could not fetch item mappings: {str(e)}"
    try:
        prices_url = PRAAMID_PRICES_URL_TEMPLATE.format(pricelist_code=pricelist_code, date=departure_date)
        prices_response = session.get(prices_url, headers=common_headers, timeout=7)
        prices_response.raise_for_status()
        prices_data = prices_response.json().get("items", [])
        price_map = {p["item"]["code"]: p["amount"] for p in prices_data if p.get("item") and p["item"].get("code")}
    except Exception as e:
        return None, f"Could not fetch prices: {str(e)}"

    car_item_code_found = None
    if num_cars > 0:
        for mapping in mappings:
            if mapping.get("capacityUnitCode") == "M1" and mapping.get("priceCategory") == "REGULAR":
                car_item_code_found = mapping.get("itemCode")
                break
        if car_item_code_found and car_item_code_found in price_map:
            item_details_for_payload.append({
                "capacityUnit": {"code": "M1", "name": "Sõiduauto (M1)"},
                "quantity": num_cars,
                "item": {"code": car_item_code_found, "name": "Sõiduauto"},
                "itemPrice": price_map[car_item_code_found],
                "amount": price_map[car_item_code_found] * num_cars,
                "vehicleRegNr": vehicle_reg_nr_from_user or "",
                "vehicleCountry": {"code": "EST", "names": {"en": "Estonia", "et": "Eesti"}} if vehicle_reg_nr_from_user else {},
                "dci": "D"
            })
        elif num_cars > 0:
            return None, f"Car item code '{car_item_code_found}' (M1/REGULAR) not found in price map or mappings."

    adult_item_code_found = None
    if num_adults > 0:
        for mapping in mappings:
            if mapping.get("capacityUnitCode") == "P" and mapping.get("priceCategory") == "REGULAR":
                adult_item_code_found = mapping.get("itemCode")
                break
        if adult_item_code_found and adult_item_code_found in price_map:
            item_details_for_payload.append({
                "capacityUnit": {"code": "P", "name": "Reisija"},
                "quantity": num_adults,
                "item": {"code": adult_item_code_found, "name": "Reisija täispilet"},
                "priceCategory": {"code": "REGULAR"},
                "itemPrice": price_map[adult_item_code_found],
                "amount": price_map[adult_item_code_found] * num_adults,
                "dci": "D",
                "vehicleRegNr": ""
            })
        elif num_adults > 0:
             return None, f"Adult passenger item code '{adult_item_code_found}' (P/REGULAR) not found in price map or mappings."

    if not item_details_for_payload and (num_cars > 0 or num_adults > 0) :
        return None, "No items could be prepared for booking (car/adult types not found or priced)."
    return item_details_for_payload, None

@app.route('/api/add_to_cart', methods=['POST'])
def add_to_cart():
    data = request.get_json()
    print(f"Received data in /api/add_to_cart: {data}")

    if not data: return jsonify({"error": "Missing request payload"}), 400
    required_fields = ['original_event_data', 'direction', 'departureDate',
                       'numCars', 'numAdults', 'userEmail', 'userPhone']
    for field in required_fields:
        if field not in data: return jsonify({"error": f"Missing field in payload: {field}"}), 400

    num_cars = int(data['numCars'])
    if num_cars > 0 and not data.get('vehicleRegNr'):
        return jsonify({"error": "Missing field in payload: vehicleRegNr (required if numCars > 0)"}), 400

    # Correctly access the actual Praamid event item:
    # data['original_event_data'] from the frontend IS the actual Praamid event item.
    event_item_from_praamid = data['original_event_data']
    print(f"DEBUG: Extracted event_item_from_praamid: {event_item_from_praamid}")

    direction_code = data['direction']
    departure_date = data['departureDate']

    pricelist_code = data.get('pricelistCode')
    if not pricelist_code:
        if event_item_from_praamid.get("pricelist") and event_item_from_praamid["pricelist"].get("code"):
            pricelist_code = event_item_from_praamid["pricelist"].get("code")
    if not pricelist_code:
        return jsonify({"error": "Missing pricelistCode, cannot determine item prices."}), 400

    num_adults = int(data['numAdults'])
    user_email = data['userEmail']
    user_phone = data['userPhone']
    vehicle_reg_nr_for_payload = data.get("vehicleRegNr", "") if num_cars > 0 else ""

    with requests.Session() as session:
        boarding_passes, error_msg = get_ticket_item_details_from_praamid(
            session, pricelist_code, departure_date, num_cars, num_adults, vehicle_reg_nr_for_payload
        )
        if error_msg: return jsonify({"error": error_msg}), 500
        if not boarding_passes and (num_cars > 0 or num_adults > 0):
            return jsonify({"error": "Failed to prepare any valid items for booking (no valid car or adult tickets found/priced)."}), 500
        if not boarding_passes and num_cars == 0 and num_adults == 0 :
             return jsonify({"error": "No items (cars or adults) specified for booking."}), 400

        event_for_payload = {
            "dtstart": event_item_from_praamid.get("dtstart"),
            "dtend": event_item_from_praamid.get("dtend"),
            "uid": event_item_from_praamid.get("uid"),
            "pricelist": {"code": pricelist_code},
            "transportationType": event_item_from_praamid.get("transportationType"),
            "ship": event_item_from_praamid.get("ship")
        }
        print(f"DEBUG: Constructed event_for_payload: {event_for_payload}")

        direction_obj_for_payload = {"code": direction_code}
        if event_item_from_praamid.get("direction"):
            direction_obj_for_payload = event_item_from_praamid.get("direction")

        booking_payload = {
            "tickets": [{
                "boardingPasses": boarding_passes,
                "services": [], "attachments": [],
                "customer": {"email": user_email},
                "phoneNumber": user_phone,
                "smsNotification": False, "smsDepartureNotification": False, "calendarInvite": False,
                "direction": direction_obj_for_payload,
                "directionCode": direction_code,
                "event": event_for_payload,
                "pricelist": {"code": pricelist_code},
                "pos": {"code": "CP"}
            }],
            "customer": {"email": user_email}
        }
        for bp in booking_payload["tickets"][0]["boardingPasses"]:
            if bp.get("capacityUnit", {}).get("code") == "M1":
                bp.pop("discountSubjects", None)

        post_headers = {
            'Content-Type': 'application/json', 'Accept': 'application/json, text/plain, */*',
            'Origin': 'https://www.praamid.ee',
            'Referer': 'https://www.praamid.ee/portal/ticket/departure'
        }
        booking_response_obj = None
        try:
            print(f"Attempting to POST to {PRAAMID_BOOKINGS_URL} (guest) with payload: {booking_payload}")
            booking_response_obj = session.post(PRAAMID_BOOKINGS_URL, headers=post_headers, json=booking_payload, timeout=20)
            booking_response_obj.raise_for_status()
            booking_confirmation = booking_response_obj.json()
            booking_uid = booking_confirmation.get("response")
            if booking_uid:
                checkout_url = f"https://www.praamid.ee/portal/ticket/checkout?bookingUid={booking_uid}"
                return jsonify({"message": "Successfully created booking.", "bookingUid": booking_uid, "checkoutUrl": checkout_url}), 201
            else:
                return jsonify({"error": "Booking created but UID not found in response.", "details": booking_confirmation}), 500
        except requests.exceptions.HTTPError as http_err:
            status_code = getattr(booking_response_obj, 'status_code', 500)
            details_text = booking_response_obj.text if booking_response_obj is not None else "No response text"
            details_json = {}
            try:
                if booking_response_obj is not None: details_json = booking_response_obj.json()
            except ValueError: pass
            print(f"HTTP Error from Praamid (guest booking): {status_code}, Response: {details_text}")
            return jsonify({"error": f"HTTP error creating booking on Praamid.ee ({http_err})",
                            "praamid_status_code": status_code,
                            "praamid_details_json": details_json,
                            "praamid_details_text": details_text
                            }), status_code
        except requests.exceptions.RequestException as e:
            print(f"Network error while creating booking (guest): {str(e)}")
            return jsonify({"error": f"Network error while creating booking: {str(e)}"}), 503
        except ValueError as e:
            print(f"JSON decode error for Praamid response (guest booking): {str(e)}")
            return jsonify({"error": f"Failed to decode JSON response from Praamid.ee during booking creation: {str(e)}"}), 500

@app.route('/api/check_slot_availability', methods=['GET'])
def check_slot_availability():
    direction = request.args.get('direction')
    departure_date_str = request.args.get('date')
    event_uid_to_check = request.args.get('event_uid')

    if not all([direction, departure_date_str, event_uid_to_check]):
        return jsonify({"error": "Missing parameters. Required: direction, date, event_uid"}), 400

    try:
        datetime.strptime(departure_date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    target_url = f"{PRAAMID_API_BASE_URL}?direction={direction}&departure-date={departure_date_str}&time-shift=300"
    headers = {'Accept': 'application/json'}
    response_obj = None

    try:
        response_obj = requests.get(target_url, headers=headers, timeout=10)
        response_obj.raise_for_status()
        praamid_data = response_obj.json()

        print(f"Checking slot: UID_to_check={event_uid_to_check}, Date={departure_date_str}, Direction={direction}")

        if praamid_data and 'items' in praamid_data:
            found_event_uids = [item.get("uid") for item in praamid_data['items']]
            print(f"UIDs found in Praamid response for this check: {found_event_uids}")

            for item in praamid_data['items']:
                if str(item.get("uid")) == str(event_uid_to_check):
                    available_cars = item.get("capacities", {}).get("sv", 0)
                    print(f"Match found for {event_uid_to_check}. Cars: {available_cars}")
                    return jsonify({
                        "event_uid": event_uid_to_check,
                        "available_cars": available_cars,
                        "is_available": available_cars > 0
                    }), 200

            print(f"Event UID {event_uid_to_check} NOT found in the list.")
            return jsonify({"error": "Event UID not found for the given date and direction"}), 404
        else:
            print(f"No schedule items found for date {departure_date_str}, direction {direction} in check_slot_availability.")
            return jsonify({"error": "No schedule items found for the given date and direction"}), 404

    except requests.exceptions.HTTPError as http_err:
        status_code = getattr(response_obj, 'status_code', 500)
        details = response_obj.text if response_obj is not None else "No response object"
        return jsonify({"error": f"HTTP error checking slot availability: {http_err}", "details": details}), status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Request exception while checking slot: {str(e)}"}), 503
    except ValueError as e:
        return jsonify({"error": f"Failed to decode JSON for slot check: {str(e)}"}), 500

@app.route('/')
def home():
    return "Ferry Ticket Checker Backend is running."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)
