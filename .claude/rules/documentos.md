---
paths:
  - documentos.py
  - test_datos.py
  - tipos_documento.py
---

# Documentos (secciones 11.6–11.9 de CLAUDE.md)

Referencia detallada de limpieza, carga masiva, anti-duplicado, chequeo previo y visita única a la vista de documentos.

### 11.6 Limpieza de documentos (`--limpiar-documentos [listar|borrar]`)

Para personas preexistentes: dejarlas sin la documentación que subió el
proveedor en un registro anterior.

- **Vista** `DocumentosTrabajador.aspx`: se llega **clickeando el RUT** en la
  grilla (no el lápiz). La grilla inferior (`tr.dxgvDataRow`) lista los
  documentos.
- Solo los documentos del **proveedor** tienen `a[title="borrar"]`; los del
  mandante no se pueden ni se deben tocar.
- Confirmación (popup DevExpress, no `window.confirm`):
  `#btnConfirmacionBorrarAceptar` (o `_2`). Éxito:
  `#btnExitoAceptar_grillaExternosDocumentosTrabajador_2` (el `<div class="btn_c">`).
  **Aceptar el popup de éxito es obligatorio** entre borrados: su
  `.ui-widget-overlay` bloquea el siguiente clic.
- Antes de cada clic: `_esperar_sin_overlays` y `_cerrar_dialogo_abierto`.
- **La grilla pagina de a 10**: se recorren todas las páginas
  (`_total_paginas`, `_ir_a_pagina`).
  🔴 **`_ir_a_pagina` arreglada (22/09/2026)**: usaba un clic por
  `page.evaluate` y `wait_for_load_state("networkidle")`, las dos cosas que
  `CLAUDE.md` sección 6 desaconseja para este sitio. La grilla **nunca
  cambiaba de página**: se leía la primera dos veces y los documentos de la
  página 2 en adelante quedaban invisibles. Se detectó en el reporte del
  22/09/2026: las 5 personas con más de 10 documentos daban exactamente 20
  entradas, con la primera mitad idéntica a la segunda. Ahora hace **clic
  real** (`a:visible:text-is("N")` dentro de
  `#grillaExternosDocumentosTrabajador`) y espera con `wait_for_function` a
  que el indicador `Página N de M` muestre la página pedida
  (`_JS_ESTA_EN_PAGINA`); devuelve True solo si llegó. `_pagina_actual`
  devuelve 0 cuando no hay paginador (10 documentos o menos). Los tres
  recorridos que la usan **saltean** la página que no se pudo abrir, porque
  leerla igual repetiría la anterior. Falta validarlo en vivo.
- Anti-loop: corta si el mismo documento se intenta borrar 2 veces seguidas;
  tope de 300 iteraciones.
- Solo corre para filas `preexistente=True` y estado ≠ ERROR.
- ⚠️ Con `--no-guardar` + `borrar` (22/09/2026) NO se borra: `simular=True` lista
  todo y `_probar_clic_borrar_y_cancelar` aprieta borrar en el primero y Cancelar
  (`SEL_CONFIRMAR_CANCELAR`) en la confirmación. Estado `simulado`, reporte
  "Docs que se BORRARÍAN". Selector de Cancelar sin validar en vivo.
- **Captura en modo prueba**: `_capturar_panel_carga` guarda
  `capturas/panel_<RUT>_<fecha>.png` antes de cancelar el panel. Expande el
  scroll interno para que salgan todas las filas y **restaura los estilos**
  después: sin restaurar, el panel queda más alto que la ventana y Cancelar no
  se puede apretar (se vio con una grilla simulada).

### 11.7 Carga masiva de documentos (`--subir-documentos CARPETA`)

**Panel**: en `DocumentosTrabajador.aspx`, botón `#btnDocumentosMasivos_2`
(div; el `<a>` sin `_2` no dispara). Abre `#panelCargaModalDocumentosMasivo`.

| Campo (fila N, 0-based) | Selector | Nota |
|---|---|---|
| Archivos | `#FileDocumentosTrabajadorMasivo` | oculto, `set_input_files` con varios |
| Nombre | `#nombre_documento_masivo_{N}` | obligatorio |
| Período | `#calendario_documento_masivo_{N}` | datepicker; obligatorio |
| Tipo documento | `#cboTipoDocumentos_{N}` | `<select>` nativo, `-1` = sin elegir |
| ¿Tiene vencimiento? | `#chk_fecha_vencimiento_documento_masivo_{N}` | checkbox |
| Fecha vencimiento | `#calendario_fecha_vencimiento_documento_masivo_{N}` | obligatoria en la práctica |

