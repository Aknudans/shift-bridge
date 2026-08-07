"""
Bot de búsqueda y comparación de colaboradores — ShiftLaboral (Fase 1: solo lectura)
=======================================================================================

QUÉ HACE:
Para cada colaborador de tu Excel de entrada, busca su RUT en ShiftLaboral. Si lo
encuentra, extrae Nombres, Apellido Paterno, Apellido Materno, Sexo, AFP, Sistema
de Salud, Sueldo Base, Proveedores, Cargo y Tiendas, y los compara contra tu
Excel. Genera un Excel de reporte con 3 estados posibles por fila:

    OK            -> RUT encontrado y todos los datos coinciden
    ADVERTENCIA   -> RUT encontrado pero uno o más datos NO coinciden (se detallan)
    NO_ENCONTRADO -> el RUT no existe en ShiftLaboral (candidato a creación futura)

Esta fase NO crea, edita ni borra nada. Solo lee. Es seguro de correr las veces
que quieras.

REQUISITOS PREVIOS (una sola vez):
    1. Python 3.9+
    2. pip install playwright pandas openpyxl
       playwright install chromium   (o usa tu Chrome normal, ver más abajo)
    3. Abrir Google Chrome manualmente con depuración remota habilitada:

       Windows (cmd):
           "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222

       Mac:
           /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222

    4. En esa ventana de Chrome, iniciar sesión MANUALMENTE en ShiftLaboral
       (https://externoslof.shiftlabor.com/) con tu usuario y contraseña, como
       siempre. El bot NUNCA maneja contraseñas — solo reutiliza tu sesión ya
       iniciada.
    5. Dejar esa ventana de Chrome abierta y correr este script.

EXCEL DE ENTRADA ESPERADO (primera hoja del archivo):
    Columnas obligatorias (nombres exactos, case-insensitive):
        RUT, NOMBRES, apellidoPaterno, apellidoMaterno, SEXO, AFP, ISAPRE,
        sueldoBase, PROVEEDOR, CARGO, TIENDA
    Columnas adicionales toleradas (usadas en Fase 2, ignoradas por ahora):
        fechaContratacion, fechaTermino

USO:
    python buscar_y_comparar.py --input colaboradores.xlsx --output reporte.xlsx

NOTA IMPORTANTE SOBRE SELECTORES:
    Los selectores usados aquí (IDs de campos, nombres de dropdowns) fueron
    extraídos inspeccionando el DOM real de ShiftLaboral el 05/08/2026. Si
    ShiftLaboral actualiza su plataforma, estos IDs pueden cambiar y el script
    dejará de funcionar — es el riesgo inherente de automatizar una interfaz
    no oficial (ver conversación previa sobre por qué no existe una API).
"""

import argparse
import time
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
from playwright.sync_api import Page

from shift_common import (
    asegurar_pagina_trabajadores,
    buscar_rut,
    cargar_excel,
    conectar_a_chrome_existente,
    escribir_reporte,
    limpiar_filtro,
    normalizar_texto,
    quitar_prefijo_catalogo,
    seleccionar_grupo_proveedor,
)

# ---------------------------------------------------------------------------
# CONFIGURACIÓN — selectores específicos de Fase 1 (búsqueda/comparación).
# Los selectores compartidos con Fase 2 (conexión, navegación, filtro de RUT,
# grupo proveedor) viven en shift_common.py — ver ese archivo para esos.
# ---------------------------------------------------------------------------

# Ícono "ver" (lupa) de la fila de resultado filtrado. CONFIRMADO EN VIVO
# 05/08/2026: el ID completo real es
# "grillaExternosProveedorTrabajadores_cell0_8_grillaExternosProveedorTrabajadores_link_ver_0"
# pero es más robusto seleccionar por atributo (inmune a cambios de índice/prefijo).
# Como filtramos por RUT único, siempre debería haber como máximo 1 resultado.
SELECTOR_BOTON_VER = 'a[title="ver"]'

