# Backend Flask application
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests # Renamed from http_requests for conventional import
import os
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

PRAAMID_API_BASE_URL = "https://www.praamid.ee/online/events"

def format_time_from_iso(iso_string):
    """Converts ISO datetime string to HH:MM format in UTC."""
    if not iso_string:
        return None
    try:
        dt_object = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt_object.strftime("%H:%M")
    except ValueError:
        # Fallback for slightly different ISO formats if necessary, or log error
        try:
            # Attempt to parse if it has milliseconds and Z
            dt_object = datetime.strptime(iso_string, "%Y-%m-%dT%H:%M:%S.%f%z")
            return dt_object.astimezone(timezone.utc).strftime("%H:%M")
        except ValueError:
            print(f"Could not parse date: {iso_string}")
            return iso_string # Or some error indicator


@app.route('/api/get_schedule', methods=['GET'])
def get_schedule():
    direction = request.args.get('direction')
    departure_date_str = request.args.get('date')
    auth_header = request.headers.get('Authorization')

    if not direction or not departure_date_str:
        return jsonify({"error": "Missing direction or date parameter"}), 400

    if not auth_header:
        return jsonify({"error": "Missing Authorization header"}), 401

    # Validate date format (YYYY-MM-DD)
    try:
        datetime.strptime(departure_date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    # Construct the target API URL
    # Using a fixed time-shift as discovered. This might need adjustment if it's dynamic.
    target_url = f"{PRAAMID_API_BASE_URL}?direction={direction}&departure-date={departure_date_str}&time-shift=300"

    headers = {
        'Authorization': auth_header,
        'Accept': 'application/json, text/plain, */*',
        # Add any other necessary headers identified from browser inspection if needed
        # 'User-Agent': 'Mozilla/5.0 ...' # Could be added if requests are blocked
    }

    try:
        response = requests.get(target_url, headers=headers, timeout=10) # Added timeout
        response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)

        praamid_data = response.json()

        processed_items = []
        if praamid_data and 'items' in praamid_data:
            for item in praamid_data['items']:
                # For the booking URL, we need the original dtstart
                # For display, we can format it if needed, but frontend will handle local time display
                pricelist_info = item.get("pricelist", {})
                processed_items.append({
                    "uid": item.get("uid"), # Added UID
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

PRAAMID_ITEM_MAPPINGS_URL = "https://www.praamid.ee/online/item-mappings"
PRAAMID_PRICES_URL_TEMPLATE = "https://www.praamid.ee/online/prices?pricelist={pricelist_code}&date={date}"
PRAAMID_BOOKINGS_URL = "https://www.praamid.ee/online/bookings"

# --- Helper function to get item codes and prices ---
# This is a simplified version. A more robust solution might involve caching these mappings.
def get_ticket_item_details(auth_header, pricelist_code, departure_date, num_cars, num_adults, vehicle_reg_nr=None):
    item_details = []

    # 1. Fetch item mappings
    try:
        mappings_response = requests.get(PRAAMID_ITEM_MAPPINGS_URL, headers={'Authorization': auth_header, 'Accept': 'application/json'}, timeout=5)
        mappings_response.raise_for_status()
        mappings = mappings_response.json().get("items", [])
    except Exception as e:
        print(f"Error fetching item mappings: {e}")
        return None, f"Could not fetch item mappings: {e}"

    # 2. Fetch prices for the specific pricelist and date
    try:
        prices_url = PRAAMID_PRICES_URL_TEMPLATE.format(pricelist_code=pricelist_code, date=departure_date)
        prices_response = requests.get(prices_url, headers={'Authorization': auth_header, 'Accept': 'application/json'}, timeout=5)
        prices_response.raise_for_status()
        prices_data = prices_response.json().get("items", [])

        price_map = {p["item"]["code"]: p["amount"] for p in prices_data if "item" in p and "code" in p["item"]}
    except Exception as e:
        print(f"Error fetching prices: {e}")
        return None, f"Could not fetch prices: {e}"

    # Find car item code and price
    if num_cars > 0:
        car_item_code = None
        for mapping in mappings:
            if mapping.get("capacityUnitCode") == "M1" and mapping.get("priceCategory") == "REGULAR": # Assuming M1 is car and REGULAR price
                car_item_code = mapping.get("itemCode") # e.g., "S06"
                break
        if car_item_code and car_item_code in price_map:
            item_details.append({
                "capacityUnit": {"code": "M1"}, # Simplified, Praamid payload is more verbose
                "quantity": num_cars,
                "item": {"code": car_item_code},
                "itemPrice": price_map[car_item_code],
                "amount": price_map[car_item_code] * num_cars,
                "vehicleRegNr": vehicle_reg_nr or "", # Add vehicle reg number if provided
                "vehicleCountry": {"code": "EST"} if vehicle_reg_nr else {}, # Assuming EST if reg_nr is present
                "dci": "D" # From observed payload
            })
        else:
            return None, f"Could not determine item code or price for passenger car (M1, REGULAR) with item code {car_item_code}."

    # Find adult passenger item code and price
    if num_adults > 0:
        adult_item_code = None
        for mapping in mappings:
            if mapping.get("capacityUnitCode") == "P" and mapping.get("priceCategory") == "REGULAR": # Assuming P is passenger
                adult_item_code = mapping.get("itemCode") # e.g., "R01"
                break
        if adult_item_code and adult_item_code in price_map:
            item_details.append({
                "capacityUnit": {"code": "P"},
                "quantity": num_adults,
                "item": {"code": adult_item_code},
                "priceCategory": {"code": "REGULAR"},
                "itemPrice": price_map[adult_item_code],
                "amount": price_map[adult_item_code] * num_adults,
                "dci": "D", # From observed payload
                "vehicleRegNr": ""
            })
        else:
            return None, f"Could not determine item code or price for adult passenger (P, REGULAR) with item code {adult_item_code}."

    if not item_details:
        return None, "No items were specified for booking or item codes/prices could not be found."

    return item_details, None


@app.route('/api/add_to_cart', methods=['POST'])
def add_to_cart():
    data = request.get_json()
    auth_header = request.headers.get('Authorization')

    if not auth_header:
        return jsonify({"error": "Missing Authorization header"}), 401
    if not data:
        return jsonify({"error": "Missing request payload"}), 400

    required_fields = ['original_event_data', 'direction', 'departureDate', 'pricelistCode', 'numCars', 'numAdults']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field in payload: {field}"}), 400

    original_event_data = data['original_event_data']
    direction_code = data['direction']
    departure_date = data['departureDate'] # YYYY-MM-DD
    pricelist_code = data['pricelistCode']
    num_cars = int(data['numCars'])
    num_adults = int(data['numAdults'])
    # vehicle_reg_nr = data.get('vehicleRegNr', None) # Assuming frontend might send this

    # --- Get item codes and prices ---
    # This part assumes the user's details (like email, phone, personal ID for discounts)
    # are implicitly handled by Praamid.ee based on the auth_header.
    # If specific discountSubjects or customer details from token are needed, this logic would be more complex.

    # For now, let's assume vehicleRegNr is hardcoded or obtained differently for simplicity, as it's not in the current frontend flow to ask for it.
    # In a real scenario, if num_cars > 0, we'd need the vehicle_reg_nr.
    # For this example, if a car is added, we'll use a placeholder or make it optional.
    # The provided payload had "219TNY".
    vehicle_reg_nr_for_payload = "219TNY" if num_cars > 0 else "" # Example, needs to be dynamic or from user input

    boarding_passes, error_msg = get_ticket_item_details(
        auth_header, pricelist_code, departure_date, num_cars, num_adults, vehicle_reg_nr_for_payload
    )

    if error_msg:
        return jsonify({"error": error_msg}), 500
    if not boarding_passes: # Should be caught by error_msg, but as a safeguard
        return jsonify({"error": "Failed to prepare items for booking."}), 500

    # --- Construct the final payload for Praamid.ee /online/bookings ---
    # This structure is based on the user-provided payload.
    # Customer email/phone might need to be fetched or assumed from token context by Praamid.
    # For simplicity, we'll use placeholders or omit if not strictly required by the API.
    # The provided payload had customer email at two levels.

    # Attempt to get user email from token (very basic parsing, not robust for production)
    user_email = "user@example.com" # Placeholder
    user_phone = "12345678" # Placeholder
    # Ideally, you'd have an endpoint like /api/me that uses the token to get user details from Praamid.ee

    booking_payload = {
        "tickets": [{
            "boardingPasses": boarding_passes,
            "services": [],
            "attachments": [],
            "customer": {"email": user_email}, # Placeholder
            "phoneNumber": user_phone, # Placeholder
            "smsNotification": False,
            "smsDepartureNotification": False,
            "calendarInvite": False,
            "direction": original_event_data.get("direction", {"code": direction_code}), # Use original if available
            "directionCode": direction_code,
            "event": { # Key details from the original event
                "dtstart": original_event_data.get("dtstart"),
                "dtend": original_event_data.get("dtend"),
                "uid": original_event_data.get("event_uid") or original_event_data.get("uid"), # Use event_uid if renamed
                "pricelist": {"code": pricelist_code},
                "transportationType": original_event_data.get("transportationType", {}),
                "ship": original_event_data.get("ship", {}),
                "capacities": original_event_data.get("capacities", {}), # May not be needed by POST but good to have context
                "status": original_event_data.get("status", "CONFIRMED")
            },
            "pricelist": {"code": pricelist_code},
            "pos": {"code": "CP"} # As seen in payload
        }],
        "customer": {"email": user_email} # Placeholder
    }

    # --- Make the POST request to Praamid.ee ---
    post_headers = {
        'Authorization': auth_header,
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/plain, */*',
        'Origin': 'https://www.praamid.ee', # Mimic browser behavior
        'Referer': 'https://www.praamid.ee/portal/ticket/departure' # Mimic browser behavior
    }

    try:
        booking_response = requests.post(PRAAMID_BOOKINGS_URL, headers=post_headers, json=booking_payload, timeout=15)
        booking_response.raise_for_status() # Check for HTTP errors

        booking_confirmation = booking_response.json()
        booking_uid = booking_confirmation.get("response")

        if booking_uid:
            checkout_url = f"https://www.praamid.ee/portal/ticket/checkout?bookingUid={booking_uid}"
            return jsonify({
                "message": "Successfully created booking.",
                "bookingUid": booking_uid,
                "checkoutUrl": checkout_url
            }), 201 # 201 Created
        else:
            return jsonify({"error": "Booking created but UID not found in response.", "details": booking_confirmation}), 500

    except requests.exceptions.HTTPError as http_err:
        error_details = {"error_message": str(http_err)}
        try:
            error_details["praamid_response"] = booking_response.json()
        except ValueError: # If response is not JSON
             error_details["praamid_response_text"] = booking_response.text
        return jsonify({"error": f"HTTP error creating booking on Praamid.ee", "details": error_details}), booking_response.status_code
    except requests.exceptions.RequestException as req_err:
        return jsonify({"error": f"Network error while creating booking: {req_err}"}), 503
    except ValueError as json_err: # Includes JSONDecodeError for booking_response.json()
        return jsonify({"error": "Failed to decode JSON response from Praamid.ee during booking creation."}), 500


    except requests.exceptions.HTTPError as http_err:
        if response.status_code == 401:
             return jsonify({"error": "Authorization failed. Token may be invalid or expired."}), 401
        return jsonify({"error": f"HTTP error occurred: {http_err}", "details": response.text}), response.status_code
    except requests.exceptions.ConnectionError as conn_err:
        return jsonify({"error": f"Error connecting to Praamid.ee: {conn_err}"}), 503
    except requests.exceptions.Timeout as timeout_err:
        return jsonify({"error": f"Request to Praamid.ee timed out: {timeout_err}"}), 504
    except requests.exceptions.RequestException as req_err:
        return jsonify({"error": f"An unexpected error occurred: {req_err}"}), 500
    except ValueError as json_err: # Includes JSONDecodeError
        return jsonify({"error": "Failed to decode JSON response from Praamid.ee"}), 500


@app.route('/')
def home():
    return "Ferry Ticket Checker Backend is running."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    # For local development, typically debug=True is fine.
    # For production, use a proper WSGI server like Gunicorn and set debug=False.
    app.run(debug=True, host='0.0.0.0', port=port)
