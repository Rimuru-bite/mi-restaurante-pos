import streamlit as st
import pandas as pd
import bcrypt
from datetime import datetime, timedelta
from st_supabase_connection import SupabaseConnection # type: ignore

# CONFIGURACIÓN
st.set_page_config(page_title="Enterprise POS", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

# --- FUNCIÓN DE VERIFICACIÓN DE CLAVE ---
def verificar_password(password_plana, hash_almacenado):
    return bcrypt.checkpw(password_plana.encode('utf-8'), hash_almacenado.encode('utf-8'))

# --- LOGIN ---
if 'autenticado' not in st.session_state:
    st.session_state.update({'autenticado': False, 'usuario': None, 'rol': None, 'tienda_id': None})

if not st.session_state['autenticado']:
    st.title("🔐 Acceso Empresarial")
    u = st.text_input("Usuario")
    p = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        res = conn.table("usuarios").select("*").eq("usuario", u).execute()
        if res.data and verificar_password(p, res.data[0]['password']):
            d = res.data[0]
            st.session_state.update({'autenticado': True, 'usuario': u, 'rol': d['rol'], 'tienda_id': d['tienda_id']})
            st.rerun()
        else:
            st.error("Credenciales incorrectas o usuario no encontrado")

# --- PANEL DE CONTROL ---
else:
    rol = st.session_state['rol']
    t_id = st.session_state['tienda_id']

    # 1. MÓDULO MESERO (Toma de pedidos)
    if rol in ['admin', 'mesero']:
        with st.sidebar:
            st.header("🍽️ Mesero")
            # Cargar productos desde Supabase
            res_p = conn.table("productos").select("*").eq("tienda_id", t_id).execute()
            productos = {p['nombre']: p['precio'] for p in res_p.data}
            
            p_sel = st.selectbox("Producto", list(productos.keys()))
            cant = st.number_input("Cantidad", min_value=1)
            mesa = st.text_input("Mesa", value="1")
            if st.button("Enviar Pedido"):
                total = productos[p_sel] * cant
                conn.table("ventas").insert({
                    "producto": p_sel, "cantidad": cant, "total": total,
                    "vendedor": st.session_state['usuario'], "tienda_id": t_id,
                    "estado": "Pendiente", "mesa": mesa
                }).execute()
                st.toast("Pedido enviado a cocina! 🍟")

    # 2. MÓDULO COCINA (Solo ve lo pendiente)
    if rol in ['admin', 'cocina']:
        st.header("👨‍🍳 Monitor de Cocina")
        pedidos = conn.table("ventas").select("*").eq("tienda_id", t_id).eq("estado", "Pendiente").execute()
        if pedidos.data:
            cols = st.columns(3)
            for i, ped in enumerate(pedidos.data):
                with cols[i % 3]:
                    with st.container(border=True):
                        st.write(f"**Mesa {ped['mesa']}**")
                        st.write(f"{ped['producto']} x{ped['cantidad']}")
                        if st.button("Listo ✅", key=f"p_{ped['id']}"):
                            conn.table("ventas").update({"estado": "Entregado"}).eq("id", ped['id']).execute()
                            st.rerun()
        else:
            st.info("Sin pedidos pendientes")

    # 3. MÓDULO DUEÑO (Analítica de Valor)
    if rol == 'admin':
        st.divider()
        st.header("📈 Reportes Gerenciales")
        res_v = conn.table("ventas").select("*").eq("tienda_id", t_id).execute()
        df = pd.DataFrame(res_v.data)
        
        if not df.empty:
            df['creado_en'] = pd.to_datetime(df['creado_en'])
            hoy = datetime.now().date()
            
            # FILTROS DE TIEMPO
            tab1, tab2, tab3 = st.tabs(["Día", "Semana", "Mes"])
            
            with tab1:
                df_hoy = df[df['creado_en'].dt.date == hoy]
                st.metric("Venta de Hoy", f"${df_hoy['total'].sum():,} COP")
                st.dataframe(df_hoy)

            with tab2:
                hace_semana = hoy - timedelta(days=7)
                df_sem = df[df['creado_en'].dt.date >= hace_semana]
                st.line_chart(df_sem.groupby(df_sem['creado_en'].dt.date)['total'].sum())

            # ESTADÍSTICAS PRO
            st.subheader("🏆 TOP Desempeño")
            col_a, col_b = st.columns(2)
            col_a.write("**Producto más vendido:**")
            col_a.bar_chart(df.groupby('producto')['cantidad'].sum())
            
            col_b.write("**Ventas por Empleado:**")
            col_b.bar_chart(df.groupby('vendedor')['total'].sum())

    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.update({'autenticado': False})
        st.rerun()
