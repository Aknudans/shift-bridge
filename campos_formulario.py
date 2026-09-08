"""
Primitivas de lectura/escritura de campos del formulario de editar/crear
trabajador en ShiftLaboral (Fase 2). No contienen lógica de negocio — solo
"cómo leo/escribo este tipo de campo", reutilizable independientemente de
qué campo específico se esté tocando.

Usado por crear_o_editar.py. Ver CLAUDE.md sección 12 para el detalle de
cada hallazgo (por qué los combobox necesitan este tratamiento, etc.).
"""

import time
from typing import Optional

from playwright.sync_api import Page

from shift_common import normalizar_texto

# Botón "Cancelar" del formulario (editar/ver/crear) — mismo id en los tres.
SELECTOR_BTN_CANCELAR = "#btnCancelar"

# Fragmento estable del id del botón ">" que confirma el Proveedor elegido y
# habilita las secciones de Categoría Trabajador (Cargo) y Tiendas.
ID_FRAGMENTO_CONFIRMAR_PROVEEDOR = "btnCargarClientesCategoria"


# Ids CONFIRMADOS EN VIVO 08/09/2026 (RUT 19439430-6, edición real con
# --subir-documentos) para el popup "Operación Exitosa" de la grilla de
# Trabajadores — mismo patrón "btnExitoAceptar_<grilla>[_2]" que ya estaba
# confirmado para la grilla de Documentos (documentos.py), solo cambia el
# nombre de la grilla.
IDS_POPUP_EXITO_TRABAJADORES = (
    "btnExitoAceptar_grillaExternosProveedorTrabajadores_2",
    "btnExitoAceptar_grillaExternosProveedorTrabajadores",
)


def cerrar_popup_operacion_exitosa(page: Page, timeout_ms: int = 8000) -> bool:
    """Cierra el popup modal "Operación Exitosa ... Aceptar" que ShiftLaboral
    muestra tras Guardar (mismo patrón ya visto al borrar documentos, ver
    documentos.py `_cerrar_dialogo_abierto`).

    🔴 CRÍTICO no omitir esto: si el popup queda sin cerrar, su overlay
    (`.ui-widget-overlay`) tapa toda la página y CUALQUIER clic posterior
    (Cancelar, buscar el siguiente RUT, etc.) se cuelga esperando un
    elemento tapado — el lote entero queda trabado en la misma fila.

    🔴 BUG CONFIRMADO Y CORREGIDO 08/09/2026: una primera versión de esta
    función buscaba el botón con un polling corto (`is_visible(timeout=500)`
    por iteración) apenas terminaba `networkidle` + un `sleep(0.5)` externo.
    En una corrida real (RUT 19439430-6) el popup SÍ apareció pero un poco
    más tarde que esa ventana — mismo patrón de bug ya documentado en
    CLAUDE.md 12.6 (`confirmar_proveedor_seleccionado`: "networkidle" no es
    señal fiable de que terminó un callback de DevExpress). El resultado fue
    que `verificar_guardado_exitoso` encontró `#btnGuardar` tapado por el
    overlay y reportó ERROR pese a que el guardado sí había funcionado, y
    encima el overlay sin cerrar hizo colgarse (timeout de 30s) el clic
    siguiente sobre el filtro de RUT. Fix: esperar EXPLÍCITAMENTE con
    `wait_for_selector(state="visible")` a que aparezca alguno de los ids
    conocidos antes de intentar clickear, en vez de un polling corto.
    """
    selector_conocidos = ", ".join(f"#{i}" for i in IDS_POPUP_EXITO_TRABAJADORES)
    try:
        page.wait_for_selector(selector_conocidos, state="visible", timeout=timeout_ms)
    except Exception:
        pass  # puede que esta vez no haya aparecido ningún popup (ej. SIN_CAMBIOS)

    cerrado = False
    for _ in range(3):  # por si queda más de un popup apilado
        boton = None
        for id_ in IDS_POPUP_EXITO_TRABAJADORES:
            loc = page.locator(f"#{id_}")
            try:
                if loc.count() and loc.first.is_visible(timeout=500):
                    boton = loc.first
                    break
            except Exception:
                pass

        if boton is None:
            # Fallback genérico por si aparece en otra grilla con otro id.
            for selector in ('[id^="btnExitoAceptar"]', '[id*="Exito"][id*="Aceptar"]'):
                loc = page.locator(selector)
                try:
                    cantidad = loc.count()
                except Exception:
                    cantidad = 0
                if cantidad > 0:
                    candidato = loc.last if cantidad > 1 else loc.first
                    try:
                        if candidato.is_visible(timeout=500):
                            boton = candidato
                            break
                    except Exception:
                        pass

        if boton is None:
            try:
                hay_popup = page.evaluate(
                    """() => Array.from(document.querySelectorAll('*')).some(e =>
                        e.offsetParent !== null
                        && /operaci[oó]n\\s+exitosa/i.test(e.textContent || '')
                    )"""
                )
            except Exception:
                hay_popup = False
            if hay_popup:
                candidato = page.locator("text=Aceptar").last
                try:
                    if candidato.is_visible(timeout=500):
                        boton = candidato
                except Exception:
                    pass

        if boton is None:
            break

        try:
            boton.click(timeout=2000)
            cerrado = True
            page.wait_for_timeout(400)
        except Exception:
            break

    return cerrado


