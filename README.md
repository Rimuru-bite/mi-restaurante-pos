# POS Restaurante (MVP)

Aplicación web (Streamlit + Supabase) para restaurantes: dueño, meseros y cocina, con cuentas individuales.
La seguridad **vive en la base de datos** (RLS y funciones); la interfaz solo muestra lo que corresponde a cada rol.

## Qué hace
| Rol | Pantallas |
|---|---|
| **Dueño** (`admin`) | Nueva orden, Órdenes, Cocina, Resumen (hoy/semana/mes + CSV), Historial (archivar), Menú, Equipo, Auditoría |
| **Mesero** | Nueva orden (con observaciones por producto), Mis órdenes (estado, entregar, anular la propia si cocina no empezó), venta rápida |
| **Cocina** | Tablero que se actualiza solo cada 5 s: ve productos, cantidades y notas (**sin precios**); marca "en preparación" y "lista" |

Reglas clave: el precio de cada ítem sale siempre de la base; nada se borra (se **archiva** u oculta); cada acción importante queda en `auditoria`;
un restaurante nunca ve datos de otro; desactivar a un empleado le corta el acceso de inmediato.

## Poner en marcha
1. **Secretos** (Streamlit Cloud → Settings → Secrets, o `.streamlit/secrets.toml` local; ver `.streamlit/secrets.toml.example`):
   ```toml
   [supabase]
   url = "https://TU-PROYECTO.supabase.co"
   key = "CLAVE_ANON_O_PUBLISHABLE"
   ```
   Usa **solo** la clave anon/publishable. La app se niega a arrancar si detecta una `service_role`/`secret`. El formato anterior
   (`[connections.supabase] SUPABASE_URL / SUPABASE_KEY`) también se lee.
2. **Dependencias:** `pip install -r requirements.txt` · **Ejecutar:** `streamlit run app.py`
3. **Base de datos:** aplicar `db/` en orden (ver abajo).
4. **Authentication (panel de Supabase):** desactivar el registro público ("Allow new users to sign up"), subir el largo mínimo de clave,
   y crear al dueño (Authentication → Users → Add user, correo propio y clave **nueva**).

## Migración de la base (`db/`), en orden
| Archivo | Qué hace | ¿Rompe la app anterior? |
|---|---|---|
| `01_respaldo.sql` | Copia las tablas a un esquema `respaldo` cerrado a la API (sin la clave en texto plano) | No |
| `02_estructura.sql` | `restaurantes`, `perfiles` (usuario único **por restaurante**), funciones `private.mi_tienda/mi_rol` | No |
| `03_columnas.sql` | Fecha, vendedor y archivado en `ventas`; `activo` en `productos`; regla `total = precio × cantidad` | No |
| `04_productos_llave.sql` | `productos.id` único; nombre único solo dentro de cada restaurante | No |
| `05_ordenes_auditoria.sql` | `ordenes`, `orden_items` (comandas y estados) y `auditoria` | No |
| `06_funciones_app.sql` | Crear orden, cambiar estado, tablero de cocina, archivar, vincular/desactivar empleados | No |
| `07_vincular_dueno.sql` | Vincula al dueño (reemplaza el correo; antes créalo en Authentication) | No |
| `08_corte_seguridad.sql` | **CORTE:** privilegios mínimos + RLS. La app anterior deja de funcionar | **Sí** |
| `09_pruebas.sql` | Pruebas de seguridad (terminan en `ROLLBACK`) | No |
| `10`–`12` | Recuperación: antes del corte / emergencia tras el corte / restaurar desde respaldo | — |

Haz un respaldo (Table Editor → exportar CSV) antes de empezar. Ejecuta 01→07 mientras la app anterior sigue en pie, **despliega esta versión de la app**
y solo entonces ejecuta el `08` y luego el `09`. Cada archivo corre en una transacción: si falla, no deja nada a medias.

## Transición desde la versión anterior
- **Login:** antes usuario + clave en la tabla `usuarios`; ahora **correo + clave de Supabase Auth**. La tabla `usuarios` queda intacta pero sin acceso desde la API
  (sus claves en texto plano deben considerarse comprometidas: no las reutilices). Bórrala solo cuando todo esté verificado.
- **"Reiniciar Día"** ya no borra: **archiva** (Historial → "Archivar y reiniciar el día"). Lo archivado sigue en reportes y respaldo.
- **Venta rápida** se mantiene (expander en "Nueva orden") para el mostrador sin cocina. Las órdenes con cocina son el flujo nuevo.
- **Empleados:** el dueño crea al empleado en Supabase → Authentication, y lo vincula desde la pestaña **Equipo**. Sin cuentas compartidas.
- `st-supabase-connection` se retiró: compartía una conexión entre todos los usuarios. Ahora hay **un cliente por sesión**.
- El rol del dueño sigue llamándose `admin`.

## Pruebas
- `python -m pytest -q` — 23 pruebas: flujos con RLS real (cliente simulado sobre Postgres local), pantallas con un sustituto de Streamlit, y módulos puros.
  Requiere un Postgres local con las migraciones 01–08 aplicadas (variables `POS_PG_HOST/PORT/USER`, `POS_TEST_TEMPLATE`); si no hay, se omiten.
- `db/09_pruebas.sql` — suite de seguridad en SQL (aplicable a Supabase real).

## Límites conocidos
- Probado contra un Postgres local que **simula** Supabase y con un sustituto de Streamlit: falta una prueba en Supabase real y en Streamlit real.
- La cocina se actualiza por sondeo cada 5 s (sin tiempo real por websockets).
- Crear cuentas de empleados requiere el panel de Supabase (hacerlo desde la app exigiría una clave `service_role` en el servidor).
- Pendiente (fuera del MVP): domicilios, cierre de caja con métodos de pago, inventario, multi-restaurante completo.