Guardar: `#btnGuardarModalCargaMasivaDocumentos_2`; Cancelar:
`#btnCancelarModalCargaMasivaDocumentos_2` (con `--no-guardar`).
Procesamiento **asíncrono** (~1-2 min): verificar después.

Detalles:
- Tras `set_input_files`, esperar a que exista `#cboTipoDocumentos_{len-1}`.
- Datepickers (Período, Vencimiento): setear `.value` no basta; usar
  `jQuery(inp).datepicker('setDate', new Date(y, m-1, d))`.
- **Período**: el sitio rechaza el vacío. Se intenta vacío primero (como lo
  hacen los usuarios) y, ante "Debe completar los campos vacíos", se llena con
  `fechaContratacion` y se reintenta (reporte `subido_con_periodo`). Para
  tipos "1 sola vez" el sitio guarda `04/01/1990` sin importar lo escrito.
- **Fecha de vencimiento**: desmarcar la casilla no la libera; se llena
  siempre con `fechaTermino` (o `fechaContratacion`).
- Corre para filas `CREADO` / `EDITADO` / `SIN_CAMBIOS`.

**Carpeta → persona** (`_buscar_carpeta_persona`): subcarpetas
`Nombre_Apellido`; calza si sus tokens `_norm` (≥2) son subconjunto de
nombre + apellidos del Excel. Sin carpeta o ambigua → se reporta.
🔴 **Asignación por lote** (`asignar_carpetas_lote`, 21/09/2026): las carpetas
se reparten para TODO el Excel antes de empezar. Si una carpeta calza con más
de una persona (p. ej. `Juan_Soto` con "Juan Carlos Soto Pérez" y "Juan Soto
Rojas"), no se sube nada a ninguna de ellas y se reporta; antes, la persona
sin carpeta propia recibía los documentos de la otra. Las carpetas que no
calzan con nadie se avisan al inicio y en el resumen final.

**Archivo → tipo** (`clasificar_nombre_archivo`, `documentos.py`; tabla en
**`tipos_documento.py`**, 22/09/2026): `_norm` ignora mayúsculas, tildes y
separadores (` `, `-`, `_`, `.`, `,`). Primero busca coincidencia exacta con
el nombre de un tipo (`CATALOGO_TIPOS_DOCUMENTO` se deriva de
`REGLAS_TIPO_DOCUMENTO`). Si no, cada tipo tiene alternativas de palabras
clave: calza si el nombre contiene TODAS las palabras de alguna, en cualquier
orden; se aceptan plurales en S/ES y se descartan `PALABRAS_RELLENO` de las
alternativas. Si calzan varios tipos, gana la alternativa con más palabras;
si empatan tipos distintos, el archivo se omite como "tipo ambiguo" (antes
ganaba la primera regex de la lista). Evitar alternativas de una sola
palabra genérica (`EPP`, `CONTRATO`).

- **Contrato de Trabajo (15/09/2026)**: los archivos llegan como "Contrato
  Trabajo", sin el "de". En el sitio el tipo que debe elegirse es
  explícitamente **`LOGISTICA FALABELLA/Contrato de Trabajo`**. Para que
  "Anexo contrato trabajo" no se tome como contrato, Anexos de Contrato tiene
  la alternativa de 3 palabras `ANEXO CONTRATO TRABAJO`, que gana a la de 2.
- 🔴 **`CD` es el contrato de trabajo (22/09/2026)**: el archivo llega como
  **`CD FALABELLA RETAIL.pdf`** (CD = contrato) y estaba en las alternativas
  de *Contrato puesta a disposición*, así que se subía con el tipo equivocado
  a las 40 personas del lote. Ahora `CD` y `CD FALABELLA RETAIL` están en
  **Contrato de Trabajo**; *Contrato puesta a disposición* conserva `CPD`,
  `CONTRATO DISPOSICION` y `CONTRATO PUESTA`. Lo confirmó el catálogo real:
  en el reporte del 22/09/2026 las 43 personas tenían cargado
  `Contrato de Trabajo` y solo 2 un `Contrato puesta a disposición`.
- **Contrato puesta a disposición**: llega con el nombre completo y fecha
  (`Contrato puesta a disposición letra E - 01-SEPTIEMBRE 206.pdf`). Hay
  variante **letra E** y **letra C**: son el mismo tipo del sitio, solo cambia
  el nombre del archivo, y las dos calzan por `CONTRATO PUESTA` /
  `CONTRATO DISPOSICION` sin reglas extra. Casos fijados en `test_datos.py`.
- **Tipo del sitio sin regla**: `TC Procedimiento de Trabajo Seguro` existe en
  el catálogo (visto en `21826722-K` y `27995448-3`) pero no está en
  `tipos_documento.py`; un archivo de ese tipo hoy queda sin reconocer.
- `_seleccionar_tipo_en_combo` elige la opción del `<select>` quitando el
  prefijo `LOGISTICA FALABELLA/` y comparando el resto **exacto** (tras
  normalizar). Si el sitio renombra un tipo, hay que cambiarlo también en
  `tipos_documento.py`.
- Archivo que no calce → se omite y se reporta, sin frenar al resto.

### 11.8 Anti-duplicado, verificación y faltantes

- **`--verificar-documentos`** (solo lectura): lista los tipos de TODOS los
  documentos cargados (proveedor y mandante).
- **`omitir_existentes=True`** (default) en la subida: se saltan los tipos ya
  cargados; el reporte los muestra como "ya tenía, no se re-subió (N)". Estado
  `sin_items_nuevos` si no queda nada por subir.
- **`DOCUMENTOS_SET_ESTANDAR`**: los 9 tipos habituales de un ingreso
  (Cédula, **Contrato de Trabajo**, Contrato puesta a disposición, Contacto en
  caso de Emergencia, Toma de conocimiento biométrico, Registro Entrega EPP,
  Capacitación Uso EPP, Capacitación IRL, RIOHS). Pasó de 8 a 9 el 22/09/2026,
  junto con la corrección de `CD`: el de trabajo llega siempre y el de puesta
  a disposición puede venir o no. ⚠️ Como el chequeo previo solo mira la
  carpeta, hoy avisa `faltan del set estándar (1): Contrato puesta a
  disposición` en todas las personas cuya carpeta no lo traiga; contra el
  sitio, a quien ya lo tenga cargado no se le avisa.
  Tras subir, se compara `subidos + ya_existian +
  tipos_sitio` (todo lo leído de la grilla, sin prefijo del catálogo) contra
  el set y se agrega `⚠ FALTAN documentos del set estándar (N): …`. Así, un
  documento ya cargado que no viene en la carpeta no se reporta como
  faltante. No bloquea el proceso.

### 11.8b Chequeo previo (21/09/2026)

Antes de conectar a Chrome, `crear_o_editar.main()` corre siempre
`chequear_datos_excel` (celdas obligatorias vacías; AFP / Sistema de Salud
fuera de `CATALOGO_AFP` / `CATALOGO_SALUD`, comparando sin tildes; desde el
22/09/2026 también RUT con formato o dígito verificador inválido
(`problema_rut` en `shift_common.py`), RUT repetido en varias filas, Sexo
distinto de Masculino/Femenino y Proveedor fuera de
`GRUPOS_PROVEEDOR_CONOCIDOS`) y, con
`--subir-documentos`, `chequear_carpeta_documentos` (reusa
`asignar_carpetas_lote` y `preparar_items_carpeta`): personas sin carpeta con
el nombre sugerido (`_carpeta_sugerida`), carpetas sin dueño, archivos no
reconocidos, archivos en subcarpetas (no se leen), tipos repetidos y faltantes
del set estándar. Lo imprime `imprimir_chequeo_previo`; no frena la corrida.
La asignación calculada se reutiliza en el lote. `--solo-chequear` termina
tras el chequeo sin abrir Chrome; en la interfaz es el botón **"Revisar antes
de iniciar"**.

**Aviso y confirmación (22/09/2026)**: si hay problemas, se escribe
`<output>_chequeo.xlsx` (`filas_reporte_chequeo`: una fila por problema,
ERROR / ADVERTENCIA; `--reporte-chequeo` cambia la ruta). En la interfaz,
Iniciar en modo crear/documentos corre primero `--solo-chequear` (fase
`chequeo_previo`), lee `Resumen chequeo: N persona(s)` y `Reporte del chequeo
previo guardado en: …` del log y, si N > 0, pregunta si continuar antes de
lanzar la corrida real (`comando_pendiente`); la comparación va directo. Por
consola, `main()` pregunta con `input()` solo si `sys.stdin.isatty()`; la
interfaz lanza los subprocesos con `stdin=DEVNULL` para que nunca se queden
esperando.

### 11.9 Una sola visita a la vista de documentos por persona

`gestionar_documentos_trabajador(page, rut, grupo, limpiar=, verificar=,
items=, ...)` abre la vista UNA vez y hace, en este orden: **borrar → leer
tipos → subir** (si se leyera antes de borrar, lo recién borrado contaría como
"ya lo tenía" y se omitiría la subida). Los tipos se leen una sola vez y se
pasan a la subida (`tipos_ya_leidos`). Vuelve a la grilla en un `finally`.
Internas: `_limpiar_en_vista_abierta`, `_leer_tipos_en_vista_abierta`,
`_subir_en_vista_abierta` (arranca cerrando diálogos y esperando overlays),
`_volver_a_trabajadores`.

La carpeta de la persona se busca antes de navegar: si no existe, no se entra a la vista.
