"""Recepción autenticada e idempotente de precios confirmados del PC."""
import os
from datetime import datetime, timezone, timedelta
from contextlib import closing
from precios_guardados import abrir, CIUDADES_LECTOR, _estado


def clave_configurada():
    clave = os.environ.get('BENJAYAYE_SYNC_KEY', '')
    return clave if len(clave) >= 32 and clave.isascii() else None


def validar_lote(datos, catalogo):
    filas = datos.get('precios') if isinstance(datos, dict) else None
    if not isinstance(filas, list) or not 1 <= len(filas) <= 100:
        raise ValueError('Envía entre 1 y 100 precios')
    salida = []
    for fila in filas:
        if not isinstance(fila, dict):
            raise ValueError('Precio inválido')
        id, ciudad, calidad = (fila.get(c) for c in ('item_id', 'ciudad', 'calidad'))
        if not isinstance(id, str) or id not in catalogo or ciudad not in CIUDADES_LECTOR or type(calidad) is not int or not 1 <= calidad <= 5:
            raise ValueError('Objeto, ciudad o calidad inválidos')
        precios = [fila.get(c) for c in ('venta', 'compra')]
        if any(p is not None and (type(p) is not int or not 0 <= p <= 10**12) for p in precios):
            raise ValueError('Precio fuera de rango')
        # Cero representa ausencia de oferta; nunca una oferta gratuita.
        venta, compra = (p if p else None for p in precios)
        if not isinstance(fila.get('fecha'), str):
            raise ValueError('Falta la fecha de lectura')
        try:
            fecha = datetime.fromisoformat(fila['fecha'])
            if fecha.tzinfo is None or fecha.year < 2000 or fecha > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('Fecha de lectura inválida') from None
        metodo = 'automatico' if fila.get('metodo') == 'automatico' else 'confirmado'
        salida.append((id, ciudad, calidad, venta, compra, fecha.astimezone(timezone.utc).isoformat(), metodo))
    return salida


def recibir(db, catalogo, datos):
    filas = validar_lote(datos, catalogo)  # Validación completa antes de escribir.
    cambios = 0
    ultima = None
    with closing(abrir(db)) as con, con:
        con.execute('BEGIN IMMEDIATE')
        for fila in filas:
            anterior = con.execute('SELECT fecha FROM precios_lector WHERE item_id=? AND ciudad=? AND calidad=?', fila[:3]).fetchone()
            if anterior and datetime.fromisoformat(anterior[0]) >= datetime.fromisoformat(fila[5]):
                continue
            con.execute('INSERT INTO precios_lector VALUES (?,?,?,?,?,?,?) ON CONFLICT(item_id,ciudad,calidad) DO UPDATE SET venta=excluded.venta,compra=excluded.compra,fecha=excluded.fecha,metodo=excluded.metodo', fila)
            con.execute('INSERT INTO historial_lector(item_id,ciudad,calidad,venta,compra,fecha,metodo) VALUES (?,?,?,?,?,?,?)', fila)
            cambios += 1
            if ultima is None or fila[5] > ultima[5]:
                ultima = fila
        if ultima:
            _estado(con, dict(zip(('item_id','ciudad','calidad','venta','compra','fecha','metodo'), ultima)), 'guardado')
    return {'ok': True, 'recibidos': len(filas), 'actualizados': cambios}
