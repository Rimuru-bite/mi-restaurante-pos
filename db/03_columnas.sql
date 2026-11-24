begin;

alter table public.ventas
  add column if not exists creado_en     timestamptz not null default now(),
  add column if not exists vendedor_id   uuid references auth.users(id) on delete set null,
  add column if not exists archivado_en  timestamptz,
  add column if not exists archivado_por uuid references auth.users(id) on delete set null;

alter table public.productos
  add column if not exists activo boolean not null default true;

alter table public.ventas
  add constraint ventas_tienda_fk foreign key (tienda_id)
  references public.restaurantes(tienda_id) not valid;
alter table public.ventas validate constraint ventas_tienda_fk;

alter table public.productos
  add constraint productos_tienda_fk foreign key (tienda_id)
  references public.restaurantes(tienda_id) not valid;
alter table public.productos validate constraint productos_tienda_fk;

-- El total debe ser precio x cantidad (evita totales manipulados)
alter table public.ventas
  add constraint ventas_total_coherente check (total = precio * cantidad) not valid;
alter table public.ventas validate constraint ventas_total_coherente;

comment on column public.usuarios.password is
  'OBSOLETA: no usar para autenticar. Contiene claves en texto plano. Borrar solo tras verificar la migración a Supabase Auth.';

commit;