def cerrar_formulario(page: Page):
    """Cierra cualquier vista/formulario abierto (editar, ver o crear) con el
    botón Cancelar, sin guardar. CRÍTICO no omitir esto entre filas — ver
    CLAUDE.md sección 6 Paso 11 (bug de fila "pegada" en modo edición)."""
    cerrar_popup_operacion_exitosa(page, timeout_ms=1500)
    try:
        page.locator(SELECTOR_BTN_CANCELAR).click(timeout=3000)
        page.wait_for_load_state("networkidle")
        time.sleep(0.3)
    except Exception:
        pass


def verificar_guardado_exitoso(page: Page, timeout: int = 4000) -> tuple[bool, str]:
    """Tras hacer clic en Guardar, confirma si el sitio realmente aplicó el
    cambio, en vez de asumirlo por default.

    ShiftLaboral no navega a otra URL al guardar: si hay un error de
    validación (campo obligatorio vacío, formato inválido, etc.) el propio
    formulario se queda abierto mostrando el error en vez de volver a la
    grilla. Se usan dos señales, cualquiera de las dos basta para reportar
    que el guardado NO se confirmó:
      1) Mensajes de validación visibles en el DOM (clases DevExpress típicas
         de error: dxeErrorCell / dxeValidationSummary / dxWarning, o
         cualquier elemento con esas palabras en class y visible).
      2) El propio botón Guardar (#btnGuardar) sigue presente y visible — si
         el guardado hubiera funcionado, el formulario se cierra y la grilla
         vuelve a su estado normal.
    """
    try:
        page.wait_for_timeout(300)
    except Exception:
        pass

    try:
        mensajes_error = page.evaluate(
            """() => {
                const sels = ['.dxeErrorCell', '.dxeValidationSummary',
                              '[class*="Error"]', '[class*="Warning"]'];
                const textos = new Set();
                sels.forEach(sel => {
                    document.querySelectorAll(sel).forEach(e => {
                        if (e.offsetParent !== null) {
                            const t = (e.textContent || e.title || '').trim();
                            if (t) textos.add(t);
                        }
                    });
                });
                return Array.from(textos);
            }"""
        )
    except Exception:
        mensajes_error = []

    if mensajes_error:
        return False, "Errores de validación del sitio: " + "; ".join(mensajes_error)

    try:
        formulario_sigue_abierto = page.locator("#btnGuardar").is_visible(timeout=timeout)
    except Exception:
        formulario_sigue_abierto = False

    if formulario_sigue_abierto:
        return False, "El formulario de Guardar sigue abierto tras el clic; no se confirmó el guardado."

    return True, ""


