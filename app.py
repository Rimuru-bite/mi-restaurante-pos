import streamlit as st
import pandas as pd
from st_supabase_connection import SupabaseConnection # type: ignore

st.set_page_config(page_title="POS Restaurante Cloud", layout="wide")
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
                d = res.data[0] # IMPORTANTE: Tomar el primer elemento
                st.session_state.update({'autenticado': True, 'usuario': d['usuario'], 'rol': d['rol'], 'tienda_id': d['tienda_id']})
                st.rerun()
            else:
                st.error("Error de acceso")

# --- APP PRINCIPAL ---
else:
    t_id = st.session_state['tienda_id']
    st.title(f"🏢 {t_id.replace('_', ' ')}")

    # 1. CARGAR MENÚ
    res_p = conn.table("productos").select("nombre, precio").eq("tienda_id", t_id).execute()
    dict_productos = {item['nombre']: item['precio'] for item in res_p.data}

    # --- BARRA LATERAL ---
    with st.sidebar:
        st.write(f"Sesión: {st.session_state['usuario']}")
        if st.button("Cerrar Sesión"):
            st.session_state.update({'autenticado': False})
            st.rerun()
        
        if st.session_state['rol'] == 'admin':
            st.divider()
            st.subheader("🛠️ Ajustar Menú")
            n_p = st.text_input("Nuevo Producto")
            p_p = st.number_input("Precio", min_value=0, step=100)
            if st.button("Guardar Producto"):
                if n_p:
                    conn.table("productos").insert({"nombre": n_p, "precio": p_p, "tienda_id": t_id}).execute()
                    st.rerun()

    # --- VENTAS ---
    if dict_productos:
        with st.container(border=True):
            st.subheader("📝 Nueva Venta")
            c1, c2 = st.columns(2)
            p_sel = c1.selectbox("Producto", list(dict_productos.keys()))
            cant = c2.number_input("Cantidad", min_value=1, value=1)
            
            if st.button("🚀 Registrar Venta", use_container_width=True):
                precio_unitario = dict_productos[p_sel]
                total_venta = precio_unitario * cant
                
                # AHORA SÍ GUARDAMOS EL PRECIO
                conn.table("ventas").insert({
                    "producto": p_sel, 
                    "precio": precio_unitario, # <--- Esto arregla el "None"
                    "cantidad": cant, 
                    "total": total_venta, 
                    "vendedor": st.session_state['usuario'], 
                    "tienda_id": t_id
                }).execute()
                st.rerun()
        
        # --- HISTORIAL Y BOTÓN DE BORRAR ---
        st.divider()
        res_v = conn.table("ventas").select("*").eq("tienda_id", t_id).execute()
        df = pd.DataFrame(res_v.data)
        
        col_h, col_b = st.columns([3, 1])
        with col_h:
            st.subheader("📊 Historial de hoy")
        with col_b:
            # BOTÓN DE BORRAR (Solo Dueño)
            if st.session_state['rol'] == 'admin' and not df.empty:
                if st.button("🗑️ Reiniciar Día", type="primary"):
                    conn.table("ventas").delete().eq("tienda_id", t_id).execute()
                    st.rerun()

        if not df.empty:
            # Reordenamos columnas para que se vea bonito
            columnas = ["producto", "precio", "cantidad", "total", "vendedor"]
            st.dataframe(df[columnas], use_container_width=True)
            st.metric("TOTAL HOY", f"${df['total'].sum():,} COP")
        else:
            st.info("No hay ventas registradas.")
    else:
        st.warning("El dueño debe agregar productos primero.")