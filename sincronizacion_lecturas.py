"""Intercambia precios confirmados entre el lector y la web, sin capturas."""
import json
import re
from contextlib import closing
from datetime import datetime, timedelta, timezone

from almacenamiento import conectar_base
from mercancias import calidad_mercado
from precios_api import CIUDADES_API

RUTA_ENVIO_LECTOR = '/api/lector/sincronizar-v2'
PROTOCOLO_LECTOR = 1
MAX_LECTURAS = 200
MAX_BYTES_LECTOR = 96 * 1024
_ID = re.compile(r'[A-Z0-9_]+(?:@[1-4])?')


def _fecha(fecha):
    if not isinstance(fecha, str) or not 20 <= len(fecha) <= 40:
        return None
    try:
        f = datetime.fromisoformat(fecha.replace('Z', '+00:00'))
        return f.astimezone(timezone.utc) if f.tzinfo and f.year >= 2000 else None
    except (ValueError, OverflowError):
        return None


def _precio(valor):
    if valor is None or (type(valor) is int and valor == 0):
        return None
    if type(valor) is not int or not 0 < valor <= 10**12:
        raise ValueError('Precio inválido')
    return valor


def _lectura(fila, catalogo, ahora):
    if not isinstance(fila, list) or len(fila) != 6:
        raise ValueError('Formato de lectura inválido')
    item, ciudad, calidad, venta, compra, fecha = fila
    if not isinstance(item, str) or len(item) > 160 or not _ID.fullmatch(item) or item not in catalogo:
        raise ValueError('Objeto fuera del catálogo de la web')
    if ciudad not in CIUDADES_API:
        raise ValueError('Ciudad no reconocida')
    if type(calidad) is not int or not 1 <= calidad <= 5:
        raise ValueError('Calidad inválida')
    f = _fecha(fecha)
    if f is None or f > ahora + timedelta(minutes=5):
        raise ValueError('Fecha inválida o reloj adelantado')
    venta, compra = _precio(venta), _precio(compra)
    if venta is None and compra is None:
        raise ValueError('Sin precio de compra ni de venta')
    return item, ciudad, calidad_mercado(item, calidad), venta, compra, f


def recibir_lecturas(db, catalogo, datos, abrir, ahora=None):
    """Acepta las filas válidas y devuelve las rechazadas por posición."""
    if not isinstance(datos, dict) or type(datos.get('version')) is not int or datos['version'] != PROTOCOLO_LECTOR:
        raise ValueError('Formato de sincronización del lector incompatible. Actualiza a V68.')
    filas = datos.get('lecturas')
    if not isinstance(filas, list) or not 1 <= len(filas) <= MAX_LECTURAS:
        raise ValueError(f'Envía entre 1 y {MAX_LECTURAS} lecturas confirmadas.')
    ahora = ahora or datetime.now(timezone.utc)
    rechazadas, validas = [], []
    for i, fila in enumerate(filas):
        try:
            validas.append(_lectura(fila, catalogo, ahora))
        except ValueError as e:
            rechazadas.append({'indice': i, 'motivo': str(e)})
    actualizadas, mas_reciente = 0, None
    if validas:
        with closing(abrir(db)) as con, con:
            con.execute('BEGIN IMMEDIATE')
            for item, ciudad, calidad, venta, compra, fecha in validas:
                clave = item, ciudad, calidad
                anterior = con.execute('SELECT fecha FROM precios_lector WHERE item_id=? AND ciudad=? AND calidad=?', clave).fetchone()
                f = _fecha(anterior[0]) if anterior else None
                if f is not None and f >= fecha:
                    continue
                con.execute('''INSERT INTO precios_lector (item_id,ciudad,calidad,venta,compra,fecha,metodo)
                    VALUES (?,?,?,?,?,?,'sincronizado')
                    ON CONFLICT(item_id,ciudad,calidad) DO UPDATE SET venta=excluded.venta,
                    compra=excluded.compra,fecha=excluded.fecha,metodo=excluded.metodo''',
                    (*clave, venta, compra, fecha.isoformat()))
                actualizadas += 1
                if mas_reciente is None or mas_reciente[0] < fecha:
                    mas_reciente = (fecha, item, ciudad, calidad, venta, compra)
            if mas_reciente:
                fecha, item, ciudad, calidad, venta, compra = mas_reciente
                anterior = con.execute('SELECT datos FROM estado_lector WHERE id=1').fetchone()
                previa = None
                if anterior:
                    try:
                        previa = _fecha(json.loads(anterior[0]).get('fecha'))
                    except (ValueError, TypeError, AttributeError):
                        pass
                if previa is None or previa < fecha:
                    estado = dict(item_id=item, ciudad=ciudad, calidad=calidad, venta=venta, compra=compra,
                                  fecha=fecha.isoformat(), recibida=ahora.isoformat(), estado='guardado')
                    con.execute('INSERT OR REPLACE INTO estado_lector VALUES (1,?)', (json.dumps(estado),))
    return {'version': PROTOCOLO_LECTOR, 'recibidas': len(filas), 'aceptadas': len(validas),
            'actualizadas': actualizadas, 'rechazadas': rechazadas}