def esperar_campos_formulario_editables(page: Page, timeout: int = 15000):
    """Espera a que el formulario de crear/editar trabajador esté REALMENTE
    editable, no solo presente en el DOM.

    🔴 Tras abrir el formulario (clic en el lápiz "editar", o en el botón ">"
    que confirma el RUT en "Crear"), DevExpress corre un callback
    (`Aspxcallbackpanel2`) que arma los campos. Mientras no termina,
    `#txtNombres` ya EXISTE pero está `readonly` — y `networkidle` NO detecta
    ese callback. Esperar solo `wait_for_selector('#txtNombres')` + un
    `time.sleep` fijo provocaba ERROR intermitente ("element is not editable",
    `Locator.fill` timeout 30s) en corridas de lote — confirmado 07/09/2026:
    2 de 6 filas fallaron así. Acá se espera a que el campo no tenga
    `readOnly`/`disabled`."""
    try:
        page.wait_for_function(
            """() => { const e = document.getElementById('txtNombres');
                       return e && !e.readOnly && !e.disabled; }""",
            timeout=timeout,
        )
    except Exception:
        # No se puso editable a tiempo: dejar que el paso siguiente falle de
        # forma visible (se registra como ERROR y el lote sigue con la
        # siguiente fila).
        pass
    time.sleep(0.2)


def _input_por_etiqueta(page: Page, etiqueta: str) -> Optional[str]:
    """Devuelve el id del input/select asociado a una etiqueta visible.

    CONFIRMADO EN VIVO 05/08/2026: a diferencia de Nombres/Apellidos/AFP (con
    etiqueta y caja en la misma fila de tabla, td + td), las etiquetas
    "Proveedores:", "Categoría Trabajador:" y "Tiendas:" están en su propia
    línea, con la caja completa DEBAJO (no al lado) — "closest('td') +
    nextElementSibling" no encuentra nada ahí y siempre devuelve null. En vez
    de asumir estructura de tabla, se toma el primer input/select/textarea
    VISIBLE que aparece después de la etiqueta en el orden del documento.
    """
    return page.evaluate(
        """(etiqueta) => {
            const el = Array.from(document.querySelectorAll('*')).find(e =>
                e.offsetParent !== null && e.children.length === 0 && e.textContent.trim() === etiqueta
            );
            if (!el) return null;
            const candidatos = Array.from(document.querySelectorAll('input, select, textarea'))
                .filter(i => i.offsetParent !== null);
            for (const input of candidatos) {
                if (el.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING) {
                    return input.id;
                }
            }
            return null;
        }""",
        etiqueta,
    )


def leer_campo_texto(page: Page, campo_id: str) -> str:
    try:
        return page.locator(f"#{campo_id}").input_value(timeout=3000).strip()
    except Exception:
        return ""


def escribir_campo_texto(page: Page, campo_id: str, valor: str):
    campo = page.locator(f"#{campo_id}")
    campo.click()
    campo.fill("")
    campo.fill(valor)
    campo.press("Tab")


def leer_combobox_simple(page: Page, fragmento: str) -> str:
    try:
        return page.locator(f'[id*="{fragmento}"][id$="_I"]').input_value(timeout=3000).strip()
    except Exception:
        return ""


def escribir_combobox_simple(page: Page, fragmento: str, valor_deseado: str):
    """Abre el combobox de selección única y hace clic en la opción cuyo
    texto calza EXACTO (ignorando mayúsculas/espacios) con valor_deseado."""
    input_visible = page.locator(f'[id*="{fragmento}"][id$="_I"]')
    input_visible.click(timeout=5000)
    time.sleep(0.3)
    opcion = page.locator(f"text={valor_deseado}").first
    opcion.click(timeout=5000)
    time.sleep(0.3)


