-- 09p · PRUEBAS PARA PRODUCCIÓN (Supabase SQL Editor). Ejecutar DESPUÉS del corte 08. Un solo pegado, tal cual.
--
-- Qué hace (3 fases, sin DDL, sin tocar Auth, sin funciones/tablas auxiliares):
--   FASE 1  Crea datos FICTICIOS con prefijo reservado 'ZZ_09P_<id aleatorio>' (restaurante, perfiles, productos) y hace COMMIT.
--   FASE 2  Corre las pruebas simulando cada rol. Cada prueba atrapa su propio error: una falla NO detiene el script.
--   FASE 3  Limpieza explícita, solo de filas con ese prefijo, y verificación de que no queda nada (si queda algo, falla con error).
--   Resultado: la última consulta devuelve una fila: pruebas_ok, pruebas_fallidas, detalle_fallos, sobras_*.
-- Si el script se corta en cualquier punto (error, cierre de pestaña): ejecutar 09p_limpieza.sql.
--
-- Perfiles falsos: se insertan con session_replication_role = replica SOLO dentro de la transacción (LOCAL), porque
-- perfiles.id apunta a auth.users y NO se crean usuarios en Auth. Efecto: en esas transacciones no se validan FKs
-- ni se disparan triggers (ver 09p_LEEME.md: lo que esto implica que NO se verifica).

-- ============================== FASE 1: datos ficticios ==============================
begin;
set local session_replication_role = replica;
do $f1$
declare
  v_run text;
  v_a text; v_b text;
begin
  if exists (select 1 from public.restaurantes where tienda_id like 'ZZ\_09P\_%')
     or exists (select 1 from public.perfiles   where tienda_id like 'ZZ\_09P\_%')
     or exists (select 1 from public.productos  where tienda_id like 'ZZ\_09P\_%')
     or exists (select 1 from public.ordenes    where tienda_id like 'ZZ\_09P\_%') then
    raise exception '09p: hay restos de una corrida anterior. Ejecuta primero 09p_limpieza.sql';
  end if;
  v_run := substr(replace(gen_random_uuid()::text, '-', ''), 1, 10);
  v_a := 'ZZ_09P_' || v_run || '_A';
  v_b := 'ZZ_09P_' || v_run || '_B';

  insert into public.restaurantes (tienda_id, nombre) values (v_a, 'Prueba 09p A'), (v_b, 'Prueba 09p B');

  -- ids nuevos (no existen en auth.users: no hay ningún usuario real involucrado)
  insert into public.perfiles (id, usuario, rol, tienda_id, activo) values
    (gen_random_uuid(), 'adm_a',  'admin',  v_a, true),
    (gen_random_uuid(), 'mes_a1', 'mesero', v_a, true),
    (gen_random_uuid(), 'mes_a2', 'mesero', v_a, true),
    (gen_random_uuid(), 'coc_a',  'cocina', v_a, true),
    (gen_random_uuid(), 'adm_b',  'admin',  v_b, true),
    (gen_random_uuid(), 'sin_perfil_activo', 'mesero', v_a, false);

  insert into public.productos (nombre, precio, tienda_id, activo) values
    ('Arepa 09p',   5000, v_a, true),
    ('Jugo 09p',    3000, v_a, true),
    ('Retirado 09p',9000, v_a, false),
    ('Arepa 09p',   7000, v_b, true);   -- mismo nombre en otro restaurante: permitido
end $f1$;
commit;

-- ============================== FASE 2: pruebas ==============================
begin;
set local session_replication_role = replica;
do $f2$
declare
  v_a text; v_b text;
  u jsonb := '{}';            -- uid por alias
  v jsonb := '{}';            -- valores guardados entre pruebas ({ord1}, {p_arepa}, ...)
  t record; v_sql text; v_res text; v_n int := 0; v_fail jsonb := '[]'; v_ok int := 0;
  v_pass boolean; v_err text; v_st text;
