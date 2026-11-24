"""Lectura y validación de las credenciales de Supabase."""
import base64
import json


class ConfigError(Exception):
    pass


def _jwt_role(key: str):
    """Rol declarado dentro de una clave JWT (sin verificar la firma). None si no se puede leer."""
    if key.startswith("sb_secret_"):
        return "service_role"
    if key.startswith("sb_publishable_"):
        return "anon"
    try:
        payload = key.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("role")
    except Exception:
        return None


def leer_credenciales(secrets) -> tuple[str, str]:
    """Acepta [supabase] url/key o el formato anterior [connections.supabase] SUPABASE_URL/SUPABASE_KEY."""
    url = key = None
    try:
        url, key = secrets["supabase"]["url"], secrets["supabase"]["key"]
    except Exception:
        try:
            c = secrets["connections"]["supabase"]
            url, key = c["SUPABASE_URL"], c["SUPABASE_KEY"]
        except Exception:
            pass
    if not url or not key:
        raise ConfigError(
            "Faltan las credenciales de Supabase. Define en los secretos de la app:\n\n"
            "[supabase]\nurl = \"https://TU-PROYECTO.supabase.co\"\nkey = \"TU_CLAVE_ANON_O_PUBLISHABLE\""
        )
    if _jwt_role(key) == "service_role":
        raise ConfigError(
            "La clave configurada es de tipo service_role/secret y se salta toda la seguridad. "
            "Usa la clave anon (publishable) en la app. Rota la clave actual en Supabase si estuvo expuesta."
        )
    return url, key
