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

Este archivo es el contexto de proyecto para Claude Code. Léelo completo antes de tocar código.

## 0. Comandos y arquitectura técnica (referencia rápida)

**Instalación** (una vez por computador; en algunos equipos `pip`/`playwright`
sueltos no están en el PATH — usar `python -m pip` / `python -m playwright`):
```
python -m pip install -r requirements.txt
python -m playwright install chromium
```

**Ejecutar el bot** (opción recomendada para el usuario final, sin Python
instalado): `dist/ShiftLaboralBot.exe` (ver sección 12.15 — construirlo con
`construir_exe.bat`). Mismo botón de "Abrir Chrome", mismos 3 modos, log en
vivo y barra de progreso, sin ninguna ventana de consola detrás.

**Ejecutar el bot en desarrollo** (con Python instalado, un solo doble-click):
```
ejecutar_interfaz.bat
```
Abre la interfaz gráfica (`interfaz.py`, ver sección 12.11): botón para abrir
Chrome en modo depuración con perfil separado, selector de Excel/carpeta,
3 modos (Comparación / Creación-edición / Subir documentos), log en vivo y
barra de progreso. `ejecutar_bot.bat` (Fase 1 sola, consola con prompts) y
`ejecutar_crear.bat` (Fase 2 sola, menú de consola) siguen funcionando para
quien prefiera la consola.

**Ejecutar el script directamente** (requiere Chrome ya abierto con
`--remote-debugging-port=9222` y sesión iniciada — ver sección 8.2 y README.md):
```
python buscar_y_comparar.py --input colaboradores.xlsx --output reporte.xlsx
```

**Tests**: `python test_datos.py` (o `python -m pytest test_datos.py`) cubre
las funciones puras — las que interpretan el Excel y las que mapean nombre de
archivo → tipo de documento (`normalizar_sexo`, `formatear_fecha`,
`autocompletar_campos_negocio`, `_norm`, `tipo_desde_nombre_archivo`,
`_buscar_carpeta_persona`, `preparar_items_carpeta`). No abre Chrome ni entra
al sitio: se puede correr en cualquier momento, sin sesión y sin riesgo.
**Correrlo siempre después de tocar `_MAPEO_NOMBRE_TIPO`.** Todo lo demás
(navegación, selectores, timing) NO tiene tests y solo se puede validar
corriéndolo contra el sitio real con un Excel de pocas filas (ver sección
8.2). No hay linter ni build configurados.

**Arquitectura**: `shift_common.py` concentra lo compartido entre
`buscar_y_comparar.py` (Fase 1) y `crear_o_editar.py` (Fase 2) — conexión a
Chrome, navegación por menú, selección de Grupo Proveedor, búsqueda de RUT,
normalización de texto y escritura del reporte Excel. No se ejecuta solo, los
dos scripts principales lo importan. Esto se extrajo para no duplicar código
entre ambas fases (antes cada script tenía su propia copia idéntica de estas
funciones).
- Se conecta a una instancia de Chrome ya corriendo vía Playwright
  `connect_over_cdp` (puerto 9222) — nunca lanza su propio navegador ni maneja
  login/contraseñas (`conectar_a_chrome_existente`, en `shift_common.py`).
- Bloque `CONFIGURACIÓN` al inicio de cada script: selectores DOM y constantes
  de negocio *específicos de esa fase* (los compartidos están en
  `shift_common.py`), sincronizado con sección 6/7/12 de este archivo.
- Flujo secuencial por fila del Excel (sin paralelismo, por el límite de sesión
  única del sitio): **selección automática del grupo/proveedor**
  (`seleccionar_grupo_proveedor`, ver sección 6) → filtrar por RUT → si existe,
  abrir vista "ver" y extraer datos → comparar contra el Excel → acumular
  `ResultadoFila` → seguir con la siguiente fila aunque una falle (`try/except`
  por fila en `main()`).
- Extracción de datos vía patrón DOM genérico `td:text-is('Etiqueta:') + td`
  (mapeado en `ETIQUETAS_DETALLE`), no vía API — no existe una para este sitio
  (sección 4).
- Salida: reporte Excel coloreado por estado (`escribir_reporte`,
  `COLORES_ESTADO`), nunca modifica el sistema origen (fase actual es solo
  lectura, sección 8.4).
- `ejecutar_bot.bat`: launcher de un click. Usa un perfil de Chrome separado
  para no chocar con las ventanas normales del usuario ni forzar cerrarlas.

## 1. Objetivo del proyecto

Empresa descarga datos de colaboradores desde la API de Talana y necesita cargarlos
en **ShiftLaboral** (`https://externoslof.shiftlabor.com/`), un sistema externo
de "Control Externos" de LOGISTICA FALABELLA que **no tiene API pública ni
importación masiva** — solo un formulario web de creación 1 a 1 (confirmado
tras exploración exhaustiva, incluyendo búsqueda de endpoints semi-documentados
en el JS del sitio: no existe ninguno usable para esto).

La solución es un **bot de automatización de navegador (RPA) con Playwright**,
NO un cliente de API, porque no hay API que consumir. Ver sección 4 para detalle
técnico de por qué se descartó esa vía.

**Meta final**: una app local que varios computadores (2 usuarios/cuentas)
puedan correr para crear/verificar colaboradores en lote, sin depender de que
alguien tenga acceso a Claude — es un script Python autocontenido.

## 2. Estado actual del proyecto

✅ Completado:
- Exploración completa del formulario de creación/edición/vista de trabajador.
- Mapeo de campos del formulario a variables de negocio (sección 5).
- Extracción de selectores DOM reales (sección 6).
- Catálogos de valores válidos para AFP, Sistema de Salud, Sede/Tienda (sección 7).
- Catálogo parcial de Cargo (~125 valores, con un par de huecos por truncamiento
  manual — **decisión de negocio: el Cargo lo escribe el usuario final a mano,
  sin validación de catálogo en el Excel**; si no calza exacto con el dropdown
  real al momento de crear, esa fila se omite y va a un reporte de errores).
- **Fase 1 (script actual, `buscar_y_comparar.py`)**: solo lectura. Busca RUT,
  compara Nombre, Apellidos, Sexo, AFP, Sistema de Salud, Sueldo Base,
  Proveedores, Cargo y Tiendas contra el Excel, genera reporte con 3 estados:
  OK / ADVERTENCIA / NO_ENCONTRADO. **Ya probado end-to-end contra el sitio
  real** (05/08/2026, con Claude in Chrome) — ver sección 8.

⏳ Pendiente (siguientes fases, en orden):
1. **Validar y corregir Fase 1** (búsqueda + comparación) contra el sitio real — ver sección 8, es la prioridad inmediata.
2. Fase 2: creación de colaboradores nuevos (cuando no se encuentra el RUT).
3. Fase 3: carga masiva de documentos por colaborador (aún sin diseñar, fuera de alcance por ahora).

## 3. Flujo de negocio acordado

```
Para cada colaborador del Excel:
  1. Seleccionar el filtro "Grupo Proveedor" correcto (hay 2 grupos/usuarios).
  2. Buscar el RUT en el grid de Trabajadores.
  3. Si NO existe -> (fase 2, futuro) crear con los datos del Excel.
  4. Si SÍ existe  -> Fase 1 actual:
       - Abrir vista de detalle (solo lectura, ícono "ver").
       - Extraer Nombre, Apellido Paterno, Apellido Materno, Sexo, AFP, Sistema
         de Salud, Sueldo Base, Proveedores, Cargo y Tiendas.
       - Comparar contra el Excel.
       - Si todo coincide -> estado OK.
       - Si algo no coincide -> estado ADVERTENCIA, con detalle de qué campo(s) difieren.
       - Un RUT duplicado NUNCA se actualiza automáticamente. Solo se reporta.
  5. Cualquier fila con Cargo que no calce exacto con el dropdown real -> se omite
     y se reporta como error (esto aplica en fase 2, creación).
```

## 4. Por qué RPA y no una API "no oficial"

Se evaluó explícitamente construir una API no oficial replicando los POST del
formulario. Se descartó por:
- El sitio es **ASP.NET WebForms clásico con DevExpress** (`__VIEWSTATE`,
  `__EVENTVALIDATION`, callbacks `Aspxcallbackpanel`), no hay capa de servicios
  JSON expuesta. Reconstruir esto a mano es frágil y se rompe con cualquier
  cambio de UI, sin aviso.
- Se buscó explícitamente en los scripts del sitio (`base_dev.js`, etc.)
  cualquier patrón `.asmx`, `.ashx`, `PageMethods`, `/api/` — solo se encontraron
  dos Page Methods menores (`Ajax.aspx/AyudaFuncionalidad`, `Ajax.aspx/InfoUsuario`),
  ninguno relacionado a trabajadores.
- Automatizar el navegador (lo que el usuario realmente ve/usa) es más lento
  pero mucho más resiliente a cambios internos de la plataforma.

## 5. Mapeo de campos de negocio → campos del formulario

🔴 **El template `SHIFT.xlsx` usa los encabezados y el orden de la "Planilla
Agosto"** (para que el usuario final copie y pegue el bloque sin remapear).
Hoja única, valores literales (NO fórmulas — se probó una versión con fórmulas
y se descartó por frágil). Orden de columnas:

```
rut | nombre | apellidoPaterno | apellidoMaterno | sexo | cargo | desde | hasta | centroCosto | sucursal | afp | isapre | sueldoBase | PROVEEDOR | TIENDA
```

`shift_common.cargar_excel()` traduce esos encabezados a los nombres internos
(`RENOMBRE_COLUMNAS_ENTRADA`) y normaliza el sexo (`normalizar_sexo`: `M`/`F`
→ `Masculino`/`Femenino`) al cargar, así el resto del código no cambió.
`centroCosto`/`sucursal` van solo para alinear el pegado; el bot los ignora.

| Columna template (interno) | Campo en ShiftLaboral | Sección del formulario |
|---|---|---|
| nombre (NOMBRES) | Nombres | Datos Trabajador |
| apellidoPaterno | Apellido Paterno | Datos Trabajador |
| apellidoMaterno | Apellido Materno | Datos Trabajador |
| sexo (SEXO) | Sexo | Datos Trabajador |
| desde (fechaContratacion) | Inicio Contrato | Datos Trabajador |
| hasta (fechaTermino) | Fin Contrato | Datos Trabajador (= fechaContratacion + 89 días) |
| afp (AFP) | AFP | Datos Trabajador |
| isapre (ISAPRE) | Sistema de Salud | Datos Trabajador |
| sueldoBase | Sueldo Base | Datos Trabajador |
| PROVEEDOR | Proveedores | Relación Clientes |
| cargo (CARGO) | (dropdown sin label visible) | Categoría Trabajador — el usuario pone el valor exacto del catálogo (`LOGISTICA FALABELLA/…`) a mano |
| TIENDA | (dropdown sin label visible) | Tiendas |

## 6. Flujo paso a paso verificado EN VIVO (05/08/2026, con Claude in Chrome)

Este flujo fue ejecutado punta a punta contra el sitio real, confirmando cada
selector y cada interacción. **Esto reemplaza y corrige la versión anterior de
esta sección**, que tenía al menos un ID incorrecto (ver paso 8).

⚠️ **Hallazgo crítico de interacción**: varios controles de este sitio (menú
lateral tipo acordeón, el ASPxComboBox de Proveedor) **NO responden a
`element.click()` ejecutado vía JavaScript puro** — no disparan el evento del
que dependen internamente (probablemente jQuery bind a `mousedown`/`mouseup`
reales, no al evento sintético de `.click()`). **Deben clickearse con un clic
de mouse real** (lo que Playwright hace por defecto con `locator.click()`,
que simula el evento a nivel de sistema/CDP, no `page.evaluate(() => el.click())`).
Si Claude Code usa `page.evaluate` para clickear algo y no funciona, este es el
motivo — cambiar a `locator.click()` normal.

### Paso 1 — Entrar al sitio
```
page.goto("https://externoslof.shiftlabor.com/Default.aspx")
```

### Paso 2 — Abrir el botón de menú (hamburguesa)
```
Selector: #icono_abrir_menu
```
Este SÍ funciona incluso con click programático simple. Es un `<a>` normal.

