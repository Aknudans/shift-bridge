"""
Utilidades compartidas entre buscar_y_comparar.py (Fase 1, solo lectura) y
crear_o_editar.py (Fase 2, creación/edición): conexión a Chrome, navegación,
búsqueda de RUT, normalización de texto y escritura del reporte Excel.

Este módulo NO se ejecuta solo — es soporte importado por los dos scripts
principales. Los selectores de acá están confirmados en vivo contra el sitio
real (ver CLAUDE.md secciones 6 y 12); cualquier selector nuevo que se
descubra debe documentarse también en CLAUDE.md, no solo quedar en el código.
"""

import sys
import time
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from playwright.sync_api import sync_playwright, Page
import pandas as pd

# ---------------------------------------------------------------------------
# CONFIGURACIÓN COMPARTIDA
# ---------------------------------------------------------------------------

BASE_URL = "https://externoslof.shiftlabor.com/Funcionalidades/Externos/ProveedorTrabajador.aspx"
CDP_URL = "http://localhost:9222"  # puerto de depuración remota de Chrome

SELECTOR_FILTRO_RUT = "#grillaExternosProveedorTrabajadores_DXFREditorcol2_I"

# Tabla principal de la grilla. CONFIRMADO EN VIVO 05/08/2026: NO usar
# "tr.dxgvDataRow" para detectar filas — si una fila quedó previamente
# "expandida" (vista de detalle abierta) en la misma sesión de navegador, su
# clase cambia a "dxgvEditFormDisplayRow" y ese selector deja de encontrarla,
# reportando "no encontrado" con un RUT que sí existe. Mejor buscar el RUT
# directamente en las celdas, sin depender de la clase de la fila.
SELECTOR_TABLA_GRILLA = "#grillaExternosProveedorTrabajadores_DXMainTable"

# Input del combo "Grupo Proveedor" (DevExpress ASPxComboBox). CONFIRMADO EN VIVO
# que requiere clic real de mouse para abrir (no responde a .click() vía JS).
SELECTOR_INPUT_GRUPO_PROVEEDOR = "#MJJerarquia00_I"

# Selectores del menú lateral, usados para navegar/resetear la vista de
# Trabajadores pasando por el menú en vez de solo recargar la URL.
SELECTOR_BOTON_MENU = "#icono_abrir_menu"
SELECTOR_MENU_EXTERNOS = "#mf_cab_01"  # ⚠️ requiere clic real de mouse
SELECTOR_MENU_TRABAJADORES = "#mf_cab_ll_01_01"

# El Excel suele traer Proveedor/Cargo/Tienda con el prefijo
# "LOGISTICA FALABELLA/" (mismo formato de catálogo), pero el sitio no
# siempre lo muestra igual entre la vista de solo lectura y el formulario
# editable (ver CLAUDE.md secciones 6 y 12). Se quita de ambos lados antes
# de comparar para no generar falsos positivos.
PREFIJO_CATALOGO = "LOGISTICA FALABELLA/"


# ---------------------------------------------------------------------------
# UTILIDADES DE TEXTO Y EXCEL
# ---------------------------------------------------------------------------

def normalizar_texto(valor: Optional[str]) -> str:
    """Normaliza texto para comparar sin sensibilidad a mayúsculas/espacios."""
    if valor is None:
        return ""
    return str(valor).strip().upper()


def quitar_prefijo_catalogo(valor: Optional[str]) -> str:
    """Quita el prefijo 'LOGISTICA FALABELLA/' (si está) antes de comparar."""
    texto = normalizar_texto(valor)
    if texto.startswith(normalizar_texto(PREFIJO_CATALOGO)):
        return texto[len(PREFIJO_CATALOGO):].strip()
    return texto


