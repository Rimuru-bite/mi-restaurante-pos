-- PRUEBAS DE SEGURIDAD Y FLUJOS. Ejecutar DESPUÉS del corte (08).
-- Todo ocurre en una transacción que termina en ROLLBACK. Si algo falla, el script se detiene con "FALLO ...".
-- Si termina sin error y la última consulta devuelve 0,0,0,0, todas las pruebas pasaron.
-- Nota: el contador de ids de `ventas` avanza aunque haya rollback (no se pierden filas).
\set ON_ERROR_STOP on
\o /dev/null
begin;

-- ---------- ayudantes (temporales) ----------
create function pg_temp.u(p text) returns uuid language sql stable as $$ select current_setting('t.' || p)::uuid $$;

create function pg_temp.como(p text) returns void language plpgsql as $$
begin
  reset role;
  perform set_config('request.jwt.claims', json_build_object('sub', current_setting('t.' || p), 'role', 'authenticated')::text, true);
  perform set_config('request.jwt.claim.sub', current_setting('t.' || p), true);
  set local role authenticated;
end $$;

create function pg_temp.como_anon() returns void language plpgsql as $$
begin
  reset role;
  perform set_config('request.jwt.claims', '', true);
  perform set_config('request.jwt.claim.sub', '', true);
  set local role anon;
end $$;

create function pg_temp.root() returns void language plpgsql as $$ begin reset role; end $$;

create function pg_temp.n(p_sql text) returns bigint language plpgsql as $$
declare r bigint; begin execute p_sql into r; return r; end $$;

create function pg_temp.espera(p_esperado bigint, p_sql text, p_msg text) returns void language plpgsql as $$
declare r bigint; begin
  execute p_sql into r;
  if r is distinct from p_esperado then
    raise exception 'FALLO %  (esperado %, obtenido %)', p_msg, p_esperado, r;
  end if;
end $$;

create function pg_temp.filas(p_esperado bigint, p_sql text, p_msg text) returns void language plpgsql as $$
declare r bigint; begin
  execute p_sql; get diagnostics r = row_count;
  if r <> p_esperado then raise exception 'FALLO %  (filas esperadas %, afectadas %)', p_msg, p_esperado, r; end if;
end $$;

create function pg_temp.ok(p_sql text, p_msg text) returns void language plpgsql as $$
begin
  begin execute p_sql;
  exception when others then raise exception 'FALLO %  (error inesperado % %)', p_msg, sqlstate, sqlerrm; end;
end $$;

-- p_estado: SQLSTATE esperado. 42501 = sin permiso / RLS; 22023 = dato inválido; P0001 = transición no permitida
create function pg_temp.negado(p_sql text, p_msg text, p_estado text default '42501') returns void language plpgsql as $$
begin
  begin execute p_sql;
  exception when others then
    if sqlstate = p_estado then return; end if;
    raise exception 'FALLO %  (error inesperado % %, se esperaba %)', p_msg, sqlstate, sqlerrm, p_estado;
  end;
  raise exception 'FALLO %  (se permitió y no debía)', p_msg;
end $$;

-- Los ayudantes temporales deben poder ejecutarse con los roles simulados
grant execute on all functions in schema pg_temp to public;

-- ---------- datos de prueba (como postgres) ----------
select set_config('t.a1',  '00000000-0000-0000-0000-00000000a001', true);  -- dueño A
select set_config('t.a2',  '00000000-0000-0000-0000-00000000a002', true);  -- mesero A
select set_config('t.a2b', '00000000-0000-0000-0000-00000000a00b', true);  -- otro mesero A
select set_config('t.a3',  '00000000-0000-0000-0000-00000000a003', true);  -- cocina A
select set_config('t.b1',  '00000000-0000-0000-0000-00000000b001', true);  -- dueño B
select set_config('t.b2',  '00000000-0000-0000-0000-00000000b002', true);  -- mesero B
select set_config('t.c1',  '00000000-0000-0000-0000-00000000c001', true);  -- autenticado sin perfil
select set_config('t.e1',  '00000000-0000-0000-0000-00000000e001', true);  -- empleado nuevo sin perfil
select set_config('t.e2',  '00000000-0000-0000-0000-00000000e002', true);  -- empleado de B

insert into public.restaurantes (tienda_id, nombre) values ('TEST_A','Test A'), ('TEST_B','Test B');
insert into auth.users (id, aud, role, email)
select pg_temp.u(k), 'authenticated', 'authenticated', k || '@test.invalid'
from unnest(array['a1','a2','a2b','a3','b1','b2','c1','e1','e2']) k;
insert into public.perfiles (id, usuario, rol, tienda_id) values
  (pg_temp.u('a1'),  'admin',       'admin',  'TEST_A'),
  (pg_temp.u('a2'),  't_mesero_a',  'mesero', 'TEST_A'),
  (pg_temp.u('a2b'), 't_mesero_a2', 'mesero', 'TEST_A'),
  (pg_temp.u('a3'),  't_cocina_a',  'cocina', 'TEST_A'),
  (pg_temp.u('b1'),  'admin',       'admin',  'TEST_B'),
  (pg_temp.u('b2'),  't_mesero_b',  'mesero', 'TEST_B'),
  (pg_temp.u('e2'),  't_cocina_b',  'cocina', 'TEST_B');
