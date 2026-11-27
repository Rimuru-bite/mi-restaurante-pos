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
        self.secrets = {"supabase": {"url": "http://fake", "key": "sb_publishable_fake"}}
        self.sidebar = _Ctx(self)

    # --- salida ---
    def _noop(self, *a, **k):
        return None
    set_page_config = title = subheader = markdown = write = caption = info = divider = metric = bar_chart = _noop

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
        return (lambda f: f) if (not a or not callable(a[0])) else a[0]

    # --- contenedores ---
    def columns(self, spec, **k):
        return [_Ctx(self) for _ in range(spec if isinstance(spec, int) else len(spec))]

    def tabs(self, nombres):
        self.tab_names = list(nombres)
        return [_Ctx(self) for _ in nombres]

    def container(self, *a, **k):
        return _Ctx(self)
    expander = form = container

    # --- widgets ---
    def text_input(self, label, value="", **k):
        self.claves[label] = k.get("key")          # última clave de widget usada por etiqueta
        return self.inputs.get(label, value)

    def number_input(self, label, min_value=None, max_value=None, value=None, **k):
        return self.inputs.get(label, value if value is not None else (min_value or 0))

    def _elegir(self, label, opciones, **k):
        opciones = list(opciones)
        v = self.inputs.get(label)
        return v if v in opciones else opciones[0]
    selectbox = radio = _elegir

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
    assert correr(st_stub, press={"✅ Marcar entregada"})
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
