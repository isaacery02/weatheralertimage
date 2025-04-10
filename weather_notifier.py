# weather_notifier.py
import logging
import os
import smtplib
import requests
# Removed: import azure.functions as func
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage # Import necessary for embedding images
import datetime
from typing import Dict, Optional, List, Tuple # Updated typing imports
import sys # Import sys for explicit stdout/stderr handling in logging

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)] # Explicitly log to stdout
)

# Removed: app = func.FunctionApp()

# --- Helper Functions ---
def get_wind_direction(degrees: int) -> str:
    """Converts wind direction in degrees to a readable format (N, NE, E, SE, etc.)."""
    directions = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    if degrees is None: return "N/A"
    try:
        return directions[int((degrees + 11.25) / 22.5) % 16]
    except (ValueError, TypeError):
        logging.warning(f"Could not parse wind direction degrees: {degrees}")
        return "N/A"

def get_weekly_weather(lat: str, lon: str, api_key: str) -> Optional[List[Dict]]:
    """Fetches the 7-day weather forecast using OpenWeather One Call API 3.0."""
    url = f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&exclude=current,minutely,hourly,alerts&appid={api_key}&units=metric"
    weekly_forecast = []
    data = {} # Initialize data

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if "daily" not in data or not isinstance(data["daily"], list):
             logging.warning("Daily forecast data ('daily' key) not found or not a list in API response. Check API plan/endpoint.")
             return None

        # Get forecast for the next 7 days (indices 1 through 7 from API response)
        for daily_data in data["daily"][1:8]:
            forecast = {
                "weather_desc": daily_data["weather"][0]["description"].capitalize(),
                "icon": daily_data["weather"][0]["icon"],
                "high_temp": round(daily_data["temp"]["max"], 1),
                "low_temp": round(daily_data["temp"]["min"], 1),
                "wind_speed": round(daily_data.get("wind_speed", 0), 1),
                "wind_direction": get_wind_direction(daily_data.get("wind_deg")),
                "humidity": daily_data.get("humidity", "N/A"), # Use .get
                "dew_point": round(daily_data.get("dew_point", 0), 1),
                "precipitation": round(daily_data.get("rain", 0),1),
                "precip_chance": round(daily_data.get("pop", 0) * 100, 1),
                "uv_index": daily_data.get("uvi", "N/A"),
                # Use fromtimestamp which assumes local time if tz not provided, convert to UTC
                "sunrise": datetime.datetime.fromtimestamp(daily_data["sunrise"], tz=datetime.timezone.utc).strftime("%H:%M %Z"),
                "sunset": datetime.datetime.fromtimestamp(daily_data["sunset"], tz=datetime.timezone.utc).strftime("%H:%M %Z"),
                "date_obj": datetime.datetime.fromtimestamp(daily_data["dt"], tz=datetime.timezone.utc),
                "date_str": datetime.datetime.fromtimestamp(daily_data["dt"], tz=datetime.timezone.utc).strftime("%Y-%m-%d"),
                "day_name": datetime.datetime.fromtimestamp(daily_data["dt"], tz=datetime.timezone.utc).strftime("%A")
            }
            weekly_forecast.append(forecast)

        if not weekly_forecast:
             logging.warning("Processed forecast list is empty. Check slicing or API data structure.")
             return None

        return weekly_forecast

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching weekly weather data: {e}")
        return None
    except (KeyError, ValueError, TypeError, IndexError) as e:
        # Log the actual data received (be mindful of API key exposure if logging publicly)
        # logging.error(f"Error parsing weekly weather data: {e}. Received data structure: {data}")
        logging.error(f"Error parsing weekly weather data: {e}.") # Safer logging
        return None

def send_email_with_images(
    user: str, password: str, to_email: str, subject: str,
    html_content: str, images: List[Tuple[bytes, str]]
) -> None:
    """Sends an HTML email with embedded images using Gmail SMTP."""
    try:
        msg_root = MIMEMultipart('related')
        msg_root['Subject'] = subject
        msg_root['From'] = user
        msg_root['To'] = to_email
        msg_root.preamble = 'This is a multi-part message in MIME format.'

        msg_alternative = MIMEMultipart('alternative')
        msg_root.attach(msg_alternative)
        msg_alternative.attach(MIMEText(html_content, 'html', 'utf-8')) # Specify utf-8

        for img_data, img_cid in images:
            if not img_data: # Skip if image data is None/empty
                 logging.warning(f"Skipping attachment for CID {img_cid} due to empty image data.")
                 continue
            try:
                 img = MIMEImage(img_data)
                 img.add_header('Content-ID', f'<{img_cid}>')
                 msg_root.attach(img)
            except Exception as img_attach_err:
                 logging.error(f"Failed to attach image with CID {img_cid}: {img_attach_err}")


        logging.info(f"Connecting to SMTP server smtp.gmail.com:465 for user {user}...")
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        # server.set_debuglevel(1) # Uncomment for verbose SMTP debugging
        server.login(user, password)
        logging.info("Sending email...")
        server.sendmail(user, to_email, msg_root.as_string())
        server.quit()
        logging.info(f"Email sent to {to_email} successfully!")

    except smtplib.SMTPAuthenticationError as e:
         logging.error(f"SMTP Authentication Error: Check email ({user}) and App Password. Details: {e}")
    except smtplib.SMTPException as e:
        logging.error(f"Error sending email: SMTP error - {e}")
    except Exception as e:
        logging.error(f"Error sending email: Unexpected error - {e}", exc_info=True) # Log traceback