-- 'admin' se repite como usuario en dos restaurantes a propósito (permitido)

insert into public.productos (nombre, precio, tienda_id, activo) values
  ('Hamburguesa', 1000, 'TEST_A', true), ('Gaseosa', 500, 'TEST_A', true), ('Descontinuado', 300, 'TEST_A', false),
  ('Hamburguesa', 9000, 'TEST_B', true);   -- mismo nombre, otro restaurante, otro precio
select set_config('t.ham',  (select id::text from public.productos where tienda_id='TEST_A' and nombre='Hamburguesa'), true);
select set_config('t.gas',  (select id::text from public.productos where tienda_id='TEST_A' and nombre='Gaseosa'), true);
select set_config('t.desc', (select id::text from public.productos where tienda_id='TEST_A' and nombre='Descontinuado'), true);
select set_config('t.hamb', (select id::text from public.productos where tienda_id='TEST_B' and nombre='Hamburguesa'), true);

insert into public.ventas (producto, precio, cantidad, vendedor, total, tienda_id, vendedor_id) values
  ('Hamburguesa',1000,1,'t_mesero_a',1000,'TEST_A', pg_temp.u('a2')),
  ('Hamburguesa',1000,2,'admin',     2000,'TEST_A', pg_temp.u('a1')),
  ('Hamburguesa',9000,1,'t_mesero_b',9000,'TEST_B', pg_temp.u('b2')),
  ('Hamburguesa',9000,1,'admin',     9000,'TEST_B', pg_temp.u('b1'));
-- una orden del restaurante B, para probar aislamiento
insert into public.ordenes (id, tienda_id, tipo, mesa, total, mesero_id, mesero)
  values ('00000000-0000-0000-0000-0000000000b0', 'TEST_B', 'mesa', '1', 9000, pg_temp.u('b2'), 't_mesero_b');
insert into public.orden_items (orden_id, tienda_id, linea, producto_id, producto, precio, cantidad)
  values ('00000000-0000-0000-0000-0000000000b0', 'TEST_B', 1, pg_temp.u('hamb'), 'Hamburguesa', 9000, 1);

-- ---------- P1. Sin sesión (anon): nada ----------
select pg_temp.como_anon();
select pg_temp.negado('select 1 from public.' || t || ' limit 1', 'P1: anon leyó ' || t)
from unnest(array['productos','ventas','usuarios','perfiles','restaurantes','ordenes','orden_items','auditoria']) t;
select pg_temp.negado($q$select 1 from respaldo.productos_20261123$q$, 'P1: anon leyó respaldo');
select pg_temp.negado($q$select private.mi_tienda()$q$, 'P1: anon ejecutó private.mi_tienda');
select pg_temp.negado($q$select public.crear_orden('mostrador',null,null,'[]'::jsonb)$q$, 'P1: anon creó orden');
select pg_temp.negado($q$select * from public.tablero_cocina()$q$, 'P1: anon vio tablero');
select pg_temp.negado($q$select public.archivar_historial()$q$, 'P1: anon archivó');
select pg_temp.negado($q$select public.cambiar_estado_orden(gen_random_uuid(),'lista')$q$, 'P1: anon cambió estado');
select pg_temp.negado($q$select public.vincular_empleado('x@x.x','xx','mesero')$q$, 'P1: anon vinculó empleado');
select pg_temp.negado($q$select public.set_empleado_activo(gen_random_uuid(), false)$q$, 'P1: anon cambió empleado');
select pg_temp.negado($q$insert into public.ventas (producto,precio,cantidad,vendedor,total,tienda_id) values ('x',1,1,'x',1,'TEST_A')$q$, 'P1: anon registró venta');

-- ---------- P2. Autenticado sin perfil: no ve ni hace nada ----------
select pg_temp.como('c1');
select pg_temp.espera(0, 'select count(*) from public.' || t, 'P2: sin perfil ve ' || t)
from unnest(array['productos','ventas','perfiles','restaurantes','ordenes','orden_items','auditoria']) t;
select pg_temp.negado($q$select public.crear_orden('mostrador',null,null,jsonb_build_array(jsonb_build_object('producto_id',current_setting('t.ham'),'cantidad',1)))$q$, 'P2: sin perfil creó orden');
select pg_temp.negado($q$select * from public.tablero_cocina()$q$, 'P2: sin perfil vio tablero');
select pg_temp.negado($q$insert into public.ventas (producto,precio,cantidad,vendedor,total,tienda_id) values ('x',1,1,'x',1,'TEST_A')$q$, 'P2: sin perfil registró venta');

