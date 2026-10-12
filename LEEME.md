# Strata Portable · Windows x64

Abre **Strata.exe**. Es una aplicación nativa de escritorio con interfaz negra en español. No abre un navegador, no inicia un servidor y no requiere instalar Python, Java o .NET.

Los motores opcionales dotPeek y Binary Ninja requieren instalaciones propias. La automatización de Binary Ninja requiere además un Python dedicado compatible y una licencia Commercial, Ultimate o headless. Los tres motores incluidos siguen funcionando sin esas instalaciones.

Conserva **toda esta carpeta**: `_internal/`, `tools/`, `runtime/`, `scripts/` y `samples/` acompañan al ejecutable. Puedes copiarla a otra ubicación con permiso de escritura. La distribución ocupa aproximadamente 1,45 GB porque incluye los tres motores, Ghidra completo y sus runtimes. El EXE por sí solo no contiene esos archivos.

## Modos

**Seguro:** decompila sin abrir la aplicación analizada. Calcula SHA-256, identifica el formato, obtiene cadenas y hexadecimal, y guarda el código que pueda recuperar el motor.

**Normal:** realiza la misma decompilación y habilita la apertura según el entorno que elijas. El botón de apertura se habilita al terminar el análisis; la muestra no se abre automáticamente al seleccionarla.

- **Este PC:** abre EXE Windows o JAR ejecutables con los permisos del usuario. Se muestra el SHA-256 y se requiere confirmar que se trata de una app conocida y confiable. Se comprueba que el original no haya cambiado y se abre desde su carpeta original para conservar las dependencias. Se registra el PID y el estado del proceso inicial durante hasta 60 segundos. Strata no detiene esa aplicación al cerrar.
- **VM / Windows Sandbox:** abre un EXE dentro de una sesión nueva y desechable, con red, GPU, portapapeles, cámara, micrófono e impresoras compartidas desactivados. Solo se mapea una carpeta de entrada en modo lectura. Un monitor de creación de procesos comienza antes de la muestra. Su registro permanece dentro de la VM. Requiere Windows Sandbox, que **no está instalado en el equipo donde se creó esta entrega**.
- **VM / VM propia:** exporta un ZIP con el EXE, su SHA-256 y `Abrir-en-VM.ps1`. Transfiere el paquete a una VM Windows desechable. El script comprueba el hash, una VM compatible y adaptadores de red desactivados, solicita confirmación de aislamiento y registra los procesos observados. Strata no configura ni inicia VMware, VirtualBox, Hyper-V u otro hipervisor. La apertura dentro de esa VM es manual.

Un EXE con dependencias de instalación puede necesitar prepararlas dentro de la VM. El paquete VM contiene el archivo seleccionado, no una instalación completa.

## Formatos

| Archivo | Motor incluido | Resultado |
|---|---|---|
| APK / DEX / CLASS / JAR | JADX 1.5.6 | Código Java aproximado y recursos admitidos |
| EXE / DLL de .NET | ILSpy 8.2.0.7535 | Código C# y proyecto |
| PE nativo / ELF / Mach-O | Ghidra 12.1.4 | Pseudocódigo C |
| Formato desconocido o error del motor | Inspección integrada | Informe, cadenas y bytes; no se presenta como código decompilado |

La selección admite cualquier archivo, pero **no existe decompilación universal**. La ofuscación, el cifrado, empaquetadores, aplicaciones iOS protegidas y formatos no compatibles pueden impedir recuperar código. El resultado no garantiza nombres, comentarios ni lenguaje originales. Abrir una aplicación no elimina automáticamente sus protecciones: esta versión no hace volcado de memoria ni desempaquetado dinámico.

APK requiere Android para ejecutarse; ELF requiere Linux y Mach-O requiere macOS. Esta app puede realizar su análisis estático en Windows, pero el modo Normal no instala automáticamente emuladores ni otros sistemas. DLL, CLASS y DEX no se tratan como aplicaciones ejecutables independientes.

## Uso

1. Pulsa **Seleccionar archivo** o **Abrir muestra de prueba**.
2. Elige **Seguro** o **Normal**. En Normal elige PC o VM y el tipo de VM.
3. Usa **Combinado · motores compatibles** (predeterminado) para coordinar todos los motores compatibles configurados. También puedes elegir **Automático · un motor** o un motor concreto. Pulsa **Decompilar aplicación**.
4. Explora código, `strings.txt`, `hex.txt`, `engine.log` y `report.json`. Usa la búsqueda del explorador y la búsqueda en el texto.
5. **Exportar ZIP** guarda los resultados. **Abrir en PC / VM** o **Exportar paquete VM** son acciones separadas y solo se habilitan para formatos compatibles.

Ctrl+O selecciona archivo. Ctrl+F lleva a la búsqueda en el visor. Los resultados e historial se guardan en `data/`. Para eliminar un análisis, cierra Strata y elimina su subcarpeta dentro de `data/`.

