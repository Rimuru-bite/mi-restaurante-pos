"""POS Restaurante: interfaz Streamlit. La seguridad real vive en la base de datos (RLS y funciones);
aquí solo se muestran las pantallas que corresponden a cada rol."""
import pandas as pd
import streamlit as st

from pos import fechas, reportes
from pos.config import ConfigError, leer_credenciales
from pos.data import ErrorApp, Repo

st.set_page_config(page_title="POS Restaurante", page_icon="🍽️", layout="wide")

ESTADOS = {"enviada": "🟡 Enviada", "en_preparacion": "🟠 En preparación", "lista": "🟢 Lista",
           "entregada": "✅ Entregada", "anulada": "⛔ Anulada"}


def cop(x) -> str:
    return f"${int(x or 0):,} COP".replace(",", ".")


def fmt_fecha(v) -> str:
    """Fecha local legible (AAAA-MM-DD HH:MM) o vacío si no hay fecha."""
    if not v:
        return ""
    return pd.to_datetime(v, utc=True).tz_convert(fechas.TZ).strftime("%Y-%m-%d %H:%M")


def seguro(fn, ok=None):
    """Ejecuta una acción y muestra el error de forma amigable. Devuelve (hecho, resultado)."""
    try:
        r = fn()
        if ok:
            st.toast(ok)
        return True, r
    except ErrorApp as e:
        st.error(str(e))
        return False, None


# ======================================================================= LOGIN
def pantalla_login(url: str, key: str):
    st.title("🍽️ POS Restaurante")
    aviso = st.session_state.pop("aviso", None)
    if aviso:
        st.warning(aviso)
    with st.form("login"):
        email = st.text_input("Correo")
        clave = st.text_input("Clave", type="password")
        entrar = st.form_submit_button("Entrar")
    if entrar:
        from supabase import create_client          # un cliente por sesión: nunca compartido entre usuarios
        repo = Repo(create_client(url, key))
        ok, _ = seguro(lambda: repo.login(email, clave))
        if ok:
            st.session_state["repo"] = repo
            st.session_state["carrito"] = []
            st.rerun()


# ============================================================ CLAVE TEMPORAL
def pantalla_cambiar_clave(repo: Repo):
    st.title("🔐 Crea tu clave")
    st.info("Entraste con una clave temporal. Elige tu propia clave para continuar (mínimo 8 caracteres).")
    with st.form("cambiar_clave"):
        n1 = st.text_input("Nueva clave", type="password")
        n2 = st.text_input("Repite la nueva clave", type="password")
        enviar = st.form_submit_button("Guardar clave", type="primary")
    if enviar:
        if n1 != n2:
            st.error("Las claves no coinciden.")
        else:
            ok, _ = seguro(lambda: repo.cambiar_clave(n1), "Clave actualizada")
            if ok:
                st.rerun()
    if st.button("Cerrar sesión"):
        repo.logout()
        st.session_state.clear()
        st.rerun()


