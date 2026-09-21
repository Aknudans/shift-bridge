> **⚠️ REGLA DE IDIOMA — INQUEBRANTABLE.** Todo texto en español de este
> proyecto (código, comentarios, docstrings, mensajes de consola/UI, este
> archivo, README.md, GUIA_EJECUCION.txt, nombres de commit) se escribe en
> **español neutro**, sin modismos ni gramática de ninguna variante regional
> específica (nada de voseo argentino/rioplatense — "vos tenés/hacé/mirá" — ni
> tuteo coloquial marcado, ni lunfardo/jerga de ningún país). Usar formas
> impersonales o de infinitivo para instrucciones ("Seleccionar el archivo",
> "Verificar que Chrome esté abierto") en vez de conjugar en 2ª persona
> ("elegí", "revisá", "tenés que"). Motivo: se detectó voseo filtrado en
> código y documentación (revertido el 10/09/2026) — no debe repetirse.

# CLAUDE.md — Bot de automatización ShiftLaboral

Este archivo es el contexto de proyecto para Claude Code. Leerlo completo antes de tocar código.

## 0. Comandos y arquitectura técnica (referencia rápida)

**Instalación** (una vez por computador; en algunos equipos `pip`/`playwright`
sueltos no están en el PATH — usar `python -m pip` / `python -m playwright`):
```
python -m pip install -r requirements.txt
python -m playwright install chromium
```

**Ejecutar el bot (usuario final, sin Python instalado)**:
`dist/ShiftLaboralBot/ShiftLaboralBot.exe`. Se entrega la **carpeta completa**
(el `.exe` solo, sin `_internal/` al lado, no funciona). Se construye con
`construir_exe.bat` (ver 11.12).

**Ejecutar el bot en desarrollo**: `ejecutar_interfaz.bat` → abre
`interfaz.py` (ver 11.10): botón "Abrir Chrome" (modo depuración, perfil
separado), selector de Excel/carpeta, 3 modos (Comparación / Creación-edición
/ Subir documentos), log en vivo y barra de progreso. `ejecutar_bot.bat`
(Fase 1 por consola) y `ejecutar_crear.bat` (Fase 2 por consola) siguen
disponibles.

**Ejecutar los scripts directamente** (requiere Chrome abierto con
`--remote-debugging-port=9222` y sesión iniciada — `abrir_chrome.bat`):
```
python buscar_y_comparar.py --input colaboradores.xlsx --output reporte.xlsx
python crear_o_editar.py --input SHIFT.xlsx [--no-guardar] [--limpiar-documentos [listar|borrar]] [--verificar-documentos] [--subir-documentos CARPETA]
```

**Tests**: `python test_datos.py` (o `python -m pytest test_datos.py`) cubre
las funciones puras — interpretación del Excel y mapeo nombre de archivo →
tipo de documento (`normalizar_sexo`, `formatear_fecha`,
`autocompletar_campos_negocio`, `_norm`, `tipo_desde_nombre_archivo`,
`_buscar_carpeta_persona`, `preparar_items_carpeta`, orden de
`gestionar_documentos_trabajador` con funciones simuladas). No abre Chrome:
se puede correr en cualquier momento. **Correrlo siempre después de tocar
`_MAPEO_NOMBRE_TIPO`.** Navegación, selectores y timing NO tienen tests: solo
se validan contra el sitio real con un Excel de pocas filas. No hay linter.

**Arquitectura**:
- `shift_common.py`: lo compartido entre Fase 1 y Fase 2 — conexión a Chrome
  (`connect_over_cdp`, puerto 9222; nunca lanza su propio navegador ni maneja
  login), navegación por menú, selección de Grupo Proveedor, búsqueda de RUT,
  normalización de texto, carga del Excel y escritura del reporte.
- `buscar_y_comparar.py` (Fase 1, solo lectura) y `crear_o_editar.py`
  (Fase 2). Cada uno tiene un bloque `CONFIGURACIÓN` con los selectores
  específicos de su fase.
- Flujo secuencial por fila (sin paralelismo, por la sesión única del sitio):
  seleccionar grupo → filtrar RUT → ver/editar/crear → acumular
  `ResultadoFila` → seguir con la siguiente fila aunque una falle
  (`try/except` por fila).
- Lectura de datos vía DOM (no existe API, ver sección 4).
- Salida: reporte Excel coloreado por estado (`escribir_reporte`,
  `COLORES_ESTADO`).

