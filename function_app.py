import logging
import os
import smtplib
import requests
import azure.functions as func
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import datetime
from typing import Dict, Optional

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
    return directions[int((degrees + 11.25) / 22.5) % 16]


def get_weather(lat: str, lon: str, api_key: str) -> Optional[Dict]:
    """Fetches tomorrow's detailed weather using OpenWeather One Call API 3.0."""
    url = f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&exclude=current,minutely,hourly,alerts&appid={api_key}&units=metric"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes

        data = response.json()
        tomorrow = data["daily"][1]  # Get tomorrow's forecast

        return {
            "weather_desc": tomorrow["weather"][0]["description"].capitalize(),
            "high_temp": round(tomorrow["temp"]["max"], 1),
            "low_temp": round(tomorrow["temp"]["min"], 1),
            "wind_speed": round(tomorrow["wind_speed"], 1),
            "wind_direction": get_wind_direction(tomorrow["wind_deg"]),
            "humidity": tomorrow["humidity"],
            "dew_point": round(tomorrow["dew_point"], 1),
            "precipitation": tomorrow.get("rain", 0),  # Rain in mm
            "precip_chance": round(tomorrow["pop"] * 100, 1),  # Probability of precipitation (%)
            "uv_index": tomorrow["uvi"],
            "sunrise": datetime.datetime.utcfromtimestamp(tomorrow["sunrise"]).strftime("%I:%M%p"),
            "sunset": datetime.datetime.utcfromtimestamp(tomorrow["sunset"]).strftime("%I:%M%p"),
            "date": datetime.datetime.utcfromtimestamp(tomorrow["dt"]).strftime("%Y-%m-%d"),
        }
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching weather data: {e}")
        return None
    except (KeyError, ValueError, TypeError) as e:
        logging.error(f"Error parsing weather data: {e}")
        return None


def send_email(user: str, password: str, to_email: str, subject: str, content: str) -> None:
    """Sends an email using Gmail SMTP."""
    try:
        msg = MIMEMultipart()
        msg["From"] = user
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(content, "plain"))

        # Connect to Gmail SMTP server
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(user, password)
        server.sendmail(user, to_email, msg.as_string())
        server.quit()

        logging.info(f"Email sent to {to_email} successfully!")
    except smtplib.SMTPException as e:
        logging.error(f"Error sending email: SMTP error - {e}")
    except Exception as e:
        logging.error(f"Error sending email: Unexpected error - {e}")


# --- Azure Function ---
@app.function_name(name="weatherNotifier")
@app.timer_trigger(
    schedule="0 7 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False
)
def WeatherAlert(myTimer: func.TimerRequest) -> None:
    """
    Timer-triggered Azure Function to fetch weather data and send an email notification.
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
    if not all(
        [
            openweather_api_key,
            gmail_user,
            gmail_password,
            to_email,
            lat,
            lon,
        ]
    ):
        logging.error(
            "Missing environment variables. Please set OPENWEATHER_API_KEY, GMAIL_USER, GMAIL_PASSWORD, TO_EMAIL, LATITUDE, and LONGITUDE."
        )
        return

    try:
        # Basic validation of lat and lon (can be improved)
        float(lat)
        float(lon)
    except ValueError:
        logging.error("LATITUDE and LONGITUDE must be numeric values.")
        return

    # --- Fetch Weather Data ---
    logging.info("Fetching weather data...")
    weather_data = get_weather(lat, lon, openweather_api_key)

    if weather_data:
        email_subject = f"🌦️ {city} Weather: {weather_data['weather_desc']}"

        email_content = f"""
        📍 Location: {city}
        📅 Date: {weather_data['date']}
        🌤️ Weather: {weather_data['weather_desc']}
        🌡️ High/Low: {weather_data['high_temp']}°C / {weather_data['low_temp']}°C
        💨 Wind: {weather_data['wind_speed']} m/s ({weather_data['wind_direction']})
        💧 Humidity: {weather_data['humidity']}%
        ❄️ Dew Point: {weather_data['dew_point']}°C
        🌧️ Precipitation: {weather_data['precipitation']} mm ({weather_data['precip_chance']}% chance)
        ☀️ UV Index: {weather_data['uv_index']}
        🌅 Sunrise: {weather_data['sunrise']}
        🌇 Sunset: {weather_data['sunset']}

        📝 Plan accordingly and stay safe!
        """

        # --- Send Email ---
        logging.info("Sending email...")
        send_email(gmail_user, gmail_password, to_email, email_subject, email_content)

    logging.info("WeatherNotifier function finished.")