-- ---------- P3. Mesero A: crea órdenes y solo ve las suyas ----------
select pg_temp.como('a2');
select pg_temp.espera(3, 'select count(*) from public.productos', 'P3: mesero debía ver 3 productos (incluye desactivados)');
select pg_temp.espera(1, 'select count(*) from public.restaurantes', 'P3: mesero debía ver 1 restaurante');
select set_config('t.o1', public.crear_orden('mesa', '5', 'sin hielo', jsonb_build_array(
  jsonb_build_object('producto_id', current_setting('t.ham'), 'cantidad', 2, 'nota', 'sin cebolla', 'precio', 1),   -- precio del cliente: se ignora
  jsonb_build_object('producto_id', current_setting('t.gas'), 'cantidad', 1)))::text, true);
select pg_temp.espera(2500, $q$select total from public.ordenes where id = current_setting('t.o1')::uuid$q$, 'P3: total de la orden debe salir de la base (1000*2 + 500)');
select pg_temp.espera(2, $q$select count(*) from public.orden_items where orden_id = current_setting('t.o1')::uuid$q$, 'P3: la orden debía tener 2 ítems');
select pg_temp.espera(1000, $q$select precio from public.orden_items where producto = 'Hamburguesa' and orden_id = current_setting('t.o1')::uuid$q$, 'P3: el precio del ítem debe ser el de la base');
select pg_temp.espera(1, $q$select count(*) from public.ordenes where estado='enviada' and mesero = 't_mesero_a' and tienda_id='TEST_A'$q$, 'P3: la orden debe quedar enviada, a nombre del mesero');
select pg_temp.negado($q$select public.crear_orden('mesa','5',null,jsonb_build_array(jsonb_build_object('producto_id',current_setting('t.hamb'),'cantidad',1)))$q$, 'P3: producto de otro restaurante', '22023');
select pg_temp.negado($q$select public.crear_orden('mesa','5',null,jsonb_build_array(jsonb_build_object('producto_id',current_setting('t.desc'),'cantidad',1)))$q$, 'P3: producto desactivado', '22023');
select pg_temp.negado($q$select public.crear_orden('mesa','5',null,jsonb_build_array(jsonb_build_object('producto_id',current_setting('t.ham'),'cantidad',0)))$q$, 'P3: cantidad 0', '22023');
select pg_temp.negado($q$select public.crear_orden('mesa','5',null,jsonb_build_array(jsonb_build_object('producto_id',current_setting('t.ham'),'cantidad',100)))$q$, 'P3: cantidad 100', '22023');
select pg_temp.negado($q$select public.crear_orden('mesa','5',null,'[]'::jsonb)$q$, 'P3: orden vacía', '22023');
select pg_temp.negado($q$select public.crear_orden('delivery',null,null,jsonb_build_array(jsonb_build_object('producto_id',current_setting('t.ham'),'cantidad',1)))$q$, 'P3: tipo inválido', '22023');
select pg_temp.negado($q$select public.crear_orden('mesa',null,null,jsonb_build_array(jsonb_build_object('producto_id',current_setting('t.ham'),'cantidad',1)))$q$, 'P3: mesa sin número', '23514');
select pg_temp.espera(1, 'select count(*) from public.ordenes', 'P3: las órdenes rechazadas no deben dejar restos');
-- escrituras directas bloqueadas: todo pasa por funciones
select pg_temp.negado($q$insert into public.ordenes (tienda_id, tipo) values ('TEST_A','mostrador')$q$, 'P3: insert directo en ordenes');
select pg_temp.negado($q$update public.ordenes set estado = 'lista'$q$, 'P3: update directo en ordenes');
select pg_temp.negado($q$delete from public.ordenes$q$, 'P3: delete en ordenes');
select pg_temp.negado($q$insert into public.orden_items (orden_id, tienda_id, linea, producto_id, producto, precio, cantidad) select id, tienda_id, 9, current_setting('t.ham')::uuid, 'x', 1, 1 from public.ordenes$q$, 'P3: insert directo en orden_items');
select pg_temp.negado($q$update public.orden_items set precio = 1$q$, 'P3: cambió precios de ítems');
select pg_temp.negado($q$delete from public.orden_items$q$, 'P3: delete en orden_items');
select pg_temp.negado($q$update public.ventas set archivado_en = now()$q$, 'P3: mesero archivó ventas');
select pg_temp.negado($q$delete from public.ventas$q$, 'P3: mesero borró ventas');
select pg_temp.negado($q$insert into public.productos (nombre,precio,tienda_id) values ('t_mesero_prod',1,'TEST_A')$q$, 'P3: mesero creó producto');
select pg_temp.filas(0, $q$update public.productos set precio = 1$q$, 'P3: mesero editó productos');
select pg_temp.negado($q$select 1 from public.usuarios limit 1$q$, 'P3: mesero leyó usuarios');
select pg_temp.negado($q$update public.perfiles set rol = 'admin'$q$, 'P3: mesero cambió su rol');
select pg_temp.negado($q$insert into public.perfiles (id,usuario,rol,tienda_id) values (current_setting('t.c1')::uuid,'t_x','admin','TEST_A')$q$, 'P3: mesero creó perfil');
select pg_temp.negado($q$select public.archivar_historial()$q$, 'P3: mesero archivó historial');
select pg_temp.negado($q$select public.vincular_empleado('e1@test.invalid','t_nuevo','mesero')$q$, 'P3: mesero vinculó empleado');
select pg_temp.negado($q$select public.set_empleado_activo(current_setting('t.a3')::uuid, false)$q$, 'P3: mesero desactivó empleado');
select pg_temp.negado($q$select * from public.tablero_cocina()$q$, 'P3: mesero vio tablero de cocina');
select pg_temp.espera(0, 'select count(*) from public.auditoria', 'P3: mesero ve auditoría');
select pg_temp.espera(1, 'select count(*) from public.perfiles', 'P3: mesero debía ver solo su perfil');
-- venta rápida: el vendedor y la fecha los fija la base
select pg_temp.negado($q$insert into public.ventas (producto,precio,cantidad,vendedor,total,tienda_id) values ('Hamburguesa',9000,1,'x',9000,'TEST_B')$q$, 'P3: venta en otro restaurante');
select pg_temp.negado($q$insert into public.ventas (producto,precio,cantidad,vendedor,total,tienda_id,vendedor_id) values ('x',1000,1,'x',1000,'TEST_A',current_setting('t.a1')::uuid)$q$, 'P3: venta a nombre de otro');
select pg_temp.negado($q$insert into public.ventas (producto,precio,cantidad,vendedor,total,tienda_id,creado_en) values ('x',1000,1,'x',1000,'TEST_A', now() - interval '40 days')$q$, 'P3: fecha atrasada');
select pg_temp.negado($q$insert into public.ventas (producto,precio,cantidad,vendedor,total,tienda_id,archivado_en) values ('x',1000,1,'x',1000,'TEST_A', now())$q$, 'P3: venta ya archivada');
select pg_temp.negado($q$insert into public.ventas (producto,precio,cantidad,vendedor,total,tienda_id) values ('x',1000,5,'x',1,'TEST_A')$q$, 'P3: total incoherente', '23514');
select pg_temp.ok($q$insert into public.ventas (producto,precio,cantidad,vendedor,total,tienda_id) values ('Hamburguesa',1000,3,'NOMBRE_FALSO',3000,'TEST_A')$q$, 'P3: venta legítima');
select pg_temp.espera(0, $q$select count(*) from public.ventas where vendedor = 'NOMBRE_FALSO'$q$, 'P3: el mesero falseó el vendedor');
select pg_temp.espera(2, 'select count(*) from public.ventas', 'P3: mesero debía ver solo sus 2 ventas');
-- segunda orden: anular la propia mientras sigue "enviada"
select set_config('t.o2', public.crear_orden('mostrador', null, null, jsonb_build_array(
  jsonb_build_object('producto_id', current_setting('t.gas'), 'cantidad', 1)))::text, true);
