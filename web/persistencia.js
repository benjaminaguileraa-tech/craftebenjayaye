"use strict";

// Copia privada por origen y perfil de navegador. No contiene datos del lector.
(() => {
  const CLAVE = 'benjayaye-respaldo-privado-v1';
  const original = window.fetch.bind(window);
  let cola = Promise.resolve(), memoria = null;
  function aviso(texto) {
    const nodo = document.getElementById('estado-persistencia');
    if (nodo) nodo.textContent = texto;
  }
  function leer() {
    const texto = localStorage.getItem(CLAVE);
    if (!texto) return null;
    const copia = JSON.parse(texto);
    if (copia.formato !== 'benjayaye-craft-calculadora' || !Array.isArray(copia.lotes) || !copia.generacion)
      throw new Error('La copia local no es válida. Descárgala antes de reemplazarla.');
    return copia;
  }
  function guardar(copia) {
    memoria = copia;
    try {
      const anterior = leer();
      if (anterior?.generacion === copia.generacion && anterior.revision > copia.revision) { memoria = null; return; }
      localStorage.setItem(CLAVE, JSON.stringify(copia));
      memoria = null;
      aviso(`Copia automática guardada en este navegador · ${copia.lotes.length} lotes. Puedes cerrar la página.`);
    } catch (error) {
      aviso('No se pudo guardar la copia en el navegador. Descarga el respaldo JSON antes de cerrar: ' + error.message);
      throw error;
    }
  }
  async function pedir(url, opciones = {}) {
    const controlador = new AbortController();
    const cancelar = () => controlador.abort();
    opciones.signal?.addEventListener('abort', cancelar, {once:true});
    if (opciones.signal?.aborted) cancelar();
    const limite = setTimeout(cancelar, 25000);
    try { return await original(url, {...opciones, signal:controlador.signal, cache:'no-store'}); }
    finally { clearTimeout(limite); opciones.signal?.removeEventListener('abort', cancelar); }
  }
  async function jsonCorrecto(respuesta) {
    const datos = await respuesta.json();
    if (!respuesta.ok) throw new Error(datos.error || 'El servidor no está disponible. Tu copia local se conserva.');
    return datos;
  }
  async function asegurar() {
    // Leer antes de contactar: un error de almacenamiento no debe borrar la copia.
    const local = leer();
    let remoto = await jsonCorrecto(await pedir('/api/respaldo'));
    if (!remoto.generacion) throw new Error('Actualiza también app.py y usuarios_web.py para activar el guardado automático.');
    if (local && local.generacion !== remoto.generacion) {
      if (remoto.lotes.length || Object.keys(remoto.precios).length || Object.keys(remoto.compras || {}).length)
        throw new Error('Hay datos distintos en el servidor. Tu copia local está protegida: descarga el respaldo JSON antes de combinarlos.');
      aviso('Recuperando tus crafteos desde la copia de este navegador…');
      const restaurado = await jsonCorrecto(await pedir('/api/respaldo/recuperar', {
        method:'POST', headers:{'Content-Type':'application/json','X-Craft-Generation':remoto.generacion}, body:JSON.stringify(local)
      }));
      remoto = restaurado._respaldo;
    }
    guardar(remoto);
    return remoto;
  }
  async function ejecutar(url, opciones) {
    const copia = await asegurar();
    const headers = new Headers(opciones.headers || {});
    headers.set('X-Craft-Generation', copia.generacion);
    const respuesta = await pedir(url, {...opciones, headers});
    if (respuesta.ok && respuesta.headers.get('Content-Type')?.includes('application/json')) {
      const datos = await respuesta.clone().json();
      if (datos._respaldo) guardar(datos._respaldo);
    }
    return respuesta;
  }
  window.fetch = (url, opciones = {}) => {
    const destino = new URL(typeof url === 'string' ? url : url.url, location.href);
    const metodo = (opciones.method || url.method || 'GET').toUpperCase();
    const ruta = destino.pathname;
    const personal = ruta === '/api/plan' || ruta.startsWith('/api/plan/') ||
      ruta === '/api/respaldo/importar' || (ruta === '/api/precios' && metodo !== 'GET');
    if (destino.origin !== location.origin || !personal) return original(url, opciones);
    const tarea = () => navigator.locks
      ? navigator.locks.request('benjayaye-crafteos', () => ejecutar(url, opciones))
      : ejecutar(url, opciones);
    const resultado = cola.then(tarea);
    cola = resultado.catch(error => aviso('Copia local conservada. ' + error.message));
    return resultado;
  };
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('descargar-respaldo-local')?.addEventListener('click', evento => {
      // Disponible incluso si el servidor está desconectado.
      let texto;
      try { texto = memoria ? JSON.stringify(memoria, null, 2) : localStorage.getItem(CLAVE); }
      catch (_) { return; }
      if (!texto) return;
      evento.preventDefault();
      const enlace = document.createElement('a');
      enlace.href = URL.createObjectURL(new Blob([texto], {type:'application/json'}));
      enlace.download = 'benjayaye-mis-crafteos.json'; enlace.click();
      setTimeout(() => URL.revokeObjectURL(enlace.href), 1000);
    });
  });
})();