begin
  select tienda_id into v_a from public.restaurantes where tienda_id like 'ZZ\_09P\_%\_A';
  select tienda_id into v_b from public.restaurantes where tienda_id like 'ZZ\_09P\_%\_B';
  if v_a is null or v_b is null or (select count(*) from public.restaurantes where tienda_id like 'ZZ\_09P\_%') <> 2 then
    raise exception '09p: la fase 1 no dejó exactamente un juego de datos de prueba';
  end if;
  select jsonb_object_agg(usuario, id) into u from public.perfiles where tienda_id in (v_a, v_b);
  v := jsonb_build_object('A', v_a, 'B', v_b,
    'p_arepa',  (select id from public.productos where tienda_id = v_a and nombre = 'Arepa 09p'),
    'p_jugo',   (select id from public.productos where tienda_id = v_a and nombre = 'Jugo 09p'),
    'p_retirado',(select id from public.productos where tienda_id = v_a and nombre = 'Retirado 09p'),
    'p_arepa_b',(select id from public.productos where tienda_id = v_b));

  -- quien: alias de usuario | 'anon' | 'sinperfil' (uid sin fila en perfiles) | 'root'
  -- espera: ok | deny | err:<SQLSTATE> | n:<N> (select count) | v:<texto> (select valor)
  -- guarda: nombre con el que se guarda el resultado de un 'select' escalar
  for t in
    select * from (values
     -- ---- anónimo sin acceso a nada
     (1,'anon','select count(*) from public.productos','deny',null),
     (2,'anon','select count(*) from public.ventas','deny',null),
     (3,'anon','select public.crear_orden(''mostrador'',null,null,''[]''::jsonb)','deny',null),
     -- ---- usuario autenticado sin perfil: nada de nada
     (4,'sinperfil','select count(*) from public.productos','n:0',null),
     (5,'sinperfil','select count(*) from public.tablero_cocina()','err:42501',null),
     (6,'sinperfil',$s$select public.crear_orden('mostrador',null,null,'[{"producto_id":"{p_arepa}","cantidad":1}]')$s$,'err:42501',null),
     -- ---- mesero crea órdenes; el precio sale de la base
     (10,'mes_a1',$s$select public.crear_orden('mostrador',null,'sin cebolla','[{"producto_id":"{p_arepa}","cantidad":2,"precio":1},{"producto_id":"{p_jugo}","cantidad":1}]')$s$,'ok','ord1'),
     (11,'mes_a1','select total::text from public.ordenes where id = ''{ord1}''','v:13000',null),
     (12,'mes_a1','select count(*) from public.orden_items where orden_id = ''{ord1}'' and precio in (5000,3000)','n:2',null),
     (13,'mes_a1',$s$select public.crear_orden('mesa',null,null,'[{"producto_id":"{p_arepa}","cantidad":1}]')$s$,'err:23514',null),
     (14,'mes_a1',$s$select public.crear_orden('mesa','5',null,'[{"producto_id":"{p_retirado}","cantidad":1}]')$s$,'err:22023',null),
     (15,'mes_a1',$s$select public.crear_orden('mesa','5',null,'[{"producto_id":"{p_arepa_b}","cantidad":1}]')$s$,'err:22023',null),
     (16,'mes_a1',$s$select public.crear_orden('mesa','5',null,'[{"producto_id":"{p_arepa}","cantidad":0}]')$s$,'err:22023',null),
     (17,'mes_a1',$s$select public.crear_orden('mesa','5',null,'[]')$s$,'err:22023',null),
     (18,'mes_a1',$s$select public.crear_orden('barra','5',null,'[{"producto_id":"{p_arepa}","cantidad":1}]')$s$,'err:22023',null),
     (19,'cocina_no','select 1','ok',null),
     -- ---- mesero: sin escritura directa ni escalada
     (20,'mes_a1','insert into public.ordenes (tienda_id, tipo, total) values (''{A}'',''mostrador'',1)','deny',null),
     (21,'mes_a1','update public.ordenes set total = 1 where id = ''{ord1}''','deny',null),
     (22,'mes_a1','with x as (update public.productos set precio = 1 where tienda_id = ''{A}'' returning 1) select count(*) from x','n:0',null),
     (23,'mes_a1','insert into public.productos (nombre, precio, tienda_id) values (''Colado'',1,''{A}'')','deny',null),
     (24,'mes_a1','update public.perfiles set rol = ''admin'' where usuario = ''mes_a1''','deny',null),
     (25,'mes_a1','select count(*) from public.auditoria','n:0',null),
     (26,'mes_a1','select count(*) from public.tablero_cocina()','err:42501',null),
     (27,'mes_a1','select public.archivar_historial()::text','err:42501',null),
     (28,'mes_a1','select public.vincular_empleado(''nadie@no-existe.invalid'',''x1'',''mesero'')::text','err:42501',null),
     -- ---- aislamiento entre restaurantes y entre meseros
     (30,'mes_a1','select count(*) from public.productos where tienda_id = ''{B}''','n:0',null),
     (31,'mes_a1','select count(*) from public.productos where tienda_id = ''{A}''','n:3',null),
     (32,'adm_b','select count(*) from public.ordenes where tienda_id = ''{A}''','n:0',null),
     (33,'adm_b','select count(*) from public.productos where tienda_id = ''{A}''','n:0',null),
     (34,'adm_b','select count(*) from public.perfiles where tienda_id = ''{A}''','n:0',null),
     (35,'mes_a2','select count(*) from public.ordenes where id = ''{ord1}''','n:0',null),
     (36,'mes_a2','select public.cambiar_estado_orden(''{ord1}'',''anulada'')::text','err:42501',null),
     (37,'adm_b','select public.cambiar_estado_orden(''{ord1}'',''anulada'')::text','err:42501',null),
     -- ---- cocina: tablero sin precios, estados en orden, sin crear órdenes
     (40,'coc_a','select count(*) from public.tablero_cocina() where orden_id = ''{ord1}''','n:1',null),
     (41,'coc_a','select count(*) from public.tablero_cocina() t where t.items::text ~ ''precio|total''','n:0',null),
     (42,'coc_a','select count(*) from public.ordenes','n:0',null),
     (43,'coc_a',$s$select public.crear_orden('mostrador',null,null,'[{"producto_id":"{p_arepa}","cantidad":1}]')$s$,'err:42501',null),
     (44,'coc_a','select public.cambiar_estado_orden(''{ord1}'',''lista'')::text','err:P0001',null),
     (45,'coc_a','select public.cambiar_estado_orden(''{ord1}'',''en_preparacion'')::text','ok',null),
     (46,'coc_a','select public.cambiar_estado_orden(''{ord1}'',''entregada'')::text','err:P0001',null),
     (47,'coc_a','select public.cambiar_estado_orden(''{ord1}'',''lista'')::text','ok',null),
     (48,'mes_a1','select estado from public.ordenes where id = ''{ord1}''','v:lista',null),
     (49,'mes_a2','select public.cambiar_estado_orden(''{ord1}'',''entregada'')::text','err:42501',null),
     (50,'mes_a1','select public.cambiar_estado_orden(''{ord1}'',''entregada'')::text','ok',null),
     (51,'mes_a1','select public.cambiar_estado_orden(''{ord1}'',''anulada'')::text','err:P0001',null),
     -- ---- mesero anula su orden recién enviada; cocina no
     (55,'mes_a1',$s$select public.crear_orden('mesa','7',null,'[{"producto_id":"{p_jugo}","cantidad":3}]')$s$,'ok','ord2'),
     (56,'coc_a','select public.cambiar_estado_orden(''{ord2}'',''anulada'')::text','err:P0001',null),
     (57,'mes_a1','select public.cambiar_estado_orden(''{ord2}'',''anulada'')::text','ok',null),
     -- ---- admin: todo dentro de su restaurante
     (60,'adm_a','select count(*) from public.ordenes where tienda_id = ''{A}''','n:2',null),
     (61,'adm_a','select count(*) from public.perfiles','n:5',null),
     (62,'adm_a','update public.productos set precio = 5500 where id = ''{p_arepa}''','ok',null),
     (63,'adm_a','insert into public.productos (nombre, precio, tienda_id) values (''Arepa 09p'', 1, ''{A}'')','err:23505',null),
     (64,'adm_a','insert into public.productos (nombre, precio, tienda_id) values (''Colado 09p'', 2500, ''{B}'')','deny',null),
     (65,'adm_a','delete from public.productos where id = ''{p_jugo}''','deny',null),
     (66,'adm_a','delete from public.ordenes where id = ''{ord1}''','deny',null),
     (67,'adm_a','select public.vincular_empleado(''nadie@no-existe.invalid'',''nuevo'',''mesero'')::text','err:22023',null),
     (68,'adm_a','select public.vincular_empleado(''nadie@no-existe.invalid'',''nuevo'',''admin'')::text','err:22023',null),
     (69,'adm_a','select public.set_empleado_activo(''{u_adm_a}''::uuid, false)::text','err:22023',null),
     (70,'adm_a','select public.set_empleado_activo(''{u_adm_b}''::uuid, false)::text','err:42501',null),
     -- ---- desactivar a un empleado le quita el acceso de inmediato
     (72,'adm_a','select public.set_empleado_activo(''{u_mes_a2}''::uuid, false)::text','ok',null),
     (73,'mes_a2',$s$select public.crear_orden('mostrador',null,null,'[{"producto_id":"{p_arepa}","cantidad":1}]')$s$,'err:42501',null),
     (74,'mes_a2','select count(*) from public.productos','n:0',null),
     (75,'adm_a','select public.set_empleado_activo(''{u_mes_a2}''::uuid, true)::text','ok',null),
     (76,'mes_a2','select count(*) from public.productos','n:3',null),
     -- ---- archivar: solo admin, solo su restaurante, solo lo terminado
     (80,'adm_a',$s$select public.crear_orden('mostrador',null,null,'[{"producto_id":"{p_arepa}","cantidad":1}]')$s$,'ok','ord3'),
     (81,'adm_a','select (r->>''ordenes'')||'',''||(r->>''ventas'') from (select public.archivar_historial() r) q','v:2,0',null),
     (82,'adm_a','select count(*) from public.ordenes where archivado_en is null','n:1',null),
     (83,'adm_a','select estado from public.ordenes where id = ''{ord3}''','v:enviada',null),
     (84,'adm_b','select (r->>''ordenes'')||'',''||(r->>''ventas'') from (select public.archivar_historial() r) q','v:0,0',null)
    ) x(n, quien, sql, espera, guarda) where quien <> 'cocina_no' order by n
  loop
    v_n := v_n + 1;
    -- sustituir marcadores {clave} y {u_alias}
    v_sql := t.sql;
    for v_res in select jsonb_object_keys(v) loop
      v_sql := replace(v_sql, '{' || v_res || '}', v ->> v_res);
    end loop;
    for v_res in select jsonb_object_keys(u) loop
      v_sql := replace(v_sql, '{u_' || v_res || '}', u ->> v_res);
    end loop;

    begin
      reset role;
      if t.quien = 'anon' then
        perform set_config('request.jwt.claims', '', true);
        perform set_config('request.jwt.claim.sub', '', true);
        set local role anon;
      else
        perform set_config('request.jwt.claims', json_build_object('sub',
            case when t.quien = 'sinperfil' then gen_random_uuid()::text else u ->> t.quien end,
            'role', 'authenticated')::text, true);
        perform set_config('request.jwt.claim.sub',
            case when t.quien = 'sinperfil' then gen_random_uuid()::text else u ->> t.quien end, true);
        set local role authenticated;
      end if;

      v_pass := false; v_err := null; v_st := null;
      if t.espera like 'n:%' or t.espera like 'v:%' or t.guarda is not null then
        execute v_sql into v_res;
        if t.guarda is not null then
          v := v || jsonb_build_object(t.guarda, v_res);
          v_pass := (t.espera = 'ok');
        elsif t.espera like 'n:%' then
          v_pass := (v_res = substr(t.espera, 3));
          if not v_pass then v_err := 'obtenido ' || coalesce(v_res, 'NULL'); end if;
        else
          v_pass := (v_res = substr(t.espera, 3));
          if not v_pass then v_err := 'obtenido ' || coalesce(v_res, 'NULL'); end if;
        end if;
      else
        execute v_sql;
        v_pass := (t.espera = 'ok');
        if not v_pass then v_err := 'se esperaba error y no hubo'; end if;
      end if;
    exception when others then
      v_st := sqlstate;
      v_pass := (t.espera = 'deny' and v_st in ('42501','42P01'))
             or (t.espera = 'err:' || v_st);
      if not v_pass then v_err := 'error ' || v_st || ' ' || left(sqlerrm, 120); end if;
    end;
    reset role;

    if v_pass then v_ok := v_ok + 1;
    else v_fail := v_fail || jsonb_build_array(jsonb_build_object('n', t.n, 'quien', t.quien, 'espera', t.espera, 'detalle', v_err));
    end if;
  end loop;

  perform set_config('pos.p09_ok', v_ok::text, false);
  perform set_config('pos.p09_fallos', v_fail::text, false);
  perform set_config('pos.p09_total', v_n::text, false);
