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
    """Converts ISO datetime string to HH:MM format in UTC."""
    if not iso_string:
        return "N/A"
    try:
        # Handle various ISO 8601 formats that might appear
        if 'Z' in iso_string: # UTC 'Zulu' time
            if '.' in iso_string: # With milliseconds
                dt_object = datetime.strptime(iso_string, "%Y-%m-%dT%H:%M:%S.%f%z")
            else: # Without milliseconds
                dt_object = datetime.strptime(iso_string, "%Y-%m-%dT%H:%M:%S%z")
        elif '+' in iso_string.split('T')[1]: # With explicit timezone offset
             dt_object = datetime.fromisoformat(iso_string)
        else: # No explicit timezone info, assume it might be local or needs context
            dt_object = datetime.fromisoformat(iso_string)
            if dt_object.tzinfo is None: # Assume UTC if naive
                 dt_object = dt_object.replace(tzinfo=timezone.utc)

        return dt_object.astimezone(timezone.utc).strftime("%H:%M")
    except ValueError as e:
        print(f"Could not parse date: {iso_string}, Error: {e}")
        parts = iso_string.split('T')
        if len(parts) > 1 and len(parts[1]) >= 5:
            return parts[1][:5] # Fallback to extracting HH:MM
        return iso_string

@app.route('/api/get_schedule', methods=['GET'])
def get_schedule():
    direction = request.args.get('direction')
    departure_date_str = request.args.get('date')
    auth_header = request.headers.get('Authorization')

    if not direction or not departure_date_str:
        return jsonify({"error": "Missing direction or date parameter"}), 400
    if not auth_header:
        return jsonify({"error": "Missing Authorization header"}), 401
    try:
        datetime.strptime(departure_date_str, '%Y-%m-%d') # Validate date format
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    target_url = f"{PRAAMID_API_BASE_URL}?direction={direction}&departure-date={departure_date_str}&time-shift=300"
    headers = {'Authorization': auth_header, 'Accept': 'application/json'}
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
        if status_code == 401:
             return jsonify({"error": "Authorization failed. Token may be invalid or expired."}), 401
        return jsonify({"error": f"HTTP error occurred: {http_err}", "details": details}), status_code
    except requests.exceptions.RequestException as e: # More generic network/request error
        return jsonify({"error": f"Request exception: {str(e)}"}), 503
    except ValueError as e: # Catches JSONDecodeError
        return jsonify({"error": f"Failed to decode JSON response: {str(e)}"}), 500


def get_ticket_item_details_from_praamid(auth_header, pricelist_code, departure_date, num_cars, num_adults, vehicle_reg_nr_from_user=None):
    item_details_for_payload = []
    common_headers = {'Authorization': auth_header, 'Accept': 'application/json'}

    try:
        mappings_response = requests.get(PRAAMID_ITEM_MAPPINGS_URL, headers=common_headers, timeout=7)
        mappings_response.raise_for_status()
        mappings = mappings_response.json().get("items", [])
    except Exception as e:
        return None, f"Could not fetch item mappings: {str(e)}"

    try:
        prices_url = PRAAMID_PRICES_URL_TEMPLATE.format(pricelist_code=pricelist_code, date=departure_date)
        prices_response = requests.get(prices_url, headers=common_headers, timeout=7)
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
        elif num_cars > 0: # Only error if cars were requested but code/price not found
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
        elif num_adults > 0: # Only error if adults were requested but code/price not found
             return None, f"Adult passenger item code '{adult_item_code_found}' (P/REGULAR) not found in price map or mappings."

    if not item_details_for_payload and (num_cars > 0 or num_adults > 0) :
        return None, "No items could be prepared for booking (car/adult types not found or priced)."

    return item_details_for_payload, None


