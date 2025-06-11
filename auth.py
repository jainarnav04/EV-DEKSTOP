from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import firebase_admin
from firebase_admin import credentials, firestore
import math  # Add this at the top with other imports
import datetime # Import datetime module
import random   # Import random module

print("Starting application...")  # Debug print

def ev_charging_time(current_percent, target_percent, charger_power_kw, battery_capacity_kwh=60,
                     charging_efficiency=0.9, k=1.6):
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

    try:
        unit_time = (1 / k) * math.log(
            (target_percent * (100 - current_percent)) /
            (current_percent * (100 - target_percent))
        )
    except (ZeroDivisionError, ValueError):
        # Fallback to linear approximation if mathematical errors occur
        linear_full_charge_time = battery_capacity_kwh / (charger_power_kw * charging_efficiency)
        return linear_full_charge_time * (target_percent - current_percent) / 100

    linear_full_charge_time = battery_capacity_kwh / (charger_power_kw * charging_efficiency)
    logistic_scale = linear_full_charge_time / 7.43
    return unit_time * logistic_scale

app = Flask(__name__)
app.secret_key = "e9f1a3b7c2e84d1d86e7df0c4a6789f120cbb89e5f843f3c74a8a776bc9ff2a5"  # Required for Flask sessions

print("Initializing Firebase...")  # Debug print
# Initialize Firebase
cred = credentials.Certificate("ev-navigation--firebase-adminsdk-2erdd-6424f06ee8.json")#change this with the new one
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
            if not name:
                return jsonify({"error": "Missing station name!"}), 400

            if doc_ref.get().exists:
                return jsonify({"error": "Station ID already exists!"}), 400

            doc_ref.set({
                "station_id": station_id,
                "access_key": access_key,
                "name": name
            })
            return jsonify({"message": "Registration successful!"}), 201

        return jsonify({"error": "Invalid action!"}), 400

    except Exception as e:
        print(f"An error occurred in login_register: {e}")
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

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
            vehicles.append(vehicle_data)
        
        print("Vehicles data being sent to template:", vehicles) # Debug print
        
        return render_template("dashboard.html", station=station_data, vehicles=vehicles)  # Pass vehicles data
    else:
        return "Error: Station not found", 404


@app.route("/update_station", methods=["POST"])
def update_station():
    if "station_id" not in session:
        return jsonify({"error": "Not logged in!"}), 403

    data = request.json
    print("Update Station Data:", data)  # Debug print
    station_id = session["station_id"]

    # Prepare update data from the form (ensure keys match what your JS sends)
    update_data = {
        "name": data.get("stationName"),
        "operator": data.get("operatorName"),
        "chargingType": data.get("chargingType") or "",  # Ensure it's always a string
        "location": data.get("location"),
        "total_slots": int(data.get("totalSlots")),
        "available_slots": int(data.get("availableSlots")),
        "charging_rate": int(data.get("chargingRate")),
        "latitude": float(data.get("latitude")) if data.get("latitude") else None, # Add latitude
        "longitude": float(data.get("longitude")) if data.get("longitude") else None # Add longitude
    }
    print("Update Data:", update_data)  # Debug print

    try:
        doc_ref = db.collection("charging_stations").document(station_id)
        doc_ref.update(update_data)
        # Verify the update
        updated_doc = doc_ref.get()
        print("Updated document data:", updated_doc.to_dict())  # Debug print
        return jsonify({"message": "Station details updated successfully!"}), 200
    except Exception as e:
        import traceback
        print(f"An error occurred during station update: {e}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route("/add_vehicle", methods=["POST"])
def add_vehicle():
    if "station_id" not in session:
        return jsonify({"error": "Not logged in!"}), 403

    data = request.json
    print("Add Vehicle Data:", data)  # Debug print
    station_id = session["station_id"]

    vehicle_number = data.get("vehicleNumber")
    arrival_time_str = data.get("arrivalTime") # Store as string initially
    chargingType = data.get("chargingType")
    initial_battery_level = float(data.get("initialBatteryLevel"))
    target_battery_level = float(data.get("targetBatteryLevel"))
    battery_capacity = float(data.get("batteryCapacity", 60))  # Default to 60 kWh if not provided

    if not vehicle_number or not arrival_time_str: # Use arrival_time_str here
        return jsonify({"error": "Missing vehicle number or arrival time!"}), 400

    try:
        # Calculate charging time and cost
        charging_time_min, charging_cost = calculate_charging_time(
            initial_battery_level,
            target_battery_level,
            battery_capacity,
            chargingType
        )

        # Generate a random wait time between 10 and 30 minutes
        wait_time_minutes = random.randint(10, 30)

        # Parse arrival_time string to datetime object (assuming format HH:MM)
        # Get today's date to combine with time for datetime object
        today = datetime.date.today()
        arrival_datetime_obj = datetime.datetime.strptime(f"{today} {arrival_time_str}", "%Y-%m-%d %H:%M")
        
        # Calculate estimated departure time
        total_duration_minutes = charging_time_min + wait_time_minutes
        departure_datetime_obj = arrival_datetime_obj + datetime.timedelta(minutes=total_duration_minutes)
        
        # Format departure_time back to HH:MM string
        departure_time_str = departure_datetime_obj.strftime("%H:%M")

        station_doc_ref = db.collection("charging_stations").document(station_id)
        vehicle_doc_ref = station_doc_ref.collection("vehicles").document()
        new_vehicle_id = vehicle_doc_ref.id

        # Create vehicle data with charging calculations and wait time
        vehicle_data = {
            "vehicle_number": vehicle_number,
            "arrival_time": arrival_time_str, # Store original arrival time string
            "departure_time": departure_time_str, # Store calculated departure time string
            "chargingType": chargingType,
            "initial_battery_level": initial_battery_level,
            "target_battery_level": target_battery_level,
            "battery_capacity": battery_capacity,
            "charging_time_minutes": round(charging_time_min),
            "charging_cost": round(charging_cost),
            "wait_time_minutes": wait_time_minutes, # Store the random wait time
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        
        # Set the new vehicle document
        vehicle_doc_ref.set(vehicle_data)
        
        return jsonify({
            "message": "Vehicle added successfully!", 
            "vehicle_id": new_vehicle_id,
            "charging_time_minutes": round(charging_time_min),
            "charging_cost": round(charging_cost),
            "wait_time_minutes": wait_time_minutes, # Return the random wait time
            "departure_time": departure_time_str # Return the calculated departure time
        }), 201
    except Exception as e:
        import traceback
        print(f"An error occurred during add_vehicle: {e}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route("/remove_vehicle", methods=["POST"])
def remove_vehicle():
    if "station_id" not in session:
        return jsonify({"error": "Not logged in!"}), 403

    data = request.json
    station_id = session["station_id"] # Get station_id from session
    vehicle_id = data.get("vehicle_id")

    if not vehicle_id:
        return jsonify({"error": "Missing vehicle ID!"}), 400

    try:
        # Delete vehicle from the subcollection under the specific station
        db.collection("charging_stations").document(station_id).collection("vehicles").document(vehicle_id).delete()
        return jsonify({"message": "Vehicle removed successfully!"}), 200
    except Exception as e:
        import traceback
        print(f"An error occurred during remove_vehicle: {e}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

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
        charging_time_hours = energy_needed_kwh / charging_speed_kw
        charging_time_minutes = charging_time_hours * 60
        charging_rate = charging_rates.get(charging_type, 15)
        charging_cost = actual_energy_consumed * charging_rate
        return charging_time_minutes, charging_cost

if __name__ == "__main__":
    app.run(debug=True)