select public.cambiar_estado_orden(current_setting('t.o2')::uuid, 'anulada');
select pg_temp.espera(1, $q$select count(*) from public.ordenes where id = current_setting('t.o2')::uuid and estado = 'anulada'$q$, 'P3: mesero anuló su orden');
select pg_temp.negado($q$select public.cambiar_estado_orden(current_setting('t.o2')::uuid, 'enviada')$q$, 'P3: revivir una orden anulada', 'P0001');
select pg_temp.negado($q$select public.cambiar_estado_orden(current_setting('t.o1')::uuid, 'lista')$q$, 'P3: mesero marcó "lista"', 'P0001');
select pg_temp.negado($q$select public.cambiar_estado_orden(current_setting('t.o1')::uuid, 'en_preparacion')$q$, 'P3: mesero marcó "en preparación"', 'P0001');
select pg_temp.espera(2, 'select count(*) from public.ordenes', 'P3: mesero debía ver sus 2 órdenes');

-- ---------- P3b. Otro mesero del mismo restaurante: no ve ni toca lo ajeno ----------
select pg_temp.como('a2b');
select pg_temp.espera(0, 'select count(*) from public.ordenes', 'P3b: otro mesero ve órdenes ajenas');
select pg_temp.espera(0, 'select count(*) from public.orden_items', 'P3b: otro mesero ve ítems ajenos');
select pg_temp.espera(0, 'select count(*) from public.ventas', 'P3b: otro mesero ve ventas ajenas');
select pg_temp.negado($q$select public.cambiar_estado_orden(current_setting('t.o1')::uuid, 'anulada')$q$, 'P3b: otro mesero tocó orden ajena');

