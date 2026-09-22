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
    GRUPOS_PROVEEDOR_CONOCIDOS,
    navegar_a_trabajadores_por_menu,
    normalizar_rut,
    normalizar_texto,
    problema_rut,
    quitar_prefijo_catalogo,
    RutAmbiguoEnGrilla,
    seleccionar_grupo_proveedor,
)
from campos_formulario import (
    CampoNoCompletado,
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
    gestionar_documentos_trabajador,
    preparar_items_carpeta,
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


# Reparte las carpetas entre todas las personas del lote de una vez, antes de
# tocar el sitio. Buscar persona por persona no alcanzaba: una carpeta
# "Juan_Soto" le calza tanto a "Juan Carlos Soto Pérez" como a "Juan Soto
# Rojas", y si el segundo no tenía carpeta propia recibía los documentos del
# primero sin ningún aviso. Si una carpeta le calza a más de una persona, no
# se le sube a ninguna: subirle la cédula de alguien a la ficha de otro es peor
# que no subir nada.
# Devuelve, en el mismo orden de `personas` (tuplas nombre, apellido paterno,
# apellido materno), la carpeta de cada una (o None y el motivo), y aparte las
# carpetas que no le calzaron a nadie de la planilla.
def asignar_carpetas_lote(base: str, personas):
    asignacion = [_buscar_carpeta_persona(base, n, ap, am) for n, ap, am in personas]

    duenos: dict[str, list[int]] = {}
    for i, (ruta, _) in enumerate(asignacion):
        if ruta:
            duenos.setdefault(ruta, []).append(i)

    for ruta, indices in duenos.items():
        if len(indices) > 1:
            nombres = "; ".join(" ".join(str(x) for x in personas[j]) for j in indices)
            motivo = (f"la carpeta '{os.path.basename(ruta)}' calza con más de una persona "
                      f"de la planilla ({nombres}); no se subió nada para no mezclar "
                      f"documentos. Renombrar la carpeta con el nombre más completo")
            for j in indices:
                asignacion[j] = (None, motivo)

    try:
        subcarpetas = sorted(d for d in os.listdir(base)
                             if os.path.isdir(os.path.join(base, d)))
    except Exception:
        subcarpetas = []
    sin_dueno = [d for d in subcarpetas if os.path.join(base, d) not in duenos]
    return asignacion, sin_dueno

# Catálogos conocidos de AFP y Sistema de Salud (ver CLAUDE.md, sección 7).
# Solo se usan para avisar en el chequeo previo; el valor que manda es el del
# sitio, así que un valor fuera de esta lista es una advertencia, no un bloqueo.
CATALOGO_AFP = ["Provida", "Habitat", "Cuprum", "Capital", "Modelo", "Planvital",
                "Jubilado", "Uno", "Sin Información"]
CATALOGO_SALUD = ["Cruz Blanca", "Banmédica", "Consalud", "Ferrosalud", "Vida Tres",
                  "Fonasa", "Sin Información"]

# Columnas que el sitio necesita sí o sí para crear o editar a alguien.
COLUMNAS_OBLIGATORIAS_CHEQUEO = [
    ("SEXO", "Sexo"), ("AFP", "AFP"), ("ISAPRE", "Sistema de Salud"),
    ("CARGO", "Cargo"), ("PROVEEDOR", "Proveedor"), ("TIENDA", "Tienda"),
    ("fechaContratacion", "Inicio Contrato"),
]


# Nombre de carpeta que calzaría con la persona: primer nombre + apellido
# paterno, sin tildes y con "_" entre palabras ("Debora_San_Martin").
def _carpeta_sugerida(nombre, ap_pat) -> str:
    primero = "" if _vacio(nombre) else (str(nombre).split() or [""])[0]
    partes = [primero] + ([] if _vacio(ap_pat) else str(ap_pat).split())
    return "_".join(_norm_texto(p).capitalize() for p in partes if p)


# Revisa el Excel antes de abrir Chrome: RUT mal escrito (formato, dígito
# verificador) o repetido, Sexo o Proveedor que no se reconocen, celdas
# obligatorias vacías y AFP o Sistema de Salud fuera del catálogo conocido.
# Estas últimas son las causas de los errores "Timeout ... text=nan" /
# "text=Sin AFP" de corridas anteriores.
# Devuelve una lista (rut, nombre, [problemas]) solo con las filas con algo.
def chequear_datos_excel(df: pd.DataFrame) -> list:
    afp_ok = {normalizar_texto(v) for v in CATALOGO_AFP}
    salud_ok = {normalizar_texto(v) for v in CATALOGO_SALUD}
    grupos_ok = {normalizar_texto(g) for g in GRUPOS_PROVEEDOR_CONOCIDOS}

    # Filas del Excel (numeradas como en Excel: la 1 es el encabezado) en que
    # aparece cada RUT, para avisar si alguien viene repetido.
    filas_por_rut: dict[str, list[int]] = {}
    for n, (_, f) in enumerate(df.iterrows(), start=2):
        clave = normalizar_rut(f["RUT"])
        if clave:
            filas_por_rut.setdefault(clave, []).append(n)

    hallazgos = []
    for _, f in df.iterrows():
        problemas = []
        motivo_rut = problema_rut(f["RUT"])
        if motivo_rut:
            problemas.append(motivo_rut)
        filas = filas_por_rut.get(normalizar_rut(f["RUT"]), [])
        if len(filas) > 1:
            problemas.append("RUT repetido en las filas "
                             + ", ".join(str(x) for x in filas)
                             + " del Excel: se procesaría más de una vez")
        if not _vacio(f.get("SEXO")) and f["SEXO"] not in ("Masculino", "Femenino"):
            problemas.append(f"Sexo '{f['SEXO']}' no reconocido (usar M, F, Masculino o Femenino)")
        if not _vacio(f.get("PROVEEDOR")):
            grupo = normalizar_texto(str(f["PROVEEDOR"]).split("/")[-1])
            if grupo not in grupos_ok:
                problemas.append(f"Proveedor '{f['PROVEEDOR']}' no es uno de los grupos "
                                 f"conocidos ({'; '.join(GRUPOS_PROVEEDOR_CONOCIDOS)})")
        for col, etiqueta in COLUMNAS_OBLIGATORIAS_CHEQUEO:
            if col in f and _vacio(f[col]):
                problemas.append(f"'{etiqueta}' vacío")
        if not _vacio(f.get("AFP")) and normalizar_texto(f["AFP"]) not in afp_ok:
            problemas.append(f"AFP '{f['AFP']}' no está en el catálogo "
                             f"({', '.join(CATALOGO_AFP)})")
        if not _vacio(f.get("ISAPRE")) and normalizar_texto(f["ISAPRE"]) not in salud_ok:
            problemas.append(f"Sistema de Salud '{f['ISAPRE']}' no está en el catálogo "
                             f"({', '.join(CATALOGO_SALUD)})")
        if problemas:
            hallazgos.append((str(f["RUT"]).strip(),
                              f"{f['NOMBRES']} {f['apellidoPaterno']}", problemas))
    return hallazgos


# Cruza la planilla con la carpeta de documentos sin abrir el sitio: a quién
# le toca cada subcarpeta, qué archivos se reconocen y cuáles no, qué quedó
# dentro de subcarpetas (no se leen) y qué falta del set estándar.
# Devuelve (por_persona, carpetas_sin_dueno, asignacion); `asignacion` es la
# misma de asignar_carpetas_lote, para reutilizarla en la corrida.
def chequear_carpeta_documentos(df: pd.DataFrame, base: str):
    personas = [(f["NOMBRES"], f["apellidoPaterno"], f["apellidoMaterno"])
                for _, f in df.iterrows()]
    asignacion, sin_dueno = asignar_carpetas_lote(base, personas)

    por_persona = []
    for (_, f), (carpeta, motivo) in zip(df.iterrows(), asignacion):
        info = {
            "rut": str(f["RUT"]).strip(),
            "nombre": f"{f['NOMBRES']} {f['apellidoPaterno']}",
            "carpeta": os.path.basename(carpeta) if carpeta else None,
            "motivo": motivo,
            "sugerida": _carpeta_sugerida(f["NOMBRES"], f["apellidoPaterno"]),
            "reconocidos": [], "omitidos": [], "en_subcarpetas": [],
            "repetidos": [], "faltan": [],
        }
        if carpeta:
            items, omitidos = preparar_items_carpeta(carpeta)
            info["reconocidos"] = [(os.path.basename(it["ruta"]), it["tipo"]) for it in items]
            info["omitidos"] = omitidos
            for raiz, _dirs, archivos in os.walk(carpeta):
                if raiz != carpeta:
                    rel = os.path.relpath(raiz, carpeta)
                    info["en_subcarpetas"] += [os.path.join(rel, a) for a in archivos]
            tipos = [it["tipo"] for it in items]
            info["repetidos"] = sorted({t for t in tipos if tipos.count(t) > 1})
            info["faltan"] = [t for t in DOCUMENTOS_SET_ESTANDAR if t not in tipos]
        por_persona.append(info)
    return por_persona, sin_dueno, asignacion


# Muestra el resultado del chequeo previo por consola (la interfaz lo ve en el
# log). Devuelve cuántas personas tienen algún problema.
def imprimir_chequeo_previo(datos: list, carpeta: Optional[tuple], base: Optional[str]) -> int:
    print("=" * 70)
    print("CHEQUEO PREVIO (no se abre el sitio ni se modifica nada)")
    print("=" * 70)

    print(f"\n-- Datos del Excel: {len(datos)} fila(s) con problemas --")
    for rut, nombre, problemas in datos:
        print(f"  ✗ {rut} {nombre}: " + "; ".join(problemas))
    if not datos:
        print("  ✓ Sin problemas en los campos obligatorios.")

    con_problemas = {rut for rut, _, _ in datos}
    if carpeta is not None:
        por_persona, sin_dueno, _ = carpeta
        sin_carpeta = [p for p in por_persona if not p["carpeta"]]
        con_carpeta = [p for p in por_persona if p["carpeta"]]

        print(f"\n-- Carpeta de documentos: {base} --")
        print(f"  Personas con carpeta: {len(con_carpeta)} de {len(por_persona)}")

        if sin_carpeta:
            print(f"\n  ✗ Sin carpeta ({len(sin_carpeta)}):")
            for p in sin_carpeta:
                print(f"    - {p['rut']} {p['nombre']}: {p['motivo']}. "
                      f"Nombre sugerido: '{p['sugerida']}'")
                con_problemas.add(p["rut"])

        if sin_dueno:
            print(f"\n  ⚠ Carpetas que no calzan con nadie ({len(sin_dueno)}), revisar "
                  f"tipeos o palabras de más (RUT, 'docs', '(1)'): {', '.join(sin_dueno)}")

        for p in con_carpeta:
            avisos = []
            if p["omitidos"]:
                avisos.append("no reconocidos: " + "; ".join(p["omitidos"]))
            if p["en_subcarpetas"]:
                avisos.append(f"en subcarpetas, NO se leen ({len(p['en_subcarpetas'])}): "
                              + ", ".join(p["en_subcarpetas"][:5])
                              + (" …" if len(p["en_subcarpetas"]) > 5 else ""))
            if p["repetidos"]:
                avisos.append("tipo repetido (se suben todos): " + ", ".join(p["repetidos"]))
            if p["faltan"]:
                avisos.append(f"faltan del set estándar ({len(p['faltan'])}; "
                              "puede que ya estén cargados en el sitio): "
                              + ", ".join(p["faltan"]))
            marca = "⚠" if avisos else "✓"
            print(f"\n  {marca} {p['rut']} {p['nombre']} -> carpeta '{p['carpeta']}': "
                  f"{len(p['reconocidos'])} archivo(s) reconocido(s)")
            for archivo, tipo in p["reconocidos"]:
                print(f"      · {archivo} -> {tipo}")
            for a in avisos:
                print(f"      ⚠ {a}")
            if p["omitidos"] or p["en_subcarpetas"]:
                con_problemas.add(p["rut"])

    print(f"\nResumen chequeo: {len(con_problemas)} persona(s) con algo que revisar.")
    print("=" * 70 + "\n")
    return len(con_problemas)


# Lo mismo que imprime el chequeo previo, pero como filas para un Excel: una
# por problema. ERROR es lo que cuenta como "persona con algo que revisar"
# (lo mismo que suma imprimir_chequeo_previo); ADVERTENCIA es informativo.
def filas_reporte_chequeo(datos: list, carpeta: Optional[tuple]) -> list:
    filas = [ResultadoFila(rut, nombre, "ERROR", "Datos del Excel: " + "; ".join(problemas))
             for rut, nombre, problemas in datos]
    if carpeta is None:
        return filas
    por_persona, sin_dueno, _ = carpeta
    for p in por_persona:
        if not p["carpeta"]:
            filas.append(ResultadoFila(
                p["rut"], p["nombre"], "ERROR",
                f"Sin carpeta de documentos: {p['motivo']}. Nombre sugerido: '{p['sugerida']}'"))
            continue
        if p["omitidos"]:
            filas.append(ResultadoFila(p["rut"], p["nombre"], "ERROR",
                                       "Archivos no reconocidos: " + "; ".join(p["omitidos"])))
        if p["en_subcarpetas"]:
            filas.append(ResultadoFila(p["rut"], p["nombre"], "ERROR",
                                       "Archivos en subcarpetas (no se leen): "
                                       + ", ".join(p["en_subcarpetas"])))
        if p["repetidos"]:
            filas.append(ResultadoFila(p["rut"], p["nombre"], "ADVERTENCIA",
                                       "Tipo repetido (se suben todos): " + ", ".join(p["repetidos"])))
        if p["faltan"]:
            filas.append(ResultadoFila(p["rut"], p["nombre"], "ADVERTENCIA",
                                       "Faltan del set estándar (puede que ya estén cargados "
                                       "en el sitio): " + ", ".join(p["faltan"])))
    for d in sin_dueno:
        filas.append(ResultadoFila("", f"(carpeta) {d}", "ADVERTENCIA",
                                   "La carpeta no calza con nadie de la planilla: revisar tipeos "
                                   "o palabras de más (RUT, 'docs', '(1)')"))
    return filas


COLORES_CHEQUEO = {"ERROR": "FFC7CE", "ADVERTENCIA": "FFEB9C"}


# Dónde queda el reporte del chequeo si no se indica: junto al reporte de la
# corrida, con "_chequeo" al final ("reporte_crear_2026....xlsx" ->
# "reporte_crear_2026..._chequeo.xlsx").
def ruta_reporte_chequeo(output: str) -> str:
    base, _ext = os.path.splitext(output)
    return base + "_chequeo.xlsx"


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


# Traduce lo que devolvió la gestión de documentos a las líneas que se leen en
# el reporte y en la consola. Avisa además si a la persona le faltó alguno de
# los documentos habituales, para el conteo del resumen final.
def _notas_documentos(docs: dict, omitidos: list) -> tuple[list[str], bool]:
    if docs["sin_rut"]:
        return ["Docs: no se pudo abrir la vista (RUT no está en la grilla)"], False

    notas = []
    faltan = False

    if docs["limpieza"]:
        accion, lista = docs["limpieza"]
        verbo = {"listado": "Docs borrables",
                 "simulado": "Docs que se BORRARÍAN (modo prueba, no se borró nada)",
                 }.get(accion, "Docs BORRADOS")
        # Las líneas entre corchetes son avisos del proceso, no documentos.
        cantidad = sum(1 for x in lista if not x.startswith("["))
        notas.append(f"{verbo} ({cantidad}): " + (" ; ".join(lista) if lista else "ninguno"))

    if docs["tipos"] is not None:
        tipos = docs["tipos"]
        notas.append(f"Docs actuales ({len(tipos)}): "
                     + (", ".join(tipos) if tipos else "ninguno"))

    if docs["subida"]:
        accion, subidos, ya_existian, errs = docs["subida"]
        verbo = {"subido": "Docs SUBIDOS",
                 "subido_con_periodo": "Docs SUBIDOS (hubo que completar Período)",
                 "sin_items_nuevos": "Docs: nada nuevo que subir",
                 "rechazado": "Docs subir RECHAZADO por el sitio",
                 "simulado": "Docs (simulado)",
                 "sin_items": "Docs subir: sin items"}.get(accion, accion)
        nota = f"{verbo} ({len(subidos)}): " + (", ".join(subidos) or "ninguno")
        if ya_existian:
            nota += f" | ya tenía, no se re-subió ({len(ya_existian)}): " + ", ".join(ya_existian)
        if omitidos:
            nota += f" | omitidos: {'; '.join(omitidos)}"
        if errs:
            nota += f" | errores: {'; '.join(errs)}"
        if docs.get("captura"):
            nota += f" | captura del panel: {docs['captura']}"

        # Si falta alguno de los documentos habituales no se frena nada, solo
        # queda la advertencia en el reporte. Lo que la persona ya tenía
        # cargado cuenta como presente aunque no venga en la carpeta de ahora.
        # Se compara sin el prefijo "LOGISTICA FALABELLA/" por si la grilla
        # del sitio lo muestra.
        presentes_norm = {quitar_prefijo_catalogo(t) for t in
                          (subidos + ya_existian + (docs.get("tipos_sitio") or []))}
        faltantes = [t for t in DOCUMENTOS_SET_ESTANDAR
                     if quitar_prefijo_catalogo(t) not in presentes_norm]
        if faltantes:
            nota += (f" | ⚠ FALTAN documentos del set estándar ({len(faltantes)}): "
                     + ", ".join(faltantes))
            faltan = True
        notas.append(nota)

    return notas, faltan


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
        escribir_combobox_simple(page, "cbSexo", fila["SEXO"], "Sexo")
        campos_cambiados.append("Sexo")
    if normalizar_texto(actuales.get("cbAFP")) != normalizar_texto(fila["AFP"]):
        escribir_combobox_simple(page, "cbAFP", fila["AFP"], "AFP")
        campos_cambiados.append("AFP")
    if normalizar_texto(actuales.get("cbIsapre")) != normalizar_texto(fila["ISAPRE"]):
        escribir_combobox_simple(page, "cbIsapre", fila["ISAPRE"], "Sistema de Salud")
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
        escribir_combobox_simple(page, "cbSexo", fila["SEXO"], "Sexo")

    escribir_campo_texto(page, "txtSueldoBase", str(fila["sueldoBase"]))
    escribir_combobox_simple(page, "cbAFP", fila["AFP"], "AFP")
    escribir_combobox_simple(page, "cbIsapre", fila["ISAPRE"], "Sistema de Salud")
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
    parser.add_argument("--solo-chequear", action="store_true",
                        help="Revisa el Excel (y la carpeta de --subir-documentos, si se indica) "
                             "sin abrir Chrome ni tocar el sitio, muestra lo que habría que "
                             "corregir y termina.")
    parser.add_argument("--reporte-chequeo", default=None,
                        help="Excel donde se guardan los problemas del chequeo previo, si los "
                             "hay (por defecto, el de --output con '_chequeo' al final).")
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
    elif LIMPIAR_DOCUMENTOS == "borrar" and NO_GUARDAR:
        print(">>> --limpiar-documentos=borrar en MODO PRUEBA: NO se borra nada. Se listan los "
              "documentos que se borrarían y se prueba el clic en borrar cancelando la "
              "confirmación.\n")
    elif LIMPIAR_DOCUMENTOS == "borrar":
        print(">>> --limpiar-documentos=borrar: se BORRARÁN (irreversible) los documentos borrables "
              "de cada persona preexistente tras editar sus datos.\n")
    if SUBIR_DOCUMENTOS:
        if not os.path.isdir(SUBIR_DOCUMENTOS):
            print(f"ERROR: la carpeta de documentos '{SUBIR_DOCUMENTOS}' no existe.")
            sys.exit(1)
        if args.solo_chequear:
            modo = "solo se revisarán (sin subir nada)"
        elif NO_GUARDAR:
            modo = "se llenará el form (Cancelar, sin subir)"
        else:
            modo = "se subirán"
        print(f">>> --subir-documentos: {modo} los documentos de '{SUBIR_DOCUMENTOS}'.\n")

    df = cargar_excel(args.input, COLUMNAS_EXCEL_REQUERIDAS)
    df = autocompletar_campos_negocio(df)
    print(f"Cargados {len(df)} colaboradores desde {args.input}\n")

    # El chequeo previo corre siempre antes de tocar el sitio y deja a la vista
    # lo que va a fallar. Si encuentra algo, lo deja además en un Excel. Con
    # --solo-chequear se termina acá (la interfaz lee el resumen y pregunta si
    # seguir); por consola, se pregunta aquí mismo.
    chequeo_carpeta = (chequear_carpeta_documentos(df, SUBIR_DOCUMENTOS)
                       if SUBIR_DOCUMENTOS else None)
    datos_chequeo = chequear_datos_excel(df)
    con_problemas = imprimir_chequeo_previo(datos_chequeo, chequeo_carpeta, SUBIR_DOCUMENTOS)
    filas_chequeo = filas_reporte_chequeo(datos_chequeo, chequeo_carpeta)
    if filas_chequeo:
        escribir_reporte(filas_chequeo, args.reporte_chequeo or ruta_reporte_chequeo(args.output),
                         COLORES_CHEQUEO, etiqueta="Reporte del chequeo previo")
    if args.solo_chequear:
        return 0
    # Solo se pregunta si hay alguien escribiendo en una consola: desde la
    # interfaz (sin consola) se pregunta allá, antes de lanzar esta corrida.
    # El ejecutable se construye sin consola y, llamado a mano desde una
    # terminal, isatty() dice que sí la hay pero después leer da EOF: sin el
    # try, la corrida moría ahí en vez de seguir.
    if con_problemas and sys.stdin is not None and sys.stdin.isatty():
        try:
            respuesta = input(f"El chequeo previo encontró {con_problemas} persona(s) con problemas. "
                              "¿Continuar de todos modos? (s/N): ").strip().lower()
        except (EOFError, OSError):
            print("No se pudo preguntar por consola; se continúa con la corrida.")
            respuesta = "s"
        if respuesta not in ("s", "si", "sí"):
            print("Ejecución cancelada: no se abrió el sitio ni se modificó nada.")
            return 0

    playwright, browser, page = conectar_a_chrome_existente()
    asegurar_pagina_trabajadores(page)

    resultados: list[ResultadoFila] = []
    grupo_actual = None
    docs_incompletos = 0  # gente a la que le faltó algún documento del set

    # Las carpetas se reparten para todo el lote antes de empezar, así se
    # detecta si una misma carpeta le calza a dos personas.
    carpetas_por_fila = {}
    carpetas_sin_dueno = []
    if chequeo_carpeta is not None:
        _, carpetas_sin_dueno, asignacion = chequeo_carpeta
        carpetas_por_fila = dict(zip(df.index, asignacion))

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

            # Cada cosa de documentos tiene su propia condición para correr:
            # borrar los viejos es solo para quien ya existía; anotar lo que
            # tiene, para cualquiera que no haya fallado; subir, para quien
            # haya quedado bien en el sistema (los estados simulados entran
            # también, si no en modo prueba esta parte nunca se probaría).
            quiere_limpiar = bool(LIMPIAR_DOCUMENTOS and resultado.preexistente
                                  and resultado.estado != "ERROR")
            quiere_verificar = bool(VERIFICAR_DOCUMENTOS and resultado.estado != "ERROR")
            quiere_subir = bool(SUBIR_DOCUMENTOS and resultado.estado in (
                "CREADO", "EDITADO", "SIN_CAMBIOS", "SIMULADO_CREAR", "SIMULADO_EDITAR"))

            # La carpeta se revisa antes de ir a ninguna parte: si no está o no
            # tiene nada que sirva, no hay nada que subir y quizás ni haga
            # falta entrar a la pantalla de documentos.
            items, omitidos = None, []
            if quiere_subir:
                carpeta, motivo = carpetas_por_fila[i]
                nota_carpeta = ""
                if not carpeta:
                    nota_carpeta = f"⚠ FALTAN TODOS los documentos: {motivo}"
                else:
                    items, omitidos = preparar_items_carpeta(carpeta)
                    if not items:
                        nota_carpeta = (
                            "⚠ FALTAN TODOS los documentos: la carpeta no tiene archivos válidos"
                            + (f" | omitidos: {omitidos}" if omitidos else ""))
                if nota_carpeta:
                    quiere_subir = False
                    docs_incompletos += 1
                    resultado.detalle = (resultado.detalle + " | " + nota_carpeta).strip(" |")
                    print(f"   -> {nota_carpeta}")

            # Todo lo que quede por hacer se resuelve en UNA sola visita a la
            # pantalla de documentos: llegar hasta ahí es lo más lento del bot.
            if quiere_limpiar or quiere_verificar or quiere_subir:
                try:
                    docs = gestionar_documentos_trabajador(
                        page, rut, proveedor,
                        limpiar=(LIMPIAR_DOCUMENTOS if quiere_limpiar else None),
                        verificar=quiere_verificar,
                        items=(items if quiere_subir else None),
                        periodo_ddmmaaaa=formatear_fecha(fila["fechaContratacion"]),
                        vencimiento_ddmmaaaa=formatear_fecha(fila["fechaTermino"]),
                        guardar=(not NO_GUARDAR),
                    )
                    notas, faltan = _notas_documentos(docs, omitidos)
                    if faltan:
                        docs_incompletos += 1
                    for nota in notas:
                        resultado.detalle = (resultado.detalle + " | " + nota).strip(" |")
                        print(f"   -> {nota}")
                except Exception as e:
                    resultado.detalle += f" | Docs: ERROR: {e}"
                    print(f"   -> Docs: ERROR: {e}")
                finally:
                    # Se volvió a la lista base, así que el grupo hay que
                    # elegirlo de nuevo en la persona siguiente.
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
            if isinstance(e, CampoNoCompletado):
                detalle = f"No se pudo completar el formulario: {e}"
            elif isinstance(e, RutAmbiguoEnGrilla):
                detalle = str(e)
            else:
                detalle = f"Error inesperado durante el procesamiento: {e}"
            resultados.append(ResultadoFila(rut=rut, nombre_excel=nombre_completo,
                                             estado="ERROR", detalle=detalle))
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
    if carpetas_sin_dueno:
        print(f"⚠ {len(carpetas_sin_dueno)} carpeta(s) no calzaron con nadie de la planilla "
              f"y no se usaron: {', '.join(carpetas_sin_dueno)}")

    # En modo prueba se deja el navegador abierto para poder revisar.
    if not NO_GUARDAR:
        browser.close()
    playwright.stop()


if __name__ == "__main__":
    main()
