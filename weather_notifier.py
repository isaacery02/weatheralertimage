import logging
import os
import smtplib
import requests
# Removed: import azure.functions as func
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import datetime
from typing import Dict, Optional, List, Tuple, Any
import json

# --- Logging Setup ---
# Setup basic logging to console for a standalone script
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler() # Log to standard output/error
        # Optionally add logging to a file:
        # logging.FileHandler("weather_script.log")
    ]
)

# Removed: app = func.FunctionApp()

# --- Constants ---
ACCUWEATHER_BASE_URL = "http://dataservice.accuweather.com"

# --- Helper Functions ---
# (Keep get_wind_direction, get_accuweather_location_key,
#  get_accuweather_forecast, and send_email_with_images exactly as they were)

def get_wind_direction(degrees: Optional[int]) -> str:
    """Converts wind direction in degrees to a readable format (N, NE, E, SE, etc.)."""
    directions = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    if degrees is None:
        return "N/A"
    try:
        degrees = int(degrees)
        return directions[int((degrees + 11.25) / 22.5) % 16]
    except (ValueError, TypeError, IndexError):
        logging.warning(f"Could not parse wind direction degrees: {degrees}")
        return "N/A"

def get_accuweather_location_key(lat: str, lon: str, api_key: str) -> Optional[str]:
    """Gets the AccuWeather Location Key for given latitude and longitude."""
    url = f"{ACCUWEATHER_BASE_URL}/locations/v1/cities/geoposition/search"
    params = {
        "apikey": api_key,
        "q": f"{lat},{lon}",
        "language": "en-us",
        "toplevel": "false"
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, dict) and "Key" in data:
            logging.info(f"Found AccuWeather Location Key: {data['Key']} for ({lat}, {lon})")
            return data["Key"]
        else:
            logging.error(f"Could not find Location Key in AccuWeather response: {data}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching AccuWeather location key: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logging.error(f"AccuWeather Location API Response: {e.response.text}")
        return None
    except (KeyError, ValueError, TypeError) as e:
        logging.error(f"Error parsing AccuWeather location key response: {e}")
        return None


def get_accuweather_forecast(location_key: str, api_key: str, days: int = 5) -> Optional[List[Dict]]:
    """
    Fetches the daily weather forecast from AccuWeather for a given Location Key.
    """
    if days not in [1, 5, 10, 15]:
        logging.warning(f"Unsupported number of forecast days requested: {days}. Defaulting to 5.")
        days = 5

    url = f"{ACCUWEATHER_BASE_URL}/forecasts/v1/daily/{days}day/{location_key}"
    params = {
        "apikey": api_key,
        "language": "en-us",
        "details": "true",
        "metric": "true"
    }
    weekly_forecast = []
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        # logging.debug(f"AccuWeather Forecast Response: {json.dumps(data, indent=2)}")

        if not data or "DailyForecasts" not in data:
            logging.error("AccuWeather forecast response is missing 'DailyForecasts'.")
            return None

        for daily_data in data["DailyForecasts"]:
            temp_data = daily_data.get("Temperature", {})
            day_data = daily_data.get("Day", {})
            wind_data = day_data.get("Wind", {})
            wind_speed_data = wind_data.get("Speed", {})
            wind_direction_data = wind_data.get("Direction", {})
            sun_data = daily_data.get("Sun", {})
            air_and_pollen = daily_data.get("AirAndPollen", [])

            uv_index_info = next((item for item in air_and_pollen if item.get("Name") == "UVIndex"), None)
            uv_index = f"{uv_index_info.get('Value')} ({uv_index_info.get('Category')})" if uv_index_info else "N/A"

            precip_value = day_data.get("Rain", {}).get("Value", 0) + \
                           day_data.get("Snow", {}).get("Value", 0) + \
                           day_data.get("Ice", {}).get("Value", 0)
            precip_prob = day_data.get("PrecipitationProbability", 0)

            wind_speed_kmh = wind_speed_data.get("Value")
            wind_speed_ms = round(wind_speed_kmh / 3.6, 1) if wind_speed_kmh is not None else 0.0

            epoch_date = daily_data.get("EpochDate")
            date_obj = datetime.datetime.fromtimestamp(epoch_date, tz=datetime.timezone.utc) if epoch_date else None
            date_str = date_obj.strftime("%Y-%m-%d") if date_obj else "N/A"
            day_name = date_obj.strftime("%A") if date_obj else "N/A"

            sunrise_str = sun_data.get("Rise")
            sunset_str = sun_data.get("Set")
            try:
                sunrise_dt = datetime.datetime.fromisoformat(sunrise_str) if sunrise_str else None
                sunset_dt = datetime.datetime.fromisoformat(sunset_str) if sunset_str else None
                sunrise_formatted = sunrise_dt.strftime("%I:%M%p %Z") if sunrise_dt else "N/A"
                sunset_formatted = sunset_dt.strftime("%I:%M%p %Z") if sunset_dt else "N/A"
            except (ValueError, TypeError) as dt_err:
                 logging.warning(f"Could not parse sunrise/sunset: {sunrise_str}, {sunset_str} - Error: {dt_err}")
                 sunrise_formatted = "N/A"
                 sunset_formatted = "N/A"

            forecast = {
                "weather_desc": day_data.get("IconPhrase", "N/A").capitalize(),
                "icon": day_data.get("Icon"),
                "high_temp": round(temp_data.get("Maximum", {}).get("Value", 0), 1),
                "low_temp": round(temp_data.get("Minimum", {}).get("Value", 0), 1),
                "wind_speed": wind_speed_ms,
                "wind_direction": get_wind_direction(wind_direction_data.get("Degrees")),
                "humidity": "N/A",
                "dew_point": "N/A",
                "precipitation": round(precip_value, 1),
                "precip_chance": precip_prob,
                "uv_index": uv_index,
                "sunrise": sunrise_formatted,
                "sunset": sunset_formatted,
                "date_obj": date_obj,
                "date_str": date_str,
                "day_name": day_name
            }
            weekly_forecast.append(forecast)

        weekly_forecast.sort(key=lambda x: x["date_obj"] or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))
        return weekly_forecast[:days]

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching AccuWeather forecast data: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logging.error(f"AccuWeather Forecast API Response: {e.response.text}")
        return None
    except (KeyError, ValueError, TypeError, IndexError) as e:
        logging.error(f"Error parsing AccuWeather forecast data: {e}")
        return None