-- ---------- P4. Cocina ----------
select pg_temp.como('a3');
select pg_temp.espera(3, 'select count(*) from public.productos', 'P4: cocina debía ver el menú');
select pg_temp.espera(0, 'select count(*) from public.ventas', 'P4: cocina ve ventas');
select pg_temp.espera(0, 'select count(*) from public.ordenes', 'P4: cocina lee la tabla de órdenes directamente');
select pg_temp.espera(0, 'select count(*) from public.orden_items', 'P4: cocina lee ítems (con precios) directamente');
select pg_temp.espera(1, 'select count(*) from public.tablero_cocina()', 'P4: el tablero debía mostrar 1 orden abierta');
select pg_temp.espera(2, 'select jsonb_array_length(items) from public.tablero_cocina()', 'P4: el tablero debía mostrar los 2 productos');
select pg_temp.espera(0, $q$select count(*) from public.tablero_cocina() t, jsonb_array_elements(t.items) i where i ? 'precio'$q$, 'P4: el tablero de cocina muestra precios');
select pg_temp.espera(1, $q$select count(*) from public.tablero_cocina() t, jsonb_array_elements(t.items) i where i->>'nota' = 'sin cebolla'$q$, 'P4: cocina debe ver las notas del ítem');
select pg_temp.negado($q$select public.cambiar_estado_orden(current_setting('t.o1')::uuid, 'lista')$q$, 'P4: cocina saltó un estado', 'P0001');
select public.cambiar_estado_orden(current_setting('t.o1')::uuid, 'en_preparacion');
select pg_temp.negado($q$select public.cambiar_estado_orden(current_setting('t.o1')::uuid, 'entregada')$q$, 'P4: cocina entregó', 'P0001');
select public.cambiar_estado_orden(current_setting('t.o1')::uuid, 'lista');
select pg_temp.negado($q$select public.cambiar_estado_orden(current_setting('t.o1')::uuid, 'anulada')$q$, 'P4: cocina anuló', 'P0001');
select pg_temp.negado($q$select public.cambiar_estado_orden(current_setting('t.o1')::uuid, 'en_preparacion')$q$, 'P4: cocina retrocedió un estado', 'P0001');
select pg_temp.negado($q$select public.cambiar_estado_orden('00000000-0000-0000-0000-0000000000b0', 'en_preparacion')$q$, 'P4: cocina A tocó orden del restaurante B');
select pg_temp.negado($q$select public.crear_orden('mostrador',null,null,jsonb_build_array(jsonb_build_object('producto_id',current_setting('t.ham'),'cantidad',1)))$q$, 'P4: cocina creó orden');
select pg_temp.negado($q$insert into public.ventas (producto,precio,cantidad,vendedor,total,tienda_id) values ('Hamburguesa',1000,1,'x',1000,'TEST_A')$q$, 'P4: cocina registró venta');
select pg_temp.negado($q$insert into public.productos (nombre,precio,tienda_id) values ('t_cocina',1,'TEST_A')$q$, 'P4: cocina creó producto');
select pg_temp.filas(0, $q$update public.productos set precio = 1$q$, 'P4: cocina editó productos');
select pg_temp.negado($q$select public.archivar_historial()$q$, 'P4: cocina archivó historial');
select pg_temp.negado($q$select public.vincular_empleado('e1@test.invalid','t_nuevo','mesero')$q$, 'P4: cocina vinculó empleado');
select pg_temp.espera(0, 'select count(*) from public.auditoria', 'P4: cocina ve auditoría');
select pg_temp.espera(1, 'select count(*) from public.perfiles', 'P4: cocina debía ver solo su perfil');

-- ---------- P4b. El mesero entrega su orden ----------
select pg_temp.como('a2');
select pg_temp.espera(1, $q$select count(*) from public.ordenes where id = current_setting('t.o1')::uuid and estado = 'lista'$q$, 'P4b: el mesero debe ver su orden en "lista"');
select public.cambiar_estado_orden(current_setting('t.o1')::uuid, 'entregada');
select pg_temp.negado($q$select public.cambiar_estado_orden(current_setting('t.o1')::uuid, 'anulada')$q$, 'P4b: mesero anuló una orden ya entregada', 'P0001');