# Mapeo de las etiquetas que aparecen en la vista de detalle (modo "ver") a
# nuestros nombres de campo internos. Deben calzar EXACTO con el texto que
# aparece en pantalla (incluye los dos puntos ":").
ETIQUETAS_DETALLE = {
    "Nombres:": "nombre",
    "Apellido Paterno:": "apellido_paterno",
    "Apellido Materno:": "apellido_materno",
    "Sexo:": "sexo",
    "AFP:": "afp",
    "Sistema de Salud:": "sistema_salud",
    "Sueldo Base:": "sueldo_base",
}

# Fragmentos ESTABLES de los ids de los listbox de solo lectura (Proveedores,
# Categoría Trabajador = Cargo, Tiendas) en la vista de detalle. El resto del
# id depende del índice de fila del grid filtrado, que no es estable — pero
# como el filtro de RUT siempre deja como máximo 1 fila, basta con buscar por
# ESTE fragmento. CONFIRMADO EN VIVO 05/08/2026 con Claude in Chrome.
ID_FRAGMENTO_PROVEEDORES = "lstProveedores"
ID_FRAGMENTO_CARGO = "lstVerClientes"
ID_FRAGMENTO_TIENDA = "listBoxTienda"

COLUMNAS_EXCEL_REQUERIDAS = [
    "RUT", "NOMBRES", "apellidoPaterno", "apellidoMaterno", "SEXO", "AFP", "ISAPRE", "PROVEEDOR",
    "sueldoBase", "CARGO", "TIENDA",
]


# ---------------------------------------------------------------------------
# MODELOS DE DATOS
# ---------------------------------------------------------------------------

@dataclass
class ResultadoFila:
    rut: str
    nombre_excel: str
    estado: str  # "OK" | "ADVERTENCIA" | "NO_ENCONTRADO"
    detalle: str = ""
    datos_sistema: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# LÓGICA DE AUTOMATIZACIÓN ESPECÍFICA DE FASE 1
# (conexión, navegación y búsqueda de RUT compartidas viven en shift_common.py)
# ---------------------------------------------------------------------------

def extraer_datos_detalle(page: Page) -> dict:
    """
    Abre la vista de detalle (ícono 'ver') de la primera fila filtrada y extrae
    los campos personales usando el patrón: <td>Etiqueta:</td><td>Valor</td>.

    Usa page.evaluate (lectura de DOM, no clic) en vez del selector de texto de
    Playwright (`td:text-is(...) + td`), porque se confirmó en vivo que el
    campo "Apellido Materno:" en particular viene envuelto en un <span> interno
    (a diferencia de los demás campos, que son texto plano dentro del <td>).
    Playwright's :text-is() prefiere el elemento MÁS INTERNO que posee el texto
    exacto — como el <span> lo posee, el <td> deja de calzar con ese selector y
    la extracción fallaba en timeout (dato quedaba en None) aunque el valor
    estuviera perfectamente visible en pantalla. Comparar textContent en JS
    plano no tiene ese problema, sea o no el texto un nodo directo del <td>.
    """
    page.click(SELECTOR_BOTON_VER)
    page.wait_for_load_state("networkidle")
    try:
        # Espera explícita a que el callback AJAX de la vista de detalle haya
        # terminado de renderizar, en vez de confiar en un sleep fijo (el
        # tiempo real puede variar según la carga del servidor).
        page.wait_for_selector("td:has-text('Nombres:')", timeout=5000)
    except Exception:
        pass
    time.sleep(0.3)

    datos = {}
    for etiqueta, campo in ETIQUETAS_DETALLE.items():
        valor = page.evaluate(
            """(etiqueta) => {
                const td = Array.from(document.querySelectorAll('td'))
                    .find(t => t.textContent.trim() === etiqueta);
                const siguiente = td ? td.nextElementSibling : null;
                return siguiente ? siguiente.textContent.trim() : null;
            }""",
            etiqueta,
        )
        # Blindaje: si la fila quedó "pegada" en modo edición de una corrida
        # anterior (ver más abajo, cierre con #btnCancelar), el <td> siguiente
        # puede contener un editor interactivo con su script de inicialización
        # completo en vez del valor simple — se manifiesta como texto de miles
        # de caracteres con código JS. Un valor de negocio real nunca es así
        # de largo, así que se descarta en vez de reportarlo como discrepancia.
        if valor is not None and len(valor) > 300:
            valor = None
        datos[campo] = valor

    datos["proveedores"] = extraer_lista_valores(page, ID_FRAGMENTO_PROVEEDORES)
    datos["cargo"] = extraer_lista_valores(page, ID_FRAGMENTO_CARGO)
    datos["tienda"] = extraer_lista_valores(page, ID_FRAGMENTO_TIENDA)

    if all(v is None for v in datos.values()):
        captura = f"debug_vista_detalle_{int(time.time())}.png"
        try:
            page.screenshot(path=captura, full_page=True)
            print(f"   -> DEPURACIÓN: no se extrajo ningún campo del detalle. "
                  f"Captura guardada en {captura} para diagnóstico.")
        except Exception:
            pass

    cerrar_vista_detalle(page)

    return datos


