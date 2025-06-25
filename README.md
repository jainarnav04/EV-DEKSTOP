# EV Charging Station Management System

A Flask-based web application for managing electric vehicle charging stations, tracking vehicle charging sessions, and calculating charging times and costs.

## Features

- **Station Management**
  - Register and manage charging stations
  - Update station details (location, charging type, slots, etc.)
  - Real-time slot availability tracking

- **Vehicle Management**
  - Add and track vehicles at charging stations
  - Calculate charging time using advanced logistic model
  - Estimate charging costs based on vehicle and station parameters
  - Track wait times and departure estimates

- **Charging Types Support**
  - AC Type 1 (7.4 kW)
  - AC Type 2 (22 kW)
  - CCS (150 kW)
  - CHAdeMO (62.5 kW)
  - GB/T (120 kW)

## Technical Details

### Charging Time Calculation
The application uses a modified logistic model to calculate charging times, which accounts for:
- Battery capacity
- Initial and target charge levels
- Charging efficiency
- Charger power rating

### Cost Calculation
Charging costs are calculated based on:
- Energy consumed (kWh)
- Charging efficiency losses
- Station-specific rates

## Prerequisites

- Python 3.7+
- Firebase account and credentials
- Flask
- Firebase Admin SDK

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/EV-Charging-Station.git
cd EV-Charging-Station
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Set up Firebase:
   - Create a Firebase project
   - Download your Firebase service account credentials
   - Store the credentials securely (DO NOT commit to version control)

4. Configure environment variables:
   - Create a `.env` file in the project root
   - Add your Firebase credentials with name "GOOGLE_APPLICATION_CREDENTIALS"
   - Add your Google API Services key with name "GOOGLE_MAPS_API_KEY"

## Usage

1. Start the Flask application:
```bash
python auth.py
```

2. Access the application at `http://localhost:5000`

3. Login with your station credentials or register a new station

## Security Notes

- Never commit Firebase credentials or other sensitive information to version control
- Use environment variables for sensitive configuration
- Keep your dependencies updated
- Follow security best practices for web applications

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## Support

For support, please open an issue in the GitHub repository or contact the maintainers.

## Acknowledgments

- Flask framework
- Firebase for backend services
- Contributors and maintainers
