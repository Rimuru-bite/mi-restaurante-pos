import streamlit as st
import pandas as pd
from st_supabase_connection import SupabaseConnection # type: ignore

st.set_page_config(page_title="POS Multi-Tienda", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

# --- INICIO DE SESIÓN ---
if 'autenticado' not in st.session_state:
    st.session_state.update({'autenticado': False, 'usuario': None, 'rol': None, 'tienda_id': None})

if not st.session_state['autenticado']:
    st.title("🔐 Acceso Multitienda")
    user_input = st.text_input("Usuario")
    pass_input = st.text_input("Contraseña", type="password")
    
    if st.button("Ingresar"):
        # Buscamos el usuario en la tabla 'usuarios' de Supabase
        res = conn.table("usuarios").select("*").eq("usuario", user_input).eq("password", pass_input).execute()
        
        if res.data:
            datos = res.data[0]
            st.session_state.update({
                'autenticado': True,
                'usuario': datos['usuario'],
                'rol': datos['rol'],
                'tienda_id': datos['tienda_id']
            })
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos")

# --- PANEL DE VENTAS ---
else:
    tienda = st.session_state['tienda_id']
    
    st.title(f"🚀 Tienda: {tienda} - Usuario: {st.session_state['usuario']}")
    
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.update({'autenticado': False})
        st.rerun()

    # REGISTRAR VENTA (Incluyendo el tienda_id)
    with st.expander("📝 Registrar Venta"):
        prod = st.selectbox("Producto", ["Corrientazo", "Gaseosa", "Bandeja Paisa"])
        cant = st.number_input("Cantidad", min_value=1, value=1)
        if st.button("Confirmar"):
            nueva_venta = {
                "producto": prod,
                "cantidad": cant,
                "total": 15000 * cant, # Ejemplo
                "vendedor": st.session_state['usuario'],
                "tienda_id": tienda  # <--- CRUCIAL: Se guarda con el ID de la tienda
            }
            conn.table("ventas").insert(nueva_venta).execute()
            st.success("Venta guardada")

    st.divider()

    # MOSTRAR VENTAS (Filtradas por tienda_id)
    st.subheader("📊 Historial de mi Tienda")
    
    # IMPORTANTE: Solo seleccionamos las filas donde tienda_id coincide
    res_ventas = conn.table("ventas").select("*").eq("tienda_id", tienda).execute()
    df = pd.DataFrame(res_ventas.data)

    if not df.empty:
        st.dataframe(df, use_container_width=True)
        
        # Ver ventas por vendedor (para que el dueño sepa quién generó qué)
        if st.session_state['rol'] == 'admin':
            st.write("### 💰 Ventas por Empleado")
            resumen = df.groupby("vendedor")["total"].sum()
            st.table(resumen)
            
            if st.button("🗑️ Reiniciar mi Tienda"):
                conn.table("ventas").delete().eq("tienda_id", tienda).execute()
                st.rerun()
    else:
        st.info("No hay ventas en esta tienda.")