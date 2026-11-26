-- Antes: crear al dueño en Supabase (Authentication > Users > Add user) con su correo y una clave nueva.
-- Reemplaza el correo UNA sola vez (primera línea de la transacción) y ejecuta.
-- Si el correo no existe, ya hay perfil, o el perfil final no corresponde a ese usuario de Auth: error y no cambia nada.
begin;

select set_config('pos.correo', lower(trim('CORREO_DEL_DUEÑO@ejemplo.com')), true);

insert into public.perfiles (id, usuario, rol, tienda_id)
select u.id, 'pedro', 'admin', 'Tienda_A'
from auth.users u
where lower(trim(u.email)) = current_setting('pos.correo');

do $$
begin
  if not exists (
    select 1
    from public.perfiles p
    join auth.users u on u.id = p.id
    where p.usuario = 'pedro' and p.rol = 'admin' and p.tienda_id = 'Tienda_A'
      and lower(trim(u.email)) = current_setting('pos.correo')
  ) then
    raise exception 'No se vinculó el perfil del dueño: revisa que el correo exista en Authentication > Users';
  end if;
end $$;

commit;
