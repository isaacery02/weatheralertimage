import logging
import os
import smtplib
import requests
import azure.functions as func
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage # Import necessary for embedding images
import datetime
from typing import Dict, Optional, List, Tuple # Updated typing imports

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

app = func.FunctionApp()

# --- Helper Functions ---
def get_wind_direction(degrees: int) -> str:
    """Converts wind direction in degrees to a readable format (N, NE, E, SE, etc.)."""
    directions = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    # Handle potential None or invalid degree values gracefully
    if degrees is None:
        return "N/A"
    try:
        return directions[int((degrees + 11.25) / 22.5) % 16]
    except (ValueError, TypeError):
        logging.warning(f"Could not parse wind direction degrees: {degrees}")
        return "N/A"


def get_weekly_weather(lat: str, lon: str, api_key: str) -> Optional[List[Dict]]:
    """Fetches the 7-day weather forecast using OpenWeather One Call API 3.0."""
    # One Call API provides up to 8 days (including today). We'll take the next 7.
    url = f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&exclude=current,minutely,hourly,alerts&appid={api_key}&units=metric"
    weekly_forecast = []

    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes

        data = response.json()

        # Get forecast for the next 7 days (indices 1 through 7)
        # Adjust slice if you want today + 6 days, or a different number
        for daily_data in data["daily"][1:8]:
            forecast = {
                "weather_desc": daily_data["weather"][0]["description"].capitalize(),
                "icon": daily_data["weather"][0]["icon"], # Get the icon code
                "high_temp": round(daily_data["temp"]["max"], 1),
                "low_temp": round(daily_data["temp"]["min"], 1),
                "wind_speed": round(daily_data.get("wind_speed", 0), 1), # Use .get for safety
                "wind_direction": get_wind_direction(daily_data.get("wind_deg")), # Use .get for safety
                "humidity": daily_data["humidity"],
                "dew_point": round(daily_data.get("dew_point", 0), 1), # Use .get for safety
                "precipitation": round(daily_data.get("rain", 0),1),  # Rain in mm, use .get
                "precip_chance": round(daily_data.get("pop", 0) * 100, 1),  # Probability of precipitation (%)
                "uv_index": daily_data.get("uvi", "N/A"), # Use .get for safety
                "sunrise": datetime.datetime.fromtimestamp(daily_data["sunrise"], tz=datetime.timezone.utc).strftime("%I:%M%p %Z"), # Add timezone info
                "sunset": datetime.datetime.fromtimestamp(daily_data["sunset"], tz=datetime.timezone.utc).strftime("%I:%M%p %Z"), # Add timezone info
                "date_obj": datetime.datetime.fromtimestamp(daily_data["dt"], tz=datetime.timezone.utc), # Store date object for formatting
                "date_str": datetime.datetime.fromtimestamp(daily_data["dt"], tz=datetime.timezone.utc).strftime("%Y-%m-%d"), # Keep string version too
                "day_name": datetime.datetime.fromtimestamp(daily_data["dt"], tz=datetime.timezone.utc).strftime("%A") # Get day name
            }
            weekly_forecast.append(forecast)

        return weekly_forecast

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching weekly weather data: {e}")
        return None
    except (KeyError, ValueError, TypeError, IndexError) as e:
        logging.error(f"Error parsing weekly weather data: {e}")
        return None


def send_email_with_images(
    user: str,
    password: str,
    to_email: str,
    subject: str,
    html_content: str,
    images: List[Tuple[bytes, str]] # List of (image_bytes, content_id)
) -> None:
    """Sends an HTML email with embedded images using Gmail SMTP."""
    try:
        # Create the root message and fill in the from, to, and subject headers
        # Use 'related' for HTML emails with embedded images
        msg_root = MIMEMultipart('related')
        msg_root['Subject'] = subject
        msg_root['From'] = user
        msg_root['To'] = to_email
        msg_root.preamble = 'This is a multi-part message in MIME format.'

        # Encapsulate the plain and HTML versions of the message body in an
        # 'alternative' part, so message agents can decide which they prefer.
        msg_alternative = MIMEMultipart('alternative')
        msg_root.attach(msg_alternative)

        # We are only sending HTML in this version, but you could add plain text
        # msg_alternative.attach(MIMEText("Please enable HTML to view this email.", 'plain'))
        msg_alternative.attach(MIMEText(html_content, 'html'))

        # Attach images
        for img_data, img_cid in images:
            img = MIMEImage(img_data)
            # Define the image's ID as referenced in the HTML body (<img src="cid:...">)
            # Important: Content-ID should be enclosed in < >
            img.add_header('Content-ID', f'<{img_cid}>')
            msg_root.attach(img)

        # Connect to Gmail SMTP server
        logging.info("Connecting to SMTP server...")
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(user, password)
        logging.info("Sending email...")
        server.sendmail(user, to_email, msg_root.as_string())
        server.quit()
        logging.info(f"Email sent to {to_email} successfully!")

    except smtplib.SMTPException as e:
        logging.error(f"Error sending email: SMTP error - {e}")
    except Exception as e:
        logging.error(f"Error sending email: Unexpected error - {e}")


