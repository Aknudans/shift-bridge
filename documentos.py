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


# ===========================================================================
# CARGA MASIVA DE DOCUMENTOS  (Fase 2, opcional, --subir-documentos)
# ===========================================================================
#
# Vista: DocumentosTrabajador.aspx (misma de la limpieza). Botón "Carga masiva
# documentos" = #btnDocumentosMasivos_2 -> panel inline
# #panelCargaModalDocumentosMasivo.
#   input file múltiple : #FileDocumentosTrabajadorMasivo
#                         (accept .pdf,.docx,.xlsx,.jpg,.png)
#   por archivo (fila .ext-doc-ms-row, índice N 0-based en orden de archivo):
#     Nombre  : #nombre_documento_masivo_{N}      (texto, obligatorio)
#     Período : #calendario_documento_masivo_{N}  (datepicker jQuery UI)
#     Tipo    : #cboTipoDocumentos_{N}            (<select> nativo)
#   Guardar  : #btnGuardarModalCargaMasivaDocumentos_2
#   Cancelar : #btnCancelarModalCargaMasivaDocumentos_2
# Procesamiento asíncrono ("actualizar la página en un par de minutos").
# Ver CLAUDE.md §12.9.

import os
import unicodedata

EXTENSIONES_OK = (".pdf", ".docx", ".xlsx", ".jpg", ".jpeg", ".png")

# Los 16 tipos del catálogo (sin el prefijo "LOGISTICA FALABELLA/").
# Confirmados en vivo 07/09/2026 leyendo el <select> #cboTipoDocumentos_0.
CATALOGO_TIPOS_DOCUMENTO = [
    "Anexos de Contrato",
    "Anexos",
    "Liquidaciones de Sueldo",
    "Registro de Capacitación IRL (Ex Odi) Mandante",
    "TC Reglamento Interno RIOHS mandante",
    "Registro Entrega EPP",
    "Registro de Capacitación Uso EPP",
    "Contrato de Trabajo",
    "Cédula de Identidad",
    "Finiquito de Trabajo",
    "Contrato puesta a disposición",
    "Visa de trabajo o ATT",
    "Contacto en caso de Emergencia",
    "Toma de conocimiento marca en biometrico (EST)",
    "Anexos de contrato personal EST",
    "Comprobante de Entrevista del personal EST y OUT",
]

SEL_BTN_CM = "#btnDocumentosMasivos_2"
SEL_CM_FILE = "#FileDocumentosTrabajadorMasivo"
SEL_CM_GUARDAR = "#btnGuardarModalCargaMasivaDocumentos_2"
SEL_CM_CANCELAR = "#btnCancelarModalCargaMasivaDocumentos_2"