### Paso 3 — Entrar a la sección "Externos"
```
Selector: #mf_cab_01
```
⚠️ Este es el que **requiere clic real de mouse**, no `.click()` de JS. Con
Playwright, `page.locator("#mf_cab_01").click()` debería funcionar bien porque
Playwright simula clics reales. Confirmado visualmente: expande el submenú
mostrando "Proveedores", "Trabajadores", "Documentos Proveedor", "Marcas
Proveedor", "Resumen documentos proveedor".

### Paso 4 — Seleccionar "Trabajadores"
```
Selector: #mf_cab_ll_01_01
```
Este SÍ funciona con click programático (es un `<a href="javascript:__doPostBack(...)">`
real). Navega a `Funcionalidades/Externos/ProveedorTrabajador.aspx`.

### Paso 5 — Seleccionar Proveedor en el combobox superior izquierdo
```
Input del combo:  #MJJerarquia00_I
```
⚠️ **Requiere clic real de mouse** para abrir el dropdown (no funciona con
`.click()` de JS, igual que el paso 3). Al abrirse, aparecen las opciones como
filas de tabla dentro de `#MJJerarquia00_DDD_L_D`. Confirmado en el DOM que la
opción "Grupo Colchagua Empresa de Servicios Transitorios S.A." es la fila con
id `MJJerarquia00_DDD_L_LBI1T0` (índice 1; índice 0 es el placeholder
"Proveedor", índice 2 sería "Grupo Santa Cruz Outsourcing S.A.").

Con Playwright, la forma más robusta es NO depender de estos IDs de fila (que
dependen del orden y pueden no ser estables si cambia el listado de proveedores),
sino usar selección por texto visible dentro del dropdown ya abierto:
```python
page.locator("#MJJerarquia00_I").click()  # abre el dropdown
page.locator(f"text={nombre_proveedor_exacto}").click()  # ej. "Grupo Colchagua Empresa de Servicios Transitorios S.A."
```

⚠️ **Decisión de diseño (implementada en `buscar_y_comparar.py`,
`seleccionar_grupo_proveedor`)**: este paso SÍ está automatizado. Se probó
manual primero (pausa con `input()`) por decisión de negocio, pero luego se
revirtió a automático por preferencia explícita del usuario. La columna
`PROVEEDOR` del Excel puede traer un prefijo tipo `LOGISTICA FALABELLA/...`
(mismo formato que los catálogos de Cargo/Tienda); el script usa solo el texto
después de la última `/` para buscar la opción visible en el dropdown, ya que
ahí no aparece ese prefijo.

### Paso 6 — Se muestran los trabajadores
El grid se recarga vía callback AJAX (DevExpress). Esperar
`page.wait_for_load_state("networkidle")` tras la selección del paso 5.

**Nota de comportamiento observada**: si ya se seleccionó un proveedor antes en
la misma sesión del navegador, al volver a entrar a la página de Trabajadores
el grid puede aparecer YA poblado con la última selección (el estado queda en
sesión del servidor). No asumir que el combo siempre está en blanco — el script
debe seleccionar explícitamente el proveedor correcto en cada corrida de todas
formas, para no arrastrar una selección de una corrida anterior por error.

### Paso 7 — Buscar por Código (RUT)
```
Selector: #grillaExternosProveedorTrabajadores_DXFREditorcol2_I
```
Este SÍ funciona con interacción estándar (click + fill/type + Enter). No
requiere trato especial. Confirmado con RUT real `10016891-K`: filtra
correctamente el grid a exactamente 1 fila.

```python
filtro = page.locator("#grillaExternosProveedorTrabajadores_DXFREditorcol2_I")
filtro.click()
filtro.fill(rut)
filtro.press("Enter")
page.wait_for_load_state("networkidle")
```

### Paso 8 — Seleccionar "ver" (ícono de lupa)
🔴 **CORRECCIÓN IMPORTANTE**: el ID documentado en una versión anterior de este
archivo (`#grillaExternosProveedorTrabajadores_link_ver_0`) estaba
**incompleto/incorrecto**. El ID real confirmado en vivo es:
```
#grillaExternosProveedorTrabajadores_cell0_8_grillaExternosProveedorTrabajadores_link_ver_0
```
Sin embargo, este ID es largo y depende del índice de fila (`cell0`, `_0` al
final). Como el filtro de RUT siempre deja como máximo 1 fila visible, la forma
más robusta y simple es **no depender del ID completo**, sino seleccionar por
atributo estable:
```python
page.locator('a[title="ver"]').first.click()
```
Esto funciona igual de bien y es inmune a que cambien los prefijos de ID.
Confirmado con clic real (no fue necesario probar `.click()` de JS para este,
usar clic real de todos modos por consistencia).

### Paso 9 — Leer los valores desde la vista de detalle

🔴 **CORRECCIÓN IMPORTANTE (05/08/2026, segunda sesión de pruebas contra el sitio
real)**: el patrón original documentado aquí, `td:text-is('{etiqueta}') + td`
con Playwright locator, **falla específicamente para "Apellido Materno:"**.
Se probó contra 2 RUTs reales (`20562265-9` y `19940824-0`) y ambos dieron
extracción `None` para ese campo, aunque el valor estaba perfectamente visible
en pantalla (confirmado con Claude in Chrome). Causa raíz confirmada
inspeccionando el DOM en vivo: el `<td>` de "Apellido Materno:" envuelve la
etiqueta en un `<span id="..._lblApellidoMaterno_0">`, a diferencia de los
demás campos (Apellido Paterno, Sexo, AFP, Sistema de Salud, etc.), que son
texto plano directo dentro del `<td>`. Playwright's `:text-is()` prefiere el
elemento MÁS INTERNO que posee el texto exacto — como el `<span>` lo posee, el
`<td>` deja de calzar con `td:text-is(...)`.

**Solución implementada en `buscar_y_comparar.py`**: en vez del locator de
Playwright, usar `page.evaluate` con JS plano que compara `textContent.trim()`
del `<td>` directamente (sin importar si el texto es un nodo directo o está
envuelto en un `<span>`), y toma `nextElementSibling` para el valor:
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
Esto es lectura de DOM vía `page.evaluate`, no un clic — no aplica la
advertencia de la sección 6 sobre clics programáticos que no disparan eventos;
esa advertencia es solo para interacciones (clicks), no para leer contenido.

Resultado real obtenido en la prueba original (para contraste/testing, sigue
siendo válido como caso de referencia):
```json
{
  "Nombres:": "VIRGINIA JEANETTE",
  "Apellido Paterno:": "STELLA",
  "Apellido Materno:": "MONARES",
  "Sexo:": "Femenino",
  "AFP:": "Provida",
  "Sistema de Salud:": "Fonasa"
}
```

### Paso 10 — Leer Sueldo Base, Proveedores, Cargo y Tiendas

**Sueldo Base** sigue el mismo patrón `<td>Sueldo Base:</td><td>Valor</td>` que
los demás campos de "Datos Trabajador" — ya cubierto por `ETIQUETAS_DETALLE` y
la extracción vía `page.evaluate` del Paso 9, sin necesitar nada especial.

**Proveedores, Categoría Trabajador (Cargo) y Tiendas** son secciones aparte,
más abajo en la misma vista de detalle (hay que hacer scroll), y usan una
estructura totalmente distinta: listbox de DevExpress (`ASPxListBox`), no pares
`<td>`. Cada ítem visible tiene clase `dxeListBoxItem` y un id largo con un
fragmento ESTABLE que sirve para ubicarlo sin depender del índice de fila
(que sí es dinámico, ligado a `Aspxcallbackpanel`). Confirmado en vivo
05/08/2026 con Claude in Chrome, RUT `20562265-9`:

```
Proveedores:            id contiene "lstProveedores"
Categoría Trabajador:   id contiene "lstVerClientes"   (= Cargo)
Tiendas:                id contiene "listBoxTienda"
```

Puede haber más de un ítem seleccionado por campo (trabajador con más de un
proveedor/cargo/tienda) — extraer TODOS los `.dxeListBoxItem` visibles
(`offsetParent !== null`, para descartar el dropdown oculto del combo superior
de "Grupo Proveedor", que reutiliza el mismo texto/clase) cuyo id contenga el
fragmento, y unir con `", "`:
```python
page.evaluate(
    """(fragmento) => {
        return Array.from(document.querySelectorAll('.dxeListBoxItem'))
            .filter(e => e.offsetParent !== null && e.id.includes(fragmento))
            .map(e => e.textContent.trim());
    }""",
    id_fragmento,
)
```

⚠️ **Prefijo inconsistente**: el Excel trae `PROVEEDOR`, `CARGO` y `TIENDA` con
el prefijo `LOGISTICA FALABELLA/` (mismo formato del catálogo), pero el sitio
NO lo muestra igual en los 3: Proveedores y Tiendas vienen SIN prefijo, Cargo
SÍ lo trae. Se normaliza quitando el prefijo de ambos lados antes de comparar
(`quitar_prefijo_catalogo` en `buscar_y_comparar.py`).

Valores reales confirmados en la prueba (RUT `20562265-9`):
```json
{
  "Sueldo Base:": "0",
  "Proveedores": "Grupo Colchagua Empresa de Servicios Transitorios S.A.",
  "Cargo": "LOGISTICA FALABELLA/Operario de Bodega EST",
  "Tiendas": "LOF1 ACCESO1"
}
```
Nota: el valor de Cargo para este trabajador específico termina en "EST" — se
confirmó que NO es un truncamiento visual de CSS (el `textContent` completo
mide 42 caracteres), es el valor real guardado en el sistema para ese
trabajador. Si el Excel dice algo distinto (ej. "...Operario de Bodega" sin
"EST"), es una discrepancia de datos real, no un bug de extracción.

### Paso 11 — Cerrar la vista de detalle con #btnCancelar (crítico)

🔴 **BUG CONFIRMADO EN VIVO 05/08/2026, corrida real completa**: si después de
extraer los datos NO se cierra la vista de detalle, la fila queda "pegada" en
modo expandido/edición. Al filtrar el siguiente RUT, DevExpress reutiliza ese
mismo estado expandido para el NUEVO trabajador que ocupa la fila 0, en vez de
mostrar la fila colapsada normal (`tr.dxgvDataRow`) — su clase pasa a
`dxgvEditFormDisplayRow`. Esto causó dos fallas distintas observadas en la
misma sesión:
1. `buscar_rut` reportó "no encontrado" para un RUT que sí existía, porque el
   selector de detección dependía de `tr.dxgvDataRow` (ver Paso 7/corrección
   en `buscar_rut`: ahora se detecta por contenido de celda, no por clase de
   fila).
2. En la corrida siguiente, al filtrar OTRO trabajador con la fila todavía
   pegada en modo edición, la extracción de Sexo/AFP/Sistema de Salud devolvió
   el HTML/JS completo de los editores ASPxComboBox en vivo (miles de
   caracteres) en vez del valor simple, generando comparaciones sin sentido.

**Fix**: después de extraer los datos, cerrar explícitamente la vista con el
botón "Cancelar":
```python
page.locator("#btnCancelar").click(timeout=3000)
page.wait_for_load_state("networkidle")
```
Confirmado en vivo: tras este clic, la clase de la fila vuelve a
`dxgvDataRow`. Implementado en `cerrar_vista_detalle()`, llamado al final de
`extraer_datos_detalle()`. Como blindaje adicional, `buscar_y_comparar.py`
también descarta (trata como `None`) cualquier valor extraído de más de 300
caracteres, ya que ningún campo de negocio real es así de largo — evita que un
futuro caso similar contamine el reporte con falsos positivos en vez de
fallar de forma visible.

## 7. Resumen de selectores (tabla de referencia rápida)

