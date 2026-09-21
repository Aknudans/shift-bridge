import time
from typing import Optional

from playwright.sync_api import Page

from shift_common import es_vacio, normalizar_texto

# Se lanza cuando un combo (Sexo, AFP, Sistema de Salud) no se pudo llenar.
# El mensaje dice qué campo era y qué valor se intentó poner, para que el
# reporte lo muestre tal cual en vez de un timeout de Playwright.
class CampoNoCompletado(Exception):
    pass


# Comparación en el navegador equivalente a normalizar_texto: sin tildes,
# sin mayúsculas y sin espacios de más.
_JS_NORM = r"""(s) => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
                           .replace(/\s+/g, ' ').trim().toUpperCase()"""


# El Cancelar del formulario, igual en ver, editar y crear.
SELECTOR_BTN_CANCELAR = "#btnCancelar"

# La flecha ">" que confirma el proveedor y recién ahí hace aparecer las
# secciones de cargo y tiendas.
ID_FRAGMENTO_CONFIRMAR_PROVEEDOR = "btnCargarClientesCategoria"


# Los dos botones posibles del aviso "Operación Exitosa" de la lista de
# trabajadores; el sitio a veces usa uno y a veces el otro.
IDS_POPUP_EXITO_TRABAJADORES = (
    "btnExitoAceptar_grillaExternosProveedorTrabajadores_2",
    "btnExitoAceptar_grillaExternosProveedorTrabajadores",
)


# Cierra el aviso de "Operación Exitosa" que sale después de guardar.
# Hay que cerrarlo sí o sí: mientras esté abierto deja una capa gris encima de
# toda la página y cualquier clic siguiente se queda esperando para siempre,
# con lo que el lote entero se traba en la misma persona.
# Se espera a que el aviso aparezca en vez de mirar una sola vez, porque a
# veces se demora más de lo que uno supondría en salir.
def cerrar_popup_operacion_exitosa(page: Page, timeout_ms: int = 8000) -> bool:
    selector_conocidos = ", ".join(f"#{i}" for i in IDS_POPUP_EXITO_TRABAJADORES)
    try:
        page.wait_for_selector(selector_conocidos, state="visible", timeout=timeout_ms)
    except Exception:
        pass  # puede que esta vez no haya salido ningún aviso

    cerrado = False
    for _ in range(3):  # por si quedó más de un aviso uno encima de otro
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
            # Si el aviso vino de otra parte del sitio, se busca a lo bruto.
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


# Cierra sin guardar lo que haya abierto. Importante hacerlo entre persona y
# persona, si no la ficha queda abierta y ensucia a la siguiente.
def cerrar_formulario(page: Page):
    cerrar_popup_operacion_exitosa(page, timeout_ms=1500)
    try:
        page.locator(SELECTOR_BTN_CANCELAR).click(timeout=3000)
        page.wait_for_load_state("networkidle")
        time.sleep(0.3)
    except Exception:
        pass


# Después de apretar Guardar, revisa si de verdad se guardó. El sitio no
# cambia de página al guardar, así que no basta con que el clic no falle: si
# algo estaba mal el formulario simplemente se queda ahí con el error. Se mira
# entonces si hay mensajes de error a la vista y si el botón Guardar sigue
# estando; cualquiera de las dos cosas significa que no se guardó.
def verificar_guardado_exitoso(page: Page, timeout: int = 4000) -> tuple[bool, str]:
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


# Espera a que el formulario se pueda escribir de verdad. Los campos aparecen
# en pantalla antes de estar listos: existen pero bloqueados, y si uno escribe
# en ese momento la fila falla. Por eso se espera a que dejen de estarlo.
def esperar_campos_formulario_editables(page: Page, timeout: int = 15000):
    try:
        page.wait_for_function(
            """() => { const e = document.getElementById('txtNombres');
                       return e && !e.readOnly && !e.disabled; }""",
            timeout=timeout,
        )
    except Exception:
        # Si no se desbloquea a tiempo, se deja que falle el paso siguiente:
        # queda como error de esa fila y el lote continúa.
        pass
    time.sleep(0.2)


# Busca la caja que corresponde a una etiqueta de la pantalla. No se puede
# asumir que estén una al lado de la otra: en proveedor, cargo y tienda la
# caja va debajo de la etiqueta. Se toma la primera caja que aparezca después.
def _input_por_etiqueta(page: Page, etiqueta: str) -> Optional[str]:
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


# Leer y escribir las cajas de texto simples y las listas desplegables de un
# solo valor (sexo, AFP, sistema de salud).

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


