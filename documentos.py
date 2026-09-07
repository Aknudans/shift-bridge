"""
Limpieza de documentos de un trabajador en ShiftLaboral (Fase 2, OPCIONAL).

⚠️⚠️  BORRA documentos reales de forma IRREVERSIBLE.  ⚠️⚠️
Solo corre si `crear_o_editar.py` recibe --limpiar-documentos, y solo sobre
personas que YA EXISTÍAN en la plataforma (identidad bloqueada al "Crear", o
RUT encontrado y editado). Nunca se ejecuta en una creación 100% nueva.

Vista involucrada: `DocumentosTrabajador.aspx`. Se llega clickeando el RUT en
la grilla de Trabajadores (NO el lápiz de editar). Estructura:
  - Grilla superior: checklist de tipos de documento (solo estado). NO se toca.
  - Grilla inferior (`tr.dxgvDataRow`): documentos efectivamente subidos. Cada
    fila tiene icono "ver" y, si lo subió el PROVEEDOR, también "borrar"
    (`a[title="borrar"]`). Los documentos cargados por el MANDANTE no tienen
    "borrar" — esos son "los que no es posible" y se dejan como están.

Popup de confirmación (DevExpress, ya presente en el DOM, oculto):
  contenedor  : #popupConfirmacionBorrar_grillaExternosDocumentosTrabajador
  confirmar   : #btnConfirmacionBorrarAceptar   ("Aceptar")
  cancelar    : #btnConfirmacionBorrarCancelar  ("Cancelar")
Popup de éxito tras borrar:
  aceptar     : #btnExitoAceptar_grillaExternosDocumentosTrabajador
Selectores confirmados en vivo 07/09/2026 (RUT de prueba 10016891-K, 20 docs,
6 con icono "borrar").
"""

import time
from typing import Optional

from playwright.sync_api import Page

from shift_common import (
    BASE_URL,
    seleccionar_grupo_proveedor,
    buscar_rut,
)

SEL_LINK_RUT = 'a[id*="link_Codigo_0"]'          # el código (RUT) en la fila filtrada
SEL_FILA_DOC = "tr.dxgvDataRow"
SEL_BORRAR = 'a[title="borrar"]'
SEL_CONFIRMAR = "#btnConfirmacionBorrarAceptar"
SEL_EXITO_OK = "#btnExitoAceptar_grillaExternosDocumentosTrabajador"
SEL_ERROR_OK = "#btnBorrarNoExitosoAceptar"

# Devuelve para cada fila borrable un texto corto identificatorio
_JS_LISTAR = """() => Array.from(document.querySelectorAll('tr.dxgvDataRow'))
    .filter(r => r.querySelector('a[title="borrar"]'))
    .map(r => {
        const tds = Array.from(r.querySelectorAll('td')).map(t => t.textContent.trim()).filter(Boolean);
        return tds.slice(1, 5).join(' | ');
    })"""

_JS_PRIMERA_BORRABLE = """() => {
    const r = Array.from(document.querySelectorAll('tr.dxgvDataRow'))
        .find(x => x.querySelector('a[title="borrar"]'));
    if (!r) return '';
    const tds = Array.from(r.querySelectorAll('td')).map(t => t.textContent.trim()).filter(Boolean);
    return tds.slice(1, 5).join(' | ');
}"""


def _abrir_vista_documentos(page: Page, rut: str, grupo_proveedor: str) -> bool:
    """Deja la grilla de Trabajadores filtrada por `rut` y abre su vista de
    documentos. Devuelve False si el RUT no aparece en la grilla."""
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    seleccionar_grupo_proveedor(page, grupo_proveedor)
    for _ in range(30):
        overlay = page.evaluate(
            "() => { const d = document.getElementById('grillaExternosProveedorTrabajadores_LD');"
            " return d && d.offsetParent !== null; }"
        )
        if not overlay:
            break
        time.sleep(0.5)
    if not buscar_rut(page, rut):
        return False
    page.locator(SEL_LINK_RUT).first.click(timeout=8000)
    page.wait_for_load_state("networkidle")
    try:
        page.wait_for_url("**/DocumentosTrabajador.aspx", timeout=10000)
    except Exception:
        pass
    time.sleep(1.0)
    return True


