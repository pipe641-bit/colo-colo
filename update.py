import hashlib
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

LEAGUES = [
    "chi.1",
    "chi.copa_chile",
    "chi.copa_chi",
    "chi.copa",
    "conmebol.libertadores",
    "conmebol.sudamericana",
]

NOMBRES_COMPETENCIAS = {
    "chi.1": "Liga de Primera de Chile",
    "chi.copa_chile": "Copa Chile",
    "chi.copa_chi": "Copa de la Liga de Chile",
    "chi.copa": "Copa Chile",
    "conmebol.libertadores": "Copa Libertadores",
    "conmebol.sudamericana": "Copa Sudamericana",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}


def obtener_json(url):
    """Consulta ESPN y devuelve el contenido JSON."""
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

            if str(equipo.get("id", "")) == TEAM_ID:
                return True

    return False


def obtener_nombre_competencia(datos, codigo_liga):
    """Obtiene el nombre visible de la competencia."""
    if codigo_liga in NOMBRES_COMPETENCIAS:
        return NOMBRES_COMPETENCIAS[codigo_liga]

    liga = datos.get("league", {})

    if liga:
        return (
            liga.get("displayName")
            or liga.get("name")
            or liga.get("shortName")
            or codigo_liga
        )

    ligas = datos.get("leagues", [])

    if ligas:
        return (
            ligas[0].get("displayName")
            or ligas[0].get("name")
            or ligas[0].get("shortName")
            or codigo_liga
        )

    return codigo_liga


def agregar_partidos_desde_datos(
    datos,
    codigo_liga,
    partidos,
):
    """Agrega únicamente partidos de Colo-Colo y evita duplicados."""
    nombre_competencia = obtener_nombre_competencia(
        datos,
        codigo_liga,
    )

    encontrados = 0

    for partido in datos.get("events", []):
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
    """Crea los doce rangos mensuales de 2026."""
    rangos = []

    for mes in range(1, 13):
        inicio = datetime(
            int(SEASON),
            mes,
            1,
        )

        if mes == 12:
            siguiente = datetime(
                int(SEASON) + 1,
                1,
                1,
            )
        else:
            siguiente = datetime(
                int(SEASON),
                mes + 1,
                1,
            )

        final = siguiente - timedelta(days=1)

        rangos.append(
            (
                inicio.strftime("%Y%m%d"),
                final.strftime("%Y%m%d"),
                inicio.strftime("%m"),
            )
        )

    return rangos


def obtener_partidos():
    """
    Busca los partidos mes por mes y también consulta
    el calendario específico del equipo como respaldo.
    """
    partidos = {}
    errores = []

    for codigo_liga in LEAGUES:
        print("\n" + "=" * 60)
        print(f"🔎 Revisando: {codigo_liga}")
        print("=" * 60)

        for fecha_inicio, fecha_final, numero_mes in obtener_rangos_mensuales():
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

                if encontrados:
                    print(
                        f"✅ Mes {numero_mes}: "
                        f"{encontrados} partido(s)"
                    )

            except Exception as error:
                errores.append(
                    f"{codigo_liga} "
                    f"{fecha_inicio}-{fecha_final}: {error}"
                )

                print(
                    f"⚠️ Error en mes {numero_mes}: {error}"
                )

            time.sleep(0.15)

        urls_respaldo = [
            (
                "https://site.api.espn.com/apis/site/v2/sports/"
                f"soccer/{codigo_liga}/teams/{TEAM_ID}/schedule"
                f"?season={SEASON}&limit=1000"
            ),
            (
                "https://site.web.api.espn.com/apis/fittwo/v3/"
                f"sports/soccer/{codigo_liga}/teams/{TEAM_ID}/schedule"
                f"?season={SEASON}&region=cl&lang=es&limit=1000"
            ),
        ]

        for url in urls_respaldo:
            try:
                datos = obtener_json(url)

                encontrados = agregar_partidos_desde_datos(
                    datos,
                    codigo_liga,
                    partidos,
                )

                print(
                    f"📅 Respaldo {codigo_liga}: "
                    f"{encontrados} registro(s)"
                )

            except Exception as error:
                errores.append(
                    f"{codigo_liga} respaldo: {error}"
                )

                print(
                    f"⚠️ Error en respaldo: {error}"
                )

    if errores:
        print(
            f"\n⚠️ Hubo {len(errores)} consultas con error, "
            "pero el calendario continuará generándose."
        )

    return list(partidos.values())


