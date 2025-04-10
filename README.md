Deploy the image as follows:

docker run
-d
--name weather-cron-container
-e OPENWEATHER_API_KEY="YOUR_OPENWEATHER_API_KEY"
-e GMAIL_USER="your_email@gmail.com⁠"
-e GMAIL_PASSWORD="YOUR_GMAIL_APP_PASSWORD"
-e TO_EMAIL="recipient_email@example.com⁠"
-e LATITUDE="YOUR_LATITUDE"
-e LONGITUDE="YOUR_LONGITUDE"
-e CITY_NAME="YourCity"
py-weather-cron:latest
