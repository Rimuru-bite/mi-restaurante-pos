import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

# --- CONEXIÓN LIMPIA A SUPABASE ---
try:
    # Esto lee los Secrets que configuraste en la web de Streamlit
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("⚠️ Error de configuración: No se encontraron los Secrets (URL o KEY).")
    st.stop()

st.set_page_config(page_title="Sistema POS Pro", layout="wide")

# --- FUNCIONES DE DATOS ---
def cargar_datos_nube():
    try:
        # Trae las ventas de la tabla llamada 'ventas'
        res = supabase.table("ventas").select("*").execute()
        return pd.DataFrame(res.data)
    except:
        return pd.DataFrame(columns=["producto", "precio", "cantidad", "total", "vendedor"])

# --- LÓGICA DE LOGIN ---
if 'autenticado' not in st.session_state:
    st.session_state.update({'autenticado': False, 'rol': None, 'usuario': ""})

if not st.session_state['autenticado']:
    st.title("🔐 Acceso")
    u = st.text_input("Usuario")
    p = st.text_input("Contraseña", type="password")
    if st.button("Entrar"):
        if u == "dueño" and p == "admin123":
            st.session_state.update({"autenticado": True, "rol": "admin", "usuario": u})
            st.rerun()
        elif u == "mesero" and p == "venta123":
            st.session_state.update({"autenticado": True, "rol": "empleado", "usuario": u})
            st.rerun()
        else:
            st.error("Datos incorrectos")
else:
    # --- APP PRINCIPAL ---
    df = cargar_datos_nube()
    
    with st.sidebar:
        st.write(f"Usuario: {st.session_state['usuario']}")
        if st.button("Cerrar Sesión"):
            st.session_state.update({"autenticado": False, "rol": None})
            st.rerun()

    st.title("🚀 Registro de Ventas")
    
    with st.expander("Registrar Venta", expanded=True):
        productos = {"Corrientazo": 15000, "Gaseosa": 3500}
        prod = st.selectbox("Producto", list(productos.keys()))
        cant = st.number_input("Cantidad", min_value=1, value=1)
        
        if st.button("Confirmar"):
            # Datos para la nube
            nueva_v = {
                "producto": str(prod),
                "precio": int(productos[prod]),
                "cantidad": int(cant),
                "total": int(productos[prod] * cant),
                "vendedor": str(st.session_state['usuario'])
            }
            try:
                # AQUÍ es donde ocurre la magia
                supabase.table("ventas").insert(nueva_v).execute()
                st.success("¡Venta guardada!")
                st.rerun()
            except Exception as e:
                st.error("Error al conectar con la tabla. Revisa que se llame 'ventas' en Supabase.")
                st.write(e)

    st.subheader("Historial")
    st.dataframe(df, use_container_width=True)