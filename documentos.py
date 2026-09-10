import time
from typing import Optional

from playwright.sync_api import Page

from shift_common import (
    BASE_URL,
    normalizar_texto,
    seleccionar_grupo_proveedor,
    buscar_rut,
)

SEL_LINK_RUT = 'a[id*="link_Codigo_0"]'          # el RUT de la fila, que es el enlace a sus documentos
SEL_FILA_DOC = "tr.dxgvDataRow"
SEL_BORRAR = 'a[title="borrar"]'
SEL_CONFIRMAR = "#btnConfirmacionBorrarAceptar"
SEL_EXITO_OK = "#btnExitoAceptar_grillaExternosDocumentosTrabajador"
SEL_ERROR_OK = "#btnBorrarNoExitosoAceptar"

# Dos lecturas de la tabla de documentos: la lista completa de los que se
# pueden borrar y, aparte, el primero de ellos. De cada uno se arma un texto
# corto que sirve para reconocerlo en el reporte.
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


# Llegar a la pantalla de documentos de una persona y volver de ahí. Es el
# camino más caro de todo el bot (recarga, elegir grupo, filtrar y entrar), así
# que conviene hacerlo una sola vez por persona y aprovechar la visita para
# todo lo que haya que hacerle: ver ese `gestionar_documentos_trabajador`.

def _abrir_vista_documentos(page: Page, rut: str, grupo_proveedor: str) -> bool:
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


def _volver_a_trabajadores(page: Page):
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")


# Esta pantalla se llena de capas grises que se comen los clics: la de
# "cargando" y las de los avisos. Estas tres funciones son para lidiar con
# eso: esperar a que no quede ninguna, clickear el primer botón que esté a la
# vista de una lista, y cerrar cualquier aviso que haya quedado abierto de la
# vuelta anterior.

def _esperar_sin_overlays(page: Page):
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


def _click_primero_visible(page: Page, selectores, timeout=3000) -> bool:
    for sel in selectores:
        try:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


def _cerrar_dialogo_abierto(page: Page):
    _click_primero_visible(page, [
        "#btnExitoAceptar_grillaExternosDocumentosTrabajador_2",
        "#btnExitoAceptar_grillaExternosDocumentosTrabajador",
        "#btnBorrarNoExitosoAceptar_2",
        "#btnBorrarNoExitosoAceptar",
        "#btnConfirmacionBorrarCancelar_2",
        "#btnConfirmacionBorrarCancelar",
    ])


# La tabla muestra de a diez documentos, así que casi siempre hay más de una
# página. Estas dos funciones son para saber cuántas hay e ir a una de ellas;
# sin recorrerlas todas uno se pierde la mitad de los documentos.

def _total_paginas(page: Page) -> int:
    try:
        m = page.evaluate(
            r"""() => { const t = document.body.innerText.match(/P.gina\s+\d+\s+de\s+(\d+)/);
                        return t ? parseInt(t[1]) : 1; }"""
        )
        return max(1, int(m))
    except Exception:
        return 1


def _ir_a_pagina(page: Page, n: int) -> bool:
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
    _esperar_sin_overlays(page)
    return clic


# Deja sin documentación a alguien que ya venía cargado de antes. Solo se
# pueden tocar los documentos que subió el proveedor: los que puso el mandante
# ni siquiera tienen botón de borrar. Con borrar=False solo se listan.
# Se van borrando de a uno, aceptando el aviso de cada uno.
# Da por hecho que la pantalla de documentos ya está abierta y la deja abierta:
# quien llama se encarga de llegar hasta ahí y de salir.
def _limpiar_en_vista_abierta(page: Page, borrar: bool = False) -> tuple[str, list[str]]:
    # Se para en la primera página donde todavía quede algo por borrar.
    def _pagina_con_borrable():
        for pg_n in range(1, _total_paginas(page) + 1):
            _ir_a_pagina(page, pg_n)
            if page.locator(SEL_BORRAR).count() > 0:
                return True
        return False

    # Solo mirar: se recorren todas las páginas y no se borra nada.
    if not borrar:
        vistos: list[str] = []
        for pg_n in range(1, _total_paginas(page) + 1):
            _ir_a_pagina(page, pg_n)
            vistos.extend(page.evaluate(_JS_LISTAR))
        return ("listado", vistos)

    borrados: list[str] = []
    guarda = 0
    repetidos = 0
    while guarda < 300:
        _cerrar_dialogo_abierto(page)
        _esperar_sin_overlays(page)
        if not _pagina_con_borrable():
            break
        guarda += 1

        etiqueta = page.evaluate(_JS_PRIMERA_BORRABLE)
        # Si el mismo documento aparece dos veces seguidas, el borrado no está
        # funcionando y hay que cortar antes de quedar dando vueltas.
        if borrados and etiqueta and etiqueta == borrados[-1]:
            repetidos += 1
            if repetidos >= 2:
                borrados.append(f"[DETENIDO: '{etiqueta}' no se borra, se aborta la limpieza]")
                break
        else:
            repetidos = 0

        page.locator(SEL_BORRAR).first.click(timeout=8000)
        # Primero el "¿está seguro?".
        page.wait_for_selector(SEL_CONFIRMAR, state="visible", timeout=6000)
        _click_primero_visible(page, [SEL_CONFIRMAR + "_2", SEL_CONFIRMAR], timeout=5000)
        page.wait_for_load_state("networkidle")
        # Y después el aviso de que salió bien (o de que falló). Aceptarlo es
        # obligatorio: si no, su capa gris tapa la tabla y el borrado
        # siguiente no llega a hacerse.
        try:
            page.wait_for_selector(
                "#btnExitoAceptar_grillaExternosDocumentosTrabajador_2, #btnBorrarNoExitosoAceptar_2",
                state="visible", timeout=6000)
        except Exception:
            pass
        _click_primero_visible(page, [
            "#btnExitoAceptar_grillaExternosDocumentosTrabajador_2",
            "#btnExitoAceptar_grillaExternosDocumentosTrabajador",
            "#btnBorrarNoExitosoAceptar_2",
            "#btnBorrarNoExitosoAceptar",
        ], timeout=5000)
        page.wait_for_load_state("networkidle")
        time.sleep(0.6)
        borrados.append(etiqueta)

    _cerrar_dialogo_abierto(page)
    return ("borrado", borrados)