# ================================================================ NUEVA ORDEN
def tab_nueva_orden(repo: Repo):
    productos = repo.productos(solo_activos=True)
    if not productos:
        st.warning("Todavía no hay productos en el menú. El dueño debe agregarlos primero.")
        return
    por_nombre = {f'{p["nombre"]} · {cop(p["precio"])}': p for p in productos}
    carrito = st.session_state.setdefault("carrito", [])
    gen = st.session_state.setdefault("orden_gen", 0)       # sube al enviar una orden: los campos del pedido anterior no pasan al siguiente

    c1, c2 = st.columns(2)
    tipo = c1.radio("Servicio", ["Mesa", "Mostrador"], horizontal=True, key="orden_tipo")
    mesa = c2.text_input("Mesa", key=f"orden_mesa_{gen}", disabled=(tipo == "Mostrador"), max_chars=30)

    with st.container(border=True):
        a, b, c = st.columns([3, 1, 3])
        sel = a.selectbox("Producto", list(por_nombre.keys()), key="orden_prod")
        cant = b.number_input("Cantidad", min_value=1, max_value=99, value=1, key="orden_cant")
        nota = c.text_input("Observación (opcional)", key=f"orden_nota_{gen}", max_chars=200)
        if st.button("➕ Agregar"):
            p = por_nombre[sel]
            carrito.append({"producto_id": p["id"], "nombre": p["nombre"], "precio": p["precio"],
                            "cantidad": int(cant), "nota": nota.strip()})
            st.rerun()

    if carrito:
        st.subheader("Orden actual")
        total = 0
        for i, it in enumerate(carrito):
            sub = it["precio"] * it["cantidad"]
            total += sub
            x, y = st.columns([6, 1])
            x.write(f'**{it["cantidad"]} × {it["nombre"]}** — {cop(sub)}' + (f' · _{it["nota"]}_' if it["nota"] else ""))
            if y.button("✖", key=f"quitar_{i}"):
                carrito.pop(i)
                st.rerun()
        st.metric("Total", cop(total))
        notas = st.text_input("Notas generales de la orden (opcional)", key=f"orden_notas_{gen}", max_chars=300)
        e1, e2 = st.columns(2)
        if e1.button("🚀 Enviar a cocina", type="primary"):
            if tipo == "Mesa" and not mesa.strip():
                st.error("Indica el número de mesa.")
            else:
                ok, _ = seguro(lambda: repo.crear_orden("mesa" if tipo == "Mesa" else "mostrador", mesa or None, notas or None, carrito),
                               "Orden enviada a cocina")
                if ok:
                    st.session_state["carrito"] = []
                    st.session_state["orden_gen"] = gen + 1
                    st.rerun()
        if e2.button("Vaciar"):
            st.session_state["carrito"] = []
            st.rerun()

    with st.expander("Venta rápida (sin pasar por cocina)"):
        sel_v = st.selectbox("Producto", list(por_nombre.keys()), key="vr_prod")
        cant_v = st.number_input("Cantidad", min_value=1, max_value=99, value=1, key="vr_cant")
        if st.button("Registrar venta"):
            p = por_nombre[sel_v]
            ok, _ = seguro(lambda: repo.venta_rapida(p["nombre"], p["precio"], cant_v), "Venta registrada")


# ====================================================================== ÓRDENES
def tab_ordenes(repo: Repo):
    es_admin = repo.perfil["rol"] == "admin"
    desde, hasta = fechas.rango("Hoy")
    ordenes = repo.ordenes(desde, hasta, incluir_archivados=False)
    if st.button("🔄 Actualizar", key="act_ordenes"):
        st.rerun()
    if not ordenes:
        st.info("No hay órdenes hoy.")
        return
    ordenes = sorted(ordenes, key=lambda o: o["estado"] != "lista")        # las Lista primero (el orden anterior se conserva)
    n_listas = sum(o["estado"] == "lista" for o in ordenes)
    if n_listas:
        st.success(f"🔔 {n_listas} pedido{'s' if n_listas > 1 else ''} listo{'s' if n_listas > 1 else ''} para entregar")
    for o in ordenes:
        estado = ESTADOS[o["estado"]] if o["estado"] != "lista" else "🟢 **¡LISTA PARA ENTREGAR!**"
        titulo = f'{estado} · {"Mesa " + o["mesa"] if o["tipo"] == "mesa" else "Mostrador"} · {cop(o["total"])}'
        with st.expander(titulo, expanded=o["estado"] in ("enviada", "en_preparacion", "lista")):
            hora = pd.to_datetime(o["creado_en"], utc=True).tz_convert(fechas.TZ).strftime("%H:%M")
            st.caption(f'{hora} · {o["mesero"] or "—"}' + (f' · {o["notas"]}' if o["notas"] else ""))
            for it in o.get("items", []):
                st.write(f'{it["cantidad"]} × {it["producto"]}' + (f' — _{it["nota"]}_' if it["nota"] else ""))
            acciones = []
            if o["estado"] == "lista":
                acciones.append(("✅ Marcar entregada", "entregada"))
            if es_admin and o["estado"] == "enviada":
                acciones.append(("▶️ En preparación", "en_preparacion"))
            if es_admin and o["estado"] == "en_preparacion":
                acciones.append(("🟢 Lista", "lista"))
            if o["estado"] == "enviada" or (es_admin and o["estado"] in ("en_preparacion", "lista")):
                acciones.append(("⛔ Anular", "anulada"))
            cols = st.columns(max(len(acciones), 1))
            for col, (etiqueta, nuevo) in zip(cols, acciones):
                if col.button(etiqueta, key=f'{o["id"]}_{nuevo}'):
                    ok, _ = seguro(lambda n=nuevo: repo.cambiar_estado(o["id"], n))
                    if ok:
                        st.rerun()


