begin;

-- Cada producto tiene su propio ID y pertenece a un restaurante.
-- El nombre solo debe ser único dentro de cada restaurante.
alter table public.productos alter column tienda_id set not null;
alter table public.productos add column if not exists id uuid not null default gen_random_uuid();
alter table public.productos drop constraint productos_pkey;
alter table public.productos add primary key (id);
alter table public.productos add constraint productos_tienda_nombre_uq unique (tienda_id, nombre);

commit;