def _norm(s: str) -> str:
    """Normaliza para comparar SIN sensibilidad a: mayúsculas/minúsculas,
    tildes/acentos, ni al separador usado (espacio, `-`, `_`, `.` o `,` son
    equivalentes). Colapsa espacios repetidos. Se usa para calzar:
      - nombre de subcarpeta  <-> nombre del colaborador (Excel)
      - nombre de archivo      <-> tipo del catálogo de documentos
    Así 'Adán_León', 'adan-leon' y 'ADAN LEON' son lo mismo."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    for ch in ("_", "-", ".", ","):
        s = s.replace(ch, " ")
    return " ".join(s.upper().split())


# Mapeo nombre de archivo real -> tipo del catálogo. Los archivos que entregan
# NO se llaman como el tipo exacto (usan abreviaturas / otra redacción), así que
# se busca por patrón sobre el nombre normalizado (`_norm`). Se evalúa EN ORDEN,
# gana el primero que matchee. Confirmado con el usuario 07/09/2026 sobre el
# set estándar de ingreso (carpeta "Adan_Leon", 8 documentos).
import re as _re

_MAPEO_NOMBRE_TIPO = [
    (_re.compile(r"\bRIOHS\b"),                     "TC Reglamento Interno RIOHS mandante"),
    (_re.compile(r"\bIRL\b|EX ?ODI"),               "Registro de Capacitación IRL (Ex Odi) Mandante"),
    (_re.compile(r"CONTACTO (DE|EN CASO)"),         "Contacto en caso de Emergencia"),
    (_re.compile(r"MARCAJE BIOMETRICO|MARCA EN BIOMETRICO|TOMA DE CONOCIMIENTO MARCA"),
     "Toma de conocimiento marca en biometrico (EST)"),
    (_re.compile(r"ENTREGA .*EPP|EPP .*ENTREGA"),   "Registro Entrega EPP"),
    (_re.compile(r"USO EPP"),                       "Registro de Capacitación Uso EPP"),
    (_re.compile(r"^C\s*I\b|CEDULA|CARNET"),        "Cédula de Identidad"),
    (_re.compile(r"^CD\b|CONTRATO PUESTA A DISPOSICION|CONTRATO DE DISPOSICION|\bCPD\b"),
     "Contrato puesta a disposición"),
    (_re.compile(r"CONTRATO DE TRABAJO"),           "Contrato de Trabajo"),
    (_re.compile(r"FINIQUITO"),                     "Finiquito de Trabajo"),
    (_re.compile(r"\bVISA\b|\bATT\b"),              "Visa de trabajo o ATT"),
    (_re.compile(r"ANEXO.*PERSONAL EST"),           "Anexos de contrato personal EST"),
    (_re.compile(r"ANEXO DE CONTRATO|ANEXOS DE CONTRATO"), "Anexos de Contrato"),
    (_re.compile(r"COMPROBANTE.*ENTREVISTA"),       "Comprobante de Entrevista del personal EST y OUT"),
    (_re.compile(r"LIQUIDACION"),                   "Liquidaciones de Sueldo"),
]


def tipo_desde_nombre_archivo(nombre_archivo: str) -> Optional[str]:
    """Del nombre del archivo (sin extensión) deduce el tipo del catálogo.
    1) coincidencia exacta con un tipo del catálogo, si no
    2) patrón de `_MAPEO_NOMBRE_TIPO`.
    Devuelve el tipo EXACTO del catálogo (sin prefijo) o None si no calza."""
    stem = os.path.splitext(os.path.basename(nombre_archivo))[0]
    objetivo = _norm(stem)
    for tipo in CATALOGO_TIPOS_DOCUMENTO:
        if _norm(tipo) == objetivo:
            return tipo
    for rx, tipo in _MAPEO_NOMBRE_TIPO:
        if rx.search(objetivo):
            return tipo
    return None


def preparar_items_carpeta(carpeta_persona: str):
    """Recorre `carpeta_persona` y arma la lista de documentos a subir.
    Devuelve (items, omitidos):
      items    = [{"ruta", "nombre", "tipo"}]  (tipo del catálogo, sin prefijo)
      omitidos = ["archivo.x (motivo)", ...]
    """
    items = []
    omitidos = []
    try:
        entradas = sorted(os.listdir(carpeta_persona))
    except Exception as e:
        return [], [f"(no se pudo leer la carpeta: {e})"]
    for nombre in entradas:
        ruta = os.path.join(carpeta_persona, nombre)
        if not os.path.isfile(ruta):
            continue
        ext = os.path.splitext(nombre)[1].lower()
        if ext not in EXTENSIONES_OK:
            omitidos.append(f"{nombre} (extensión no aceptada)")
            continue
        tipo = tipo_desde_nombre_archivo(nombre)
        if not tipo:
            omitidos.append(f"{nombre} (el nombre no calza con ningún tipo del catálogo)")
            continue
        items.append({"ruta": ruta, "nombre": os.path.splitext(nombre)[0], "tipo": tipo})
    return items, omitidos


def _seleccionar_tipo_en_combo(page: Page, indice: int, tipo_sin_prefijo: str) -> bool:
    """Selecciona en #cboTipoDocumentos_{indice} la opción cuyo texto calza con
    `tipo_sin_prefijo` (el <select> lista 'LOGISTICA FALABELLA/<Tipo>')."""
    valor = page.evaluate(
        """(args) => {
            const cbo = document.getElementById('cboTipoDocumentos_' + args.idx);
            if (!cbo) return null;
            const norm = s => (s || '').normalize('NFKD').replace(/[\\u0300-\\u036f]/g, '')
                .toUpperCase().replace(/[_\\-.,]/g, ' ').replace(/\\s+/g, ' ').trim();
            const objetivo = norm(args.tipo);
            for (const o of cbo.options) {
                let t = norm(o.textContent);
                const pre = 'LOGISTICA FALABELLA/';
                if (t.startsWith(pre)) t = t.slice(pre.length).trim();
                if (t === objetivo) return o.value;
            }
            return null;
        }""",
        {"idx": indice, "tipo": tipo_sin_prefijo},
    )
    if valor is None:
        return False
    page.select_option(f"#cboTipoDocumentos_{indice}", value=valor)
    return True


def _set_periodo(page: Page, indice: int, valor_ddmmaaaa: str,
                 campo: str = "calendario_documento_masivo"):
    """Setea un campo de fecha (datepicker jQuery UI: Período o Fecha de
    Vencimiento). Igual que 'Fin Contrato': .fill() suele fallar en estos
    inputs -> se setea .value + eventos."""
    sel = f"#{campo}_{indice}"
    # Estos inputs son datepicker de jQuery UI. Setear el `.value` (por .fill()
    # o por JS) NO actualiza el modelo interno del datepicker y al Guardar el
    # sitio usa la fecha por defecto (quedó '04/01/1990' en las pruebas). Hay
    # que usar `datepicker('setDate', Date)`.
    page.evaluate(
        """(args) => {
            const inp = document.querySelector(args.sel);
            if (!inp) return;
            const [d, m, y] = args.val.split('/').map(Number);
            const fecha = new Date(y, m - 1, d);
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(inp, args.val);
            try {
                if (window.jQuery && jQuery(inp).hasClass('hasDatepicker')) {
                    jQuery(inp).datepicker('setDate', fecha);
                }
            } catch (e) {}
            ['input', 'keyup', 'change', 'blur'].forEach(e => inp.dispatchEvent(new Event(e, {bubbles: true})));
        }""",
        {"sel": sel, "val": valor_ddmmaaaa},
    )


_MSG_CAMPOS_VACIOS = "Debe completar los campos vac"


def _guardar_carga_masiva(page: Page) -> bool:
    """Clic en Guardar de la carga masiva + acepta el popup de éxito.
    Devuelve False si el sitio muestra "Debe completar los campos vacíos"
    (validación fallida, el panel sigue abierto)."""
    page.locator(SEL_CM_GUARDAR).first.click(timeout=8000)
    page.wait_for_load_state("networkidle")
    time.sleep(1.5)
    if _MSG_CAMPOS_VACIOS in page.inner_text("body"):
        return False
    for sel in ("#btnExitoAceptar_grillaExternosDocumentosTrabajador_2",
                "#btnExitoAceptar_grillaExternosDocumentosTrabajador"):
        try:
            if page.locator(sel).is_visible(timeout=2500):
                page.locator(sel).click(timeout=3000)
                break
        except Exception:
            pass
    time.sleep(1.0)
    return True


def subir_documentos_trabajador(
    page: Page, rut: str, grupo_proveedor: str,
    items, periodo_ddmmaaaa: str, vencimiento_ddmmaaaa: str = "",
    guardar: bool = True, dejar_periodo_vacio: bool = True,
):
    """Sube `items` ([{ruta, nombre, tipo}]) al trabajador `rut` vía la carga
    masiva.

    - `periodo_ddmmaaaa`: fecha para el campo "Período". Los usuarios reales lo
      dejan VACÍO en la carga masiva, así que por defecto
      (`dejar_periodo_vacio=True`) NO se llena; solo se completa si el sitio
      rechaza el Guardar con "Debe completar los campos vacíos" (fallback
      auto — comportamiento inferido, sin verificar en vivo que el sitio
      acepte Período vacío).
    - `vencimiento_ddmmaaaa`: "Fecha de vencimiento". El sitio SÍ la exige
      (probado); si viene vacía se usa `periodo_ddmmaaaa`.

    guardar=False -> llena el formulario pero hace Cancelar (modo prueba).

    Devuelve (accion, subidos, errores):
      accion = "subido" | "subido_con_periodo" | "simulado" | "sin_rut" |
               "sin_items" | "rechazado"
    """
    if not items:
        return ("sin_items", [], [])
    if not _abrir_vista_documentos(page, rut, grupo_proveedor):
        return ("sin_rut", [], [])

    errores = []
    page.locator(SEL_BTN_CM).first.click(timeout=8000)
    page.wait_for_selector(SEL_CM_FILE, state="attached", timeout=8000)
    time.sleep(0.5)

    page.set_input_files(SEL_CM_FILE, [it["ruta"] for it in items])
    try:
        page.wait_for_selector(f"#cboTipoDocumentos_{len(items) - 1}", timeout=10000)
    except Exception:
        errores.append("no aparecieron todas las filas de archivos tras seleccionarlos")
    time.sleep(0.8)

    subidos = []
    for n, it in enumerate(items):
        try:
            page.fill(f"#nombre_documento_masivo_{n}", it["nombre"], timeout=4000)
        except Exception:
            errores.append(f"{it['nombre']}: no se pudo escribir el Nombre")
        if not dejar_periodo_vacio:
            _set_periodo(page, n, periodo_ddmmaaaa, campo="calendario_documento_masivo")
        # La "Fecha de vencimiento" es OBLIGATORIA (probado: desmarcar la
        # casilla / ComplentarInfo NO la libera).
        _set_periodo(page, n, vencimiento_ddmmaaaa or periodo_ddmmaaaa,
                     campo="calendario_fecha_vencimiento_documento_masivo")
        if _seleccionar_tipo_en_combo(page, n, it["tipo"]):
            subidos.append(it["tipo"])
        else:
            errores.append(f"{it['nombre']}: el tipo '{it['tipo']}' no está en el combo")

    if not guardar:
        try:
            page.locator(SEL_CM_CANCELAR).first.click(timeout=5000)
        except Exception:
            pass
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        return ("simulado", subidos, errores)

    accion = "subido"
    if not _guardar_carga_masiva(page):
        # El sitio pidió completar campos. Si habíamos dejado el Período
        # vacío, lo llenamos ahora (con `periodo_ddmmaaaa`) y reintentamos.
        if dejar_periodo_vacio and periodo_ddmmaaaa:
            for n in range(len(items)):
                _set_periodo(page, n, periodo_ddmmaaaa, campo="calendario_documento_masivo")
            if _guardar_carga_masiva(page):
                accion = "subido_con_periodo"
            else:
                errores.append("el sitio rechazó el Guardar aun con Período completo")
                accion = "rechazado"
        else:
            errores.append("el sitio rechazó el Guardar ('Debe completar los campos vacíos')")
            accion = "rechazado"
        if accion == "rechazado":
            try:
                page.locator(SEL_CM_CANCELAR).first.click(timeout=5000)
            except Exception:
                pass

    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    return (accion, subidos, errores)