@st.fragment(run_every=5)
def mis_ordenes_auto(repo: Repo):
    """«Mis órdenes» del mesero: se refresca sola cada 5 s. Solo existe mientras esa sección está seleccionada."""
    tab_ordenes(repo)


# ======================================================================= COCINA
@st.fragment(run_every=5)
def tab_cocina(repo: Repo):
    """Se refresca sola cada 5 segundos."""
    ok, tablero = seguro(repo.tablero_cocina)
    if not ok:
        return
    if not tablero:
        st.info("No hay órdenes pendientes. 🎉")
        return
    for o in tablero:
        hora = pd.to_datetime(o["creado_en"], utc=True).tz_convert(fechas.TZ).strftime("%H:%M")
        with st.container(border=True):
            st.markdown(f'### {"Mesa " + o["mesa"] if o["tipo"] == "mesa" else "Mostrador"} · {ESTADOS[o["estado"]]}')
            st.caption(f'{hora} · {o["mesero"] or "—"}')
            for it in o["items"]:
                st.markdown(f'**{it["cantidad"]} × {it["producto"]}**' + (f' — _{it["nota"]}_' if it.get("nota") else ""))
            if o.get("notas"):
                st.info(o["notas"])
            if o["estado"] == "enviada" and st.button("▶️ Empezar a preparar", key=f'k_{o["orden_id"]}'):
                if seguro(lambda: repo.cambiar_estado(o["orden_id"], "en_preparacion"))[0]:
                    st.rerun(scope="fragment")
            if o["estado"] == "en_preparacion" and st.button("🟢 Marcar lista", key=f'k_{o["orden_id"]}'):
                if seguro(lambda: repo.cambiar_estado(o["orden_id"], "lista"))[0]:
                    st.rerun(scope="fragment")
            if o["estado"] == "lista":
                st.success("Lista para entregar")


# ======================================================================= RESUMEN
def tab_resumen(repo: Repo):
    periodo = st.selectbox("Periodo", fechas.PERIODOS, key="res_periodo")
    desde, hasta = fechas.rango(periodo)
    ventas = repo.ventas(desde, hasta, incluir_archivados=True)      # los reportes incluyen lo archivado
    ordenes = repo.ordenes(desde, hasta, incluir_archivados=True, con_items=False)
    r = reportes.resumen(ventas, ordenes)
    a, b, c, d = st.columns(4)
    a.metric("Total", cop(r["total"]))
    b.metric("Órdenes", f'{r["n_ordenes"]} · {cop(r["ordenes"])}')
    c.metric("Ventas rápidas", f'{r["n_ventas"]} · {cop(r["ventas_rapidas"])}')
    d.metric("Anuladas", r["anuladas"])
    df = reportes.por_dia(ventas, ordenes)
    if df.empty:
        st.info("Sin movimientos en este periodo.")
        return
    st.bar_chart(df.set_index("fecha")["total"])
    st.dataframe(df)
    st.download_button("⬇️ Descargar resumen (CSV)", reportes.a_csv(df), f"resumen_{periodo.lower().replace(' ', '_')}.csv", "text/csv")