## 1. Objetivo del proyecto

La empresa descarga datos de colaboradores desde la API de Talana y necesita
cargarlos en **ShiftLaboral** (`https://externoslof.shiftlabor.com/`), sistema
de "Control Externos" de LOGISTICA FALABELLA que **no tiene API pública ni
importación masiva de trabajadores** — solo un formulario web 1 a 1.

La solución es un **bot RPA con Playwright**. Meta: una app local que 2
usuarios/cuentas puedan correr para crear/verificar colaboradores y subir sus
documentos en lote, sin depender de Claude.

## 2. Estado actual

Pipeline completo implementado y validado en vivo con 1-2 personas por corrida:
- **Fase 1** (`buscar_y_comparar.py`): comparación OK / ADVERTENCIA /
  NO_ENCONTRADO.
- **Fase 2** (`crear_o_editar.py`): crear/editar con verificación real del
  guardado, `--no-guardar`, limpieza, verificación y carga masiva de
  documentos sin duplicados, aviso de documentos faltantes.
- Interfaz gráfica (`interfaz.py`) y ejecutable empaquetado en carpeta.

Pendientes activos: sección 12.

## 3. Flujo de negocio acordado

```
Para cada colaborador del Excel:
  1. Seleccionar el "Grupo Proveedor" correcto (hay 2 grupos/usuarios).
  2. Buscar el RUT en el grid de Trabajadores.
  3. Fase 1 (comparar): si existe, abrir "ver", extraer y comparar
     -> OK / ADVERTENCIA (con detalle) / NO_ENCONTRADO. Nunca modifica nada.
  4. Fase 2 (crear/editar): si existe -> editar solo lo que difiere;
     si no existe -> crear. Detalle en sección 11.1.
  5. Cargo que no calce exacto con el catálogo real -> la fila completa se
     omite y se reporta (OMITIDO_CARGO).
```

## 4. Por qué RPA y no una API "no oficial"

- El sitio es **ASP.NET WebForms clásico con DevExpress** (`__VIEWSTATE`,
  `__EVENTVALIDATION`, callbacks `Aspxcallbackpanel`), sin capa JSON.
  Reconstruir los POST a mano es frágil y se rompe sin aviso.
- En los scripts del sitio solo existen dos Page Methods menores
  (`Ajax.aspx/AyudaFuncionalidad`, `Ajax.aspx/InfoUsuario`), ninguno de
  trabajadores.
- Automatizar el navegador es más lento pero mucho más resiliente.

## 5. Mapeo de campos de negocio → campos del formulario

🔴 **El template `SHIFT.xlsx` usa los encabezados y el orden de la "Planilla
Agosto"** (para copiar y pegar el bloque sin remapear). Hoja única, valores
literales (NO fórmulas). Orden de columnas:

```
rut | nombre | apellidoPaterno | apellidoMaterno | sexo | cargo | desde | hasta | centroCosto | sucursal | afp | isapre | sueldoBase | PROVEEDOR | TIENDA
```

`shift_common.cargar_excel()` traduce los encabezados a nombres internos
(`RENOMBRE_COLUMNAS_ENTRADA`) y normaliza el sexo (`normalizar_sexo`: `M`/`F`
→ `Masculino`/`Femenino`). `centroCosto`/`sucursal` solo alinean el pegado;
el bot los ignora.

| Columna template (interno) | Campo en ShiftLaboral | Sección del formulario |
|---|---|---|
| nombre (NOMBRES) | Nombres | Datos Trabajador |
| apellidoPaterno | Apellido Paterno | Datos Trabajador |
| apellidoMaterno | Apellido Materno | Datos Trabajador |
| sexo (SEXO) | Sexo | Datos Trabajador |
| desde (fechaContratacion) | Inicio Contrato | Datos Trabajador |
| hasta (fechaTermino) | Fin Contrato | Datos Trabajador (vacío → fechaContratacion + 89 días) |
| afp (AFP) | AFP | Datos Trabajador |
| isapre (ISAPRE) | Sistema de Salud | Datos Trabajador |
| sueldoBase | Sueldo Base | Datos Trabajador (vacío → 0) |
| PROVEEDOR | Proveedores | Relación Clientes |
| cargo (CARGO) | Categoría Trabajador | valor exacto del catálogo (`LOGISTICA FALABELLA/…`), escrito a mano por el usuario |
| TIENDA | Tiendas | Tiendas |

