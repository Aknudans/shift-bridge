"""
Bot de creación y edición de colaboradores — ShiftLaboral (Fase 2)
====================================================================

QUÉ HACE:
Para cada colaborador de tu Excel de entrada, busca su RUT en ShiftLaboral:

    - Si NO existe -> hace clic en "Crear" y llena el formulario completo con
      los datos del Excel.
    - Si SÍ existe -> hace clic en "editar", lee los valores ACTUALES del
      formulario, calcula qué campos difieren del Excel, y modifica SOLO esos
      campos (nunca toca los que ya coinciden).

En ambos casos, si el Cargo del Excel no calza EXACTO con una opción real del
catálogo (dropdown "Categoría Trabajador"), esa fila se OMITE COMPLETA (no se
crea ni se edita nada de esa persona) y se reporta como error.

Al final genera un Excel de reporte con el resultado de cada fila: CREADO,
EDITADO (con el detalle de qué campos cambiaron), SIN_CAMBIOS, OMITIDO_CARGO
o ERROR.

⚠️ A DIFERENCIA DE buscar_y_comparar.py (Fase 1, solo lectura), este script
   SÍ modifica datos reales en ShiftLaboral. Probarlo primero con 2-3 filas
   de prueba antes de correrlo contra el Excel completo de producción — igual
   protocolo que el descrito en CLAUDE.md sección 8, pero aplicado a Fase 2.

REQUISITOS PREVIOS: los mismos que buscar_y_comparar.py — ver ese archivo o
README.md. Usar preferentemente ejecutar_crear.bat, que automatiza la
apertura de Chrome y el login.

EXCEL DE ENTRADA ESPERADO: mismas columnas que buscar_y_comparar.py, más
fechaContratacion y fechaTermino, que aquí SÍ son obligatorias (se usan para
Inicio Contrato / Fin Contrato al crear o editar).

USO:
    python crear_o_editar.py --input colaboradores.xlsx --output reporte_crear.xlsx

NOTA IMPORTANTE: los selectores de "editar"/"Crear"/"Guardar" fueron
explorados en vivo el 05/08/2026 (ver CLAUDE.md sección 12), pero el botón
"Guardar" nunca se probó realmente durante esa exploración (a propósito, para
no modificar datos sin autorización). Validar con cuidado la primera corrida.
"""

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Optional

import pandas as pd
from playwright.sync_api import Page

# La consola de Windows (cp1252) no puede imprimir varios caracteres que
# aparecen en los mensajes de error de Playwright (flechas, etc.). Sin esto,
# un `print()` de un error revienta con UnicodeEncodeError y MATA todo el
# script en vez de registrar la fila y seguir con la siguiente.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from shift_common import (
    asegurar_pagina_trabajadores,
    buscar_rut,
    cargar_excel,
    conectar_a_chrome_existente,
    escribir_reporte,
    limpiar_filtro,
    navegar_a_trabajadores_por_menu,
    normalizar_texto,
    quitar_prefijo_catalogo,
    seleccionar_grupo_proveedor,
)
from campos_formulario import (
    cerrar_formulario,
    confirmar_proveedor_seleccionado,
    esperar_campos_formulario_editables,
    escribir_campo_texto,
    escribir_combobox_simple,
    establecer_multiselect_valor_unico,
    leer_campo_texto,
    leer_combobox_simple,
    leer_multiselect,
    validar_cargo_existe,
)
from documentos import limpiar_documentos_trabajador

# ---------------------------------------------------------------------------
# CONFIGURACIÓN — selectores específicos de Fase 2 (crear/editar). Los
# selectores compartidos con Fase 1 (conexión, navegación, filtro de RUT,
# grupo proveedor) viven en shift_common.py; las primitivas de lectura/
# escritura de campos del formulario (comboboxes, multi-select, etc.) viven
# en campos_formulario.py — ver esos archivos para esos selectores.
# ---------------------------------------------------------------------------

