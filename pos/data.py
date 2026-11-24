"""Acceso a datos. Todo pasa por un cliente de Supabase POR SESIÓN, autenticado como el usuario:
la seguridad real (RLS y funciones) vive en la base de datos, no aquí."""


class ErrorApp(Exception):
    """Error con mensaje apto para mostrar al usuario."""


def _mensaje(e: Exception) -> str:
    return str(getattr(e, "message", None) or e)


class Repo:
    def __init__(self, client):
        self.c = client
        self.perfil: dict | None = None

    # ---------- infraestructura ----------
    def _run(self, fn):
        try:
            return fn()
        except Exception as e:
            if "jwt expired" in _mensaje(e).lower():       # sesión vencida: renovar una vez y reintentar
                try:
                    self.c.auth.refresh_session()
                    return fn()
                except Exception as e2:
                    raise ErrorApp("Tu sesión venció. Vuelve a iniciar sesión.") from e2
            raise ErrorApp(_mensaje(e)) from e

    def _tabla(self, nombre, q):
        return self._run(lambda: q(self.c.table(nombre)).execute().data)

    def _rpc(self, nombre, params=None):
        return self._run(lambda: self.c.rpc(nombre, params or {}).execute().data)

    # ---------- sesión ----------
    def login(self, email: str, password: str) -> dict:
        try:
            r = self.c.auth.sign_in_with_password({"email": (email or "").strip(), "password": password or ""})
            uid = r.user.id
        except Exception as e:
            raise ErrorApp("Correo o clave incorrectos.") from e
        filas = self._tabla("perfiles", lambda t: t.select("id, usuario, rol, tienda_id, activo").eq("id", uid))
        if not filas or not filas[0]["activo"]:
            self.logout()
            raise ErrorApp("Tu cuenta no tiene acceso a ningún restaurante. Pide al dueño que te vincule o te reactive.")
        p = filas[0]
        r_t = self._tabla("restaurantes", lambda t: t.select("nombre").eq("tienda_id", p["tienda_id"]))
        p["tienda_nombre"] = r_t[0]["nombre"] if r_t else p["tienda_id"]
        self.perfil = p
        return p

    def logout(self):
        try:
            self.c.auth.sign_out()
        except Exception:
            pass
        self.perfil = None

    # ---------- menú ----------
    def productos(self, solo_activos=True) -> list[dict]:
        def q(t):
            s = t.select("id, nombre, precio, activo")
            return (s.eq("activo", True) if solo_activos else s).order("nombre")
        return self._tabla("productos", q)

    def crear_producto(self, nombre: str, precio: int):
        nombre = (nombre or "").strip()
        if not nombre:
            raise ErrorApp("El producto necesita un nombre.")
        if precio is None or int(precio) < 0:
            raise ErrorApp("El precio no puede ser negativo.")
        return self._tabla("productos", lambda t: t.insert({"nombre": nombre, "precio": int(precio), "tienda_id": self.perfil["tienda_id"], "activo": True}))

    def editar_producto(self, producto_id: str, precio: int | None = None, activo: bool | None = None):
        cambios = {}
        if precio is not None:
            if int(precio) < 0:
                raise ErrorApp("El precio no puede ser negativo.")
            cambios["precio"] = int(precio)
        if activo is not None:
            cambios["activo"] = bool(activo)
        if not cambios:
            return []
        filas = self._tabla("productos", lambda t: t.update(cambios).eq("id", producto_id))
        if not filas:
            raise ErrorApp("No se pudo modificar el producto.")
        return filas

    # ---------- órdenes ----------
    def crear_orden(self, tipo: str, mesa: str | None, notas: str | None, items: list[dict]) -> str:
        """items: [{"producto_id", "cantidad", "nota"}]. El precio lo pone la base de datos."""
        payload = [{"producto_id": i["producto_id"], "cantidad": int(i["cantidad"]), "nota": i.get("nota") or None} for i in items]
        return self._rpc("crear_orden", {"p_tipo": tipo, "p_mesa": mesa, "p_notas": notas, "p_items": payload})

    def cambiar_estado(self, orden_id: str, estado: str):
        self._rpc("cambiar_estado_orden", {"p_id": orden_id, "p_estado": estado})

    def tablero_cocina(self) -> list[dict]:
        return self._rpc("tablero_cocina") or []

    def ordenes(self, desde=None, hasta=None, incluir_archivados=False, con_items=True) -> list[dict]:
        def q(t):
            s = t.select("*")
            if desde is not None:
                s = s.gte("creado_en", desde.isoformat())
            if hasta is not None:
                s = s.lt("creado_en", hasta.isoformat())
            if not incluir_archivados:
                s = s.is_("archivado_en", "null")
            return s.order("creado_en", desc=True)
        filas = self._tabla("ordenes", q)
        if con_items and filas:
            ids = [f["id"] for f in filas]
            items = self._tabla("orden_items", lambda t: t.select("orden_id, linea, producto, precio, cantidad, nota").in_("orden_id", ids).order("linea"))
            por_orden: dict[str, list] = {}
            for it in items:
                por_orden.setdefault(it["orden_id"], []).append(it)
            for f in filas:
                f["items"] = por_orden.get(f["id"], [])
        return filas

    # ---------- ventas rápidas (compatibilidad con la versión anterior) ----------
    def venta_rapida(self, producto: str, precio: int, cantidad: int):
        if int(cantidad) < 1:
            raise ErrorApp("La cantidad debe ser al menos 1.")
        return self._tabla("ventas", lambda t: t.insert({
            "producto": producto, "precio": int(precio), "cantidad": int(cantidad),
            "total": int(precio) * int(cantidad), "vendedor": self.perfil["usuario"], "tienda_id": self.perfil["tienda_id"]}))

    def ventas(self, desde=None, hasta=None, incluir_archivados=False) -> list[dict]:
        def q(t):
            s = t.select("*")
            if desde is not None:
                s = s.gte("creado_en", desde.isoformat())
            if hasta is not None:
                s = s.lt("creado_en", hasta.isoformat())
            if not incluir_archivados:
                s = s.is_("archivado_en", "null")
            return s.order("creado_en", desc=True)
        return self._tabla("ventas", q)

    def archivar_historial(self) -> dict:
        return self._rpc("archivar_historial")

    # ---------- equipo y auditoría (solo dueño) ----------
    def empleados(self) -> list[dict]:
        return self._tabla("perfiles", lambda t: t.select("id, usuario, rol, activo, creado_en").order("creado_en"))

    def vincular_empleado(self, email: str, usuario: str, rol: str) -> str:
        return self._rpc("vincular_empleado", {"p_email": email, "p_usuario": usuario, "p_rol": rol})

    def set_empleado_activo(self, empleado_id: str, activo: bool):
        self._rpc("set_empleado_activo", {"p_id": empleado_id, "p_activo": bool(activo)})

    def auditoria(self, limite=200) -> list[dict]:
        return self._tabla("auditoria", lambda t: t.select("creado_en, usuario, accion, tabla, detalle").order("creado_en", desc=True).limit(limite))
