-- Antes: crear al dueño en Supabase (Authentication > Users > Add user) con su correo y una clave nueva.
-- Reemplaza el correo y ejecuta.
begin;

insert into public.perfiles (id, usuario, rol, tienda_id)
select u.id, 'pedro', 'admin', 'Tienda_A'
from auth.users u
where u.email = 'CORREO_DEL_DUEÑO@ejemplo.com';

do $$
begin
  if (select count(*) from public.perfiles where usuario = 'pedro' and tienda_id = 'Tienda_A') <> 1
  then raise exception 'No se vinculó el perfil del dueño: revisa que el correo exista en Authentication > Users'; end if;
end $$;

commit;