# ===================================================================== HISTORIAL
def tab_historial(repo: Repo):
    c1, c2 = st.columns(2)
    periodo = c1.selectbox("Periodo", fechas.PERIODOS, key="hist_periodo")
    incluir = c2.checkbox("Mostrar también lo archivado", key="hist_arch")
    desde, hasta = fechas.rango(periodo)
    ordenes = repo.ordenes(desde, hasta, incluir_archivados=incluir, con_items=True)
    ventas = repo.ventas(desde, hasta, incluir_archivados=incluir)

    st.subheader("Órdenes")
    if ordenes:
        df_o = pd.DataFrame([{
            "fecha": pd.to_datetime(o["creado_en"], utc=True).tz_convert(fechas.TZ).strftime("%Y-%m-%d %H:%M"),
            "servicio": ("Mesa " + o["mesa"]) if o["tipo"] == "mesa" else "Mostrador", "estado": ESTADOS.get(o["estado"], o["estado"]),
            "mesero": o["mesero"], "productos": "; ".join(f'{i["cantidad"]}x {i["producto"]}' for i in o.get("items", [])),
            "total": o["total"], "archivada": o["archivado_en"] is not None} for o in ordenes])
        st.dataframe(df_o)
        st.download_button("⬇️ Descargar órdenes (CSV)", reportes.a_csv(df_o), "ordenes.csv", "text/csv")
    else:
        st.info("Sin órdenes en este periodo.")
    st.subheader("Ventas rápidas")
    if ventas:
        df_v = pd.DataFrame(ventas)[["creado_en", "producto", "precio", "cantidad", "total", "vendedor", "archivado_en"]]
        df_v["creado_en"] = df_v["creado_en"].map(fmt_fecha)
        df_v["archivado_en"] = df_v["archivado_en"].map(fmt_fecha)
        st.dataframe(df_v)
        st.download_button("⬇️ Descargar ventas (CSV)", reportes.a_csv(df_v), "ventas.csv", "text/csv")
    else:
        st.info("Sin ventas rápidas en este periodo.")

    st.divider()
    st.caption("Archivar oculta lo terminado de la vista diaria. No borra nada: sigue en los reportes y en el respaldo.")
    confirmar = st.checkbox("Entiendo que se ocultarán las órdenes terminadas y las ventas actuales", key="conf_archivar")
    if st.button("🗂️ Archivar y reiniciar el día", disabled=not confirmar):
        ok, r = seguro(repo.archivar_historial)
        if ok:
            st.success(f'Archivadas {r["ordenes"]} órdenes y {r["ventas"]} ventas.')


# ======================================================================== MENÚ
def tab_menu(repo: Repo):
    productos = repo.productos(solo_activos=False)
    if productos:
        st.dataframe(pd.DataFrame(productos)[["nombre", "precio", "activo"]])
    with st.form("nuevo_producto", clear_on_submit=True):
        st.subheader("Nuevo producto")
        nombre = st.text_input("Nombre")
        precio = st.number_input("Precio (COP)", min_value=0, step=100)
        if st.form_submit_button("Guardar"):
            ok, _ = seguro(lambda: repo.crear_producto(nombre, precio), "Producto creado")
            if ok:
                st.rerun()
    if productos:
        st.subheader("Editar producto")
        etiquetas = {f'{p["nombre"]} · {cop(p["precio"])}' + ("" if p["activo"] else " (desactivado)"): p for p in productos}
        p = etiquetas[st.selectbox("Producto", list(etiquetas.keys()), key="menu_edit")]
        nuevo = st.number_input("Nuevo precio (COP)", min_value=0, step=100, value=int(p["precio"] or 0), key=f'precio_{p["id"]}')
        c1, c2 = st.columns(2)
        if c1.button("Guardar precio"):
            if seguro(lambda: repo.editar_producto(p["id"], precio=nuevo), "Precio actualizado")[0]:
                st.rerun()
        if c2.button("Desactivar" if p["activo"] else "Reactivar"):
            if seguro(lambda: repo.editar_producto(p["id"], activo=not p["activo"]), "Listo")[0]:
                st.rerun()
        st.caption("Los productos no se borran: se desactivan, y el historial conserva sus nombres y precios.")