def _tablas(con):
    con.execute('''CREATE TABLE IF NOT EXISTS sincronizacion_lector_envios (
        item_id TEXT NOT NULL, ciudad TEXT NOT NULL, calidad INTEGER NOT NULL,
        venta, compra, fecha TEXT NOT NULL, motivo TEXT,
        PRIMARY KEY (item_id,ciudad,calidad)) WITHOUT ROWID''')
    con.execute('CREATE TABLE IF NOT EXISTS sincronizacion_lector_destino (id INTEGER PRIMARY KEY, url TEXT NOT NULL)')


def pendientes_lector(db, destino, *, reenviar=False):
    if not db.is_file():
        return [], (0, None)
    with closing(conectar_base(db)) as con, con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='precios_lector'").fetchone():
            return [], (0, None)
        existe_destino = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sincronizacion_lector_destino'").fetchone()
        if reenviar or not existe_destino or con.execute('SELECT url FROM sincronizacion_lector_destino WHERE id=1').fetchone() != (destino,):
            con.execute('BEGIN IMMEDIATE')
            _tablas(con)
            con.execute('DELETE FROM sincronizacion_lector_envios')
            con.execute('INSERT OR REPLACE INTO sincronizacion_lector_destino VALUES (1,?)', (destino,))
        filas = con.execute('''SELECT p.item_id,p.ciudad,p.calidad,p.venta,p.compra,p.fecha
            FROM precios_lector p LEFT JOIN sincronizacion_lector_envios e USING (item_id,ciudad,calidad)
            WHERE e.item_id IS NULL OR p.venta IS NOT e.venta OR p.compra IS NOT e.compra OR p.fecha IS NOT e.fecha
            ORDER BY p.item_id,p.ciudad,p.calidad LIMIT ?''', (MAX_LECTURAS,)).fetchall()
        rechazadas = con.execute('''SELECT count(*),min(e.motivo) FROM sincronizacion_lector_envios e
            JOIN precios_lector p USING (item_id,ciudad,calidad)
            WHERE e.motivo IS NOT NULL AND p.venta IS e.venta AND p.compra IS e.compra AND p.fecha IS e.fecha''').fetchone()
        return filas, rechazadas


def confirmar_lecturas(db, destino, filas, rechazadas):
    """Registra el resultado por versión de la fila; un cambio local queda pendiente."""
    with closing(conectar_base(db)) as con, con:
        con.execute('BEGIN IMMEDIATE')
        if con.execute('SELECT url FROM sincronizacion_lector_destino WHERE id=1').fetchone() == (destino,):
            con.executemany('INSERT OR REPLACE INTO sincronizacion_lector_envios VALUES (?,?,?,?,?,?,?)',
                            ((*fila, rechazadas.get(i)) for i, fila in enumerate(filas)))
