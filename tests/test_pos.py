"""Pruebas de la app contra la base real de esquema (db/01..08) usando el cliente falso con RLS activo.
Ejecutar: python -m pytest -q  (requiere Postgres local con la base plantilla; ver tests/README)."""
import base64
import json
from datetime import datetime

import pytest

from pos import fechas, reportes
from pos.config import ConfigError, leer_credenciales
from pos.data import ErrorApp
from tests.conftest import CLAVE


def _jwt(role):
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{b({'alg': 'HS256'})}.{b({'role': role})}.firma"


# ------------------------------------------------------------------ login
def test_login_dueno(entrar):
    p = entrar("a1").perfil
    assert (p["rol"], p["tienda_id"], p["tienda_nombre"]) == ("admin", "TEST_A", "Restaurante A")


def test_login_clave_incorrecta(conn):
    from pos.data import Repo
    from tests.fake_supabase import FakeClient
    with pytest.raises(ErrorApp, match="incorrectos"):
        Repo(FakeClient(conn)).login("a1@test.invalid", "otra-clave")


def test_login_sin_perfil_no_entra(entrar):
    with pytest.raises(ErrorApp, match="no tiene acceso"):
        entrar("c1")


def test_login_empleado_desactivado(entrar, conn):
    admin = entrar("a1")
    uid = next(e["id"] for e in admin.empleados() if e["usuario"] == "luis")
    admin.set_empleado_activo(uid, False)
    with pytest.raises(ErrorApp, match="no tiene acceso"):
        entrar("a2b")
    admin.set_empleado_activo(uid, True)
    assert entrar("a2b").perfil["usuario"] == "luis"


# --------------------------------------------------------- menú y aislamiento
def test_menu_aislado_por_restaurante(entrar):
    a, b = entrar("a1").productos(), entrar("b1").productos()
    assert {p["nombre"]: p["precio"] for p in a if p["nombre"] in ("Hamburguesa", "Gaseosa")} == {"Hamburguesa": 2500, "Gaseosa": 1500}
    assert [(p["nombre"], p["precio"]) for p in b] == [("Hamburguesa", 9000)]   # mismo nombre, otro restaurante, otro precio


def test_menu_editar_y_desactivar(entrar):
    admin, mesero = entrar("a1"), entrar("a2")
    admin.crear_producto("Papas", 1800)
    papas = next(p for p in admin.productos() if p["nombre"] == "Papas")
    admin.editar_producto(papas["id"], precio=2000)
    assert next(p for p in admin.productos() if p["nombre"] == "Papas")["precio"] == 2000
    with pytest.raises(ErrorApp):                        # nombre repetido en el mismo restaurante
        admin.crear_producto("Papas", 1)
    with pytest.raises(ErrorApp):                        # el mesero no administra el menú
        mesero.crear_producto("Intruso", 1)
    with pytest.raises(ErrorApp):
        mesero.editar_producto(papas["id"], precio=1)
    admin.editar_producto(papas["id"], activo=False)
    assert "Papas" not in [p["nombre"] for p in mesero.productos(solo_activos=True)]
    assert "Papas" in [p["nombre"] for p in admin.productos(solo_activos=False)]
    with pytest.raises(ErrorApp):
        admin.crear_producto("", 100)


# ------------------------------------------------------------ flujo de órdenes
def _items(repo, **cant):
    ids = {p["nombre"]: p["id"] for p in repo.productos()}
    return [{"producto_id": ids[n], "cantidad": c, "nota": "sin cebolla" if n == "Hamburguesa" else ""} for n, c in cant.items()]


def test_flujo_mesero_cocina_entrega(entrar):
    ana, luis, cocina, admin = entrar("a2"), entrar("a2b"), entrar("a3"), entrar("a1")
    oid = ana.crear_orden("mesa", "12", "alérgico al maní", _items(ana, Hamburguesa=2, Gaseosa=1))

    mia = next(o for o in ana.ordenes() if o["id"] == oid)
    assert mia["total"] == 6500 and mia["estado"] == "enviada" and mia["mesero"] == "ana"      # precio sale de la base
    assert [(i["producto"], i["cantidad"], i["nota"]) for i in mia["items"]] == [("Hamburguesa", 2, "sin cebolla"), ("Gaseosa", 1, None)]
    assert oid not in [o["id"] for o in luis.ordenes()]                                        # otro mesero no la ve

    t = next(o for o in cocina.tablero_cocina() if o["orden_id"] == oid)                       # cocina la ve, sin precios
    assert t["mesa"] == "12" and t["notas"] == "alérgico al maní" and t["estado"] == "enviada"
    assert all(set(i) == {"producto", "cantidad", "nota"} for i in t["items"])
    assert "total" not in t

    with pytest.raises(ErrorApp):                                                              # cocina no puede saltar estados ni entregar
        cocina.cambiar_estado(oid, "lista")
    cocina.cambiar_estado(oid, "en_preparacion")
    cocina.cambiar_estado(oid, "lista")
    with pytest.raises(ErrorApp):
        cocina.cambiar_estado(oid, "entregada")
    with pytest.raises(ErrorApp):                                                              # otro mesero no puede entregarla
        luis.cambiar_estado(oid, "entregada")
    ana.cambiar_estado(oid, "entregada")
    assert next(o for o in admin.ordenes() if o["id"] == oid)["estado"] == "entregada"
    assert oid not in [o["orden_id"] for o in cocina.tablero_cocina()]                         # sale del tablero


