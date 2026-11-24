-- Operaciones de la app que escriben órdenes y empleados. Todas validan rol y restaurante dentro de la base.
begin;

-- Las funciones nuevas nacen sin permiso para anon/authenticated; se conceden una por una abajo.
alter default privileges in schema public revoke execute on functions from anon, authenticated;
alter default privileges revoke execute on functions from public;

-- 1. Crear orden (el precio sale SIEMPRE de la tabla productos, nunca del cliente)
create or replace function public.crear_orden(p_tipo text, p_mesa text, p_notas text, p_items jsonb)
returns uuid language plpgsql security definer set search_path = ''
as $$
declare
  v_tienda text := private.mi_tienda();
  v_rol    text := private.mi_rol();
  v_uid    uuid := auth.uid();
  v_nombre text;
  v_orden  uuid;
  v_item   jsonb;
  v_linea  int;
  v_prod   record;
  v_cant   int;
  v_total  bigint := 0;
begin
  if v_tienda is null or v_rol not in ('admin','mesero') then
    raise exception 'No autorizado' using errcode = '42501';
  end if;
  if p_tipo is null or p_tipo not in ('mesa','mostrador') then
    raise exception 'Tipo de orden inválido' using errcode = '22023';
  end if;
  if p_items is null or jsonb_typeof(p_items) <> 'array'
     or jsonb_array_length(p_items) < 1 or jsonb_array_length(p_items) > 50 then
    raise exception 'La orden debe tener entre 1 y 50 productos' using errcode = '22023';
  end if;

  select usuario into v_nombre from public.perfiles where id = v_uid;
  insert into public.ordenes (tienda_id, tipo, mesa, notas, mesero_id, mesero)
  values (v_tienda, p_tipo, nullif(trim(p_mesa), ''), nullif(trim(p_notas), ''), v_uid, v_nombre)
  returning id into v_orden;

  for v_item, v_linea in select e.value, e.ordinality::int from jsonb_array_elements(p_items) with ordinality e loop
    v_cant := (v_item ->> 'cantidad')::int;
    if v_cant is null or v_cant < 1 or v_cant > 99 then
      raise exception 'Cantidad inválida (1 a 99)' using errcode = '22023';
    end if;
    select id, nombre, precio into v_prod
    from public.productos
    where id = (v_item ->> 'producto_id')::uuid and tienda_id = v_tienda and activo;
    if not found then
      raise exception 'Producto no disponible' using errcode = '22023';
    end if;
    if v_prod.precio is null then
      raise exception 'Producto sin precio' using errcode = '22023';
    end if;
    insert into public.orden_items (orden_id, tienda_id, linea, producto_id, producto, precio, cantidad, nota)
    values (v_orden, v_tienda, v_linea, v_prod.id, v_prod.nombre, v_prod.precio, v_cant, nullif(trim(v_item ->> 'nota'), ''));
    v_total := v_total + v_prod.precio * v_cant;
  end loop;

  update public.ordenes set total = v_total where id = v_orden;
  perform private.registrar_auditoria(v_tienda, 'orden_creada', 'ordenes', v_orden::text,
    jsonb_build_object('tipo', p_tipo, 'mesa', nullif(trim(p_mesa), ''), 'total', v_total));
  return v_orden;
end $$;

-- 2. Cambiar el estado de una orden (cocina avanza; mesero entrega o anula la suya; admin todo)
create or replace function public.cambiar_estado_orden(p_id uuid, p_estado text)
returns void language plpgsql security definer set search_path = ''
as $$
declare
  v_tienda text := private.mi_tienda();
  v_rol    text := private.mi_rol();
  v_o      public.ordenes;
  v_ok     boolean := false;
begin
  if v_tienda is null or v_rol is null then
    raise exception 'No autorizado' using errcode = '42501';
  end if;
  select * into v_o from public.ordenes
  where id = p_id and tienda_id = v_tienda and archivado_en is null for update;
  if not found then
    raise exception 'Orden no encontrada' using errcode = '42501';
  end if;

  if v_rol = 'cocina' then
    v_ok := (v_o.estado = 'enviada' and p_estado = 'en_preparacion')
         or (v_o.estado = 'en_preparacion' and p_estado = 'lista');
  elsif v_rol = 'mesero' then
    if v_o.mesero_id is distinct from auth.uid() then
      raise exception 'Orden no encontrada' using errcode = '42501';
    end if;
    v_ok := (v_o.estado = 'lista' and p_estado = 'entregada')
         or (v_o.estado = 'enviada' and p_estado = 'anulada');
  elsif v_rol = 'admin' then
    v_ok := (v_o.estado = 'enviada' and p_estado = 'en_preparacion')
         or (v_o.estado = 'en_preparacion' and p_estado = 'lista')
         or (v_o.estado = 'lista' and p_estado = 'entregada')
         or (v_o.estado in ('enviada','en_preparacion','lista') and p_estado = 'anulada');
  end if;

  if not v_ok then
    raise exception 'Cambio de estado no permitido: % -> % (rol %)', v_o.estado, p_estado, v_rol;
  end if;
  update public.ordenes set estado = p_estado where id = p_id;