## 6. Flujo verificado en vivo — Fase 1 (lectura)

⚠️ **Regla de interacción de este sitio**: varios controles (menú acordeón,
ASPxComboBox) **NO responden a `page.evaluate(() => el.click())`**. Usar
siempre clic real de Playwright (`locator.click()`). Leer DOM vía
`page.evaluate` sí está bien.

⚠️ **`networkidle` NO es señal fiable de que terminó un callback DevExpress.**
Esperar explícitamente al elemento que se necesita (`wait_for_function` /
`wait_for_selector`). Esto causó varios bugs de timing ya corregidos.

1. **Entrar**: `page.goto("https://externoslof.shiftlabor.com/Default.aspx")`
2. **Menú hamburguesa**: `#icono_abrir_menu`
3. **Sección "Externos"**: `#mf_cab_01` (**clic real**)
4. **"Trabajadores"**: `#mf_cab_ll_01_01` → `Funcionalidades/Externos/ProveedorTrabajador.aspx`
5. **Grupo Proveedor**: abrir `#MJJerarquia00_I` (**clic real**) y clickear la
   opción por texto visible. La columna `PROVEEDOR` puede traer prefijo
   `LOGISTICA FALABELLA/`; se usa solo el texto tras la última `/`.
   Seleccionar siempre explícitamente: el servidor recuerda la última
   selección de la sesión.
6. **Esperar recarga del grid** (callback AJAX).
7. **Filtro RUT**: `#grillaExternosProveedorTrabajadores_DXFREditorcol2_I`
   (click + fill + Enter). Deja 0 o 1 fila. La detección de "encontrado" se
   hace por contenido de celda, no por la clase `tr.dxgvDataRow`.
8. **Botón "ver"**: `a[title="ver"]` (`.first`). No usar el id largo por índice.
9. **Leer "Datos Trabajador"** con JS que compara `textContent.trim()` del
   `<td>` y toma `nextElementSibling` (el locator `td:text-is(...)` falla con
   "Apellido Materno:", cuya etiqueta va envuelta en un `<span>`):
   ```python
   valor = page.evaluate(
       """(etiqueta) => {
           const td = Array.from(document.querySelectorAll('td'))
               .find(t => t.textContent.trim() === etiqueta);
           const siguiente = td ? td.nextElementSibling : null;
           return siguiente ? siguiente.textContent.trim() : null;
       }""",
       etiqueta,
   )
   ```
   Sueldo Base sigue el mismo patrón.
10. **Proveedores / Cargo / Tiendas**: listbox DevExpress. Tomar todos los
    `.dxeListBoxItem` visibles (`offsetParent !== null`) cuyo id contenga
    `lstProveedores` / `lstVerClientes` (Cargo) / `listBoxTienda`, unidos con
    `", "`. En la vista "ver", Proveedores y Tiendas vienen SIN prefijo
    `LOGISTICA FALABELLA/` y Cargo CON prefijo → se normaliza con
    `quitar_prefijo_catalogo` en ambos lados.
11. **Cerrar la vista con `#btnCancelar`** (crítico): si no se cierra, la fila
    queda en modo expandido y contamina la búsqueda y extracción del RUT
    siguiente. Implementado en `cerrar_vista_detalle()`. Blindaje: valores
    extraídos de más de 300 caracteres se tratan como `None`.

## 7. Selectores de referencia rápida

| Elemento | Selector | ¿Clic real? |
|---|---|---|
| Menú hamburguesa | `#icono_abrir_menu` | No |
| Sección "Externos" | `#mf_cab_01` | **Sí** |
| Link "Trabajadores" | `#mf_cab_ll_01_01` | No |
| Combo Proveedor | `#MJJerarquia00_I` | **Sí** |
| Opción del combo | `text={nombre exacto}` | Sí |
| Filtro RUT | `#grillaExternosProveedorTrabajadores_DXFREditorcol2_I` | No |
| Botón "ver" / "editar" | `a[title="ver"]` / `a[title="editar"]` (`.first`) | Sí |
| Grid principal | `#grillaExternosProveedorTrabajadores_DXMainTable` | — |
| Link RUT (→ documentos) | `a[id*="link_Codigo_0"]` | Sí |

Otros filtros del grid (mismo patrón, no probados):
`..._DXFREditorcol1_I` (Tipo Código), `col3` (Nombres), `col4` (Apellido
Paterno), `col5` (Apellido Materno).