# Versión suelta de lo anterior, para usarla sola: navega hasta la persona,
# hace la limpieza y vuelve a la lista de trabajadores.
def limpiar_documentos_trabajador(
    page: Page, rut: str, grupo_proveedor: str, borrar: bool = False
) -> tuple[str, list[str]]:
    if not _abrir_vista_documentos(page, rut, grupo_proveedor):
        return ("sin_rut", [])
    resultado = _limpiar_en_vista_abierta(page, borrar)
    _volver_a_trabajadores(page)
    return resultado


# Saca el tipo de cada documento cargado, sin importar quién lo haya subido.
# Con esto se sabe qué tiene ya la persona y no se le vuelve a subir lo mismo.
_JS_LISTAR_TIPOS = """() => Array.from(document.querySelectorAll('tr.dxgvDataRow')).map(r => {
    const tds = Array.from(r.querySelectorAll('td')).map(t => t.textContent.trim());
    return tds[2] || '';
}).filter(Boolean)"""


# Para cuando la pantalla de documentos ya está abierta y solo hay que leerla,
# sin volver a navegar hasta ella.
def _leer_tipos_en_vista_abierta(page: Page) -> list[str]:
    _cerrar_dialogo_abierto(page)
    _esperar_sin_overlays(page)
    tipos: list[str] = []
    for pg_n in range(1, _total_paginas(page) + 1):
        _ir_a_pagina(page, pg_n)
        tipos.extend(page.evaluate(_JS_LISTAR_TIPOS))
    return tipos


# Versión suelta de lo anterior, para usarla sola: navega hasta la persona,
# lee lo que tiene cargado y vuelve. No sube ni borra nada.
def tipos_documentos_existentes(page: Page, rut: str, grupo_proveedor: str) -> tuple[str, list[str]]:
    if not _abrir_vista_documentos(page, rut, grupo_proveedor):
        return ("sin_rut", [])
    tipos = _leer_tipos_en_vista_abierta(page)
    _volver_a_trabajadores(page)
    return ("listado", tipos)


# De acá para abajo, la subida de documentos. Se usa el módulo de carga masiva
# del propio sitio, que está en la misma pantalla: se eligen todos los
# archivos de una vez y aparece una fila por archivo, donde hay que poner
# nombre, período, tipo y fecha de vencimiento. El sitio procesa después, por
# su cuenta, así que los documentos no aparecen al toque.

import os
import unicodedata

EXTENSIONES_OK = (".pdf", ".docx", ".xlsx", ".jpg", ".jpeg", ".png")

# Los tipos de documento que ofrece el sitio, escritos igual que allá pero sin
# el prefijo del catálogo adelante.
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

# Los ocho documentos que trae normalmente la carpeta de un ingreso nuevo. Si
# falta alguno no se frena nada, solo queda avisado en el reporte.
DOCUMENTOS_SET_ESTANDAR = [
    "Cédula de Identidad",
    "Contrato puesta a disposición",
    "Contacto en caso de Emergencia",
    "Toma de conocimiento marca en biometrico (EST)",
    "Registro Entrega EPP",
    "Registro de Capacitación Uso EPP",
    "Registro de Capacitación IRL (Ex Odi) Mandante",
    "TC Reglamento Interno RIOHS mandante",
]

