begin;

create table public.restaurantes (
  tienda_id text primary key,
  nombre    text not null,
  activo    boolean not null default true,
  creado_en timestamptz not null default now()
);

insert into public.restaurantes (tienda_id, nombre)
select t, replace(t, '_', ' ')
from (
  select tienda_id as t from public.usuarios  where tienda_id is not null
  union select tienda_id from public.productos where tienda_id is not null
  union select tienda_id from public.ventas    where tienda_id is not null
) x
on conflict do nothing;

create table public.perfiles (
  id        uuid primary key references auth.users(id) on delete cascade,
  usuario   text not null,
  rol       text not null check (rol in ('admin','mesero','cocina')),
  tienda_id text not null references public.restaurantes(tienda_id),
  activo    boolean not null default true,
  creado_en timestamptz not null default now(),
  constraint perfiles_usuario_por_restaurante unique (tienda_id, usuario)
);
comment on column public.perfiles.rol is
  'admin = dueño/propietario del restaurante; mesero; cocina. Un rol nuevo solo se agrega cuando se necesite.';
alter table public.perfiles enable row level security;

create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated;

create or replace function private.mi_tienda() returns text
language sql stable security definer set search_path = ''
as $$ select tienda_id from public.perfiles where id = (select auth.uid()) and activo $$;

create or replace function private.mi_rol() returns text
language sql stable security definer set search_path = ''
as $$ select rol from public.perfiles where id = (select auth.uid()) and activo $$;

revoke all on function private.mi_tienda() from public, anon;
revoke all on function private.mi_rol()    from public, anon;
grant execute on function private.mi_tienda() to authenticated;
grant execute on function private.mi_rol()    to authenticated;

commit;
