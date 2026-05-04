import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

# --- CONFIGURACIÓN DE SUPABASE ---
# Asegúrate de que no haya espacios ni puntos extra al final de estas comillas
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]# <--- PEGA AQUÍ LA SECRET KEY DE TU FOTO

# Conexión a la base de datos
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Sistema POS Pro - Supabase", layout="wide")

# --- MEMORIA DEL SISTEMA ---
if 'autenticado' not in st.session_state:
    st.session_state.update({'autenticado': False, 'rol': None, 'usuario': ""})

# Función para traer ventas de la nube
def cargar_datos_nube():
    try:
        response = supabase.table("ventas").select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        return pd.DataFrame(columns=["created_at", "producto", "precio", "cantidad", "total", "vendedor"])

# --- PANTALLA DE LOGIN (Igual que antes) ---
if not st.session_state['autenticado']:
    st.title("🔐 Acceso al Sistema")
    user = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")
    if st.button("Iniciar Sesión"):
        if user == "dueño" and password == "admin123":
            st.session_state.update({"autenticado": True, "rol": "admin", "usuario": user})
            st.rerun()
        elif user == "mesero" and password == "venta123":
            st.session_state.update({"autenticado": True, "rol": "empleado", "usuario": user})
            st.rerun()
        else:
            st.error("Credenciales incorrectas")
else:
    # --- SISTEMA PRINCIPAL ---
    df_ventas = cargar_datos_nube()
    
    with st.sidebar:
        st.header(f"Hola, {st.session_state['usuario'].capitalize()}")
        if st.session_state['rol'] == "admin":
            if st.button("🗑️ Borrar Historial (Nube)"):
                supabase.table("ventas").delete().neq("producto", "none").execute()
                st.rerun()
        if st.button("Cerrar Sesión"):
            st.session_state.update({"autenticado": False, "rol": None, "usuario": ""})
            st.rerun()

    st.title("🚀 Gestión en la Nube")
    
    with st.expander("➕ Registrar Nueva Venta", expanded=True):
        productos = {"Corrientazo": 15000, "Gaseosa": 3500, "Jugos": 5000, "Bandeja Paisa": 25000}
        c1, c2 = st.columns(2)
        with c1:
            prod = st.selectbox("Producto", list(productos.keys()))
        with c2:
            cant = st.number_input("Cantidad", min_value=1, value=1)
            
        if st.button("Confirmar Venta"):
            try:
                precio = productos[prod]
                total = precio * cant
                vendedor = st.session_state['usuario']
                
                # ENVIAR A SUPABASE
                datos_venta = {
                    "producto": prod,
                    "precio": precio,
                    "cantidad": cant,
                    "total": total,
                    "vendedor": vendedor
                }
                supabase.table("ventas").insert(datos_venta).execute()
                st.success(f"✅ Venta guardada en la nube!")
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar: {e}")

    st.divider()
    st.subheader("📊 Historial de Ventas Reales")
    if not df_ventas.empty:
        st.dataframe(df_ventas, use_container_width=True)
        st.metric("RECAUDO TOTAL", f"${df_ventas['total'].sum():,} COP")
    else:
        st.info("No hay ventas registradas en la base de datos.")