# El template SHIFT.xlsx usa los MISMOS nombres/orden de columna que la
# "Planilla Agosto" de origen (rut, nombre, sexo, cargo, desde, hasta, afp,
# isapre, ...), para que el usuario final copie y pegue el bloque sin remapear
# nada. Acá se traducen a los nombres internos que espera el resto del código
# (RUT, NOMBRES, SEXO, CARGO, fechaContratacion, fechaTermino, AFP, ISAPRE).
# Las columnas centroCosto/sucursal vienen en el template solo para que el
# pegado calce en columna; el bot no las usa.
RENOMBRE_COLUMNAS_ENTRADA = {
    "rut": "RUT",
    "nombre": "NOMBRES",
    "sexo": "SEXO",
    "cargo": "CARGO",
    "desde": "fechaContratacion",
    "hasta": "fechaTermino",
    "afp": "AFP",
    "isapre": "ISAPRE",
}


def normalizar_sexo(valor: Optional[str]) -> str:
    """'M' / 'Masculino' -> 'Masculino'; 'F' / 'Femenino' -> 'Femenino'.

    La Planilla Agosto trae el sexo como 'M'/'F'; ShiftLaboral (y la
    comparación de Fase 1) esperan la palabra completa. Se aplica al cargar el
    Excel para que el resto del código no tenga que saber de esto."""
    if valor is None:
        return ""
    t = str(valor).strip().upper()
    if t in ("M", "MASCULINO"):
        return "Masculino"
    if t in ("F", "FEMENINO"):
        return "Femenino"
    if t in ("", "NAN", "NONE"):
        return ""
    return str(valor).strip()


def cargar_excel(path: str, columnas_requeridas: list[str]) -> pd.DataFrame:
    """Carga la primera hoja del Excel, traduce los encabezados estilo
    'Planilla Agosto' a los nombres internos, normaliza el sexo y valida que
    estén todas las columnas obligatorias."""
    df = pd.read_excel(path, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns=RENOMBRE_COLUMNAS_ENTRADA)

    if "SEXO" in df.columns:
        df["SEXO"] = df["SEXO"].map(normalizar_sexo)

    faltantes = [c for c in columnas_requeridas if c not in df.columns]
    if faltantes:
        print(f"ERROR: Faltan columnas obligatorias en el Excel de entrada: {faltantes}")
        sys.exit(1)

    return df


# ---------------------------------------------------------------------------
# CONEXIÓN Y NAVEGACIÓN
# ---------------------------------------------------------------------------

def conectar_a_chrome_existente():
    """
    Se conecta a una ventana de Chrome YA ABIERTA (con --remote-debugging-port=9222)
    donde el usuario ya inició sesión manualmente en ShiftLaboral. No abre una
    ventana nueva ni maneja credenciales.
    """
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(CDP_URL)
    except Exception as e:
        print("ERROR: No se pudo conectar a Chrome en el puerto 9222.")
        print("¿Abriste Chrome con --remote-debugging-port=9222 y dejaste esa ventana abierta?")
        print(f"Detalle técnico: {e}")
        sys.exit(1)

    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.pages[0] if context.pages else context.new_page()
    return playwright, browser, page


def asegurar_pagina_trabajadores(page: Page):
    if BASE_URL not in page.url:
        page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")


def navegar_a_trabajadores_por_menu(page: Page):
    """
    Va a la vista de Trabajadores pasando por el menú lateral (hamburguesa ->
    Externos -> Trabajadores), en vez de solo recargar la URL. Se usa tanto
    para navegación inicial como para RESETEAR la vista después de un
    Crear/Editar exitoso (pedido explícito del usuario en Fase 2), asegurando
    que el servidor quede en un estado limpio antes de la siguiente fila.

    Usa .click() de Playwright (clic real), NO page.evaluate — confirmado que
    el paso "Externos" no responde a click programático vía JS.

    Como esto navega a una página nueva, el Grupo Proveedor seleccionado se
    pierde — quien llama debe volver a seleccionarlo para la siguiente fila.
    """
    page.locator(SELECTOR_BOTON_MENU).click(timeout=5000)
    time.sleep(0.3)
    page.locator(SELECTOR_MENU_EXTERNOS).click(timeout=5000)  # requiere clic real, confirmado
    time.sleep(0.3)
    page.locator(SELECTOR_MENU_TRABAJADORES).click(timeout=5000)
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)


