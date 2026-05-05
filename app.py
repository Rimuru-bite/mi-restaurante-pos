import streamlit as st
import pandas as pd
from datetime import datetime
from st_supabase_connection import SupabaseConnection # type: ignore

# 1. Configuración de página
st.set_page_config(page_title="POS Restaurante Cloud", layout="wide")

# 2. Conexión a Supabase
# Asegúrate de haber puesto tus credenciales en los "Secrets" de Streamlit Cloud
conn = st.connection("supabase", type=SupabaseConnection)

# 3. Gestión de Sesión (Login)
if 'autenticado' not in st.session_state:
    st.session_state.update({'autenticado': False, 'rol': None, 'usuario': ""})

# --- PANTALLA DE ACCESO ---
if not st.session_state['autenticado']:
    st.title("🔐 Acceso al Sistema")
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
    # Encabezado y Salir
    col_t, col_b = st.columns([4, 1])
    with col_t:
        st.title(f"🚀 Panel - {st.session_state['usuario'].capitalize()}")
    with col_b:
        if st.button("Cerrar Sesión"):
            st.session_state.update({'autenticado': False})
            st.rerun()

    # --- REGISTRO DE VENTAS ---
    st.subheader("📝 Registrar Venta")
    productos = {"Corrientazo": 15000, "Gaseosa": 3500, "Jugos": 5000, "Bandeja Paisa": 25000}
    
    c1, c2, c3 = st.columns(3)
    with c1:
        prod = st.selectbox("Producto", list(productos.keys()))
    with c2:
        cant = st.number_input("Cantidad", min_value=1, value=1)
    with c3:
        st.write("") # Espacio visual
        st.write("") 
        if st.button("Confirmar Venta"):
            total_venta = productos[prod] * cant
            
            # GUARDAR EN SUPABASE
            nueva_venta = {
                "producto": prod,
                "precio": productos[prod],
                "cantidad": cant,
                "total": total_venta,
                "vendedor": st.session_state['usuario']
            }
            
            try:
                conn.table("ventas").insert(nueva_venta).execute()
                st.success(f"✅ Venta en la nube: ${total_venta:,}")
            except Exception as e:
                st.error(f"Error al conectar con Supabase: {e}")

    st.divider()

    # --- CONSULTAR VENTAS DE LA NUBE ---
    col_h, col_r = st.columns([3, 1])
    with col_h:
        st.subheader("📊 Ventas en Tiempo Real")
    
    with col_r:
        # Solo el dueño puede borrar (en Supabase esto borra todas las filas)
        if st.session_state['rol'] == "admin":
            if st.button("🗑️ REINICIAR TODO EL DÍA"):
                try:
                    # Borra todas las filas de la tabla ventas
                    conn.table("ventas").delete().neq("producto", "vacío").execute()
                    st.warning("Historial borrado de la nube")
                    st.rerun()
                except Exception as e:
                    st.error("No se pudo borrar: Revisa los permisos (RLS) en Supabase")

    # Mostrar los datos de la nube
    try:
        res = conn.table("ventas").select("*").execute()
        df_ventas = pd.DataFrame(res.data)
        
        if not df_ventas.empty:
            st.dataframe(df_ventas, use_container_width=True)
            st.metric("RECAUDO TOTAL CLOUD", f"${df_ventas['total'].sum():,} COP")
        else:
            st.info("Aún no hay ventas en la base de datos.")
    except:
        st.info("Conectando con la base de datos...")