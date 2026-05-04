import streamlit as st
import pandas as pd
from datetime import datetime

# Configuración visual
st.set_page_config(page_title="Sistema POS Pro", layout="wide")

# --- MEMORIA DEL SISTEMA ---
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False
if 'rol' not in st.session_state:
    st.session_state['rol'] = None
if 'usuario' not in st.session_state:
    st.session_state['usuario'] = ""

def cargar_datos():
    try:
        return pd.read_csv("ventas.csv")
    except:
        return pd.DataFrame(columns=["Fecha", "Producto", "Precio", "Cantidad", "Total", "Atendido por"])

# --- PANTALLA DE LOGIN ---
if not st.session_state['autenticado']:
    st.title("🔐 Acceso al Sistema")
    user = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")
    
    if st.button("Iniciar Sesión"):
        # Definición de usuarios y roles
        if user == "dueño" and password == "admin123":
            st.session_state.update({"autenticado": True, "rol": "admin", "usuario": user})
            st.rerun()
        elif user == "mesero" and password == "venta123":
            st.session_state.update({"autenticado": True, "rol": "empleado", "usuario": user})
            st.rerun()
        else:
            st.error("Credenciales incorrectas")

# --- SISTEMA PRINCIPAL ---
else:
    df_ventas = cargar_datos()
    
    # Barra lateral (Sidebar)
    with st.sidebar:
        st.header(f"Bienvenido, {st.session_state['usuario'].capitalize()}")
        st.write(f"Rol: *{st.session_state['rol'].upper()}*")
        st.divider()
        
        # EL PODER DEL DUEÑO: Borrar historial
        if st.session_state['rol'] == "admin":
            st.subheader("⚙️ Configuración")
            if st.button("🗑️ Borrar Todo el Historial"):
                df_ventas = pd.DataFrame(columns=df_ventas.columns)
                df_ventas.to_csv("ventas.csv", index=False)
                st.warning("Historial borrado por el Administrador")
                st.rerun()
        
        if st.button("Cerrar Sesión"):
            st.session_state.update({"autenticado": False, "rol": None, "usuario": ""})
            st.rerun()

    # Interfaz de Ventas
    st.title("🚀 Gestión de Restaurante")
    
    # Sección de Registro
    with st.expander("➕ Registrar Nueva Venta", expanded=True):
        productos = {"Corrientazo": 15000, "Gaseosa": 3500, "Jugos": 5000, "Bandeja Paisa": 25000}
        c1, c2 = st.columns(2)
        with c1:
            prod = st.selectbox("Producto", list(productos.keys()))
        with c2:
            cant = st.number_input("Cantidad", min_value=1, value=1)
            
        if st.button("Confirmar Venta"):
            precio = productos[prod]
            total = precio * cant
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
            atendido = st.session_state['usuario']
            
            nueva = pd.DataFrame([[fecha, prod, precio, cant, total, atendido]], columns=df_ventas.columns)
            df_ventas = pd.concat([df_ventas, nueva], ignore_index=True)
            df_ventas.to_csv("ventas.csv", index=False)
            st.success(f"Venta guardada por {atendido}: ${total:,} COP")

    # Sección de Visualización
    st.divider()
    st.subheader("📊 Historial de Ventas")
    
    if not df_ventas.empty:
        st.dataframe(df_ventas, use_container_width=True)
        
        # Resumen financiero
        c1, c2 = st.columns(2)
        with c1:
            st.metric("RECAUDO TOTAL", f"${df_ventas['Total'].sum():,} COP")
        with c2:
            st.metric("TOTAL PEDIDOS", len(df_ventas))
    else:
        st.info("No hay ventas en la base de datos.")