| Elemento | Selector | ¿Requiere clic real (no JS)? |
|---|---|---|
| Botón menú hamburguesa | `#icono_abrir_menu` | No |
| Sección "Externos" (expandir) | `#mf_cab_01` | **Sí** |
| Link "Trabajadores" | `#mf_cab_ll_01_01` | No |
| Input combo Proveedor | `#MJJerarquia00_I` | **Sí** (para abrir) |
| Opción del combo Proveedor | `text={nombre exacto}` dentro del dropdown abierto | Sí (recomendado) |
| Filtro RUT en grid | `#grillaExternosProveedorTrabajadores_DXFREditorcol2_I` | No |
| Botón "ver" (fila filtrada) | `a[title="ver"]` (usar `.first`) | Recomendado clic real por consistencia |
| Grid principal | `#grillaExternosProveedorTrabajadores_DXMainTable` | — |
| Filas de resultado | `tr.dxgvDataRow` | — |

Filtros adicionales del grid (mismo patrón que RUT, no probados en esta sesión
pero mismo mecanismo esperado):
```
Filtro Tipo Código:      #grillaExternosProveedorTrabajadores_DXFREditorcol1_I
Filtro Nombres:          #grillaExternosProveedorTrabajadores_DXFREditorcol3_I
Filtro Apellido Paterno: #grillaExternosProveedorTrabajadores_DXFREditorcol4_I
Filtro Apellido Materno: #grillaExternosProveedorTrabajadores_DXFREditorcol5_I
```

Proveedores disponibles (texto exacto a usar en el selector por texto del paso 5):
- "Grupo Colchagua Empresa de Servicios Transitorios S.A."
- "Grupo Santa Cruz Outsourcing S.A."

Formulario de creación/edición completo (secciones, ya no en modo solo-lectura):
- "Datos Trabajador" (RUT, Nombres, Apellidos, Sexo, fechas, AFP, Salud, Sueldo)
- "Relación Clientes" → dropdown "Proveedores" (con botón ">" para confirmar selección)
- "Categoría Trabajador" → dropdown multi-select con checkboxes = **Cargo**
- "Tiendas" → dropdown multi-select con checkboxes = **Sede/Loaf**
- Botones "Cancelar" / "Guardar" al fondo del formulario

## 7. Catálogos de valores válidos

**AFP**: Provida, Habitat, Cuprum, Capital, Modelo, Planvital, Jubilado, Uno, Sin Información

**Sistema de Salud**: Cruz Blanca, Banmédica, Consalud, Ferrosalud, Vida Tres, Fonasa, Sin Información

**Sede/Tienda** (bajo LOGISTICA FALABELLA/): LOF1 ACCESO1, LOF2 ACCESO1, LOF3

**Cargo**: ~125 opciones bajo LOGISTICA FALABELLA/. Lista larga, no se valida en
Excel por decisión de negocio (ver sección 3). Si se necesita el catálogo
completo para otro propósito, extraerlo en vivo del dropdown en vez de confiar
en copias anteriores (hubo truncamiento manual al capturarlo la primera vez).

## 8. Cómo confirmar que el bot funciona (PRIORIDAD INMEDIATA)

El script `buscar_y_comparar.py` fue escrito con selectores extraídos del DOM
real, pero **nunca se ha ejecutado de punta a punta**. Antes de usarlo con
datos reales de producción, seguir este protocolo de verificación:

### 8.1 Preparar un Excel de prueba mínimo (3-5 filas)
Incluir a propósito:
- 1 RUT que se sepa que **existe** en ShiftLaboral y con datos que **coincidan**
  exactamente con lo que hay en Excel → debe resultar en `OK`.
- 1 RUT que **exista** pero con un dato deliberadamente distinto (ej. cambiar
  la AFP en el Excel) → debe resultar en `ADVERTENCIA` con el detalle correcto.
- 1 RUT que **no exista** (inventado, con dígito verificador válido para no
  chocar con validaciones de formato) → debe resultar en `NO_ENCONTRADO`.