def convertir_fecha(fecha_texto):
    """Convierte una fecha UTC de ESPN al horario de Chile."""
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
    """Obtiene el equipo local, visitante y condición de Colo-Colo."""
    competencias = partido.get("competitions", [])

    if not competencias:
        return None, None, None, None

    competidores = competencias[0].get(
        "competitors",
        [],
    )

    local = None
    visitante = None

    for competidor in competidores:
        equipo = competidor.get("team", {})

        datos_equipo = {
            "id": str(equipo.get("id", "")),
            "nombre": (
                equipo.get("displayName")
                or equipo.get("shortDisplayName")
                or equipo.get("name")
                or "Equipo por confirmar"
            ),
        }

        if competidor.get("homeAway") == "home":
            local = datos_equipo

        elif competidor.get("homeAway") == "away":
            visitante = datos_equipo

    rival = None
    condicion = None

    if local and local["id"] == TEAM_ID:
        condicion = "local"

        if visitante:
            rival = visitante["nombre"]

    elif visitante and visitante["id"] == TEAM_ID:
        condicion = "visita"

        if local:
            rival = local["nombre"]

    return local, visitante, rival, condicion


def obtener_estadio(partido):
    """Obtiene el nombre del estadio y la ciudad."""
    competencias = partido.get("competitions", [])

    if not competencias:
        return "Estadio por confirmar"

    venue = competencias[0].get("venue", {})

    nombre = (
        venue.get("fullName")
        or venue.get("shortName")
        or "Estadio por confirmar"
    )

    direccion = venue.get("address", {})

    ciudad = (
        direccion.get("city")
        or direccion.get("summary")
    )

    if ciudad and ciudad.lower() not in nombre.lower():
        return f"{nombre}, {ciudad}"

    return nombre


def obtener_datos_estado(partido):
    """
    Obtiene el estado del partido y determina cómo
    debe mostrarse en el calendario.
    """
    status = partido.get("status", {})
    tipo = status.get("type", {})

    nombre = str(
        tipo.get("name")
        or ""
    ).lower()

    descripcion = (
        tipo.get("description")
        or tipo.get("detail")
        or tipo.get("shortDetail")
        or tipo.get("name")
        or "Programado"
    )

    estado_espn = str(descripcion).lower()

    cancelado = (
        "cancel" in nombre
        or "cancel" in estado_espn
    )

    aplazado = any(
        palabra in nombre or palabra in estado_espn
        for palabra in [
            "postpon",
            "suspend",
            "delay",
            "aplaz",
            "suspend",
        ]
    )

    finalizado = any(
        palabra in nombre or palabra in estado_espn
        for palabra in [
            "final",
            "complete",
            "full time",
        ]
    )

    if cancelado:
        return {
            "texto": "Cancelado",
            "ical": "CANCELLED",
            "emoji": "🚫",
        }

    if aplazado:
        return {
            "texto": "Aplazado o suspendido",
            "ical": "TENTATIVE",
            "emoji": "⏸️",
        }

    if finalizado:
        return {
            "texto": "Finalizado",
            "ical": "CONFIRMED",
            "emoji": "✅",
        }

    return {
        "texto": "Programado",
        "ical": "CONFIRMED",
        "emoji": "",
    }