Proveedores disponibles:
- "Grupo Colchagua Empresa de Servicios Transitorios S.A."
- "Grupo Santa Cruz Outsourcing S.A."

### Catálogos de valores válidos

**AFP**: Provida, Habitat, Cuprum, Capital, Modelo, Planvital, Jubilado, Uno, Sin Información

**Sistema de Salud**: Cruz Blanca, Banmédica, Consalud, Ferrosalud, Vida Tres, Fonasa, Sin Información

**Sede/Tienda** (bajo LOGISTICA FALABELLA/): LOF1 ACCESO1, LOF2 ACCESO1, LOF3

**Cargo**: 122 opciones bajo LOGISTICA FALABELLA/. No se valida en el Excel;
el bot lo valida contra el dropdown real. Incluye tanto
`Operario de Bodega` como `Operario de Bodega EST` (son cargos distintos; el
habitual en la planilla es la variante `EST`, pero lo decide el usuario).
Si se necesita el catálogo completo, extraerlo en vivo.

## 8. Validación y reglas de seguridad

### Casos de referencia (Grupo Colchagua)
- `10016891-K` — VIRGINIA JEANETTE STELLA MONARES, Femenino, Provida, Fonasa
  → debe dar `OK`. Cambiar la AFP a "Habitat" en el Excel debe dar
  `ADVERTENCIA: AFP no coincide (sistema: 'Provida' / excel: 'Habitat')`.
- `22710691-3` — PABLO IGNACIO ALFARO BAHAMONDE, creado por el bot; se usa
  para probar edición y documentos.
- `22708167-8`, `11847694-8` — identidad ya registrada por otro cliente
  (caso "identidad bloqueada", 11.5).

Todo cambio en navegación, selectores o timing se valida primero con
`--no-guardar` y un Excel de pocas filas, observando el navegador.

### Reglas no negociables
- El bot **nunca** maneja, guarda ni pide contraseñas: asume sesión iniciada
  manualmente.
- No correr múltiples instancias en paralelo con el mismo usuario
  (ShiftLaboral fuerza **sesión única por usuario**; si alguien más inicia
  sesión, la actual se cae).
- Si algo falla, **registrar el error y seguir con la siguiente fila**, nunca
  detener el lote en silencio ni dejar el navegador en un estado
  inconsistente sin avisar.

## 9. Archivos del proyecto

```
shift_common.py         — módulo compartido (conexión, navegación, RUT,
                          normalización, Excel, reporte). No se ejecuta solo.
campos_formulario.py    — primitivas de lectura/escritura del formulario
                          editar/crear: comboboxes, multi-select, validar
                          Cargo, verificar guardado, cerrar formulario y
                          popup de éxito. Sin lógica de negocio.
buscar_y_comparar.py    — Fase 1 (búsqueda + comparación, solo lectura).
crear_o_editar.py       — Fase 2 (creación/edición + flags de documentos).
documentos.py           — limpieza, verificación y carga masiva de
                          documentos; mapeo nombre de archivo → tipo.
interfaz.py             — interfaz gráfica (customtkinter). Corre los modos
                          como subproceso, no reimplementa la lógica.
app_entry.py            — punto de entrada único: sin argumentos abre la
                          interfaz; con --modo-comparar / --modo-crear corre
                          esa lógica y termina.
test_datos.py           — pruebas de funciones puras (no toca el navegador).
ejecutar_interfaz.bat   — launcher de la interfaz.
ejecutar_bot.bat        — launcher de consola, Fase 1.
ejecutar_crear.bat      — launcher de consola, Fase 2 (guarda de verdad, sin
                          flags de documentos).
abrir_chrome.bat        — solo abre el Chrome de depuración (puerto 9222,
                          perfil separado) para correr scripts a mano.
ShiftLaboralBot.spec    — receta de PyInstaller (versionada).
construir_exe.bat       — arma dist/ShiftLaboralBot/ (build/ y dist/ están
                          en .gitignore).
requirements.txt        — dependencias (pyinstaller solo para construir).
README.md / GUIA_EJECUCION.txt — instrucciones para el usuario final.
```

## 10. Convenciones del proyecto

- Comentarios y mensajes en español neutro (ver regla al inicio).
- Selectores y configuración centralizados en el bloque `CONFIGURACIÓN` de
  cada script. Todo selector nuevo confirmado se documenta aquí (secciones
  6, 7 y 11).