-- ---------- P5. Dueño A ----------
select pg_temp.como('a1');
select pg_temp.espera(2, 'select count(*) from public.ordenes', 'P5: dueño debía ver las 2 órdenes de su restaurante');
select pg_temp.espera(3, 'select count(*) from public.orden_items', 'P5: dueño debía ver los 3 ítems de su restaurante');
select pg_temp.espera(0, $q$select count(*) from public.ordenes where tienda_id <> 'TEST_A'$q$, 'P5: dueño ve órdenes de otro restaurante');
select pg_temp.espera(3, 'select count(*) from public.ventas', 'P5: dueño debía ver las 3 ventas de su restaurante');
select pg_temp.espera(0, $q$select count(*) from public.ventas where tienda_id <> 'TEST_A'$q$, 'P5: dueño ve ventas de otro restaurante');
select pg_temp.espera(4, 'select count(*) from public.perfiles', 'P5: dueño debía ver los 4 perfiles de su restaurante');
select pg_temp.espera(1, 'select count(*) from public.restaurantes', 'P5: dueño debía ver 1 restaurante');
select pg_temp.espera(0, 'select count(*) from public.productos where precio = 9000', 'P5: dueño ve el producto de otro restaurante');
-- productos
select pg_temp.ok($q$insert into public.productos (nombre,precio,tienda_id) values ('t_nuevo_a',500,'TEST_A')$q$, 'P5: dueño no pudo crear producto');
select pg_temp.negado($q$insert into public.productos (nombre,precio,tienda_id) values ('Hamburguesa',1,'TEST_A')$q$, 'P5: nombre duplicado en el mismo restaurante', '23505');
select pg_temp.negado($q$insert into public.productos (id,nombre,precio,tienda_id) values (gen_random_uuid(),'t_id',1,'TEST_A')$q$, 'P5: dueño fijó el id del producto');
select pg_temp.filas(1, $q$update public.productos set precio = 1200 where nombre = 't_nuevo_a'$q$, 'P5: dueño no pudo editar su producto');
select pg_temp.filas(0, $q$update public.productos set precio = 1 where tienda_id = 'TEST_B'$q$, 'P5: dueño editó producto de otro restaurante');
select pg_temp.negado($q$insert into public.productos (nombre,precio,tienda_id) values ('t_cruce',1,'TEST_B')$q$, 'P5: dueño creó producto en otro restaurante');
select pg_temp.negado($q$update public.productos set nombre = 'otro'$q$, 'P5: dueño cambió el nombre de un producto');
select pg_temp.negado($q$delete from public.productos$q$, 'P5: dueño borró productos');
select pg_temp.negado($q$delete from public.ventas$q$, 'P5: dueño borró ventas');
select pg_temp.negado($q$delete from public.ordenes$q$, 'P5: dueño borró órdenes');
select pg_temp.negado($q$update public.ordenes set estado = 'lista'$q$, 'P5: dueño modificó órdenes por fuera de las funciones');
select pg_temp.negado($q$update public.ventas set total = 0$q$, 'P5: dueño modificó ventas');
select pg_temp.negado($q$select 1 from public.usuarios limit 1$q$, 'P5: dueño leyó usuarios');
select pg_temp.negado($q$update public.perfiles set rol = 'mesero'$q$, 'P5: dueño cambió perfiles directamente');
select pg_temp.negado($q$insert into public.perfiles (id,usuario,rol,tienda_id) values (current_setting('t.c1')::uuid,'t_x','mesero','TEST_A')$q$, 'P5: dueño creó perfil directamente');
-- órdenes del dueño y transiciones
select set_config('t.o3', public.crear_orden('mostrador', null, 'para llevar', jsonb_build_array(
  jsonb_build_object('producto_id', current_setting('t.ham'), 'cantidad', 1)))::text, true);
select pg_temp.negado($q$select public.cambiar_estado_orden(current_setting('t.o3')::uuid, 'lista')$q$, 'P5: dueño saltó un estado', 'P0001');
select public.cambiar_estado_orden(current_setting('t.o3')::uuid, 'en_preparacion');
select public.cambiar_estado_orden(current_setting('t.o3')::uuid, 'lista');
select public.cambiar_estado_orden(current_setting('t.o3')::uuid, 'anulada');
select set_config('t.o4', public.crear_orden('mesa', '7', null, jsonb_build_array(
  jsonb_build_object('producto_id', current_setting('t.gas'), 'cantidad', 4)))::text, true);
