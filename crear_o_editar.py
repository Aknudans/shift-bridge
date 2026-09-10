import argparse
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

import pandas as pd
from playwright.sync_api import Page

# La consola de Windows no sabe mostrar algunos símbolos que traen los
# mensajes de error. Sin esto, imprimir un error mataba el programa entero en
# vez de anotar la fila y seguir con la siguiente.
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
    cerrar_popup_operacion_exitosa,
    confirmar_proveedor_seleccionado,
    esperar_campos_formulario_editables,
    escribir_campo_texto,
    escribir_combobox_simple,
    establecer_multiselect_valor_unico,
    leer_campo_texto,
    leer_combobox_simple,
    leer_multiselect,
    validar_cargo_existe,
    verificar_guardado_exitoso,
)
from documentos import (
    _norm as _norm_texto,
    DOCUMENTOS_SET_ESTANDAR,
    limpiar_documentos_trabajador,
    preparar_items_carpeta,
    subir_documentos_trabajador,
    tipos_documentos_existentes,
)

# Selectores de esta fase, la que crea y edita gente.

SELECTOR_BOTON_EDITAR = 'a[title="editar"]'
SELECTOR_BOTON_CREAR_NUEVO = "text=Crear"
# La caja de RUT que se ve en pantalla. Hay otra parecida escondida detrás que
# no hay que tocar.
SELECTOR_RUT_CREAR = "#txtRutVer_I"
SELECTOR_BTN_ACEPTAR_RUT = "#btnAceptaRut"

SELECTOR_BTN_GUARDAR = "#btnGuardar"

# Opciones que se prenden desde la línea de comandos y valen para toda la
# corrida: llenar sin guardar, borrar documentos viejos, subir los nuevos y
# revisar cuáles ya tiene cada persona.
NO_GUARDAR = False
LIMPIAR_DOCUMENTOS = None
SUBIR_DOCUMENTOS = None
VERIFICAR_DOCUMENTOS = False


# Busca la carpeta de documentos que le corresponde a una persona. Compara por
# palabras sueltas, sin importar el orden ni las tildes, así "Adan_Leon" calza
# con "ADAN IGNACIO LEON BRAVO". Si no encuentra ninguna, o si hay dos que
# calzan igual de bien, no adivina: avisa por qué no pudo.
def _buscar_carpeta_persona(base: str, nombre: str, ap_pat: str, ap_mat: str):
    tokens_persona = set(_norm_texto(f"{nombre} {ap_pat} {ap_mat}").split())
    try:
        subcarpetas = [d for d in os.listdir(base)
                       if os.path.isdir(os.path.join(base, d))]
    except Exception as e:
        return None, f"no se pudo leer '{base}': {e}"

    candidatas = []
    for d in subcarpetas:
        toks = set(_norm_texto(d).split())
        if len(toks) >= 2 and toks.issubset(tokens_persona):
            candidatas.append((len(toks), d))
    if not candidatas:
        return None, "sin carpeta de documentos que calce con el nombre"
    candidatas.sort(reverse=True)
    if len(candidatas) > 1 and candidatas[0][0] == candidatas[1][0]:
        empatadas = [d for n, d in candidatas if n == candidatas[0][0]]
        return None, f"carpeta ambigua: {empatadas}"
    return os.path.join(base, candidatas[0][1]), ""

# Las cajas de texto del formulario. Por suerte se llaman igual al crear que
# al editar, así que el mismo código sirve para los dos casos.
CAMPOS_TEXTO = {
    "Nombres:": "txtNombres",
    "Apellido Paterno:": "txtApellidoPaterno",
    "Apellido Materno:": "txtApellidoMaterno",
    "Sueldo Base:": "txtSueldoBase",
}

# Las listas de un solo valor. Su nombre completo cambia según la fila, así
# que se guarda solo el pedazo que se mantiene.
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


# Lo que se anota de cada persona para el reporte. "preexistente" marca a los
# que ya estaban en la plataforma: son los únicos a los que se les limpian los
# documentos viejos.
@dataclass
class ResultadoFila:
    rut: str
    nombre_excel: str
    estado: str
    detalle: str = ""
    preexistente: bool = False


# Las fechas vienen del Excel en un formato y el sitio las pide en otro.
def formatear_fecha(valor: Optional[str]) -> str:
    if valor is None or str(valor).strip() == "" or str(valor).lower() == "nan":
        return ""
    fecha = pd.to_datetime(valor)
    return fecha.strftime("%d/%m/%Y")


