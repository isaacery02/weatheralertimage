import logging
import os
import smtplib
import requests
import azure.functions as func
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Define Azure Function App instance
app = func.FunctionApp()

@app.timer_trigger(schedule="0 0 7 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)
def WeatherAlert(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info("The timer is past due!")

    logging.info("Fetching weather data...")

    # Read API keys and email info from environment variables
    openweather_api_key = os.getenv("OPENWEATHER_API_KEY")
    gmail_user = os.getenv("GMAIL_USER")  # Your Gmail address
    gmail_password = os.getenv("GMAIL_PASSWORD")  # Your App Password
    city = os.getenv("MY_CITY", "London")
    to_email = os.getenv("TO_EMAIL")

    if not openweather_api_key or not gmail_user or not gmail_password:
        logging.error("Missing environment variables. Please set OPENWEATHER_API_KEY, GMAIL_USER, and GMAIL_PASSWORD.")
        return

    # Fetch the weather data
    weather_data = get_weather(city, openweather_api_key)
    
    if weather_data:
        weather_main = weather_data["weather"][0]["main"]
        weather_desc = weather_data["weather"][0]["description"]
        temp = weather_data["main"]["temp"]

        logging.info(f"Weather in {city}: {weather_main} ({weather_desc}), {temp}°C")

        # Send the weather report via email
        email_subject = f"☀️ Today's Weather in {city}"
        email_content = f"Good morning!\n\nThe weather in {city} today is '{weather_desc}' with a temperature of {temp}°C.\n\nHave a great day!"
        
        send_email(gmail_user, gmail_password, to_email, email_subject, email_content)
    else:
        logging.error("Failed to fetch weather data.")

def get_weather(city, api_key):
    """Fetches weather data from OpenWeather API"""
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
    response = requests.get(url)
    
    if response.status_code == 200:
        return response.json()
    else:
        logging.error(f"Error fetching weather: {response.status_code}")
        return None

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
