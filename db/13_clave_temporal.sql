-- Clave temporal: los empleados vinculados por el dueño deben cambiar la clave en su primer ingreso.
-- Aditivo: una columna con valor por defecto false y una función nueva. Los perfiles existentes (el dueño) no cambian.
begin;

alter table public.perfiles add column if not exists debe_cambiar_clave boolean not null default false;

-- Los empleados nuevos nacen con la marca activada (el dueño les crea la cuenta con una clave temporal)
create or replace function public.vincular_empleado(p_email text, p_usuario text, p_rol text)
returns uuid language plpgsql security definer set search_path = ''
as $$
declare v_tienda text := private.mi_tienda(); v_id uuid;
begin
  if v_tienda is null or private.mi_rol() <> 'admin' then
    raise exception 'No autorizado' using errcode = '42501';
  end if;
  if p_rol not in ('mesero','cocina') then
    raise exception 'Rol inválido: solo mesero o cocina' using errcode = '22023';
  end if;
  if p_usuario is null or length(trim(p_usuario)) < 2 or length(trim(p_usuario)) > 40 then
    raise exception 'Nombre de usuario inválido' using errcode = '22023';
  end if;
  select id into v_id from auth.users where lower(email) = lower(trim(p_email));
  if v_id is null then
    raise exception 'Ese correo no existe en Authentication: créalo primero en el panel de Supabase' using errcode = '22023';
  end if;
  if exists (select 1 from public.perfiles where id = v_id) then
    raise exception 'Ese usuario ya tiene perfil' using errcode = '23505';
  end if;
  insert into public.perfiles (id, usuario, rol, tienda_id, debe_cambiar_clave)
  values (v_id, trim(p_usuario), p_rol, v_tienda, true);
  return v_id;
end $$;

-- El usuario desactiva SU PROPIA marca después de cambiar su clave (la clave misma la cambia Supabase Auth)
create or replace function public.clave_cambiada()
returns void language plpgsql security definer set search_path = ''
as $$
begin
  if auth.uid() is null then
    raise exception 'No autorizado' using errcode = '42501';
  end if;
  update public.perfiles set debe_cambiar_clave = false where id = auth.uid();
end $$;
revoke all on function public.clave_cambiada() from public, anon;
grant execute on function public.clave_cambiada() to authenticated;

commit;
