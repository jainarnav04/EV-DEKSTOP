from flask import Flask, request, jsonify, session, redirect, url_for, render_template
import firebase_admin
from firebase_admin import credentials, auth, firestore
from datetime import datetime, date, timedelta
import os
from functools import wraps
from dotenv import load_dotenv

load_dotenv()
# --- SendGrid imports ---
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback_secret_for_dev_only") # Required for Flask sessions

print("Initializing Firebase...") 

# Use environment variable for credential path in deployment, fallback to local file for development
firebase_cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
cred = credentials.Certificate(firebase_cred_path)
firebase_admin.initialize_app(cred)
db = firestore.client()
print("Firebase initialized successfully!")  # Debug print

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

@app.route("/")
def index():
    """Render the main index page."""
    return render_template("index.html")

@app.route("/driver")
def driver():
    """Render the driver page."""
    return render_template("driver.html")

@app.route("/login", methods=["GET", "POST"])
def login_register():
    """Handle both login and registration."""
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
            station_id = data.get("station_id")
            email = data.get("email")
            if not station_id or not email:
                return jsonify({"error": "Missing station ID or email!"}), 400

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
                "email": email.lower().strip()
            })
            
            return jsonify({
                "message": "Registration successful!",
                "station_id": station_id,
                "email": email.lower().strip()
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
            return jsonify({"success": True, "message": "OTP sent to your registered email. Enter the OTP to reset your access key."}), 200
        else:
            return jsonify({"success": False, "message": "Station ID and Email do not match."}), 404
    else:
        return jsonify({"success": False, "message": "Station ID not found."}), 404

def update_vehicle_statuses(vehicles_ref):
    """Update vehicle statuses based on current time."""
    now = datetime.now()
    batch = db.batch()
    updated_count = 0
    
    for vehicle_doc in vehicles_ref.stream():
        vehicle_data = vehicle_doc.to_dict()
        vehicle_ref = vehicles_ref.document(vehicle_doc.id)
        
        # Only update if status is WAITING and charging start time has passed
        if (vehicle_data.get('status') == 'WAITING' and 
            'charging_start_time' in vehicle_data):
            try:
                start_time = datetime.strptime(
                    vehicle_data['charging_start_time'], 
                    '%Y-%m-%d %H:%M'
                )
                if now >= start_time:
                    batch.update(vehicle_ref, {'status': 'CHARGING'})
                    batch.update(vehicle_ref, {'wait_time_minutes': 0})
                    updated_count += 1
            except (ValueError, TypeError) as e:
                print(f"Error parsing charging time for vehicle {vehicle_doc.id}: {e}")
    
    # Commit all updates in a single batch
    if updated_count > 0:
        batch.commit()
        print(f"Updated {updated_count} vehicle(s) to CHARGING status.")
    
    return updated_count

@app.route("/dashboard")
def dashboard():
    if "station_id" not in session:
        print("No station_id found in session!")  # Debugging
        return redirect(url_for("login_register"))  # Redirect to login if session is missing

    station_id = session["station_id"]
    print(f"Station ID from session: {station_id}")  # Debugging

    doc_ref = db.collection("charging_stations").document(station_id)
    doc = doc_ref.get()
    
    # Update vehicle statuses before fetching them
    if doc.exists:
        vehicles_ref = doc_ref.collection("vehicles")
        update_vehicle_statuses(vehicles_ref)

    if doc.exists:
        station_data = doc.to_dict()
        print("Station data loaded for dashboard:", station_data) # Debug print
        print("Station Charging Type from DB:", station_data.get("chargingType")) # Debug print for charging type
        
        # Fetch vehicles associated with this station from the vehicles subcollection
        vehicles_ref = db.collection("charging_stations").document(station_id).collection("vehicles").order_by("arrival_time")
        vehicles = []
        now = datetime.now()
        
        for doc in vehicles_ref.stream():
            vehicle_data = doc.to_dict()
            vehicle_data["id"] = doc.id  # Add the document ID to the vehicle data
            
            # Ensure all required fields exist with defaults
            vehicle_data['status'] = vehicle_data.get('status', 'WAITING').upper()
            
            try:
                # Parse and format times from stored values
                if 'arrival_time' in vehicle_data:
                    arrival_dt = datetime.strptime(vehicle_data['arrival_time'], '%Y-%m-%d %H:%M')
                    vehicle_data['arrival_dt'] = arrival_dt
                    
                    # Use stored charging_start_time if available
                    if 'charging_start_time' in vehicle_data and vehicle_data['charging_start_time']:
                        charging_start_dt = datetime.strptime(
                            vehicle_data['charging_start_time'], 
                            '%Y-%m-%d %H:%M'
                        )
                        vehicle_data['start_time'] = vehicle_data['charging_start_time']
                        
                        # Use stored departure_time if available
                        if 'departure_time' in vehicle_data and vehicle_data['departure_time']:
                            departure_dt = datetime.strptime(
                                vehicle_data['departure_time'], 
                                '%Y-%m-%d %H:%M'
                            )
                            vehicle_data['end_time'] = vehicle_data['departure_time']
                        else:
                            # Calculate departure_time if missing
                            charging_time = vehicle_data.get('charging_time_minutes', 0)
                            departure_dt = charging_start_dt + timedelta(minutes=int(charging_time))
                            vehicle_data['end_time'] = departure_dt.strftime('%Y-%m-%d %H:%M')
                            
                        # Update status based on current time
                        if vehicle_data['status'] == 'WAITING' and now >= charging_start_dt:
                            vehicle_data['status'] = 'CHARGING'
                    
                    vehicles.append(vehicle_data)
                    
            except Exception as e:
                print(f"Error processing vehicle {doc.id}: {e}")
                continue

        # --- Calculate slot free times based on vehicle schedules ---
        slot_free_time = {}
        total_slots = int(station_data.get('totalSlots') or station_data.get('total_slots') or 2)
        
        # Group vehicles by slot
        slot_vehicles = {i: [] for i in range(1, total_slots + 1)}
        for v in vehicles:
            slot = int(v.get('slot_number', 1))
            if 1 <= slot <= total_slots:
                slot_vehicles[slot].append(v)
        
        # Calculate free time for each slot
        for slot, slot_vs in slot_vehicles.items():
            # Sort vehicles in this slot by start time
            slot_vs_sorted = sorted(
                [v for v in slot_vs if 'start_time' in v and 'end_time' in v],
                key=lambda x: x['start_time']
            )
            
            if not slot_vs_sorted:
                slot_free_time[slot] = now.strftime('%Y-%m-%d %H:%M')
                continue
                
            # Find the latest end time in this slot
            last_end = max(
                [datetime.strptime(v['end_time'], '%Y-%m-%d %H:%M') for v in slot_vs_sorted]
            )
            
            # Add 1-minute buffer after the last vehicle
            slot_free_time[slot] = (last_end + timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M')
        
        print("Slot free times with 1-minute buffer:", slot_free_time)
        
        # Use the latest wait time from the database (updated by the scheduled job)
        wait_minutes = station_data.get('latest_wait_time_minutes', 0)
        print(f"Current wait time from database: {wait_minutes} minutes")

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
    # Round to nearest whole number for consistency with frontend
    return round(final_percent)

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
        # Find slot with minimum wait and get its free time
        assigned_slot_number = min(slot_waits, key=slot_waits.get, default=1)
        wait_time_minutes = slot_waits[assigned_slot_number]
        slot_number = assigned_slot_number
        
        # Calculate charging start time (slot's free time + 1 minute buffer)
        if wait_time_minutes > 0:
            # Add 1 minute to wait time to account for buffer
            wait_time_minutes += 1
            # Charging starts after wait time (which now includes buffer)
            charging_start_datetime_obj = arrival_datetime_obj + timedelta(minutes=wait_time_minutes)
            vehicle_status = "WAITING"
        else:
            # If no wait, charging starts at arrival time
            charging_start_datetime_obj = arrival_datetime_obj
            vehicle_status = "CHARGING"
            
        # Calculate departure time (charging start time + charging duration)
        departure_datetime_obj = charging_start_datetime_obj + timedelta(minutes=round(charging_time_min))
        
        # Update wait time to be the difference between charging start and arrival
        actual_wait_minutes = max(0, (charging_start_datetime_obj - arrival_datetime_obj).total_seconds() // 60)
        
        print("DEBUG: Reached point 1 in add_vehicle")  # Add this before the print statements in question
        print(f"Assigned slot: {slot_number}, wait time: {actual_wait_minutes} min, status: {vehicle_status}")
        print("DEBUG: Reached point 2 in add_vehicle")  # Add this after the print statements in question
        print(f"Charging starts at: {charging_start_datetime_obj}, ends at: {departure_datetime_obj}")

        # Store station wait time in Firestore
        try:
            station_doc_ref.update({"latest_wait_time_minutes": actual_wait_minutes})
        except Exception as e:
            print(f"Warning: Could not update latest_wait_time_minutes for station {station_id}: {e}")
        
        # Format times as full datetime strings
        arrival_time_full = arrival_datetime_obj.strftime("%Y-%m-%d %H:%M")
        departure_time_full = departure_datetime_obj.strftime("%Y-%m-%d %H:%M")
        charging_start_time_full = charging_start_datetime_obj.strftime("%Y-%m-%d %H:%M")
        
        # The charging start time is already calculated above with the slot's free time
        # which includes the 1-minute buffer from the previous vehicle's departure

        vehicle_doc_ref = station_doc_ref.collection("vehicles").document()
        new_vehicle_id = vehicle_doc_ref.id

        # Create vehicle data with charging calculations and wait time
        vehicle_data = {
            "vehicle_number": vehicle_number,
            "arrival_time": arrival_time_full,
            "departure_time": departure_time_full,
            "charging_start_time": charging_start_time_full,
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

@app.route("/api/vehicle_count")
def vehicle_count():
    if "station_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    vehicles_ref = db.collection("charging_stations").document(session["station_id"]).collection("vehicles")
    count = len(list(vehicles_ref.stream()))
    return jsonify({"vehicle_count": count})
# Add this import at the top of your main.py file
from apscheduler.schedulers.background import BackgroundScheduler

# Add this new function somewhere in your main.py file
def update_all_station_wait_times():
    """
    This function runs in the background to update wait times for ALL stations.
    """
    with app.app_context():  # Required for background tasks to access the app
        print("SCHEDULER: Running job to update wait times...")
        stations_ref = db.collection("charging_stations")
        
        for station_doc in stations_ref.stream():
            station_id = station_doc.id
            station_data = station_doc.to_dict()
            now = datetime.now()

            # This logic is the same as in your dashboard function
            vehicles_ref = station_doc.reference.collection("vehicles")
            total_slots = int(station_data.get('total_slots', 0))
            slot_free_at = {i: now for i in range(1, total_slots + 1)}

            for v_doc in vehicles_ref.stream():
                v = v_doc.to_dict()
                departure_time_str = v.get('departure_time')
                if not departure_time_str: continue
                try:
                    slot_number = int(v.get('slot_number', 1))
                    departure_dt = datetime.strptime(departure_time_str, '%Y-%m-%d %H:%M')
                    if departure_dt > now:
                        current_free_time = slot_free_at.get(slot_number, now)
                        slot_free_at[slot_number] = max(current_free_time, departure_dt)
                except (ValueError, TypeError):
                    continue

            wait_minutes = 0
            if slot_free_at:
                earliest_free_dt = min(slot_free_at.values())
                if earliest_free_dt > now:
                    wait_minutes = round((earliest_free_dt - now).total_seconds() / 60)
            
            current_wait_time = station_data.get('latest_wait_time_minutes')
            if current_wait_time is None or int(current_wait_time) != wait_minutes:
                print(f"SCHEDULER: Updating station '{station_id}' wait time from {current_wait_time} to {wait_minutes} min.")
                station_doc.reference.update({'latest_wait_time_minutes': wait_minutes})
def remove_completed_vehicles():
    """
    This background job checks all stations for completed vehicles and removes them.
    A vehicle is 'completed' if its departure time is in the past.
    """
    with app.app_context(): # Required for background tasks
        print("SCHEDULER: Running job to remove completed vehicles...")
        now = datetime.now()
        stations_ref = db.collection("charging_stations")
        
        for station_doc in stations_ref.stream():
            vehicles_ref = station_doc.reference.collection("vehicles")
            for vehicle_doc in vehicles_ref.stream():
                vehicle_data = vehicle_doc.to_dict()
                departure_time_str = vehicle_data.get('departure_time')

                if not departure_time_str:
                    continue

                try:
                    departure_dt = datetime.strptime(departure_time_str, '%Y-%m-%d %H:%M')
                    
                    # Check if the vehicle's departure time has passed
                    if departure_dt <= now:
                        print(f"SCHEDULER: Removing completed vehicle '{vehicle_data.get('vehicle_number')}' from station '{station_doc.id}'.")
                        vehicle_doc.reference.delete()
                        
                except (ValueError, TypeError):
                    # Ignore vehicles with an invalid departure time format
                    continue
@app.route('/logout')
def logout():
    """Handle user logout by clearing the session and redirecting to login page."""
    # Clear the session data
    session.clear()
    # Redirect to the login page
    return redirect(url_for('login_register'))

if __name__ == "__main__":
    # Run the Flask app
    app.run(debug=True)
