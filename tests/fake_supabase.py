"""Cliente falso con la misma interfaz que usa pos/data.py (supabase-py), respaldado por un Postgres local.
Cada consulta corre en su propia transacción con el rol `authenticated` y el JWT del usuario, igual que PostgREST,
así las políticas RLS y los permisos de la base se aplican de verdad. NO reemplaza una prueba contra Supabase real."""
import json
import re
import subprocess
from datetime import date, datetime
from types import SimpleNamespace

TABLE_FUNCS = {"tablero_cocina"}
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


class FakeAPIError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.message, self.code = message, code


def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (datetime, date)):
        return "'" + v.isoformat() + "'"
    if isinstance(v, (dict, list)):
        return "'" + json.dumps(v).replace("'", "''") + "'::jsonb"
    return "'" + str(v).replace("'", "''") + "'"


def ident(x):
    if not _IDENT.match(x):
        raise ValueError(f"identificador no permitido: {x}")
    return x


class Conn:
    def __init__(self, db, host="127.0.0.1", port="5544", user="postgres"):
        self.args = ["psql", "-h", host, "-p", str(port), "-U", user, "-d", db, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose"]

    def run(self, sql, uid=None):
        pre = "begin;\n"
        if uid:
            claims = json.dumps({"sub": uid, "role": "authenticated"}).replace("'", "''")
            pre += f"select set_config('request.jwt.claims','{claims}',true), set_config('request.jwt.claim.sub','{uid}',true);\nset local role authenticated;\n"
        else:
            pre += "set local role anon;\n"
        p = subprocess.run(self.args, input=pre + sql + ";\ncommit;\n", capture_output=True, text=True)
        if p.returncode != 0:
            m = re.search(r"ERROR:\s+(\w{5}):\s+(.*)", p.stderr)
            raise FakeAPIError(m.group(2).strip() if m else p.stderr.strip(), m.group(1) if m else None)
        lines = [l for l in p.stdout.splitlines() if l and l not in ("BEGIN", "COMMIT", "SET")]
        texto = "\n".join(l for l in lines if not l.startswith("set_config") and "|" not in l[:3] or l.startswith(("[", "{")))
        # El resultado es la última sentencia que devuelve JSON (las anteriores son set_config)
        for i in range(len(lines)):
            try:
                return json.loads("\n".join(lines[i:]))
            except ValueError:
                continue
        return []

    def admin(self, sql):
        p = subprocess.run(self.args, input=sql, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(p.stderr)
        return p.stdout


class Resp:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, client, tabla):
        self.cl, self.t = client, ident(tabla)
        self.cols, self.where, self.order_by, self.lim, self.op, self.payload = "*", [], None, None, "select", None

    def select(self, cols="*"):
        if "(" in cols:
            raise NotImplementedError("embeds no soportados en el cliente falso")
        self.cols = cols
        return self

    def insert(self, row):
        self.op, self.payload = "insert", row
        return self

    def update(self, row):
        self.op, self.payload = "update", row
        return self

    def eq(self, c, v):
        self.where.append(f"{ident(c)} = {lit(v)}")
        return self

    def gte(self, c, v):
        self.where.append(f"{ident(c)} >= {lit(v)}")
        return self

    def lt(self, c, v):
        self.where.append(f"{ident(c)} < {lit(v)}")
        return self

    def is_(self, c, v):
        assert v == "null"
        self.where.append(f"{ident(c)} is null")
        return self

    def in_(self, c, vals):
        self.where.append(f"{ident(c)} in ({', '.join(lit(v) for v in vals)})" if vals else "false")
        return self

    def order(self, c, desc=False):
        self.order_by = f"{ident(c)} {'desc' if desc else 'asc'}"
        return self

    def limit(self, n):
        self.lim = int(n)
        return self

    def execute(self):
        w = (" where " + " and ".join(self.where)) if self.where else ""
        if self.op == "select":
            cols = ", ".join(ident(c.strip()) for c in self.cols.split(",")) if self.cols != "*" else "*"
            q = f"select {cols} from public.{self.t}{w}" + (f" order by {self.order_by}" if self.order_by else "") + (f" limit {self.lim}" if self.lim else "")
            sql = f"select coalesce(jsonb_agg(t), '[]'::jsonb) from ({q}) t"
        elif self.op == "insert":
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            cols = list(rows[0].keys())
            vals = ", ".join("(" + ", ".join(lit(r[c]) for c in cols) + ")" for r in rows)
            sql = f"with r as (insert into public.{self.t} ({', '.join(ident(c) for c in cols)}) values {vals} returning *) select coalesce(jsonb_agg(r), '[]'::jsonb) from r"
        else:
            sets = ", ".join(f"{ident(k)} = {lit(v)}" for k, v in self.payload.items())
            sql = f"with r as (update public.{self.t} set {sets}{w} returning *) select coalesce(jsonb_agg(r), '[]'::jsonb) from r"
        return Resp(self.cl.conn.run(sql, self.cl.uid))


class Rpc:
    def __init__(self, client, fn, params):
        self.cl, self.fn, self.params = client, ident(fn), params

    def execute(self):
        args = ", ".join(f"{ident(k)} => {lit(v)}" + ("::jsonb" if isinstance(v, (list, dict)) else "") for k, v in self.params.items())
        if self.fn in TABLE_FUNCS:
            sql = f"select coalesce(jsonb_agg(t), '[]'::jsonb) from public.{self.fn}({args}) t"
        else:
            sql = f"select to_jsonb(public.{self.fn}({args}))"
        return Resp(self.cl.conn.run(sql, self.cl.uid))


class Auth:
    def __init__(self, client):
        self.cl = client

    def sign_in_with_password(self, cred):
        r = self.cl.conn.admin(
            f"select id from auth.users where lower(email) = lower({lit(cred['email'])}) "
            f"and encrypted_password = crypt({lit(cred['password'])}, encrypted_password)").strip()
        if not r:
            raise FakeAPIError("Invalid login credentials", "invalid_credentials")
        self.cl.uid = r
        return SimpleNamespace(user=SimpleNamespace(id=r), session=SimpleNamespace(access_token="fake"))

    def sign_out(self):
        self.cl.uid = None

    def refresh_session(self):
        if not self.cl.uid:
            raise FakeAPIError("no session")


class FakeClient:
    def __init__(self, conn):
        self.conn, self.uid = conn, None
        self.auth = Auth(self)

    def table(self, nombre):
        return Query(self, nombre)

    def rpc(self, fn, params=None):
        return Rpc(self, fn, params or {})
