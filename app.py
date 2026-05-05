import streamlit as st
import pandas as pd
from st_supabase_connection import SupabaseConnection # type: ignore

# 1. CONFIGURACIÓN
st.set_page_config(page_title="SaaS Restaurante Pro", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

# Inicializar sesión
if 'autenticado' not in st.session_state:
    st.session_state.update({'autenticado': False, 'usuario': None, 'rol': None, 'tienda_id': None})

# --- BLOQUE DE LOGIN (Solo se muestra si no está autenticado) ---
if not st.session_state['autenticado']:
    st.title("🔐 Acceso al Sistema")
    # Usamos un formulario para evitar envíos dobles
    with st.form("login_form"):
        u = st.text_input("Nombre de Usuario")
        p = st.text_input("Contraseña", type="password")
        enviar = st.form_submit_button("Ingresar")
        
        if enviar:
            res = conn.table("usuarios").select("*").eq("usuario", u).eq("password", p).execute()
            if res.data:
                datos = res.data[0] # Tomamos el primer resultado
                st.session_state.update({
                    'autenticado': True, 
                    'usuario': datos['usuario'], 
                    'rol': datos['rol'], 
                    'tienda_id': datos['tienda_id']
                })
                st.rerun()
            else:
                st.error("Credenciales incorrectas")

# --- BLOQUE PRINCIPAL (Solo se muestra si ya entró) ---
else:
    t_id = st.session_state['tienda_id']
    st.title(f"🏢 Gestión: {t_id.replace('_', ' ')}")
    
    # Cargar productos
    res_prod = conn.table("productos").select("*").eq("tienda_id", t_id).execute()
    dict_productos = {p['nombre']: p['precio'] for p in res_prod.data}

    # BARRA LATERAL
    with st.sidebar:
        st.header(f"Hola, {st.session_state['usuario']}")
        if st.button("Cerrar Sesión"):
            st.session_state.update({'autenticado': False})
            st.rerun()
        
        if st.session_state['rol'] == 'admin':
            st.divider()
            st.subheader("🛠️ Menú")
            # Agregar producto
            with st.expander("➕ Añadir"):
                n_p = st.text_input("Nombre")
                p_p = st.number_input("Precio", min_value=0, step=500)
                if st.button("Guardar"):
                    conn.table("productos").insert({"nombre": n_p, "precio": p_p, "tienda_id": t_id}).execute()
                    st.rerun()
            
            # Editar/Borrar
            if dict_productos:
                st.write("*Editar:*")
                edit_p = st.selectbox("Seleccionar", list(dict_productos.keys()))
                new_p = st.number_input("Nuevo Precio", value=dict_productos[edit_p])
                if st.button("Actualizar"):
                    conn.table("productos").update({"precio": new_p}).eq("nombre", edit_p).eq("tienda_id", t_id).execute()
                    st.rerun()
                if st.button("🗑️ Borrar"):
                    conn.table("productos").delete().eq("nombre", edit_p).eq("tienda_id", t_id).execute()
                    st.rerun()

    # VENTAS
    if dict_productos:
        with st.container(border=True):
            st.subheader("📝 Nueva Venta")
            c1, c2 = st.columns(2)
            p_sel = c1.selectbox("Producto", list(dict_productos.keys()))
            cant = c2.number_input("Cantidad", min_value=1, value=1)
            if st.button("🚀 Registrar", use_container_width=True):
                total = dict_productos[p_sel] * cant
                conn.table("ventas").insert({"producto": p_sel, "cantidad": cant, "total": total, "vendedor": st.session_state['usuario'], "tienda_id": t_id}).execute()
                st.success("¡Venta exitosa!")
                st.rerun()

    # HISTORIAL
    st.divider()
    v_res = conn.table("ventas").select("*").eq("tienda_id", t_id).execute()
    df = pd.DataFrame(v_res.data)
    if not df.empty:
        st.subheader("📊 Historial")
        if st.session_state['rol'] == 'admin' and st.button("Limpiar día"):
            conn.table("ventas").delete().eq("tienda_id", t_id).execute()
            st.rerun()
        st.dataframe(df, use_container_width=True)
        st.metric("TOTAL", f"${df['total'].sum():,} COP")