def test_mesero_anula_solo_si_no_empezo(entrar):
    ana, cocina = entrar("a2"), entrar("a3")
    o1 = ana.crear_orden("mostrador", None, None, _items(ana, Gaseosa=1))
    ana.cambiar_estado(o1, "anulada")
    o2 = ana.crear_orden("mostrador", None, None, _items(ana, Gaseosa=1))
    cocina.cambiar_estado(o2, "en_preparacion")
    with pytest.raises(ErrorApp):
        ana.cambiar_estado(o2, "anulada")


def test_validaciones_de_orden(entrar):
    ana = entrar("a2")
    ajeno = entrar("b1").productos()[0]["id"]
    for args in [("mesa", None, None, _items(ana, Gaseosa=1)),                       # mesa sin número
                 ("mostrador", None, None, []),                                       # orden vacía
                 ("mostrador", None, None, _items(ana, Gaseosa=0)),                   # cantidad 0
                 ("mostrador", None, None, [{"producto_id": ajeno, "cantidad": 1}]),  # producto de otro restaurante
                 ("delivery", None, None, _items(ana, Gaseosa=1))]:                   # tipo inválido
        with pytest.raises(ErrorApp):
            ana.crear_orden(*args)


def test_cocina_y_sin_permisos(entrar):
    cocina, ana = entrar("a3"), entrar("a2")
    with pytest.raises(ErrorApp):
        cocina.crear_orden("mostrador", None, None, _items(ana, Gaseosa=1))
    with pytest.raises(ErrorApp):
        cocina.venta_rapida("Hamburguesa", 2500, 1)
    with pytest.raises(ErrorApp):
        ana.tablero_cocina()
    with pytest.raises(ErrorApp):
        ana.archivar_historial()
    with pytest.raises(ErrorApp):
        ana.vincular_empleado("nuevo@test.invalid", "x" * 3, "mesero")
    assert cocina.ventas() == [] and cocina.ordenes() == [] and cocina.auditoria() == []


def test_no_se_puede_escribir_por_fuera_de_las_funciones(entrar):
    ana = entrar("a2")
    with pytest.raises(ErrorApp):   # insertar una orden con un total inventado
        ana._tabla("ordenes", lambda t: t.insert({"tienda_id": "TEST_A", "tipo": "mostrador", "total": 1}))
    with pytest.raises(ErrorApp):
        ana._tabla("ordenes", lambda t: t.update({"estado": "lista"}))
    with pytest.raises(ErrorApp):
        ana._tabla("perfiles", lambda t: t.update({"rol": "admin"}))


# ------------------------------------------------------------ ventas rápidas
def test_venta_rapida(entrar):
    ana, luis, admin, b = entrar("a2"), entrar("a2b"), entrar("a1"), entrar("b1")
    vid = ana.venta_rapida("Hamburguesa", 2500, 2)[0]["id"]
    v = next(x for x in admin.ventas() if x["id"] == vid)
    assert (v["total"], v["vendedor"], v["tienda_id"]) == (5000, "ana", "TEST_A")
    assert vid in [x["id"] for x in ana.ventas()] and vid not in [x["id"] for x in luis.ventas()]
    assert vid not in [x["id"] for x in b.ventas()]
    with pytest.raises(ErrorApp):
        ana.venta_rapida("Hamburguesa", 2500, 0)