Límites: 100 MB de entrada; hasta cinco minutos por motor; Java con heap de hasta 2 GB; visor de hasta 2 MB y 20 000 líneas; 10 000 cadenas ASCII; hexadecimal de los primeros 64 KB. Puede haber código parcial cuando el motor devuelve errores. La observación Normal no sustituye un trazador completo de archivos, registro, memoria o red.

## Análisis combinado

Un único análisis coordina los motores por formato: JADX para Java/Android; ILSpy y aportes exportados de dotPeek para .NET; Ghidra y Binary Ninja automático configurado para binarios nativos. Se ejecutan por turnos para limitar el uso de memoria. Las herramientas no compatibles con el formato no se fuerzan.

**Código recuperado** muestra primero un resumen de todos los motores, sin clasificación de calidad ni elección de una versión preferida. Cada salida automática está en `motors/<motor>/` en el mismo explorador. `combined.json` y `combined-summary.txt` registran código recuperado, errores, motores sin configurar y exportaciones manuales pendientes. **Ver todos los aportes** vuelve al resumen. Si un motor falla, el coordinador conserva su registro y continúa con los demás. Un resultado con código de algún motor puede conservar errores de otros: consulta el resumen.

Las importaciones de dotPeek/Binary Ninja se añaden al mismo expediente e índice sin sobrescribir las versiones previas. **Exportar ZIP** incluye los aportes de todos los motores y las importaciones. **Revisar con IA** abre la selección de archivos del expediente, identificados por sus rutas; puedes elegir versiones de varios motores. Conserva el límite de 48.000 caracteres y la vista previa exacta antes de cada envío. No se envía código automáticamente.

dotPeek y Binary Ninja siguen requiriendo instalación/configuración. dotPeek aporta una exportación manual; Binary Ninja automático requiere su API y una licencia compatible. El modo combinado muestra esas limitaciones, sin simular resultados ausentes. El código de motores distintos se conserva como versiones independientes, no se mezcla automáticamente ni se garantiza equivalencia o recuperación del original.

## Agentes y modelos

En **Agentes y modelos → Modelos y claves API → Añadir modelo**, configura nombre, proveedor, URL base, modelo exacto y una clave opcional.

- **compatible:** API con `POST /chat/completions`, mensajes de texto y respuesta `choices[].message.content`. Ejemplo de URL base: `https://api.openai.com/v1`. Strata añade `/chat/completions` si no está presente. Se envían `stream: false` y `max_tokens: 4096`; no todas las APIs o modelos admiten este contrato. No incluye adaptadores específicos para Claude, Gemini ni APIs que solo admitan Responses.
- **ollama:** URL inicial `http://localhost:11434`, endpoint `/api/chat`, `format: json`, `stream: false` y `num_predict: 4096`. Instala Ollama y prepara el modelo por separado. Strata no instala servicios ni descarga modelos.

Los proveedores remotos requieren HTTPS con validación de certificados. HTTP solo se permite en `localhost`, `127.0.0.1` y otras direcciones de bucle local, incluido `::1`. La clave se transmite como autorización Bearer cuando la configuras; no aparece en la vista previa, registros ni exportaciones.

Las claves se guardan cifradas con DPAPI en `data/ai-settings.json`, para el usuario de Windows actual. No es una contraseña portable: al cambiar de usuario o PC puede ser necesario introducirla de nuevo. En Editar conexión, deja el campo vacío para conservar la clave o marca **Eliminar la clave guardada**. Al duplicar una conexión, su clave no se copia. El cifrado no impide que programas ejecutados con tu mismo usuario accedan a ella.

En la pestaña **Agentes personalizados**, crea uno o más agentes con conexión, rol e instrucciones. Los roles incluyen plantillas de analista, desofuscador y revisor. Puedes editar, duplicar y eliminar agentes; una conexión utilizada no puede eliminarse hasta cambiar o eliminar sus agentes.

## Análisis con IA

1. Abre **Análisis con IA** en el menú lateral. Importa archivos JavaScript, Java, C#, C o C++, o añade código desde un análisis terminado. El botón **Analizar con IA** del visor añade el archivo actual a esta sección; todavía no lo envía.
2. Marca entre uno y tres agentes haciendo clic en sus filas; otro clic los desmarca. El primer agente aparece seleccionado para facilitar el inicio. Se ordenan por rol: analista, desofuscador y revisor.
3. **Revisar mensaje y analizar** guarda una sesión y muestra la solicitud completa: modelo, instrucciones, código y resultados anteriores. El envío solo comienza al pulsar **Enviar este mensaje**.
4. El resultado aparece en **Revisión de cambios**. **Revisar siguiente agente** muestra el mensaje completo para ese agente, incluidos los resultados recibidos antes. No hay llamadas automáticas al siguiente agente ni reintentos.
5. Lee el resumen y selecciona una propuesta. La comparación muestra **Original** y **Propuesta** lado a lado: las líneas modificadas del original se resaltan en rojo y las de la propuesta en verde. **Guardar copia revisada** conserva el original. Las propuestas de IA no garantizan equivalencia ni recuperan necesariamente nombres originales.
6. **Mostrar detalles técnicos** despliega evidencias, transformaciones y consumo informado. El resumen permanece separado de esos registros.
7. **Exportar sesión** incluye la sesión y las copias aceptadas. Si todos los archivos proceden del mismo análisis, sus resultados también se incorporan a la exportación habitual de ese análisis.

