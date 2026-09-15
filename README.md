# Bot ShiftLaboral

Automatización de la carga de colaboradores y sus documentos en
**ShiftLaboral** (`https://externoslof.shiftlabor.com/`), el sistema de
"Control Externos" de LOGISTICA FALABELLA.

## Objetivo del proyecto

La empresa obtiene los datos de sus colaboradores desde Talana y debe
registrarlos en ShiftLaboral. Ese sitio **no tiene API pública ni importación
masiva de trabajadores**: solo ofrece un formulario web para ingresar a las
personas una por una, y otro para subir sus documentos.

Este proyecto resuelve ese trabajo manual con un **bot RPA** (automatización
del navegador con Playwright) que, a partir de un Excel, puede:

1. **Comparar** los datos del Excel contra lo que ya está registrado en
   ShiftLaboral, sin modificar nada.
2. **Crear o editar** colaboradores: si la persona existe, corrige solo los
   campos que difieren; si no existe, la crea.
3. **Subir documentos** de cada persona desde una carpeta, detectando el tipo
   de documento por el nombre del archivo y sin duplicar lo que ya está
   cargado.

Al terminar, genera un **reporte Excel** con una fila por persona, coloreada
según el resultado, y el detalle de lo que se hizo.

El bot trabaja sobre una sesión de Chrome iniciada manualmente: **nunca pide,
ve ni guarda contraseñas**.

---

## Uso de la interfaz

La interfaz es una ventana de escritorio con los pasos ordenados de arriba
hacia abajo. También tiene un botón **«¿Cómo se usa?»** con esta misma ayuda
resumida.

### Cómo abrirla

- **Con el ejecutable** (sin Python instalado): abrir
  `ShiftLaboralBot\ShiftLaboralBot.exe`. Se debe copiar la **carpeta
  completa** `ShiftLaboralBot`; el `.exe` solo, sin la carpeta `_internal`
  al lado, no funciona.
- **En desarrollo** (con Python): ejecutar `ejecutar_interfaz.bat`.

### Paso 1 — Abrir Chrome e iniciar sesión

1. Hacer clic en **«Abrir Chrome de depuración»**. Se abre una ventana de
   Chrome aparte (perfil separado del Chrome habitual) en la página de
   ShiftLaboral.
   - Si Chrome no está instalado en una ruta estándar, la interfaz pedirá
     seleccionar `chrome.exe` manualmente.
2. **Iniciar sesión a mano** en esa ventana con el usuario habitual.
3. **Dejar esa ventana abierta** mientras el bot trabaja. Basta con hacerlo
   una vez por jornada.

> ⚠ ShiftLaboral permite **una sola sesión por usuario**. Si alguien más
> inicia sesión con la misma cuenta, la sesión se cae y el bot se detiene a
> la mitad. No usar el mismo usuario en dos computadores al mismo tiempo.

### Paso 2 — Seleccionar el modo

| Modo | Qué hace | ¿Modifica el sitio? |
|---|---|---|
| **Comparación** | Busca cada RUT y compara el sistema contra el Excel. Resultado: `OK`, `ADVERTENCIA` (con el detalle de lo que no coincide) o `NO_ENCONTRADO`. | No |
| **Creación / edición** | Si la persona existe, edita solo los campos distintos; si no existe, la crea. Resultado: `CREADO`, `EDITADO`, `SIN_CAMBIOS`, `OMITIDO_CARGO` o `ERROR`. | Sí |
| **Subir documentos** | Hace lo mismo que Creación / edición y además sube los documentos de la carpeta de cada persona. | Sí |

> ⚠ Si el **cargo** del Excel no coincide exactamente con alguno del catálogo
> del sitio, la persona se omite completa (no se toca ningún campo) y queda
> en el reporte como `OMITIDO_CARGO`.

### Paso 3 — Seleccionar los archivos

