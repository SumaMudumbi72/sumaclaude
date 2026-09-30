import requests
from flask import Flask, render_template, request

app = Flask(__name__)

# Open-Meteo is free and needs no API key: https://open-meteo.com
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 10  # seconds

# WMO weather interpretation codes used by Open-Meteo.
WEATHER_CODES = {
    0: ("Clear sky", "☀️"),
    1: ("Mainly clear", "🌤️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"),
    48: ("Freezing fog", "🌫️"),
    51: ("Light drizzle", "🌦️"),
    53: ("Drizzle", "🌦️"),
    55: ("Heavy drizzle", "🌧️"),
    56: ("Light freezing drizzle", "🌧️"),
    57: ("Freezing drizzle", "🌧️"),
    61: ("Light rain", "🌦️"),
    63: ("Rain", "🌧️"),
    65: ("Heavy rain", "🌧️"),
    66: ("Light freezing rain", "🌧️"),
    67: ("Freezing rain", "🌧️"),
    71: ("Light snow", "🌨️"),
    73: ("Snow", "🌨️"),
    75: ("Heavy snow", "❄️"),
    77: ("Snow grains", "🌨️"),
    80: ("Light showers", "🌦️"),
    81: ("Showers", "🌧️"),
    82: ("Violent showers", "⛈️"),
    85: ("Light snow showers", "🌨️"),
    86: ("Snow showers", "❄️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm with hail", "⛈️"),
    99: ("Thunderstorm with heavy hail", "⛈️"),
}


class WeatherError(Exception):
    """An error with a message that is safe to show the user."""


def find_city(name):
    resp = requests.get(
        GEOCODING_URL,
        params={"name": name, "count": 1, "language": "en", "format": "json"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    results = resp.json().get("results")
    if not results:
        raise WeatherError(f'Couldn\'t find a city called "{name}".')
    return results[0]


def current_weather(lat, lon):
    resp = requests.get(
        FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
            "weather_code,wind_speed_10m",
            "timezone": "auto",
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["current"]


def get_weather(city_name):
    try:
        place = find_city(city_name)
        current = current_weather(place["latitude"], place["longitude"])
    except requests.Timeout:
        raise WeatherError("The weather service took too long to respond. Try again.")
    except (requests.RequestException, KeyError, ValueError):
        raise WeatherError("Couldn't reach the weather service. Try again later.")

    temp_c = current["temperature_2m"]
    feels_c = current["apparent_temperature"]
    description, icon = WEATHER_CODES.get(current["weather_code"], ("Unknown", "🌡️"))
    parts = [place["name"], place.get("admin1"), place.get("country")]
    # Skip empty and repeated parts, e.g. "Tokyo, Tokyo, Japan" -> "Tokyo, Japan".
    location = ", ".join(dict.fromkeys(part for part in parts if part))
    return {
        "location": location,
        "description": description,
        "icon": icon,
        "temp_c": round(temp_c),
        "temp_f": round(temp_c * 9 / 5 + 32),
        "feels_c": round(feels_c),
        "feels_f": round(feels_c * 9 / 5 + 32),
        "humidity": current["relative_humidity_2m"],
        "wind_kmh": round(current["wind_speed_10m"]),
        "time": current["time"].replace("T", " "),
    }


@app.route("/")
def index():
    city = request.args.get("city", "").strip()
    weather = error = None
    if city:
        if len(city) > 100:
            error = "City name must be 100 characters or fewer."
        else:
            try:
                weather = get_weather(city)
            except WeatherError as exc:
                error = str(exc)
    return render_template("index.html", city=city, weather=weather, error=error)


if __name__ == "__main__":
    app.run(debug=True, port=5004)