def seleccionar_grupo_proveedor(page: Page, nombre_proveedor: str):
    """
    Selecciona automáticamente el proveedor/grupo correcto en el combo superior
    izquierdo (#MJJerarquia00_I) antes de buscar, ya que el listado de
    trabajadores solo muestra los del grupo seleccionado.

    CONFIRMADO EN VIVO: el combo requiere clic real de mouse para abrir (no
    responde a .click() programático vía JS) — locator.click() de Playwright
    simula un clic real y sí funciona.

    La columna PROVEEDOR del Excel puede venir con un prefijo tipo
    "LOGISTICA FALABELLA/..." (mismo formato usado en los catálogos de
    Cargo/Tienda), pero el dropdown del sitio solo muestra el texto después de
    esa barra (ej. "Grupo Colchagua Empresa de Servicios Transitorios S.A.").
    Se usa solo esa última parte para buscar la opción visible.
    """
    texto_busqueda = nombre_proveedor.split("/")[-1].strip()

    page.locator(SELECTOR_INPUT_GRUPO_PROVEEDOR).click(timeout=5000)
    time.sleep(0.3)
    opcion = page.locator(f"text={texto_busqueda}").first
    opcion.click(timeout=5000)
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)


def buscar_rut(page: Page, rut: str) -> bool:
    """Escribe el RUT en el filtro de la grilla y presiona Enter. Devuelve True si hay resultados.

    CONFIRMADO EN VIVO 05/08/2026: `networkidle` se cumple ANTES de que el
    callback AJAX de DevExpress termine de renderizar la fila filtrada — un
    RUT real llegó a reportarse como "no encontrado" porque se leyó el grid
    demasiado pronto. Se agrega una espera explícita a que aparezca el RUT en
    una celda de la grilla (o se agote el timeout, señal de que de verdad no
    hay resultados) en vez de confiar solo en un sleep fijo.
    """
    filtro = page.locator(SELECTOR_FILTRO_RUT)
    filtro.click()
    filtro.fill("")
    filtro.fill(rut)
    filtro.press("Enter")
    page.wait_for_load_state("networkidle")
    selector_resultado = f"{SELECTOR_TABLA_GRILLA} td:has-text('{rut}')"
    try:
        page.wait_for_selector(selector_resultado, timeout=5000)
    except Exception:
        pass
    time.sleep(0.3)

    return page.locator(selector_resultado).count() > 0


def limpiar_filtro(page: Page):
    """Limpia el filtro de RUT para dejar la grilla lista para la siguiente búsqueda."""
    filtro = page.locator(SELECTOR_FILTRO_RUT)
    filtro.click()
    filtro.fill("")
    filtro.press("Enter")
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)


# ---------------------------------------------------------------------------
# REPORTE DE SALIDA
# ---------------------------------------------------------------------------

def escribir_reporte(resultados: list, output_path: str, colores_estado: dict):
    """Escribe un reporte Excel coloreado por estado.

    `resultados` es cualquier lista de objetos con atributos .rut,
    .nombre_excel, .estado y .detalle (cada script define su propio
    ResultadoFila, con campos adicionales si los necesita).
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Reporte"

    encabezados = ["RUT", "Nombre (Excel)", "Estado", "Detalle"]
    ws.append(encabezados)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for r in resultados:
        ws.append([r.rut, r.nombre_excel, r.estado, r.detalle])
        fill = PatternFill(start_color=colores_estado.get(r.estado, "FFFFFF"),
                            end_color=colores_estado.get(r.estado, "FFFFFF"),
                            fill_type="solid")
        for cell in ws[ws.max_row]:
            cell.fill = fill

    for col_cells in ws.columns:
        largo = max(len(str(c.value)) if c.value else 0 for c in col_cells)
        ws.column_dimensions[col_cells[0].column_letter].width = min(largo + 4, 80)

    try:
        wb.save(output_path)
    except PermissionError:
        alterno = f"{output_path.rsplit('.', 1)[0]}_{int(time.time())}.xlsx"
        print(f"\nADVERTENCIA: no se pudo guardar en '{output_path}' "
              f"(¿está abierto en Excel u otro programa?). Guardando como '{alterno}' en su lugar.")
        wb.save(alterno)
        output_path = alterno

    print(f"\nReporte guardado en: {output_path}")
