import streamlit as st
import pandas as pd
from st_supabase_connection import SupabaseConnection # type: ignore

st.set_page_config(page_title="SaaS Restaurante Pro", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

if 'autenticado' not in st.session_state:
    st.session_state.update({'autenticado': False, 'usuario': None, 'rol': None, 'tienda_id': None})

# --- LOGIN ---
if not st.session_state['autenticado']:
    st.title("🔐 Acceso")
    u = st.text_input("Usuario")
    p = st.text_input("Clave", type="password")
    if st.button("Entrar"):
        res = conn.table("usuarios").select("*").eq("usuario", u).eq("password", p).execute()
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
            st.error("Credenciales incorrectas")

# --- APLICACIÓN PRINCIPAL ---
else:
    t_id = st.session_state['tienda_id']
    st.title(f"🏢 Gestión: {t_id.replace('_', ' ')}")
    
    # Cargar productos de la tienda actual
    res_prod = conn.table("productos").select("*").eq("tienda_id", t_id).execute()
    dict_productos = {p['nombre']: p['precio'] for p in res_prod.data}

    # --- BARRA LATERAL (GESTIÓN Y PERFIL) ---
    with st.sidebar:
        st.header(f"Hola, {st.session_state['usuario'].capitalize()}")
        st.write(f"Rol: *{st.session_state['rol'].upper()}*")
        
        if st.button("Cerrar Sesión"):
            st.session_state.update({'autenticado': False})
            st.rerun()
        
        # --- GESTIÓN DE PRODUCTOS (SOLO DUEÑO) ---
        if st.session_state['rol'] == 'admin':
            st.divider()
            st.subheader("🛠️ Configurar Menú")
            
            # Opción 1: Agregar nuevo
            with st.expander("➕ Añadir Plato"):
                n_prod = st.text_input("Nombre del plato")
                p_prod = st.number_input("Precio", min_value=0, step=500)
                if st.button("Guardar Nuevo"):
                    conn.table("productos").insert({"nombre": n_prod, "precio": p_prod, "tienda_id": t_id}).execute()
                    st.success("Añadido")
                    st.rerun()

            # Opción 2: Editar o Eliminar
            if dict_productos:
                st.divider()
                st.write("*Editar / Eliminar:*")
                p_edit = st.selectbox("Selecciona producto", list(dict_productos.keys()))
                n_precio = st.number_input("Nuevo Precio", value=dict_productos[p_edit], step=500)
                
st.set_page_config(page_title="SaaS Restaurante Pro", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

if 'autenticado' not in st.session_state:
    st.session_state.update({'autenticado': False, 'usuario': None, 'rol': None, 'tienda_id': None})

# --- PANTALLA DE LOGIN ---
if not st.session_state['autenticado']:
    st.title("🔐 Acceso al Sistema")
    col_login, _ = st.columns([1, 2])
    with col_login:
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.button("Ingresar"):
            res = conn.table("usuarios").select("*").eq("usuario", u).eq("password", p).execute()
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
                st.error("Credenciales incorrectas")

# --- APLICACIÓN PRINCIPAL ---
else:
    t_id = st.session_state['tienda_id']
    st.title(f"🏢 Gestión: {t_id.replace('_', ' ')}")
    
    # Cargar productos de la tienda actual
    res_prod = conn.table("productos").select("*").eq("tienda_id", t_id).execute()
    dict_productos = {p['nombre']: p['precio'] for p in res_prod.data}

    # --- BARRA LATERAL (GESTIÓN Y PERFIL) ---
    with st.sidebar:
        st.header(f"Hola, {st.session_state['usuario'].capitalize()}")
        st.write(f"Rol: *{st.session_state['rol'].upper()}*")
        
        if st.button("Cerrar Sesión"):
            st.session_state.update({'autenticado': False})
            st.rerun()
        
        # --- GESTIÓN DE PRODUCTOS (SOLO DUEÑO) ---
        if st.session_state['rol'] == 'admin':
            st.divider()
            st.subheader("🛠️ Configurar Menú")
            
            # Opción 1: Agregar nuevo
            with st.expander("➕ Añadir Plato"):
                n_prod = st.text_input("Nombre del plato")
                p_prod = st.number_input("Precio", min_value=0, step=500)
                if st.button("Guardar Nuevo"):
                    conn.table("productos").insert({"nombre": n_prod, "precio": p_prod, "tienda_id": t_id}).execute()
                    st.success("Añadido")
                    st.rerun()

            # Opción 2: Editar o Eliminar
            if dict_productos:
                st.divider()
                st.write("*Editar / Eliminar:*")
                p_edit = st.selectbox("Selecciona producto", list(dict_productos.keys()))
                n_precio = st.number_input("Nuevo Precio", value=dict_productos[p_edit], step=500)
                
                c_ed1, c_ed2 = st.columns(2)
                with c_ed1:
                    if st.button("Actualizar"):
                        conn.table("productos").update({"precio": n_precio}).eq("nombre", p_edit).eq("tienda_id", t_id).execute()
                        st.success("Actualizado")
                        st.rerun()
                with c_ed2:
                    if st.button("🗑️ Borrar"):
                        conn.table("productos").delete().eq("nombre", p_edit).eq("tienda_id", t_id).execute()
                        st.warning("Eliminado")
                        st.rerun()

    # --- REGISTRO DE VENTAS (PANTALLA CENTRAL) ---
    if dict_productos:
        with st.container(border=True):
            st.subheader("📝 Nueva Venta")
            col1, col2 = st.columns(2)
            with col1:
                seleccionado = st.selectbox("Seleccione producto", list(dict_productos.keys()))
            with col2:
                cantidad = st.number_input("Cantidad", min_value=1, value=1)
            
            if st.button("🚀 Finalizar Venta", use_container_width=True):
                v_total = dict_productos[seleccionado] * cantidad
                datos_v = {
                    "producto": seleccionado, "cantidad": cantidad, "total": v_total,
                    "vendedor": st.session_state['usuario'], "tienda_id": t_id
                }
                conn.table("ventas").insert(datos_v).execute()
                st.balloons()
                st.success(f"Venta registrada: ${v_total:,} COP")
    else:
        st.info("Aún no tienes productos en el menú. Usa la barra lateral para agregar el primero.")

    # --- TABLA DE VENTAS Y RESULTADOS ---
    st.divider()
    res_v = conn.table("ventas").select("*").eq("tienda_id", t_id).execute()
    df = pd.DataFrame(res_v.data)

    if not df.empty:
        col_h, col_b = st.columns([3, 1])
        with col_h:
            st.subheader("📊 Historial de hoy")
        with col_b:
            if st.session_state['rol'] == 'admin':
                if st.button("⚠️ Reiniciar Todo"):
                    conn.table("ventas").delete().eq("tienda_id", t_id).execute()
                    st.rerun()

        st.dataframe(df, use_container_width=True)
        
        # Totales
        c_t1, c_t2 = st.columns(2)
        with c_t1:
            st.metric("RECAUDO TOTAL", f"${df['total'].sum():,} COP")
        with c_t2:
            if st.session_state['rol'] == 'admin':
                st.write("*Ventas por Vendedor:*")
                st.table(df.groupby("vendedor")["total"].sum())
    else:
        st.info("No hay registros de ventas para esta tienda.")