Límite: 48.000 caracteres de código en total, tres agentes por ronda, hasta 4.096 tokens de salida solicitados por agente y 120 segundos por solicitud. No se trunca código ni se acepta una respuesta que el proveedor marca como incompleta. La API puede imponer límites menores. Se muestra consumo cuando el proveedor informa cantidades; no se estima un coste monetario sin conocer su tarifa.

**Cancelar ronda** detiene la espera y cierra la conexión disponible. Una solicitud ya enviada puede consumir saldo aunque se cancele. Una ronda adicional se inicia manualmente. No se ha probado con claves de pago reales: las pruebas de protocolos utilizan servidores simulados locales.

Los agentes no reciben herramientas de ejecución ni acceso al disco. Solo se envían las instrucciones, los archivos seleccionados y los resultados anteriores visibles. Revisa el código antes de enviarlo: puede contener información privada. Las sesiones contienen ese código y se guardan sin cifrar en `data/ai/<id>/`; el cifrado DPAPI protege las claves, no el historial de código. El ZIP no incluye la configuración ni las claves guardadas, pero conserva el código que elegiste analizar.

## Desofuscación local de JavaScript

Abre **Desofuscador local** en el menú lateral. Importa archivos `.js`, `.mjs` o `.cjs` y pulsa **Desofuscar archivos**. Se procesan todos los archivos de esa lista; no hace falta seleccionarlos otra vez. **Cargar ejemplo** añade `samples/Obfuscated.js` para probarlo.

La selección de archivos de esta sección es independiente de **Análisis con IA**. Sus resultados también se abren en **Revisión de cambios**, donde puedes leer el resumen, comparar las versiones y guardar una copia.

Tree-sitter analiza la sintaxis sin ejecutar JavaScript. Las reglas resuelven concatenaciones de cadenas literales, normalizan escapes reconocidos y simplifican suma, resta y multiplicación entre enteros seguros. Cada cambio incluye regla, línea y texto anterior/posterior. El resultado se vuelve a analizar antes de ofrecerlo como copia.

Se conservan expresiones con variables, llamadas, comentarios dentro de operaciones, números inseguros, escapes ambiguos y directivas. Si el archivo tiene errores de sintaxis, se conserva completo sin transformaciones. No hace `eval`, descifra cadenas dinámicas, elimina flujos complejos ni recupera nombres originales. Java, C# y pseudocódigo C utilizan las propuestas de agentes, no este desofuscador local.

El historial IA/local está en **Historial → Análisis de código**. La pestaña **Aplicaciones** conserva las decompilaciones anteriores. Puedes abrir sesiones en Revisión de cambios, consultar copias y exportarlas; inicia nuevas consultas desde Análisis con IA o Desofuscador local. Los análisis existentes siguen siendo compatibles con esta interfaz.

## Pruebas y fuentes

`samples/Hello.class`, `Hello.dll` y `classes.dex` contienen exclusivamente un método de multiplicación; sus fuentes están incluidas. `NativeHost.bin` es una copia del apphost de Microsoft .NET 7 usada como muestra PE nativa **solo para análisis estático**.

`VALIDACION.json` contiene las pruebas ejecutadas desde el EXE final. Para repetirlas: `Strata.exe --self-test`; el informe aparece en `VALIDACION.json`. Ninguna prueba ejecuta la muestra: las aperturas PC/VM se comprueban con mocks.

`VALIDACION-IA.json` contiene 18 pruebas nuevas de agentes, claves, conexiones y desofuscación; se repiten con `Strata.exe --ai-self-test`. Las solicitudes usan servidores simulados en bucle local. La equivalencia JavaScript ejecuta únicamente ejemplos controlados y requiere Node para esa prueba de desarrollo; Node no es necesario para usar el desofuscador. `VALIDACION-INTERFAZ-IA.json` registra la revisión de la ventana, dos mensajes con agentes simulados, diferencias, copias, cancelación e historial. La validación suma 27 pruebas automáticas y la revisión del flujo nativo.

No se realizó un traslado real de claves a otro usuario o equipo: se verificó el manejo del fallo de DPAPI con datos dañados y descifrado fallido simulado. La propuesta de JavaScript incluida en el historial de demostración se obtuvo con el EXE y no ejecutó la muestra.

El código de la interfaz y motor está en `src/`. `CONSTRUIR.ps1` describe la compilación del EXE; requiere Python y PyInstaller solo para desarrollar, no para usar la app. La carpeta de herramientas y runtimes debe acompañar a cualquier nueva compilación.

Las licencias de terceros están en sus distribuciones y en `LICENCIAS/`.

Al añadir un modelo, la opción **Crear también un analista listo para usar** está activada. Puedes empezar con ese agente y personalizar otros después. El menú agrupa las tareas y destaca la pantalla actual en blanco; pasar el ratón por otra opción no cambia la selección.

