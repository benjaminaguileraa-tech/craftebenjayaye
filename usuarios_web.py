"""Espacios privados por navegador, aislados en cada solicitud HTTP."""
import os
import re
import secrets
from contextvars import ContextVar
from functools import wraps
from hashlib import sha256
from http.cookies import SimpleCookie, CookieError
from urllib.parse import urlsplit
from threading import RLock

# Serializa cada espacio privado sin mantener un registro ilimitado de visitantes.
CERROJOS = tuple(RLock() for _ in range(64))

COOKIE = 'benjayaye_visitante'
VISITANTE = ContextVar('visitante_web', default=None)
TOKEN_VALIDO = re.compile(r'^[A-Za-z0-9_-]{43}$')


def ruta_privada(base_compartida):
    visitante = VISITANTE.get()
    # Las operaciones locales sin petición HTTP conservan su base original.
    if visitante is None:
        return base_compartida
    nombre = sha256(visitante.encode('ascii')).hexdigest()
    return base_compartida.parent / 'usuarios' / (nombre + '.sqlite3')


def ruta_personal(ruta):
    return ruta == '/api/precios' or ruta == '/api/plan' or ruta.startswith('/api/plan/') or ruta == '/api/respaldo' or ruta.startswith('/api/respaldo/')


def leer_visitante(cabecera):
    cookies = SimpleCookie()
    try:
        cookies.load(cabecera)
        valor = cookies.get(COOKIE)
        if valor and TOKEN_VALIDO.fullmatch(valor.value):
            return valor.value
    except (CookieError, ValueError):
        pass
    return None


def espacio_privado(metodo):
    @wraps(metodo)
    def ejecutar(self, *args, **kwargs):
        ruta = urlsplit(self.path).path
        self._cookie_visitante_nueva = None
        self._respuesta_personal = ruta_personal(ruta) or ruta == '/'
        visitante = None
        if self._respuesta_personal:
            visitante = leer_visitante(self.headers.get('Cookie', ''))
            if self.command not in ('GET', 'HEAD'):
                origen = self.headers.get('Origin')
                externo = self.headers.get('Sec-Fetch-Site') == 'cross-site'
                if externo or (origen and urlsplit(origen).netloc != self.headers.get('Host', '')):
                    self._json(403, {'error': 'Abre la calculadora directamente para modificar tus datos.'})
                    return
                if not visitante:
                    self._json(428, {'error': 'Recarga la página y permite sus cookies para guardar tus crafteos privados.'})
                    return
            if not visitante:
                visitante = secrets.token_urlsafe(32)
                self._cookie_visitante_nueva = visitante
        contexto = VISITANTE.set(visitante)
        try:
            if visitante and ruta_personal(ruta):
                with CERROJOS[int(sha256(visitante.encode()).hexdigest(), 16) % len(CERROJOS)]:
                    esperada = self.headers.get('X-Craft-Generation')
                    if esperada and self.command not in ('GET', 'HEAD') and esperada != self._generacion_privada():
                        self._json(409, {'error': 'El servidor se reinició. Actualiza la lista para recuperar tu copia antes de continuar.'})
                        return
                    return metodo(self, *args, **kwargs)
            return metodo(self, *args, **kwargs)
        finally:
            VISITANTE.reset(contexto)
    return ejecutar


def cabeceras_privadas(handler):
    if getattr(handler, '_respuesta_personal', False):
        handler.send_header('Cache-Control', 'private, no-store')
        handler.send_header('Vary', 'Cookie')
    token = getattr(handler, '_cookie_visitante_nueva', None)
    if token:
        seguro = os.environ.get('RENDER', '').lower() == 'true' or handler.headers.get('X-Forwarded-Proto', '').split(',')[0].strip() == 'https'
        cookie = COOKIE + '=' + token + '; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax'
        if seguro:
            cookie += '; Secure'
        handler.send_header('Set-Cookie', cookie)
        handler._cookie_visitante_nueva = None