def obtener_transmision(partido):
    """Busca los canales de televisión informados por ESPN."""
    nombres = []

    fuentes = []

    fuentes.extend(
        partido.get("broadcasts", [])
    )

    for competencia in partido.get("competitions", []):
        fuentes.extend(
            competencia.get("broadcasts", [])
        )

    for transmision in fuentes:
        if isinstance(transmision, str):
            nombre = transmision

        elif isinstance(transmision, dict):
            medio = transmision.get("media", {})

            nombre = (
                transmision.get("name")
                or transmision.get("shortName")
                or transmision.get("displayName")
                or medio.get("shortName")
                or medio.get("name")
            )

            if not nombre:
                nombres_transmision = transmision.get(
                    "names",
                    [],
                )

                if nombres_transmision:
                    nombre = ", ".join(
                        str(valor)
                        for valor in nombres_transmision
                    )

        else:
            nombre = None

        if nombre and nombre not in nombres:
            nombres.append(nombre)

    if nombres:
        return ", ".join(nombres)

    return "Por confirmar"


def obtener_enlace(partido):
    """Obtiene el enlace de ESPN correspondiente al partido."""
    for enlace in partido.get("links", []):
        url = enlace.get("href")

        if url:
            return url

    return ""


def cargar_historial():
    """
    Lee el calendario anterior para conservar el número SEQUENCE.
    Solo aumenta cuando cambian los datos de un partido.
    """
    historial = {}

    if not os.path.exists(OUTPUT_FILE):
        return historial

    try:
        with open(OUTPUT_FILE, "rb") as archivo:
            calendario_anterior = Calendar.from_ical(
                archivo.read()
            )

        for componente in calendario_anterior.walk():
            if componente.name != "VEVENT":
                continue

            uid = str(
                componente.get("uid", "")
            )

            if not uid:
                continue

            sequence = int(
                componente.get("sequence", 0)
            )

            content_hash = str(
                componente.get(
                    "x-content-hash",
                    "",
                )
            )

            historial[uid] = {
                "sequence": sequence,
                "hash": content_hash,
            }

    except Exception as error:
        print(
            f"⚠️ No se pudo leer el calendario anterior: "
            f"{error}"
        )

    return historial


def crear_hash_evento(
    titulo,
    inicio,
    final,
    estadio,
    descripcion,
    estado,
):
    """Crea una huella que permite detectar cambios reales."""
    contenido = "|".join(
        [
            titulo,
            inicio.isoformat(),
            final.isoformat(),
            estadio,
            descripcion,
            estado,
        ]
    )

    return hashlib.sha256(
        contenido.encode("utf-8")
    ).hexdigest()


def agregar_alarma(
    evento,
    titulo,
    anticipacion,
    texto_tiempo,
):
    """Agrega una notificación al evento."""
    alarma = Alarm()

    alarma.add(
        "action",
        "DISPLAY",
    )

    alarma.add(
        "description",
        f"{titulo} comienza {texto_tiempo}",
    )

    alarma.add(
        "trigger",
        anticipacion,
    )

    evento.add_component(alarma)


