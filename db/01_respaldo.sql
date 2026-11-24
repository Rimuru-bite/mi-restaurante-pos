begin;

create schema if not exists respaldo;
revoke all on schema respaldo from public, anon, authenticated;

create table respaldo.productos_20261123 as table public.productos;
create table respaldo.ventas_20261123    as table public.ventas;
-- usuarios: sin la columna password (clave en texto plano): no se copia
create table respaldo.usuarios_20261123  as
  select usuario, rol, tienda_id from public.usuarios;

alter table respaldo.productos_20261123 enable row level security;
alter table respaldo.ventas_20261123    enable row level security;
alter table respaldo.usuarios_20261123  enable row level security;

-- Comprobación interna: si las copias no coinciden con el original, aborta todo
do $$
begin
  if (select count(*) from respaldo.productos_20261123) <> (select count(*) from public.productos)
  or (select count(*) from respaldo.ventas_20261123)    <> (select count(*) from public.ventas)
  or (select count(*) from respaldo.usuarios_20261123)  <> (select count(*) from public.usuarios)
  then raise exception 'El respaldo no coincide con las tablas originales'; end if;
end $$;

commit;