def cerrar_vista_detalle(page: Page):
    """
    Cierra la vista de detalle con el botón "Cancelar" (#btnCancelar).

    CONFIRMADO EN VIVO 05/08/2026: si no se cierra explícitamente, la fila
    queda "pegada" en modo edición/expandido — al filtrar la siguiente fila,
    DevExpress reutiliza ese mismo estado expandido para el nuevo trabajador
    en vez de mostrar la fila colapsada normal, lo que corrompió una corrida
    completa (ver sección 6 del CLAUDE.md, "Paso 11").
    """
    try:
        page.locator("#btnCancelar").click(timeout=3000)
        page.wait_for_load_state("networkidle")
        time.sleep(0.3)
    except Exception:
        pass


def extraer_lista_valores(page: Page, id_fragmento: str) -> Optional[str]:
    """
    Extrae todos los valores seleccionados de un listbox de solo lectura
    (DevExpress ASPxListBox: Proveedores, Categoría Trabajador/Cargo, Tiendas)
    en la vista de detalle, dado un fragmento estable del id (el resto depende
    del índice de fila del grid filtrado, que no es estable).

    Puede haber más de un valor si el trabajador tiene más de un
    proveedor/cargo/tienda asignado — se unen con ", " para poder comparar
    contra el Excel como un solo string. Devuelve None si no encontró nada.
    """
    valores = page.evaluate(
        """(fragmento) => {
            return Array.from(document.querySelectorAll('.dxeListBoxItem'))
                .filter(e => e.offsetParent !== null && e.id.includes(fragmento))
                .map(e => e.textContent.trim());
        }""",
        id_fragmento,
    )
    return ", ".join(valores) if valores else None


def comparar_datos(fila_excel: pd.Series, datos_sistema: dict) -> tuple[str, str]:
    """Compara los datos del Excel contra lo extraído del sistema. Devuelve (estado, detalle)."""
    comparaciones = [
        ("Nombre", fila_excel["NOMBRES"], datos_sistema.get("nombre"), normalizar_texto),
        ("Apellido Paterno", fila_excel["apellidoPaterno"], datos_sistema.get("apellido_paterno"), normalizar_texto),
        ("Apellido Materno", fila_excel["apellidoMaterno"], datos_sistema.get("apellido_materno"), normalizar_texto),
        ("Sexo", fila_excel["SEXO"], datos_sistema.get("sexo"), normalizar_texto),
        ("AFP", fila_excel["AFP"], datos_sistema.get("afp"), normalizar_texto),
        ("Sistema de Salud", fila_excel["ISAPRE"], datos_sistema.get("sistema_salud"), normalizar_texto),
        ("Sueldo Base", fila_excel["sueldoBase"], datos_sistema.get("sueldo_base"), normalizar_texto),
        ("Proveedores", fila_excel["PROVEEDOR"], datos_sistema.get("proveedores"), quitar_prefijo_catalogo),
        ("Cargo", fila_excel["CARGO"], datos_sistema.get("cargo"), quitar_prefijo_catalogo),
        ("Tiendas", fila_excel["TIENDA"], datos_sistema.get("tienda"), quitar_prefijo_catalogo),
    ]

    discrepancias = []
    for nombre_campo, valor_excel, valor_sistema, normalizar in comparaciones:
        if normalizar(valor_excel) != normalizar(valor_sistema):
            discrepancias.append(
                f"{nombre_campo} no coincide (sistema: '{valor_sistema}' / excel: '{valor_excel}')"
            )

    if discrepancias:
        return "ADVERTENCIA", "; ".join(discrepancias)
    return "OK", "Todos los datos coinciden"


