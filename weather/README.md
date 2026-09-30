# Weather

A standalone Flask app that shows the current weather for any city.

## Features

- Enter a city name
- See the current conditions (e.g. "Partly cloudy")
- Temperature in °C and °F, plus humidity
- Also shows "feels like" temperature and wind speed

Weather data comes from [Open-Meteo](https://open-meteo.com/), which is free
and needs no API key. The app looks up the city with Open-Meteo's geocoding
API, then fetches current conditions for those coordinates. If several places
share a name, the best match (usually the largest) is used. To pick a
different one, add a region or country after a comma, e.g. "Portland, Maine"
or "Paris, Texas". The full location shown on the result tells you which place
you got.

Searches use the URL (`/?city=Paris`), so you can bookmark or share a city.

## Getting started

Requires Python 3.9+ and an internet connection. Run these from the
`weather/` folder:

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5004 in your browser. (It uses port 5004 so it can
run alongside the other apps in this repo on 5001–5003.)
