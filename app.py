import streamlit as st
import pandas as pd
from st_supabase_connection import SupabaseConnection  # type: ignore
import bcrypt # type: ignore
from datetime import datetime, timedelta
import re

st.set_page_config(page_title="POS Restaurante Cloud", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

# ============================================================================
# INICIALIZACIÓN DE SESSION STATE
# ============================================================================
if 'autenticado' not in st.session_state:
    st.session_state.update({
        'autenticado': False,
        'usuario': None,
        'rol': None,
        'tienda_id': None,
        'intento_fallido': 0
    })

# ============================================================================
# FUNCIONES AUXILIARES (VALIDACIÓN Y SEGURIDAD)
# ============================================================================

def validar_usuario(usuario: str) -> bool:
    """Valida formato de usuario"""
    if not usuario or len(usuario) < 3 or len(usuario) > 50:
        return False
    # Solo alfanuméricos y guiones bajos
    return bool(re.match(r'^[a-zA-Z0-9_]{3,50}$', usuario))

def validar_contrasena(contrasena: str) -> bool:
    """Valida que la contraseña sea segura"""
    if not contrasena or len(contrasena) < 6:
        return False
    return True

def validar_nombre_producto(nombre: str) -> bool:
    """Valida nombre de producto"""
    if not nombre or len(nombre) < 2 or len(nombre) > 100:
        return False
    return True

def validar_precio(precio: float) -> bool:
    """Valida que el precio sea válido"""
    return isinstance(precio, (int, float)) and 100 <= precio <= 5000000

def hash_password(password: str) -> str:
    """Hashea una contraseña con bcrypt"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verificar_password(password: str, hash_guardado: str) -> bool:
    """Verifica una contraseña contra su hash"""
    try:
        return bcrypt.checkpw(password.encode(), hash_guardado.encode())
    except Exception:
        return False

def ejecutar_query(funcion_query, descripcion: str = "operación"):
    """Ejecuta una query con manejo de errores"""
    try:
        resultado = funcion_query()
        return True, resultado
    except Exception as e:
        st.error(f"❌ Error en {descripcion}: {str(e)}")
        return False, None

# ============================================================================
# LOGIN
# ============================================================================
if not st.session_state['autenticado']:
    st.title("🔐 Acceso al Sistema POS")
    
    with st.form("login_form", clear_on_submit=True):
        usuario = st.text_input(
            "Usuario",
            max_chars=50,
            help="Alfanuméricos y guiones bajos (3-50 caracteres)"
        )
        contrasena = st.text_input("Contraseña", type="password")
        
        col1, col2 = st.columns(2)
        submit = col1.form_submit_button("🔓 Entrar", use_container_width=True)
        
        if submit:
            # Validar entrada
            if not validar_usuario(usuario):
                st.error("⚠️ Usuario inválido (3-50 caracteres, solo letras, números y _)")
            elif not validar_contrasena(contrasena):
                st.error("⚠️ Contraseña debe tener al menos 6 caracteres")
            else:
                # Buscar usuario
                exito, res = ejecutar_query(
                    lambda: conn.table("usuarios").select("*").eq("usuario", usuario).execute(),
                    "búsqueda de usuario"
                )
                
                if exito and res.data:
                    usuario_data = res.data[0]
                    
                    # Verificar contraseña
                    if verificar_password(contrasena, usuario_data.get('password_hash', '')):
                        # LOGIN EXITOSO
                        st.session_state.update({
                            'autenticado': True,
                            'usuario': usuario_data['usuario'],
                            'rol': usuario_data['rol'],
                            'tienda_id': usuario_data['tienda_id'],
                            'intento_fallido': 0
                        })
                        st.success("✅ Bienvenido!")
                        st.rerun()
                    else:
                        # LOGIN FALLIDO
                        st.session_state['intento_fallido'] += 1
                        st.error(f"❌ Credenciales incorrectas ({st.session_state['intento_fallido']}/3)")
                        
                        # Bloquear después de 3 intentos
                        if st.session_state['intento_fallido'] >= 3:
                            st.warning("⚠️ Demasiados intentos. Intenta en 5 minutos.")
                            st.stop()
                else:
                    st.session_state['intento_fallido'] += 1
                    st.error(f"❌ Usuario no encontrado ({st.session_state['intento_fallido']}/3)")
                    
                    if st.session_state['intento_fallido'] >= 3:
                        st.warning("⚠️ Demasiados intentos. Intenta en 5 minutos.")
                        st.stop()

# ============================================================================
# APP PRINCIPAL (SOLO SI ESTÁ AUTENTICADO)
# ============================================================================
else:
    t_id = st.session_state['tienda_id']
    st.title(f"🏢 {t_id.replace('_', ' ').title()}")
    
    # --- CARGAR MENÚ CON MANEJO DE ERRORES ---
    exito, res_p = ejecutar_query(
        lambda: conn.table("productos")
            .select("nombre, precio")
            .eq("tienda_id", t_id)
            .execute(),
        "carga de productos"
    )
    
    dict_productos = {item['nombre']: item['precio'] for item in res_p.data} if exito and res_p.data else {}
    
    # =========================================================================
    # BARRA LATERAL
    # =========================================================================
    with st.sidebar:
        st.write(f"👤 Sesión: **{st.session_state['usuario']}**")
        st.caption(f"Rol: {st.session_state['rol']}")
        
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.update({'autenticado': False})
            st.rerun()
        
        # --- ADMINISTRACIÓN (SOLO ADMIN) ---
        if st.session_state['rol'] == 'admin':
            st.divider()
            st.subheader("🛠️ Ajustar Menú")
            
            nombre_producto = st.text_input(
                "Nuevo Producto",
                max_chars=100,
                help="Nombre del producto (2-100 caracteres)"
            )
            precio_producto = st.number_input(
                "Precio (COP)",
                min_value=100,
                max_value=5000000,
                step=100,
                help="Entre $100 y $5.000.000"
            )
            
            if st.button("💾 Guardar Producto", use_container_width=True):
                # Validar entrada
                if not validar_nombre_producto(nombre_producto):
                    st.error("⚠️ Nombre inválido (2-100 caracteres)")
                elif not validar_precio(precio_producto):
                    st.error("⚠️ Precio fuera de rango ($100 - $5.000.000)")
                else:
                    # Verificar si ya existe
                    exito_check, res_check = ejecutar_query(
                        lambda: conn.table("productos")
                            .select("*")
                            .eq("nombre", nombre_producto)
                            .eq("tienda_id", t_id)
                            .execute(),
                        "verificación de duplicado"
                    )
                    
                    if exito_check and res_check.data:
                        st.error("⚠️ Este producto ya existe")
                    else:
                        # Guardar producto
                        exito_insert, _ = ejecutar_query(
                            lambda: conn.table("productos").insert({
                                "nombre": nombre_producto,
                                "precio": precio_producto,
                                "tienda_id": t_id,
                                "creado_en": datetime.now().isoformat()
                            }).execute(),
                            "inserción de producto"
                        )
                        
                        if exito_insert:
                            st.success(f"✅ Producto '{nombre_producto}' guardado")
                            st.rerun()
    
    # =========================================================================
    # SECCIÓN DE VENTAS
    # =========================================================================
    if dict_productos:
        with st.container(border=True):
            st.subheader("📝 Nueva Venta")
            c1, c2 = st.columns(2)
            
            p_sel = c1.selectbox("Producto", list(dict_productos.keys()))
            cant = c2.number_input("Cantidad", min_value=1, max_value=999, value=1)
            
            if st.button("🚀 Registrar Venta", use_container_width=True, type="primary"):
                precio_unitario = dict_productos[p_sel]
                total_venta = precio_unitario * cant
                
                # Guardar venta con manejo de errores
                exito_venta, _ = ejecutar_query(
                    lambda: conn.table("ventas").insert({
                        "producto": p_sel,
                        "precio": precio_unitario,
                        "cantidad": cant,
                        "total": total_venta,
                        "vendedor": st.session_state['usuario'],
                        "tienda_id": t_id,
                        "fecha": datetime.now().isoformat()
                    }).execute(),
                    "registro de venta"
                )
                
                if exito_venta:
                    st.success(f"✅ Venta de ${total_venta:,} COP registrada")
                    st.rerun()
        
        # =====================================================================
        # HISTORIAL DE VENTAS (FILTRADO POR HOY)
        # =====================================================================
        st.divider()
        
        # Cargar ventas
        exito_hist, res_v = ejecutar_query(
            lambda: conn.table("ventas")
                .select("*")
                .eq("tienda_id", t_id)
                .execute(),
            "carga de historial"
        )
        
        if exito_hist and res_v.data:
            df = pd.DataFrame(res_v.data)
            
            # FILTRAR POR HOY
            if 'fecha' in df.columns:
                try:
                    df['fecha'] = pd.to_datetime(df['fecha'])
                    hoy = pd.Timestamp.now().normalize()
                    df_hoy = df[df['fecha'].dt.normalize() == hoy]
                except Exception as e:
                    st.warning(f"⚠️ Error al procesar fechas: {e}")
                    df_hoy = df
            else:
                df_hoy = df
            
            # Encabezado con opciones
            col_h, col_b = st.columns([3, 1])
            with col_h:
                st.subheader(f"📊 Historial de hoy ({len(df_hoy)} ventas)")
            with col_b:
                # BOTÓN DE REINICIAR (Solo ADMIN)
                if st.session_state['rol'] == 'admin' and not df_hoy.empty:
                    if st.button("🗑️ Reiniciar", type="primary", key="btn_reiniciar"):
                        st.session_state['confirmar_reinicio'] = True
            
            # CONFIRMACIÓN DE REINICIO
            if st.session_state.get('confirmar_reinicio', False):
                st.warning("⚠️ ¿Estás seguro? Esta acción borrará todas las ventas de hoy y NO se puede deshacer.")
                col_si, col_no = st.columns(2)
                
                with col_si:
                    if st.button("✅ Sí, reiniciar el día", type="primary"):
                        exito_delete, _ = ejecutar_query(
                            lambda: conn.table("ventas")
                                .delete()
                                .eq("tienda_id", t_id)
                                .execute(),
                            "eliminación de ventas"
                        )
                        
                        if exito_delete:
                            st.success("✅ Historial reiniciado")
                            st.session_state['confirmar_reinicio'] = False
                            st.rerun()
                
                with col_no:
                    if st.button("❌ Cancelar"):
                        st.session_state['confirmar_reinicio'] = False
                        st.rerun()
            
            # MOSTRAR HISTORIAL
            if not df_hoy.empty:
                columnas = ["producto", "precio", "cantidad", "total", "vendedor"]
                # Filtrar solo columnas que existan
                columnas = [col for col in columnas if col in df_hoy.columns]
                
                st.dataframe(df_hoy[columnas], use_container_width=True, hide_index=True)
                
                # TOTALES
                total_hoy = df_hoy['total'].sum() if 'total' in df_hoy.columns else 0
                cantidad_hoy = df_hoy['cantidad'].sum() if 'cantidad' in df_hoy.columns else 0
                
                col_t1, col_t2 = st.columns(2)
                col_t1.metric("💰 TOTAL HOY", f"${total_hoy:,.0f} COP")
                col_t2.metric("📦 UNIDADES", f"{cantidad_hoy:.0f}")
            else:
                st.info("ℹ️ No hay ventas registradas hoy")
        else:
            st.info("ℹ️ No hay historial disponible")
    
    else:
        st.warning("⚠️ El dueño debe agregar productos al menú primero")