SELECTOR_BOTON_EDITAR = 'a[title="editar"]'
SELECTOR_BOTON_CREAR_NUEVO = "text=Crear"
# ⚠️ El input real editable es "#txtRutVer_I" — "#txtRutVer_Raw" es un input
# oculto (type="hidden") que NO hay que tocar directamente (confirmado en vivo).
SELECTOR_RUT_CREAR = "#txtRutVer_I"
SELECTOR_BTN_ACEPTAR_RUT = "#btnAceptaRut"

# Botón "Guardar" del formulario. CONFIRMADO EN VIVO 05/08/2026 por inspección
# de DOM — NUNCA se hizo clic real en él durante la exploración, para no
# modificar datos reales sin autorización. Validar con cuidado la primera
# corrida (ver CLAUDE.md sección 12).
SELECTOR_BTN_GUARDAR = "#btnGuardar"

# Modo de prueba: si es True, el script llena el formulario completo pero NO
# hace clic en Guardar (ni resetea la vista por menú). Sirve para revisar
# visualmente lo que se ingresaría antes de tocar datos reales. Se activa con
# el flag --no-guardar y lo setea main().
NO_GUARDAR = False

# None | "listar" | "borrar" — limpieza de documentos de personas preexistentes.
# Lo setea main() desde --limpiar-documentos. None = no se toca nada.
LIMPIAR_DOCUMENTOS = None

# Campos de texto simples: mismo ID en "editar" y en "Crear" (gran ventaja,
# confirmado en vivo). Mapeo etiqueta -> id.
CAMPOS_TEXTO = {
    "Nombres:": "txtNombres",
    "Apellido Paterno:": "txtApellidoPaterno",
    "Apellido Materno:": "txtApellidoMaterno",
    "Sueldo Base:": "txtSueldoBase",
}

# Combobox de selección única (sin checkboxes) — fragmento estable del id,
# terminado en "_I" para el input visible (evitar "_VI", que es el valor
# oculto). Mismo fragmento en editar y crear, solo cambia el prefijo de fila.
COMBOBOX_SIMPLES = {
    "Sexo:": "cbSexo",
    "AFP:": "cbAFP",
    "Sistema de Salud:": "cbIsapre",
}

SELECTOR_FECHA_INICIO = "#calendarioFechaInicio_txtCalendar"
SELECTOR_FECHA_TERMINO = "#calendarioFechaTermino_txtCalendar"

COLUMNAS_EXCEL_REQUERIDAS = [
    "RUT", "NOMBRES", "apellidoPaterno", "apellidoMaterno", "SEXO", "AFP", "ISAPRE",
    "sueldoBase", "PROVEEDOR", "CARGO", "TIENDA", "fechaContratacion", "fechaTermino",
]


# ---------------------------------------------------------------------------
# MODELOS DE DATOS
# ---------------------------------------------------------------------------

@dataclass
class ResultadoFila:
    rut: str
    nombre_excel: str
    estado: str  # "CREADO" | "EDITADO" | "SIN_CAMBIOS" | "OMITIDO_CARGO" | "ERROR"
    detalle: str = ""
    # True si la persona YA EXISTÍA en la plataforma (RUT encontrado y editado,
    # o identidad bloqueada al "Crear"). Habilita la limpieza de documentos.
    preexistente: bool = False


# ---------------------------------------------------------------------------
# UTILIDADES ESPECÍFICAS DE FASE 2
# (normalizar_texto/quitar_prefijo_catalogo/cargar_excel viven en shift_common.py)
# ---------------------------------------------------------------------------


def formatear_fecha(valor: Optional[str]) -> str:
    """Convierte una fecha del Excel (ej. '2026-04-08 00:00:00') al formato
    dd/mm/aaaa que usa el formulario de ShiftLaboral."""
    if valor is None or str(valor).strip() == "" or str(valor).lower() == "nan":
        return ""
    fecha = pd.to_datetime(valor)
    return fecha.strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# LECTURA DE VALORES ACTUALES (para decidir qué difiere antes de editar)
# (las primitivas de lectura/escritura de campos viven en campos_formulario.py)
# ---------------------------------------------------------------------------