def leer_multiselect(page: Page, etiqueta: str) -> list[str]:
    """Lee el valor actual (semicolon-separated en el input visible cuando
    hay más de uno) de un combobox multi-select (Proveedores/Cargo/Tiendas)."""
    campo_id = _input_por_etiqueta(page, etiqueta)
    if not campo_id:
        return []
    try:
        valor = page.locator(f"#{campo_id}").input_value(timeout=3000).strip()
    except Exception:
        return []
    if not valor:
        return []
    return [v.strip() for v in valor.split(";") if v.strip()]


def _esperar_grid_sin_overlay(page: Page, timeout: int = 10000):
    """Espera a que el overlay de carga del grid (`dxgvLoadingDiv`) desaparezca.

    Ese overlay tapa toda la grilla y **intercepta los clics** — si está activo
    cuando se intenta abrir un dropdown (Proveedores/Cargo/Tiendas), Playwright
    reintenta hasta agotar el timeout y la fila cae en ERROR
    (`dxgvLoadingDiv intercepts pointer events`). Aparece tras cualquier
    callback de DevExpress sobre la grilla y `networkidle` no lo detecta."""
    try:
        page.wait_for_function(
            """() => { const d = document.getElementById('grillaExternosProveedorTrabajadores_LD');
                       return !d || d.offsetParent === null; }""",
            timeout=timeout,
        )
    except Exception:
        pass


def _esperar_items_listbox(page: Page, timeout: int = 5000):
    """Espera a que el listbox de DevExpress recién abierto tenga al menos un
    ítem con checkbox visible. El dropdown de "Categoría Trabajador" tiene
    ~122 opciones y tarda en renderizar — con un `time.sleep` fijo corto a
    veces se leía la lista vacía y se descartaba un Cargo que sí existía."""
    try:
        page.wait_for_function(
            """() => Array.from(document.querySelectorAll('.dxeListBoxItem'))
                .some(e => e.offsetParent !== null && e.querySelector('input[type=checkbox]'))""",
            timeout=timeout,
        )
    except Exception:
        pass
    time.sleep(0.2)


def obtener_opciones_multiselect(page: Page, etiqueta: str) -> list[dict]:
    """Abre el dropdown de un multi-select y devuelve todas sus opciones
    visibles con su texto y si están marcadas. NO cierra el dropdown.

    CONFIRMADO EN VIVO 05/08/2026: cada opción del checkbox list de DevExpress
    se renderiza como DOS elementos `.dxeListBoxItem` SEPARADOS y consecutivos
    — uno con el `<input type="checkbox">` (clase "dxeC", sin texto) y el
    siguiente con el texto de la etiqueta (clase "dxeT", sin checkbox). No son
    un único elemento con ambos. Hay que emparejarlos por posición.
    """
    campo_id = _input_por_etiqueta(page, etiqueta)
    if not campo_id:
        return []
    _esperar_grid_sin_overlay(page)
    page.locator(f"#{campo_id}").click(timeout=5000)
    _esperar_items_listbox(page)
    return page.evaluate(
        """() => {
            const items = Array.from(document.querySelectorAll('.dxeListBoxItem'))
                .filter(e => e.offsetParent !== null);
            const opciones = [];
            for (let i = 0; i < items.length - 1; i++) {
                const chk = items[i].querySelector('input[type="checkbox"]');
                if (!chk) continue;
                const texto = items[i + 1].textContent.trim();
                if (!texto || texto === 'Seleccionar Todos') continue;
                opciones.push({ texto, marcado: chk.checked });
            }
            return opciones;
        }"""
    )