select public.cambiar_estado_orden(current_setting('t.o4')::uuid, 'en_preparacion');
select pg_temp.negado($q$select public.cambiar_estado_orden('00000000-0000-0000-0000-0000000000b0', 'anulada')$q$, 'P5: dueño A tocó orden del restaurante B');
-- empleados
select set_config('t.nuevo', public.vincular_empleado('E1@test.invalid', 't_cocina2', 'cocina')::text, true);
select pg_temp.espera(1, $q$select count(*) from public.perfiles where usuario = 't_cocina2' and rol = 'cocina' and tienda_id = 'TEST_A'$q$, 'P5: empleado vinculado');
select pg_temp.negado($q$select public.vincular_empleado('e1@test.invalid','t_otro','mesero')$q$, 'P5: vincular dos veces al mismo usuario', '23505');
select pg_temp.negado($q$select public.vincular_empleado('e2@test.invalid','t_robado','mesero')$q$, 'P5: vincular a un empleado de otro restaurante', '23505');
select pg_temp.negado($q$select public.vincular_empleado('no_existe@test.invalid','t_x','mesero')$q$, 'P5: vincular correo inexistente', '22023');
select pg_temp.negado($q$select public.vincular_empleado('c1@test.invalid','t_x','admin')$q$, 'P5: crear otro admin', '22023');
select pg_temp.negado($q$select public.vincular_empleado('c1@test.invalid','x','mesero')$q$, 'P5: usuario demasiado corto', '22023');
select pg_temp.negado($q$select public.set_empleado_activo(current_setting('t.a1')::uuid, false)$q$, 'P5: dueño se desactivó a sí mismo', '22023');
select pg_temp.negado($q$select public.set_empleado_activo(current_setting('t.e2')::uuid, false)$q$, 'P5: dueño A desactivó empleado de B');
select public.set_empleado_activo(current_setting('t.nuevo')::uuid, false);
select pg_temp.espera(1, $q$select count(*) from public.perfiles where usuario = 't_cocina2' and not activo$q$, 'P5: empleado desactivado');
-- auditoría
select pg_temp.espera(0, $q$select count(*) from public.auditoria where tienda_id <> 'TEST_A'$q$, 'P5: auditoría de otro restaurante visible');
select pg_temp.espera(6, $q$select count(distinct accion) from public.auditoria where accion in ('orden_creada','orden_estado','producto_creado','producto_modificado','empleado_vinculado','empleado_activo')$q$, 'P5: la auditoría debe registrar creación, estados, productos y empleados');
select pg_temp.espera(1, $q$select count(*) from public.auditoria where accion = 'orden_estado' and detalle->>'de' = 'lista' and detalle->>'a' = 'anulada' and usuario = 'admin'$q$, 'P5: la anulación debe quedar auditada con el usuario');
-- archivar ("reiniciar día"): oculta lo terminado, no borra nada
select pg_temp.espera(3, $q$select (public.archivar_historial() ->> 'ordenes')::bigint$q$, 'P5: debía archivar 3 órdenes terminadas (entregada + 2 anuladas)');
select pg_temp.espera(0, $q$select (public.archivar_historial() ->> 'ordenes')::bigint$q$, 'P5: archivar de nuevo no debe archivar nada más');
select pg_temp.espera(1, $q$select count(*) from public.ordenes where archivado_en is null and estado = 'en_preparacion'$q$, 'P5: la orden en curso no se archiva');
select pg_temp.espera(4, 'select count(*) from public.ordenes', 'P5: el dueño sigue viendo todo (incluido lo archivado)');
select pg_temp.espera(3, 'select count(*) from public.ventas where archivado_en is not null', 'P5: las 3 ventas debían quedar archivadas (no borradas)');
select pg_temp.espera(3, $q$select count(*) from public.auditoria where accion = 'orden_archivada'$q$, 'P5: archivado de órdenes auditado');
select pg_temp.espera(3, $q$select count(*) from public.auditoria where accion = 'venta_archivada'$q$, 'P5: archivado de ventas auditado');

-- ---------- P5b. Tras archivar: mesero y cocina ----------
select pg_temp.como('a2');
select pg_temp.espera(0, 'select count(*) from public.ordenes', 'P5b: mesero aún ve órdenes archivadas');
select pg_temp.espera(0, 'select count(*) from public.ventas', 'P5b: mesero aún ve ventas archivadas');
select pg_temp.como('a3');
select pg_temp.espera(1, 'select count(*) from public.tablero_cocina()', 'P5b: cocina debía ver solo la orden en curso');

-- ---------- P6. Restaurante B no ve nada de A ----------
select pg_temp.como('b1');
select pg_temp.espera(0, $q$select count(*) from public.ordenes where tienda_id = 'TEST_A'$q$, 'P6: dueño B ve órdenes de A');
select pg_temp.espera(1, 'select count(*) from public.ordenes', 'P6: dueño B debía ver su única orden');
select pg_temp.espera(0, $q$select count(*) from public.ventas where tienda_id = 'TEST_A'$q$, 'P6: dueño B ve ventas de A');
select pg_temp.espera(1, 'select count(*) from public.productos', 'P6: dueño B debía ver 1 producto');
select pg_temp.espera(9000, 'select precio from public.productos', 'P6: dueño B debía ver el precio de B');
select pg_temp.espera(0, $q$select count(*) from public.auditoria where tienda_id <> 'TEST_B'$q$, 'P6: dueño B ve auditoría de A');
select pg_temp.espera(0, $q$select count(*) from public.perfiles where tienda_id = 'TEST_A'$q$, 'P6: dueño B ve perfiles de A');
select pg_temp.negado($q$select public.set_empleado_activo(current_setting('t.a2')::uuid, false)$q$, 'P6: dueño B desactivó empleado de A');
select pg_temp.negado($q$select public.cambiar_estado_orden(current_setting('t.o4')::uuid, 'anulada')$q$, 'P6: dueño B tocó orden de A');
select pg_temp.espera(2, $q$select (public.archivar_historial() ->> 'ventas')::bigint$q$, 'P6: archivar de B solo debía alcanzar sus 2 ventas');
select pg_temp.como('b2');
select pg_temp.espera(1, 'select count(*) from public.ordenes', 'P6: mesero B debía ver su orden');
select pg_temp.espera(1, 'select count(*) from public.orden_items', 'P6: mesero B debía ver sus ítems');
select pg_temp.root();
select pg_temp.espera(0, $q$select count(*) from public.ordenes where tienda_id = 'TEST_A' and estado = 'en_preparacion' and archivado_en is not null$q$, 'P6: el archivado de B alcanzó órdenes de A');
select pg_temp.espera(0, $q$select count(*) from public.ventas where tienda_id = 'TEST_B' and archivado_en is null$q$, 'P6: las ventas de B debían quedar archivadas');

