import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from icalendar import Alarm, Calendar, Event


TEAM_ID = "2688"
SEASON = "2026"
OUTPUT_FILE = "colo-colo.ics"

CHILE_TZ = ZoneInfo("America/Santiago")

# Competiciones en las que podría participar Colo-Colo.
LEAGUES = [
    "chi.1",
    "chi.copa_chile",
    "conmebol.libertadores",
    "conmebol.sudamericana",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}


def obtener_json(url):
    """Consulta una URL y devuelve su JSON."""
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def obtener_partidos():
    """
    Busca el calendario de Colo-Colo en distintas competiciones.
    Prueba más de una variante del endpoint de ESPN.
    """
    partidos = {}
    errores = []

    for league in LEAGUES:
        urls = [
            (
                "https://site.api.espn.com/apis/site/v2/sports/"
                f"soccer/{league}/teams/{TEAM_ID}/schedule"
                f"?season={SEASON}"
            ),
            (
                "https://site.web.api.espn.com/apis/fittwo/v3/sports/"
                f"soccer/{league}/teams/{TEAM_ID}/schedule"
                f"?season={SEASON}&region=us&lang=es"
            ),
        ]

        datos_competicion = None

        for url in urls:
            try:
                datos = obtener_json(url)

                if datos.get("events"):
                    datos_competicion = datos
                    print(
                        f"✅ {league}: "
                        f"{len(datos['events'])} eventos encontrados"
                    )
                    break

                print(f"⚠️ {league}: endpoint respondió sin eventos")

            except Exception as error:
                errores.append(f"{league}: {error}")
                print(f"⚠️ Error consultando {league}: {error}")

        if not datos_competicion:
            continue

        nombre_liga = (
            datos_competicion.get("league", {}).get("name")
            or datos_competicion.get("season", {}).get("name")
            or league
        )

        for partido in datos_competicion.get("events", []):
            partido_id = str(
                partido.get("id")
                or partido.get("uid")
                or partido.get("date", "")
            )

            if not partido_id:
                continue

            partido["_competition_name"] = nombre_liga
            partidos[partido_id] = partido

    if errores:
        print("\nAlgunas consultas presentaron errores:")
        for error in errores:
            print(f"- {error}")

    return list(partidos.values())


def convertir_fecha(fecha_texto):
    """Convierte la fecha UTC de ESPN al horario de Chile."""
    if not fecha_texto:
        return None

    fecha_texto = fecha_texto.replace("Z", "+00:00")
    fecha = datetime.fromisoformat(fecha_texto)

    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)

    return fecha.astimezone(CHILE_TZ)


def obtener_competidores(partido):
    """Obtiene local, visitante y rival de Colo-Colo."""
    competencias = partido.get("competitions", [])

    if not competencias:
        return None, None, None

    competidores = competencias[0].get("competitors", [])

    local = None
    visitante = None

    for competidor in competidores:
        equipo = competidor.get("team", {})
        equipo_id = str(equipo.get("id", ""))

        nombre = (
            equipo.get("displayName")
            or equipo.get("shortDisplayName")
            or equipo.get("name")
            or "Equipo por confirmar"
        )

        condicion = competidor.get("homeAway")

        if condicion == "home":
            local = {
                "id": equipo_id,
                "nombre": nombre,
            }
        elif condicion == "away":
            visitante = {
                "id": equipo_id,
                "nombre": nombre,
            }

    rival = None

    if local and local["id"] != TEAM_ID:
        rival = local["nombre"]
    elif visitante and visitante["id"] != TEAM_ID:
        rival = visitante["nombre"]

    return local, visitante, rival