def establecer_multiselect_valor_unico(page: Page, etiqueta: str, valor_deseado: str) -> bool:
    """Deja UN ÚNICO valor marcado en un combobox multi-select (Proveedores/
    Cargo/Tiendas): desmarca cualquier opción marcada que no sea la deseada,
    y marca la deseada si no lo estaba. Devuelve False si valor_deseado no
    existe EXACTO entre las opciones reales (candidato a fila omitida).

    Todo el emparejamiento checkbox+texto y el clic se hacen en un solo
    page.evaluate (necesita la referencia viva al <input>, no solo su texto)
    — ver nota de obtener_opciones_multiselect sobre por qué están separados.
    """
    campo_id = _input_por_etiqueta(page, etiqueta)
    if not campo_id:
        return False
    _esperar_grid_sin_overlay(page)
    page.locator(f"#{campo_id}").click(timeout=5000)
    _esperar_items_listbox(page)

    resultado = page.evaluate(
        """(valorDeseado) => {
            const norm = (s) => (s || '').trim().toUpperCase();
            const items = Array.from(document.querySelectorAll('.dxeListBoxItem'))
                .filter(e => e.offsetParent !== null);
            const pares = [];
            for (let i = 0; i < items.length - 1; i++) {
                const chk = items[i].querySelector('input[type="checkbox"]');
                if (!chk) continue;
                const texto = items[i + 1].textContent.trim();
                if (!texto || texto === 'Seleccionar Todos') continue;
                pares.push({ checkbox: chk, texto, marcado: chk.checked });
            }
            const deseadoNorm = norm(valorDeseado);
            const existe = pares.some(p => norm(p.texto) === deseadoNorm);
            if (!existe) return { existe: false };
            for (const p of pares) {
                const coincide = norm(p.texto) === deseadoNorm;
                if (p.marcado !== coincide) {
                    p.checkbox.click();
                }
            }
            return { existe: true };
        }""",
        valor_deseado,
    )

    page.keyboard.press("Escape")
    time.sleep(0.2)
    return resultado["existe"]


def validar_cargo_existe(page: Page, cargo_deseado: str) -> bool:
    """Solo valida (sin modificar nada) si cargo_deseado existe EXACTO en el
    catálogo real de Categoría Trabajador. Cierra el dropdown al terminar."""
    opciones = obtener_opciones_multiselect(page, "Categoría Trabajador:")
    texto_normalizado = normalizar_texto(cargo_deseado)
    existe = any(normalizar_texto(o["texto"]) == texto_normalizado for o in opciones)
    page.keyboard.press("Escape")
    time.sleep(0.2)
    return existe


def confirmar_proveedor_seleccionado(page: Page):
    """Hace clic en el botón '>' que confirma el Proveedor y habilita las
    secciones de Categoría Trabajador (Cargo) y Tiendas.

    🔴 El '>' dispara un callback AJAX de DevExpress que INYECTA las secciones
    "Categoría Trabajador" y "Tiendas" en el DOM. `networkidle` se cumple
    ANTES de que ese callback termine (mismo patrón que el filtro de RUT y el
    grid — ver CLAUDE.md secciones 7/11). Por eso se ESPERA EXPLÍCITAMENTE a
    que aparezca la etiqueta "Categoría Trabajador:" antes de devolver el
    control. Sin esta espera, `validar_cargo_existe` corría contra un DOM sin
    esa sección y reportaba TODAS las filas como OMITIDO_CARGO
    (bug confirmado en vivo 07/09/2026: la sección tardaba ~0.5s más en
    aparecer de lo que `time.sleep(0.5)` cubría)."""
    page.locator(f'[id*="{ID_FRAGMENTO_CONFIRMAR_PROVEEDOR}"]').first.click(timeout=5000)
    page.wait_for_load_state("networkidle")
    try:
        page.wait_for_function(
            """() => !!Array.from(document.querySelectorAll('*')).find(
                e => e.children.length === 0 && e.textContent.trim() === 'Categoría Trabajador:'
            )""",
            timeout=10000,
        )
    except Exception:
        # No apareció en 10s: no forzamos error acá, dejamos que el paso
        # siguiente (validar_cargo_existe) falle de forma visible y explícita.
        pass
    time.sleep(0.3)