-- ---------- P7. Desactivar a un empleado le corta el acceso de inmediato (y solo a él) ----------
update public.perfiles set activo = false where id = pg_temp.u('a3');
select pg_temp.como('a3');
select pg_temp.espera(0, 'select count(*) from public.productos', 'P7: empleado desactivado aún ve productos');
select pg_temp.negado($q$select * from public.tablero_cocina()$q$, 'P7: empleado desactivado ve el tablero');
select pg_temp.negado($q$select public.cambiar_estado_orden(current_setting('t.o4')::uuid, 'lista')$q$, 'P7: empleado desactivado cambió estado');
select pg_temp.como('a2');
select pg_temp.espera(4, 'select count(*) from public.productos', 'P7: la desactivación afectó a otro empleado');

-- ---------- P8. Reglas de estructura (como postgres) ----------
select pg_temp.root();
select pg_temp.negado($q$insert into public.perfiles (id,usuario,rol,tienda_id) values (current_setting('t.c1')::uuid,'t_mesero_a','mesero','TEST_A')$q$, 'P8: nombre de usuario duplicado dentro del restaurante', '23505');
select pg_temp.negado($q$update public.ordenes set estado = 'cualquiera'$q$, 'P8: estado inválido', '23514');
select pg_temp.negado($q$update public.orden_items set cantidad = 0$q$, 'P8: cantidad inválida', '23514');

-- ---------- P9. Objetos nuevos nacen cerrados ----------
create table public.t_prueba_nueva (id int);
create function public.t_fn_nueva() returns int language sql as 'select 1';
select pg_temp.espera(0, $q$select count(*) from (values (has_table_privilege('anon','public.t_prueba_nueva','select')), (has_table_privilege('authenticated','public.t_prueba_nueva','select')), (has_function_privilege('anon','public.t_fn_nueva()','execute')), (has_function_privilege('authenticated','public.t_fn_nueva()','execute'))) v(x) where x$q$, 'P9: objetos nuevos nacen con permisos para la API');
select pg_temp.espera(0, $q$select count(*) from information_schema.role_routine_grants where routine_schema = 'public' and grantee in ('anon','PUBLIC') and routine_name in ('crear_orden','cambiar_estado_orden','tablero_cocina','archivar_historial','vincular_empleado','set_empleado_activo')$q$, 'P9: funciones públicas ejecutables por anon');

-- ---------- P10. El dueño real, con el flujo de la app (solo si ya está vinculado) ----------
do $$
declare pid uuid;
begin
  select id into pid from public.perfiles where usuario = 'pedro' and tienda_id = 'Tienda_A';
  if pid is null then raise notice 'P10 omitida: pedro aún no está vinculado'; return; end if;
  perform set_config('t.pedro', pid::text, true);
  perform set_config('t.pprod', (select id::text from public.productos where tienda_id = 'Tienda_A' and activo order by nombre limit 1), true);
end $$;
select pg_temp.como('pedro') where current_setting('t.pedro', true) is not null;
select pg_temp.espera((select count(*) from public.productos where tienda_id = 'Tienda_A' and activo), $q$select count(*) from public.productos where tienda_id = 'Tienda_A' and activo$q$, 'P10: pedro debía ver su menú') where current_setting('t.pedro', true) is not null;
select public.crear_orden('mostrador', null, null, jsonb_build_array(jsonb_build_object('producto_id', current_setting('t.pprod'), 'cantidad', 2))) where current_setting('t.pedro', true) is not null;
select pg_temp.ok($q$insert into public.ventas (producto,precio,cantidad,total,vendedor,tienda_id) values ('Hamburguesa',2500,2,5000,'pedro','Tienda_A')$q$, 'P10: pedro registró venta rápida') where current_setting('t.pedro', true) is not null;
select pg_temp.espera(1, $q$select count(*) from public.ordenes where tienda_id = 'Tienda_A'$q$, 'P10: pedro debía ver su orden') where current_setting('t.pedro', true) is not null;

rollback;

-- Si no hubo ningún error, todas las pruebas pasaron. Comprobación de que no quedó basura (todo debe dar 0):
\o
select
  (select count(*) from public.productos    where tienda_id like 'TEST\_%') as productos_de_prueba,
  (select count(*) from public.ordenes      where tienda_id like 'TEST\_%' or tienda_id = 'Tienda_A') as ordenes_de_prueba,
  (select count(*) from public.restaurantes where tienda_id like 'TEST\_%') as restaurantes_de_prueba,
  (select count(*) from information_schema.tables where table_schema = 'public' and table_name = 't_prueba_nueva') as tablas_de_prueba;