# Abre la lista y elige la opción que coincida con lo pedido, sin importar
# tildes ni mayúsculas ("banmedica" elige "Banmédica"). Solo se miran las
# opciones visibles de ese combo: antes se buscaba cualquier texto de la
# página y una celda vacía ("nan") calzaba con un aviso oculto del sitio.
# Si el valor viene vacío o no está en la lista, lanza CampoNoCompletado.
def escribir_combobox_simple(page: Page, fragmento: str, valor_deseado: str,
                             etiqueta: Optional[str] = None):
    nombre_campo = etiqueta or fragmento
    if es_vacio(valor_deseado):
        raise CampoNoCompletado(
            f"campo '{nombre_campo}' vacío en el Excel; completarlo con un valor del catálogo."
        )
    valor = str(valor_deseado).strip()

    try:
        page.locator(f'[id*="{fragmento}"][id$="_I"]').click(timeout=5000)
    except Exception as e:
        raise CampoNoCompletado(
            f"no se pudo abrir el campo '{nombre_campo}' para poner '{valor}': {e}"
        )
    time.sleep(0.3)

    info = page.evaluate(
        """([fragmento, deseado]) => {
            const norm = """ + _JS_NORM + """;
            document.querySelectorAll('[data-bot-opcion]')
                .forEach(e => e.removeAttribute('data-bot-opcion'));
            const visibles = Array.from(document.querySelectorAll('.dxeListBoxItem'))
                .filter(e => e.offsetParent !== null && e.textContent.trim() !== '');
            const delCombo = visibles.filter(e => (e.id || '').includes(fragmento));
            const items = delCombo.length ? delCombo : visibles;
            const objetivo = items.find(e => norm(e.textContent) === norm(deseado));
            if (objetivo) objetivo.setAttribute('data-bot-opcion', '1');
            return { ok: !!objetivo, opciones: items.map(e => e.textContent.trim()) };
        }""",
        [fragmento, valor],
    )

    if not info["ok"]:
        page.keyboard.press("Escape")
        disponibles = ", ".join(info["opciones"]) or "no se pudieron leer"
        raise CampoNoCompletado(
            f"campo '{nombre_campo}': el valor '{valor}' no existe en la lista del sitio "
            f"(opciones: {disponibles})."
        )

    try:
        page.locator('[data-bot-opcion="1"]').first.click(timeout=5000)
    except Exception as e:
        raise CampoNoCompletado(
            f"campo '{nombre_campo}': no se pudo seleccionar '{valor}': {e}"
        )
    time.sleep(0.3)


# Lee qué tiene puesto hoy una lista de las que aceptan varios valores
# (proveedor, cargo, tienda). El sitio los muestra juntos separados por ";".
def leer_multiselect(page: Page, etiqueta: str) -> list[str]:
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


# Dos esperas chicas pero necesarias antes de tocar una lista desplegable:
# que se vaya el velo de "cargando" que tapa la grilla y se come los clics, y
# que la lista alcance a dibujar sus opciones. La de cargo tiene más de cien y
# si se lee muy pronto parece vacía y se descarta un cargo que sí existía.

def _esperar_grid_sin_overlay(page: Page, timeout: int = 10000):
    try:
        page.wait_for_function(
            """() => { const d = document.getElementById('grillaExternosProveedorTrabajadores_LD');
                       return !d || d.offsetParent === null; }""",
            timeout=timeout,
        )
    except Exception:
        pass


def _esperar_items_listbox(page: Page, timeout: int = 5000):
    try:
        page.wait_for_function(
            """() => Array.from(document.querySelectorAll('.dxeListBoxItem'))
                .some(e => e.offsetParent !== null && e.querySelector('input[type=checkbox]'))""",
            timeout=timeout,
        )
    except Exception:
        pass
    time.sleep(0.2)


# Abre la lista y devuelve todas sus opciones, diciendo cuáles están marcadas.
# Ojo con cómo está armada por dentro: la casilla y el texto de cada opción
# son dos elementos distintos y seguidos, no uno solo, así que hay que irlos
# emparejando de a pares. La lista queda abierta al salir.
def obtener_opciones_multiselect(page: Page, etiqueta: str) -> list[dict]:
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


# Deja marcada una sola opción: desmarca todo lo demás y marca la que se
# pide. Estas listas suman en vez de reemplazar, por eso hay que desmarcar a
# mano. Avisa con False si esa opción no existe en el sitio.
def establecer_multiselect_valor_unico(page: Page, etiqueta: str, valor_deseado: str) -> bool:
    campo_id = _input_por_etiqueta(page, etiqueta)
    if not campo_id:
        return False
    _esperar_grid_sin_overlay(page)
    page.locator(f"#{campo_id}").click(timeout=5000)
    _esperar_items_listbox(page)

    resultado = page.evaluate(
        """(valorDeseado) => {
            const norm = """ + _JS_NORM + """;
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


# Mira si el cargo escrito en el Excel existe tal cual en el sitio. No cambia
# nada, solo revisa; si no existe, esa persona se omite completa.
def validar_cargo_existe(page: Page, cargo_deseado: str) -> bool:
    opciones = obtener_opciones_multiselect(page, "Categoría Trabajador:")
    texto_normalizado = normalizar_texto(cargo_deseado)
    existe = any(normalizar_texto(o["texto"]) == texto_normalizado for o in opciones)
    page.keyboard.press("Escape")
    time.sleep(0.2)
    return existe


# Aprieta la flecha que confirma el proveedor. Recién después de eso el sitio
# agrega las secciones de cargo y tienda, y se demora un poco en hacerlo: hay
# que esperarlas de verdad, porque si no todas las filas salían omitidas por
# "cargo inexistente" cuando en realidad el cargo aún no se había dibujado.
def confirmar_proveedor_seleccionado(page: Page):
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
        # Si igual no apareció, no se corta acá: se deja que falle el paso
        # siguiente, que avisa mejor qué pasó.
        pass
    time.sleep(0.3)
