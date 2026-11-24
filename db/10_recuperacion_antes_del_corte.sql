-- Deshace los bloques 02 a 06 (solo ANTES del corte 08). La app anterior no se ve afectada.
-- No ejecutar si ya hay datos útiles en órdenes o columnas nuevas. El respaldo (bloque 01) NO se borra.
begin;

drop function if exists public.crear_orden(text,text,text,jsonb);
drop function if exists public.cambiar_estado_orden(uuid,text);
drop function if exists public.tablero_cocina();
drop function if exists public.archivar_historial();
drop function if exists public.vincular_empleado(text,text,text);
drop function if exists public.set_empleado_activo(uuid,boolean);

drop table if exists public.orden_items;
drop table if exists public.ordenes;
drop table if exists public.auditoria;
drop trigger if exists productos_auditar on public.productos;
drop trigger if exists ventas_auditar on public.ventas;
drop trigger if exists perfiles_auditar on public.perfiles;
drop function if exists private.trg_auditar();
drop function if exists private.registrar_auditoria(text,text,text,text,jsonb);

drop table if exists public.perfiles;

alter table public.ventas    drop constraint if exists ventas_total_coherente;
alter table public.ventas    drop constraint if exists ventas_tienda_fk;
alter table public.productos drop constraint if exists productos_tienda_fk;

alter table public.productos drop constraint if exists productos_tienda_nombre_uq;
alter table public.productos drop constraint productos_pkey;
alter table public.productos add primary key (nombre);
alter table public.productos drop column if exists id;
alter table public.productos alter column tienda_id drop not null;
alter table public.productos drop column if exists activo;

alter table public.ventas
  drop column if exists creado_en, drop column if exists vendedor_id,
  drop column if exists archivado_en, drop column if exists archivado_por;

drop table if exists public.restaurantes;
drop function if exists private.mi_tienda();
drop function if exists private.mi_rol();
comment on column public.usuarios.password is null;

commit;