def crear_calendario(partidos, historial):
    """Construye el calendario iCalendar completo."""
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
        (
            "Calendario automático de partidos de "
            "Colo-Colo durante 2026"
        ),
    )

    partidos_ordenados = sorted(
        partidos,
        key=lambda partido: partido.get("date", ""),
    )

    cantidad = 0
    modificados = 0
    momento_actual = datetime.now(timezone.utc)

    for partido in partidos_ordenados:
        inicio = convertir_fecha(
            partido.get("date")
        )

        if inicio is None:
            continue

        if inicio.year != int(SEASON):
            continue

        (
            local,
            visitante,
            rival,
            condicion,
        ) = obtener_competidores(partido)

        if not local or not visitante:
            print(
                "⚠️ Partido omitido porque faltan equipos: "
                f"{partido.get('id')}"
            )

            continue

        estado = obtener_datos_estado(partido)
        estadio = obtener_estadio(partido)
        transmision = obtener_transmision(partido)
        enlace = obtener_enlace(partido)

        competencia = partido.get(
            "_competition_name",
            "Competencia por confirmar",
        )

        if condicion == "local":
            emoji_condicion = "🏠"
            texto_condicion = "Local"

        elif condicion == "visita":
            emoji_condicion = "✈️"
            texto_condicion = "Visita"

        else:
            emoji_condicion = "⚽"
            texto_condicion = "Por confirmar"

        prefijo_estado = estado["emoji"]

        titulo_base = (
            f"{emoji_condicion} "
            f"{local['nombre']} vs {visitante['nombre']}"
        )

        if prefijo_estado:
            titulo = f"{prefijo_estado} {titulo_base}"
        else:
            titulo = titulo_base

        final = inicio + timedelta(hours=2)

        descripcion = (
            f"⚽ Partido: "
            f"{local['nombre']} vs {visitante['nombre']}\n"
            f"🏁 Condición: {texto_condicion}\n"
            f"👤 Rival: {rival or 'Por confirmar'}\n"
            f"🏆 Competencia: {competencia}\n"
            f"📅 Estado: {estado['texto']}\n"
            f"🏟️ Estadio: {estadio}\n"
            f"📺 Transmisión: {transmision}\n"
            f"🗓️ Temporada: {SEASON}"
        )

        if enlace:
            descripcion += (
                f"\n🔗 Más información: {enlace}"
            )

        descripcion += (
            "\n\nCalendario actualizado "
            "automáticamente desde ESPN."
        )

        partido_id = str(
            partido.get("id")
            or partido.get("uid")
        )

        uid = (
            f"espn-{partido_id}"
            f"@colo-colo-{SEASON}"
        )

        content_hash = crear_hash_evento(
            titulo,
            inicio,
            final,
            estadio,
            descripcion,
            estado["ical"],
        )

        datos_anteriores = historial.get(
            uid,
            {},
        )

        sequence_anterior = int(
            datos_anteriores.get(
                "sequence",
                0,
            )
        )

        hash_anterior = datos_anteriores.get(
            "hash",
            "",
        )

        if hash_anterior and hash_anterior != content_hash:
            sequence = sequence_anterior + 1
            modificados += 1

            print(
                f"🔄 Cambio detectado: {titulo}"
            )

        else:
            sequence = sequence_anterior

        evento = Event()

        evento.add("uid", uid)
        evento.add("summary", titulo)
        evento.add("dtstart", inicio)
        evento.add("dtend", final)
        evento.add("dtstamp", momento_actual)
        evento.add("last-modified", momento_actual)
        evento.add("location", estadio)
        evento.add("description", descripcion)
        evento.add("status", estado["ical"])
        evento.add("transp", "OPAQUE")
        evento.add("sequence", sequence)

        evento.add(
            "x-content-hash",
            content_hash,
        )

        if enlace:
            evento.add("url", enlace)

        if estado["ical"] != "CANCELLED":
            agregar_alarma(
                evento,
                titulo_base,
                timedelta(days=-1),
                "en 24 horas",
            )

            agregar_alarma(
                evento,
                titulo_base,
                timedelta(hours=-1),
                "en una hora",
            )

        calendario.add_component(evento)

        cantidad += 1

        print(
            f"➕ {inicio.strftime('%d-%m-%Y %H:%M')} | "
            f"{titulo}"
        )

    return calendario, cantidad, modificados


def guardar_calendario(calendario):
    """Guarda el calendario de forma segura."""
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
        "🔎 Buscando los partidos de "
        "Colo-Colo durante 2026..."
    )

    historial = cargar_historial()
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

    (
        calendario,
        cantidad,
        modificados,
    ) = crear_calendario(
        partidos,
        historial,
    )

    if cantidad == 0:
        print(
            "\n❌ No se crearon eventos válidos."
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
        f"🔄 Partidos modificados: {modificados}"
    )

    print(
        f"✅ Archivo guardado: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