def obtener_estadio(partido):
    competencias = partido.get("competitions", [])

    if not competencias:
        return "Estadio por confirmar"

    competencia = competencias[0]
    venue = competencia.get("venue", {})

    nombre = (
        venue.get("fullName")
        or venue.get("shortName")
        or "Estadio por confirmar"
    )

    ciudad = (
        venue.get("address", {}).get("city")
        or venue.get("address", {}).get("summary")
    )

    if ciudad and ciudad.lower() not in nombre.lower():
        return f"{nombre}, {ciudad}"

    return nombre


def obtener_estado(partido):
    status = partido.get("status", {})
    tipo = status.get("type", {})

    return (
        tipo.get("description")
        or tipo.get("detail")
        or tipo.get("name")
        or "Programado"
    )


def crear_calendario(partidos):
    cal = Calendar()

    cal.add("prodid", "-//Calendario Colo-Colo 2026//pipe641-bit//ES")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "Colo-Colo 2026 ⚽")
    cal.add("x-wr-timezone", "America/Santiago")
    cal.add(
        "x-wr-caldesc",
        "Calendario automático de partidos de Colo-Colo durante 2026",
    )

    partidos_ordenados = sorted(
        partidos,
        key=lambda p: p.get("date", ""),
    )

    eventos_agregados = 0

    for partido in partidos_ordenados:
        inicio = convertir_fecha(partido.get("date"))

        if inicio is None or inicio.year != 2026:
            continue

        local, visitante, rival = obtener_competidores(partido)

        if not local or not visitante:
            print(
                f"⚠️ Partido omitido por falta de equipos: "
                f"{partido.get('id')}"
            )
            continue

        nombre_local = local["nombre"]
        nombre_visitante = visitante["nombre"]

        competencia = partido.get("_competition_name", "Competencia")
        estadio = obtener_estadio(partido)
        estado = obtener_estado(partido)

        titulo = f"⚽ {nombre_local} vs {nombre_visitante}"

        descripcion = (
            f"Partido: {nombre_local} vs {nombre_visitante}\n"
            f"Rival de Colo-Colo: {rival or 'Por confirmar'}\n"
            f"Competencia: {competencia}\n"
            f"Estado: {estado}\n"
            f"Estadio: {estadio}\n"
            f"Temporada: 2026\n\n"
            "Calendario actualizado automáticamente desde ESPN."
        )

        evento = Event()

        evento.add("uid", f"espn-{partido.get('id')}@colo-colo-2026")
        evento.add("summary", titulo)
        evento.add("dtstart", inicio)
        evento.add("dtend", inicio + timedelta(hours=2))
        evento.add("dtstamp", datetime.now(timezone.utc))
        evento.add("location", estadio)
        evento.add("description", descripcion)
        evento.add("status", "CONFIRMED")
        evento.add("transp", "OPAQUE")
        evento.add("sequence", 0)

        alarma = Alarm()
        alarma.add("action", "DISPLAY")
        alarma.add("description", f"{titulo} comienza en una hora")
        alarma.add("trigger", timedelta(hours=-1))

        evento.add_component(alarma)
        cal.add_component(evento)

        eventos_agregados += 1

    return cal, eventos_agregados


def guardar_calendario(calendario):
    archivo_temporal = f"{OUTPUT_FILE}.tmp"

    with open(archivo_temporal, "wb") as archivo:
        archivo.write(calendario.to_ical())

    os.replace(archivo_temporal, OUTPUT_FILE)


def main():
    print("Buscando partidos de Colo-Colo en ESPN...")

    partidos = obtener_partidos()

    if not partidos:
        print(
            "\n❌ ESPN no entregó partidos. "
            "El calendario anterior no será reemplazado."
        )
        sys.exit(1)

    calendario, cantidad = crear_calendario(partidos)

    if cantidad == 0:
        print(
            "\n❌ No se pudieron crear eventos válidos para 2026. "
            "El calendario anterior no será reemplazado."
        )
        sys.exit(1)

    guardar_calendario(calendario)

    print(f"\n✅ Calendario generado con {cantidad} partidos.")
    print(f"✅ Archivo guardado: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