# --------------------------------------------------------------- equipo
def test_equipo_vincular_login_y_revocar(entrar, conn):
    admin = entrar("a1")
    admin.vincular_empleado("nuevo@test.invalid", "nuevo", "mesero")
    with pytest.raises(ErrorApp):
        admin.vincular_empleado("nuevo@test.invalid", "otro", "mesero")     # ya vinculado
    with pytest.raises(ErrorApp):
        admin.vincular_empleado("noexiste@test.invalid", "x1", "mesero")
    with pytest.raises(ErrorApp):
        admin.vincular_empleado("nuevo@test.invalid", "xx", "admin")        # no se crean más dueños desde la app
    from pos.data import Repo
    from tests.fake_supabase import FakeClient
    nuevo = Repo(FakeClient(conn))
    conn.admin("update auth.users set encrypted_password = crypt('%s', gen_salt('bf')) where email = 'nuevo@test.invalid';" % CLAVE)
    assert nuevo.login("nuevo@test.invalid", CLAVE)["rol"] == "mesero"
    uid = next(e["id"] for e in admin.empleados() if e["usuario"] == "nuevo")
    admin.set_empleado_activo(uid, False)
    assert nuevo.productos() == []                                           # acceso revocado de inmediato: ya no ve nada
    with pytest.raises(ErrorApp):
        nuevo.crear_orden("mostrador", None, None, _items(admin, Gaseosa=1))
    with pytest.raises(ErrorApp):
        admin.set_empleado_activo(admin.perfil["id"], False)                 # no puede desactivarse a sí mismo
    assert {e["usuario"] for e in entrar("b1").empleados()} == {"admin", "bea"}   # B no ve el equipo de A


# ------------------------------------------- archivar, reportes y auditoría
def test_archivar_no_borra_y_audita(entrar):
    ana, cocina, admin = entrar("a2"), entrar("a3"), entrar("a1")
    pendiente = ana.crear_orden("mesa", "99", None, _items(ana, Gaseosa=1))
    cocina.cambiar_estado(pendiente, "en_preparacion")
    desde, hasta = fechas.rango("Hoy")
    antes = reportes.resumen(admin.ventas(desde, hasta, True), admin.ordenes(desde, hasta, True, False))

    r = admin.archivar_historial()
    assert r["ordenes"] >= 1 and r["ventas"] >= 1

    en_curso = {"enviada", "en_preparacion", "lista"}
    assert all(o["estado"] in en_curso for o in ana.ordenes(desde, hasta))              # el mesero ya no ve lo archivado
    assert ana.ventas() == []
    visibles = admin.ordenes(desde, hasta, incluir_archivados=False)
    assert pendiente in [o["id"] for o in visibles]                                     # la orden en curso NO se archiva
    assert all(o["estado"] in en_curso for o in visibles)                               # solo quedan órdenes en curso
    despues = reportes.resumen(admin.ventas(desde, hasta, True), admin.ordenes(desde, hasta, True, False))
    assert despues == antes                                                              # los reportes no pierden nada
    assert admin.archivar_historial()["ordenes"] == 0                                    # idempotente

    acciones = {a["accion"] for a in admin.auditoria()}
    assert {"orden_creada", "orden_estado", "orden_archivada", "venta_archivada", "producto_creado", "empleado_vinculado"} <= acciones
    assert ana.auditoria() == []                                                          # el mesero no ve la auditoría
    aud_b = entrar("b1").auditoria()                                                      # y B solo ve la suya: nada de lo que pasó en A
    assert aud_b and not any(a["accion"].startswith(("orden", "venta")) or a["usuario"] in ("ana", "luis", "cocina_a") for a in aud_b)


def test_aislamiento_total_entre_restaurantes(entrar):
    a, b = entrar("a1"), entrar("b1")
    ids_a = {o["id"] for o in a.ordenes(incluir_archivados=True)}
    assert ids_a and ids_a.isdisjoint({o["id"] for o in b.ordenes(incluir_archivados=True)})
    assert {v["tienda_id"] for v in b.ventas(incluir_archivados=True)} <= {"TEST_B"}
    with pytest.raises(ErrorApp):
        b.cambiar_estado(next(iter(ids_a)), "anulada")


# ----------------------------------------------------------- módulos puros
def test_reportes_zona_horaria_y_anuladas():
    ventas = [{"creado_en": "2026-11-25T03:30:00+00:00", "total": 1000}]     # 22:30 del 24 en Colombia
    ordenes = [{"creado_en": "2026-11-24T15:00:00+00:00", "total": 5000, "estado": "entregada"},
               {"creado_en": "2026-11-24T16:00:00+00:00", "total": 7000, "estado": "anulada"}]
    r = reportes.resumen(ventas, ordenes)
    assert r == {"ventas_rapidas": 1000, "n_ventas": 1, "ordenes": 5000, "n_ordenes": 1, "anuladas": 1, "total": 6000}
    df = reportes.por_dia(ventas, ordenes)
    assert [str(f) for f in df["fecha"]] == ["2026-11-24"] and int(df["total"][0]) == 6000
    assert reportes.resumen([], [])["total"] == 0 and reportes.por_dia([], []).empty
    assert reportes.a_csv(df).startswith(b"\xef\xbb\xbf")


