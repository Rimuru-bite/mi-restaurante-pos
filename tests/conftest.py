"""Fixtures: crea una base temporal a partir de una base ya migrada (db/01..08) y datos ficticios."""
import os
import subprocess

import pytest

from tests.fake_supabase import Conn, FakeClient, lit

HOST, PORT, USER = os.getenv("POS_PG_HOST", "127.0.0.1"), os.getenv("POS_PG_PORT", "5544"), os.getenv("POS_PG_USER", "postgres")
TEMPLATE = os.getenv("POS_TEST_TEMPLATE", "d1")     # base con las migraciones 01-08 aplicadas
DB = "pos_pytest"

U = {k: f"00000000-0000-0000-0000-0000000000{n:02d}" for n, k in enumerate(["a1", "a2", "a2b", "a3", "b1", "b2", "c1"], start=10)}
CLAVE = "clave-ficticia-123"


def _psql(db, sql):
    return subprocess.run(["psql", "-h", HOST, "-p", PORT, "-U", USER, "-d", db, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-c", sql],
                          capture_output=True, text=True)


@pytest.fixture(scope="session")
def conn():
    r = _psql("postgres", f"drop database if exists {DB}")
    if r.returncode != 0:
        pytest.skip(f"No hay Postgres de pruebas disponible: {r.stderr.strip()[:120]}")
    assert _psql("postgres", f"create database {DB} template {TEMPLATE}").returncode == 0
    c = Conn(DB, HOST, PORT, USER)
    c.admin("create extension if not exists pgcrypto;")
    usuarios = [("a1", "admin", "admin", "TEST_A"), ("a2", "ana", "mesero", "TEST_A"), ("a2b", "luis", "mesero", "TEST_A"),
                ("a3", "cocina_a", "cocina", "TEST_A"), ("b1", "admin", "admin", "TEST_B"), ("b2", "bea", "mesero", "TEST_B"),
                ("c1", None, None, None)]
    sql = "insert into public.restaurantes (tienda_id, nombre) values ('TEST_A','Restaurante A'), ('TEST_B','Restaurante B');\n"
    for k, nombre, rol, tienda in usuarios:
        sql += (f"insert into auth.users (id, aud, role, email, encrypted_password) values "
                f"({lit(U[k])}, 'authenticated','authenticated', '{k}@test.invalid', crypt('{CLAVE}', gen_salt('bf')));\n")
        if rol:
            sql += f"insert into public.perfiles (id, usuario, rol, tienda_id) values ({lit(U[k])}, {lit(nombre)}, {lit(rol)}, {lit(tienda)});\n"
    sql += ("insert into public.productos (nombre, precio, tienda_id) values ('Hamburguesa',2500,'TEST_A'),('Gaseosa',1500,'TEST_A'),('Hamburguesa',9000,'TEST_B');\n"
            "insert into auth.users (id, aud, role, email, encrypted_password) values ('00000000-0000-0000-0000-0000000000e1','authenticated','authenticated','nuevo@test.invalid', crypt('x', gen_salt('bf')));\n")
    c.admin(sql)
    yield c
    _psql("postgres", f"drop database if exists {DB}")


@pytest.fixture
def entrar(conn):
    from pos.data import Repo

    def _entrar(clave_usuario):
        repo = Repo(FakeClient(conn))
        repo.login(f"{clave_usuario}@test.invalid", CLAVE)
        return repo
    return _entrar
