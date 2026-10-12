# XS-DECOMPILER · Strata

Aplicación nativa portable para Windows x64: ingeniería inversa, decompilación coordinada y revisión de código asistida por IA. Interfaz negra sencilla en español, sin servidor web.

**[Descargar Strata 1.4.0](https://github.com/emoboy723/XS-DECOMPILER/releases/tag/v1.4.0)** · [Guía completa](LEEME.md) · [Motores externos](MOTORES-EXTERNOS.md) · [Cambios](CHANGELOG.md)

## Empezar

Descarga `Strata-1.4.0-windows-x64-portable.zip`, extrae **toda la carpeta** en una ubicación con permiso de escritura y abre `Strata.exe`. Conserva `_internal`, `tools`, `runtime` y `scripts`: el ejecutable por separado no funciona. No requiere instalar Python, Java ni .NET. La carpeta completa ocupa aproximadamente 1,45 GB. El ejecutable no tiene firma Authenticode.

## Funciones

| Área | Qué puedes hacer |
|---|---|
| Decompilación | APK, DEX, CLASS y JAR con JADX; EXE/DLL .NET con ILSpy; PE, ELF y Mach-O nativos con Ghidra |
| Análisis combinado | Coordinar motores compatibles en un expediente, conservar todos los aportes sin ranking, ver fallos y exportar un ZIP conjunto |
| Motores externos | Abrir dotPeek y añadir sus exportaciones; usar Binary Ninja GUI o su API licenciada para recuperar HLIL |
| Modo Seguro | Inspeccionar y decompilar sin ejecutar la muestra |
| Modo Normal | Decompilar y después solicitar explícitamente la apertura en PC, Windows Sandbox o preparar un paquete para una VM propia |
| Inspección | Identificación de formato, SHA-256, cadenas, hexadecimal, búsqueda, registros y código recuperado |
| Agentes y modelos | Crear, editar, duplicar y eliminar conexiones y agentes; plantillas de analista, desofuscador y revisor |
| IA | Chat Completions compatible con OpenAI y Ollama existente; selección y vista previa exacta antes del envío, estado, cancelación y consumo cuando se informa |
| Desofuscación local | Simplificaciones conservadoras de JavaScript con Tree-sitter, sin ejecutarlo: cadenas, escapes y operaciones enteras admitidas |
| Revisión | Comparación lado a lado, propuestas aceptadas guardadas como copias, historial y exportación |
| Claves | Cifrado DPAPI ligado al usuario y PC; excluidas de registros y exportaciones |

JADX, ILSpy, Ghidra y sus runtimes están incluidos en la descarga portable. **dotPeek y Binary Ninja no están incluidos**. dotPeek aporta exportaciones manuales; la automatización de Binary Ninja necesita una instalación, API Python y licencia compatibles. Cada motor conserva sus resultados: Strata no fusiona automáticamente código ni determina cuál es mejor.

La IA recibe únicamente el contenido aprobado en la vista previa y no dispone de herramientas para ejecutar comandos ni leer otros archivos. Máximo 3 agentes por ronda, 48.000 caracteres seleccionados y 120 segundos por petición. Las rondas posteriores son manuales. HTTPS para proveedores remotos; HTTP permitido únicamente para bucle local. Ollama inicia con `http://localhost:11434` y no descarga modelos automáticamente.

El modo Normal no ejecuta automáticamente al comenzar el análisis. La apertura en PC requiere confirmar una muestra confiable. Windows Sandbox debe estar disponible; las VM propias se preparan manualmente. No hay recuperación universal, volcado de memoria ni desempaquetado dinámico. La IA puede proponer cambios incorrectos y la recuperación no reproduce necesariamente nombres, comentarios o código originales.

## Desarrollo

En Windows con Python 3.13 y Git:

```powershell
git clone https://github.com/emoboy723/XS-DECOMPILER.git
cd XS-DECOMPILER
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
$env:PYTHONPATH = "$PWD/src"
python src/desktop.py
python -m unittest discover -s src -p ai_selftest.py
python -m unittest discover -s tests -p check_external_tools.py
python -m unittest discover -s tests -p check_combined.py
./CONSTRUIR.ps1
```

`CONSTRUIR.ps1` genera el EXE y `_internal` en `compiled/Strata`. Para ejecutar los motores coloca `tools/` y `runtime/` de la distribución oficial en la raíz del proyecto. Para distribuir un build conserva también `scripts/`, `samples/`, `LICENCIAS/` y sus avisos. El build de CI contiene la interfaz y el parser, **no los motores externos**.

Los ejemplos JavaScript ejecutados por los tests de equivalencia son fixtures controlados y requieren Node.js. La prueba de ILSpy se omite si no está instalado. Los scripts `tests/check_*_ui.py` requieren una sesión de escritorio. `src/selftest.py` requiere los motores incluidos y comprueba la distribución completa.

## Validación de 1.4.0

48 pruebas funcionales y 31 comprobaciones de interfaz registradas en [validation](validation). Incluyen decompilación con los motores distribuidos, servidores IA simulados, DPAPI, desofuscación y coordinación de resultados. Los adaptadores dotPeek/Binary Ninja se verificaron con simulaciones; esas herramientas no estaban instaladas. El traslado real a otro usuario/PC y la apertura en Windows Sandbox no se comprobaron en este equipo. Los informes describen estos límites.

## Licencias

Código propio: [MIT](LICENSE). Los terceros conservan sus licencias: [avisos](LICENCIAS/AVISOS.md) y archivos legales dentro de la descarga. El código fuente correspondiente al Temurin JDK incluido se adjunta a la misma Release como `OpenJDK21U-jdk-sources_21.0.12.1_1.tar.gz`. Sus condiciones GPLv2 con Classpath Exception no quedan sustituidas por MIT.

Usa las herramientas sobre software que tengas derecho a analizar. Para colaborar consulta [CONTRIBUTING.md](CONTRIBUTING.md); para fallos de seguridad consulta [SECURITY.md](SECURITY.md).
