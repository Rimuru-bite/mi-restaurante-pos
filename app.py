import streamlit as st
import pandas as pd
from st_supabase_connection import SupabaseConnection # type: ignore

st.set_page_config(page_title="SaaS Restaurante", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

if 'autenticado' not in st.session_state:
    st.session_state.update({'autenticado': False, 'usuario': None, 'rol': None, 'tienda_id': None})

# --- LOGIN ---
if not st.session_state['autenticado']:
    st.title("🔐 Acceso")
    with st.form("login"):
        u = st.text_input("Usuario")
        p = st.text_input("Clave", type="password")
        if st.form_submit_button("Entrar"):
            res = conn.table("usuarios").select("*").eq("usuario", u).eq("password", p).execute()
            if res.data:
                d = res.data[0]
                st.session_state.update({'autenticado': True, 'usuario': d['usuario'], 'rol': d['rol'], 'tienda_id': d['tienda_id']})
                st.rerun()
            else:
                st.error("Error de acceso")

# --- APP PRINCIPAL ---
else:
    t_id = st.session_state['tienda_id']
    st.title(f"🏢 {t_id}")

    # 1. LEER PRODUCTOS (Aquí estaba el fallo)
    try:
        res_p = conn.table("productos").select("nombre, precio").eq("tienda_id", t_id).execute()
        # Creamos el diccionario asegurando que los nombres sean los de tu imagen
        dict_productos = {item['nombre']: item['precio'] for item in res_p.data}
    except Exception as e:
        st.error(f"Error cargando menú: {e}")
        dict_productos = {}

    # --- BARRA LATERAL ---
    with st.sidebar:
        st.write(f"Usuario: {st.session_state['usuario']}")
        if st.button("Cerrar Sesión"):
            st.session_state.update({'autenticado': False})
            st.rerun()
        
        if st.session_state['rol'] == 'admin':
            st.divider()
            st.subheader("🛠️ Ajustar Menú")
            n_p = st.text_input("Nuevo Producto")
            p_p = st.number_input("Precio", min_value=0, step=100)
            if st.button("Guardar en Nube"):
                if n_p:
                    conn.table("productos").insert({"nombre": n_p, "precio": p_p, "tienda_id": t_id}).execute()
                    st.success("¡Guardado!")
                    st.rerun()

    # --- VENTAS Y TABLA ---
    if dict_productos:
        col1, col2 = st.columns(2)
        with col1:
            p_sel = st.selectbox("Producto", list(dict_productos.keys()))
            cant = st.number_input("Cantidad", min_value=1, value=1)
            if st.button("🚀 Vender"):
                total = dict_productos[p_sel] * cant
                conn.table("ventas").insert({
                    "producto": p_sel, "cantidad": cant, "total": total, 
                    "vendedor": st.session_state['usuario'], "tienda_id": t_id
                }).execute()
                st.rerun()
        
        # Mostrar Historial
        st.divider()
        res_v = conn.table("ventas").select("*").eq("tienda_id", t_id).execute()
        df = pd.DataFrame(res_v.data)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            st.metric("TOTAL HOY", f"${df['total'].sum():,} COP")
    else:
        st.warning("Agregue productos para empezar.")