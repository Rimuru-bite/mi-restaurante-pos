import streamlit as st
import pandas as pd
from datetime import datetime

# 1. Configuración de página
st.set_page_config(page_title="POS Restaurante Pro", layout="wide")

# 2. Gestión de Sesión (Login)
if 'autenticado' not in st.session_state:
    st.session_state.update({'autenticado': False, 'rol': None, 'usuario': ""})

def cargar_datos():
    try:
        return pd.read_csv("ventas.csv")
    except:
        return pd.DataFrame(columns=["Fecha", "Producto", "Precio", "Cantidad", "Total", "Vendedor"])

# --- PANTALLA DE ACCESO ---
if not st.session_state['autenticado']:
    st.title("🔐 Acceso al Sistema")
    col_login, _ = st.columns([1, 2])
    with col_login:
        user = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        if st.button("Ingresar"):
            if user == "dueño" and password == "admin123":
                st.session_state.update({"autenticado": True, "rol": "admin", "usuario": user})
                st.rerun()
            elif user == "mesero" and password == "venta123":
                st.session_state.update({"autenticado": True, "rol": "mesero", "usuario": user})
                st.rerun()
            else:
                st.error("Credenciales incorrectas")

# --- PANTALLA PRINCIPAL ---
else:
    df_ventas = cargar_datos()
    
    # Encabezado y Salir
    col_t, col_b = st.columns([4, 1])
    with col_t:
        st.title(f"🚀 Panel de Control - {st.session_state['usuario'].capitalize()}")
    with col_b:
        if st.button("Cerrar Sesión"):
            st.session_state.update({'autenticado': False})
            st.rerun()

    # --- REGISTRO DE VENTAS ---
    st.subheader("📝 Registrar Venta")
    productos = {"Corrientazo": 15000, "Gaseosa": 3500, "Jugos": 5000, "Bandeja Paisa": 25000}
    
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        prod = st.selectbox("Producto", list(productos.keys()))
    with c2:
        cant = st.number_input("Cantidad", min_value=1, value=1)
    with c3:
        st.write("") # Espacio
        st.write("") 
        if st.button("Confirmar Venta"):
            total = productos[prod] * cant
            nueva = pd.DataFrame([[datetime.now().strftime("%H:%M:%S"), prod, productos[prod], cant, total, st.session_state['usuario']]], 
                                columns=df_ventas.columns)
            df_ventas = pd.concat([df_ventas, nueva], ignore_index=True)
            df_ventas.to_csv("ventas.csv", index=False)
            st.success(f"Venta Guardada: ${total:,}")
            st.rerun()

    st.divider()

    # --- HISTORIAL Y BOTÓN DE BORRAR (Solo Dueño) ---
    col_h, col_r = st.columns([3, 1])
    with col_h:
        st.subheader("📊 Ventas del Día")
    
    with col_r:
        # AQUÍ ESTÁ LA LIBERTAD TOTAL PARA EL DUEÑO
        if st.session_state['rol'] == "admin":
            if st.button("🗑️ REINICIAR TODO EL DÍA"):
                df_ventas = pd.DataFrame(columns=df_ventas.columns)
                df_ventas.to_csv("ventas.csv", index=False)
                st.warning("Historial borrado")
                st.rerun()

    if not df_ventas.empty:
        st.dataframe(df_ventas, use_container_width=True)
        st.metric("RECAUDO TOTAL", f"${df_ventas['Total'].sum():,} COP")
    else:
        st.info("No hay ventas registradas aún.")