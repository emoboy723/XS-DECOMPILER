# Seguridad

La versión publicada es 1.4.0. Para una vulnerabilidad, utiliza la pestaña Security → Report a vulnerability del repositorio. Evita publicar credenciales, muestras privadas o detalles explotables en un issue público.

Strata decompila en modo Seguro sin ejecutar la muestra, pero los parsers de terceros procesan archivos no confiables: utiliza una VM aislada para muestras desconocidas. El modo Normal ejecuta únicamente después de una acción y confirmación explícitas. Las claves DPAPI no se trasladan entre usuarios o equipos; debes volver a introducirlas. La salida de IA requiere revisión humana.
