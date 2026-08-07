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


def cerrar_formulario(page: Page):
    """Cierra cualquier vista/formulario abierto (editar, ver o crear) con el
    botón Cancelar, sin guardar. CRÍTICO no omitir esto entre filas — ver
    CLAUDE.md sección 6 Paso 11 (bug de fila "pegada" en modo edición)."""
    try:
        page.locator(SELECTOR_BTN_CANCELAR).click(timeout=3000)
        page.wait_for_load_state("networkidle")
        time.sleep(0.3)
    except Exception:
        pass


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
    page.locator(f"#{campo_id}").click(timeout=5000)
    time.sleep(0.3)
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
    page.locator(f"#{campo_id}").click(timeout=5000)
    time.sleep(0.3)

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
    secciones de Categoría Trabajador (Cargo) y Tiendas."""
    page.locator(f'[id*="{ID_FRAGMENTO_CONFIRMAR_PROVEEDOR}"]').first.click(timeout=5000)
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)
