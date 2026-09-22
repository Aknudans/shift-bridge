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
    RutAmbiguoEnGrilla,
    seleccionar_grupo_proveedor,
)

# Selectores propios de esta fase, la que solo mira y compara. Lo que se
# comparte con la fase de creación está en shift_common.py.

# La lupa para abrir la ficha. Se busca por el título del enlace y no por su
# id, que cambia según la fila.
SELECTOR_BOTON_VER = 'a[title="ver"]'

# Cómo se llama cada dato en pantalla y cómo lo llamamos nosotros. El texto
# tiene que ir igual que en la ficha, con los dos puntos incluidos.
ETIQUETAS_DETALLE = {
    "Nombres:": "nombre",
    "Apellido Paterno:": "apellido_paterno",
    "Apellido Materno:": "apellido_materno",
    "Sexo:": "sexo",
    "AFP:": "afp",
    "Sistema de Salud:": "sistema_salud",
    "Sueldo Base:": "sueldo_base",
}

# Proveedor, cargo y tienda no son texto suelto sino listas aparte. De sus ids
# largos solo este pedazo se mantiene igual, y con eso alcanza para ubicarlas.
ID_FRAGMENTO_PROVEEDORES = "lstProveedores"
ID_FRAGMENTO_CARGO = "lstVerClientes"
ID_FRAGMENTO_TIENDA = "listBoxTienda"

COLUMNAS_EXCEL_REQUERIDAS = [
    "RUT", "NOMBRES", "apellidoPaterno", "apellidoMaterno", "SEXO", "AFP", "ISAPRE", "PROVEEDOR",
    "sueldoBase", "CARGO", "TIENDA",
]


# Lo que se anota de cada persona para armar después el reporte.
@dataclass
class ResultadoFila:
    rut: str
    nombre_excel: str
    estado: str
    detalle: str = ""
    datos_sistema: dict = field(default_factory=dict)


# Abre la ficha de la persona filtrada y se trae todos sus datos.
# La lectura se hace con un poco de JavaScript en vez de con los buscadores de
# Playwright porque el apellido materno viene envuelto de otra forma que el
# resto y con esos buscadores nunca aparecía.
def extraer_datos_detalle(page: Page) -> dict:
    page.click(SELECTOR_BOTON_VER)
    page.wait_for_load_state("networkidle")
    try:
        # Se espera a que la ficha esté dibujada; cuánto demora depende de
        # cómo ande el servidor, así que no sirve esperar un rato fijo.
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
        # Si la fila quedó abierta en modo edición de una vuelta anterior, en
        # vez del dato se lee el código del formulario. Ningún dato real es
        # tan largo, así que se descarta antes de ensuciar el reporte.
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


# Cierra la ficha con el botón Cancelar. Es obligatorio: si queda abierta, la
# siguiente persona hereda esa vista abierta y se leen datos que no son suyos.
def cerrar_vista_detalle(page: Page):
    try:
        page.locator("#btnCancelar").click(timeout=3000)
        page.wait_for_load_state("networkidle")
        time.sleep(0.3)
    except Exception:
        pass


# Lee las listas de proveedor, cargo y tienda de la ficha. Una persona puede
# tener más de uno de cada cosa, así que se devuelven todos juntos separados
# por coma para poder compararlos contra la celda del Excel.
def extraer_lista_valores(page: Page, id_fragmento: str) -> Optional[str]:
    valores = page.evaluate(
        """(fragmento) => {
            return Array.from(document.querySelectorAll('.dxeListBoxItem'))
                .filter(e => e.offsetParent !== null && e.id.includes(fragmento))
                .map(e => e.textContent.trim());
        }""",
        id_fragmento,
    )
    return ", ".join(valores) if valores else None


# Campo por campo, Excel contra sistema. Si todo calza queda en OK; si algo
# difiere, queda en advertencia con el detalle de qué no cuadra.
def comparar_datos(fila_excel: pd.Series, datos_sistema: dict) -> tuple[str, str]:
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


# Color de fondo de cada fila del reporte, para leerlo de un vistazo.
COLORES_ESTADO = {
    "OK": "C6EFCE",
    "ADVERTENCIA": "FFEB9C",
    "NO_ENCONTRADO": "FFC7CE",
}


# Recorre el Excel fila por fila: elige el grupo, busca el RUT, compara y
# anota el resultado. Si una persona falla, se deja el error escrito y se
# sigue con la siguiente, nunca se corta el lote entero.
# Los argumentos se pueden pasar a mano en vez de leerlos de la línea de
# comandos, que es como los llama la app empaquetada.
def main(argv=None):
    parser = argparse.ArgumentParser(description="Bot de búsqueda y comparación — ShiftLaboral (solo lectura)")
    parser.add_argument("--input", required=True, help="Ruta al Excel de colaboradores a verificar")
    parser.add_argument("--output", default="reporte.xlsx", help="Ruta del Excel de salida")
    args = parser.parse_args(argv)

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
                                             detalle=(str(e) if isinstance(e, RutAmbiguoEnGrilla)
                                                      else f"Error inesperado durante el procesamiento: {e}")))
            print(f"   -> ERROR: {e}")
            # Se intenta dejar la página en orden para la fila siguiente.
            try:
                asegurar_pagina_trabajadores(page)
            except Exception:
                pass

    escribir_reporte(resultados, args.output, COLORES_ESTADO)

    # Conteo final para la consola.
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