def leer_valores_actuales(page: Page) -> dict:
    """Lee todos los valores actuales del formulario de edición ya abierto."""
    datos = {}
    for etiqueta, campo_id in CAMPOS_TEXTO.items():
        datos[campo_id] = leer_campo_texto(page, campo_id)
    for etiqueta, fragmento in COMBOBOX_SIMPLES.items():
        datos[fragmento] = leer_combobox_simple(page, fragmento)
    datos["proveedores"] = leer_multiselect(page, "Proveedores:")
    datos["cargo"] = leer_multiselect(page, "Categoría Trabajador:")
    datos["tienda"] = leer_multiselect(page, "Tiendas:")
    try:
        datos["fecha_inicio"] = page.locator(SELECTOR_FECHA_INICIO).input_value(timeout=3000).strip()
    except Exception:
        datos["fecha_inicio"] = ""
    try:
        datos["fecha_termino"] = page.locator(SELECTOR_FECHA_TERMINO).input_value(timeout=3000).strip()
    except Exception:
        datos["fecha_termino"] = ""
    return datos


# ---------------------------------------------------------------------------
# FLUJO: EDITAR TRABAJADOR EXISTENTE
# ---------------------------------------------------------------------------

def editar_trabajador_existente(page: Page, fila: pd.Series) -> ResultadoFila:
    rut = str(fila["RUT"]).strip()
    nombre_completo = f"{fila['NOMBRES']} {fila['apellidoPaterno']}"

    page.locator(SELECTOR_BOTON_EDITAR).first.click(timeout=5000)
    page.wait_for_load_state("networkidle")
    esperar_campos_formulario_editables(page)

    # 1) Validar Cargo ANTES de tocar cualquier campo. Si no calza, se omite
    #    la fila completa (decisión de negocio confirmada, CLAUDE.md 12.4).
    cargo_deseado = fila["CARGO"]
    if not validar_cargo_existe(page, cargo_deseado):
        cerrar_formulario(page)
        return ResultadoFila(
            rut=rut, nombre_excel=nombre_completo, estado="OMITIDO_CARGO",
            detalle=f"Cargo '{cargo_deseado}' no existe en el catálogo real. Fila completa omitida.",
        )

    # 2) Leer valores actuales y calcular diffs.
    actuales = leer_valores_actuales(page)
    campos_cambiados = []

    def _tal_vez_actualizar_texto(etiqueta, campo_id, valor_excel):
        if normalizar_texto(actuales.get(campo_id)) != normalizar_texto(valor_excel):
            escribir_campo_texto(page, campo_id, str(valor_excel))
            campos_cambiados.append(etiqueta)

    _tal_vez_actualizar_texto("Nombres", "txtNombres", fila["NOMBRES"])
    _tal_vez_actualizar_texto("Apellido Paterno", "txtApellidoPaterno", fila["apellidoPaterno"])
    _tal_vez_actualizar_texto("Apellido Materno", "txtApellidoMaterno", fila["apellidoMaterno"])
    _tal_vez_actualizar_texto("Sueldo Base", "txtSueldoBase", fila["sueldoBase"])

    if normalizar_texto(actuales.get("cbSexo")) != normalizar_texto(fila["SEXO"]):
        escribir_combobox_simple(page, "cbSexo", fila["SEXO"])
        campos_cambiados.append("Sexo")
    if normalizar_texto(actuales.get("cbAFP")) != normalizar_texto(fila["AFP"]):
        escribir_combobox_simple(page, "cbAFP", fila["AFP"])
        campos_cambiados.append("AFP")
    if normalizar_texto(actuales.get("cbIsapre")) != normalizar_texto(fila["ISAPRE"]):
        escribir_combobox_simple(page, "cbIsapre", fila["ISAPRE"])
        campos_cambiados.append("Sistema de Salud")

    fecha_inicio_excel = formatear_fecha(fila["fechaContratacion"])
    fecha_termino_excel = formatear_fecha(fila["fechaTermino"])
    if actuales.get("fecha_inicio") != fecha_inicio_excel:
        escribir_campo_texto(page, "calendarioFechaInicio_txtCalendar", fecha_inicio_excel)
        campos_cambiados.append("Inicio Contrato")
    if actuales.get("fecha_termino") != fecha_termino_excel:
        escribir_campo_texto(page, "calendarioFechaTermino_txtCalendar", fecha_termino_excel)
        campos_cambiados.append("Fin Contrato")

    # NOTA: a diferencia de la vista de solo lectura (Fase 1), en el formulario
    # de editar/crear los 3 catálogos (Proveedores, Categoría Trabajador,
    # Tiendas) SÍ muestran el prefijo "LOGISTICA FALABELLA/" — confirmado en
    # vivo. Por eso aquí se pasa el valor COMPLETO del Excel (con prefijo) a
    # establecer_multiselect_valor_unico, sin recortarlo.
    proveedor_excel = quitar_prefijo_catalogo(fila["PROVEEDOR"])
    proveedores_actuales = [quitar_prefijo_catalogo(v) for v in actuales.get("proveedores", [])]
    if proveedores_actuales != [proveedor_excel]:
        if not establecer_multiselect_valor_unico(page, "Proveedores:", fila["PROVEEDOR"]):
            cerrar_formulario(page)
            return ResultadoFila(
                rut=rut, nombre_excel=nombre_completo, estado="ERROR",
                detalle=f"Proveedor '{fila['PROVEEDOR']}' no existe en el catálogo real.",
            )
        campos_cambiados.append("Proveedores")

    cargo_actual = [quitar_prefijo_catalogo(v) for v in actuales.get("cargo", [])]
    if cargo_actual != [quitar_prefijo_catalogo(cargo_deseado)]:
        establecer_multiselect_valor_unico(page, "Categoría Trabajador:", cargo_deseado)
        campos_cambiados.append("Cargo")

    tienda_excel = quitar_prefijo_catalogo(fila["TIENDA"])
    tienda_actual = [quitar_prefijo_catalogo(v) for v in actuales.get("tienda", [])]
    if tienda_actual != [tienda_excel]:
        if not establecer_multiselect_valor_unico(page, "Tiendas:", fila["TIENDA"]):
            cerrar_formulario(page)
            return ResultadoFila(
                rut=rut, nombre_excel=nombre_completo, estado="ERROR",
                detalle=f"Tienda '{fila['TIENDA']}' no existe en el catálogo real.",
            )
        campos_cambiados.append("Tiendas")

    if not campos_cambiados:
        cerrar_formulario(page)
        return ResultadoFila(rut=rut, nombre_excel=nombre_completo, estado="SIN_CAMBIOS",
                              detalle="Todos los datos ya coincidían.")

    if NO_GUARDAR:
        return ResultadoFila(
            rut=rut, nombre_excel=nombre_completo, estado="SIMULADO_EDITAR",
            detalle="Cambios preparados, NO guardado (--no-guardar): " + ", ".join(campos_cambiados),
        )

    page.locator(SELECTOR_BTN_GUARDAR).click(timeout=5000)
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)

    return ResultadoFila(rut=rut, nombre_excel=nombre_completo, estado="EDITADO",
                          detalle="Campos actualizados: " + ", ".join(campos_cambiados))