# ---------------------------------------------------------------------------
# REPORTE DE SALIDA
# ---------------------------------------------------------------------------

COLORES_ESTADO = {
    "OK": "C6EFCE",             # verde suave
    "ADVERTENCIA": "FFEB9C",    # amarillo suave
    "NO_ENCONTRADO": "FFC7CE",  # rojo suave
}


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Bot de búsqueda y comparación — ShiftLaboral (solo lectura)")
    parser.add_argument("--input", required=True, help="Ruta al Excel de colaboradores a verificar")
    parser.add_argument("--output", default="reporte.xlsx", help="Ruta del Excel de salida")
    args = parser.parse_args()

    df = cargar_excel(args.input, COLUMNAS_EXCEL_REQUERIDAS)
    print(f"Cargados {len(df)} colaboradores desde {args.input}")

    playwright, browser, page = conectar_a_chrome_existente()
    asegurar_pagina_trabajadores(page)

    resultados: list[ResultadoFila] = []
    grupo_actual = None

    for i, fila in df.iterrows():
        rut = str(fila["RUT"]).strip()
        nombre_completo = f"{fila['NOMBRES']} {fila['apellidoPaterno']}"
        print(f"[{i+1}/{len(df)}] Buscando RUT {rut} ({nombre_completo})...")

        try:
            proveedor = str(fila["PROVEEDOR"]).strip()
            if proveedor != grupo_actual:
                seleccionar_grupo_proveedor(page, proveedor)
                grupo_actual = proveedor

            encontrado = buscar_rut(page, rut)

            if not encontrado:
                resultados.append(ResultadoFila(rut=rut, nombre_excel=nombre_completo,
                                                 estado="NO_ENCONTRADO",
                                                 detalle="RUT no existe en ShiftLaboral"))
                print("   -> No encontrado")
                continue

            datos_sistema = extraer_datos_detalle(page)
            estado, detalle = comparar_datos(fila, datos_sistema)
            resultados.append(ResultadoFila(rut=rut, nombre_excel=nombre_completo,
                                             estado=estado, detalle=detalle,
                                             datos_sistema=datos_sistema))
            print(f"   -> {estado}: {detalle}")

            limpiar_filtro(page)

        except Exception as e:
            resultados.append(ResultadoFila(rut=rut, nombre_excel=nombre_completo,
                                             estado="ERROR",
                                             detalle=f"Error inesperado durante el procesamiento: {e}"))
            print(f"   -> ERROR: {e}")
            # Intentar recuperar el estado de la página para la siguiente fila
            try:
                asegurar_pagina_trabajadores(page)
            except Exception:
                pass

    escribir_reporte(resultados, args.output, COLORES_ESTADO)

    # Resumen en consola
    total = len(resultados)
    ok = sum(1 for r in resultados if r.estado == "OK")
    adv = sum(1 for r in resultados if r.estado == "ADVERTENCIA")
    no_enc = sum(1 for r in resultados if r.estado == "NO_ENCONTRADO")
    err = sum(1 for r in resultados if r.estado == "ERROR")
    print(f"\nResumen: {total} procesados | OK: {ok} | Advertencia: {adv} | No encontrado: {no_enc} | Error: {err}")

    browser.close()
    playwright.stop()


if __name__ == "__main__":
    main()