# Una celda del Excel que en la práctica está sin llenar.
def _vacio(valor) -> bool:
    if valor is None:
        return True
    if isinstance(valor, float) and pd.isna(valor):
        return True
    return str(valor).strip().lower() in ("", "nan", "nat")


# Rellena lo que la planilla suele traer en blanco: si no viene la fecha de
# término, se toma la de inicio más 89 días, que es como se calcula siempre; y
# si no viene el sueldo, va cero. Se deja marcada la fila para que el reporte
# avise que ese dato lo puso el bot y no la planilla.
def autocompletar_campos_negocio(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["_fecha_termino_autocompletada"] = False
    df["_sueldo_autocompletado"] = False

    for idx, fila in df.iterrows():
        if _vacio(fila.get("fechaTermino")) and not _vacio(fila.get("fechaContratacion")):
            inicio = pd.to_datetime(fila["fechaContratacion"])
            df.at[idx, "fechaTermino"] = str(inicio + pd.Timedelta(days=89))
            df.at[idx, "_fecha_termino_autocompletada"] = True
        if _vacio(fila.get("sueldoBase")):
            df.at[idx, "sueldoBase"] = "0"
            df.at[idx, "_sueldo_autocompletado"] = True

    return df


# Agrega al reporte la aclaración de qué datos se completaron solos.
def _con_nota_autocompletado(resultado: ResultadoFila, fila: pd.Series) -> ResultadoFila:
    notas = []
    if bool(fila.get("_fecha_termino_autocompletada")):
        notas.append("Fin Contrato autocompletado a "
                      f"{formatear_fecha(fila['fechaTermino'])} (Inicio + 89 días; venía vacío en el Excel)")
    if bool(fila.get("_sueldo_autocompletado")):
        notas.append("Sueldo Base autocompletado a 0 (venía vacío en el Excel)")
    if notas:
        resultado.detalle = (resultado.detalle + " | " + "; ".join(notas)).strip(" |")
    return resultado


# Saca una foto de cómo está hoy el formulario, para después comparar contra
# el Excel y tocar solamente lo que de verdad cambió.
def leer_valores_actuales(page: Page) -> dict:
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


# Corrige a alguien que ya está en el sistema. Primero revisa el cargo: si no
# existe tal cual en el sitio, se deja a esa persona intacta y se pasa a la
# siguiente. Después compara campo por campo y solo escribe donde hay
# diferencia, para no pisar datos que ya estaban bien.
def editar_trabajador_existente(page: Page, fila: pd.Series) -> ResultadoFila:
    rut = str(fila["RUT"]).strip()
    nombre_completo = f"{fila['NOMBRES']} {fila['apellidoPaterno']}"

    page.locator(SELECTOR_BOTON_EDITAR).first.click(timeout=5000)
    page.wait_for_load_state("networkidle")
    esperar_campos_formulario_editables(page)

    # El cargo se revisa antes que nada, para no dejar a alguien a medio editar.
    cargo_deseado = fila["CARGO"]
    if not validar_cargo_existe(page, cargo_deseado):
        cerrar_formulario(page)
        return ResultadoFila(
            rut=rut, nombre_excel=nombre_completo, estado="OMITIDO_CARGO",
            detalle=f"Cargo '{cargo_deseado}' no existe en el catálogo real. Fila completa omitida.",
        )

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

    # Acá el sitio sí muestra el prefijo del catálogo en proveedor, cargo y
    # tienda (en la ficha de solo lectura no), así que se le pasa el valor
    # completo del Excel tal como viene, sin recortarle nada.
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
        return _con_nota_autocompletado(ResultadoFila(
            rut=rut, nombre_excel=nombre_completo, estado="SIN_CAMBIOS",
            detalle="Todos los datos ya coincidían.",
        ), fila)

    if NO_GUARDAR:
        return _con_nota_autocompletado(ResultadoFila(
            rut=rut, nombre_excel=nombre_completo, estado="SIMULADO_EDITAR",
            detalle="Cambios preparados, NO guardado (--no-guardar): " + ", ".join(campos_cambiados),
        ), fila)

    page.locator(SELECTOR_BTN_GUARDAR).click(timeout=5000)
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)

    # Cerrar el aviso de éxito y recién ahí confirmar que se guardó de verdad.
    cerrar_popup_operacion_exitosa(page)

    guardado_ok, motivo_error = verificar_guardado_exitoso(page)
    if not guardado_ok:
        cerrar_formulario(page)
        return ResultadoFila(
            rut=rut, nombre_excel=nombre_completo, estado="ERROR",
            detalle=f"No se pudo confirmar la edición: {motivo_error}",
        )

    return _con_nota_autocompletado(ResultadoFila(
        rut=rut, nombre_excel=nombre_completo, estado="EDITADO",
        detalle="Campos actualizados: " + ", ".join(campos_cambiados),
    ), fila)


