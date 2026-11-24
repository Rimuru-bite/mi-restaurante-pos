"""Rangos de fechas en la zona horaria del restaurante (Colombia, UTC-5, sin horario de verano)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Bogota")
PERIODOS = ("Hoy", "Esta semana", "Este mes")


def ahora() -> datetime:
    return datetime.now(TZ)


def rango(periodo: str, ref: datetime | None = None) -> tuple[datetime, datetime]:
    """(desde, hasta) con hasta exclusivo."""
    ref = (ref or ahora()).astimezone(TZ)
    dia = ref.replace(hour=0, minute=0, second=0, microsecond=0)
    if periodo == "Hoy":
        return dia, dia + timedelta(days=1)
    if periodo == "Esta semana":
        ini = dia - timedelta(days=dia.weekday())          # lunes
        return ini, ini + timedelta(days=7)
    if periodo == "Este mes":
        ini = dia.replace(day=1)
        fin = (ini.replace(year=ini.year + 1, month=1) if ini.month == 12 else ini.replace(month=ini.month + 1))
        return ini, fin
    raise ValueError(f"Periodo desconocido: {periodo}")
