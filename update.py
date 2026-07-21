import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime
import pytz
import uuid

URL = "https://www.espn.com/soccer/team/fixtures/_/id/2688/colo-colo"

cal = Calendar()
cal.add("prodid", "-//Colo-Colo Calendario//")
cal.add("version", "2.0")

tz = pytz.timezone("America/Santiago")

headers = {
    "User-Agent": "Mozilla/5.0"
}

html = requests.get(URL, headers=headers).text

soup = BeautifulSoup(html, "lxml")

partidos = soup.find_all("section")

for partido in partidos:
    texto = partido.get_text(" ", strip=True)

    if "Colo Colo" in texto:
        try:
            evento = Event()

            evento.add(
                "summary",
                "⚽ Colo-Colo - Partido"
            )

            evento.add(
                "description",
                texto
            )

            evento.add(
                "uid",
                str(uuid.uuid4())
            )

            fecha = datetime.now(tz)

            evento.add(
                "dtstart",
                fecha
            )

            evento.add(
                "dtend",
                fecha
            )

            cal.add_component(evento)

        except:
            pass


with open("colo-colo.ics", "wb") as archivo:
    archivo.write(cal.to_ical())

print("Calendario generado correctamente")
