-- CORTE: la app anterior (clave anon + tabla usuarios) deja de funcionar al ejecutar esto.
-- Ejecutar solo cuando la app nueva (Supabase Auth) esté desplegada.
begin;

-- 8-0. Precondición: debe existir al menos un admin activo vinculado a un usuario de Auth (bloque 07).
-- Sin él, el corte dejaría a todos sin acceso. Si falla, no se cambia nada.
do $$
begin
  if not exists (select 1 from public.perfiles p join auth.users u on u.id = p.id
                 where p.rol = 'admin' and p.activo) then
    raise exception 'Corte cancelado: no hay un admin activo vinculado a Auth. Ejecuta antes el bloque 07.';
  end if;
end $$;

-- 8a. Quitar todo y devolver solo lo mínimo
revoke all on table public.usuarios, public.ventas, public.productos, public.restaurantes,
                    public.perfiles, public.ordenes, public.orden_items, public.auditoria
  from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
alter default privileges in schema public revoke all on tables    from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;

alter table public.usuarios     enable row level security;  -- sin políticas: cerrada a la API
alter table public.ventas       enable row level security;
alter table public.productos    enable row level security;
alter table public.restaurantes enable row level security;
alter table public.perfiles     enable row level security;
alter table public.ordenes      enable row level security;
alter table public.orden_items  enable row level security;
alter table public.auditoria    enable row level security;

grant select on public.restaurantes, public.perfiles, public.ordenes, public.orden_items, public.auditoria to authenticated;

-- Ventas (venta rápida): solo estas columnas se escriben; el resto lo fija la base. No hay UPDATE ni DELETE.
grant select on public.ventas to authenticated;
grant insert (producto, precio, cantidad, vendedor, total, tienda_id) on public.ventas to authenticated;

-- Productos: el dueño crea y edita precio / activo (no hay DELETE: se desactiva)
grant select on public.productos to authenticated;
grant insert (nombre, precio, tienda_id, activo) on public.productos to authenticated;
grant update (precio, activo) on public.productos to authenticated;

-- 8b. El vendedor lo fija la base con la identidad real
create or replace function private.fijar_vendedor() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  new.vendedor_id := coalesce(auth.uid(), new.vendedor_id);
  new.vendedor    := coalesce((select usuario from public.perfiles where id = auth.uid()), new.vendedor);
  return new;
end $$;
revoke all on function private.fijar_vendedor() from public, anon, authenticated;
create trigger ventas_fijar_vendedor before insert on public.ventas
  for each row execute function private.fijar_vendedor();

-- 8c. Políticas
create policy restaurantes_ver on public.restaurantes for select to authenticated
  using (tienda_id = (select private.mi_tienda()));

create policy perfiles_ver on public.perfiles for select to authenticated
  using (id = (select auth.uid())
         or (tienda_id = (select private.mi_tienda()) and (select private.mi_rol()) = 'admin'));

create policy productos_ver on public.productos for select to authenticated
  using (tienda_id = (select private.mi_tienda()));
create policy productos_crear on public.productos for insert to authenticated
  with check (tienda_id = (select private.mi_tienda()) and (select private.mi_rol()) = 'admin');
create policy productos_editar on public.productos for update to authenticated
  using      (tienda_id = (select private.mi_tienda()) and (select private.mi_rol()) = 'admin')
  with check (tienda_id = (select private.mi_tienda()) and (select private.mi_rol()) = 'admin');

create policy ventas_ver_admin on public.ventas for select to authenticated
  using (tienda_id = (select private.mi_tienda()) and (select private.mi_rol()) = 'admin');
create policy ventas_ver_mesero on public.ventas for select to authenticated
  using (tienda_id = (select private.mi_tienda()) and (select private.mi_rol()) = 'mesero'
         and vendedor_id = (select auth.uid()) and archivado_en is null);
create policy ventas_crear on public.ventas for insert to authenticated
  with check (tienda_id = (select private.mi_tienda()) and (select private.mi_rol()) in ('admin','mesero')
              and vendedor_id = (select auth.uid()));

-- Órdenes: se escriben solo con las funciones; aquí solo lectura. Cocina las ve por tablero_cocina() (sin precios).
create policy ordenes_ver_admin on public.ordenes for select to authenticated
  using (tienda_id = (select private.mi_tienda()) and (select private.mi_rol()) = 'admin');
create policy ordenes_ver_mesero on public.ordenes for select to authenticated
  using (tienda_id = (select private.mi_tienda()) and (select private.mi_rol()) = 'mesero'
         and mesero_id = (select auth.uid()) and archivado_en is null);
create policy orden_items_ver on public.orden_items for select to authenticated
  using (exists (select 1 from public.ordenes o where o.id = orden_items.orden_id));

create policy auditoria_ver on public.auditoria for select to authenticated
  using (tienda_id = (select private.mi_tienda()) and (select private.mi_rol()) = 'admin');

commit;