- **Excel de entrada**: el archivo con los colaboradores (ver
  [Formato del Excel](#formato-del-excel)).
- **Reporte de salida**: dónde se guarda el resultado. Por defecto,
  `reporte.xlsx` junto al programa. Si ese archivo está abierto en Excel al
  terminar, el reporte se guarda con otro nombre para no perderlo.
- **Carpeta de documentos** (solo en el modo *Subir documentos*): ver
  [Carpeta de documentos](#carpeta-de-documentos).

### Paso 4 — Opciones

Estas opciones no aparecen en el modo Comparación, que nunca modifica nada.

- **Modo prueba: llenar el formulario pero NO guardar** — el bot llena todos
  los formularios pero no presiona Guardar. Sirve para revisar qué haría antes
  de dejarlo actuar. Se recomienda usarlo con pocas filas y observando la
  ventana de Chrome.
- **Anotar en el reporte qué documentos tiene ya cada persona** — agrega al
  reporte la lista de documentos cargados. No sube ni borra nada.
- **Documentos anteriores de quienes ya existían** — qué hacer con los
  documentos que el proveedor subió en un registro anterior de una persona
  preexistente:
  - *No tocarlos* (por defecto).
  - *Solo anotarlos en el reporte*.
  - *Borrarlos (no se puede deshacer)* — pide una confirmación adicional al
    iniciar.

> ⚠ El **modo prueba NO protege el borrado** de documentos: con «Borrarlos»,
> los documentos se eliminan de todas formas y no se pueden recuperar. Los
> documentos cargados por el mandante nunca se tocan.

### Paso 5 — Iniciar y seguir el avance

1. Hacer clic en **«Iniciar»**.
2. El recuadro **«Log en vivo»** muestra en qué persona va el bot y qué hizo
   con ella; la barra de progreso avanza a medida que termina cada una.
3. Si una persona falla, el error queda registrado y el bot **continúa con la
   siguiente**; el lote no se detiene por una sola fila.
4. Al terminar, abrir el reporte de salida.

> ⚠ El botón rojo **«Cancelar proceso»** detiene todo de inmediato. Puede
> dejar un formulario a medio llenar en el sitio y **no genera el reporte
> final** (solo queda lo visible en el log). Usarlo únicamente si algo va mal.

### El reporte

Una fila por persona, con un color según el resultado (verde: realizado;
amarillo: omitido o con advertencia; rojo: error) y una columna de detalle
que indica qué campos cambiaron, qué documentos se subieron, cuáles ya
existían y cuáles faltan del set estándar de ingreso.

---

## Formato del Excel

Se usa la primera hoja, con **los mismos encabezados y el mismo orden que la
"Planilla Agosto"**, para poder copiar y pegar el bloque de personas
directamente (pegar como **valores**, no como fórmulas):

```
rut | nombre | apellidoPaterno | apellidoMaterno | sexo | cargo | desde | hasta | centroCosto | sucursal | afp | isapre | sueldoBase | PROVEEDOR | TIENDA
```

- `rut`: con o sin puntos.
- `sexo`: `M` / `F` (se traduce a Masculino / Femenino).
- `desde` / `hasta`: inicio y fin de contrato. Si `hasta` está vacío, se usa
  `desde` + 89 días.
- `centroCosto` y `sucursal`: solo mantienen el pegado alineado; el bot no
  los usa.
- `sueldoBase`: si está vacío, se toma como 0.
- `cargo`: valor **exacto** del catálogo del sitio, con prefijo. Ejemplo:
  `LOGISTICA FALABELLA/Operario de Bodega EST`.
- `PROVEEDOR`: por ejemplo
  `LOGISTICA FALABELLA/Grupo Colchagua Empresa de Servicios Transitorios S.A.`
  o `LOGISTICA FALABELLA/Grupo Santa Cruz Outsourcing S.A.`
- `TIENDA`: por ejemplo `LOGISTICA FALABELLA/LOF1 ACCESO1`.

Las columnas `sueldoBase`, `PROVEEDOR` y `TIENDA` no vienen en la planilla y
se completan manualmente.

## Carpeta de documentos

```
Documentos/
├── Adan_Leon/
│   ├── CI Adan Leon.pdf
│   ├── CPD Adan Leon.pdf
│   └── RIOHS.pdf
└── Virginia_Stella/
    └── ...
```

- Una **subcarpeta por persona**, con nombre y apellido separados por `_`.
- El **nombre de cada archivo** determina el tipo de documento. Se reconocen
  las abreviaturas habituales (`CI`, `CPD`, `IRL`, `RIOHS`, `EPP`, `Contrato
  Trabajo`, `Finiquito`, `Liquidacion`, etc.), sin importar mayúsculas,
  tildes ni separadores.
- Un archivo que no se reconoce se omite y queda informado en el reporte; el
  resto se sube igual.
- Nunca se sube un tipo de documento que la persona ya tenga cargado, así que
  se puede volver a correr sin duplicar.
- Si a una persona le falta algún documento del set estándar de ingreso, se
  agrega una advertencia en el reporte (no detiene el proceso).
- El sitio procesa la carga en segundo plano: los documentos pueden tardar
  1-2 minutos en aparecer.

## Si algo falla

- **«No se pudo conectar a Chrome»**: la ventana de depuración se cerró o no
  se abrió. Presionar de nuevo «Abrir Chrome de depuración» y no cerrarla.
- **El sitio pide iniciar sesión a mitad de la corrida**: la sesión expiró o
  alguien más ingresó con la misma cuenta. Iniciar sesión de nuevo en esa
  ventana y volver a correr: lo ya hecho queda hecho y lo que está bien no se
  vuelve a modificar.
- **Muchas filas `OMITIDO_CARGO`**: revisar que la columna `cargo` tenga el
  valor exacto del catálogo, con el prefijo `LOGISTICA FALABELLA/`.

## Recomendaciones

- Probar siempre primero con **2-3 filas** y el **modo prueba** activado antes
  de correr un lote completo.
- No ejecutar varias instancias del bot al mismo tiempo con el mismo usuario.

---

## Para desarrolladores

Instalación (una vez por computador):

```
python -m pip install -r requirements.txt
python -m playwright install chromium
```

- Ejecución por consola: `ejecutar_bot.bat` (Comparación) y
  `ejecutar_crear.bat` (Creación / edición), o directamente
  `buscar_y_comparar.py` / `crear_o_editar.py` con Chrome abierto en el
  puerto 9222 (`abrir_chrome.bat`).
- Pruebas de funciones puras (no abren Chrome): `python test_datos.py`.
- Construir el ejecutable: `construir_exe.bat` (genera
  `dist/ShiftLaboralBot/`).
- Detalle técnico, selectores y decisiones de diseño: `CLAUDE.md`.
