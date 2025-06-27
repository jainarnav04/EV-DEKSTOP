from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import firebase_admin
from firebase_admin import credentials, firestore 
from datetime import datetime, date, timedelta # Use direct imports for datetime, date, timedelta
import os
from dotenv import load_dotenv
load_dotenv()
# --- SendGrid imports ---
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Flask app initialization
app = Flask(__name__)

# ==================== EMAIL OTP SENDER ====================
def send_otp_email(receiver_email, otp):
    """
    Send an OTP email using SendGrid API.
    Credentials are loaded from environment variables:
    - SENDGRID_API_KEY
    - EMAIL_SENDER
    """
    sender_email = os.environ.get("EMAIL_SENDER")
    sendgrid_api_key = os.environ.get("SENDGRID_API_KEY")
    if not sender_email or not sendgrid_api_key:
        raise Exception("SendGrid credentials not set in environment variables.")

    message = Mail(
        from_email=sender_email,
        to_emails=receiver_email,
        subject="Your Easy Vahan Login Credentials Reset Request",
        plain_text_content=f"Your OTP is: {otp}\n\nThis OTP is valid for 5 minutes.\nIf you did not request this, please ignore this email.\n\nThanks,\nEasy Vahan Team"
    )
    try:
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        print(f"OTP sent to {receiver_email}, status code: {response.status_code}")
    except Exception as e:
        print(f"Error sending OTP email: {e}")
        raise