- **Código compartido entre fases vive en `shift_common.py`**; nunca
  duplicarlo en los scripts de cada fase.
- **Primitivas del formulario de Fase 2 viven en `campos_formulario.py`**,
  separadas de la lógica de negocio (`editar_trabajador_existente` /
  `crear_trabajador_nuevo` en `crear_o_editar.py`).
- Si un control no responde, probar clic real de Playwright antes de asumir
  que el selector está mal, y esperar explícitamente el elemento en vez de
  confiar en `networkidle` (sección 6).
- La fuente de verdad es siempre el sitio real, no este documento.

## 11. Fase 2 — Creación, edición y documentos

### 11.1 Flujo de negocio

```
Para cada colaborador del Excel:
  1. Seleccionar el Grupo Proveedor.
  2. Buscar el RUT en el grid.
  3a. Si SE ENCUENTRA -> "editar" (lápiz):
        - Leer los valores ACTUALES del formulario.
        - Validar el Cargo contra el catálogo real; si no calza -> se omite
          la fila COMPLETA (OMITIDO_CARGO).
        - Calcular el diff completo y modificar SOLO los campos que difieren.
        - Guardar (#btnGuardar) y verificar el guardado.
  3b. Si NO SE ENCUENTRA -> "Crear":
        - Validar Cargo igual que en 3a.
        - Llenar el formulario con todos los datos del Excel.
        - Guardar, verificar y confirmar que el RUT aparece en la grilla.
  4. Reportar: CREADO / EDITADO (con campos cambiados) / SIN_CAMBIOS /
     OMITIDO_CARGO / ERROR (o SIMULADO_CREAR / SIMULADO_EDITAR con --no-guardar).
  5. Tras CREADO/EDITADO, volver a Trabajadores por el menú lateral
     (hamburguesa -> Externos -> Trabajadores) para dejar el servidor en un
     estado limpio; el grupo se vuelve a seleccionar en la fila siguiente.
```

No hay modo "dry-run" en dos corridas: en una sola corrida se calcula el diff
antes de tocar nada y se reporta lo hecho. `--no-guardar` llena todo pero no
hace clic en Guardar.

### 11.2 Formulario "editar" — selectores

No se puede pasar de "ver" a "editar" en la misma fila: cerrar primero con
`#btnCancelar`.

```
Nombres:            #txtNombres
Apellido Paterno:   #txtApellidoPaterno
Apellido Materno:   #txtApellidoMaterno
Sexo:               [id*="cbSexo"]     (ASPxComboBox)
Inicio Contrato:    #calendarioFechaInicio_txtCalendar
Fin Contrato:       #calendarioFechaTermino_txtCalendar  (+ checkbox "Indefinido")
AFP:                [id*="cbAFP"]      (ASPxComboBox)
Sistema de Salud:   [id*="cbIsapre"]   (ASPxComboBox)
Sueldo Base:        #txtSueldoBase
Proveedores:        #ASPxDropDownEdit3_I (checkboxes + botón ">" para confirmar)
Categoría Trabajador (Cargo) y Tiendas: dropdowns con checkboxes
Botones:            #btnCancelar / #btnGuardar
```
- Los ids de texto y fechas son iguales en Editar y en Crear. Los combos
  cambian el resto del id (`_ef0_…_0_VI` vs `_efnew_…_VI`): usar siempre
  selección por fragmento.
- Combos Sexo/AFP/Isapre: `escribir_combobox_simple()` (clic en
  `[id*="cbXxx"][id$="_I"]` + clic en la opción por texto).
- Fin Contrato es un datepicker de jQuery UI: `.fill()` funciona.
- 🔴 **Multi-select ACUMULATIVO** (Proveedores, Cargo, Tiendas): clickear una
  opción suma al valor actual (`"A;B"`). Para dejar un único valor hay que
  desmarcar explícitamente los demás (`establecer_multiselect_valor_unico`).
  Se asume un solo valor por campo, como en el Excel.
- Cada opción son **dos** `.dxeListBoxItem` consecutivos: uno `dxeC`
  (checkbox) y otro `dxeT` (texto). Se emparejan por posición.
- Las etiquetas "Proveedores:", "Categoría Trabajador:" y "Tiendas:" tienen
  la caja DEBAJO, no al lado: se toma el primer `input`/`select` visible
  posterior a la etiqueta (`compareDocumentPosition`).
- En el formulario editable, los 3 multi-select **SÍ traen el prefijo**
  `LOGISTICA FALABELLA/`: pasar el valor completo del Excel, sin recortar.
