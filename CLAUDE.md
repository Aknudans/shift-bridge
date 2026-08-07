# CLAUDE.md — Bot de automatización ShiftLaboral

Este archivo es el contexto de proyecto para Claude Code. Léelo completo antes de tocar código.

## 0. Comandos y arquitectura técnica (referencia rápida)

**Instalación** (una vez por computador; en algunos equipos `pip`/`playwright`
sueltos no están en el PATH — usar `python -m pip` / `python -m playwright`):
```
python -m pip install -r requirements.txt
python -m playwright install chromium
```

**Ejecutar el bot** (opción recomendada, un solo doble-click):
```
ejecutar_bot.bat
```
Abre Chrome en modo depuración con un perfil separado (`--user-data-dir`), pausa
para que inicies sesión manualmente la primera vez, pide el Excel de entrada
(se puede arrastrar a la consola) y corre el script.

**Ejecutar el script directamente** (requiere Chrome ya abierto con
`--remote-debugging-port=9222` y sesión iniciada — ver sección 8.2 y README.md):
```
python buscar_y_comparar.py --input colaboradores.xlsx --output reporte.xlsx
```

No hay tests, linter ni build configurados — son scripts autocontenidos (más
un módulo de soporte compartido). La única forma de "probar" un cambio es
correrlo contra el sitio real (idealmente con pausas visibles, ver sección
8.2) con un Excel de pocas filas.

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

| Columna en Excel | Campo en ShiftLaboral | Sección del formulario |
|---|---|---|
| NOMBRES | Nombres | Datos Trabajador |
| apellidoPaterno | Apellido Paterno | Datos Trabajador |
| apellidoMaterno | Apellido Materno | Datos Trabajador |
| SEXO | Sexo | Datos Trabajador |
| fechaContratacion | Inicio Contrato | Datos Trabajador |
| fechaTermino | Fin Contrato | Datos Trabajador (= fechaContratacion + 89 días) |
| AFP | AFP | Datos Trabajador |
| ISAPRE | Sistema de Salud | Datos Trabajador |
| sueldoBase | Sueldo Base | Datos Trabajador |
| PROVEEDOR | Proveedores | Relación Clientes |
| CARGO | (dropdown sin label visible) | Categoría Trabajador — texto libre, sin validación en Excel |
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
crear_o_editar.py       — script Fase 2 (creación/edición), ver sección 12
ejecutar_crear.bat      — launcher de un click para Fase 2, dedicado y separado
                          del anterior a propósito (repo: rama `Crear`)
requirements.txt       — dependencias Python
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

⚠️ **Sigue pendiente**: el botón `#btnGuardar` nunca se clickeó de verdad
(decisión explícita del usuario). Antes de usar `crear_o_editar.py` contra
datos de producción, probarlo con cuidado con 1-2 filas de prueba primero,
observando visualmente cada paso — mismo protocolo que la sección 8, pero
para Fase 2.