SEL_BTN_CM = "#btnDocumentosMasivos_2"
SEL_CM_FILE = "#FileDocumentosTrabajadorMasivo"
SEL_CM_GUARDAR = "#btnGuardarModalCargaMasivaDocumentos_2"
SEL_CM_CANCELAR = "#btnCancelarModalCargaMasivaDocumentos_2"


# Empareja nombres escritos de cualquier manera: sin tildes, sin importar
# mayúsculas y tratando guiones, puntos y guiones bajos como si fueran
# espacios. Así "Adán_León", "adan-leon" y "ADAN LEON" son lo mismo. Se usa
# tanto para calzar carpeta con persona como archivo con tipo de documento.
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    for ch in ("_", "-", ".", ","):
        s = s.replace(ch, " ")
    return " ".join(s.upper().split())


# Los archivos que entrega la gente no se llaman como el tipo del catálogo:
# usan abreviaturas y otra redacción. Esta tabla traduce lo uno en lo otro
# buscando pedazos del nombre. Se revisa en orden y gana el primero que calce,
# así que conviene dejar arriba los casos más específicos. Cuando aparezcan
# nombres nuevos que no calcen con nada, se agregan acá.
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


# Adivina qué tipo de documento es un archivo por su nombre: primero busca que
# se llame igual que un tipo del catálogo y, si no, prueba con la tabla de
# equivalencias. Si no calza con nada, devuelve None y el archivo se omite.
def tipo_desde_nombre_archivo(nombre_archivo: str) -> Optional[str]:
    stem = os.path.splitext(os.path.basename(nombre_archivo))[0]
    objetivo = _norm(stem)
    for tipo in CATALOGO_TIPOS_DOCUMENTO:
        if _norm(tipo) == objetivo:
            return tipo
    for rx, tipo in _MAPEO_NOMBRE_TIPO:
        if rx.search(objetivo):
            return tipo
    return None


# Revisa la carpeta de una persona y arma la lista de lo que se le va a subir.
# Lo que no sirve queda aparte, con el motivo, para que salga en el reporte en
# vez de desaparecer sin más.
def preparar_items_carpeta(carpeta_persona: str):
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


# Elige el tipo en la lista desplegable de una de las filas de archivos. En el
# sitio los tipos aparecen con el prefijo del catálogo adelante, así que se lo
# saca antes de comparar.
def _seleccionar_tipo_en_combo(page: Page, indice: int, tipo_sin_prefijo: str) -> bool:
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


# Llena una fecha (el período o el vencimiento) de una de las filas. Estos
# campos abren un calendario y no basta con escribirles el texto: hay que
# avisarle al calendario, si no al guardar el sitio ignora lo escrito y pone
# una fecha cualquiera.
def _set_periodo(page: Page, indice: int, valor_ddmmaaaa: str,
                 campo: str = "calendario_documento_masivo"):
    sel = f"#{campo}_{indice}"
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


# Aprieta Guardar y acepta el aviso de éxito. Devuelve False si el sitio se
# queja de que faltan campos por llenar.
def _guardar_carga_masiva(page: Page) -> bool:
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


# Le sube a una persona todos los documentos de su carpeta, de una sola vez.
# Antes de subir mira qué tiene ya cargado y saltea esos: el sitio no revisa
# nada de eso, así que correr esto dos veces le dejaba los documentos
# duplicados.
# El período se deja en blanco, que es como lo hacen a mano; si el sitio lo
# rechaza, se completa con la fecha de contratación y se reintenta. La fecha
# de vencimiento en cambio siempre hay que ponerla, el sitio no la perdona.
# Con guardar=False se llena todo pero se cancela, para poder mirar sin subir.
# Da por hecho que la pantalla ya está abierta y la deja abierta.
# `tipos_ya_leidos` sirve para no releer la tabla cuando quien llama acaba de
# leerla: paginarla de nuevo es caro y no habría cambiado nada.
def _subir_en_vista_abierta(
    page: Page, items, periodo_ddmmaaaa: str, vencimiento_ddmmaaaa: str = "",
    guardar: bool = True, dejar_periodo_vacio: bool = True,
    omitir_existentes: bool = True, tipos_ya_leidos=None,
):
    if not items:
        return ("sin_items", [], [], [])

    ya_existian: list[str] = []
    items_a_subir = items
    if omitir_existentes:
        tipos = tipos_ya_leidos if tipos_ya_leidos is not None else _leer_tipos_en_vista_abierta(page)
        tipos_actuales_norm = {normalizar_texto(t) for t in tipos}
        items_a_subir = []
        for it in items:
            if normalizar_texto(it["tipo"]) in tipos_actuales_norm:
                ya_existian.append(it["tipo"])
            else:
                items_a_subir.append(it)

    if not items_a_subir:
        return ("sin_items_nuevos", [], ya_existian, [])

    # Si antes de esto hubo un borrado, puede haber quedado algún aviso abierto
    # tapando el botón de carga masiva.
    _cerrar_dialogo_abierto(page)
    _esperar_sin_overlays(page)

    errores = []
    page.locator(SEL_BTN_CM).first.click(timeout=8000)
    page.wait_for_selector(SEL_CM_FILE, state="attached", timeout=8000)
    time.sleep(0.5)

    page.set_input_files(SEL_CM_FILE, [it["ruta"] for it in items_a_subir])
    try:
        page.wait_for_selector(f"#cboTipoDocumentos_{len(items_a_subir) - 1}", timeout=10000)
    except Exception:
        errores.append("no aparecieron todas las filas de archivos tras seleccionarlos")
    time.sleep(0.8)

    subidos = []
    for n, it in enumerate(items_a_subir):
        try:
            page.fill(f"#nombre_documento_masivo_{n}", it["nombre"], timeout=4000)
        except Exception:
            errores.append(f"{it['nombre']}: no se pudo escribir el Nombre")
        if not dejar_periodo_vacio:
            _set_periodo(page, n, periodo_ddmmaaaa, campo="calendario_documento_masivo")
        # La fecha de vencimiento va siempre: destildar la casilla no sirve,
        # el sitio la sigue exigiendo igual.
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
        return ("simulado", subidos, ya_existian, errores)

    accion = "subido"
    if not _guardar_carga_masiva(page):
        # Si se quejó por campos vacíos, se le pone el período y se reintenta.
        if dejar_periodo_vacio and periodo_ddmmaaaa:
            for n in range(len(items_a_subir)):
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

    return (accion, subidos, ya_existian, errores)