- Antes de abrir un dropdown, esperar a que no esté el overlay
  `dxgvLoadingDiv` (`_esperar_grid_sin_overlay`) y, tras abrirlo, a que haya
  ítems visibles (`_esperar_items_listbox`).
- **Sección "Marcas"**: fuera de alcance, el bot no la toca.

### 11.3 Formulario "Crear"

Botón `text=Crear` (esquina inferior derecha de la grilla), en 2 pasos:

**Paso A**: Tipo Código (default "Cédula Chilena (CI)") + RUT en
`#txtRutVer_I` (no tocar `#txtRutVer_Raw`, que es hidden) + confirmar con
`#btnAceptaRut`. Escribir sin puntos funciona; el sitio auto-formatea.

**Paso B**: aparecen los mismos campos que en editar, con defaults que hay que
sobrescribir siempre (Inicio Contrato = hoy, AFP "Uno", Salud "Sin
Información", Sueldo "0", Sexo "Masculino").

⚠️ Cargo y Tiendas **no existen en el DOM hasta confirmar un Proveedor**
(botón ">"). `confirmar_proveedor_seleccionado()` espera con
`wait_for_function` a que aparezca "Categoría Trabajador:" (con solo
`networkidle` todas las filas salían `OMITIDO_CARGO`).

### 11.4 Verificación del guardado (`campos_formulario.py`)

- 🔴 **`verificar_guardado_exitoso()`**: el sitio no cambia de URL al guardar;
  si falla la validación, el formulario sigue abierto. Tras cada Guardar se
  comprueba que no haya errores DevExpress visibles y que `#btnGuardar` ya no
  esté visible; si no, `ERROR` con el motivo. En "Crear" además se vuelve a
  buscar el RUT en la grilla como confirmación positiva.
- 🔴 **Popup "Operación Exitosa"** tras cada Guardar: si no se cierra, su
  overlay bloquea todos los clics siguientes. `cerrar_popup_operacion_exitosa()`
  espera con `wait_for_selector(state="visible")` a
  `#btnExitoAceptar_grillaExternosProveedorTrabajadores` (o variante `_2`) y
  lo acepta. También se llama defensivamente desde `cerrar_formulario()`.
- `autocompletar_campos_negocio(df)` (tras `cargar_excel()`): Fin Contrato
  vacío → Inicio + 89 días; Sueldo Base vacío → 0. Deja nota en el reporte.
- `sys.stdout/err.reconfigure(encoding="utf-8", errors="replace")` al inicio
  de `crear_o_editar.py`: evita que un error de Playwright con caracteres no
  cp1252 termine el script.

### 11.5 Identidad preexistente ("identidad bloqueada")

La maestra de personas es compartida entre todos los proveedores de
LOGISTICA FALABELLA. Al confirmar en "Crear" un RUT ya registrado por otro
cliente, el sitio **autocompleta Nombres/Apellidos/Sexo y los deja
`readonly`**. `crear_trabajador_nuevo` espera a que el formulario quede
editable o bloqueado con valor precargado y, si está bloqueado:
- Compara Nombres/Apellidos con el Excel (`normalizar_texto`).
- **Coinciden** → no toca identidad ni Sexo, llena el resto y guarda; la fila
  queda marcada como `preexistente`.
- **Difieren** → cierra el formulario y reporta `ERROR` con el detalle. No
  crea nada.

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

**Archivo → tipo** (`tipo_desde_nombre_archivo`, `documentos.py`): `_norm`
ignora mayúsculas, tildes y separadores (` `, `-`, `_`, `.`, `,`). Primero
busca coincidencia exacta con `CATALOGO_TIPOS_DOCUMENTO` (16 tipos, sin
prefijo); si no, recorre `_MAPEO_NOMBRE_TIPO` en orden (gana el primero):

| Patrón en el nombre | Tipo |
|---|---|
| `RIOHS` | TC Reglamento Interno RIOHS mandante |
| `IRL` / `EX ODI` | Registro de Capacitación IRL (Ex Odi) Mandante |
| `CONTACTO DE/EN CASO` | Contacto en caso de Emergencia |
| `MARCAJE BIOMETRICO` / `TOMA DE CONOCIMIENTO MARCA` | Toma de conocimiento marca en biometrico (EST) |
| `ENTREGA … EPP` | Registro Entrega EPP |
| `USO EPP` | Registro de Capacitación Uso EPP |
| `^C I` / `CEDULA` / `CARNET` | Cédula de Identidad |
| `ANEXO … PERSONAL EST` | Anexos de contrato personal EST |
| `ANEXO(S) (DE) CONTRATO` | Anexos de Contrato |
| `^CD` / `CPD` / `CONTRATO PUESTA A DISPOSICION` | Contrato puesta a disposición |
| `CONTRATO (DE) TRABAJO` | Contrato de Trabajo |
| `FINIQUITO` | Finiquito de Trabajo |
| `VISA` / `ATT` | Visa de trabajo o ATT |
| `COMPROBANTE … ENTREVISTA` | Comprobante de Entrevista del personal EST y OUT |
| `LIQUIDACION` | Liquidaciones de Sueldo |

- **Contrato de Trabajo (15/09/2026)**: los archivos llegan como "Contrato
  Trabajo", sin el "de". En el sitio el tipo que debe elegirse es
  explícitamente **`LOGISTICA FALABELLA/Contrato de Trabajo`**. La regla
  acepta ambas formas. Las reglas de **anexos van antes** que las de
  contratos para que "Anexo contrato trabajo" no se tome como contrato.
- `_seleccionar_tipo_en_combo` elige la opción del `<select>` quitando el
  prefijo `LOGISTICA FALABELLA/` y comparando el resto **exacto** (tras
  normalizar). Si el sitio renombra un tipo, hay que cambiarlo también en
  `CATALOGO_TIPOS_DOCUMENTO`.
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

### 11.9 Una sola visita a la vista de documentos por persona

`gestionar_documentos_trabajador(page, rut, grupo, limpiar=, verificar=,
items=, ...)` abre la vista UNA vez y hace, en este orden: **borrar → leer
tipos → subir** (si se leyera antes de borrar, lo recién borrado contaría como
"ya lo tenía" y se omitiría la subida). Los tipos se leen una sola vez y se
pasan a la subida (`tipos_ya_leidos`). Vuelve a la grilla en un `finally`.
Internas: `_limpiar_en_vista_abierta`, `_leer_tipos_en_vista_abierta`,
`_subir_en_vista_abierta` (arranca cerrando diálogos y esperando overlays),
`_volver_a_trabajadores`.

Las funciones públicas `limpiar_documentos_trabajador`,
`tipos_documentos_existentes` y `subir_documentos_trabajador` siguen
existiendo como envoltorios. La carpeta de la persona se busca antes de
navegar: si no existe, no se entra a la vista. Firma de la subida: devuelve
4 valores (`accion`, `subidos`, `ya_existian`, `errores`).

### 11.10 Interfaz gráfica (`interfaz.py`)

- 3 modos, selector de Excel / reporte / carpeta (solo en modo documentos),
  checkbox `--no-guardar`, checkbox "verificar documentos" y menú de limpieza
  (No tocarlos / Solo anotarlos / Borrarlos) — estos dos solo fuera del modo
  Comparación. Borrar pide confirmación extra al Iniciar.
- Corre los modos como subproceso en un hilo aparte y muestra su stdout; la
  barra de progreso lee las líneas `[i/N] ...`.
- **"Abrir Chrome de depuración"**: busca `chrome.exe` en `%ProgramFiles%`,
  `%ProgramFiles(x86)%` y `%LOCALAPPDATA%`; si no lo encuentra, permite
  elegirlo a mano (lo recuerda en la sesión). Los `.bat` usan la misma
  búsqueda.
- **"Cancelar proceso"**: pide confirmación y ejecuta
  `taskkill /F /T /PID <pid>` (el `/T` termina también el driver Node.js de
  Playwright). No afecta al Chrome de depuración.
- **"¿Cómo se usa?"**: ventana `CTkToplevel` aparte (una sola instancia). El
  texto vive en la constante `AYUDA` (lista de `(título, [párrafos])`); los
  párrafos que empiezan con `⚠` se pintan en rojo. El ícono se pone con
  `after(250, ...)` porque customtkinter lo pisa en Windows.

### 11.11 Chrome de depuración

`--user-data-dir` DEBE ser una ruta absoluta: desde un shell que no expande
`%LOCALAPPDATA%` (Git Bash), Chrome responde *"DevTools remote debugging
requires a non-default data directory"* y no abre el puerto 9222.
```
chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\Users\GC\AppData\Local\ChromeDebugShiftLaboral" <url>
```
La sesión de ShiftLaboral se cae cada cierto tiempo (sesión única) → volver a
iniciar sesión.

### 11.12 Empaquetado con PyInstaller

- **`app_entry.py`** como dispatcher: empaquetado, `sys.executable` es el
  propio `.exe`, así que `interfaz.py` (`_comando_base_modo`) se relanza con
  `[sys.executable, "--modo-crear", ...]`; en desarrollo usa
  `[sys.executable, "-u", "app_entry.py", "--modo-crear", ...]`.
  `buscar_y_comparar.main(argv=None)` y `crear_o_editar.main(argv=None)`
  aceptan argumentos.
- Sin consola: `.exe` compilado con `console=False` y subproceso con
  `creationflags=subprocess.CREATE_NO_WINDOW`. Playwright ya soporta
  `sys.frozen` y oculta la consola de su driver.
- `ShiftLaboralBot.spec` calcula en tiempo de build la ruta de
  `playwright/driver` (se agrega con `--add-data`, PyInstaller no la detecta)
  e incluye `collect_data_files('customtkinter')`.
- **Formato carpeta** (`exclude_binaries=True` + `COLLECT`), no onefile: el
  onefile descomprimía ~7.400 archivos en `%TEMP%` en cada apertura (dos veces,
  por el relanzamiento) y tardaba ~18 s en mostrar la ventana. En carpeta:
  ~1 s. Lista `EXCLUIDOS` (jedi, IPython, ipykernel, zmq, PIL, pygments,
  setuptools…); si algún día se usa algo de esa lista (p. ej. `CTkImage`),
  sacarlo de ahí. `upx=False`.
- Cerrar el programa antes de construir (`construir_exe.bat` usa
  `--noconfirm`).

## 12. PENDIENTES (actualizado 15/09/2026)

Rama `main`. Todo lo anterior está implementado y validado en vivo salvo lo
que se indica aquí.

### Prioridad ALTA
1. **Lote real grande (5-10+ personas)** con crear/editar +
   `--subir-documentos` (+ `--limpiar-documentos borrar` sobre alguna
   identidad preexistente). Hasta ahora las corridas fueron de 1-2 personas;
   los bugs de timing/overlay de este sitio suelen aparecer con iteraciones
   repetidas.
2. **Validar en vivo `gestionar_documentos_trabajador` (11.9)** con UNA
   persona y los tres flags juntos antes de usarlo en lote. Los tests solo
   cubren el orden con funciones simuladas.
3. **Validar en vivo "Contrato Trabajo" (11.7)**: subir a una persona un
   archivo con ese nombre y confirmar en la grilla que queda como
   `LOGISTICA FALABELLA/Contrato de Trabajo`.
4. **Probar el `.exe` con un modo real** (crear/editar y/o subir documentos)
   con sesión iniciada. Solo se validó que llega a conectar a Chrome.
5. **Guardado real de identidades bloqueadas** (`22708167-8`, `11847694-8`,
   11.5): validado con `--no-guardar`, falta confirmar con Guardar real. Si
   AFP / Sistema de Salud quedan en su default ("Uno" / "Sin Información"),
   reabrir: fue un bug reportado que no se pudo reproducir el 08/09/2026.

### Prioridad MEDIA
6. **Reconciliar `SHIFT.xlsx` vs carpetas de documentos** antes de subir
   (hoy el aviso de faltantes es posterior, no una verificación previa).
7. **Completar `_MAPEO_NOMBRE_TIPO`** a medida que aparezcan nombres de
   archivo nuevos; correr `test_datos.py` después de cada cambio.
8. **Decidir si `--no-guardar` debe forzar la limpieza a `listar`** (hoy no
   protege el borrado; cambiarlo alteraría un comportamiento existente).

### Prioridad BAJA
9. **Período de tipos Mensual/Anual** (Liquidaciones, EPP anual): sin
   verificar qué guarda el sitio.
10. **Refactor opcional**: sacar los globales de opciones de
    `crear_o_editar.py` a un dataclass y partir su `main()` en
    `procesar_fila()`. Solo si el archivo sigue creciendo y con más tests.
11. **`SHIFT.xlsx`**: se versiona como template vacío (`!SHIFT.xlsx` en
    `.gitignore`). El archivo con datos reales nunca se commitea
    (`git update-index --skip-worktree SHIFT.xlsx`); respaldo local en
    `SHIFT.datos.local.xlsx`.