# ---------------------------------------------------------------------------
# FLUJO: CREAR TRABAJADOR NUEVO
# ---------------------------------------------------------------------------

def crear_trabajador_nuevo(page: Page, fila: pd.Series) -> ResultadoFila:
    rut = str(fila["RUT"]).strip()
    nombre_completo = f"{fila['NOMBRES']} {fila['apellidoPaterno']}"

    page.locator(SELECTOR_BOTON_CREAR_NUEVO).first.click(timeout=5000)
    page.wait_for_load_state("networkidle")
    time.sleep(0.3)

    rut_input = page.locator(SELECTOR_RUT_CREAR)
    rut_input.click()
    rut_input.fill(rut)
    rut_input.press("Tab")
    time.sleep(0.3)
    page.locator(SELECTOR_BTN_ACEPTAR_RUT).click(timeout=5000)
    page.wait_for_load_state("networkidle")

    # Tras confirmar el RUT pueden pasar 2 cosas (confirmado en vivo 07/09/2026):
    #  (a) RUT NUEVO para la plataforma -> Nombres/Apellidos vacíos y editables
    #      (una vez que termina el callback de DevExpress).
    #  (b) RUT YA REGISTRADO en ShiftLaboral (posiblemente por OTRO cliente, fuera
    #      de nuestros grupos) -> el sitio autocompleta Nombres/Apellidos/Sexo y
    #      los deja READONLY. No se pueden sobrescribir (y no se debe: es la
    #      identidad legal de la persona). Antes esto reventaba con
    #      `Locator.fill: Timeout 30000ms ... element is not editable`.
    # Se espera a que el form termine de armarse en cualquiera de los 2 estados.
    try:
        page.wait_for_function(
            """() => {
                const e = document.getElementById('txtNombres');
                if (!e) return false;
                if (!e.readOnly && !e.disabled) return true;           // (a) editable
                if (e.readOnly && e.value.trim() !== '') return true;   // (b) identidad precargada
                return false;
            }""",
            timeout=8000,
        )
    except Exception:
        pass
    time.sleep(0.3)

    ident = page.evaluate(
        """() => {
            const g = id => (document.getElementById(id) || {}).value || '';
            const e = document.getElementById('txtNombres');
            return { readonly: !!(e && e.readOnly), nombres: g('txtNombres'),
                     apPat: g('txtApellidoPaterno'), apMat: g('txtApellidoMaterno') };
        }"""
    )
    identidad_bloqueada = ident["readonly"] and ident["nombres"].strip() != ""

    if identidad_bloqueada:
        # El RUT ya existe en la maestra de personas de ShiftLaboral. Comparamos
        # la identidad que trae el sistema contra el Excel.
        difs = []
        for etiqueta, val_sis, col in (
            ("Nombres", ident["nombres"], "NOMBRES"),
            ("Apellido Paterno", ident["apPat"], "apellidoPaterno"),
            ("Apellido Materno", ident["apMat"], "apellidoMaterno"),
        ):
            if normalizar_texto(val_sis) != normalizar_texto(fila[col]):
                difs.append(f"{etiqueta} (sistema: '{val_sis}' / excel: '{fila[col]}')")
        if difs:
            cerrar_formulario(page)
            return ResultadoFila(
                rut=rut, nombre_excel=nombre_completo, estado="ERROR",
                detalle="RUT ya registrado en ShiftLaboral con identidad DISTINTA a la del "
                        "Excel; no se creó nada. Diferencias: " + "; ".join(difs),
            )
        # Identidad coincide -> se continúa SIN tocar Nombres/Apellidos/Sexo
        # (vienen readonly). El resto de campos se llenan igual que siempre.
    else:
        escribir_campo_texto(page, "txtNombres", str(fila["NOMBRES"]))
        escribir_campo_texto(page, "txtApellidoPaterno", str(fila["apellidoPaterno"]))
        escribir_campo_texto(page, "txtApellidoMaterno", str(fila["apellidoMaterno"]))
        escribir_combobox_simple(page, "cbSexo", fila["SEXO"])

    escribir_campo_texto(page, "txtSueldoBase", str(fila["sueldoBase"]))
    escribir_combobox_simple(page, "cbAFP", fila["AFP"])
    escribir_combobox_simple(page, "cbIsapre", fila["ISAPRE"])
    escribir_campo_texto(page, "calendarioFechaInicio_txtCalendar", formatear_fecha(fila["fechaContratacion"]))
    escribir_campo_texto(page, "calendarioFechaTermino_txtCalendar", formatear_fecha(fila["fechaTermino"]))

    if not establecer_multiselect_valor_unico(page, "Proveedores:", fila["PROVEEDOR"]):
        cerrar_formulario(page)
        return ResultadoFila(rut=rut, nombre_excel=nombre_completo, estado="ERROR",
                              detalle=f"Proveedor '{fila['PROVEEDOR']}' no existe en el catálogo real.")

    confirmar_proveedor_seleccionado(page)

    cargo_deseado = fila["CARGO"]
    if not validar_cargo_existe(page, cargo_deseado):
        cerrar_formulario(page)
        return ResultadoFila(rut=rut, nombre_excel=nombre_completo, estado="OMITIDO_CARGO",
                              detalle=f"Cargo '{cargo_deseado}' no existe en el catálogo real. Creación omitida.")
    establecer_multiselect_valor_unico(page, "Categoría Trabajador:", cargo_deseado)

    if not establecer_multiselect_valor_unico(page, "Tiendas:", fila["TIENDA"]):
        cerrar_formulario(page)
        return ResultadoFila(rut=rut, nombre_excel=nombre_completo, estado="ERROR",
                              detalle=f"Tienda '{fila['TIENDA']}' no existe en el catálogo real.")

    nota_identidad = (
        " (identidad ya existía en ShiftLaboral y coincide con el Excel; se asoció al grupo)"
        if identidad_bloqueada else ""
    )

    if NO_GUARDAR:
        return ResultadoFila(
            rut=rut, nombre_excel=nombre_completo, estado="SIMULADO_CREAR",
            detalle=f"Formulario de creación lleno, NO se hizo clic en Guardar (--no-guardar).{nota_identidad}",
        )

    page.locator(SELECTOR_BTN_GUARDAR).click(timeout=5000)
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)

    return ResultadoFila(rut=rut, nombre_excel=nombre_completo, estado="CREADO",
                          detalle=f"Colaborador creado con los datos del Excel.{nota_identidad}")