end $$;

-- 3. Tablero de cocina: sin precios ni totales
create or replace function public.tablero_cocina()
returns table (orden_id uuid, tipo text, mesa text, notas text, estado text,
               creado_en timestamptz, mesero text, items jsonb)
language plpgsql stable security definer set search_path = ''
as $$
begin
  if coalesce(private.mi_rol(), '') not in ('admin','cocina') then
    raise exception 'No autorizado' using errcode = '42501';
  end if;
  return query
    select o.id, o.tipo, o.mesa, o.notas, o.estado, o.creado_en, o.mesero,
           (select coalesce(jsonb_agg(jsonb_build_object('producto', i.producto, 'cantidad', i.cantidad, 'nota', i.nota)
                                      order by i.linea), '[]'::jsonb)
            from public.orden_items i where i.orden_id = o.id)
    from public.ordenes o
    where o.tienda_id = private.mi_tienda()
      and o.archivado_en is null
      and o.estado in ('enviada','en_preparacion','lista')
    order by o.creado_en;
end $$;

-- 4. "Reiniciar día": oculta (archiva) lo terminado; no borra nada
create or replace function public.archivar_historial()
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare v_tienda text := private.mi_tienda(); v_o int; v_v int;
begin
  if v_tienda is null or private.mi_rol() <> 'admin' then
    raise exception 'No autorizado' using errcode = '42501';
  end if;
  update public.ordenes set archivado_en = now(), archivado_por = auth.uid()
  where tienda_id = v_tienda and archivado_en is null and estado in ('entregada','anulada');
  get diagnostics v_o = row_count;
  update public.ventas set archivado_en = now(), archivado_por = auth.uid()
  where tienda_id = v_tienda and archivado_en is null;
  get diagnostics v_v = row_count;
  return jsonb_build_object('ordenes', v_o, 'ventas', v_v);
end $$;

-- 5. Vincular a un empleado que el dueño ya creó en Authentication
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
  insert into public.perfiles (id, usuario, rol, tienda_id) values (v_id, trim(p_usuario), p_rol, v_tienda);
  return v_id;
end $$;

-- 6. Activar / desactivar a un empleado (revoca el acceso de inmediato)
create or replace function public.set_empleado_activo(p_id uuid, p_activo boolean)
returns void language plpgsql security definer set search_path = ''
as $$
declare v_tienda text := private.mi_tienda();
begin
  if v_tienda is null or private.mi_rol() <> 'admin' then
    raise exception 'No autorizado' using errcode = '42501';
  end if;
  if p_id = auth.uid() then
    raise exception 'No puedes desactivarte a ti mismo' using errcode = '22023';
  end if;
  update public.perfiles set activo = p_activo
  where id = p_id and tienda_id = v_tienda and rol <> 'admin';
  if not found then
    raise exception 'Empleado no encontrado' using errcode = '42501';
  end if;
end $$;

-- Permisos de ejecución: solo usuarios con sesión (cada función valida su rol por dentro)
revoke all on function public.crear_orden(text,text,text,jsonb)        from public, anon;
revoke all on function public.cambiar_estado_orden(uuid,text)          from public, anon;
revoke all on function public.tablero_cocina()                         from public, anon;
revoke all on function public.archivar_historial()                     from public, anon;
revoke all on function public.vincular_empleado(text,text,text)        from public, anon;
revoke all on function public.set_empleado_activo(uuid,boolean)        from public, anon;
grant execute on function public.crear_orden(text,text,text,jsonb)     to authenticated;
grant execute on function public.cambiar_estado_orden(uuid,text)       to authenticated;
grant execute on function public.tablero_cocina()                      to authenticated;
grant execute on function public.archivar_historial()                  to authenticated;
grant execute on function public.vincular_empleado(text,text,text)     to authenticated;
grant execute on function public.set_empleado_activo(uuid,boolean)     to authenticated;

commit;