exception when others then
  -- falla inesperada del arnés (no de una prueba): se registra y la fase 3 limpia igual
  reset role;
  perform set_config('pos.p09_ok', '0', false);
  perform set_config('pos.p09_total', '0', false);
  perform set_config('pos.p09_fallos', jsonb_build_array(jsonb_build_object('n', 0, 'detalle', 'ARNÉS: ' || sqlstate || ' ' || left(sqlerrm, 200)))::text, false);
end $f2$;
commit;

-- ============================== FASE 3: limpieza + verificación ==============================
begin;
set local session_replication_role = replica;   -- los ids falsos no existen en auth.users; sin esto el borrado de hijos/padres iría por FKs
do $f3$
begin
  -- solo filas con el prefijo reservado; hijos antes que padres
  delete from public.orden_items where tienda_id like 'ZZ\_09P\_%';
  delete from public.ordenes     where tienda_id like 'ZZ\_09P\_%';
  delete from public.ventas      where tienda_id like 'ZZ\_09P\_%';
  delete from public.productos   where tienda_id like 'ZZ\_09P\_%';
  delete from public.perfiles    where tienda_id like 'ZZ\_09P\_%';
  delete from public.auditoria   where tienda_id like 'ZZ\_09P\_%';
  delete from public.restaurantes where tienda_id like 'ZZ\_09P\_%';
  if (select count(*) from public.restaurantes where tienda_id like 'ZZ\_09P\_%')
   + (select count(*) from public.perfiles     where tienda_id like 'ZZ\_09P\_%')
   + (select count(*) from public.productos    where tienda_id like 'ZZ\_09P\_%')
   + (select count(*) from public.ordenes      where tienda_id like 'ZZ\_09P\_%')
   + (select count(*) from public.orden_items  where tienda_id like 'ZZ\_09P\_%')
   + (select count(*) from public.ventas       where tienda_id like 'ZZ\_09P\_%')
   + (select count(*) from public.auditoria    where tienda_id like 'ZZ\_09P\_%') > 0 then
    raise exception '09p: quedaron filas de prueba tras la limpieza';
  end if;
end $f3$;
commit;

-- ============================== RESULTADO ==============================
select current_setting('pos.p09_ok', true)                       as pruebas_ok,
       (current_setting('pos.p09_total', true)::int - current_setting('pos.p09_ok', true)::int) as pruebas_fallidas,
       current_setting('pos.p09_fallos', true)                   as detalle_fallos,
       (select count(*) from public.restaurantes where tienda_id like 'ZZ\_09P\_%') as sobras_restaurantes,
       (select count(*) from public.perfiles     where tienda_id like 'ZZ\_09P\_%') as sobras_perfiles,
       (select count(*) from public.productos    where tienda_id like 'ZZ\_09P\_%') as sobras_productos,
       (select count(*) from public.ordenes      where tienda_id like 'ZZ\_09P\_%') as sobras_ordenes,
       (select count(*) from public.orden_items  where tienda_id like 'ZZ\_09P\_%') as sobras_items,
       (select count(*) from public.ventas       where tienda_id like 'ZZ\_09P\_%') as sobras_ventas,
       (select count(*) from public.auditoria    where tienda_id like 'ZZ\_09P\_%') as sobras_auditoria;
