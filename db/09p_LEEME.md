# 09p · pruebas para producción (Supabase SQL Editor)

**Cuándo:** después del corte 08. **Cómo:** pegar `09p_pruebas_produccion.sql` completo y ejecutar. Si se corta: ejecutar `09p_limpieza.sql`.
**Resultado esperado:** `pruebas_fallidas = 0`, `detalle_fallos = []` y todas las `sobras_* = 0`.

## Garantías de seguridad
- Sin DDL, sin funciones/tablas auxiliares, sin comandos de psql, sin tocar Auth (no crea ni modifica `auth.users`).
- Todo dato de prueba lleva el prefijo reservado `ZZ_09P_<id aleatorio>` (único por corrida). Nada real lo usa.
- Limpieza explícita por prefijo (fase 3, o `09p_limpieza.sql`) y verificación: si queda algo, lanza error.
- Una corrida nueva se niega a empezar si hay restos de otra (`ejecuta 09p_limpieza.sql`).
- Cada prueba atrapa su error: una falla no detiene el script ni evita la limpieza.

## Qué verifica (68 comprobaciones, simulando cada rol con `request.jwt.claims`)
Anónimo sin acceso · usuario sin perfil/inactivo sin acceso · mesero: crea orden con precio tomado de la base (ignora el que envíe el cliente), rechaza producto inactivo/de otro restaurante/cantidad 0/lista vacía/tipo inválido/mesa sin número, no escribe directo en órdenes/productos/perfiles ni se sube de rol, no ve auditoría ni tablero · aislamiento entre restaurantes y entre meseros · cocina: tablero sin precios, transiciones válidas en orden, no crea órdenes ni anula · mesero entrega/anula solo la suya · admin: edita precios, nombre único por restaurante (nombre repetido permitido en otro), no borra, no vincula roles inválidos, no se desactiva ni toca otro restaurante · desactivar empleado corta el acceso al instante · archivar: solo admin, solo su restaurante, solo órdenes terminadas.

## Qué NO verifica
- **Auditoría (triggers):** los perfiles falsos exigen `session_replication_role = replica`, que desactiva triggers y FKs en esa transacción. Verificada localmente (`09_pruebas.sql`, pytest).
- **Venta rápida (`ventas`) y su trigger `ventas_fijar_vendedor`**, y **éxito de `vincular_empleado`**: requieren un usuario real en `auth.users`; no se crean. Cubiertos en local.
- **Login real / JWT real / expiración de sesión:** se simula el rol por SQL; el login se valida a mano en la app desplegada.
- **Foreign keys a `auth.users`:** no se comprueban (modo replica).
- Rendimiento y carga.

## Efectos que no se revierten
- Contadores de identidad (`auditoria.id`, ids de `ventas`) pueden avanzar; no se pierden ni cambian filas reales.
- Estadísticas/autovacuum y filas muertas en las tablas tocadas (inserciones y borrados de prueba).
- Aparece en los logs de Supabase la actividad de la corrida.
- `session_replication_role` se fija solo con `SET LOCAL` (vuelve a normal al terminar cada transacción).
