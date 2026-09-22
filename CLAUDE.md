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
python crear_o_editar.py --input SHIFT.xlsx [--no-guardar] [--limpiar-documentos [listar|borrar]] [--verificar-documentos] [--subir-documentos CARPETA] [--solo-chequear]
```

**Tests**: `python test_datos.py` (o `python -m pytest test_datos.py`) cubre
las funciones puras — interpretación del Excel y mapeo nombre de archivo →
tipo de documento (`normalizar_sexo`, `formatear_fecha`,
`autocompletar_campos_negocio`, `_norm`, `tipo_desde_nombre_archivo`,
`_buscar_carpeta_persona`, `preparar_items_carpeta`, orden de
`gestionar_documentos_trabajador` con funciones simuladas). No abre Chrome:
se puede correr en cualquier momento. **Correrlo siempre después de tocar
`tipos_documento.py`.** Navegación, selectores y timing NO tienen tests: solo
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
   🔴 **Coincidencia exacta (22/09/2026)**: `buscar_rut` cuenta celdas cuyo
   texto (sin puntos/espacios, en mayúsculas) es el RUT exacto y celdas que
   solo lo contienen. Si hay alguna parcial de más (p. ej. `11234567-8` al
   buscar `1234567-8`), lanza `RutAmbiguoEnGrilla` y la fila queda en ERROR
   sin tocar nada: los botones "ver"/"editar"/link RUT usan `.first` y podrían
   abrir a otra persona. Antes era `td:has-text(rut)` (substring). Falta
   validarlo en vivo.
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
- Combos Sexo/AFP/Isapre: `escribir_combobox_simple(page, frag, valor, etiqueta)`
  (clic en `[id*="cbXxx"][id$="_I"]` + clic real en el `.dxeListBoxItem`
  visible del combo cuyo texto coincide sin tildes ni mayúsculas). Valor vacío
  o inexistente → `CampoNoCompletado` con el campo y el valor; el reporte lo
  muestra como "No se pudo completar el formulario: …" (antes, una celda vacía
  buscaba `text=nan` y calzaba con el aviso oculto `#alerta_jornadas`).
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
- Compara Nombres/Apellidos con el Excel (`normalizar_texto`: ignora
  mayúsculas, tildes —incluida la de la ñ— y espacios de más; 21/09/2026,
  antes "HENRIQUEZ" vs "Henríquez" daba identidad distinta).
- `cargar_excel` deja NOMBRES y apellidos con `formatear_nombre_propio`
  (sin tildes, mayúscula inicial por palabra, conserva la ñ): así se escriben
  en el sitio al crear o editar.
- **Coinciden** → no toca identidad ni Sexo, llena el resto y guarda; la fila
  queda marcada como `preexistente`.
- **Difieren** → cierra el formulario y reporta `ERROR` con el detalle. No
  crea nada.

### 11.6–11.9 Documentos (limpieza, carga masiva, anti-duplicado, chequeo previo)

Detalle en `.claude/rules/documentos.md` (se carga al trabajar con `documentos.py` o `test_datos.py`; leerlo antes de tocar la lógica de documentos desde otro archivo).

- ⚠️ Desde el 22/09/2026, `--no-guardar` **sí protege el borrado**: con `--limpiar-documentos borrar` se listan los documentos que se borrarían y, con el primero, se prueba el clic en borrar y se aprieta **Cancelar** en la confirmación (`_probar_clic_borrar_y_cancelar`); Aceptar nunca se aprieta. Sin `--no-guardar`, `borrar` elimina de verdad.

### 11.10 Interfaz gráfica y 11.12 Empaquetado

Detalle en `.claude/rules/interfaz-empaquetado.md` (se carga al trabajar con `interfaz.py`, `app_entry.py`, `ShiftLaboralBot.spec` o `construir_exe.bat`).

### 11.11 Chrome de depuración

`--user-data-dir` DEBE ser una ruta absoluta: desde un shell que no expande
`%LOCALAPPDATA%` (Git Bash), Chrome responde *"DevTools remote debugging
requires a non-default data directory"* y no abre el puerto 9222.
```
chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\Users\GC\AppData\Local\ChromeDebugShiftLaboral" <url>
```
La sesión de ShiftLaboral se cae cada cierto tiempo (sesión única) → volver a
iniciar sesión.

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
   El 22/09/2026, corriéndolo a mano desde una terminal, aparecieron dos
   errores que mataban la corrida **después** de hacer el trabajo
   (`OSError: [Errno 22]` al imprimir y `EOFError` en la confirmación del
   chequeo previo): ya están corregidos y documentados en
   `.claude/rules/interfaz-empaquetado.md`, pero falta volver a probar el
   `.exe` reconstruido.
5. **Guardado real de identidades bloqueadas** (`22708167-8`, `11847694-8`,
   11.5): validado con `--no-guardar`, falta confirmar con Guardar real. Si
   AFP / Sistema de Salud quedan en su default ("Uno" / "Sin Información"),
   reabrir: fue un bug reportado que no se pudo reproducir el 08/09/2026.

### Prioridad MEDIA
6. ~~Reconciliar `SHIFT.xlsx` vs carpetas antes de subir~~ → hecho con el
   chequeo previo (11.8b). Falta usarlo en un lote real.
7. **Completar `tipos_documento.py`** (palabras clave por tipo) a medida que
   aparezcan nombres de archivo nuevos; correr `test_datos.py` después de cada cambio.
8. ~~Decidir si `--no-guardar` debe proteger el borrado~~ → hecho (22/09/2026):
   en modo prueba se lista y se prueba el clic en borrar cancelando la
   confirmación. Falta validar en vivo el selector `#btnConfirmacionBorrarCancelar`
   (o `_2`). En modo prueba se guarda además una captura del panel de carga en
   `capturas/` (ignorada por git).

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
