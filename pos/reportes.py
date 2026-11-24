"""Resúmenes y exportación (solo pandas)."""
import pandas as pd

from .fechas import TZ


def _df(filas, cols):
    df = pd.DataFrame(filas)
    for c in cols:
        if c not in df.columns:
            df[c] = pd.Series(dtype="object")
    return df


def _fecha(serie):
    return pd.to_datetime(serie, utc=True, format="ISO8601").dt.tz_convert(TZ).dt.date


def resumen(ventas: list[dict], ordenes: list[dict]) -> dict:
    """Totales del periodo. Las órdenes anuladas no suman."""
    v = _df(ventas, ["total"])
    o = _df(ordenes, ["total", "estado"])
    o_ok = o[o["estado"] != "anulada"] if len(o) else o
    tv = int(v["total"].sum()) if len(v) else 0
    to = int(o_ok["total"].sum()) if len(o_ok) else 0
    return {
        "ventas_rapidas": tv, "n_ventas": len(v),
        "ordenes": to, "n_ordenes": len(o_ok),
        "anuladas": int((o["estado"] == "anulada").sum()) if len(o) else 0,
        "total": tv + to,
    }


def por_dia(ventas: list[dict], ordenes: list[dict]) -> pd.DataFrame:
    """Una fila por día: ventas rápidas, órdenes y total."""
    v = _df(ventas, ["creado_en", "total"])
    o = _df(ordenes, ["creado_en", "total", "estado"])
    partes = []
    if len(v):
        partes.append(pd.DataFrame({"fecha": _fecha(v["creado_en"]), "ventas_rapidas": v["total"].astype("int64"), "ordenes": 0}))
    if len(o):
        o = o[o["estado"] != "anulada"]
        if len(o):
            partes.append(pd.DataFrame({"fecha": _fecha(o["creado_en"]), "ventas_rapidas": 0, "ordenes": o["total"].astype("int64")}))
    if not partes:
        return pd.DataFrame(columns=["fecha", "ventas_rapidas", "ordenes", "total"])
    df = pd.concat(partes).groupby("fecha", as_index=False).sum()
    df["total"] = df["ventas_rapidas"] + df["ordenes"]
    return df.sort_values("fecha").reset_index(drop=True)


def a_csv(df: pd.DataFrame) -> bytes:
    # utf-8-sig para que Excel abra bien las tildes
    return df.to_csv(index=False).encode("utf-8-sig")