# ====================================================================== EQUIPO
def tab_equipo(repo: Repo):
    emp = repo.empleados()
    if emp:
        st.dataframe(pd.DataFrame(emp)[["usuario", "rol", "activo"]])
    st.subheader("Agregar empleado")
    st.caption("1) Crea su usuario en Supabase → Authentication → Users → Add user, con su correo y una clave temporal "
               "(marca «Auto Confirm User»); una cuenta por persona, sin cuentas compartidas. Entrégale la clave temporal en persona. "
               "2) Vincúlalo aquí a tu restaurante. "
               "3) En su primer ingreso la app le pedirá crear su propia clave; la temporal deja de servir.")
    with st.form("vincular", clear_on_submit=True):
        email = st.text_input("Correo del empleado")
        usuario = st.text_input("Nombre a mostrar (ej. Ana)")
        rol = st.selectbox("Rol", ["mesero", "cocina"])
        if st.form_submit_button("Vincular"):
            ok, _ = seguro(lambda: repo.vincular_empleado(email, usuario, rol), "Empleado vinculado")
            if ok:
                st.rerun()
    otros = [e for e in emp if e["rol"] != "admin"]
    if otros:
        st.subheader("Activar o desactivar acceso")
        e = {f'{x["usuario"]} ({x["rol"]})' + ("" if x["activo"] else " — desactivado"): x for x in otros}
        x = e[st.selectbox("Empleado", list(e.keys()), key="emp_sel")]
        if st.button("Reactivar acceso" if not x["activo"] else "Quitar acceso"):
            if seguro(lambda: repo.set_empleado_activo(x["id"], not x["activo"]), "Listo")[0]:
                st.rerun()


# =================================================================== AUDITORÍA
def tab_auditoria(repo: Repo):
    filas = repo.auditoria()
    if not filas:
        st.info("Aún no hay acciones registradas.")
        return
    df = pd.DataFrame(filas)
    df["creado_en"] = pd.to_datetime(df["creado_en"], utc=True).dt.tz_convert(fechas.TZ).dt.strftime("%Y-%m-%d %H:%M")
    st.dataframe(df)
    st.download_button("⬇️ Descargar auditoría (CSV)", reportes.a_csv(df.astype({"detalle": str})), "auditoria.csv", "text/csv")


# ======================================================================== APP
def pantalla_app(repo: Repo):
    ok, activa = seguro(repo.cuenta_activa)
    if not ok:
        return
    if not activa:                       # el dueño desactivó esta cuenta durante la sesión
        repo.logout()
        st.session_state.clear()
        st.session_state["aviso"] = "Tu cuenta fue desactivada. Pide al dueño que la reactive."
        st.rerun()
    p = repo.perfil
    with st.sidebar:
        st.markdown(f'**{p["tienda_nombre"]}**')
        st.write(f'👤 {p["usuario"]} · {p["rol"]}')
        if st.button("Cerrar sesión"):
            repo.logout()
            st.session_state.clear()
            st.rerun()
    st.title(f'🍽️ {p["tienda_nombre"]}')

    if p["rol"] == "mesero":
        vista = st.radio("Sección", ["Nueva orden", "Mis órdenes"], horizontal=True, label_visibility="collapsed", key="vista_mesero")
        try:
            (tab_nueva_orden if vista == "Nueva orden" else mis_ordenes_auto)(repo)
        except ErrorApp as e:
            st.error(str(e))
        return

    pantallas = {
        "admin": [("Nueva orden", tab_nueva_orden), ("Órdenes", tab_ordenes), ("Cocina", tab_cocina), ("Resumen", tab_resumen),
                  ("Historial", tab_historial), ("Menú", tab_menu), ("Equipo", tab_equipo), ("Auditoría", tab_auditoria)],
        "cocina": [("Cocina", tab_cocina)],
    }.get(p["rol"], [])
    if not pantallas:
        st.error("Tu rol no tiene pantallas asignadas.")
        return
    for tab, (_, fn) in zip(st.tabs([n for n, _ in pantallas]), pantallas):
        with tab:
            try:
                fn(repo)
            except ErrorApp as e:
                st.error(str(e))


def main():
    try:
        url, key = leer_credenciales(st.secrets)
    except ConfigError as e:
        st.error(str(e))
        st.stop()
    repo = st.session_state.get("repo")
    if repo is None or repo.perfil is None:
        pantalla_login(url, key)
    elif repo.perfil.get("debe_cambiar_clave"):
        pantalla_cambiar_clave(repo)
    else:
        pantalla_app(repo)


main()