# Da de alta a alguien que no estaba en el grupo. Primero se escribe el RUT y
# se confirma; de ahí en adelante aparece el resto del formulario.
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

    # Al confirmar el RUT pueden pasar dos cosas: que sea alguien nuevo del
    # todo, y entonces el nombre viene vacío y se puede escribir; o que la
    # plataforma ya lo conozca de otro cliente, y ahí ella misma completa
    # nombre y apellidos y los deja bloqueados, porque la identidad de una
    # persona no se cambia, solo se la suma al grupo. Se espera a que el
    # formulario termine de armarse en cualquiera de los dos casos.
    try:
        page.wait_for_function(
            """() => {
                const e = document.getElementById('txtNombres');
                if (!e) return false;
                if (!e.readOnly && !e.disabled) return true;           // persona nueva
                if (e.readOnly && e.value.trim() !== '') return true;   // ya la conocían
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
        # Si la plataforma ya tenía a esta persona, se contrasta lo que ella
        # dice contra lo que dice el Excel antes de seguir.
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
        # Si coincide, se sigue sin tocar nombre, apellidos ni sexo; el resto
        # del formulario se llena igual que siempre.
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
        return _con_nota_autocompletado(ResultadoFila(
            rut=rut, nombre_excel=nombre_completo, estado="SIMULADO_CREAR",
            detalle=f"Formulario de creación lleno, NO se hizo clic en Guardar (--no-guardar).{nota_identidad}",
        ), fila)

    page.locator(SELECTOR_BTN_GUARDAR).click(timeout=5000)
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)

    # El aviso de "Operación Exitosa" se cierra antes de cualquier otra cosa:
    # mientras esté abierto, todo lo que venga después se queda esperando.
    cerrar_popup_operacion_exitosa(page)

    # Que no haya reventado nada no significa que se haya guardado, así que se
    # comprueba en serio.
    guardado_ok, motivo_error = verificar_guardado_exitoso(page)
    if not guardado_ok:
        cerrar_formulario(page)
        return ResultadoFila(
            rut=rut, nombre_excel=nombre_completo, estado="ERROR",
            detalle=f"No se pudo confirmar la creación: {motivo_error}",
        )

    # Y como prueba final, se vuelve a buscar el RUT en la lista para ver que
    # la persona quedó realmente ahí.
    try:
        limpiar_filtro(page)
    except Exception:
        pass
    try:
        creado_en_grilla = buscar_rut(page, rut)
    except Exception:
        creado_en_grilla = False
    if not creado_en_grilla:
        return ResultadoFila(
            rut=rut, nombre_excel=nombre_completo, estado="ERROR",
            detalle="Se guardó sin errores de validación, pero el RUT no aparece en la grilla "
                    "al re-buscarlo: no se pudo confirmar la creación.",
        )

    return _con_nota_autocompletado(ResultadoFila(
        rut=rut, nombre_excel=nombre_completo, estado="CREADO",
        detalle=f"Colaborador creado con los datos del Excel.{nota_identidad}",
    ), fila)


# Color de fondo de cada fila del reporte según cómo terminó.
COLORES_ESTADO = {
    "CREADO": "C6EFCE",
    "EDITADO": "C6EFCE",
    "SIN_CAMBIOS": "D9E1F2",
    "OMITIDO_CARGO": "FFEB9C",
    "ERROR": "FFC7CE",
}


# Recorre el Excel persona por persona: elige el grupo, busca el RUT y según
# esté o no, la edita o la crea. Después, si se pidió, le limpia los
# documentos viejos y le sube los nuevos. Si alguien falla queda anotado el
# error y se sigue con el que viene; al final se escribe el reporte.
# Los argumentos se pueden pasar a mano, que es como los llama la app
# empaquetada.
def main(argv=None):
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
    parser.add_argument("--subir-documentos", metavar="CARPETA", default=None,
                        help="Carpeta con una subcarpeta por persona (nombre = nombre del "
                             "colaborador) y adentro los archivos (nombre del archivo = tipo del "
                             "catálogo). Tras crear/editar a cada persona sube esos documentos por "
                             "carga masiva. Período = fechaContratacion del Excel. Con --no-guardar "
                             "llena el formulario pero hace Cancelar. NUNCA re-sube un tipo de "
                             "documento que la persona ya tenga cargado (ver tipos_documentos_"
                             "existentes en documentos.py).")
    parser.add_argument("--verificar-documentos", action="store_true",
                        help="De solo lectura: lista los tipos de documento que CADA persona YA "
                             "tiene cargados (proveedor o mandante), sin subir ni borrar nada. "
                             "Pensado como paso previo de chequeo antes de --subir-documentos "
                             "(que de todas formas ya evita duplicar un tipo existente por su "
                             "cuenta). Se puede usar solo o junto con --subir-documentos.")
    args = parser.parse_args(argv)

    global NO_GUARDAR, LIMPIAR_DOCUMENTOS, SUBIR_DOCUMENTOS, VERIFICAR_DOCUMENTOS
    NO_GUARDAR = args.no_guardar
    LIMPIAR_DOCUMENTOS = args.limpiar_documentos
    SUBIR_DOCUMENTOS = args.subir_documentos
    VERIFICAR_DOCUMENTOS = args.verificar_documentos
    if NO_GUARDAR:
        print(">>> MODO PRUEBA (--no-guardar): se llenará el formulario pero NO se guardará nada.\n")
    if LIMPIAR_DOCUMENTOS == "listar":
        print(">>> --limpiar-documentos=listar: se LISTAN los documentos borrables de cada persona "
              "preexistente, NO se borra nada.\n")
    elif LIMPIAR_DOCUMENTOS == "borrar":
        print(">>> --limpiar-documentos=borrar: se BORRARÁN (irreversible) los documentos borrables "
              "de cada persona preexistente tras editar sus datos.\n")
    if SUBIR_DOCUMENTOS:
        if not os.path.isdir(SUBIR_DOCUMENTOS):
            print(f"ERROR: la carpeta de documentos '{SUBIR_DOCUMENTOS}' no existe.")
            sys.exit(1)
        modo = "se subirán" if not NO_GUARDAR else "se llenará el form (Cancelar, sin subir)"
        print(f">>> --subir-documentos: {modo} los documentos de '{SUBIR_DOCUMENTOS}'.\n")

    df = cargar_excel(args.input, COLUMNAS_EXCEL_REQUERIDAS)
    df = autocompletar_campos_negocio(df)
    print(f"Cargados {len(df)} colaboradores desde {args.input}")

    playwright, browser, page = conectar_a_chrome_existente()
    asegurar_pagina_trabajadores(page)

    resultados: list[ResultadoFila] = []
    grupo_actual = None
    docs_incompletos = 0  # gente a la que le faltó algún documento del set

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

            # Borrar los documentos viejos: solo si se pidió, solo a quien ya
            # existía y solo si no hubo problemas al procesarla.
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
                    # Esto deja la página en la lista base, así que el grupo
                    # hay que volver a elegirlo en la persona siguiente.
                    grupo_actual = None

            # Repasar qué documentos tiene ya cada persona, sin tocar nada.
            if VERIFICAR_DOCUMENTOS and resultado.estado != "ERROR":
                try:
                    accion_v, tipos_v = tipos_documentos_existentes(page, rut, proveedor)
                    if accion_v == "sin_rut":
                        nota_v = "Docs actuales: no se pudo abrir la vista (RUT no está en la grilla)"
                    else:
                        nota_v = (f"Docs actuales ({len(tipos_v)}): "
                                  + (", ".join(tipos_v) if tipos_v else "ninguno"))
                    resultado.detalle = (resultado.detalle + " | " + nota_v).strip(" |")
                    print(f"   -> {nota_v}")
                except Exception as e:
                    resultado.detalle += f" | Docs verificar: ERROR: {e}"
                    print(f"   -> Docs verificar: ERROR: {e}")
                finally:
                    grupo_actual = None

            # Subir los documentos nuevos, si se pidió y la persona quedó bien
            # en el sistema. Los estados simulados también entran acá: son los
            # de la corrida de prueba, y si no, en modo prueba nunca se
            # alcanzaba a probar esta parte.
            if (SUBIR_DOCUMENTOS
                    and resultado.estado in (
                        "CREADO", "EDITADO", "SIN_CAMBIOS",
                        "SIMULADO_CREAR", "SIMULADO_EDITAR",
                    )):
                try:
                    carpeta, motivo = _buscar_carpeta_persona(
                        SUBIR_DOCUMENTOS, fila["NOMBRES"],
                        fila["apellidoPaterno"], fila["apellidoMaterno"])
                    if not carpeta:
                        nota = f"⚠ FALTAN TODOS los documentos: {motivo}"
                        docs_incompletos += 1
                    else:
                        items, omitidos = preparar_items_carpeta(carpeta)
                        if not items:
                            nota = ("⚠ FALTAN TODOS los documentos: la carpeta no tiene archivos válidos"
                                    + (f" | omitidos: {omitidos}" if omitidos else ""))
                            docs_incompletos += 1
                        else:
                            periodo = formatear_fecha(fila["fechaContratacion"])
                            vencimiento = formatear_fecha(fila["fechaTermino"])
                            accion, subidos, ya_existian, errs = subir_documentos_trabajador(
                                page, rut, proveedor, items, periodo,
                                vencimiento_ddmmaaaa=vencimiento,
                                guardar=(not NO_GUARDAR))
                            verbo = {"subido": "Docs SUBIDOS",
                                     "subido_con_periodo": "Docs SUBIDOS (hubo que completar Período)",
                                     "sin_items_nuevos": "Docs: nada nuevo que subir",
                                     "rechazado": "Docs subir RECHAZADO por el sitio",
                                     "simulado": "Docs (simulado)",
                                     "sin_rut": "Docs subir: RUT no está en la grilla",
                                     "sin_items": "Docs subir: sin items"}.get(accion, accion)
                            nota = f"{verbo} ({len(subidos)}): " + (", ".join(subidos) or "ninguno")
                            if ya_existian:
                                nota += f" | ya tenía, no se re-subió ({len(ya_existian)}): " + ", ".join(ya_existian)
                            if omitidos:
                                nota += f" | omitidos: {'; '.join(omitidos)}"
                            if errs:
                                nota += f" | errores: {'; '.join(errs)}"

                            # Si falta alguno de los documentos habituales no
                            # se frena nada, solo queda la advertencia en el
                            # reporte. Lo que la persona ya tenía cargado
                            # cuenta como presente aunque no venga en la
                            # carpeta de esta vez.
                            presentes_norm = {normalizar_texto(t) for t in (subidos + ya_existian)}
                            faltantes = [t for t in DOCUMENTOS_SET_ESTANDAR
                                         if normalizar_texto(t) not in presentes_norm]
                            if faltantes:
                                nota += (f" | ⚠ FALTAN documentos del set estándar ({len(faltantes)}): "
                                         + ", ".join(faltantes))
                                docs_incompletos += 1
                    resultado.detalle = (resultado.detalle + " | " + nota).strip(" |")
                    print(f"   -> {nota}")
                except Exception as e:
                    resultado.detalle += f" | Docs subir: ERROR: {e}"
                    print(f"   -> Docs subir: ERROR: {e}")
                finally:
                    grupo_actual = None

            if resultado.estado in ("CREADO", "EDITADO"):
                # Después de guardar se vuelve a entrar por el menú, así el
                # sitio queda limpio y no arrastra nada a la persona siguiente.
                navegar_a_trabajadores_por_menu(page)
                grupo_actual = None  # al navegar se pierde, hay que reelegirlo
            elif resultado.estado.startswith("SIMULADO"):
                # En modo prueba: al último se deja el formulario abierto para
                # poder mirarlo, y si quedan más personas se recarga la página
                # para que la siguiente empiece de cero.
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
    if SUBIR_DOCUMENTOS and docs_incompletos:
        print(f"⚠ {docs_incompletos} persona(s) con documentos faltantes del set estándar "
              f"— revisar el detalle de cada fila en {args.output}.")

    # En modo prueba se deja el navegador abierto para poder revisar.
    if not NO_GUARDAR:
        browser.close()
    playwright.stop()


if __name__ == "__main__":
    main()