**Caso de prueba real, verificado en vivo el 05/08/2026** (grupo "Grupo
Colchagua Empresa de Servicios Transitorios S.A."), usar como fila "debe dar OK":

| Columna Excel | Valor a usar |
|---|---|
| RUT | 10016891-K |
| NOMBRES | VIRGINIA JEANETTE |
| apellidoPaterno | STELLA |
| apellidoMaterno | MONARES |
| SEXO | Femenino |
| AFP | Provida |
| ISAPRE | Fonasa |
| PROVEEDOR | Grupo Colchagua Empresa de Servicios Transitorios S.A. |

Para forzar un caso `ADVERTENCIA`, duplicar la fila anterior pero cambiar, por
ejemplo, `AFP` a `"Habitat"` — el script debería reportar exactamente:
`"AFP no coincide (sistema: 'Provida' / excel: 'Habitat')"`.

Otro RUT válido del mismo grupo para tener un segundo dato de contraste:
`10104074-7` (DANIEL ROBERTO / AZU / POMMIER) — sus valores exactos de
Sexo/AFP/Salud no se registraron en esta sesión, extraerlos en vivo con el
propio script antes de armar el caso de prueba.

### 8.2 Correr en modo verbose / paso a paso
Recomiendo que Claude Code, al iniciar, corra el script con `--headed` (Playwright
visible, no headless) y agregue prints/pausas entre pasos la primera vez, para
observar visualmente que cada acción (filtrar, click en "ver", extracción)
hace lo esperado antes de confiar en la extracción automática.

### 8.3 Checklist de validación
- [ ] El script se conecta correctamente a Chrome vía CDP (puerto 9222).
- [ ] Selecciona el grupo/proveedor correcto antes de buscar cada RUT.
- [ ] El filtro de RUT efectivamente reduce el grid a 0 o 1 fila (nunca más).
- [ ] Al hacer click en "ver", se abre la vista de detalle sin errores.
- [ ] Los 6 campos personales se extraen con el valor correcto (comparar
      manualmente contra lo que se ve en pantalla en 2-3 casos).
- [ ] La comparación OK/ADVERTENCIA/NO_ENCONTRADO clasifica correctamente
      los 3 casos de prueba de la sección 8.1.
- [ ] El reporte Excel de salida tiene el color/formato esperado y es legible.
- [ ] Correr el script dos veces seguidas no dobla ni corrompe nada (es
      idempotente, porque es de solo lectura — pero confirmarlo).
- [ ] Verificar comportamiento si la sesión de Chrome se cae a mitad de la
      corrida (recordar: ShiftLaboral fuerza **sesión única por usuario** — si
      alguien más inicia sesión con el mismo usuario, la sesión actual se cae).

### 8.4 Reglas de seguridad a respetar (no negociables)
- El bot **nunca** debe manejar, guardar ni pedir contraseñas — siempre asume
  sesión ya iniciada manualmente por la persona.
- No correr múltiples instancias en paralelo con el mismo usuario (límite de
  sesión única confirmado en el sitio).
- Si algo fallа, el script debe **loguear el error y seguir con la siguiente
  fila**, nunca detener todo el lote silenciosamente ni dejar el navegador en
  un estado inconsistente sin avisar.

✅ **Fase 2 (creación/edición) aprobada explícitamente por el usuario** —
ver sección 12. La restricción de "solo lectura" que aplicaba aquí quedó
superada; sigue vigente todo lo demás de esta lista.

## 9. Archivos del proyecto

```
shift_common.py         — módulo compartido: conexión a Chrome, navegación,
                          búsqueda de RUT, normalización de texto y reporte.
                          NO se ejecuta solo, lo importan los dos scripts.
campos_formulario.py    — primitivas de lectura/escritura de campos del
                          formulario editar/crear (Fase 2): comboboxes,
                          multi-select, cerrar formulario. Sin lógica de
                          negocio. NO se ejecuta solo, lo importa crear_o_editar.py.
buscar_y_comparar.py   — script principal, Fase 1 (búsqueda + comparación)
ejecutar_bot.bat        — launcher de un click para Fase 1 (solo comparación)
crear_o_editar.py       — script Fase 2 (creación/edición), ver sección 12.
                          Acepta --no-guardar: llena el formulario pero NO
                          hace clic en Guardar (modo prueba, ver 12.6).
ejecutar_crear.bat      — launcher de un click para Fase 2, dedicado y separado
                          del anterior a propósito (repo: rama `Crear`).
                          Corre crear_o_editar.py SIN flags (Guardar real, sin
                          limpiar ni subir docs).
abrir_chrome.bat        — SOLO abre el Chrome de depuración (puerto 9222,
                          perfil separado) y pausa para el login. No corre
                          ningún script. Usarlo antes de ejecutar
                          "python crear_o_editar.py ..." a mano con
                          --limpiar-documentos / --subir-documentos / --no-guardar.
documentos.py           — módulo Fase 2 opcional: limpieza (--limpiar-documentos),
                          verificación (tipos_documentos_existentes) y carga
                          masiva (--subir-documentos) de documentos del
                          trabajador. Ver secciones 12.8-12.13 y 12.16 (las 3
                          cosas en una sola visita a la vista de documentos:
                          gestionar_documentos_trabajador). NO se ejecuta solo,
                          lo importa crear_o_editar.py.
interfaz.py             — interfaz gráfica (customtkinter) de escritorio: elegir
                          modo (Comparación / Creación-edición / Subir
                          documentos), Excel y carpeta, botón "Abrir Chrome",
                          log en vivo y barra de progreso. Corre los scripts
                          como subproceso (no reimplementa su lógica). Ver 12.11.
test_datos.py           — pruebas de las funciones puras (Excel + mapeo de
                          nombres de archivo a tipos). No toca el navegador.
                          Correr con `python test_datos.py`. Ver sección 0.
ejecutar_interfaz.bat   — launcher de un click para interfaz.py.
app_entry.py            — punto de entrada único del .exe empaquetado (ver
                          12.15): sin argumentos abre la interfaz, con
                          --modo-comparar/--modo-crear corre esa lógica y
                          termina. NO se usa corriendo los scripts sueltos
                          con Python, solo lo necesita interfaz.py cuando NO
                          está empaquetado (en el .exe, se relanza a sí mismo).
ShiftLaboralBot.spec    — receta de PyInstaller para armar el .exe. Ver 12.15.
construir_exe.bat       — corre PyInstaller y arma dist/ShiftLaboralBot.exe.
requirements.txt       — dependencias Python (incluye customtkinter, pyinstaller)
README.md              — instrucciones de uso para el usuario final (no técnico)
CLAUDE.md              — este archivo
```

## 10. Convenciones del proyecto

- Comentarios y mensajes de consola en español (el equipo y usuarios finales
  trabajan en español).
- Selectores y configuración centralizados al inicio del script, en la sección
  `CONFIGURACIÓN`, para poder ajustarlos rápido si el sitio cambia.
- Cualquier selector nuevo que se descubra/confirme debe documentarse en este
  archivo (sección 6/7), no solo dejarse en el código.
- **Código compartido entre Fase 1 y Fase 2 vive en `shift_common.py`**
  (conexión a Chrome, navegación por menú, selección de Grupo Proveedor,
  búsqueda de RUT, normalización de texto, escritura del reporte). Si se
  necesita ajustar alguna de esas piezas, hacerlo ahí — nunca duplicarla de
  nuevo en `buscar_y_comparar.py` o `crear_o_editar.py`, ambos la importan.
- **Primitivas de campos del formulario de Fase 2 viven en
  `campos_formulario.py`** (leer/escribir texto, combobox simple,
  multi-select, validar Cargo, cerrar formulario) — separadas de la lógica de
  negocio (`editar_trabajador_existente`/`crear_trabajador_nuevo` en
  `crear_o_editar.py`, que decide QUÉ campo tocar y con qué valor).
- **Lección general de este sitio**: si un botón/control parece no responder a
  una interacción esperada, probar con un clic real de Playwright
  (`locator.click()`) antes de asumir que el selector está mal — varios
  controles de ShiftLaboral (menú acordeón, combos DevExpress) no responden a
  clics disparados vía `page.evaluate(() => el.click())`. Esto ya costó tiempo
  de debugging una vez (ver sección 6), documentarlo evita repetirlo.

## 11. Estado de verificación de este documento

Las secciones 6 y 7 (selectores y flujo paso a paso) fueron **verificadas en
vivo contra el sitio real** el 05/08/2026, ejecutando cada paso con Claude in
Chrome y confirmando resultados (incluida una corrección a un ID que estaba
mal documentado en una versión anterior de este archivo — el botón "ver").
El resto del documento (catálogos, mapeo de campos, reglas de negocio) también
proviene de exploración en vivo pero no fue re-verificado en esta sesión
puntual. Ante cualquier duda, la fuente de verdad es siempre el sitio real, no
este documento.

## 12. Fase 2 — Creación y edición de colaboradores

Explorado en vivo el 05/08/2026 con Claude in Chrome (rama `Crear`). Repo
separado del flujo de Fase 1: habrá un script y un `.bat` propios
(`crear_o_editar.py` / `ejecutar_crear.bat`), sin tocar `buscar_y_comparar.py`
ni `ejecutar_bot.bat`, que quedan dedicados exclusivamente a comparar.

### 12.1 Flujo de negocio acordado

```
Para cada colaborador del Excel:
  1. Seleccionar el Grupo Proveedor correcto (igual que Fase 1).
  2. Buscar el RUT en el grid.
  3a. Si SE ENCUENTRA -> click en "editar" (lápiz):
        - Leer los valores ACTUALES del formulario (justo antes de tocar nada).
        - Validar el Cargo del Excel contra las opciones reales del catálogo
          (dropdown de Categoría Trabajador). Si NO calza exacto -> se omite
          la fila COMPLETA (no se edita ningún campo de esa persona) y se
          reporta como error/omitido.
        - Si el Cargo es válido: comparar cada campo (misma lógica de
          comparar_datos) y modificar SOLO los que difieren, dejando el
          resto intacto (nunca sobrescribir campos que ya coinciden).
        - Guardar (#btnGuardar).
  3b. Si NO SE ENCUENTRA -> click en "Crear" (botón abajo a la derecha de la
      grilla):
        - Validar el Cargo del Excel contra el catálogo real igual que en 3a
          -> si no calza, se omite la creación completa de esa persona.
        - Llenar el formulario vacío con TODOS los datos del Excel.
        - Guardar (#btnGuardar).
  4. En AMBOS casos, registrar en el reporte final qué se hizo: CREADO /
     EDITADO (con el detalle de qué campos cambiaron) / OMITIDO (Cargo
     inválido) / ERROR.
```

✅ **Decisión de negocio confirmada por el usuario** (no es un modo
"dry-run" separado en dos corridas): en una sola corrida, el script debe
**estar seguro de qué va a editar antes de tocar cualquier campo** — es
decir, calcular el diff completo contra los valores reales leídos del
formulario en ese momento, y solo entonces aplicar los cambios — y al
terminar, generar un reporte de **qué se editó/creó/omitió**, análogo al
reporte de Fase 1 pero orientado a acciones realizadas, no solo a
detectar discrepancias.

### 12.2 Vista "editar" (ícono lápiz) — campos y selectores confirmados

⚠️ **No se puede pasar de "ver" a "editar" directamente en la misma fila** —
hay que cerrar la vista abierta primero (botón `#btnCancelar`, ver sección 6
Paso 11) y volver a hacer clic en el ícono de editar desde la fila colapsada.
Confirmado en vivo: intentarlo sin cerrar deja la vista sin cambiar.

Al hacer clic en el ícono de editar (`a[title="editar"]`, junto al de "ver"),
los mismos campos de "Datos Trabajador" se vuelven inputs editables:

```
Nombres:            #txtNombres                 (input texto, ID ESTABLE)
Apellido Paterno:   #txtApellidoPaterno          (input texto, ID ESTABLE)
Apellido Materno:   #txtApellidoMaterno          (input texto, ID ESTABLE)
Sexo:               id contiene "cbSexo"         (ASPxComboBox)
Inicio Contrato:    #calendarioFechaInicio_txtCalendar   (ID ESTABLE)
Fin Contrato:       #calendarioFechaTermino_txtCalendar  (ID ESTABLE)
                    + checkbox "Indefinido" junto al campo
AFP:                id contiene "cbAFP"          (ASPxComboBox)
Sistema de Salud:   id contiene "cbIsapre"        (ASPxComboBox)
Sueldo Base:        #txtSueldoBase               (input texto, ID ESTABLE)
```
Los inputs de texto (`txtNombres`, `txtApellidoPaterno`, `txtApellidoMaterno`,
`txtSueldoBase`) y las fechas tienen **el mismo ID en Editar y en Crear** —
gran ventaja, un solo bloque de código sirve para ambos flujos. Los combobox
(Sexo/AFP/Isapre) tienen un id largo con fragmento estable (`cbSexo`, `cbAFP`,
`cbIsapre`) pero el resto del id cambia entre "editar fila existente"
(`..._ef0_..._cbSexo_0_VI`) y "crear nuevo" (`..._efnew_..._cbSexo_VI`) — usar
selección por fragmento (`[id*="cbSexo"]`), nunca el id completo.

Más abajo (scroll), igual que en "ver":
```
Proveedores:            #ASPxDropDownEdit3_I  (combo con checkboxes + botón ">" para confirmar)
Categoría Trabajador:   dropdown con checkboxes (Cargo) — mismo mecanismo que el combo de Grupo Proveedor
Tiendas:                dropdown con checkboxes — mismo mecanismo
```
🔴 **Crítico**: estos 3 dropdowns son **multi-select ACUMULATIVO** — hacer
clic en una opción **suma** al valor actual, no lo reemplaza (confirmado en
vivo: seleccionar una 2da opción de Categoría Trabajador dejó el input
mostrando `"Opción A;Opción B"`, separadas por `;`). Para dejar un ÚNICO valor
correcto hay que **desmarcar explícitamente cualquier checkbox ya marcado que
no sea el deseado**, no alcanza con marcar el nuevo. Esto aplica tanto a
Proveedores como a Categoría Trabajador y Tiendas.

Botones al fondo del formulario de edición: `#btnCancelar` (cierra sin
guardar, confirmado que revierte la fila a `dxgvDataRow` normal) y
**`#btnGuardar`** (CONFIRMADO EN VIVO por inspección de DOM — nunca se hizo
clic real en él durante la exploración, solo se leyó su id, para no modificar
datos reales sin autorización explícita de guardar).

### 12.3 Vista "Crear" (colaborador nuevo)

Botón "Crear" (`text=Crear`, esquina inferior derecha de la grilla) abre una
fila nueva arriba de la grilla, en 2 pasos:

**Paso A — Tipo Código + Rut**:
```
Tipo Código:  dropdown, default "Cédula Chilena (CI)"
Rut:          #txtRutVer_Raw  (input texto, ID ESTABLE)
              + botón ">" para confirmar (mismo patrón que Proveedores)
```
El campo Rut valida el formato en vivo (mensaje "RUT, Correcto" en verde) y
auto-formatea con puntos (`12345678-5` → `12.345.678-5`) — escribir sin
puntos funciona bien, no hace falta pre-formatear desde Python.

**Paso B — tras confirmar el RUT**, aparece el resto del formulario, **con
los mismos IDs que la vista "editar"** (`#txtNombres`, `#cbSexo`, etc. — ver
sección 12.2), todos vacíos salvo:
- Inicio Contrato: viene pre-llenado con la fecha de HOY — hay que
  sobrescribirlo con el valor del Excel.
- AFP: default "Uno". Sistema de Salud: default "Sin Información". Sueldo
  Base: default "0". Sexo: default "Masculino". Todos hay que sobrescribirlos
  siempre, nunca asumir que el default sirve.

⚠️ **Orden de dependencia confirmado**: "Categoría Trabajador" (Cargo) y
"Tiendas" **no aparecen en el formulario hasta que se confirma un Proveedor**
(botón ">" junto al combo Proveedores). Si el flujo intenta llenar Cargo/Tienda
antes de confirmar Proveedor, esos campos ni existen en el DOM todavía.

Botones: "Cancelar" (junto al Paso A, cierra sin guardar) y, al final del
formulario completo, **`#btnGuardar`** (mismo id que en editar).

### 12.4 Decisiones de negocio confirmadas

- **Cargo inválido al editar un trabajador existente**: se omite la fila
  COMPLETA (ningún campo de esa persona se toca), igual que la regla ya
  definida para creación (sección 3). Se reporta como omitido/error.
- **Flujo de una sola corrida**: no hay modo "dry-run" separado. El script
  calcula el diff contra los valores reales del formulario antes de tocar
  cualquier campo, aplica solo lo que difiere, y al final reporta qué se
  editó/creó/omitió (ver sección 12.1).
- **Multi-select (Proveedores/Cargo/Tiendas)**: por ahora se asume que cada
  trabajador tiene exactamente UN valor por campo (igual que las columnas del
  Excel, que traen un solo valor cada una) — el código debe desmarcar
  cualquier checkbox previo que no sea el deseado antes de marcar el nuevo.
  Si en el futuro se necesita soportar múltiples valores por campo, revisar
  esta sección primero.
- **Reseteo de vista tras guardar exitoso**: pedido explícito del usuario —
  después de un `CREADO` o `EDITADO`, el bot navega por el menú lateral
  (hamburguesa -> Externos -> Trabajadores, `resetear_vista_trabajadores()`
  en `crear_o_editar.py`) en vez de solo recargar la URL, para asegurar que
  el servidor quede en un estado limpio antes de procesar la siguiente fila.
  Como esto navega a una página nueva, el Grupo Proveedor seleccionado se
  pierde y se vuelve a seleccionar en la fila siguiente.

### 12.5 Bugs encontrados y corregidos durante la implementación (05/08/2026)

Probado en vivo con Claude in Chrome contra el RUT de prueba `20562265-9`
(Ana Laura), **sin hacer clic real en Guardar** en ningún momento (decisión
explícita: no modificar datos reales todavía). Se encontraron y corrigieron
3 bugs antes de llegar a ese punto:

1. **Checkbox y texto son elementos SEPARADOS.** Cada opción del checkbox
   list de Categoría Trabajador/Tiendas/Proveedores en el formulario
   editable NO es un único `.dxeListBoxItem` con checkbox+texto adentro —
   son DOS elementos `.dxeListBoxItem` consecutivos: uno clase `dxeC` (solo
   el `<input type="checkbox">`) y el siguiente clase `dxeT` (solo el
   texto). Leerlos/clickearlos como si fueran uno solo rompía la detección
   de qué está marcado y el click no marcaba nada. Fix: emparejar por
   posición en `obtener_opciones_multiselect()` y `establecer_multiselect_valor_unico()`.

2. **`_input_por_etiqueta()` asumía layout de tabla de 2 columnas.** Funciona
   para "Nombres:"/"Apellido Paterno:"/etc. (etiqueta y caja en la misma fila,
   `td` + `td`), pero "Proveedores:", "Categoría Trabajador:" y "Tiendas:"
   tienen la etiqueta en su propia línea y la caja DEBAJO, no al lado. Fix:
   en vez de asumir estructura de tabla, se toma el primer `input`/`select`
   visible que aparece después de la etiqueta en el orden del documento
   (`compareDocumentPosition`).

3. **Prefijo "LOGISTICA FALABELLA/" inconsistente entre vista de solo
   lectura y formulario editable.** En la vista "ver" (Fase 1), Proveedores
   y Tiendas NO traen el prefijo, pero Cargo sí (documentado en sección 6,
   Paso 10). **En el formulario de editar/crear, en cambio, los 3 SÍ traen
   el prefijo completo** — confirmado en vivo para Proveedores y Tiendas
   (antes se les quitaba el prefijo antes de buscarlos en el dropdown, lo
   que hacía que nunca se encontraran). Fix: en `crear_o_editar.py`, pasar
   siempre el valor COMPLETO del Excel (con prefijo) a
   `establecer_multiselect_valor_unico()` para los 3 campos, sin recortar.

4. **Botón de confirmar RUT en "Crear"**: id real confirmado en vivo es
   `#btnAceptaRut` (no un patrón adivinado por XPath). El input real
   editable del RUT es `#txtRutVer_I` — `#txtRutVer_Raw` es un input oculto
   (`type="hidden"`) que no hay que tocar directamente.

### 12.6 Segunda ronda de pruebas del script (07/09/2026, RUT `22710691-3`)

Pasada real de `crear_o_editar.py --no-guardar` (flag nuevo, ver abajo) contra
un colaborador nuevo del "Grupo Colchagua". El formulario se llenó completo y
correcto (13 campos, idénticos a una pasada manual de control con Claude in
Chrome), **sin clickear Guardar todavía**. Hallazgos:

5. **`--no-guardar` (modo prueba).** `crear_o_editar.py` ahora acepta
   `--no-guardar`: llena todo el formulario pero NO hace clic en `#btnGuardar`,
   deja el navegador/formulario abiertos y reporta estado `SIMULADO_CREAR` /
   `SIMULADO_EDITAR`. Es el modo con que se valida cada cambio antes de tocar
   datos reales. Sin el flag, el comportamiento es el de siempre (sí guarda).

6. 🔴 **Bug de timing en `confirmar_proveedor_seleccionado()`** (corregido).
   El botón `>` dispara un callback AJAX de DevExpress que INYECTA las
   secciones "Categoría Trabajador" y "Tiendas" en el DOM. `networkidle` +
   `time.sleep(0.5)` se cumplían ~0.5s ANTES de que esas secciones
   aparecieran (medido en vivo: aparecían a ~1.06s). Resultado:
   `validar_cargo_existe()` corría contra un DOM sin la sección, no encontraba
   la etiqueta, y **TODAS las filas se reportaban como `OMITIDO_CARGO`** aunque
   el Cargo existiera perfectamente en el catálogo. Fix: `confirmar_proveedor_
   seleccionado()` ahora hace `page.wait_for_function(...)` esperando a que
   aparezca la etiqueta "Categoría Trabajador:" antes de devolver. Mismo
   patrón de bug que el filtro de RUT / grid (secciones 7 y 11): en este sitio
   `networkidle` NO es señal fiable de "callback DevExpress terminó".

7. **Espera de ítems del listbox.** `obtener_opciones_multiselect()` y
   `establecer_multiselect_valor_unico()` reemplazaron su `time.sleep(0.3)`
   fijo tras abrir el dropdown por `_esperar_items_listbox()` (espera a que
   haya al menos un ítem con checkbox visible). El dropdown de "Categoría
   Trabajador" tiene ~122 opciones y a veces no alcanzaba a renderizar en
   0.3s → lista vacía → Cargo válido descartado.

8. **Fin Contrato es un input con datepicker de jQuery UI** (`class="inp
   hasDatepicker"`), NO un ASPxDateEdit de DevExpress. `escribir_campo_texto()`
   (Playwright `.fill()`) SÍ funciona en él. (Nota: interacción por teclado
   vía CDP crudo — fuera de Playwright — no "pega" en este campo; hay que usar
   `.fill()` o setear `.value` + eventos `input/change/blur`.)

9. **Los combos Sexo/AFP/Isapre SÍ responden a `escribir_combobox_simple()`**
   (abrir con click en el input `[id*="cbXxx"][id$="_I"]` + click en la opción
   por texto). Confirmado en la pasada del script.

10. **Catálogo de Cargo**: tiene 122 opciones e incluye TANTO
    `LOGISTICA FALABELLA/Operario de Bodega` COMO
    `LOGISTICA FALABELLA/Operario de Bodega EST` (son dos cargos distintos).
    Para "Operario de Bodega" de la planilla, el valor de negocio habitual es
    la variante **`EST`** — pero la decisión la toma el usuario final a mano en
    la planilla (ver 12.4), el bot solo valida contra el catálogo real.

11. **Sección "Marcas"** (dropdown + botón `>` + grilla "No existe
    información", debajo de Tiendas en el formulario de crear/editar):
    **fuera de alcance**, el bot NO la toca. No está en las columnas del Excel
    ni en los requerimientos.

12. **Lanzar el Chrome de depuración**: el `--user-data-dir` DEBE ser una ruta
    absoluta real. Si se pasa `%LOCALAPPDATA%\ChromeDebugShiftLaboral` desde un
    shell que no expande esa variable (p.ej. Git Bash), Chrome la rechaza con
    *"DevTools remote debugging requires a non-default data directory"* y NO
    abre el puerto 9222. `ejecutar_crear.bat` corre en cmd, donde sí expande —
    pero al invocar Chrome a mano usar la ruta completa
    (`C:\Users\<user>\AppData\Local\ChromeDebugShiftLaboral`).

✅ **Guardado real VALIDADO (07/09/2026).** Corrida final de
`crear_o_editar.py` SIN `--no-guardar`, 1 fila (RUT `22710691-3`, PABLO
IGNACIO ALFARO BAHAMONDE, Grupo Colchagua): estado `CREADO`. Verificado
después abriendo la vista "ver" del propio sistema — los 13 campos quedaron
guardados correctos (Sexo Masculino, Inicio 07/09/2026, Fin 05/12/2026, AFP
Uno, Salud Fonasa, Sueldo 0, Proveedor Grupo Colchagua, Cargo
"LOGISTICA FALABELLA/Operario de Bodega EST", Tienda "LOF1 ACCESO1"). El reset
post-guardado (`navegar_a_trabajadores_por_menu`: hamburguesa → Externos →
Trabajadores) también funcionó y dejó la vista lista para la fila siguiente.
El botón real es `#btnGuardar` y `crear_trabajador_nuevo()` lo clickea al final.

✅ **Edición con Guardar real VALIDADA (07/09/2026).** Sobre el mismo RUT
`22710691-3` recién creado: se cambió en el Excel `AFP` (Uno→Modelo) y
`sueldoBase` (0→550000), se corrió el script → estado `EDITADO: Campos
actualizados: Sueldo Base, AFP`. Verificado en la vista "ver": ambos campos
cambiaron y **todo el resto quedó intacto** (la lógica de "modificar solo lo
que difiere" funciona, no hubo falsos positivos en Proveedores/Cargo/Tiendas/
fechas/nombres). Después se revirtió al estado original con otra corrida
(EDITADO de vuelta a Uno/0).

### 12.7 Primer lote real (07/09/2026) — bug de "campo readonly" (corregido)

Lote de 6 filas de "Grupo Colchagua" (5 nuevas + PABLO ya existente).
Resultado: **3 CREADO, 1 SIN_CAMBIOS (PABLO), 2 ERROR**. Verificado contra el
sistema: los 3 CREADO existen, los 2 ERROR NO dejaron nada a medias, el manejo
de error por fila funcionó (el lote siguió tras cada fallo) y el reset entre
filas (`navegar_a_trabajadores_por_menu`) aguantó las 6 iteraciones.

🔴 **Las 2 filas que fallaban** (`22708167-8`, `11847694-8`): NO era una race
condition — era **determinista**. Esos RUT **ya existen en la maestra de
personas de ShiftLaboral** (registrados por OTRO cliente; la plataforma es
compartida entre todos los proveedores de LOGISTICA FALABELLA — verificado:
NO están en Colchagua ni en Santa Cruz). Al confirmar en "Crear" un RUT que la
plataforma ya conoce, el sitio **autocompleta Nombres/Apellidos/Sexo y los
deja `readonly`** (no se puede cambiar la identidad legal de una persona;
solo se la asocia al grupo). El código hacía `escribir_campo_texto('txtNombres', ...)`
sin condición → `.fill()` sobre un `readonly` → `Locator.fill: Timeout 30000ms
... element is not editable` → `ERROR`.

**Fix (07/09/2026, `crear_trabajador_nuevo`)**: tras `#btnAceptaRut` se espera
a que el form quede en uno de 2 estados (`wait_for_function`): campo editable
(RUT nuevo) **o** campo `readonly` con valor precargado (RUT ya en el
sistema). Si está bloqueado:
- Se **comparan** Nombres/Apellido Paterno/Apellido Materno del sistema contra
  el Excel (con `normalizar_texto`).
- **Coinciden** → se sigue el flujo SIN tocar identidad/Sexo; se llena el
  resto (Sueldo/AFP/Isapre/fechas/Proveedor/Cargo/Tienda) y se guarda.
  `detalle` lleva la nota "(identidad ya existía en ShiftLaboral y coincide…)".
- **Difieren** → `cerrar_formulario` y `ResultadoFila(estado="ERROR", ...)`
  con el detalle de qué campo difiere ("sistema: 'X' / excel: 'Y'"). No crea
  nada. (Comportamiento pedido explícitamente por el usuario.)

Bugs de apoyo corregidos en la misma tanda:
- **Crash de Unicode**: `print(f"... {e}")` de un error de Playwright reventaba
  con `UnicodeEncodeError` (consola cp1252 no puede con las flechas del call
  log) y **mataba todo el script**. Fix: `sys.stdout/err.reconfigure(
  encoding="utf-8", errors="replace")` al inicio de `crear_o_editar.py`.
- **Overlay del grid intercepta clics**: `dxgvLoadingDiv` tapando la grilla
  hacía fallar la apertura del dropdown de Cargo en la rama de edición. Fix:
  `_esperar_grid_sin_overlay()` en `campos_formulario.py`, llamado antes de
  abrir el dropdown en `obtener_opciones_multiselect` y
  `establecer_multiselect_valor_unico`.
- La `esperar_campos_formulario_editables()` sigue usándose en
  `editar_trabajador_existente` (tras el lápiz).

**Validado en `--no-guardar`** con el lote de 6: 4 `SIN_CAMBIOS`, 2
`SIMULADO_CREAR` (Matias y Cristian, identidad preexistente que coincide),
0 `ERROR`.

⚠️ **Aún sin cerrar**: la corrida REAL (sin `--no-guardar`) de esas 2 filas
(`22708167-8`, `11847694-8`) para confirmar que Guardar asocia bien a una
persona con identidad preexistente. Y validar un lote más grande.

⚠️ **Bug menor pendiente** (rama identidad-bloqueada): al "Crear" un RUM ya
conocido, además de Nombres/Apellidos también los combos **AFP y Sistema de
Salud quedan sin escribir** (se guardan con el default "Uno" / "Sin
Información"). La pasada de edición siguiente lo detecta y corrige
(`EDITADO: AFP, Sistema de Salud`), pero convendría arreglarlo para que quede
bien a la primera.

### 12.8 Limpieza de documentos de personas preexistentes (07/09/2026)

Requerimiento: si al "Crear" la persona YA EXISTE, después de editar sus datos
hay que **dejarla sin documentación** — borrar los documentos que el proveedor
subió en un registro anterior.

- **Vista**: `DocumentosTrabajador.aspx`. Se llega **clickeando el RUT en la
  grilla** (`a[id*="link_Codigo_0"]`), NO el lápiz. Tiene una grilla superior
  (checklist de tipos, no se toca) y una **grilla inferior** (`tr.dxgvDataRow`)
  con los documentos subidos.
- Cada fila tiene icono `ver` y, **solo si lo subió el proveedor**, también
  `borrar` (`a[title="borrar"]`). Los documentos cargados por el **mandante**
  no tienen `borrar` — no se pueden ni se deben tocar.
- **Popup de confirmación** (DevExpress, ya en el DOM): contenedor
  `#popupConfirmacionBorrar_grillaExternosDocumentosTrabajador`, confirmar
  `#btnConfirmacionBorrarAceptar`, cancelar `#btnConfirmacionBorrarCancelar`.
  Tras borrar aparece popup de éxito → `#btnExitoAceptar_grillaExternosDocumentosTrabajador`.
  (NO es `window.confirm` nativo.)
- **Módulo `documentos.py`** → `limpiar_documentos_trabajador(page, rut,
  grupo, borrar)`. Navega a la grilla, selecciona grupo, filtra el RUT, abre
  la vista de documentos y:
  - `borrar=False` → devuelve la lista de documentos borrables. No borra.
  - `borrar=True` → los borra uno por uno (clic borrar → confirmar → aceptar
    éxito), con guarda anti-loop (si el conteo no baja, corta). Al terminar
    vuelve a `BASE_URL`.
- **`crear_o_editar.py`**: flag `--limpiar-documentos [listar|borrar]` (default
  sin flag = no toca nada; `--limpiar-documentos` a secas = `listar`). Solo
  corre para filas con `ResultadoFila.preexistente=True` (rama de edición, o
  "Crear" con identidad bloqueada que coincide) y estado ≠ ERROR. El resultado
  se anexa a `detalle` ("Docs borrables (N): …" / "Docs BORRADOS (N): …").
- **Validado end-to-end (07/09/2026)**: `borrar` contra RUT `20401344-6`
  (Adán) → eliminó sus **9 documentos** del proveedor (Contrato de Trabajo,
  Cédula, Anexos, capacitaciones, etc.), dejó los del mandante, verificado
  "borrables restantes: 0".

Detalles de implementación que costaron encontrar (todos en `documentos.py`):
- **Aceptar el popup de éxito es obligatorio entre borrados.** Tras confirmar
  ("¿Está seguro?" → `#btnConfirmacionBorrarAceptar`) aparece
  "Operación exitosa … Aceptar". Si no se acepta, su **overlay
  `.ui-widget-overlay` (jQuery UI modal) queda tapando la grilla** y el
  siguiente clic en `borrar` falla con "intercepts pointer events". El botón
  real es **`#btnExitoAceptar_grillaExternosDocumentosTrabajador_2`** (un
  `<div class="btn_c">`, NO el `<a>` con id sin `_2`). Idem el de confirmación
  puede tener variante `_2`. Se prueban ambos.
- Antes de cada clic se espera a que no haya `.ui-widget-overlay`,
  `[class*="dxpcModalBackground"]`, `.modalExternos` ni
  `#grillaExternosDocumentosTrabajador_LD` visibles (`_esperar_sin_overlays`),
  y se cierra cualquier diálogo que haya quedado abierto (`_cerrar_dialogo_abierto`).
- **La grilla de documentos PAGINA** (10 por página; el ejemplo tenía 25 docs
  en 3 páginas). `page.locator('a[title="borrar"]').count()` solo ve la página
  actual. Se recorren todas las páginas (`_total_paginas` lee "Página X de N"
  del texto, `_ir_a_pagina` clickea el número en el pager
  `#grillaExternosDocumentosTrabajador`), tanto en `listar` como en `borrar`.
- Blindajes anti-loop: corta si el mismo documento se intenta borrar 2 veces
  seguidas (borrado sin efecto) y tope duro de 300 iteraciones.

### 12.9 Carga masiva de documentos (explorado 07/09/2026, rama `carga-masiva`)

Fase siguiente: tras limpiar los documentos viejos y crear/editar a la
persona, **subirle sus documentos nuevos** con el módulo de carga masiva del
propio sitio.

**Dónde**: en `DocumentosTrabajador.aspx` (misma vista de la limpieza, se
llega clickeando el RUT), botón **"Carga masiva documentos"** =
`#btnDocumentosMasivos_2` (un `<div class="btn_c">`; el `<a>` sin `_2` no
dispara). Abre un panel inline (`#panelCargaModalDocumentosMasivo`), NO una
página nueva — la URL sigue siendo `DocumentosTrabajador.aspx`.

**Flujo**:
1. Clic en `#btnDocumentosMasivos_2` → aparece el panel con botón "Examinar" y
   el `<input type="file">` **`#FileDocumentosTrabajadorMasivo`**
   (`accept=".pdf,.docx,.xlsx,.jpg,.png"`, oculto — con Playwright usar
   `set_input_files`, acepta múltiples).
2. Por cada archivo seleccionado aparece una fila `.ext-doc-ms-row` con índice
   N (0-based, en el orden de los archivos):
   | Campo | Selector | Nota |
   |---|---|---|
   | Nombre (a mostrar) | `#nombre_documento_masivo_{N}` | texto libre, obligatorio |
   | Período | `#calendario_documento_masivo_{N}` | input datepicker jQuery UI (`calendarioJS`), obligatorio; mismo trato que "Fin Contrato" (setear `.value` + eventos si `.fill()` no pega) |
   | Tipo documento | `#cboTipoDocumentos_{N}` | **`<select>` nativo** (¡fácil! `select_option`). value `-1` = sin elegir. 16 opciones `LOGISTICA FALABELLA/…` (Contrato de Trabajo, Cédula de Identidad, Anexos, Liquidaciones, Finiquito, etc. — el mismo catálogo del grid superior) |
   | ¿Tiene fecha de vencimiento? | `#chk_fecha_vencimiento_documento_masivo_{N}` | checkbox |
   | Fecha vencimiento | `#calendario_fecha_vencimiento_documento_masivo_{N}` | datepicker, solo si el checkbox está marcado |
   | Quitar este archivo | icono basura en la fila | descarta el archivo del lote |
3. **Guardar**: `#btnGuardarModalCargaMasivaDocumentos_2` (div). Cancelar:
   `#btnCancelarModalCargaMasivaDocumentos_2`.
4. Validaciones del sitio: "Debe completar los campos vacíos" (Nombre +
   Período + Tipo obligatorios por fila), "Debe seleccionar al menos un
   documento".
5. El sitio avisa: *"Debe actualizar la pagina en un par de minutos para
   visualizar los estados actuales de los documentos"* → el procesamiento es
   **asíncrono**; tras Guardar hay que esperar / recargar antes de verificar.

**IMPLEMENTADO Y VALIDADO EN VIVO (07/09/2026)** — flag `--subir-documentos
CARPETA` en `crear_o_editar.py`, funciones en `documentos.py`:

- **Estructura esperada** (carpeta real `Ingresos Lunes 07-09-2026/`, formato
  `Nombre_Apellido` por subcarpeta). Los archivos NO se llaman como el tipo
  del catálogo: usan abreviaturas (`C.I …`, `CD FALABELLA RETAIL`, `MARCAJE
  BIOMETRICO`, `irl …`, `riohs …`, `PROCEDIMIENTO USO EPP`, `Registro de
  entrega de EPP …`). Extensiones: `.pdf .docx .xlsx .jpg .jpeg .png`.
- **`_norm()`**: normaliza para calzar SIN sensibilidad a mayúsculas, tildes,
  ni al separador (` `, `-`, `_`, `.`, `,` son equivalentes). Se usa para
  carpeta↔persona y archivo↔tipo.
- **Carpeta → RUT** (`_buscar_carpeta_persona` en `crear_o_editar.py`): calce
  por conjunto de palabras `_norm` — la carpeta calza si sus tokens (≥2) son
  subconjunto de `nombre+apellidoPaterno+apellidoMaterno` del Excel. `Adan_Leon`
  → "ADAN LEON" ⊆ "ADAN IGNACIO LEON BRAVO". Sin carpeta / ambigua → se reporta.
- **Archivo → Tipo** (`tipo_desde_nombre_archivo`): 1) coincidencia exacta con
  un tipo del catálogo (`CATALOGO_TIPOS_DOCUMENTO`, 16 tipos), si no 2) tabla
  `_MAPEO_NOMBRE_TIPO` (lista de regex → tipo, evaluada en orden). Cubre el set
  estándar de ingreso confirmado por el usuario (07/09/2026, carpeta
  `Adan_Leon`, 8 documentos, 0 omitidos):
  | patrón en el nombre | tipo |
  |---|---|
  | `RIOHS` | TC Reglamento Interno RIOHS mandante |
  | `IRL` / `EX ODI` | Registro de Capacitación IRL (Ex Odi) Mandante |
  | `CONTACTO DE/EN CASO` | Contacto en caso de Emergencia |
  | `MARCAJE BIOMETRICO` | Toma de conocimiento marca en biometrico (EST) |
  | `ENTREGA … EPP` | Registro Entrega EPP |
  | `USO EPP` | Registro de Capacitación Uso EPP |
  | `^C I` / `CEDULA` / `CARNET` | Cédula de Identidad |
  | `^CD` / `CPD` / `CONTRATO PUESTA A DISPOSICION` | Contrato puesta a disposición |
  Archivo que no calce → se omite y se reporta (no frena al resto).
- Corre para filas con estado `CREADO`/`EDITADO`/`SIN_CAMBIOS`. Con
  `--no-guardar` llena el form pero hace Cancelar.

🔴 **Detalles que costaron (todos en `documentos.py`)**:
- **Período**: los usuarios reales lo dejan VACÍO en la carga masiva. Por eso
  `dejar_periodo_vacio=True` (default) → el bot NO lo llena. **NO verificado en
  vivo** que el sitio acepte Período vacío (a fecha 07/09/2026 no había sesión
  para probar) → fallback: si al Guardar aparece "Debe completar los campos
  vacíos", el bot llena el Período (con `fechaContratacion`) y reintenta una
  vez. Reporte: `subido` (vacío funcionó) vs `subido_con_periodo` (hubo que
  llenarlo) vs `rechazado`.
- La **"Fecha de vencimiento" SÍ es OBLIGATORIA** — desmarcar la casilla
  `#chk_fecha_vencimiento_documento_masivo_{N}` por JS + `change` +
  `ComplentarInfo(N)` NO la libera (queda `input-error`). Se llena SIEMPRE con
  `fechaTermino` (o `fechaContratacion` si no hay).
- **Período** y **Fecha vencimiento** son inputs datepicker de jQuery UI
  (`.hasDatepicker`). Setear `.value` por JS no basta: hay que
  `jQuery(inp).datepicker('setDate', new Date(y,m-1,d))`. Aun así, para tipos
  **"1 sola vez"** (Contrato, Cédula) el sitio guarda el Período como
  `04/01/1990` (el del tipo) sin importar lo que se ponga — parece ser por
  diseño; sin verificar para tipos Mensual/Anual.
- Tras `set_input_files` esperar a que aparezcan TODAS las filas
  (`#cboTipoDocumentos_{len-1}`). El `<select>` de Tipo es NATIVO
  (`select_option`, fácil).
- Guardar es `#btnGuardarModalCargaMasivaDocumentos_2`; procesamiento
  **asíncrono** (~1-2 min) — verificar recién después.

✅ Validado: subió "Contrato de Trabajo" + "Cédula de Identidad" a
`22710691-3` (2 veces), verificado en la grilla, y después limpiado con
`--limpiar-documentos borrar`.

### 12.10 Autocompletado de negocio + verificación real de guardado (08/09/2026)

Sesión de endurecimiento de `crear_o_editar.py`/`campos_formulario.py` a partir
de datos reales del Excel que traían columnas vacías, y de una corrida real
que reportó éxito sin haber guardado.

- **`autocompletar_campos_negocio(df)`** (crear_o_editar.py), corre justo
  después de `cargar_excel()`: si `fechaTermino` viene vacía, se calcula como
  `fechaContratacion + 89 días` (misma regla de negocio de la Planilla
  Agosto); si `sueldoBase` viene vacío, se interpreta como `0` (antes
  quedaba como el string literal `"nan"` escrito tal cual en el campo Sueldo
  Base — bug real, encontrado con un Excel de prueba de 2 filas). Deja una
  nota en el reporte de cada fila afectada ("Fin Contrato autocompletado...",
  "Sueldo Base autocompletado a 0...").
- 🔴 **`verificar_guardado_exitoso()`** (campos_formulario.py), CRÍTICO: el
  código anterior asumía éxito (`CREADO`/`EDITADO`) con solo hacer clic en
  `#btnGuardar` y esperar `networkidle` — sin comprobar si el sitio realmente
  guardó. ShiftLaboral no cambia de URL al guardar: si hay un error de
  validación, el mismo formulario queda abierto en vez de avisar con una
  excepción de Playwright. Ahora se confirma explícitamente tras cada
  Guardar: (1) que no haya mensajes de error DevExpress visibles
  (`.dxeErrorCell`/`.dxeValidationSummary`/clases con "Error"/"Warning"), y
  (2) que `#btnGuardar` ya no esté visible (si sigue ahí, el guardado no se
  aplicó). Si algo falla, se reporta `ERROR` con el motivo en vez de un falso
  `CREADO`/`EDITADO`. En `crear_trabajador_nuevo` además hay una
  **confirmación positiva**: tras pasar la verificación, se limpia el filtro
  y se vuelve a buscar el RUT en la grilla — si no aparece, `ERROR` en vez de
  asumir que se creó.
- 🔴 **Popup "Operación Exitosa" tras Guardar — bug real y corregido en 2
  pasadas.** ShiftLaboral muestra un popup modal "Operación Exitosa" con
  botón "Aceptar" tras cada Guardar (mismo patrón que el borrado de
  documentos, §12.8). Si no se cierra, su overlay tapa la página y CUALQUIER
  clic posterior se cuelga 30s (síntoma reportado por el usuario: "produce un
  loop en el que el programa no puede seguir progresando"). Fix en
  `cerrar_popup_operacion_exitosa()` (campos_formulario.py), llamado justo
  después de cada clic en `#btnGuardar` (y defensivamente dentro de
  `cerrar_formulario()`). IDs CONFIRMADOS EN VIVO 08/09/2026 (RUT
  `19439430-6`, edición real) para la grilla de **Trabajadores**:
  `#btnExitoAceptar_grillaExternosProveedorTrabajadores` y variante `_2`
  (mismo patrón `btnExitoAceptar_<grilla>[_2]` que ya existía para la grilla
  de Documentos). 🔴 Una primera versión de la función (con polling corto de
  `is_visible(timeout=500)`) SÍ falló en vivo una vez porque el popup apareció
  un poco después de esa ventana — mismo patrón de bug de timing de
  DevExpress ya documentado en 12.6 (`confirmar_proveedor_seleccionado`).
  Fix definitivo: esperar EXPLÍCITAMENTE con
  `page.wait_for_selector(state="visible")` a que aparezca alguno de los IDs
  conocidos antes de intentar clickear. Verificado: el guardado se había
  aplicado igual en el intento fallido (solo falló la detección del popup,
  no el guardado — confirmado releyendo el sistema con `buscar_y_comparar.py`).

### 12.11 Interfaz gráfica (`interfaz.py`, customtkinter) (08/09/2026)

Implementada la app de escritorio pendiente en §13 (versión anterior): un
`.py` con 3 modos elegibles (Comparación / Creación-edición / Subir
documentos), selector de Excel y de reporte de salida, selector de carpeta de
documentos (solo visible en modo "Subir documentos"), checkbox
"--no-guardar", botón "Abrir Chrome de depuración" (mismo perfil/puerto que
`abrir_chrome.bat`), log en vivo y barra de progreso (parseando las líneas
`[i/N] ...` que ya imprimen los scripts). **No reimplementa la lógica de
negocio**: corre `buscar_y_comparar.py`/`crear_o_editar.py` como subproceso
(`sys.executable -u ...`) en un hilo aparte y muestra su stdout, para no
duplicar/arriesgar romper la automatización ya probada. Launcher:
`ejecutar_interfaz.bat`.

**Actualizado 10/09/2026**: `--limpiar-documentos` y `--verificar-documentos`
(ver 12.12) YA están expuestos en la interfaz — un checkbox para "verificar" y
un menú de 3 opciones (No tocarlos / Solo anotarlos / Borrarlos) para
"limpiar". Ambos solo aparecen fuera del modo Comparación, que es de solo
lectura. La opción de BORRAR pide una confirmación extra al apretar Iniciar,
por ser lo único irreversible de toda la app.

### 12.12 Anti-duplicado y verificación de documentos existentes (08/09/2026)

Hallazgo del usuario: nada impedía que `--subir-documentos` subiera los MISMOS
documentos dos veces si se corría de nuevo sobre una persona ya procesada
(sin validación de ese lado en el sitio). Fix en `documentos.py`:

- **`tipos_documentos_existentes(page, rut, grupo_proveedor)`**: de solo
  lectura, abre la vista de documentos y devuelve el tipo de TODOS los
  documentos ya cargados (proveedor O mandante — a diferencia de
  `limpiar_documentos_trabajador`, que solo lista los borrables). Expuesta en
  `crear_o_editar.py` como flag independiente **`--verificar-documentos`**
  (solo lectura, no sube ni borra nada) — el paso de "verificar antes de
  agregar" pedido explícitamente por el usuario.
- **`subir_documentos_trabajador(..., omitir_existentes=True)`** (default):
  antes de abrir "Carga masiva documentos", lee los tipos ya existentes y
  salta cualquier `item` cuyo tipo ya esté cargado. Nuevo valor de retorno
  `ya_existian` (además de `subidos`/`errores` — la firma pasó de 3 a 4
  elementos, actualizar cualquier código que la llame). Reportado en el
  detalle de cada fila como "ya tenía, no se re-subió (N): ...", distinto de
  "SUBIDOS (N): ...". Nuevo estado de acción `"sin_items_nuevos"` cuando todo
  lo de la carpeta ya estaba cargado.
- Refactor de soporte: los helpers internos de paginación/overlays de
  `limpiar_documentos_trabajador` (`_esperar_sin_overlays`,
  `_click_primero_visible`, `_cerrar_dialogo_abierto`, `_total_paginas`,
  `_ir_a_pagina`) se subieron a nivel de módulo (antes anidados) para poder
  reusarlos en `tipos_documentos_existentes`/`subir_documentos_trabajador`
  sin duplicar código.
- ✅ Validado en vivo (RUT `19439430-6`, Francisco Alvarez, sus 8 documentos
  ya cargados): segunda corrida de `--subir-documentos` detectó los 8 tipos
  existentes, no volvió a subir nada, y se confirmó contra el DOM que seguía
  en exactamente 8 documentos (sin duplicados).

### 12.13 Aviso de documentos faltantes del set estándar (08/09/2026)

Pedido del usuario: si a una persona le faltan documentos de la carpeta, que
NO bloquee el proceso (se crea/edita igual y se suben los que sí están), pero
que quede advertido en el reporte.

- **`DOCUMENTOS_SET_ESTANDAR`** (documentos.py): los 8 tipos que trae
  normalmente la carpeta de un ingreso nuevo (Cédula de Identidad, Contrato
  puesta a disposición, Contacto en caso de Emergencia, Toma de conocimiento
  marca en biometrico (EST), Registro Entrega EPP, Registro de Capacitación
  Uso EPP, Registro de Capacitación IRL (Ex Odi) Mandante, TC Reglamento
  Interno RIOHS mandante).
- Tras cada `--subir-documentos`, `crear_o_editar.py` compara
  `subidos + ya_existian` contra ese set (así no avisa por algo que la
  persona ya tenía cargado de una corrida anterior aunque no viniera en la
  carpeta de esta vez) y agrega al detalle de la fila: `⚠ FALTAN documentos
  del set estándar (N): ...`. El resumen final de consola cuenta cuántas
  personas quedaron con documentos incompletos.
- ✅ Validado en vivo: Ariel Díaz (carpeta con solo 5 de 8 archivos) quedó
  marcado con "FALTAN (3): Cédula de Identidad, Contrato puesta a
  disposición, Contacto en caso de Emergencia" — exactamente los que
  faltaban en su carpeta real — mientras sus 5 documentos disponibles se
  subieron igual. Francisco Alvarez (carpeta completa) no generó ninguna
  advertencia.

### 12.14 Bug "identidad-bloqueada" (§13 pendiente anterior, punto 6) — NO reproducido (08/09/2026)

El pendiente decía que al "Crear" un RUT ya conocido por la plataforma (otro
cliente), además de Nombres/Apellidos/Sexo (que correctamente quedan
`readonly`), los combos AFP y Sistema de Salud tampoco se escribían y
quedaban en su default ("Uno"/"Sin Información").

**Se intentó reproducir en vivo el 08/09/2026** con el mismo RUT documentado
originalmente (`22708167-8`, identidad de "Matias Ignacio", bloqueada) y la
secuencia exacta de `crear_trabajador_nuevo()`: Sueldo Base → AFP → Isapre →
Proveedor → confirmar → Cargo → Tienda. En cada paso, AFP y Sistema de Salud
(seteados a "Habitat"/"Fonasa" de prueba) se mantuvieron correctos de
principio a fin — el bug **no se reprodujo**. No se hizo clic en Guardar (no
se modificó nada real), y el formulario se cerró con Cancelar al terminar.

Conclusión: lo más probable es que este bug ya haya quedado resuelto como
efecto colateral de otros fixes de timing hechos después de documentarlo
(sección 12.10 de esta sesión, o el `wait_for_function` de
`esperar_campos_formulario_editables`/la espera tras confirmar el RUT en
"Crear"). **No se tocó código** para esto — agregar un fix especulativo sin
un caso real que falle agrega riesgo sin beneficio comprobado. Queda como
"posiblemente resuelto, confirmar en la próxima corrida real de lote grande
sobre una identidad bloqueada" en vez de cerrado del todo.

### 12.15 Botón "Cancelar proceso" y empaquetado con PyInstaller (08/09/2026)

**Botón de emergencia en `interfaz.py`.** Pedido explícito del usuario: poder
cortar TODO de inmediato si algo va mal a mitad de una corrida. Se agregó
`self.boton_cancelar` (rojo, junto a "Iniciar", habilitado solo mientras hay
un proceso corriendo). Al confirmar (pide confirmación explícita, avisando
que puede dejar un formulario a medio llenar en ShiftLaboral y que el reporte
final NO se genera), mata el proceso con `taskkill /F /T /PID <pid>` en un
hilo aparte — el `/T` es clave: se lleva puesto también el proceso interno
del driver de Playwright (Node.js), que `Popen.terminate()` solo no siempre
mata en Windows. **Probado en vivo**: lanzada una corrida real, cortada a los
2.5s — el proceso murió al instante, sin dejar ningún `node.exe` huérfano, y
el Chrome de depuración (proceso separado) siguió funcionando sin verse
afectado.

**Empaquetado con PyInstaller (`ShiftLaboralBot.exe`).** Objetivo: que el
usuario final interactúe lo menos posible con archivos sueltos (.py, .bat) y
que no aparezca ninguna ventana de consola detrás de la app.

- 🔴 **Problema de arquitectura y su solución.** `interfaz.py` lanzaba
  `buscar_y_comparar.py`/`crear_o_editar.py` como subproceso con
  `[sys.executable, "-u", "script.py", ...]`. Empaquetado, `sys.executable`
  deja de ser un `python.exe` suelto: ES el propio `.exe`, y no hay ningún
  `.py` al lado para pasarle. Solución (patrón estándar para apps
  empaquetadas que necesitan aislar trabajo en un subproceso):
  **`app_entry.py`**, nuevo punto de entrada único que actúa como
  dispatcher — sin argumentos abre la interfaz; con `--modo-comparar` o
  `--modo-crear` corre esa lógica (llamando directo a
  `buscar_y_comparar.main(argv)` / `crear_o_editar.main(argv)`, a los que
  se les agregó el parámetro opcional `argv=None`) y termina. `interfaz.py`
  (`_comando_base_modo`) arma el comando distinto según `sys.frozen`:
  empaquetado, `[sys.executable, "--modo-crear", ...]` (se relanza a sí
  mismo); en desarrollo, `[sys.executable, "-u", "app_entry.py", "--modo-crear", ...]`.
- **Sin ventana de consola, en ningún lado.** `subprocess.Popen(...,
  creationflags=subprocess.CREATE_NO_WINDOW)` en `interfaz.py` — evita que
  Windows abra/parpadee una consola negra cada vez que se lanza el
  subproceso (python.exe/el .exe son de subsistema consola por default,
  aunque el .exe final se compile `console=False`). El `.exe` en sí se
  compila con `console=False` (`ShiftLaboralBot.spec`), así que ni siquiera
  la ventana principal de la interfaz tiene consola detrás.
- **Playwright funciona empaquetado sin cambios**: su propio código YA
  soporta `sys.frozen` (`compute_driver_executable()` en
  `playwright/_impl/_driver.py`) y YA oculta la consola de su proceso driver
  interno en Windows (`STARTF_USESHOWWINDOW` + `SW_HIDE`, en
  `_transport.py`) — no hubo que tocar nada de eso. Sí hay que empaquetar a
  mano la carpeta `playwright/driver` (Node.js + scripts, ~100 MB) con
  `--add-data`, porque PyInstaller no la detecta sola (no es código Python
  importado, es un recurso de datos).
- **`ShiftLaboralBot.spec`**: calcula la ruta del driver de Playwright en el
  momento de construir (`os.path.dirname(playwright.__file__)`), NO
  hardcodeada, para que el mismo `.spec` sirva en cualquier computador.
  También incluye `collect_data_files('customtkinter')` (temas/JSON que
  necesita en runtime). Un solo archivo (`--onefile`), sin consola
  (`console=False`).
- **`construir_exe.bat`**: instala PyInstaller si falta y corre
  `pyinstaller ShiftLaboralBot.spec`. Resultado: `dist/ShiftLaboralBot.exe`
  (~97 MB, la mayor parte es el driver de Playwright).
- ✅ **Validado en vivo (08/09/2026)**: `dist/ShiftLaboralBot.exe
  --modo-comparar --input SHIFT.xlsx --output ...` llegó exactamente al mismo
  punto que en modo desarrollo (cargó el Excel, intentó conectar a Chrome en
  el puerto 9222). Lanzado sin argumentos, apareció la ventana "Bot
  ShiftLaboral" — confirmado con `Get-Process` que NO hay ningún
  `conhost.exe`/consola asociada al proceso. (Nota: un `.exe --onefile`
  siempre muestra 2 procesos con el mismo nombre en el Administrador de
  Tareas — el lanzador que se autoextrae + el proceso real; es
  comportamiento normal de PyInstaller, no un bug.) **Falta**: probar un
  modo real (crear/editar + subir documentos) desde el `.exe` con sesión de
  ShiftLaboral iniciada — no se pudo completar en esta sesión porque la
  sesión de Chrome había expirado y requiere login manual.
- `.gitignore`: `build/` y `dist/` ignorados (el `.exe` pesa ~100 MB, no
  tiene sentido versionarlo); `ShiftLaboralBot.spec` SÍ se versiona.
  `requirements.txt` agrega `pyinstaller>=6.0` con nota de que solo hace
  falta para construir el `.exe`, no para correr los scripts con Python.

## 13. PENDIENTES — retomar próxima sesión (actualizado 08/09/2026)

Estado al cierre del 08/09/2026 (rama `carga-masiva`, sale de `Crear`).
Pipeline `crear_o_editar.py` funcionando y ENDURECIDO con datos y corridas
reales: crear/editar + `--no-guardar` + `--limpiar-documentos [listar|borrar]`
+ `--subir-documentos CARPETA` (ahora anti-duplicado, ver 12.12) +
`--verificar-documentos` (nuevo, solo lectura, ver 12.12). Autocompletado de
Fin Contrato/Sueldo Base (12.10), verificación real de guardado y manejo del
popup "Operación Exitosa" (12.10), aviso de documentos faltantes (12.13), e
interfaz gráfica `interfaz.py` (12.11) ya implementados y validados en vivo.

### Resueltos en esta sesión (ya no son pendientes)
- ~~1. Verificar en vivo la carga masiva SIN Período~~ → CONFIRMADO: el sitio
  SÍ rechaza el Período vacío; el fallback (completar y reintentar) funciona
  y quedó validado en vivo (ver 12.10/12.12).
- ~~2. Prueba end-to-end del pipeline completo~~ → hecho sobre 1-2 personas
  reales (crear/editar + subir documentos, con y sin `--no-guardar`);
  **falta todavía a mayor escala**, ver punto 1 nuevo más abajo.
- ~~5. LA INTERFAZ (customtkinter)~~ → implementada (`interfaz.py` +
  `ejecutar_interfaz.bat`), ver 12.11. Aún le faltan exponer
  `--limpiar-documentos`/`--verificar-documentos` (hoy solo por CLI).
- ~~6. Bug identidad-bloqueada (AFP/Isapre)~~ → **NO reproducido** en un
  intento en vivo dedicado (ver 12.14). Probablemente ya resuelto como
  efecto colateral de otros fixes de timing. Queda en observación, no en
  pendiente activo — si reaparece en el lote grande (punto 1 de abajo),
  retomar con el caso real en la mano.

### Prioridad ALTA
1. **Prueba end-to-end de un lote real MÁS GRANDE (5-10+ personas).** Todo lo
   endurecido en 12.10-12.13 solo se probó con 1-2 personas por corrida. Los
   bugs de timing/overlay de este sitio (varios ya documentados) tienden a
   aparecer recién con iteraciones repetidas en un lote real, no en pruebas
   puntuales. Correr crear/editar + `--subir-documentos` (+ opcionalmente
   `--limpiar-documentos borrar` sobre alguna identidad preexistente) sobre
   un lote grande y revisar el reporte fila por fila.
2. **Reconciliar `SHIFT.xlsx` vs carpeta de documentos de cada lote.**
   Confirmar que toda persona del Excel tenga carpeta de documentos y
   viceversa antes de correr `--subir-documentos` en serio (la advertencia de
   12.13 ayuda, pero es post-hoc, no una reconciliación previa).
3. **Probar `dist/ShiftLaboralBot.exe` con un modo real** (crear/editar y/o
   subir documentos, no solo comparación) con sesión de ShiftLaboral
   iniciada — ver 12.15. Solo se validó que el `.exe` llega a intentar
   conectar a Chrome; falta confirmar un guardado/subida real desde el
   ejecutable empaquetado (no solo desde `python crear_o_editar.py` directo).

### Prioridad MEDIA
3. **Completar `_MAPEO_NOMBRE_TIPO`** (`documentos.py`) para archivos que
   aparezcan en otras carpetas y no estén cubiertos (hoy cubre el set
   estándar de 8 confirmado en "Adan_Leon"/"Ariel_Diaz"/"Francisco_Alvarez").
   Ir agregando patrones a medida que aparezcan, y correr `test_datos.py`
   después de cada cambio.
4. ~~Exponer `--limpiar-documentos` y `--verificar-documentos` en
   `interfaz.py`~~ → HECHO 10/09/2026, ver 12.11.

### Resueltos 10/09/2026 (sesión de endurecimiento previo a la entrega)
- **Ruta de Chrome ya no está hardcodeada.** `interfaz.py` y los 3 `.bat`
  asumían `C:\Program Files\Google\Chrome\Application\chrome.exe`. En un
  equipo con Chrome de 32 bits o instalado por usuario, "Abrir Chrome" fallaba
  sin explicación — bug de despliegue que NO se manifiesta en el equipo de
  desarrollo, solo en el del otro usuario. Ahora se prueban las 3 ubicaciones
  habituales (`%ProgramFiles%`, `%ProgramFiles(x86)%`, `%LOCALAPPDATA%`); la
  interfaz además ofrece buscar el `chrome.exe` a mano si no aparece en
  ninguna, y recuerda esa ruta por el resto de la sesión.
- **`test_datos.py`** (nuevo, ver sección 0): cubre las funciones puras.
- **Flags de documentos expuestos en la interfaz** (ver 12.11).

Evaluados y NO hechos a propósito (no aportan hoy y sí agregan riesgo sobre
código ya validado en vivo): sacar los globales `NO_GUARDAR`/`LIMPIAR_
DOCUMENTOS`/etc. de `crear_o_editar.py` a un dataclass de opciones (funciona
porque es un proceso por corrida; el riesgo real aparece solo si algún día se
llama `main()` dos veces en el mismo proceso), y partir el `main()` de
`crear_o_editar.py` (~200 líneas) en un `procesar_fila()`. Retomar el segundo
si el archivo sigue creciendo — y recién después de tener más cobertura de
tests.

### 12.16 Una sola visita a la vista de documentos por persona (10/09/2026)

🔴 **Optimización de tiempo, la más grande del proyecto.** Los tres flags de
documentos (`--limpiar-documentos`, `--verificar-documentos`,
`--subir-documentos`) llamaban cada uno a su propia función pública, y las tres
empezaban por `_abrir_vista_documentos()`: `goto(BASE_URL)` → `networkidle` →
`seleccionar_grupo_proveedor` → esperar overlay → `buscar_rut` → clic en el RUT
→ `networkidle` → `sleep(1.0)`. Son ~2,5s de esperas fijas más 4 `networkidle`
más 3 cargas reales: **10-15s por visita**. Pedir los tres flags hacía ese
mismo camino 3 veces seguidas para la misma persona. Encima
`--verificar-documentos` leía la tabla de tipos (paginándola entera) y después
`subir_documentos_trabajador` la volvía a leer por dentro.

**Fix**: se separó "navegar hasta la vista" de "trabajar sobre la vista".
- Nuevas internas en `documentos.py`, todas asumen la vista YA abierta y la
  dejan abierta: `_limpiar_en_vista_abierta`, `_subir_en_vista_abierta`
  (+ `_leer_tipos_en_vista_abierta`, que ya existía). `_volver_a_trabajadores`
  centraliza la salida.
- **`gestionar_documentos_trabajador(page, rut, grupo, limpiar=, verificar=,
  items=, ...)`**: abre la vista UNA vez, hace lo que se le pida en el orden
  correcto (**borrar → leer tipos → subir**; ese orden importa: si se leyera
  antes de borrar, lo recién borrado contaría como "ya lo tenía" y se saltearía
  la subida), y vuelve a la grilla en un `finally`. La lectura de tipos se hace
  **una sola vez** y se le pasa a la subida por `tipos_ya_leidos`.
- Las 3 funciones públicas viejas (`limpiar_documentos_trabajador`,
  `tipos_documentos_existentes`, `subir_documentos_trabajador`) **siguen
  existiendo** como envoltorios finos (navegan, llaman a la interna, vuelven) —
  no se rompió ninguna firma, y sirven de alternativa si la versión combinada
  diera problemas.
- `crear_o_editar.py`: los 3 bloques del bucle se unificaron en uno. La carpeta
  de la persona se busca ANTES de navegar, así que si no existe no se entra a
  la vista de documentos en absoluto. Las líneas del reporte quedaron
  idénticas; se extrajo `_notas_documentos()` para armarlas.

De 3 navegaciones + 2 lecturas de tabla a **1 navegación + 1 lectura**. En un
lote de 20 personas con los tres flags, del orden de 10 minutos menos.

⚠️ **Falta validarlo contra el sitio real.** `test_datos.py` cubre el orden de
las llamadas, que se navega una sola vez, que los tipos no se releen y las
líneas del reporte — pero con las funciones internas simuladas, sin navegador.
Lo que NO está probado es que el sitio aguante hacer las tres cosas seguidas
sin el "reseteo" implícito que daba renavegar entre una y otra (por eso
`_subir_en_vista_abierta` arranca con `_cerrar_dialogo_abierto` +
`_esperar_sin_overlays`, por si el borrado dejó algún aviso tapando el botón de
carga masiva). **Probar primero con UNA persona y los tres flags juntos** antes
de usarlo en un lote grande.

### Prioridad BAJA / a revisar
5. **Período de tipos Mensual/Anual** (Liquidaciones, EPP anual): para tipos
   "1 sola vez" el sitio fija el Período a `04/01/1990` ignore lo que se
   ponga; sin verificar qué hace con Mensual/Anual. Si el negocio necesita el
   período correcto ahí, investigar.
6. **Ramas / merge.** Estamos en `carga-masiva` ← `Crear` ← `main`. El trabajo
   de esta sesión se mergeó `carga-masiva` → `Crear` (ver commit del
   08/09/2026); decidir cuándo mergear `Crear` → `main`.
7. **`SHIFT.xlsx`**: versionado como TEMPLATE vacío (excepción `!SHIFT.xlsx`
   en `.gitignore`). El archivo local con datos reales NUNCA se commitea —
   `git update-index --skip-worktree SHIFT.xlsx` si molesta en `git status`.
   Backup local de datos: `SHIFT.datos.local.xlsx`.

### Cómo dejar el entorno para retomar
- Abrir Chrome: `abrir_chrome.bat` (o `ejecutar_crear.bat`), iniciar sesión en
  ShiftLaboral, dejar la ventana abierta (puerto 9222).
- Si Claude Code necesita lanzarlo: `chrome.exe --remote-debugging-port=9222
  --user-data-dir="C:\Users\GC\AppData\Local\ChromeDebugShiftLaboral" <url>`
  (ruta ABSOLUTA — `%LOCALAPPDATA%` no expande fuera de cmd). La sesión de
  ShiftLaboral se cae sola cada tanto (sesión única por usuario) — re-login.