@app.route('/api/add_to_cart', methods=['POST'])
def add_to_cart():
    data = request.get_json()
    auth_header = request.headers.get('Authorization')

    if not auth_header: return jsonify({"error": "Missing Authorization header"}), 401
    if not data: return jsonify({"error": "Missing request payload"}), 400

    required_fields = ['original_event_data', 'direction', 'departureDate', 'numCars', 'numAdults']
    for field in required_fields:
        if field not in data: return jsonify({"error": f"Missing field in payload: {field}"}), 400

    original_event_data = data['original_event_data']
    direction_code = data['direction']
    departure_date = data['departureDate']

    pricelist_code = data.get('pricelistCode')
    # Fallback logic for pricelist_code if not directly in data but nested in original_event_data
    if not pricelist_code:
        if original_event_data.get("pricelist") and original_event_data["pricelist"].get("code"):
            pricelist_code = original_event_data["pricelist"].get("code")
        elif original_event_data.get("original_event_data", {}).get("pricelist") and \
             original_event_data["original_event_data"]["pricelist"].get("code"):
            pricelist_code = original_event_data["original_event_data"]["pricelist"].get("code")

    if not pricelist_code: # Final check
        return jsonify({"error": "Missing pricelistCode, cannot determine item prices."}), 400

    num_cars = int(data['numCars'])
    num_adults = int(data['numAdults'])

    vehicle_reg_nr_for_payload = data.get("vehicleRegNr", "") if num_cars > 0 else ""
    # Add warning if car is booked but no reg_nr provided by frontend (frontend currently doesn't ask for it)
    if num_cars > 0 and not vehicle_reg_nr_for_payload:
        print("Warning: Car booked but vehicleRegNr not provided by frontend. Praamid.ee might require it or auto-fill.")


    boarding_passes, error_msg = get_ticket_item_details_from_praamid(
        auth_header, pricelist_code, departure_date, num_cars, num_adults, vehicle_reg_nr_for_payload
    )

    if error_msg: return jsonify({"error": error_msg}), 500
    # If no items were requested (0 cars, 0 adults), boarding_passes will be empty.
    # If items were requested but couldn't be prepared (e.g. price not found), error_msg handles it.
    if not boarding_passes and (num_cars > 0 or num_adults > 0):
        return jsonify({"error": "Failed to prepare any valid items for booking (e.g., item codes or prices not found)."}), 500
    if num_cars == 0 and num_adults == 0 : # Explicitly check if no items were intended for booking
         return jsonify({"error": "No items (cars or adults) specified for booking."}), 400

    user_email_placeholder = data.get("userEmail", "user@example.com")
    user_phone_placeholder = data.get("userPhone", "12345678")

    # Extract event details from original_event_data.original_event_data which was passed from /get_schedule
    event_source_data = original_event_data.get("original_event_data", {})
    event_for_payload = {
        "dtstart": event_source_data.get("dtstart"),
        "dtend": event_source_data.get("dtend"),
        "uid": event_source_data.get("uid"), # This should be the event UID from the /events API
        "pricelist": {"code": pricelist_code},
        "transportationType": event_source_data.get("transportationType"),
        "ship": event_source_data.get("ship")
    }

    direction_obj_for_payload = {"code": direction_code}
    if event_source_data.get("direction"):
        direction_obj_for_payload = event_source_data.get("direction")

    booking_payload = {
        "tickets": [{
            "boardingPasses": boarding_passes,
            "services": [], "attachments": [],
            "customer": {"email": user_email_placeholder},
            "phoneNumber": user_phone_placeholder,
            "smsNotification": False, "smsDepartureNotification": False, "calendarInvite": False,
            "direction": direction_obj_for_payload,
            "directionCode": direction_code,
            "event": event_for_payload,
            "pricelist": {"code": pricelist_code},
            "pos": {"code": "CP"}
        }],
        "customer": {"email": user_email_placeholder}
    }

    post_headers = {
        'Authorization': auth_header,
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/plain, */*',
        'Origin': 'https://www.praamid.ee',
        'Referer': 'https://www.praamid.ee/portal/ticket/departure'
    }

    booking_response_obj = None

    try:
        print(f"Attempting to POST to {PRAAMID_BOOKINGS_URL} with payload: {booking_payload}")
        booking_response_obj = requests.post(PRAAMID_BOOKINGS_URL, headers=post_headers, json=booking_payload, timeout=20)
        booking_response_obj.raise_for_status()
        booking_confirmation = booking_response_obj.json()
        booking_uid = booking_confirmation.get("response")

        if booking_uid:
            checkout_url = f"https://www.praamid.ee/portal/ticket/checkout?bookingUid={booking_uid}"
            return jsonify({
                "message": "Successfully created booking.",
                "bookingUid": booking_uid,
                "checkoutUrl": checkout_url
            }), 201
        else:
            return jsonify({"error": "Booking created but UID not found in response.", "details": booking_confirmation}), 500
    except requests.exceptions.HTTPError as http_err:
        status_code = getattr(booking_response_obj, 'status_code', 500)
        details_text = booking_response_obj.text if booking_response_obj is not None else "No response text"
        details_json = {}
        try:
            if booking_response_obj is not None: details_json = booking_response_obj.json()
        except ValueError: pass # Keep text if not json

        print(f"HTTP Error from Praamid: {status_code}, Response: {details_text}")
        return jsonify({"error": f"HTTP error creating booking on Praamid.ee ({http_err})",
                        "praamid_status_code": status_code,
                        "praamid_details_json": details_json,
                        "praamid_details_text": details_text
                        }), status_code
    except requests.exceptions.RequestException as e:
        print(f"Network error while creating booking: {str(e)}")
        return jsonify({"error": f"Network error while creating booking: {str(e)}"}), 503
    except ValueError as e:
        print(f"JSON decode error for Praamid response: {str(e)}")
        return jsonify({"error": f"Failed to decode JSON response from Praamid.ee during booking creation: {str(e)}"}), 500

@app.route('/')
def home():
    return "Ferry Ticket Checker Backend is running."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)
