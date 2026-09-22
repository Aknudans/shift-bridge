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
- Anti-loop: corta si el mismo documento se intenta borrar 2 veces seguidas;
  tope de 300 iteraciones.
- Solo corre para filas `preexistente=True` y estado ≠ ERROR.
- ⚠️ `--no-guardar` **NO** protege el borrado: con `borrar` los documentos se
  borran igual (la ayuda de la interfaz lo advierte).

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
- **`DOCUMENTOS_SET_ESTANDAR`**: los 8 tipos habituales de un ingreso
  (Cédula, Contrato puesta a disposición, Contacto en caso de Emergencia,
  Toma de conocimiento biométrico, Registro Entrega EPP, Capacitación Uso EPP,
  Capacitación IRL, RIOHS). Tras subir, se compara `subidos + ya_existian +
  tipos_sitio` (todo lo leído de la grilla, sin prefijo del catálogo) contra
  el set y se agrega `⚠ FALTAN documentos del set estándar (N): …`. Así, un
  documento ya cargado que no viene en la carpeta no se reporta como
  faltante. No bloquea el proceso.

### 11.8b Chequeo previo (21/09/2026)

Antes de conectar a Chrome, `crear_o_editar.main()` corre siempre
`chequear_datos_excel` (celdas obligatorias vacías; AFP / Sistema de Salud
fuera de `CATALOGO_AFP` / `CATALOGO_SALUD`, comparando sin tildes) y, con
`--subir-documentos`, `chequear_carpeta_documentos` (reusa
`asignar_carpetas_lote` y `preparar_items_carpeta`): personas sin carpeta con
el nombre sugerido (`_carpeta_sugerida`), carpetas sin dueño, archivos no
reconocidos, archivos en subcarpetas (no se leen), tipos repetidos y faltantes
del set estándar. Lo imprime `imprimir_chequeo_previo`; no frena la corrida.
La asignación calculada se reutiliza en el lote. `--solo-chequear` termina
tras el chequeo sin abrir Chrome; en la interfaz es el botón **"Revisar antes
de iniciar"**.

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