# Custom Exception Classes
class InvalidUsage(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['error'] = self.message
        return rv

class UnauthorizedError(InvalidUsage):
    status_code = 403

class MissingDataError(InvalidUsage):
    status_code = 400

class NotFoundError(InvalidUsage):
    status_code = 404

class CalculationError(InvalidUsage):
    status_code = 500

print("Starting application...")  # Debug print

def ev_charging_time(current_percent, target_percent, charger_power_kw, battery_capacity_kwh,
                     charging_efficiency=0.9):
    """Calculate charging time using a modified logistic model, handling edge cases"""
    if not (0 <= current_percent <= 100 and 0 <= target_percent <= 100):
        raise ValueError("Percentages must be between 0 and 100")
    
    # Special cases to avoid math errors
    if current_percent >= target_percent:
        return 0.0
    if current_percent == 0:
        current_percent = 0.1  # Avoid division by zero
    if target_percent == 100:
        target_percent = 99.9  # Avoid division by zero

    percent_to_charge = target_percent - current_percent
    energy_needed_kwh = (percent_to_charge / 100) * battery_capacity_kwh
    charge_time_hours = energy_needed_kwh / (charger_power_kw * charging_efficiency)
    return charge_time_hours

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback_secret_for_dev_only") # Required for Flask sessions

print("Initializing Firebase...")  # Debug print
# Initialize Firebase
import os

# Use environment variable for credential path in deployment, fallback to local file for development
firebase_cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
cred = credentials.Certificate(firebase_cred_path)
firebase_admin.initialize_app(cred)
db = firestore.client()
print("Firebase initialized successfully!")  # Debug print

@app.route("/", methods=["GET", "POST"])
def login_register():
    if request.method == "GET":
        return render_template("login.html")  # Ensure login.html is inside "templates" folder

    try:
        data = request.json
        print(f"Received Data: {data}")  # Debugging

        action = data.get("action")  # Determines if it's login or register
        station_id = data.get("station_id")
        access_key = data.get("access_key")

        if not station_id or not access_key:
            return jsonify({"error": "Missing credentials!"}), 400

        doc_ref = db.collection("charging_stations").document(station_id)

        if action == "login":
            doc = doc_ref.get()
            if doc.exists:
                station_data = doc.to_dict()
                if station_data["access_key"] == access_key:
                    session["station_id"] = station_id  # Store station_id in the session
                    return jsonify({
                        "message": "Login successful!", 
                        "station_data": station_data,
                        "redirect": "/dashboard"  # Optional: instruct the frontend to redirect
                    }), 200
                return jsonify({"error": "Invalid access key!"}), 401
            return jsonify({"error": "Station ID not found!"}), 404

        elif action == "register":
            name = data.get("name")
            email = data.get("email")
            if not name or not email:
                return jsonify({"error": "Missing station name or email!"}), 400

            # Check if station ID already exists
            if doc_ref.get().exists:
                return jsonify({"error": "Station ID already exists!"}), 400
                
            # Check if email is already registered (case-insensitive)
            stations_ref = db.collection("charging_stations")
            email_query = stations_ref.where("email", "==", email.lower().strip()).limit(1)
            email_docs = list(email_query.stream())
            
            if email_docs:
                return jsonify({"error": "This email is already registered with another station!"}), 400

            # Create new station
            doc_ref.set({
                "station_id": station_id,
                "access_key": access_key,
                "name": name,
                "email": email.lower().strip()
            })
            
            return jsonify({
                "message": "Registration successful!",
                "station_id": station_id,
                "email": email.lower().strip(),
                "name": name
            }), 201

        return jsonify({"error": "Invalid action!"}), 400

    except Exception as e:
        print(f"An error occurred in login_register: {e}")
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

@app.route("/reset-access-key", methods=["POST"])
def reset_access_key():
    data = request.json
    station_id = data.get("station_id")
    email = data.get("email")

    if not station_id and not email:
        return jsonify({"success": False, "message": "Missing Station ID or Email!"}), 400

    doc_ref = db.collection("charging_stations").document(station_id)
    doc = doc_ref.get()

    if doc.exists:
        station_data = doc.to_dict()
        if station_data.get("email") == email:
            print(f"Simulating sending reset link to {email} for Station ID: {station_id}")
            # --- Email Sending Integration ---
            # Generate a secure random 6-digit OTP
            import secrets
            from datetime import timezone
            otp = str(secrets.randbelow(900000) + 100000)
            # Store OTP with expiration time (5 minutes from now)
            otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
            doc_ref.update({
                'reset_otp': otp,
                'reset_otp_expiry': otp_expiry
            })
            send_otp_email(email, otp)
            print(f"Successfully sent OTP to {email}")
            # In a real application, you would integrate with an email service here

            # Example (using a hypothetical `send_email` function):
            # try:
            #     send_email(
            #         to_email=email,
            #         subject="Your EV-App Access Key Reset Request",
            #         body=f"Hello,\n\nYou requested an access key reset for your station ID: {station_id}.\nYour access key is: {station_data['access_key']}\n\nPlease keep this secure.\n\nThanks,\nEV-App Team"
            #     )
            #     print(f"Successfully sent reset link to {email}")
            # except Exception as email_exc:
            #     print(f"Error sending email: {email_exc}")
            #     # Consider returning an error here, or logging it and proceeding
            # ---------------------------------------------
            return jsonify({"success": True, "message": "OTP sent to your registered email. Enter the OTP to reset your access key."}), 200
        else:
            return jsonify({"success": False, "message": "Station ID and Email do not match."}), 404
    else:
        return jsonify({"success": False, "message": "Station ID not found."}), 404

@app.route("/dashboard")
def dashboard():
    if "station_id" not in session:
        print("No station_id found in session!")  # Debugging
        return redirect(url_for("login_register"))  # Redirect to login if session is missing

    station_id = session["station_id"]
    print(f"Station ID from session: {station_id}")  # Debugging

    doc_ref = db.collection("charging_stations").document(station_id)
    doc = doc_ref.get()

    if doc.exists:
        station_data = doc.to_dict()
        print("Station data loaded for dashboard:", station_data) # Debug print
        print("Station Charging Type from DB:", station_data.get("chargingType")) # Debug print for charging type
        
        # Fetch vehicles associated with this station from the vehicles subcollection
        vehicles_ref = db.collection("charging_stations").document(station_id).collection("vehicles").order_by("arrival_time") # Order by arrival_time
        vehicles = []
        for doc in vehicles_ref.stream():
            vehicle_data = doc.to_dict()
            vehicle_data["id"] = doc.id  # Add the document ID to the vehicle data
            # Ensure start_time and end_time are present and are full datetime strings
            arrival_time = vehicle_data.get('arrival_time')
            charging_time = vehicle_data.get('charging_time_minutes')
            if arrival_time and charging_time is not None:
                # Parse arrival_time if string
                if isinstance(arrival_time, str):
                    try:
                        arrival_dt = datetime.strptime(arrival_time, '%Y-%m-%d %H:%M')
                    except Exception:
                        arrival_dt = None
                else:
                    arrival_dt = arrival_time
                if arrival_dt:
                    vehicle_data['start_time'] = arrival_dt.strftime('%Y-%m-%d %H:%M')
                    end_dt = arrival_dt + timedelta(minutes=int(charging_time))
                    vehicle_data['end_time'] = end_dt.strftime('%Y-%m-%d %H:%M')
            vehicles.append(vehicle_data)

        # --- Compute free time for each slot with queue logic ---
        from collections import defaultdict
        slot_queues = defaultdict(list)
        for v in vehicles:
            slot = v.get('slot_number') or v.get('slot') or 1
            slot_queues[slot].append(v)
        slot_free_time = {}
        from datetime import datetime
        now = datetime.now()
        # Get all possible slots (from vehicles and from station data if available)
        all_slots = set(slot_queues.keys())
        total_slots = station_data.get('totalSlots') or station_data.get('total_slots')
        if total_slots:
            all_slots.update(range(1, int(total_slots) + 1))
        print("--- Slot Queue Debug ---")
        for slot in sorted(all_slots):
            queue = slot_queues.get(slot, [])
            # Sort vehicles by arrival_time (parsed as datetime)
            queue_sorted = sorted(queue, key=lambda v: datetime.strptime(v['arrival_time'], '%Y-%m-%d %H:%M')) if queue else []
            if queue_sorted:
                first_arrival = datetime.strptime(queue_sorted[0]['arrival_time'], '%Y-%m-%d %H:%M')
                prev_end = min(now, first_arrival)
            else:
                prev_end = now
            print(f"Slot {slot} queue:")
            for idx, v in enumerate(queue_sorted):
                arrival_time = v.get('arrival_time')
                charging_time = v.get('charging_time_minutes')
                if isinstance(arrival_time, str):
                    try:
                        arrival_dt = datetime.strptime(arrival_time, '%Y-%m-%d %H:%M')
                    except Exception:
                        arrival_dt = now
                else:
                    arrival_dt = arrival_time or now
                start_dt = max(arrival_dt, prev_end)
                end_dt = start_dt + timedelta(minutes=int(charging_time) if charging_time is not None else 0)
                print(f"  Vehicle {v.get('vehicle_number','?')} (id={v.get('id')}) arrives {arrival_dt}, starts {start_dt}, ends {end_dt}")
                prev_end = end_dt
            # The slot is free after the last vehicle ends (or now if empty)
            slot_free_time[slot] = prev_end.strftime('%Y-%m-%d %H:%M')
            print(f"  Slot {slot} free at: {slot_free_time[slot]}")
        print("Slot free times:", slot_free_time)

        # Dynamically calculate available slots just before rendering
        total_slots = station_data.get('totalSlots') or station_data.get('total_slots')
        charging_count = sum(1 for v in vehicles if v.get('status', '').upper() == 'CHARGING')
        available_slots = max(int(total_slots) - charging_count, 0) if total_slots else 0
        google_maps_api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
        return render_template("dashboard.html", station=station_data, vehicles=vehicles, slot_free_time=slot_free_time, available_slots=available_slots, google_maps_api_key=google_maps_api_key)  # Pass vehicles data and dynamic available_slotsa and dynamic available_slots
    else:
        return "Error: Station not found", 404


@app.route("/update_station", methods=["POST"])
def update_station():
    if "station_id" not in session:
        raise UnauthorizedError("Not logged in!")

    data = request.json
    print("Update Station Data:", data)  # Debug print
    station_id = session["station_id"]

    # Validate required fields for update
    required_fields = ["stationName", "operatorName", "chargingType", "location", "totalSlots", "chargingRate"]
    for field in required_fields:
        if data.get(field) is None:
            raise MissingDataError(f"Missing data for required field: {field}!")

    try:
        total_slots = int(data.get("totalSlots"))
        charging_rate = int(data.get("chargingRate"))
    except ValueError:
        raise InvalidUsage("Invalid data type for slots or charging rate. Must be integers.")
    if total_slots <= 0:
        raise InvalidUsage("Total slots must be a positive number.")
    if charging_rate <= 0:
        raise InvalidUsage("Charging rate must be a positive number.")

    # Get current vehicles charging
    doc_ref = db.collection("charging_stations").document(station_id)
    vehicles_ref = doc_ref.collection("vehicles")
    charging_vehicles = [doc.to_dict() for doc in vehicles_ref.stream() if doc.to_dict().get('status', '').upper() == 'CHARGING']
    charging_count = len(charging_vehicles)
    # available_slots = total_slots - charging_count, but never below 0
    available_slots = max(total_slots - charging_count, 0)

    update_data = {
        "name": data.get("stationName"),
        "operator": data.get("operatorName"),
        "chargingType": data.get("chargingType"),
        "location": data.get("location"),
        "total_slots": total_slots,
        "available_slots": available_slots,
        "charging_rate": charging_rate,
        "latitude": float(data.get("latitude")) if data.get("latitude") else None,
        "longitude": float(data.get("longitude")) if data.get("longitude") else None
    }

    doc_ref = db.collection("charging_stations").document(station_id)
    if not doc_ref.get().exists:
        raise NotFoundError("Station not found!")

    try:
        doc_ref.update(update_data)
        updated_doc = doc_ref.get()
        print("Updated document data:", updated_doc.to_dict())  # Debug print
        return jsonify({"message": "Station details updated successfully!"}), 200
    except Exception as e:
        import traceback
        print(f"An error occurred during station update: {e}")
        print(traceback.format_exc())
        raise InvalidUsage(f"An error occurred while updating station details: {str(e)}", status_code=500)

def estimate_final_battery(initial_battery_level, charging_time_minutes, battery_capacity_kWh, charging_type):
    """
    Estimate the final battery percentage after a given charging time.
    Args:
        initial_battery_level (float): Initial battery percentage (0-100)
        charging_time_minutes (int): Charging time in minutes
        battery_capacity_kWh (float): Battery capacity in kWh
        charging_type (str): Type of charger (AC Type 1, AC Type 2, CCS, CHAdeMO, GB/T)
    Returns:
        float: Estimated final battery percentage (capped at 100)
    """
    # Charging speeds (kW) and efficiencies by type
    charging_speeds = {
        "AC Type 1": 7.4, "AC Type 2": 22.0, "CCS": 150.0, "CHAdeMO": 62.5, "GB/T": 120.0
    }
    charging_efficiencies = {
        "AC Type 1": 0.85, "AC Type 2": 0.88, "CCS": 0.92, "CHAdeMO": 0.92, "GB/T": 0.90
    }
    charger_power = charging_speeds.get(charging_type, 7.4)
    efficiency = charging_efficiencies.get(charging_type, 0.85)
    hours = charging_time_minutes / 60.0
    energy_added = charger_power * hours * efficiency  # kWh
    percent_added = (energy_added / battery_capacity_kWh) * 100
    final_percent = initial_battery_level + percent_added
    final_percent = min(max(final_percent, 0), 100)
    return round(final_percent, 1)

@app.route("/add_vehicle", methods=["POST"])
def add_vehicle():
    if "station_id" not in session:
        raise UnauthorizedError("Not logged in!")

    data = request.json
    print("Add Vehicle Data:", data)  # Debug print
    station_id = session["station_id"]

    # Validate required fields
    # Accept either targetBatteryLevel or targetChargeMinutes (or both, prioritize minutes)
    required_fields = ["vehicleNumber", "arrivalTime", "chargingType", "initialBatteryLevel", "batteryCapacity"]
    for field in required_fields:
        if data.get(field) is None:
            raise MissingDataError(f"Missing data for required field: {field}!")

    try:
        vehicle_number = data.get("vehicleNumber")
        arrival_time_str = data.get("arrivalTime")
        chargingType = data.get("chargingType")
        initial_battery_level = float(data.get("initialBatteryLevel"))
        battery_capacity = float(data.get("batteryCapacity"))
        # Optional fields
        target_battery_level = data.get("targetBatteryLevel")
        charging_time_minutes = data.get("charging_time_minutes") or data.get("targetChargeMinutes")
        target_battery_level = float(target_battery_level) if target_battery_level not in (None, "") else None
        charging_time_minutes = int(charging_time_minutes) if charging_time_minutes not in (None, "") else None
    except ValueError:
        raise InvalidUsage("Invalid data type for battery levels, capacity, or minutes. Must be numbers.")

    # Require at least one of target_battery_level or charging_time_minutes
    if target_battery_level is None and charging_time_minutes is None:
        raise MissingDataError("Please provide either a target battery level or charging time in minutes.")

    if not vehicle_number:
        raise MissingDataError("Vehicle number cannot be empty!")
    if initial_battery_level < 0 or initial_battery_level > 100:
        raise InvalidUsage("Initial battery level must be between 0 and 100.")
    if battery_capacity <= 0:
        raise InvalidUsage("Battery capacity must be a positive number.")
    if not chargingType:
        raise MissingDataError("Charging Type is required!")

    # Validation for target_battery_level
    if target_battery_level is not None:
        if target_battery_level < 0 or target_battery_level > 100:
            raise InvalidUsage("Target battery level must be between 0 and 100.")
        if target_battery_level <= initial_battery_level:
            raise InvalidUsage("Target battery level must be greater than initial battery level.")
    # Validation for charging_time_minutes
    if charging_time_minutes is not None:
        if charging_time_minutes <= 0:
            raise InvalidUsage("Charging time in minutes must be greater than 0.")

    try:
        # Prioritize minutes if provided
        estimated_final_battery = None
        if charging_time_minutes is not None:
            charging_time_min = charging_time_minutes
            # Charging cost calculation for charging_time_minutes scenario (match frontend logic)
            charging_speeds = {
        "AC Type 1": 7.4,    # 7.4 kW
        "AC Type 2": 22.0,   # 22 kW
        "CCS": 150.0,        # 150 kW
        "CHAdeMO": 62.5,    # 62.5 kW
        "GB/T": 120.0        # 120 kW
    }
            charging_efficiency = {
    "AC Type 1": 0.85,
    "AC Type 2": 0.88,
    "CCS": 0.92,
    "CHAdeMO": 0.92,
    "GB/T": 0.90
}
            charging_rates = {
                "AC Type 1": 15, "AC Type 2": 18, "CCS": 25, "CHAdeMO": 25, "GB/T": 20
            }
            charger_power = charging_speeds.get(chargingType, 7.4)
            efficiency = charging_efficiency.get(chargingType, 0.90)
            rate = charging_rates.get(chargingType, 18)
            hours = charging_time_minutes / 60.0
            energy_added = charger_power * hours * efficiency
            max_energy_addable = ((100 - initial_battery_level) / 100) * battery_capacity
            usable_energy = min(energy_added, max_energy_addable)
            charging_cost = (usable_energy / efficiency) * rate
            # Calculate estimated final battery percentage
            estimated_final_battery = estimate_final_battery(
                initial_battery_level, charging_time_minutes, battery_capacity, chargingType
            )
        else:
            # Unify cost calculation for target battery scenario
            charging_speeds = {
                "AC Type 1": 7.4,    # 7.4 kW
                "AC Type 2": 22.0,   # 22 kW
                "CCS": 150.0,        # 150 kW
                "CHAdeMO": 62.5,    # 62.5 kW
                "GB/T": 120.0        # 120 kW
            }
            charging_efficiency = {
    "AC Type 1": 0.85,
    "AC Type 2": 0.88,
    "CCS": 0.92,
    "CHAdeMO": 0.92,
    "GB/T": 0.90
}
            charging_rates = {
                "AC Type 1": 15, "AC Type 2": 18, "CCS": 25, "CHAdeMO": 25, "GB/T": 20
            }
            charger_power = charging_speeds.get(chargingType, 7.4)
            efficiency = charging_efficiency.get(chargingType, 0.90)
            rate = charging_rates.get(chargingType, 18)
            energy_needed_kwh = (target_battery_level - initial_battery_level) / 100 * battery_capacity
            energy_from_grid = energy_needed_kwh / efficiency
            charging_cost = energy_from_grid * rate
            # Charging time calculation (as before, using efficiency)
            charging_time_hours = energy_needed_kwh / (charger_power * efficiency)
            charging_time_min = charging_time_hours * 60
            estimated_final_battery = target_battery_level

        # Parse arrival_time string to datetime object (assuming format HH:MM)
        today = date.today()
        arrival_datetime_obj = datetime.strptime(f"{today} {arrival_time_str}", "%Y-%m-%d %H:%M")

        # --- Wait time calculation: minimum of (max departure time per slot - arrival time) ---
        station_doc_ref = db.collection("charging_stations").document(station_id)
        station_snapshot = station_doc_ref.get()
        total_slots = 0
        if station_snapshot.exists:
            station_data = station_snapshot.to_dict()
            total_slots = station_data.get('total_slots', 0)
        vehicles_ref = station_doc_ref.collection("vehicles")
        all_vehicles = [doc.to_dict() for doc in vehicles_ref.stream()]
        from collections import defaultdict
        slot_departures = defaultdict(list)
        for v in all_vehicles:
            slot = v.get('slot_number') or v.get('slot') or 1
            dep_time = v.get('departure_time')
            if dep_time:
                try:
                    dep_dt = datetime.strptime(dep_time, "%Y-%m-%d %H:%M")
                    slot_departures[slot].append(dep_dt)
                except Exception as e:
                    print(f"Error parsing departure_time for vehicle {v.get('vehicle_number','?')}: {e}")
        slot_waits = {}
        print(f"New vehicle arrival time: {arrival_datetime_obj}")
        for i in range(1, total_slots+1):
            departures = slot_departures.get(i, [])
            if departures:
                max_dep = max(departures)
            else:
                max_dep = arrival_datetime_obj
            wait = (max_dep - arrival_datetime_obj).total_seconds() // 60
            slot_waits[i] = max(0, int(wait))
            print(f"Slot {i}: max departure = {max_dep}, wait = {slot_waits[i]} min")
        # Find slot with minimum wait
        assigned_slot_number = min(slot_waits, key=slot_waits.get, default=1)
        wait_time_minutes = slot_waits[assigned_slot_number]
        vehicle_status = "CHARGING" if wait_time_minutes == 0 else "WAITING"
        slot_number = assigned_slot_number
        print(f"Assigned slot: {slot_number}, wait time: {wait_time_minutes} min, status: {vehicle_status}")

        # Store station wait time in Firestore
        try:
            station_doc_ref.update({"latest_wait_time_minutes": wait_time_minutes})
        except Exception as e:
            print(f"Warning: Could not update latest_wait_time_minutes for station {station_id}: {e}")

        # Calculate estimated departure time
        total_duration_minutes = charging_time_min + wait_time_minutes
        departure_datetime_obj = arrival_datetime_obj + timedelta(minutes=total_duration_minutes)
        
        # Format arrival and departure as full datetime strings
        arrival_time_full = arrival_datetime_obj.strftime("%Y-%m-%d %H:%M")
        departure_time_full = departure_datetime_obj.strftime("%Y-%m-%d %H:%M")

        vehicle_doc_ref = station_doc_ref.collection("vehicles").document()
        new_vehicle_id = vehicle_doc_ref.id

        # Create vehicle data with charging calculations and wait time
        vehicle_data = {
            "vehicle_number": vehicle_number,
            "arrival_time": arrival_time_full,
            "departure_time": departure_time_full,
            "chargingType": chargingType,
            "estimated_final_battery": estimated_final_battery if estimated_final_battery is not None else None,
            "initial_battery_level": initial_battery_level,
            "target_battery_level": target_battery_level,

            "battery_capacity": battery_capacity,
            "charging_time_minutes": round(charging_time_min),
            "charging_cost": round(charging_cost) if charging_cost is not None else None,
            "wait_time_minutes": wait_time_minutes,
            "status": vehicle_status,
            "slot_number": slot_number,
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        
        vehicle_doc_ref.set(vehicle_data)
        # Calculate available slots dynamically (do not update Firestore)
        vehicles_ref = station_doc_ref.collection("vehicles")
        charging_count = sum(1 for doc in vehicles_ref.stream() if doc.to_dict().get('status', '').upper() == 'CHARGING')
        available_slots = max(total_slots - charging_count, 0) if total_slots else 0

        return jsonify({
            "message": "Vehicle added successfully!", 
            "vehicle_id": new_vehicle_id,
            "charging_time_minutes": round(charging_time_min),
            "charging_cost": round(charging_cost) if charging_cost is not None else None,
            "wait_time_minutes": wait_time_minutes,
            "departure_time": departure_time_full,
            "available_slots": available_slots,
            "target_type": "minutes" if charging_time_min is not None else "percentage"
        }), 201
    except CalculationError as e:
        raise e # Re-raise CalculationError as is
    except Exception as e:
        import traceback
        print(f"An error occurred during add_vehicle: {e}")
        print(traceback.format_exc())
        raise InvalidUsage(f"An error occurred while adding vehicle: {str(e)}", status_code=500)

@app.route("/remove_vehicle", methods=["POST"])
def remove_vehicle():
    if "station_id" not in session:
        raise UnauthorizedError("Not logged in!")

    data = request.json
    station_id = session["station_id"]
    vehicle_id = data.get("vehicle_id")

    if not vehicle_id:
        raise MissingDataError("Missing vehicle ID!")

    try:
        station_doc_ref = db.collection("charging_stations").document(station_id)
        if not station_doc_ref.get().exists:
            raise NotFoundError("Charging station not found!")

        vehicle_doc_ref = station_doc_ref.collection("vehicles").document(vehicle_id)
        if not vehicle_doc_ref.get().exists:
            raise NotFoundError("Vehicle not found!")

        # Get vehicle data before deletion for response
        vehicle_data = vehicle_doc_ref.get().to_dict()
        
        # Delete the vehicle document
        vehicle_doc_ref.delete()
        
        # Update the station's charging count if needed
        if vehicle_data.get('status', '').upper() == 'CHARGING':
            # Get the current charging count
            station_data = station_doc_ref.get().to_dict() or {}
            current_charging = station_data.get('charging_count', 0)
            if current_charging > 0:
                station_doc_ref.update({
                    'charging_count': firestore.Increment(-1)
                })

        return jsonify({
            "message": "Vehicle removed successfully!",
            "success": True
        }), 200
        
    except Exception as e:
        import traceback
        print(f"An error occurred during remove_vehicle: {e}")
        print(traceback.format_exc())
        return jsonify({
            "error": f"An error occurred while removing the vehicle: {str(e)}",
            "success": False
        }), 500

def calculate_charging_time(initial_battery_level, target_battery_level, battery_capacity_kWh, charging_type):
    """
    Calculate charging time based on charger type and battery levels using logistic model.
    
    Args:
        initial_battery_level (float): Initial battery percentage (0-100)
        target_battery_level (float): Target battery percentage (0-100)
        battery_capacity_kWh (float): Battery capacity in kWh
        charging_type (str): Type of charger (AC Type 1, AC Type 2, CCS, CHAdeMO, GB/T)
    
    Returns:
        tuple: (charging_time_minutes, charging_cost)
    """
    # Charging speeds in kW for different charger types
    charging_speeds = {
        "AC Type 1": 7.4,    # 7.4 kW
        "AC Type 2": 22.0,   # 22 kW
        "CCS": 150.0,        # 150 kW
        "CHAdeMO": 62.5,    # 62.5 kW
        "GB/T": 120.0        # 120 kW
    }
    
    # Charging rates in ₹/kWh for different charger types
    charging_rates = {
        "AC Type 1": 15,
        "AC Type 2": 18,
        "CCS": 25,
        "CHAdeMO": 25,
        "GB/T": 20
    }
    
    # Charging efficiency for different charger types (typical values)
    charging_efficiency = {
        "AC Type 1": 0.85,  # 85% efficient
        "AC Type 2": 0.88,  # 88% efficient
        "CCS": 0.92,        # 92% efficient
        "CHAdeMO": 0.92,    # 92% efficient
        "GB/T": 0.90        # 90% efficient
    }
    
    # Get charging speed and efficiency for the selected type
    charging_speed_kw = charging_speeds.get(charging_type, 7.4)  # Default to AC Type 1 if type not found
    efficiency = charging_efficiency.get(charging_type, 0.85)  # Default to 85% if type not found
    
    try:
        # Calculate charging time using logistic model
        charging_time_hours = ev_charging_time(
            initial_battery_level,
            target_battery_level,
            charging_speed_kw,
            battery_capacity_kWh
        )
        
        # Convert to minutes
        charging_time_minutes = charging_time_hours * 60
        
        # Calculate energy needed and cost with efficiency factor
        battery_percentage_to_charge = target_battery_level - initial_battery_level
        energy_needed_kwh = (battery_percentage_to_charge / 100) * battery_capacity_kWh
        actual_energy_consumed = energy_needed_kwh / efficiency  # Account for charging losses
        charging_rate = charging_rates.get(charging_type, 15)  # Default to AC Type 1 rate if type not found
        charging_cost = actual_energy_consumed * charging_rate
        
        return charging_time_minutes, charging_cost
        
    except ValueError as e:
        print(f"Error calculating charging time: {e}")
        # Fallback to linear calculation if logistic model fails
        battery_percentage_to_charge = target_battery_level - initial_battery_level
        energy_needed_kwh = (battery_percentage_to_charge / 100) * battery_capacity_kWh
        actual_energy_consumed = energy_needed_kwh / efficiency  # Account for charging losses
        charging_time_hours = energy_needed_kwh / (charging_speed_kw * efficiency)
        charging_time_minutes = charging_time_hours * 60
        charging_rate = charging_rates.get(charging_type, 15)
        charging_cost = (energy_needed_kwh / efficiency) * charging_rate
        return charging_time_minutes, charging_cost

@app.errorhandler(InvalidUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response

# ================= EV Slot Booking System Integration =====================
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import uuid

# Booking status enum
class BookingStatus:
    PENDING = "pending"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

# In-memory booking storage (for demo; can be moved to Firestore if needed)
bookings: Dict[str, dict] = {}
user_bookings: Dict[str, List[str]] = {}

from flask import request, jsonify, session

def get_logged_in_user_id():
    return session.get("user_id") or session.get("station_id")

# Helper: Fetch vehicle from Firestore
def get_vehicle(user_id, vehicle_id):
    vehicle_doc_ref = db.collection("users").document(user_id).collection("vehicles").document(vehicle_id)
    doc = vehicle_doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    return None

# Helper: Fetch station from Firestore
def get_station(station_id):
    doc = db.collection("charging_stations").document(station_id).get()
    if doc.exists:
        return doc.to_dict()
    return None

# Helper: Check if station is available for the time window
def is_station_available(station_id, start_time, end_time):
    # Check for conflicting bookings
    for booking in bookings.values():
        if booking['station_id'] == station_id and booking['status'] in [BookingStatus.CONFIRMED, BookingStatus.IN_PROGRESS]:
            # Time overlap
            if start_time < booking['end_time'] and end_time > booking['start_time']:
                return False
    return True

# Helper: Calculate priority score (simple version)
def calculate_priority_score(user_id, vehicle, preferred_time):
    score = 0.0
    battery_urgency = (100 - vehicle['current_charge']) / 100
    score += battery_urgency * 40
    time_diff = abs((datetime.now() - preferred_time).total_seconds()) / 3600
    time_score = max(0, 20 - time_diff)
    score += time_score
    user_booking_count = len(user_bookings.get(user_id, []))
    loyalty_score = min(user_booking_count * 2, 10)
    score += loyalty_score
    return score

@app.route("/find_slots", methods=["POST"])
def find_slots():
    data = request.json
    user_id = get_logged_in_user_id()
    vehicle_id = data.get("vehicle_id")
    start_time_str = data.get("start_time")
    duration = int(data.get("duration", 60))
    charging_type = data.get("charging_type")
    if not user_id or not vehicle_id or not start_time_str:
        return jsonify({"error": "Missing user_id, vehicle_id or start_time"}), 400
    vehicle = get_vehicle(user_id, vehicle_id)
    if not vehicle:
        return jsonify({"error": "Vehicle not found"}), 404
    try:
        start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")
        end_time = start_time + timedelta(minutes=duration)
        # Query all stations that support the requested charging type
        stations_ref = db.collection("charging_stations")
        stations = stations_ref.where("charging_type", "==", charging_type).stream() if charging_type else stations_ref.stream()
        available_slots = []
        for station_doc in stations:
            station = station_doc.to_dict()
            if not is_station_available(station['station_id'], start_time, end_time):
                continue
            slot = {
                'station_id': station['station_id'],
                'station_name': station.get('name'),
                'location': station.get('location'),
                'charging_type': station.get('charging_type'),
                'power_rating': station.get('power_rating'),
                'start_time': start_time,
                'end_time': end_time,
                'duration': duration
            }
            available_slots.append(slot)
        return jsonify({"slots": available_slots})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/create_booking", methods=["POST"])
def create_booking():
    user_id = get_logged_in_user_id()
    data = request.json
    vehicle_id = data.get("vehicle_id")
    station_id = data.get("station_id")
    start_time_str = data.get("start_time")
    target_charge = int(data.get("target_charge", 80))
    if not user_id or not vehicle_id or not station_id or not start_time_str:
        return jsonify({"error": "Missing required fields"}), 400
    vehicle = get_vehicle(user_id, vehicle_id)
    station = get_station(station_id)
    if not vehicle or not station:
        return jsonify({"error": "Vehicle or Station not found"}), 404
    try:
        requested_start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")
        num_slots = int(station.get('num_slots', 1))
        # Build a list of bookings for this station, sorted by slot_number and start_time
        station_bookings = [b for b in bookings.values() if b['station_id'] == station_id and b['status'] in [BookingStatus.CONFIRMED, BookingStatus.IN_PROGRESS]]
        # For each slot, find the next available time (end_time of last booking in that slot)
        slot_available_times = [requested_start_time for _ in range(num_slots)]
        # For each slot, collect its bookings and get the latest end_time
        for slot in range(num_slots):
            slot_bookings = [b for b in station_bookings if b.get('slot_number') == slot+1]
            if slot_bookings:
                latest_end = max(b['end_time'] for b in slot_bookings)
                slot_available_times[slot] = latest_end
        # Find the slot with the minimum next available time
        min_slot_index = slot_available_times.index(min(slot_available_times))
        assigned_slot = min_slot_index + 1
        actual_start_time = max(requested_start_time, slot_available_times[min_slot_index])
        # Calculate charging duration
        charging_time_minutes, _ = calculate_charging_time(
            vehicle['current_charge'],
            target_charge,
            vehicle['battery_capacity'],
            station['charging_type']
        )
        actual_end_time = actual_start_time + timedelta(minutes=charging_time_minutes)
        priority_score = calculate_priority_score(user_id, vehicle, actual_start_time)
        booking_id = str(uuid.uuid4())
        booking = {
            'id': booking_id,
            'user_id': user_id,
            'vehicle_id': vehicle_id,
            'station_id': station_id,
            'slot_number': assigned_slot,
            'start_time': actual_start_time,
            'end_time': actual_end_time,
            'estimated_duration': charging_time_minutes,
            'status': BookingStatus.CONFIRMED,
            'priority_score': priority_score,
            'created_at': datetime.now()
        }
        bookings[booking_id] = booking
        if user_id not in user_bookings:
            user_bookings[user_id] = []
        user_bookings[user_id].append(booking_id)
        return jsonify({
            "booking_id": booking_id,
            "status": BookingStatus.CONFIRMED,
            "priority_score": priority_score,
            "assigned_slot": assigned_slot,
            "scheduled_start_time": actual_start_time.strftime('%Y-%m-%d %H:%M'),
            "scheduled_end_time": actual_end_time.strftime('%Y-%m-%d %H:%M'),
            "wait_time_minutes": int((actual_start_time - requested_start_time).total_seconds() // 60) if actual_start_time > requested_start_time else 0
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/my_bookings", methods=["GET"])
def my_bookings():
    user_id = get_logged_in_user_id()
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    booking_ids = user_bookings.get(user_id, [])
    user_booking_objs = [bookings[bid] for bid in booking_ids if bid in bookings]
    bookings_list = [{
        'booking_id': b['id'],
        'vehicle_id': b['vehicle_id'],
        'station_id': b['station_id'],
        'start_time': b['start_time'].strftime('%Y-%m-%d %H:%M'),
        'end_time': b['end_time'].strftime('%Y-%m-%d %H:%M'),
        'status': b['status'],
        'priority_score': b['priority_score']
    } for b in user_booking_objs]
    return jsonify({"bookings": bookings_list})

@app.route("/cancel_booking", methods=["POST"])
def cancel_booking():
    user_id = get_logged_in_user_id()
    data = request.json
    booking_id = data.get("booking_id")
    if not user_id or not booking_id:
        return jsonify({"error": "Missing booking_id or not logged in"}), 400
    booking = bookings.get(booking_id)
    if not booking or booking['user_id'] != user_id:
        return jsonify({"error": "Booking not found or unauthorized"}), 404
    if booking['status'] == BookingStatus.IN_PROGRESS:
        return jsonify({"error": "Cannot cancel ongoing charging"}), 409
    booking['status'] = BookingStatus.CANCELLED
    return jsonify({"message": "Booking cancelled"}), 200

@app.route("/station_queue/<station_id>", methods=["GET"])
def station_queue(station_id):
    # Get all bookings for this station
    station_bookings = [b for b in bookings.values() if b['station_id'] == station_id and b['status'] in [BookingStatus.CONFIRMED, BookingStatus.IN_PROGRESS]]
    # Group by slot_number
    from collections import defaultdict
    slots = defaultdict(list)
    for b in station_bookings:
        slots[b.get('slot_number', 1)].append(b)
    # Sort each slot's bookings by start_time
    result = {}
    for slot_num, bks in slots.items():
        result[slot_num] = sorted([
            {
                'booking_id': b['id'],
                'user_id': b['user_id'],
                'vehicle_id': b['vehicle_id'],
                'start_time': b['start_time'].strftime('%Y-%m-%d %H:%M'),
                'end_time': b['end_time'].strftime('%Y-%m-%d %H:%M'),
                'status': b['status'],
                'priority_score': b['priority_score']
            } for b in bks
        ], key=lambda x: x['start_time'])
    return jsonify({"slots": result})

@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.json
    station_id = data.get("station_id")
    otp = data.get("otp")
    new_access_key = data.get("new_access_key")
    if not station_id or not otp or not new_access_key:
        return jsonify({"success": False, "message": "Missing required fields."}), 400

    doc_ref = db.collection("charging_stations").document(station_id)
    doc = doc_ref.get()
    if not doc.exists:
        return jsonify({"success": False, "message": "Station ID not found."}), 404
    station_data = doc.to_dict()
    stored_otp = station_data.get("reset_otp")
    otp_expiry = station_data.get("reset_otp_expiry")
    if not stored_otp or not otp_expiry:
        return jsonify({"success": False, "message": "OTP not found. Please request a new OTP."}), 400

    # Convert Firestore timestamp to datetime if needed
    if hasattr(otp_expiry, 'to_datetime'):
        otp_expiry = otp_expiry.to_datetime()
    elif isinstance(otp_expiry, dict) and 'seconds' in otp_expiry:
        from datetime import timezone
        otp_expiry = datetime.fromtimestamp(otp_expiry['seconds'], tz=timezone.utc)

    if otp != stored_otp:
        return jsonify({
            "success": False, 
            "message": "The OTP you entered is incorrect. Please check and try again."
        }), 400
    from datetime import timezone
    current_time = datetime.now(timezone.utc)
    if current_time > otp_expiry:
        return jsonify({
            "success": False, 
            "message": f"This OTP has expired. Please request a new OTP."
        }), 400

    # Update access key and clear OTP fields
    doc_ref.update({
        'access_key': new_access_key,
        'reset_otp': firestore.DELETE_FIELD,
        'reset_otp_expiry': firestore.DELETE_FIELD
    })
    return jsonify({"success": True, "message": "Access key updated successfully."}), 200

if __name__ == "__main__":
    app.run(debug=True)
