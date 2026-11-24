-- Comandas (ordenes + orden_items), estados de cocina y auditoría. Solo agrega objetos nuevos.
begin;

create table public.ordenes (
  id             uuid primary key default gen_random_uuid(),
  tienda_id      text not null references public.restaurantes(tienda_id),
  tipo           text not null check (tipo in ('mesa','mostrador')),
  mesa           text check (mesa is null or length(mesa) <= 30),
  estado         text not null default 'enviada'
                   check (estado in ('enviada','en_preparacion','lista','entregada','anulada')),
  notas          text check (notas is null or length(notas) <= 300),
  total          bigint not null default 0 check (total >= 0),
  mesero_id      uuid references auth.users(id) on delete set null,
  mesero         text,
  creado_en      timestamptz not null default now(),
  actualizado_en timestamptz not null default now(),
  archivado_en   timestamptz,
  archivado_por  uuid references auth.users(id) on delete set null,
  constraint ordenes_mesa_requerida check (tipo <> 'mesa' or (mesa is not null and length(trim(mesa)) > 0))
);
create index ordenes_tienda_fecha_idx  on public.ordenes (tienda_id, creado_en desc);
create index ordenes_tienda_estado_idx on public.ordenes (tienda_id, estado) where archivado_en is null;

create table public.orden_items (
  id          uuid primary key default gen_random_uuid(),
  orden_id    uuid not null references public.ordenes(id) on delete restrict,
  tienda_id   text not null references public.restaurantes(tienda_id),
  linea       int  not null,
  producto_id uuid not null references public.productos(id) on delete restrict,
  producto    text not null,           -- nombre al momento de pedir
  precio      bigint not null check (precio >= 0),  -- precio al momento de pedir
  cantidad    int  not null check (cantidad between 1 and 99),
  nota        text check (nota is null or length(nota) <= 200)
);
create index orden_items_orden_idx on public.orden_items (orden_id);

create table public.auditoria (
  id          bigint generated always as identity primary key,
  tienda_id   text,
  usuario_id  uuid,
  usuario     text,
  accion      text not null,
  tabla       text,
  registro_id text,
  detalle     jsonb,
  creado_en   timestamptz not null default now()
);
create index auditoria_tienda_fecha_idx on public.auditoria (tienda_id, creado_en desc);

-- Nacen cerradas: RLS activo y sin permisos para la API hasta el corte (08)
alter table public.ordenes     enable row level security;
alter table public.orden_items enable row level security;
alter table public.auditoria   enable row level security;
revoke all on public.ordenes, public.orden_items, public.auditoria from anon, authenticated;

-- Auditoría
create or replace function private.registrar_auditoria(p_tienda text, p_accion text, p_tabla text, p_registro text, p_detalle jsonb)
returns void language plpgsql security definer set search_path = ''
as $$
declare v_uid uuid := auth.uid(); v_nombre text;
begin
  select usuario into v_nombre from public.perfiles where id = v_uid;
  insert into public.auditoria (tienda_id, usuario_id, usuario, accion, tabla, registro_id, detalle)
  values (p_tienda, v_uid, coalesce(v_nombre, case when v_uid is null then 'sistema' end), p_accion, p_tabla, p_registro, p_detalle);
end $$;
revoke all on function private.registrar_auditoria(text,text,text,text,jsonb) from public, anon, authenticated;

create or replace function private.trg_auditar() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  if tg_table_name = 'productos' then
    if tg_op = 'INSERT' then
      perform private.registrar_auditoria(new.tienda_id, 'producto_creado', 'productos', new.id::text,
        jsonb_build_object('nombre', new.nombre, 'precio', new.precio));
    elsif new.precio is distinct from old.precio or new.activo is distinct from old.activo then
      perform private.registrar_auditoria(new.tienda_id, 'producto_modificado', 'productos', new.id::text,
        jsonb_build_object('nombre', new.nombre, 'precio_antes', old.precio, 'precio', new.precio,
                           'activo_antes', old.activo, 'activo', new.activo));
    end if;
  elsif tg_table_name = 'ordenes' then
    new.actualizado_en := now();
    if new.estado is distinct from old.estado then
      perform private.registrar_auditoria(new.tienda_id, 'orden_estado', 'ordenes', new.id::text,
        jsonb_build_object('de', old.estado, 'a', new.estado));
    end if;
    if old.archivado_en is null and new.archivado_en is not null then
      perform private.registrar_auditoria(new.tienda_id, 'orden_archivada', 'ordenes', new.id::text, null);
    end if;
  elsif tg_table_name = 'ventas' then
    if old.archivado_en is null and new.archivado_en is not null then
      perform private.registrar_auditoria(new.tienda_id, 'venta_archivada', 'ventas', new.id::text,
        jsonb_build_object('total', new.total));
    end if;
  elsif tg_table_name = 'perfiles' then
    if tg_op = 'INSERT' then
      perform private.registrar_auditoria(new.tienda_id, 'empleado_vinculado', 'perfiles', new.id::text,
        jsonb_build_object('usuario', new.usuario, 'rol', new.rol));
    elsif new.activo is distinct from old.activo then
      perform private.registrar_auditoria(new.tienda_id, 'empleado_activo', 'perfiles', new.id::text,
        jsonb_build_object('usuario', new.usuario, 'activo', new.activo));
    end if;
  end if;
  return new;
end $$;
revoke all on function private.trg_auditar() from public, anon, authenticated;

create trigger productos_auditar after insert or update on public.productos
  for each row execute function private.trg_auditar();
create trigger ordenes_auditar   before update on public.ordenes
  for each row execute function private.trg_auditar();
create trigger ventas_auditar    after update on public.ventas
  for each row execute function private.trg_auditar();
create trigger perfiles_auditar  after insert or update on public.perfiles
  for each row execute function private.trg_auditar();

commit;
