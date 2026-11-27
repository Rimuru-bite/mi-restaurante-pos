"""Prueba de humo de app.py con un SUSTITUTO de Streamlit (no es Streamlit real): ejecuta cada pantalla por rol
contra datos reales de la base y simula clics/entradas. Atrapa errores de claves, forma de datos y flujo."""
import importlib
import sys
import types

import pytest

from tests.conftest import CLAVE
from tests.fake_supabase import FakeClient


class _Rerun(Exception):
    pass


class _Stop(Exception):
    pass


class _Ctx:
    def __init__(self, st):
        self._st = st

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, n):          # col.button(...), sidebar.x(...) delegan en el sustituto
        return getattr(self._st, n)


class StubSt(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.reset()

    def reset(self):
        self.session_state = {}
        self.inputs, self.press = {}, set()
        self.errors, self.success, self.frames, self.toasts, self.warnings = [], [], [], [], []
        self.claves = {}
        self.fragmentos, self.ejecutados, self.expanders = {}, [], []
        self.md, self.col_specs = [], []
        self.secrets = {"supabase": {"url": "http://fake", "key": "sb_publishable_fake"}}
        self.sidebar = _Ctx(self)

    # --- salida ---
    def _noop(self, *a, **k):
        return None
    set_page_config = title = subheader = write = caption = info = divider = metric = bar_chart = _noop

    def markdown(self, m, *a, **k):
        self.md.append(str(m))

    def warning(self, m, *a, **k):
        self.warnings.append(str(m))

    def error(self, m, *a, **k):
        self.errors.append(str(m))

    def success(self, m, *a, **k):  # noqa: F811 (se redefine como método)
        self.success_msgs.append(str(m))

    def toast(self, m, *a, **k):
        self.toasts.append(str(m))

    def dataframe(self, df, *a, **k):
        self.frames.append(df)

    def download_button(self, *a, **k):
        return False

    # --- control ---
    def rerun(self, *a, **k):
        raise _Rerun()

    def stop(self):
        raise _Stop()

    def fragment(self, *a, **k):
        def envolver(f):
            self.fragmentos[f.__name__] = k.get("run_every")

            def corre(*x, **y):
                self.ejecutados.append(f.__name__)
                return f(*x, **y)
            corre.__name__ = f.__name__
            return corre
        return envolver(a[0]) if (a and callable(a[0])) else envolver

    # --- contenedores ---
    def columns(self, spec, **k):
        self.col_specs.append(spec if isinstance(spec, int) else len(spec))
        return [_Ctx(self) for _ in range(spec if isinstance(spec, int) else len(spec))]

    def tabs(self, nombres):
        self.tab_names = list(nombres)
        return [_Ctx(self) for _ in nombres]

    def container(self, *a, **k):
        return _Ctx(self)
    form = container

    def expander(self, label, *a, **k):
        self.expanders.append(str(label))
        return _Ctx(self)

    # --- widgets ---
    def text_input(self, label, value="", **k):
        self.claves[label] = k.get("key")          # última clave de widget usada por etiqueta
        return self.inputs.get(label, value)

    def number_input(self, label, min_value=None, max_value=None, value=None, **k):
        return self.inputs.get(label, value if value is not None else (min_value or 0))

    def _elegir(self, label, opciones, index=0, **k):
        opciones = list(opciones)
        v = self.inputs.get(label)
        return v if v in opciones else opciones[index or 0]
    selectbox = _elegir

    def radio(self, label, opciones, **k):
        if label == "Sección":                      # selector de secciones del mesero: equivale a sus "pestañas"
            self.tab_names = list(opciones)
        return self._elegir(label, opciones, **k)          # respeta index=

    def checkbox(self, label, **k):
        return self.inputs.get(label, False)

    def button(self, label, key=None, **k):
        return (label in self.press or key in self.press) and not k.get("disabled", False)
    form_submit_button = button


@pytest.fixture
def st_stub(monkeypatch):
    st = StubSt()
    st.success_msgs = []
    st.success = lambda m, *a, **k: st.success_msgs.append(str(m))
    mod_sb = types.ModuleType("supabase")
    holder = {}
    mod_sb.create_client = lambda url, key: FakeClient(holder["conn"])
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setitem(sys.modules, "supabase", mod_sb)
    st._holder = holder
    return st


def correr(st, **kw):
    """Ejecuta app.py una vez (como un 'rerun' de Streamlit). Devuelve True si pidió rerun."""
    st.inputs.update(kw.get("inputs", {}))
    st.press = set(kw.get("press", ()))
    st.errors.clear()
    sys.modules.pop("app", None)
    try:
        importlib.import_module("app")
    except _Rerun:
        return True
    except _Stop:
        return False
    return False


def entrar(st, conn, usuario):
    st._holder["conn"] = conn
    st.session_state.clear()
    assert correr(st, inputs={"Correo": f"{usuario}@test.invalid", "Clave": CLAVE}, press={"Entrar"})    # login → rerun
    assert st.errors == [] and st.session_state["repo"].perfil
    correr(st)


def test_login_incorrecto_muestra_error(st_stub, conn):
    st_stub._holder["conn"] = conn
    correr(st_stub, inputs={"Correo": "a1@test.invalid", "Clave": "mal"}, press={"Entrar"})
    assert st_stub.errors == ["Correo o clave incorrectos."] and "repo" not in st_stub.session_state


def test_credenciales_peligrosas_bloquean_la_app(st_stub):
    st_stub.secrets = {"supabase": {"url": "http://x", "key": "sb_secret_abc"}}
    correr(st_stub)
    assert st_stub.errors and "service_role" in st_stub.errors[0]


def test_pantallas_por_rol(st_stub, conn):
    esperadas = {"a1": ["Nueva orden", "Órdenes", "Cocina", "Resumen", "Historial", "Menú", "Equipo", "Auditoría"],
                 "a2": ["Nueva orden", "Mis órdenes"], "a3": ["Cocina"]}
    for usuario, tabs in esperadas.items():
        entrar(st_stub, conn, usuario)
        assert st_stub.tab_names == tabs, usuario
        assert st_stub.errors == [], (usuario, st_stub.errors)       # ninguna pantalla falla con datos reales


def test_flujo_mesero_envia_orden_y_cocina_la_ve(st_stub, conn):
    entrar(st_stub, conn, "a2")
    # agregar al carrito dos veces y enviar a cocina
    assert correr(st_stub, inputs={"Servicio": "Mesa", "Mesa": "21", "Producto": "Gaseosa · $1.500 COP", "Cantidad": 2,
                                   "Observación (opcional)": "con hielo"}, press={"➕ Agregar"})
    carrito = st_stub.session_state["carrito"]
    assert [(c["nombre"], c["cantidad"], c["nota"]) for c in carrito] == [("Gaseosa", 2, "con hielo")]
    assert correr(st_stub, inputs={"Mesa": "21"}, press={"🚀 Enviar a cocina"})
    assert st_stub.errors == [] and st_stub.session_state["carrito"] == []
    assert any("enviada a cocina" in t for t in st_stub.toasts)

    # sin número de mesa no se envía
    st_stub.session_state["carrito"] = carrito
    correr(st_stub, inputs={"Mesa": ""}, press={"🚀 Enviar a cocina"})
    assert st_stub.errors == ["Indica el número de mesa."]

    # cocina ve la orden y la avanza
    entrar(st_stub, conn, "a3")
    st_stub.press, st_stub.errors = set(), []
    assert correr(st_stub, press={"▶️ Empezar a preparar"})
    assert st_stub.errors == []
    assert correr(st_stub, press={"🟢 Marcar lista"})
    assert st_stub.errors == []

    # el mesero la ve "lista" y la entrega desde su pantalla
    entrar(st_stub, conn, "a2")
    assert correr(st_stub, inputs={"Sección": "Mis órdenes"}, press={"✅ Marcar entregada"})
    assert st_stub.errors == []


def test_dueno_opera_menu_equipo_y_archivo(st_stub, conn):
    entrar(st_stub, conn, "a1")
    assert correr(st_stub, inputs={"Nombre": "Jugo", "Precio (COP)": 3000}, press={"Guardar"})
    assert st_stub.errors == [] and any("Producto creado" in t for t in st_stub.toasts)
    correr(st_stub, press={"Guardar"}, inputs={"Nombre": "Jugo", "Precio (COP)": 3000})        # duplicado → error amigable
    assert st_stub.errors
    correr(st_stub, press={"Vincular"}, inputs={"Correo del empleado": "nadie@test.invalid", "Nombre a mostrar (ej. Ana)": "Zoe"})
    assert st_stub.errors and "Authentication" in st_stub.errors[0]
    # archivar exige confirmar
    correr(st_stub, press={"🗂️ Archivar y reiniciar el día"})
    assert not any("Archivadas" in m for m in st_stub.success_msgs)
    assert correr(st_stub, press={"🗂️ Archivar y reiniciar el día"}, inputs={"Entiendo que se ocultarán las órdenes terminadas y las ventas actuales": True}) is False
    assert any("Archivadas" in m for m in st_stub.success_msgs) and st_stub.errors == []
    # las tablas de reportes salen con datos
    assert any(len(f) for f in st_stub.frames)


def test_clave_temporal_obliga_a_cambiarla_antes_de_entrar(st_stub, conn):
    conn.admin("insert into auth.users (id, aud, role, email, encrypted_password) values "
               f"('00000000-0000-0000-0000-0000000000e3','authenticated','authenticated','tmp3@test.invalid', crypt('{CLAVE}', gen_salt('bf')));"
               "insert into public.perfiles (id, usuario, rol, tienda_id, debe_cambiar_clave) values "
               "('00000000-0000-0000-0000-0000000000e3','tmp3','mesero','TEST_A', true);")
    st_stub.tab_names = []
    entrar(st_stub, conn, "tmp3")
    assert st_stub.tab_names == [] and st_stub.errors == []                       # solo la pantalla de cambio
    correr(st_stub, inputs={"Nueva clave": "uno-123456", "Repite la nueva clave": "otro-123456"}, press={"Guardar clave"})
    assert st_stub.errors == ["Las claves no coinciden."]
    assert correr(st_stub, inputs={"Nueva clave": "Clave-nueva-123", "Repite la nueva clave": "Clave-nueva-123"}, press={"Guardar clave"})
    correr(st_stub)
    assert st_stub.tab_names == ["Nueva orden", "Mis órdenes"]


def test_empleado_desactivado_durante_la_sesion_vuelve_al_login_con_aviso(st_stub, conn):
    entrar(st_stub, conn, "b2")                                    # bea, mesero activo
    try:
        conn.admin("update public.perfiles set activo = false where usuario = 'bea'")
        assert correr(st_stub), st_stub.errors                     # pide rerun y limpia la sesión
        assert "repo" not in st_stub.session_state
        assert "desactivada" in st_stub.session_state["aviso"]
        correr(st_stub)                                            # el login muestra el aviso una sola vez
        assert any("desactivada" in str(m) for m in st_stub.warnings)
    finally:
        conn.admin("update public.perfiles set activo = true where usuario = 'bea'")


def test_menu_vacio_con_cuenta_activa_conserva_su_aviso(st_stub, conn):
    conn.admin("insert into public.restaurantes (tienda_id, nombre) values ('TEST_C','Restaurante C');"
               "insert into auth.users (id, aud, role, email, encrypted_password) values "
               f"('00000000-0000-0000-0000-0000000000e4','authenticated','authenticated','vacio@test.invalid', crypt('{CLAVE}', gen_salt('bf')));"
               "insert into public.perfiles (id, usuario, rol, tienda_id) values ('00000000-0000-0000-0000-0000000000e4','vacio','mesero','TEST_C');")
    entrar(st_stub, conn, "vacio")
    assert any("Todavía no hay productos" in str(m) for m in st_stub.warnings)
    assert "repo" in st_stub.session_state                         # sigue dentro: no es una cuenta desactivada


def test_pedido_nuevo_no_hereda_mesa_ni_observacion_del_anterior(st_stub, conn):
    entrar(st_stub, conn, "a2")
    correr(st_stub, inputs={"Producto": "Gaseosa · $1.500 COP", "Cantidad": 1, "Observación (opcional)": "con hielo"}, press={"➕ Agregar"})
    clave_mesa, clave_obs = st_stub.claves["Mesa"], st_stub.claves["Observación (opcional)"]
    gen = st_stub.session_state["orden_gen"]
    # envío fallido (sin mesa): NO se reinician los campos
    correr(st_stub, inputs={"Mesa": ""}, press={"🚀 Enviar a cocina"})
    assert st_stub.errors == ["Indica el número de mesa."]
    assert st_stub.session_state["orden_gen"] == gen and st_stub.claves["Mesa"] == clave_mesa
    assert st_stub.session_state["carrito"]                                   # el carrito sigue intacto
    # envío correcto: la generación sube y Mesa/Observación nacen con claves nuevas (vacías)
    assert correr(st_stub, inputs={"Mesa": "9"}, press={"🚀 Enviar a cocina"})
    assert st_stub.errors == [] and st_stub.session_state["carrito"] == []
    assert st_stub.session_state["orden_gen"] == gen + 1
    correr(st_stub)
    assert st_stub.claves["Mesa"] != clave_mesa and st_stub.claves["Observación (opcional)"] != clave_obs


def test_historial_muestra_fechas_y_estados_legibles(st_stub, conn):
    entrar(st_stub, conn, "a1")
    repo = st_stub.session_state["repo"]
    prod = repo.productos()[0]
    repo.crear_orden("mostrador", None, None, [{"producto_id": prod["id"], "cantidad": 1}])
    repo.cambiar_estado(next(o["id"] for o in repo.ordenes() if o["estado"] == "enviada"), "en_preparacion")
    repo.venta_rapida(prod["nombre"], prod["precio"], 1)
    st_stub.frames.clear()
    correr(st_stub)
    ordenes = next(f for f in st_stub.frames if "servicio" in f.columns)
    ventas = next(f for f in st_stub.frames if "vendedor" in f.columns and "creado_en" in f.columns)
    assert set(ordenes["estado"]) <= set(sys.modules["app"].ESTADOS.values()) and "🟠 En preparación" in set(ordenes["estado"])
    assert not any("_" in e for e in ordenes["estado"])                        # nada de en_preparacion
    import re
    for col in ("creado_en", "archivado_en"):
        assert all(re.fullmatch(r"(\d{4}-\d\d-\d\d \d\d:\d\d)?", v) for v in ventas[col]), col   # sin ISO crudo (T ni zona)
    assert ventas["creado_en"].iloc[0] != ""


def test_texto_de_equipo_describe_la_clave_temporal(st_stub, conn):
    captions = []
    st_stub.caption = lambda m, *a, **k: captions.append(str(m))
    entrar(st_stub, conn, "a1")
    assert any("clave temporal" in c and "primer ingreso" in c for c in captions)


def _cocina_repo(conn):
    from pos.data import Repo
    r = Repo(FakeClient(conn))
    r.login("a3@test.invalid", CLAVE)
    return r


def test_mis_ordenes_se_refresca_sola_y_resalta_las_listas(st_stub, conn):
    from pos import fechas
    entrar(st_stub, conn, "a2")
    repo = st_stub.session_state["repo"]
    prod = repo.productos()[0]
    oid = repo.crear_orden("mostrador", None, None, [{"producto_id": prod["id"], "cantidad": 1}])
    # refresco automático: fragmento con run_every=5, y solo se ejecuta en la sección «Mis órdenes»
    assert st_stub.fragmentos["mis_ordenes_auto"] == 5
    st_stub.ejecutados.clear()
    correr(st_stub, inputs={"Sección": "Nueva orden"})
    assert "mis_ordenes_auto" not in st_stub.ejecutados
    st_stub.expanders.clear(); st_stub.success_msgs.clear()
    correr(st_stub, inputs={"Sección": "Mis órdenes"})
    assert "mis_ordenes_auto" in st_stub.ejecutados and st_stub.errors == []
    antes = list(st_stub.expanders)
    assert not any("LISTA" in e for e in antes) and not any("listo" in m for m in st_stub.success_msgs)
    # cocina avanza la orden; el siguiente «tick» del refresco la muestra destacada y primera
    k = _cocina_repo(conn)
    k.cambiar_estado(oid, "en_preparacion")
    k.cambiar_estado(oid, "lista")
    st_stub.expanders.clear(); st_stub.success_msgs.clear()
    correr(st_stub, inputs={"Sección": "Mis órdenes"})
    listas = sum(o["estado"] == "lista" for o in repo.ordenes(*fechas.rango("Hoy")))
    assert listas >= 1
    assert "LISTA" in st_stub.expanders[0]                                   # las Lista van primero
    assert sum("LISTA" in e for e in st_stub.expanders) == listas
    assert sum("listo" in m and "para entregar" in m for m in st_stub.success_msgs) == 1     # un solo aviso fijo, no uno por tick
    # sin duplicados ni estados alterados por el refresco
    assert len(st_stub.expanders) == len(antes)
    estado_antes = {o["id"]: o["estado"] for o in repo.ordenes(*fechas.rango("Hoy"))}
    for _ in range(3):
        st_stub.expanders.clear()
        correr(st_stub, inputs={"Sección": "Mis órdenes"})
        assert len(st_stub.expanders) == len(antes)                            # mismas órdenes en cada refresco
    assert {o["id"]: o["estado"] for o in repo.ordenes(*fechas.rango("Hoy"))} == estado_antes


def test_boton_manual_actualizar_sigue_funcionando(st_stub, conn):
    entrar(st_stub, conn, "a2")
    repo = st_stub.session_state["repo"]
    repo.crear_orden("mostrador", None, None, [{"producto_id": repo.productos()[0]["id"], "cantidad": 1}])
    assert correr(st_stub, inputs={"Sección": "Mis órdenes"}, press={"🔄 Actualizar"})    # pide rerun


def test_dueno_no_se_ve_afectado_su_pestana_ordenes_no_es_automatica(st_stub, conn):
    entrar(st_stub, conn, "a1")
    st_stub.ejecutados.clear()
    correr(st_stub)
    assert "mis_ordenes_auto" not in st_stub.ejecutados and "Órdenes" in st_stub.tab_names


# ---------------------------------------------------------------- COCINA (KDS)
def _preparar_cocina(conn):
    """Deja en TEST_A solo 4 pedidos pendientes (mesas 11 a 14) con antigüedades controladas. No devuelve nada."""
    from pos.data import Repo
    conn.admin("update public.ordenes set estado = 'entregada' where tienda_id = 'TEST_A' and estado in ('enviada','en_preparacion','lista')")
    r = Repo(FakeClient(conn)); r.login("a2@test.invalid", CLAVE)
    prod = r.productos()[0]
    k = Repo(FakeClient(conn)); k.login("a3@test.invalid", CLAVE)
    edades = {"11": ("2 minutes 20 seconds", None), "12": ("6 minutes 20 seconds", "en_preparacion"),
              "13": ("12 minutes 20 seconds", None), "14": ("30 minutes 20 seconds", "lista")}
    for mesa, (edad, estado) in edades.items():
        nota = "sin cebolla" if mesa == "13" else None
        oid = r.crear_orden("mesa", mesa, "URGENTE sin sal" if mesa == "12" else None,
                            [{"producto_id": prod["id"], "cantidad": 2, "nota": nota}])
        if estado in ("en_preparacion", "lista"):
            k.cambiar_estado(oid, "en_preparacion")
        if estado == "lista":
            k.cambiar_estado(oid, "lista")
        conn.admin(f"update public.ordenes set creado_en = now() - interval '{edad}' where id = '{oid}'")


def _cocina(st, conn, **inputs):
    entrar(st, conn, "a3")
    st.md.clear(); st.col_specs.clear(); st.warnings.clear(); st.success_msgs.clear()
    correr(st, inputs=inputs)


def test_kds_umbrales_de_tiempo_y_color(st_stub, conn):
    _cocina(st_stub, conn)
    app = sys.modules["app"]
    for mins, esperado in [(0, ("green", False)), (4, ("green", False)), (5, ("orange", False)), (10, ("orange", False)),
                           (11, ("red", True)), (90, ("red", True))]:
        assert app.semaforo(mins) == esperado, mins
    from datetime import datetime, timedelta, timezone
    ahora = datetime.now(timezone.utc)
    assert app.minutos_espera((ahora - timedelta(minutes=7, seconds=30)).isoformat(), ahora) == 7
    assert app.minutos_espera((ahora + timedelta(minutes=3)).isoformat(), ahora) == 0       # nunca negativo


def test_kds_tarjetas_orden_estados_observaciones_y_sin_precios(st_stub, conn):
    _preparar_cocina(conn)
    _cocina(st_stub, conn)
    md = " ".join(st_stub.md)
    mesas = [m.split("## ")[1] for m in st_stub.md if m.startswith("## ")]
    assert mesas == ["Mesa 14", "Mesa 13", "Mesa 12", "Mesa 11"]                 # más antigua primero
    # tiempo y color por umbral; atrasado también cuando ya está Lista
    assert ":green[**⏱ 2 min**]" in md and ":orange[**⏱ 6 min**]" in md
    assert ":red[**⏱ 12 min · ATRASADO**]" in md and ":red[**⏱ 30 min · ATRASADO**]" in md
    # estados con emoji y texto
    assert "🆕 NUEVA" in md and "🟠 EN PREPARACIÓN" in md and "🟢 LISTA" in md
    assert any("Lista para entregar" in m for m in st_stub.success_msgs)
    # observaciones destacadas (de la orden y del ítem)
    assert any("URGENTE sin sal" in w for w in st_stub.warnings)
    assert "📝 sin cebolla" in md
    assert "2 × " in md
    # cocina no ve precios ni totales
    assert "$" not in md and "COP" not in md and not any("$" in w for w in st_stub.warnings)


def test_kds_columnas_1_2_3_y_dos_por_defecto(st_stub, conn):
    _preparar_cocina(conn)
    _cocina(st_stub, conn)
    assert st_stub.col_specs == [2, 2]                                           # 4 pedidos → 2 filas de 2 (por defecto)
    for n, filas in ((1, [1, 1, 1, 1]), (2, [2, 2]), (3, [3, 3])):
        _cocina(st_stub, conn, Columnas=n)
        assert st_stub.col_specs == filas, n
    # reparto por filas: el 1.º (más antiguo) arriba a la izquierda, el 2.º a su derecha
    _cocina(st_stub, conn, Columnas=2)
    mesas = [m.split("## ")[1] for m in st_stub.md if m.startswith("## ")]
    assert mesas[:2] == ["Mesa 14", "Mesa 13"]


def test_kds_acciones_siguen_funcionando(st_stub, conn):
    _preparar_cocina(conn)
    entrar(st_stub, conn, "a3")

    def estados():
        return conn.admin("select string_agg(mesa||'='||estado, ',' order by mesa) from public.ordenes "
                          "where tienda_id='TEST_A' and mesa in ('11','12','13','14') and estado in ('enviada','en_preparacion','lista')").strip()
    assert estados() == "11=enviada,12=en_preparacion,13=enviada,14=lista"
    ids = {m: conn.admin(f"select id from public.ordenes where tienda_id='TEST_A' and mesa='{m}' and estado in ('enviada','en_preparacion','lista')").strip()
           for m in ("11", "12", "13", "14")}
    assert correr(st_stub, press={f"k_{ids['11']}"}) and st_stub.errors == []              # NUEVA → en preparación
    assert estados() == "11=en_preparacion,12=en_preparacion,13=enviada,14=lista"
    assert correr(st_stub, press={f"k_{ids['12']}"}) and st_stub.errors == []              # en preparación → LISTA
    assert estados() == "11=en_preparacion,12=lista,13=enviada,14=lista"                   # el Lista previo se conserva
