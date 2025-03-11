import logging
import os
import smtplib
import requests
import azure.functions as func
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Define Azure Function App instance
app = func.FunctionApp()

@app.timer_trigger(schedule="* 1 * * * *", arg_name="myTimer", run_on_startup=True, use_monitor=False)
def WeatherAlert(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info("The timer is past due!")

    logging.info("Fetching weather data...")

    # Read API keys and email info from environment variables
    openweather_api_key = os.getenv("OPENWEATHER_API_KEY")
    gmail_user = os.getenv("GMAIL_USER")  # Your Gmail address
    gmail_password = os.getenv("GMAIL_PASSWORD")  # Your App Password
    to_email = os.getenv("TO_EMAIL")

    if not openweather_api_key or not gmail_user or not gmail_password:
        logging.error("Missing environment variables. Please set OPENWEATHER_API_KEY, GMAIL_USER, and GMAIL_PASSWORD.")
        return

    # Fetch the weather data
    lat = os.getenv("LATITUDE")
    lon = os.getenv("LONGITUDE")
    # Read city name from environment variables
    city = os.getenv("CITY_NAME", "Unknown Location")
    weather_data = get_weather(lat, lon, openweather_api_key)

    
    if weather_data:
        email_subject = f"🌦️ {city} weather: {weather_data["weather_desc"]}"

        email_content = f"""
        📍 Location: {city}  
        📅 Date: {weather_data["date"]}

        🌤️ Weather: {weather_data["weather_desc"]}  
        🌡️ High/Low: {weather_data["high_temp"]}°C / {weather_data["low_temp"]}°C  
        💨 Wind: {weather_data["wind_speed"]} m/s ({weather_data["wind_direction"]})  
        💧 Humidity: {weather_data["humidity"]}%  
        ❄️ Dew Point: {weather_data["dew_point"]}°C  
        🌧️ Precipitation: {weather_data["precipitation"]} mm ({weather_data["precip_chance"]}% chance)  
        ☀️ UV Index: {weather_data["uv_index"]}  
        🌅 Sunrise: {weather_data["sunrise"]}  
        🌇 Sunset: {weather_data["sunset"]}  

        📝 Plan accordingly and stay safe!
        """

        send_email(gmail_user, gmail_password, to_email, email_subject, email_content)



import datetime
from collections import Counter

# Custom mapping for weather descriptions
WEATHER_DETAILS = {
    "clear sky": "☀️ A beautiful sunny day with clear skies.",
    "few clouds": "🌤️ Mostly sunny with a few scattered clouds.",
    "scattered clouds": "🌥️ Partly cloudy with scattered clouds.",
    "broken clouds": "☁️ Mostly cloudy with some breaks of sun.",
    "overcast clouds": "🌫️ Overcast skies, little to no sunshine.",
    "light rain": "🌦️ Light rain showers expected, bring an umbrella.",
    "moderate rain": "🌧️ Rain expected throughout the day, plan accordingly.",
    "heavy rain": "⛈️ Heavy rain with possible thunderstorms.",
    "light snow": "❄️ Light snow showers, roads might be slippery.",
    "moderate snow": "🌨️ Steady snowfall expected, wear warm clothes.",
    "heavy snow": "❄️❄️ Heavy snowfall, potential travel disruptions.",
    "thunderstorm": "⚡ Thunderstorms likely, stay indoors if possible.",
    "mist": "🌫️ Misty conditions, visibility may be reduced.",
    "fog": "🌁 Dense fog, travel may be affected.",
}

import datetime
import requests

def get_weather(lat, lon, api_key):
    """Fetches tomorrow's detailed weather using OpenWeather One Call API 3.0"""
    url = f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&exclude=current,minutely,hourly,alerts&appid={api_key}&units=metric"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()

        # Get tomorrow's forecast (daily[1] is tomorrow)
        tomorrow = data["daily"][1]
        
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
            "sunrise": datetime.datetime.utcfromtimestamp(tomorrow["sunrise"]).strftime('%I:%M%p'),
            "sunset": datetime.datetime.utcfromtimestamp(tomorrow["sunset"]).strftime('%I:%M%p'),
            "date": datetime.datetime.utcfromtimestamp(tomorrow["dt"]).strftime('%Y-%m-%d')
        }

    else:
        logging.error(f"Error fetching weather: {response.status_code}")
        return None

def get_wind_direction(degrees):
    """Converts wind direction in degrees to a readable format (N, NE, E, SE, etc.)"""
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return directions[int((degrees + 11.25) / 22.5) % 16]





def send_email(user, password, to_email, subject, content):
    """Sends an email using Gmail SMTP"""
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
    
    except Exception as e:
        logging.error(f"Error sending email: {str(e)}")
