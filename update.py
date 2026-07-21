from icalendar import Calendar, Event
from datetime import datetime, timedelta
import pytz
import uuid

cal = Calendar()

cal.add("prodid", "-//Colo-Colo Calendario//")
cal.add("version", "2.0")

tz = pytz.timezone("America/Santiago")

evento = Event()

evento.add("summary", "⚽ Colo-Colo Partido de prueba")

evento.add(
    "description",
    "Calendario automático Colo-Colo"
)

inicio = tz.localize(datetime.now() + timedelta(days=1))

evento.add("dtstart", inicio)
evento.add("dtend", inicio + timedelta(hours=2))

evento.add("uid", str(uuid.uuid4()))

cal.add_component(evento)

with open("colo-colo.ics", "wb") as f:
    f.write(cal.to_ical())

print("Calendario creado")
