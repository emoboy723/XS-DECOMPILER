# Strata 1.4.0 — análisis combinado, agentes y desofuscación

Primera publicación pública del proyecto XS-DECOMPILER.

- Aplicación Windows x64 portable con interfaz nativa negra en español.
- Modo Seguro sin ejecución y modo Normal con apertura explícita en PC, Windows Sandbox o paquete para VM propia.
- JADX, ILSpy y Ghidra incluidos para Java/Android, .NET y binarios nativos; inspección de formatos, SHA-256, cadenas y hexadecimal.
- Coordinación de motores compatibles en un único expediente. Todos los aportes, errores e importaciones visibles, sin ranking ni fusión automática.
- Integración opcional de dotPeek mediante GUI/exportación manual y Binary Ninja mediante GUI/API licenciada. No se incluyen sus instalaciones.
- Conexiones a Chat Completions compatible con OpenAI y Ollama; agentes configurables con plantillas de análisis, desofuscación y revisión.
- Claves protegidas con DPAPI; vista previa exacta y aprobación antes de enviar código; tareas en segundo plano, cancelación, errores y consumo disponible.
- Desofuscador local JavaScript con Tree-sitter, transformaciones conservadoras y registro de cambios, sin ejecutar código seleccionado.
- Secciones separadas de Análisis con IA, Desofuscador local y Revisión de cambios; comparación lado a lado y registros técnicos desplegables.
- Modificaciones aceptadas como copias, historial y exportación de resultados y aportes de todos los motores.
- 48 pruebas funcionales y 31 comprobaciones UI registradas. APIs IA y adaptadores de herramientas opcionales probados con simulaciones; traslado DPAPI real y Windows Sandbox pendientes de validación en otro entorno.

## Descargar

Extrae **toda** la carpeta de `Strata-1.4.0-windows-x64-portable.zip` y ejecuta `Strata.exe`. No requiere instalación de Python/Java/.NET. El EXE no está firmado. Conserva `_internal`, `tools`, `runtime`, `scripts` y sus licencias. Se publican SHA-256 y las fuentes correspondientes al JDK redistribuido.

Límites: 100 MB por muestra, cinco minutos por motor, tres agentes por ronda, 48.000 caracteres por selección y 120 segundos por petición IA. No hay decompilación universal, desempaquetado dinámico ni eliminación automática de protecciones. Consulta la guía para requisitos de las herramientas y entornos de ejecución.
