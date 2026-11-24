-- Si se dañaron datos: restaura desde el respaldo interno (bloque 01). Revisa antes el contenido de las tablas destino.
-- No sobrescribe: solo agrega filas que no existan.
begin;

insert into public.productos (nombre, precio, tienda_id)
select b.nombre, b.precio, b.tienda_id
from respaldo.productos_20261123 b
where not exists (
  select 1 from public.productos p where p.tienda_id = b.tienda_id and p.nombre = b.nombre
);

insert into public.ventas (id, producto, precio, cantidad, vendedor, total, tienda_id)
select b.id, b.producto, b.precio, b.cantidad, b.vendedor, b.total, b.tienda_id
from respaldo.ventas_20261123 b
where not exists (select 1 from public.ventas v where v.id = b.id);

commit;
