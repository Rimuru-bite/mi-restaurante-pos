-- SOLO EMERGENCIA, y solo después del corte (08). Devuelve el acceso que tenía la app anterior.
-- Deja la base ABIERTA como estaba al inicio: úsalo de forma temporal mientras se corrige el problema.
begin;
alter table public.usuarios     disable row level security;
alter table public.ventas       disable row level security;
alter table public.productos    disable row level security;
alter table public.restaurantes disable row level security;
grant all on public.usuarios, public.ventas, public.productos to anon, authenticated;
grant all on all sequences in schema public to anon, authenticated;
commit;