# ---------------------------------------------------------------------------
# REPORTE DE SALIDA
# ---------------------------------------------------------------------------

COLORES_ESTADO = {
    "CREADO": "C6EFCE",
    "EDITADO": "C6EFCE",
    "SIN_CAMBIOS": "D9E1F2",
    "OMITIDO_CARGO": "FFEB9C",
    "ERROR": "FFC7CE",
}


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Bot de creación/edición — ShiftLaboral (Fase 2)")
    parser.add_argument("--input", required=True, help="Ruta al Excel de colaboradores a crear/editar")
    parser.add_argument("--output", default="reporte_crear.xlsx", help="Ruta del Excel de salida")
    parser.add_argument("--no-guardar", action="store_true",
                        help="Llena el formulario completo pero NO hace clic en Guardar (modo prueba). "
                             "Deja el formulario abierto para revisión visual.")
    parser.add_argument("--limpiar-documentos", nargs="?", const="listar",
                        choices=["listar", "borrar"], default=None,
                        help="Solo para personas que YA EXISTÍAN: tras editar sus datos, entra a la "
                             "vista de documentos (clic en el RUT) y 'listar' (solo reporta qué "
                             "documentos son borrables) o 'borrar' (los ELIMINA, irreversible). "
                             "Sin este flag no se toca ningún documento.")
    args = parser.parse_args()

    global NO_GUARDAR, LIMPIAR_DOCUMENTOS
    NO_GUARDAR = args.no_guardar
    LIMPIAR_DOCUMENTOS = args.limpiar_documentos
    if NO_GUARDAR:
        print(">>> MODO PRUEBA (--no-guardar): se llenará el formulario pero NO se guardará nada.\n")
    if LIMPIAR_DOCUMENTOS == "listar":
        print(">>> --limpiar-documentos=listar: se LISTAN los documentos borrables de cada persona "
              "preexistente, NO se borra nada.\n")
    elif LIMPIAR_DOCUMENTOS == "borrar":
        print(">>> --limpiar-documentos=borrar: se BORRARÁN (irreversible) los documentos borrables "
              "de cada persona preexistente tras editar sus datos.\n")

    df = cargar_excel(args.input, COLUMNAS_EXCEL_REQUERIDAS)
    print(f"Cargados {len(df)} colaboradores desde {args.input}")

    playwright, browser, page = conectar_a_chrome_existente()
    asegurar_pagina_trabajadores(page)

    resultados: list[ResultadoFila] = []
    grupo_actual = None

    for i, fila in df.iterrows():
        rut = str(fila["RUT"]).strip()
        nombre_completo = f"{fila['NOMBRES']} {fila['apellidoPaterno']}"
        print(f"[{i+1}/{len(df)}] Procesando RUT {rut} ({nombre_completo})...")

        try:
            proveedor = str(fila["PROVEEDOR"]).strip()
            if proveedor != grupo_actual:
                seleccionar_grupo_proveedor(page, proveedor)
                grupo_actual = proveedor

            encontrado = buscar_rut(page, rut)

            if encontrado:
                resultado = editar_trabajador_existente(page, fila)
                resultado.preexistente = True
            else:
                resultado = crear_trabajador_nuevo(page, fila)
                if "identidad ya existía" in resultado.detalle:
                    resultado.preexistente = True

            resultados.append(resultado)
            print(f"   -> {resultado.estado}: {resultado.detalle}")

            # Limpieza de documentos: SOLO si se pidió por flag Y la persona
            # ya existía Y no hubo error al procesarla.
            if (LIMPIAR_DOCUMENTOS and resultado.preexistente
                    and resultado.estado != "ERROR"):
                try:
                    accion, docs = limpiar_documentos_trabajador(
                        page, rut, proveedor,
                        borrar=(LIMPIAR_DOCUMENTOS == "borrar"),
                    )
                    if accion == "sin_rut":
                        nota = "Docs: no se pudo abrir la vista (RUT no está en la grilla)"
                    elif accion == "listado":
                        nota = (f"Docs borrables ({len(docs)}): "
                                + (" ; ".join(docs) if docs else "ninguno"))
                    else:
                        nota = (f"Docs BORRADOS ({len(docs)}): "
                                + (" ; ".join(docs) if docs else "ninguno"))
                    resultado.detalle = (resultado.detalle + " | " + nota).strip(" |")
                    print(f"   -> {nota}")
                except Exception as e:
                    resultado.detalle += f" | Docs: ERROR en limpieza: {e}"
                    print(f"   -> Docs: ERROR en limpieza: {e}")
                finally:
                    # limpiar_documentos_trabajador deja la página en la grilla
                    # base; el proveedor hay que reseleccionarlo en la sig. fila.
                    grupo_actual = None

            if resultado.estado in ("CREADO", "EDITADO"):
                # Pedido explícito del usuario: tras un guardado exitoso,
                # resetear la vista pasando por el menú antes de seguir, para
                # no arrastrar ningún estado residual del guardado anterior.
                navegar_a_trabajadores_por_menu(page)
                grupo_actual = None  # se perdió al navegar, hay que reseleccionarlo
            elif resultado.estado.startswith("SIMULADO"):
                # Modo prueba (--no-guardar). Si es la ÚLTIMA fila, se deja el
                # formulario abierto para poder revisarlo en pantalla; si hay
                # más filas, se descarta con un reload duro para que la
                # siguiente arranque de cero (dejarlo abierto, o resetear por
                # menú tras un form sin guardar, rompía la fila siguiente).
                if i < len(df) - 1:
                    cerrar_formulario(page)
                    asegurar_pagina_trabajadores(page)
                    page.goto(page.url)
                    page.wait_for_load_state("networkidle")
                    grupo_actual = None
            else:
                limpiar_filtro(page)

        except Exception as e:
            resultados.append(ResultadoFila(rut=rut, nombre_excel=nombre_completo,
                                             estado="ERROR",
                                             detalle=f"Error inesperado durante el procesamiento: {e}"))
            print(f"   -> ERROR: {e}")
            try:
                cerrar_formulario(page)
                asegurar_pagina_trabajadores(page)
            except Exception:
                pass

    escribir_reporte(resultados, args.output, COLORES_ESTADO)

    total = len(resultados)
    creados = sum(1 for r in resultados if r.estado == "CREADO")
    editados = sum(1 for r in resultados if r.estado == "EDITADO")
    simulados = sum(1 for r in resultados if r.estado.startswith("SIMULADO"))
    sin_cambios = sum(1 for r in resultados if r.estado == "SIN_CAMBIOS")
    omitidos = sum(1 for r in resultados if r.estado == "OMITIDO_CARGO")
    errores = sum(1 for r in resultados if r.estado == "ERROR")
    print(f"\nResumen: {total} procesados | Creados: {creados} | Editados: {editados} | "
          f"Simulados (--no-guardar): {simulados} | "
          f"Sin cambios: {sin_cambios} | Omitidos (Cargo): {omitidos} | Error: {errores}")

    # En modo prueba dejamos el navegador y el formulario intactos para revisión.
    if not NO_GUARDAR:
        browser.close()
    playwright.stop()


if __name__ == "__main__":
    main()
