import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

# --- 1. CONEXIÓN SEGURA ---
try:
    # Lee los datos desde los Secrets de Streamlit Cloud
    url = st.secrets["SUPABASE_URL"].strip().rstrip("/")
    key = st.secrets["SUPABASE_KEY"].strip()
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("⚠️ Error: No se encontraron las llaves en los Secrets de Streamlit.")
    st.stop()

st.set_page_config(page_title="POS Restaurante - Nube", layout="wide")

# --- 2. FUNCIONES DE BASE DE DATOS ---
def cargar_ventas():
    try:
        # Trae todo de la tabla 'ventas'
        res = supabase.table("ventas").select("*").execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        # Si falla, devuelve una tabla vacía con tus columnas reales
        return pd.DataFrame(columns=["created_at", "producto", "precio_venta", "cantidad_vendida", "total_recaudo", "atendido_por"])

# --- 3. LÓGICA DE ACCESO ---
if 'autenticado' not in st.session_state:
    st.session_state.update({'autenticado': False, 'rol': None, 'usuario': ""})

if not st.session_state['autenticado']:
    st.title("🔐 Acceso al Sistema")
    u = st.text_input("Usuario")
    p = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if u == "dueño" and p == "admin123":
            st.session_state.update({"autenticado": True, "rol": "admin", "usuario": u})
            st.rerun()
        elif u == "mesero" and p == "venta123":
            st.session_state.update({"autenticado": True, "rol": "empleado", "usuario": u})
            st.rerun()
        else:
            st.error("Usuario o clave incorrectos")
else:
    # --- 4. APLICACIÓN PRINCIPAL ---
    df_ventas = cargar_ventas()
    
    with st.sidebar:
        st.header(f"👤 {st.session_state['usuario'].capitalize()}")
        st.write(f"Rol: {st.session_state['rol']}")
        st.divider()
        if st.button("Cerrar Sesión"):
            st.session_state.update({"autenticado": False, "rol": None, "usuario": ""})
            st.rerun()

    st.title("🚀 Gestión de Ventas (Supabase)")

    # Formulario de Registro
    with st.expander("📝 Registrar Nueva Venta", expanded=True):
        menu = {"Corrientazo": 15000, "Gaseosa": 3500, "Jugos": 5000, "Bandeja Paisa": 25000}
        col1, col2 = st.columns(2)
        with col1:
            prod_nombre = st.selectbox("Producto", list(menu.keys()))
        with col2:
            cantidad = st.number_input("Cantidad", min_value=1, value=1)
        
        if st.button("Confirmar Venta"):
            try:
                precio = menu[prod_nombre]
                total = precio * cantidad
                
                # MAPEO EXACTO A TUS COLUMNAS DE SUPABASE
                datos_supabase = {
                    "producto": str(prod_nombre),
                    "precio_venta": int(precio),
                    "cantidad_vendida": int(cantidad),
                    "total_recaudo": int(total),
                    "atendido_por": str(st.session_state['usuario'])
                }
                
                # Insertar en la tabla 'ventas'
                supabase.table("ventas").insert(datos_supabase).execute()
                st.success(f"✅ Venta guardada: ${total:,} COP")
                st.rerun()
            except Exception as e:
                st.error("Error al guardar. Verifica la conexión.")
                st.write(e)

    # Mostrar Historial
    st.divider()
    st.subheader("📊 Historial en Tiempo Real")
    if not df_ventas.empty:
        # Mostramos la tabla formateada
        st.dataframe(df_ventas, use_container_width=True)
        
        # Resumen Financiero usando tus nombres de columna
        recaudo = df_ventas["total_recaudo"].sum()
        st.metric("TOTAL RECAUDADO (NUBE)", f"${recaudo:,} COP")
    else:
        st.info("No hay registros en la base de datos de Supabase.")