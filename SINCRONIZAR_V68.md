# V68 · Sincronizar con Render

El puente de consola anterior usaba un envío distinto. Si muestra `HTTP 400 El lote contiene datos no válidos`, ciérralo con **Ctrl+C** en esa ventana. El lector sigue guardando en su base local.

1. Actualiza tu calculadora en Render con **BenjayayeCraft_Solo_Web_V68.zip**. Si tu repositorio tiene cambios propios, como perfiles por navegador, conserva esos cambios e integra el receptor de V68 sobre tu versión. Usa la misma carpeta de datos que ya tenía tu servidor.
2. En **Environment**, usa **BENJAYAYE_API_SYNC_TOKEN** para la clave de envío. La web V68 también reconoce **BENJAYAYE_SYNC_KEY** si no existe el primero y la clave tiene entre 32 y 128 caracteres de letras, números, guiones o guiones bajos. Si necesitas una nueva, genera una en tu PC con `python -c "import secrets; print(secrets.token_urlsafe(32))"`. La clave de acceso a la página es distinta del token de envío.
3. Abre `INICIAR_LECTOR_WINDOWS.bat` en la edición **PC V68**. En **Analizador → Sincronizar con web…**, pon la URL base (por ejemplo, `https://benjayaye-craft.onrender.com`) y el mismo token de envío. Si ya tenías la URL y el token guardados en el lector nuevo, el campo del token se puede dejar vacío.
4. Marca **Enviar también lecturas de pantalla confirmadas** y pulsa **Guardar y reenviar todo**. Se suben los últimos precios guardados por objeto, ciudad y calidad, junto con las cotizaciones públicas ya consultadas. Después se envían los cambios mientras el lector siga abierto. Para consultar precios públicos nuevos, pulsa **Analizar**. Si las lecturas de pantalla se encuentran en otra carpeta, usa **Vista en vivo → Ajustes → Importar precios de una versión anterior…**, elige su `datos/precios.sqlite3` y vuelve a sincronizar.
5. En la web abre **Mercado** y comprueba que dice **V68**. Selecciona **Precios → Ambos** y elige el mismo objeto, variante, ciudad y calidad. Para ver solo lecturas usa **Lector de pantalla**. Para inspeccionar la API, abre **Ver cotizaciones sincronizadas de la API**.

Los precios de pantalla y los de la API se envían por separado. Si una lectura no coincide con el catálogo, la ciudad, la calidad o la fecha, las válidas del mismo lote se guardan y la rechazada queda en el equipo. No se envían capturas, lotes ni precios manuales.

Para una instalación estándar de la web, el comando de inicio es `python app.py --web-alojada`; utiliza **BENJAYAYE_ACCESO_WEB** para la clave privada de acceso. Los ajustes del servidor y de persistencia se explican en [SINCRONIZAR_API_V66.md](SINCRONIZAR_API_V66.md).