# --- Main Execution Logic ---
def run_weekly_weather_alert():
    """Fetches the weekly weather forecast and sends an email notification."""
    logging.info("Weekly WeatherNotifier script started.")

    # --- Configuration ---
    openweather_api_key = os.getenv("OPENWEATHER_API_KEY")
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_PASSWORD")
    to_email = os.getenv("TO_EMAIL")
    lat = os.getenv("LATITUDE")
    lon = os.getenv("LONGITUDE")
    city = os.getenv("CITY_NAME", "DefaultCity") # Provide a default

    # --- Validate Environment Variables ---
    required_vars = {
        "OPENWEATHER_API_KEY": openweather_api_key, "GMAIL_USER": gmail_user,
        "GMAIL_PASSWORD": gmail_password, "TO_EMAIL": to_email,
        "LATITUDE": lat, "LONGITUDE": lon,
    }
    missing_vars = [name for name, value in required_vars.items() if not value]
    if missing_vars:
        logging.error(f"Missing environment variables: {', '.join(missing_vars)}")
        return
    logging.info("All required environment variables found.")

    try:
        float(lat)
        float(lon)
    except ValueError:
        logging.error("LATITUDE and LONGITUDE must be numeric values.")
        return

    # --- Fetch Weekly Weather Data ---
    logging.info(f"Fetching weekly weather data for {city} ({lat}, {lon})...")
    weekly_data = get_weekly_weather(lat, lon, openweather_api_key)

    if weekly_data:
        logging.info(f"Successfully fetched data for {len(weekly_data)} days.")
        email_subject = f"🌦️ 7-Day Weather Forecast for {city}"
        email_images = [] # To store (image_bytes, content_id) tuples
        html_content = f"""
        <html><head><style>
        body {{ font-family: sans-serif; line-height: 1.5; }} h1 {{ color: #333; }}
        h2 {{ color: #555; border-bottom: 1px solid #eee; padding-bottom: 5px; margin-top: 20px;}}
        .day-forecast {{ margin-bottom: 15px; padding: 10px; border: 1px solid #ddd; border-radius: 5px; background-color: #f9f9f9; }}
        .weather-icon {{ vertical-align: middle; width: 50px; height: 50px; margin-right: 10px; }} strong {{ color: #444; }}
        </style></head><body><h1>🗓️ 7-Day Weather Forecast for {city}</h1>
        """

        for day_forecast in weekly_data:
            icon_code = day_forecast['icon']
            icon_url = f"http://openweathermap.org/img/wn/{icon_code}@2x.png"
            image_cid = f"icon_{day_forecast['date_str']}_{icon_code}" # Unique CID
            img_tag = f'(icon {icon_code})' # Default placeholder
            icon_bytes = None # Initialize icon_bytes

            try:
                logging.debug(f"Fetching icon: {icon_url}")
                icon_response = requests.get(icon_url, timeout=10) # Add timeout
                icon_response.raise_for_status()
                icon_bytes = icon_response.content
                if icon_bytes: # Check if content is not empty
                     email_images.append((icon_bytes, image_cid)) # Store bytes and CID
                     img_tag = f'<img src="cid:{image_cid}" alt="{day_forecast["weather_desc"]}" class="weather-icon">'
                else:
                     logging.warning(f"Fetched empty content for weather icon {icon_code} from {icon_url}")

            except requests.exceptions.RequestException as img_err:
                logging.warning(f"Could not fetch weather icon {icon_code}: {img_err}")
                # Keep default img_tag placeholder


            html_content += f"""
            <div class="day-forecast">
              <h2>{day_forecast['day_name']}, {day_forecast['date_obj'].strftime('%B %d')}</h2>
              <p>
                {img_tag}
                <strong>Weather:</strong> {day_forecast['weather_desc']} <br>
                <strong>🌡️ High/Low:</strong> {day_forecast['high_temp']}°C / {day_forecast['low_temp']}°C <br>
                <strong>💨 Wind:</strong> {day_forecast['wind_speed']} m/s ({day_forecast['wind_direction']}) <br>
                <strong>💧 Humidity:</strong> {day_forecast['humidity']}% <br>
                <strong>🌧️ Precipitation:</strong> {day_forecast['precipitation']} mm ({day_forecast['precip_chance']}% chance) <br>
                <strong>☀️ UV Index:</strong> {day_forecast['uv_index']} <br>
                <strong>🌅 Sunrise:</strong> {day_forecast['sunrise']} / <strong>🌇 Sunset:</strong> {day_forecast['sunset']}
              </p>
            </div>
            """

        html_content += "<p><i>Weather data provided by OpenWeatherMap.</i></p></body></html>"

        # --- Send Email ---
        logging.info(f"Preparing to send weekly forecast email to {to_email}...")
        send_email_with_images(
            gmail_user, gmail_password, to_email, email_subject,
            html_content, email_images # Pass the list of images
        )
    else:
        logging.error("Failed to retrieve or process weekly weather data. Email not sent.")

    logging.info("Weekly WeatherNotifier script finished.")


# --- Script Entry Point ---
if __name__ == "__main__":
    # This block executes when the script is run directly
    run_weekly_weather_alert()