def test_rangos_de_fechas():
    ref = datetime(2026, 11, 24, 15, 0, tzinfo=fechas.TZ)                     # martes
    assert fechas.rango("Hoy", ref)[0].isoformat() == "2026-11-24T00:00:00-05:00"
    assert fechas.rango("Esta semana", ref)[0].date().isoformat() == "2026-11-23"
    assert fechas.rango("Este mes", ref)[1].date().isoformat() == "2026-12-01"
    assert fechas.rango("Este mes", datetime(2026, 12, 15, tzinfo=fechas.TZ))[1].date().isoformat() == "2027-01-01"
    with pytest.raises(ValueError):
        fechas.rango("Ayer")


def test_config_credenciales():
    ok = {"supabase": {"url": "https://x.supabase.co", "key": _jwt("anon")}}
    assert leer_credenciales(ok)[0] == "https://x.supabase.co"
    viejo = {"connections": {"supabase": {"SUPABASE_URL": "https://y.supabase.co", "SUPABASE_KEY": "sb_publishable_abc"}}}
    assert leer_credenciales(viejo) == ("https://y.supabase.co", "sb_publishable_abc")
    for mala in [{"supabase": {"url": "https://x", "key": _jwt("service_role")}},
                 {"supabase": {"url": "https://x", "key": "sb_secret_abc"}},
                 {"connections": {"supabase": {"SUPABASE_URL": "https://x", "SUPABASE_KEY": _jwt("service_role")}}}]:
        with pytest.raises(ConfigError, match="service_role"):
            leer_credenciales(mala)
    with pytest.raises(ConfigError, match="Faltan"):
        leer_credenciales({})


def test_normalizar_url():
    from pos.config import normalizar_url
    base = "https://abc.supabase.co"
    for u in (base, base + "/", base + "/rest/v1", base + "/rest/v1/", " " + base + "/auth/v1 "):
        assert normalizar_url(u) == base


def test_clave_temporal_flujo_completo(conn, entrar):
    from pos.data import ErrorApp, Repo
    from tests.fake_supabase import FakeClient
    from tests.conftest import CLAVE
    conn.admin("insert into auth.users (id, aud, role, email, encrypted_password) values "
               "('00000000-0000-0000-0000-0000000000e2','authenticated','authenticated','temp2@test.invalid', crypt('x', gen_salt('bf')))")
    admin = entrar("a1")
    admin.vincular_empleado("temp2@test.invalid", "temporal", "mesero")
    assert admin.perfil.get("debe_cambiar_clave") is False                       # el dueño no está obligado
    assert conn.admin("select debe_cambiar_clave from public.perfiles where usuario='temporal'").strip() == "t"
    nuevo = Repo(FakeClient(conn))
    nuevo.login("temp2@test.invalid", "x")                                       # clave temporal de la fixture
    assert nuevo.perfil["debe_cambiar_clave"] is True
    with pytest.raises(ErrorApp):
        nuevo.cambiar_clave("corta")                                              # mínimo 8
    nuevo.cambiar_clave("Mi-clave-propia-1")
    assert nuevo.perfil["debe_cambiar_clave"] is False
    assert conn.admin("select debe_cambiar_clave from public.perfiles where usuario='temporal'").strip() == "f"
    Repo(FakeClient(conn)).login("temp2@test.invalid", "Mi-clave-propia-1")       # la clave nueva funciona
    with pytest.raises(ErrorApp):
        Repo(FakeClient(conn)).login("temp2@test.invalid", "x")                   # la temporal ya no


def test_clave_cambiada_solo_afecta_a_quien_la_llama(conn, entrar):
    conn.admin("update public.perfiles set debe_cambiar_clave = true where usuario in ('ana','luis')")
    entrar("a2")._rpc("clave_cambiada")
    est = conn.admin("select string_agg(usuario||'='||debe_cambiar_clave, ',' order by usuario) from public.perfiles where usuario in ('ana','luis')").strip()
    assert est == "ana=false,luis=true"
    with pytest.raises(Exception):
        Repo = __import__("pos.data", fromlist=["Repo"]).Repo
        Repo(__import__("tests.fake_supabase", fromlist=["FakeClient"]).FakeClient(conn))._rpc("clave_cambiada")   # sin sesión
