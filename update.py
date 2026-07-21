import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from icalendar import Alarm, Calendar, Event


TEAM_ID = "2688"
SEASON = "2026"
OUTPUT_FILE = "colo-colo.ics"

CHILE_TZ = ZoneInfo("America/Santiago")

# Posibles competiciones de Colo-Colo.
LEAGUES = [
    "chi.1",
    "chi.copa_chile",
    "chi.copa_chi",
    "chi.copa",
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
    """Consulta una dirección de ESPN y devuelve su contenido JSON."""
    respuesta = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    respuesta.raise_for_status()
    return respuesta.json()


def es_partido_colo_colo(partido):
    """Comprueba si Colo-Colo participa en el partido."""
    for competencia in partido.get("competitions", []):
        for competidor in competencia.get("competitors", []):
            equipo = competidor.get("team", {})
            equipo_id = str(equipo.get("id", ""))

            if equipo_id == TEAM_ID:
                return True

    return False


def obtener_nombre_competencia(datos, codigo_liga):
    """Obtiene el nombre visible de la competición."""
    liga = datos.get("league", {})

    if liga:
        return (
            liga.get("name")
            or liga.get("displayName")
            or liga.get("shortName")
            or codigo_liga
        )

    ligas = datos.get("leagues", [])

    if ligas:
        return (
            ligas[0].get("name")
            or ligas[0].get("displayName")
            or ligas[0].get("shortName")
            or codigo_liga
        )

    return codigo_liga


def agregar_partidos_desde_datos(
    datos,
    codigo_liga,
    partidos,
):
    """
    Agrega únicamente los partidos donde participe Colo-Colo.
    Usa el ID de ESPN para evitar duplicados.
    """
    eventos = datos.get("events", [])

    nombre_competencia = obtener_nombre_competencia(
        datos,
        codigo_liga,
    )

    encontrados = 0

    for partido in eventos:
        if not es_partido_colo_colo(partido):
            continue

        partido_id = str(
            partido.get("id")
            or partido.get("uid")
            or ""
        )

        if not partido_id:
            continue

        partido["_competition_name"] = nombre_competencia
        partido["_league_code"] = codigo_liga

        partidos[partido_id] = partido
        encontrados += 1

    return encontrados


def obtener_rangos_mensuales():
    """Genera los doce rangos mensuales de 2026."""
    rangos = []

    for mes in range(1, 13):
        fecha_inicio = datetime(
            int(SEASON),
            mes,
            1,
        )

        if mes == 12:
            fecha_siguiente = datetime(
                int(SEASON) + 1,
                1,
                1,
            )
        else:
            fecha_siguiente = datetime(
                int(SEASON),
                mes + 1,
                1,
            )

        fecha_final = fecha_siguiente - timedelta(days=1)

        rangos.append(
            (
                fecha_inicio.strftime("%Y%m%d"),
                fecha_final.strftime("%Y%m%d"),
                fecha_inicio.strftime("%B"),
            )
        )

    return rangos


def obtener_partidos():
    """
    Consulta ESPN mes por mes para encontrar todos los partidos
    de Colo-Colo durante 2026.

    También consulta el calendario específico del equipo como respaldo.
    """
    partidos = {}
    errores = []

    rangos_mensuales = obtener_rangos_mensuales()

    for codigo_liga in LEAGUES:
        print("\n" + "=" * 60)
        print(f"🔎 Revisando competición: {codigo_liga}")
        print("=" * 60)

        total_liga = 0

        # Consulta cada mes por separado.
        for fecha_inicio, fecha_final, nombre_mes in rangos_mensuales:
            url = (
                "https://site.api.espn.com/apis/site/v2/sports/"
                f"soccer/{codigo_liga}/scoreboard"
                f"?dates={fecha_inicio}-{fecha_final}"
                "&limit=1000"
            )

            try:
                datos = obtener_json(url)

                encontrados = agregar_partidos_desde_datos(
                    datos,
                    codigo_liga,
                    partidos,
                )

                total_liga += encontrados

                if encontrados > 0:
                    print(
                        f"✅ {nombre_mes}: "
                        f"{encontrados} partido(s) encontrado(s)"
                    )
                else:
                    print(
                        f"➖ {nombre_mes}: "
                        "sin partidos de Colo-Colo"
                    )

            except Exception as error:
                mensaje = (
                    f"{codigo_liga} "
                    f"{fecha_inicio}-{fecha_final}: {error}"
                )

                errores.append(mensaje)

                print(
                    f"⚠️ Error consultando {nombre_mes}: "
                    f"{error}"
                )

            # Pequeña pausa para no saturar ESPN.
            time.sleep(0.2)

        # Consulta el calendario del equipo como respaldo.
        urls_respaldo = [
            (
                "https://site.api.espn.com/apis/site/v2/sports/"
                f"soccer/{codigo_liga}/teams/{TEAM_ID}/schedule"
                f"?season={SEASON}&limit=1000"
            ),
            (
                "https://site.web.api.espn.com/apis/fittwo/v3/"
                f"sports/soccer/{codigo_liga}/teams/"
                f"{TEAM_ID}/schedule"
                f"?season={SEASON}&region=cl&lang=es"
                "&limit=1000"
            ),
        ]

        for url_respaldo in urls_respaldo:
            try:
                datos = obtener_json(url_respaldo)

                encontrados = agregar_partidos_desde_datos(
                    datos,
                    codigo_liga,
                    partidos,
                )

                print(
                    f"📅 Respaldo: "
                    f"{encontrados} registro(s) encontrado(s)"
                )

            except Exception as error:
                mensaje = (
                    f"{codigo_liga} respaldo: {error}"
                )

                errores.append(mensaje)

                print(
                    f"⚠️ Error en respaldo "
                    f"{codigo_liga}: {error}"
                )

        print(
            f"📊 Total encontrado en consultas mensuales "
            f"para {codigo_liga}: {total_liga}"
        )

    if errores:
        print(
            f"\n⚠️ Hubo {len(errores)} consultas con error."
        )

        for error in errores:
            print(f"- {error}")

    return list(partidos.values())


def convertir_fecha(fecha_texto):
    """Convierte la fecha UTC de ESPN al horario de Chile."""
    if not fecha_texto:
        return None

    try:
        fecha_texto = fecha_texto.replace(
            "Z",
            "+00:00",
        )

        fecha = datetime.fromisoformat(fecha_texto)

        if fecha.tzinfo is None:
            fecha = fecha.replace(
                tzinfo=timezone.utc,
            )

        return fecha.astimezone(CHILE_TZ)

    except (ValueError, TypeError) as error:
        print(
            f"⚠️ Fecha inválida: {fecha_texto}. "
            f"Error: {error}"
        )

        return None


def obtener_competidores(partido):
    """Obtiene los equipos local y visitante."""
    competencias = partido.get("competitions", [])

    if not competencias:
        return None, None, None

    competidores = competencias[0].get(
        "competitors",
        [],
    )

    local = None
    visitante = None

    for competidor in competidores:
        equipo = competidor.get("team", {})

        equipo_id = str(
            equipo.get("id", "")
        )

        nombre = (
            equipo.get("displayName")
            or equipo.get("shortDisplayName")
            or equipo.get("name")
            or "Equipo por confirmar"
        )

        datos_equipo = {
            "id": equipo_id,
            "nombre": nombre,
        }

        condicion = competidor.get("homeAway")

        if condicion == "home":
            local = datos_equipo

        elif condicion == "away":
            visitante = datos_equipo

    rival = None

    if local and local["id"] != TEAM_ID:
        rival = local["nombre"]

    elif visitante and visitante["id"] != TEAM_ID:
        rival = visitante["nombre"]

    return local, visitante, rival


def obtener_estadio(partido):
    """Obtiene el estadio del encuentro."""
    competencias = partido.get("competitions", [])

    if not competencias:
        return "Estadio por confirmar"

    competencia = competencias[0]
    estadio = competencia.get("venue", {})

    nombre = (
        estadio.get("fullName")
        or estadio.get("shortName")
        or "Estadio por confirmar"
    )

    direccion = estadio.get("address", {})

    ciudad = (
        direccion.get("city")
        or direccion.get("summary")
    )

    if ciudad and ciudad.lower() not in nombre.lower():
        return f"{nombre}, {ciudad}"

    return nombre


def obtener_estado(partido):
    """Obtiene el estado del partido."""
    estado = partido.get("status", {})
    tipo = estado.get("type", {})

    return (
        tipo.get("description")
        or tipo.get("detail")
        or tipo.get("shortDetail")
        or tipo.get("name")
        or "Programado"
    )


def obtener_enlace(partido):
    """Obtiene el enlace de ESPN del partido, si está disponible."""
    for enlace in partido.get("links", []):
        url = enlace.get("href")

        if url:
            return url

    return ""


def crear_calendario(partidos):
    """Crea el calendario iCalendar."""
    calendario = Calendar()

    calendario.add(
        "prodid",
        "-//Calendario Colo-Colo 2026//pipe641-bit//ES",
    )

    calendario.add("version", "2.0")
    calendario.add("calscale", "GREGORIAN")
    calendario.add("method", "PUBLISH")

    calendario.add(
        "x-wr-calname",
        "Colo-Colo 2026 ⚽",
    )

    calendario.add(
        "x-wr-timezone",
        "America/Santiago",
    )

    calendario.add(
        "x-wr-caldesc",
        "Calendario automático de partidos de Colo-Colo durante 2026",
    )

    partidos_ordenados = sorted(
        partidos,
        key=lambda partido: partido.get("date", ""),
    )

    cantidad_eventos = 0
    momento_actual = datetime.now(timezone.utc)

    for partido in partidos_ordenados:
        inicio = convertir_fecha(
            partido.get("date")
        )

        if inicio is None:
            continue

        if inicio.year != int(SEASON):
            continue

        local, visitante, rival = obtener_competidores(
            partido
        )

        if not local or not visitante:
            print(
                "⚠️ Partido omitido porque faltan equipos: "
                f"{partido.get('id')}"
            )

            continue

        nombre_local = local["nombre"]
        nombre_visitante = visitante["nombre"]

        competencia = partido.get(
            "_competition_name",
            "Competencia por confirmar",
        )

        estadio = obtener_estadio(partido)
        estado = obtener_estado(partido)
        enlace = obtener_enlace(partido)

        titulo = (
            f"⚽ {nombre_local} vs {nombre_visitante}"
        )

        descripcion = (
            f"Partido: {nombre_local} vs {nombre_visitante}\n"
            f"Rival de Colo-Colo: "
            f"{rival or 'Por confirmar'}\n"
            f"Competencia: {competencia}\n"
            f"Estado: {estado}\n"
            f"Estadio: {estadio}\n"
            f"Temporada: {SEASON}"
        )

        if enlace:
            descripcion += f"\nMás información: {enlace}"

        descripcion += (
            "\n\nCalendario actualizado automáticamente "
            "desde ESPN."
        )

        partido_id = str(
            partido.get("id")
            or partido.get("uid")
        )

        evento = Event()

        evento.add(
            "uid",
            f"espn-{partido_id}@colo-colo-{SEASON}",
        )

        evento.add("summary", titulo)
        evento.add("dtstart", inicio)

        evento.add(
            "dtend",
            inicio + timedelta(hours=2),
        )

        evento.add(
            "dtstamp",
            momento_actual,
        )

        evento.add(
            "last-modified",
            momento_actual,
        )

        evento.add("location", estadio)
        evento.add("description", descripcion)
        evento.add("status", "CONFIRMED")
        evento.add("transp", "OPAQUE")
        evento.add("sequence", 0)

        if enlace:
            evento.add("url", enlace)

        alarma = Alarm()

        alarma.add(
            "action",
            "DISPLAY",
        )

        alarma.add(
            "description",
            f"{titulo} comienza en una hora",
        )

        alarma.add(
            "trigger",
            timedelta(hours=-1),
        )

        evento.add_component(alarma)
        calendario.add_component(evento)

        cantidad_eventos += 1

        print(
            f"➕ {inicio.strftime('%d-%m-%Y %H:%M')} | "
            f"{nombre_local} vs {nombre_visitante}"
        )

    return calendario, cantidad_eventos


def guardar_calendario(calendario):
    """Guarda el calendario sin reemplazarlo parcialmente."""
    archivo_temporal = f"{OUTPUT_FILE}.tmp"

    with open(
        archivo_temporal,
        "wb",
    ) as archivo:
        archivo.write(
            calendario.to_ical()
        )

    os.replace(
        archivo_temporal,
        OUTPUT_FILE,
    )


def main():
    print(
        "🔎 Buscando todos los partidos "
        "de Colo-Colo durante 2026..."
    )

    partidos = obtener_partidos()

    print(
        f"\n📊 Partidos únicos encontrados: "
        f"{len(partidos)}"
    )

    if not partidos:
        print(
            "\n❌ ESPN no entregó partidos."
        )

        print(
            "El calendario anterior no será reemplazado."
        )

        sys.exit(1)

    calendario, cantidad = crear_calendario(
        partidos
    )

    if cantidad == 0:
        print(
            "\n❌ No se pudieron crear eventos válidos."
        )

        print(
            "El calendario anterior no será reemplazado."
        )

        sys.exit(1)

    guardar_calendario(calendario)

    print(
        f"\n✅ Calendario generado con "
        f"{cantidad} partidos."
    )

    print(
        f"✅ Archivo guardado: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