# --- Azure Function ---
@app.function_name(name="weatherNotifier")
@app.timer_trigger(
    schedule="0 0 7 * * *", # Runs at 7:00 AM UTC every day
    arg_name="myTimer",
    run_on_startup=True,
    use_monitor=False
)
def WeatherAlert(myTimer: func.TimerRequest) -> None:
    """
    Timer-triggered Azure Function to fetch the weekly weather forecast
    and send an email notification with embedded icons.
    """
    if myTimer.past_due:
        logging.warning("The timer is past due!")

    logging.info("WeatherNotifier function started.")

    # --- Configuration ---
    openweather_api_key = os.getenv("OPENWEATHER_API_KEY")
    gmail_user = os.getenv("GMAIL_USER")  # Your Gmail address
    gmail_password = os.getenv("GMAIL_PASSWORD")  # Your App Password
    to_email = os.getenv("TO_EMAIL")
    lat = os.getenv("LATITUDE")
    lon = os.getenv("LONGITUDE")
    city = os.getenv("CITY_NAME", "Unknown Location")

    # --- Validate Environment Variables ---
    required_vars = {
        "OPENWEATHER_API_KEY": openweather_api_key,
        "GMAIL_USER": gmail_user,
        "GMAIL_PASSWORD": gmail_password,
        "TO_EMAIL": to_email,
        "LATITUDE": lat,
        "LONGITUDE": lon,
    }
    missing_vars = [name for name, value in required_vars.items() if not value]
    if missing_vars:
        logging.error(f"Missing environment variables: {', '.join(missing_vars)}")
        return

    try:
        # Basic validation of lat and lon
        float(lat)
        float(lon)
    except ValueError:
        logging.error("LATITUDE and LONGITUDE must be numeric values.")
        return

    # --- Fetch Weekly Weather Data ---
    logging.info(f"Fetching weekly weather data for {city} ({lat}, {lon})...")
    weekly_data = get_weekly_weather(lat, lon, openweather_api_key)

    if weekly_data:
        email_subject = f"🌦️ 7-Day Weather Forecast for {city}"
        email_images = [] # To store (image_bytes, content_id) tuples
        html_content = f"""
        <html>
        <head>
          <style>
            body {{ font-family: sans-serif; line-height: 1.5; }}
            h1 {{ color: #333; }}
            h2 {{ color: #555; border-bottom: 1px solid #eee; padding-bottom: 5px; margin-top: 20px;}}
            .day-forecast {{ margin-bottom: 15px; padding: 10px; border: 1px solid #ddd; border-radius: 5px; background-color: #f9f9f9; }}
            .weather-icon {{ vertical-align: middle; width: 50px; height: 50px; margin-right: 10px; }}
            strong {{ color: #444; }}
          </style>
        </head>
        <body>
          <h1>🗓️ 7-Day Weather Forecast for {city}</h1>
        """

        for day_forecast in weekly_data:
            icon_code = day_forecast['icon']
            icon_url = f"http://openweathermap.org/img/wn/{icon_code}@2x.png"
            image_cid = f"icon_{day_forecast['date_str']}_{icon_code}" # Unique CID for each image

            # Fetch the icon image
            try:
                icon_response = requests.get(icon_url)
                icon_response.raise_for_status()
                email_images.append((icon_response.content, image_cid)) # Store bytes and CID
                img_tag = f'<img src="cid:{image_cid}" alt="{day_forecast["weather_desc"]}" class="weather-icon">'
            except requests.exceptions.RequestException as img_err:
                logging.warning(f"Could not fetch weather icon {icon_code}: {img_err}")
                img_tag = '(icon unavailable)' # Placeholder if image fetch fails


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

        html_content += """
          <p><i>Weather data provided by OpenWeatherMap.</i></p>
        </body>
        </html>
        """

        # --- Send Email ---
        logging.info("Sending weekly forecast email...")
        send_email_with_images(
            gmail_user,
            gmail_password,
            to_email,
            email_subject,
            html_content,
            email_images # Pass the list of images to embed
        )
    else:
        logging.error("Failed to retrieve weekly weather data. Email not sent.")

    logging.info("WeatherNotifier function finished.")