def send_email_with_images(
    user: str,
    password: str,
    to_email: str,
    subject: str,
    html_content: str,
    images: List[Tuple[bytes, str]]
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
        msg_alternative.attach(MIMEText(html_content, 'html'))

        for img_data, img_cid in images:
            img = MIMEImage(img_data)
            img.add_header('Content-ID', f'<{img_cid}>')
            msg_root.attach(img)

        logging.info(f"Connecting to SMTP server smtp.gmail.com:465 as {user}...")
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(user, password)
        logging.info(f"Sending email to {to_email}...")
        server.sendmail(user, to_email, msg_root.as_string())
        server.quit()
        logging.info(f"Email sent to {to_email} successfully!")

    except smtplib.SMTPAuthenticationError as e:
        logging.error(f"Error sending email: SMTP Authentication failed for user {user}. Check email/password/app password. - {e}")
    except smtplib.SMTPException as e:
        logging.error(f"Error sending email: SMTP error - {e}")
    except Exception as e:
        logging.error(f"Error sending email: Unexpected error - {e}")


# --- Main Execution Logic ---

# Removed Azure Function decorators and trigger parameter
def main() -> None:
    """
    Main function to fetch AccuWeather forecast and send email notification.
    """
    logging.info("WeatherNotifier script started (Standalone Version).")

    # --- Configuration ---
    # Load configuration from environment variables
    # IMPORTANT: Ensure these variables are set in your environment before running!
    accuweather_api_key = os.getenv("ACCUWEATHER_API_KEY")
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_PASSWORD") # Use App Password if 2FA is enabled
    to_email = os.getenv("TO_EMAIL")
    lat = os.getenv("LATITUDE")
    lon = os.getenv("LONGITUDE")
    city = os.getenv("CITY_NAME", "Your Location") # Provide a default or set env var
    forecast_days = int(os.getenv("FORECAST_DAYS", "5")) # Default to 5 days

    # --- Validate Environment Variables ---
    required_vars = {
        "ACCUWEATHER_API_KEY": accuweather_api_key,
        "GMAIL_USER": gmail_user,
        "GMAIL_PASSWORD": gmail_password,
        "TO_EMAIL": to_email,
        "LATITUDE": lat,
        "LONGITUDE": lon,
    }
    missing_vars = [name for name, value in required_vars.items() if not value]
    if missing_vars:
        logging.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logging.error("Script cannot continue without configuration. Exiting.")
        return # Stop execution

    try:
        float(lat)
        float(lon)
        if not (1 <= forecast_days <= 15):
             raise ValueError("FORECAST_DAYS must be between 1 and 15.")
    except ValueError as e:
        logging.error(f"Configuration error: {e}. Ensure LATITUDE/LONGITUDE are numeric and FORECAST_DAYS is valid.")
        return

    # --- Fetch AccuWeather Location Key ---
    logging.info(f"Fetching AccuWeather Location Key for {city} ({lat}, {lon})...")
    location_key = get_accuweather_location_key(lat, lon, accuweather_api_key)

    if not location_key:
        logging.error("Failed to get AccuWeather Location Key. Cannot proceed.")
        return

    # --- Fetch AccuWeather Forecast Data ---
    logging.info(f"Fetching {forecast_days}-day AccuWeather forecast using Location Key {location_key}...")
    forecast_data = get_accuweather_forecast(location_key, accuweather_api_key, forecast_days)

    if forecast_data:
        actual_days = len(forecast_data)
        email_subject = f"🌦️ {actual_days}-Day AccuWeather Forecast for {city}"
        email_images = []
        fetched_icons = {} # Cache fetched icons

        # --- Start HTML ---
        # (HTML generation logic remains the same as before)
        html_content = f"""
        <html>
        <head>
          <style>
            body {{ font-family: sans-serif; line-height: 1.5; }}
            h1 {{ color: #333; }}
            h2 {{ color: #555; border-bottom: 1px solid #eee; padding-bottom: 5px; margin-top: 20px;}}
            .day-forecast {{ margin-bottom: 15px; padding: 10px; border: 1px solid #ddd; border-radius: 5px; background-color: #f9f9f9; }}
            .weather-icon {{ vertical-align: middle; width: 75px; height: 45px; margin-right: 10px; object-fit: contain; }}
            .summary-container {{ display: flex; flex-direction: row; flex-wrap: wrap; justify-content: flex-start; margin-bottom: 20px; }}
            .summary-item {{ display: flex; flex-direction: column; align-items: center; border: 1px solid #eee; padding: 8px; margin: 5px; border-radius: 5px; min-width: 60px; text-align: center;}}
            .summary-day {{ font-size: 0.8em; color: #777; margin-bottom: 5px; }}
            .summary-icon-small {{ width: 45px; height: 27px; vertical-align: middle; object-fit: contain;}}
            strong {{ color: #444; }}
            .detail-label {{ display: inline-block; min-width: 100px; }}
          </style>
        </head>
        <body>
          <h1>🗓️ {actual_days}-Day Weather Forecast for {city}</h1>
          <div class="summary-container">
        """

        # --- Create Image Summary Line ---
        for day_forecast in forecast_data:
            icon_code = day_forecast.get('icon')
            date_str = day_forecast.get('date_str', 'no_date')
            weather_desc = day_forecast.get('weather_desc', 'N/A')
            day_name = day_forecast.get('day_name', 'N/A')

            if icon_code:
                icon_code_str = str(icon_code).zfill(2)
                icon_url = f"https://developer.accuweather.com/sites/default/files/{icon_code_str}-s.png"
                image_cid = f"summary_icon_{date_str}_{icon_code_str}"

                if icon_code_str not in fetched_icons:
                    try:
                        icon_response = requests.get(icon_url, timeout=10) # Add timeout
                        icon_response.raise_for_status()
                        icon_bytes = icon_response.content
                        fetched_icons[icon_code_str] = icon_bytes
                        email_images.append((icon_bytes, image_cid))
                    except requests.exceptions.RequestException as img_err:
                        logging.warning(f"Could not fetch summary AccuWeather icon {icon_code_str} ({icon_url}): {img_err}")
                        fetched_icons[icon_code_str] = None
                else:
                    icon_bytes = fetched_icons[icon_code_str]
                    if icon_bytes and not any(cid == image_cid for _, cid in email_images):
                         email_images.append((icon_bytes, image_cid))

                if fetched_icons.get(icon_code_str): # Use .get() for safety
                    html_content += f"""
                    <div class="summary-item">
                      <div class="summary-day">{day_name}</div>
                      <img src="cid:{image_cid}" alt="{weather_desc}" class="summary-icon-small" title="{weather_desc}">
                    </div>
                    """
                else:
                    html_content += f"""
                    <div class="summary-item">
                      <div class="summary-day">{day_name}</div>
                      ({weather_desc})
                    </div>
                    """
            else:
                 html_content += f"""
                    <div class="summary-item">
                      <div class="summary-day">{day_name}</div>
                      ({weather_desc})
                    </div>
                    """
        html_content += """
          </div>
        """ # End summary container

        # --- Create Detailed Daily Forecast Sections ---
        for day_forecast in forecast_data:
            icon_code = day_forecast.get('icon')
            date_str = day_forecast.get('date_str', 'no_date')
            weather_desc = day_forecast.get('weather_desc', 'N/A')
            img_tag = '(icon unavailable)'

            if icon_code:
                icon_code_str = str(icon_code).zfill(2)
                image_cid = f"summary_icon_{date_str}_{icon_code_str}"
                if fetched_icons.get(icon_code_str):
                    img_tag = f'<img src="cid:{image_cid}" alt="{weather_desc}" class="weather-icon" title="{weather_desc}">'
                else:
                    img_tag = f'({weather_desc} - icon unavailable)'

            # Format date nicely for the heading
            date_heading = day_forecast.get('date_obj').strftime('%B %d') if day_forecast.get('date_obj') else ''

            html_content += f"""
            <div class="day-forecast">
              <h2>{day_forecast.get('day_name', '')}, {date_heading}</h2>
              <p>
                {img_tag} <br>
                <span class="detail-label"><strong>Weather:</strong></span> {weather_desc} <br>
                <span class="detail-label"><strong>🌡️ High/Low:</strong></span> {day_forecast.get('high_temp', 'N/A')}°C / {day_forecast.get('low_temp', 'N/A')}°C <br>
                <span class="detail-label"><strong>💨 Wind:</strong></span> {day_forecast.get('wind_speed', 'N/A')} m/s ({day_forecast.get('wind_direction', 'N/A')}) <br>
                <span class="detail-label"><strong>💧 Humidity:</strong></span> {day_forecast.get('humidity', 'N/A')} <br>
                <span class="detail-label"><strong>🌧️ Precip:</strong></span> {day_forecast.get('precipitation', 'N/A')} mm ({day_forecast.get('precip_chance', 'N/A')}% chance) <br>
                <span class="detail-label"><strong>☀️ UV Index:</strong></span> {day_forecast.get('uv_index', 'N/A')} <br>
                <span class="detail-label"><strong>🌅 Sunrise:</strong></span> {day_forecast.get('sunrise', 'N/A')} / <strong>🌇 Sunset:</strong> {day_forecast.get('sunset', 'N/A')}
              </p>
            </div>
            """

        html_content += """
          <p><i>Weather data provided by AccuWeather.</i></p>
        </body>
        </html>
        """

        # --- Send Email ---
        logging.info("Preparing to send forecast email...")
        send_email_with_images(
            gmail_user,
            gmail_password,
            to_email,
            email_subject,
            html_content,
            email_images
        )
    else:
        logging.error("Failed to retrieve AccuWeather forecast data. Email not sent.")

    logging.info("WeatherNotifier script finished.")


# --- Script Entry Point ---
if __name__ == "__main__":
    # This block executes when the script is run directly
    main()