# Versión suelta de lo anterior, para usarla sola: navega hasta la persona,
# sube y vuelve a la lista de trabajadores.
def subir_documentos_trabajador(
    page: Page, rut: str, grupo_proveedor: str,
    items, periodo_ddmmaaaa: str, vencimiento_ddmmaaaa: str = "",
    guardar: bool = True, dejar_periodo_vacio: bool = True,
    omitir_existentes: bool = True,
):
    if not items:
        return ("sin_items", [], [], [])
    if not _abrir_vista_documentos(page, rut, grupo_proveedor):
        return ("sin_rut", [], [], [])
    resultado = _subir_en_vista_abierta(
        page, items, periodo_ddmmaaaa, vencimiento_ddmmaaaa,
        guardar=guardar, dejar_periodo_vacio=dejar_periodo_vacio,
        omitir_existentes=omitir_existentes)
    _volver_a_trabajadores(page)
    return resultado


# Le hace a una persona TODO lo que haya que hacerle con sus documentos en una
# sola visita: limpiar los viejos, anotar los que tiene y subir los nuevos.
# Antes cada una de esas tres cosas navegaba por su cuenta hasta la misma
# pantalla, y llegar ahí es lo más lento del bot: pedir las tres significaba
# hacer tres veces el mismo camino y leer dos veces la misma tabla.
#
# El orden importa: primero se borra lo viejo, después se mira qué quedó, y
# recién entonces se sube — así lo que se acaba de borrar no cuenta como "ya lo
# tenía" y no se saltea la subida.
#
# Devuelve un diccionario con lo que se haya hecho; las claves que no
# correspondan vienen en None, para que quien llama sepa distinguir "no se
# pidió" de "se pidió y no encontró nada".
def gestionar_documentos_trabajador(
    page: Page, rut: str, grupo_proveedor: str,
    limpiar=None, verificar: bool = False, items=None,
    periodo_ddmmaaaa: str = "", vencimiento_ddmmaaaa: str = "",
    guardar: bool = True, omitir_existentes: bool = True,
):
    resultado = {"sin_rut": False, "limpieza": None, "tipos": None, "subida": None}
    if not (limpiar or verificar or items):
        return resultado

    if not _abrir_vista_documentos(page, rut, grupo_proveedor):
        resultado["sin_rut"] = True
        return resultado

    try:
        if limpiar:
            resultado["limpieza"] = _limpiar_en_vista_abierta(page, borrar=(limpiar == "borrar"))

        # Se lee una sola vez y se reusa para la subida, que necesita lo mismo.
        tipos = None
        if verificar or (items and omitir_existentes):
            tipos = _leer_tipos_en_vista_abierta(page)
            if verificar:
                resultado["tipos"] = tipos

        if items:
            resultado["subida"] = _subir_en_vista_abierta(
                page, items, periodo_ddmmaaaa, vencimiento_ddmmaaaa,
                guardar=guardar, omitir_existentes=omitir_existentes,
                tipos_ya_leidos=tipos)
    finally:
        # Pase lo que pase hay que volver a la lista, o la fila siguiente
        # arranca parada en la pantalla equivocada.
        _volver_a_trabajadores(page)

    return resultado
