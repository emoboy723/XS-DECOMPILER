# dotPeek y Binary Ninja en Strata

El modo predeterminado **Combinado · motores compatibles** reúne los aportes en un único análisis. Usa el resumen y el explorador para ver las salidas de cada motor sin priorizar ninguna. Las exportaciones manuales que importes se incorporan al mismo índice; el ZIP contiene todos los aportes. El selector individual sigue disponible para trabajos específicos.

La integración es opcional. No se incluyen instaladores, licencias ni copias de estas herramientas. En el equipo de entrega no están instaladas; los adaptadores se han probado con una API simulada y llamadas de apertura simuladas, no con motores externos reales.

## Configuración

1. Instala [dotPeek desde JetBrains](https://www.jetbrains.com/decompiler/) o [Binary Ninja desde Vector 35](https://binary.ninja/), según tu necesidad.
2. En Strata abre **Motores y ayuda → Herramientas externas**. Elige la pestaña de la herramienta y pulsa **Buscar instalaciones** o **Examinar** para indicar su ejecutable. Guarda las rutas.
3. Las rutas pueden ser absolutas o relativas a la carpeta portable. Si trasladas Strata a otro PC, instala/configura allí las herramientas. La configuración está en `data/external-tools.json`; no contiene licencias.

## dotPeek (.NET)

Al seleccionar un EXE o DLL .NET aparece **dotPeek · exportación en su interfaz** en el selector de motor. Este recorrido genera primero la inspección local. En **Código recuperado**, pulsa **Abrir en dotPeek** para abrir la copia del ensamblado como datos. Esto no ejecuta la aplicación analizada.

Dentro de dotPeek selecciona el ensamblado, usa **Export to Project** y elige una carpeta fuera de los resultados de Strata. Después pulsa **Importar código exportado** y selecciona esa carpeta. Se copian archivos `.cs`, `.csproj` y `.sln` a un directorio nuevo dentro de los resultados. No se construye ni ejecuta el proyecto. ILSpy sigue disponible para obtener C# directamente dentro de Strata.

[Guía oficial de exportación de dotPeek](https://www.jetbrains.com/help/decompiler/Exporting_Assembly_to_Project.html).

## Binary Ninja (binarios nativos)

Con su ejecutable configurado, **Abrir en Binary Ninja** abre la copia del binario para análisis avanzado. Para importar una exportación manual selecciona una carpeta con pseudocódigo `.c`, `.h`, `.cpp` o `.txt`. Una base de datos `.bndb` no es código y no se importa al visor. La disponibilidad de análisis, arquitecturas y exportación depende de la edición instalada.

Para decompilación automática:

1. Usa una licencia **Commercial, Ultimate o headless**. Free y Non-commercial no habilitan este adaptador sin interfaz.
2. Prepara un Python dedicado compatible con la versión de Binary Ninja siguiendo su documentación. No uses su intérprete integrado, que el fabricante reserva para su consola, ni Python de Microsoft Store.
3. En la pestaña Binary Ninja pulsa **Configurar decompilación automática…**. Selecciona `python.exe` y la carpeta que contiene `binaryninja/__init__.py` (normalmente `python` dentro de la instalación). Activa la API y guarda.
4. Selecciona un PE nativo, ELF o Mach-O y elige **Binary Ninja · API automática**. El adaptador `scripts/binaryninja_export.py` recupera el árbol HLIL de cada función, guarda `decompiled.c` y un índice `functions.json`. Es pseudocódigo HLIL, no código fuente original ni C garantizado compilable. Las funciones sin HLIL quedan registradas.

Se utiliza un proceso separado con Python aislado (`-I`), sin plugins de usuario/repositorio ni ajustes de usuario. El límite es de cinco minutos. Un error de API/licencia se muestra en el resultado y `engine.log`; no se cambia silenciosamente a Ghidra. Si se recupera código parcial, se conserva y se informa del error. La licencia se comprueba al analizar: el estado **configurada** solo confirma las rutas y la opción de automatización.

[Automatización y Python en Binary Ninja](https://docs.binary.ninja/dev/batch.html), [API HLIL](https://api.binary.ninja/binaryninja.highlevelil-module.html).

## Resultados e importación

Los motores externos no abren ni ejecutan la muestra como programa. El modo Normal sigue usando el botón y confirmación separados para ejecutar una aplicación en PC/VM. Abrir el decompilador no activa ese modo.

Las importaciones se guardan como copias en carpetas nuevas, con registro de procedencia; no sobrescriben los resultados previos. Strata no verifica que una exportación seleccionada corresponda al binario: esa asociación la declara el usuario. El estado de decompilación automática se conserva separado de la importación. Límite por importación: 20.000 archivos y 100 MB. Se omiten binarios, enlaces simbólicos y junctions. Las copias aparecen en el explorador, se pueden enviar a los agentes mediante la selección habitual y se incluyen al exportar resultados.

## Validación

`VALIDACION-MOTORES-EXTERNOS.json`: doce pruebas de configuración, formato, apertura como argumento de datos, importación sin sobrescribir y ejecución del adaptador contra una API simulada (éxito y error de licencia). `VALIDACION-MOTORES-UI.json`: selector y configuración en ventana mínima. `VALIDACION.json`: nueve pruebas repetidas con JADX, ILSpy y Ghidra reales incluidos. No se ha validado la calidad de dotPeek/Binary Ninja reales, porque aún no están instalados.
