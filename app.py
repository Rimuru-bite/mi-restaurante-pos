import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

# --- CONFIGURACIÓN DE CONEXIÓN SEGURA ---
# Lee las llaves desde la sección 'Secrets' de Streamlit Cloud
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("Error de configuración: Revisa los Secrets en Streamlit Cloud.")
    st.stop()

st.set_page_config(page_title="Sistema POS Profesional", layout="wide")

# --- MEMORIA DEL SISTEMA ---
if 'autenticado' not in st.session_state:
    st.session_state.update({'autenticado': False, 'rol': None, 'usuario': ""})

# --- FUNCIONES DE BASE DE DATOS ---
def cargar_ventas():
    try:
        respuesta = supabase.table("ventas").select("*").execute()
        return pd.DataFrame(respuesta.data)
    except:
        return pd.DataFrame()

# --- PANTALLA DE LOGIN ---
if not st.session_state['autenticado']:
    st.title("🔐 Acceso al Sistema de Ventas")
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
    # --- INTERFAZ PRINCIPAL ---
    st.sidebar.header(f"Bienvenido, {st.session_state['usuario'].capitalize()}")
    st.sidebar.write(f"Rol: *{st.session_state['rol'].upper()}*")
    
    # Botón de borrar historial (Solo Dueño)
    if st.session_state['rol'] == "admin":
        if st.sidebar.button("🗑️ Borrar todo en la Nube"):
            # Este comando borra las filas de la tabla ventas en Supabase
            supabase.table("ventas").delete().neq("id", 0).execute()
            st.sidebar.success("Historial borrado")
            st.rerun()
            
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.update({'autenticado': False, 'rol': None, 'usuario': ""})
        st.rerun()

    st.title("🚀 Gestión de Restaurante (Cloud)")
    
    # Registrar Venta
    with st.expander("➕ Registrar Nueva Venta", expanded=True):
        productos = {"Corrientazo": 15000, "Gaseosa": 3500, "Jugos": 5000, "Bandeja Paisa": 25000}
        c1, c2 = st.columns(2)
        with c1:
            prod = st.selectbox("Producto", list(productos.keys()))
        with c2:
            cant = st.number_input("Cantidad", min_value=1, value=1)
            
        if st.button("Confirmar Venta"):
            try:
                datos = {
                    "producto": prod,
                    "precio": productos[prod],
                    "cantidad": cant,
                    "total": productos[prod] * cant,
                    "atendido_por": st.session_state['usuario']
                }
                supabase.table("ventas").insert(datos).execute()
                st.success(f"✅ Venta guardada en Supabase por {st.session_state['usuario']}")
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar: {e}")

    # Mostrar Historial
    st.divider()
    st.subheader("📊 Historial de Ventas")
    df = cargar_ventas()
    
    if not df.empty:
        # Reordenamos columnas para que se vea mejor
        columnas_orden = ["created_at", "producto", "precio", "cantidad", "total", "atendido_por"]
        # Filtrar solo las que existan para evitar errores si los nombres cambian
        cols_finales = [c for c in columnas_orden if c in df.columns]
        st.dataframe(df[cols_finales], use_container_width=True)
        
        c1, c2 = st.columns(2)
        with c1:
            st.metric("RECAUDO TOTAL", f"${df['total'].sum():,} COP")
        with c2:
            st.metric("NÚMERO DE VENTAS", len(df))
    else:
        st.info("Aún no hay ventas registradas en la base de datos.")