-- 09p_limpieza · Borra SOLO las filas de prueba de 09p (prefijo reservado 'ZZ_09P_'). Seguro de ejecutar varias veces.
-- Úsalo si 09p se cortó a medias. No toca Auth, ni datos reales (ningún restaurante real empieza con ZZ_09P_).
begin;
set local session_replication_role = replica;
do $l$
begin
  delete from public.orden_items  where tienda_id like 'ZZ\_09P\_%';
  delete from public.ordenes      where tienda_id like 'ZZ\_09P\_%';
  delete from public.ventas       where tienda_id like 'ZZ\_09P\_%';
  delete from public.productos    where tienda_id like 'ZZ\_09P\_%';
  delete from public.perfiles     where tienda_id like 'ZZ\_09P\_%';
  delete from public.auditoria    where tienda_id like 'ZZ\_09P\_%';
  delete from public.restaurantes where tienda_id like 'ZZ\_09P\_%';
  if (select count(*) from public.restaurantes where tienda_id like 'ZZ\_09P\_%')
   + (select count(*) from public.perfiles     where tienda_id like 'ZZ\_09P\_%')
   + (select count(*) from public.productos    where tienda_id like 'ZZ\_09P\_%')
   + (select count(*) from public.ordenes      where tienda_id like 'ZZ\_09P\_%')
   + (select count(*) from public.orden_items  where tienda_id like 'ZZ\_09P\_%')
   + (select count(*) from public.ventas       where tienda_id like 'ZZ\_09P\_%')
   + (select count(*) from public.auditoria    where tienda_id like 'ZZ\_09P\_%') > 0 then
    raise exception '09p_limpieza: quedaron filas de prueba';
  end if;
end $l$;
commit;
select (select count(*) from public.restaurantes where tienda_id like 'ZZ\_09P\_%') as sobras_restaurantes,
       (select count(*) from public.perfiles     where tienda_id like 'ZZ\_09P\_%') as sobras_perfiles,
       (select count(*) from public.productos    where tienda_id like 'ZZ\_09P\_%') as sobras_productos,
       (select count(*) from public.ordenes      where tienda_id like 'ZZ\_09P\_%') as sobras_ordenes,
       (select count(*) from public.ventas       where tienda_id like 'ZZ\_09P\_%') as sobras_ventas;