def limpiar_documentos_trabajador(
    page: Page, rut: str, grupo_proveedor: str, borrar: bool = False
) -> tuple[str, list[str]]:
    """Abre la vista de documentos de `rut` y:
      - borrar=False -> lista los documentos que TIENEN icono "borrar" (los
        que el proveedor puede eliminar). NO borra nada.
      - borrar=True  -> los borra uno por uno, aceptando el popup de
        confirmación de cada uno.
    Al terminar vuelve a la grilla de Trabajadores.

    Devuelve (accion, lista) donde accion es "listado" | "borrado" | "sin_rut"
    y lista son los textos de los documentos listados/borrados.
    """
    if not _abrir_vista_documentos(page, rut, grupo_proveedor):
        return ("sin_rut", [])

    def _esperar_sin_overlays():
        """Espera a que no haya overlays interceptando clics: el de carga de la
        grilla (`dxgvLoadingDiv`), el backdrop de modal jQuery UI
        (`.ui-widget-overlay`), o el de DevExpress (`.dxpcModalBackground`)."""
        try:
            page.wait_for_function(
                """() => {
                    const ld = document.getElementById('grillaExternosDocumentosTrabajador_LD');
                    if (ld && ld.offsetParent !== null) return false;
                    const tapa = Array.from(document.querySelectorAll(
                        '.ui-widget-overlay, [class*="dxpcModalBackground"], .modalExternos'))
                        .some(e => e.offsetParent !== null);
                    return !tapa;
                }""",
                timeout=10000,
            )
        except Exception:
            pass
        time.sleep(0.3)

    def _click_primero_visible(selectores, timeout=3000):
        """Clickea el primero de `selectores` que esté visible. Devuelve True
        si clickeó alguno."""
        for sel in selectores:
            try:
                loc = page.locator(sel)
                if loc.count() and loc.first.is_visible():
                    loc.first.click(timeout=timeout)
                    return True
            except Exception:
                continue
        return False

    def _cerrar_dialogo_abierto():
        """Si quedó un diálogo (éxito/error/confirmación) abierto de una
        iteración anterior, lo cierra para no bloquear el próximo clic."""
        _click_primero_visible([
            "#btnExitoAceptar_grillaExternosDocumentosTrabajador_2",
            "#btnExitoAceptar_grillaExternosDocumentosTrabajador",
            "#btnBorrarNoExitosoAceptar_2",
            "#btnBorrarNoExitosoAceptar",
            "#btnConfirmacionBorrarCancelar_2",
            "#btnConfirmacionBorrarCancelar",
        ])

    def _total_paginas():
        try:
            m = page.evaluate(
                r"""() => { const t = document.body.innerText.match(/P.gina\s+\d+\s+de\s+(\d+)/);
                            return t ? parseInt(t[1]) : 1; }"""
            )
            return max(1, int(m))
        except Exception:
            return 1

    def _ir_a_pagina(n):
        """Navega el pager de la grilla de documentos a la página n."""
        clic = page.evaluate(
            """(n) => {
                const cont = document.getElementById('grillaExternosDocumentosTrabajador');
                if (!cont) return false;
                const a = Array.from(cont.querySelectorAll('a'))
                    .find(x => x.offsetParent !== null && x.textContent.trim() === String(n));
                if (a) { a.click(); return true; }
                return false;
            }""",
            n,
        )
        page.wait_for_load_state("networkidle")
        _esperar_sin_overlays()
        return clic

    def _pagina_con_borrable():
        """Recorre las páginas y se queda en la primera que tenga un icono
        'borrar'. Devuelve True si encontró alguna, False si no queda ninguna."""
        for pg_n in range(1, _total_paginas() + 1):
            _ir_a_pagina(pg_n)
            if page.locator(SEL_BORRAR).count() > 0:
                return True
        return False

    # --- modo LISTAR: recorre todas las páginas, no borra nada ---
    if not borrar:
        vistos: list[str] = []
        for pg_n in range(1, _total_paginas() + 1):
            _ir_a_pagina(pg_n)
            vistos.extend(page.evaluate(_JS_LISTAR))
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        return ("listado", vistos)

    borrados: list[str] = []
    guarda = 0
    repetidos = 0
    while guarda < 300:
        _cerrar_dialogo_abierto()
        _esperar_sin_overlays()
        if not _pagina_con_borrable():
            break
        guarda += 1

        etiqueta = page.evaluate(_JS_PRIMERA_BORRABLE)
        # Blindaje: si intentamos borrar 2 veces seguidas el MISMO documento,
        # el borrado no está surtiendo efecto -> cortar.
        if borrados and etiqueta and etiqueta == borrados[-1]:
            repetidos += 1
            if repetidos >= 2:
                borrados.append(f"[DETENIDO: '{etiqueta}' no se borra, se aborta la limpieza]")
                break
        else:
            repetidos = 0

        page.locator(SEL_BORRAR).first.click(timeout=8000)
        # 1) popup "¿Está seguro de borrar el documento?" -> Aceptar
        page.wait_for_selector(SEL_CONFIRMAR, state="visible", timeout=6000)
        _click_primero_visible([SEL_CONFIRMAR + "_2", SEL_CONFIRMAR], timeout=5000)
        page.wait_for_load_state("networkidle")
        # 2) popup "Operación exitosa ... Aceptar" (o el de error) -> Aceptar
        try:
            page.wait_for_selector(
                "#btnExitoAceptar_grillaExternosDocumentosTrabajador_2, #btnBorrarNoExitosoAceptar_2",
                state="visible", timeout=6000)
        except Exception:
            pass
        _click_primero_visible([
            "#btnExitoAceptar_grillaExternosDocumentosTrabajador_2",
            "#btnExitoAceptar_grillaExternosDocumentosTrabajador",
            "#btnBorrarNoExitosoAceptar_2",
            "#btnBorrarNoExitosoAceptar",
        ], timeout=5000)
        page.wait_for_load_state("networkidle")
        time.sleep(0.6)
        borrados.append(etiqueta)

    _cerrar_dialogo_abierto()
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    return ("borrado", borrados)
