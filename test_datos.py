# Pruebas de las funciones que NO tocan el navegador: las que interpretan el
# Excel y las que deciden a qué tipo corresponde cada archivo. Son las que más
# se van a seguir editando (cada lote trae nombres de archivo nuevos) y donde
# ya aparecieron errores reales, así que conviene tenerlas cubiertas.
#
# Correr:  python test_datos.py     (o: python -m pytest test_datos.py)
#
# Nada de esto abre Chrome ni entra al sitio: se puede correr en cualquier
# momento, sin sesión iniciada y sin riesgo de tocar datos reales.

import os
import shutil
import tempfile

import pandas as pd

from shift_common import (
    formatear_nombre_propio,
    normalizar_sexo,
    normalizar_texto,
    quitar_prefijo_catalogo,
)
from crear_o_editar import (
    _buscar_carpeta_persona,
    _carpeta_sugerida,
    chequear_carpeta_documentos,
    chequear_datos_excel,
    asignar_carpetas_lote,
    _vacio,
    autocompletar_campos_negocio,
    formatear_fecha,
)
from documentos import (_norm, _palabras_alternativa, clasificar_nombre_archivo,
                        preparar_items_carpeta, tipo_desde_nombre_archivo)
from tipos_documento import REGLAS_TIPO_DOCUMENTO


# La planilla trae el sexo abreviado y el sitio lo pide completo.
def test_normalizar_sexo():
    assert normalizar_sexo("M") == "Masculino"
    assert normalizar_sexo("f") == "Femenino"
    assert normalizar_sexo("Femenino") == "Femenino"
    assert normalizar_sexo("") == ""
    assert normalizar_sexo(None) == ""
    # Una celda vacía leída por pandas llega como el texto "nan".
    assert normalizar_sexo("nan") == ""


# El prefijo del catálogo aparece de un lado y del otro no, según la pantalla.
def test_quitar_prefijo_catalogo():
    assert quitar_prefijo_catalogo("LOGISTICA FALABELLA/Operario de Bodega EST") == "OPERARIO DE BODEGA EST"
    assert quitar_prefijo_catalogo("LOF1 ACCESO1") == "LOF1 ACCESO1"
    assert quitar_prefijo_catalogo(None) == ""
    assert normalizar_texto("  provida ") == "PROVIDA"


# Tildes y mayúsculas no deben hacer creer que es otra persona: fue la causa
# de los falsos "identidad DISTINTA" (HENRIQUEZ vs Henríquez).
def test_normalizar_texto_ignora_tildes_y_mayusculas():
    assert normalizar_texto("Henríquez") == normalizar_texto("HENRIQUEZ")
    assert normalizar_texto("Valentina Noemí") == normalizar_texto("VALENTINA NOEMI")
    assert normalizar_texto("MARIA ISABEL  Paredes") == "MARIA ISABEL PAREDES"
    assert normalizar_texto("Muñoz") == normalizar_texto("MUNOZ")
    assert normalizar_texto("Banmédica") == "BANMEDICA"


# Así se escriben en el sitio nombres y apellidos: sin tildes y con mayúscula
# inicial en cada palabra. La ñ se conserva.
def test_formatear_nombre_propio():
    assert formatear_nombre_propio("VALDÉS") == "Valdes"
    assert formatear_nombre_propio("débora abigail") == "Debora Abigail"
    assert formatear_nombre_propio("MARIA ISABEL  ") == "Maria Isabel"
    assert formatear_nombre_propio("San martin") == "San Martin"
    assert formatear_nombre_propio("MUÑOZ") == "Muñoz"
    assert formatear_nombre_propio("saint-felix") == "Saint-Felix"
    assert formatear_nombre_propio(None) == ""
    assert formatear_nombre_propio("nan") == ""
    assert formatear_nombre_propio(float("nan")) == ""


# El chequeo previo detecta en el Excel lo que después termina en un timeout
# del sitio: celdas obligatorias vacías y AFP/Salud fuera del catálogo.
def test_chequear_datos_excel():
    base = dict(RUT="1-9", NOMBRES="Ana", apellidoPaterno="Rojas", SEXO="Femenino",
                AFP="Provida", ISAPRE="Fonasa", CARGO="X", PROVEEDOR="Y", TIENDA="Z",
                fechaContratacion="2026-09-01")
    df = pd.DataFrame([
        base,
        dict(base, RUT="2-7", AFP="Sin AFP"),
        dict(base, RUT="3-5", AFP=float("nan"), ISAPRE="banmedica"),
        dict(base, RUT="4-3", SEXO=""),
    ])
    hallazgos = {rut: probs for rut, _, probs in chequear_datos_excel(df)}
    assert "1-9" not in hallazgos
    assert any("Sin AFP" in p for p in hallazgos["2-7"])
    # "banmedica" sin tilde es válido; la AFP vacía no.
    assert hallazgos["3-5"] == ["'AFP' vacío"]
    assert hallazgos["4-3"] == ["'Sexo' vacío"]


def test_carpeta_sugerida():
    assert _carpeta_sugerida("Débora Abigail", "San Martín") == "Debora_San_Martin"
    assert _carpeta_sugerida("Ayleen Yordana", "Palma") == "Ayleen_Palma"


# Cruce planilla/carpeta: quién no tiene carpeta, qué archivos no se
# reconocen y qué quedó escondido en subcarpetas.
def test_chequear_carpeta_documentos():
    base = tempfile.mkdtemp()
    try:
        carpeta = os.path.join(base, "Ana_Rojas")
        os.makedirs(os.path.join(carpeta, "_pdf"))
        for nombre in ("CI Ana.pdf", "Riohs.pdf", "EPP.pdf", "foto.heic",
                       os.path.join("_pdf", "cedula.pdf")):
            open(os.path.join(carpeta, nombre), "w").close()
        os.makedirs(os.path.join(base, "Pedro_Extra"))

        df = pd.DataFrame([
            dict(RUT="1-9", NOMBRES="Ana", apellidoPaterno="Rojas", apellidoMaterno="Vera"),
            dict(RUT="2-7", NOMBRES="Karen", apellidoPaterno="Bravo", apellidoMaterno="Diaz"),
        ])
        por_persona, sin_dueno, asignacion = chequear_carpeta_documentos(df, base)
        ana, karen = por_persona

        assert ana["carpeta"] == "Ana_Rojas"
        assert [t for _, t in ana["reconocidos"]] == [
            "Cédula de Identidad", "TC Reglamento Interno RIOHS mandante"]
        assert len(ana["omitidos"]) == 2  # EPP.pdf y foto.heic
        assert ana["en_subcarpetas"] == [os.path.join("_pdf", "cedula.pdf")]
        assert "Registro Entrega EPP" in ana["faltan"]

        assert karen["carpeta"] is None and karen["sugerida"] == "Karen_Bravo"
        assert sin_dueno == ["Pedro_Extra"]
        assert asignacion[0][0] == carpeta
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_formatear_fecha():
    assert formatear_fecha("2026-04-08 00:00:00") == "08/04/2026"
    assert formatear_fecha("") == ""
    assert formatear_fecha(None) == ""
    assert formatear_fecha("nan") == ""


def test_vacio():
    assert _vacio(None)
    assert _vacio("")
    assert _vacio("  ")
    assert _vacio("nan")
    assert _vacio(float("nan"))
    assert not _vacio("0")
    assert not _vacio("550000")


# Si falta la fecha de término se calcula, y si falta el sueldo va cero. El
# cero importa: antes quedaba el texto "nan" y se escribía así en el sitio.
def test_autocompletar_campos_negocio():
    df = pd.DataFrame([
        {"fechaContratacion": "2026-09-07", "fechaTermino": "", "sueldoBase": ""},
        {"fechaContratacion": "2026-09-07", "fechaTermino": "2026-10-01", "sueldoBase": "550000"},
    ])
    salida = autocompletar_campos_negocio(df)

    assert formatear_fecha(salida.loc[0, "fechaTermino"]) == "05/12/2026"
    assert salida.loc[0, "sueldoBase"] == "0"
    assert bool(salida.loc[0, "_fecha_termino_autocompletada"])
    assert bool(salida.loc[0, "_sueldo_autocompletado"])

    # La fila que venía completa no se toca.
    assert formatear_fecha(salida.loc[1, "fechaTermino"]) == "01/10/2026"
    assert salida.loc[1, "sueldoBase"] == "550000"
    assert not bool(salida.loc[1, "_fecha_termino_autocompletada"])
    assert not bool(salida.loc[1, "_sueldo_autocompletado"])


# Tildes, mayúsculas y separadores tienen que dar todos lo mismo.
def test_norm():
    assert _norm("Adán_León") == _norm("adan-leon") == _norm("ADAN LEON") == "ADAN LEON"
    assert _norm("C.I  Juan") == "C I JUAN"
    assert _norm(None) == ""


# Los archivos reales no se llaman como el tipo del catálogo.
def test_tipo_desde_nombre_archivo():
    casos = {
        "C.I ADAN LEON.pdf": "Cédula de Identidad",
        "CD FALABELLA RETAIL.pdf": "Contrato puesta a disposición",
        "MARCAJE BIOMETRICO.pdf": "Toma de conocimiento marca en biometrico (EST)",
        "irl adan leon.pdf": "Registro de Capacitación IRL (Ex Odi) Mandante",
        "riohs adan leon.pdf": "TC Reglamento Interno RIOHS mandante",
        "PROCEDIMIENTO USO EPP.pdf": "Registro de Capacitación Uso EPP",
        "Registro de entrega de EPP.pdf": "Registro Entrega EPP",
        "CONTACTO EN CASO DE EMERGENCIA.pdf": "Contacto en caso de Emergencia",
        # Nombre igual al tipo del catálogo: tiene que calzar por la vía directa.
        "Contrato de Trabajo.pdf": "Contrato de Trabajo",
        # Así llegan en la práctica: sin el "de".
        "Contrato Trabajo.pdf": "Contrato de Trabajo",
        "CONTRATO_TRABAJO ADAN LEON.pdf": "Contrato de Trabajo",
        "Anexo contrato trabajo.pdf": "Anexos de Contrato",
        "Finiquito de Trabajo.docx": "Finiquito de Trabajo",
        # Variantes con "de" de más o de menos, en otro orden o en plural.
        "Contrato de puesta a disposición.pdf": "Contrato puesta a disposición",
        "Capacitacion uso de EPP.pdf": "Registro de Capacitación Uso EPP",
        "Contacto emergencia.pdf": "Contacto en caso de Emergencia",
        "Reglamento interno.pdf": "TC Reglamento Interno RIOHS mandante",
        "Copia de contrato trabajo (1).pdf": "Contrato de Trabajo",
        "Liquidaciones agosto.pdf": "Liquidaciones de Sueldo",
        "Anexo contrato personal EST.pdf": "Anexos de contrato personal EST",
        "Ex-ODI.pdf": "Registro de Capacitación IRL (Ex Odi) Mandante",
        "Carnet.PDF": "Cédula de Identidad",
    }
    for archivo, esperado in casos.items():
        assert tipo_desde_nombre_archivo(archivo) == esperado, archivo

    # Lo que no calza con nada se omite, no se inventa un tipo.
    for archivo in ("foto vacaciones.jpg", "EPP.pdf", "scan0001.pdf", "Girl.pdf"):
        assert tipo_desde_nombre_archivo(archivo) is None, archivo


# Si un nombre calza igual de bien con dos tipos distintos, no se adivina: se
# omite y el motivo lo dice.
def test_clasificar_nombre_ambiguo():
    tipo, motivo = clasificar_nombre_archivo("Contrato trabajo y entrega EPP.pdf")
    assert tipo is None
    assert "ambiguo" in motivo and "Contrato de Trabajo" in motivo and "Registro Entrega EPP" in motivo


# La tabla de tipos_documento.py se edita a mano: cada tipo una sola vez y
# ninguna alternativa que quede vacía al quitarle las palabras de relleno.
def test_tabla_tipos_documento():
    tipos = [t for t, _ in REGLAS_TIPO_DOCUMENTO]
    assert len(tipos) == len(set(tipos)), "hay un tipo repetido en tipos_documento.py"
    for tipo, alternativas in REGLAS_TIPO_DOCUMENTO:
        for alt in alternativas:
            assert _palabras_alternativa(alt), f"alternativa vacía en {tipo!r}: {alt!r}"


# "Adan_Leon" tiene que calzar con "ADAN IGNACIO LEON BRAVO".
def test_buscar_carpeta_persona():
    base = tempfile.mkdtemp()
    try:
        for nombre in ("Adan_Leon", "Ariel_Diaz", "otro"):
            os.makedirs(os.path.join(base, nombre))

        ruta, motivo = _buscar_carpeta_persona(base, "ADAN IGNACIO", "LEON", "BRAVO")
        assert ruta == os.path.join(base, "Adan_Leon")
        assert motivo == ""

        # Nadie que calce: se avisa, no se agarra cualquiera.
        ruta, motivo = _buscar_carpeta_persona(base, "PEDRO", "GOMEZ", "SOTO")
        assert ruta is None
        assert "sin carpeta" in motivo
    finally:
        shutil.rmtree(base, ignore_errors=True)


# Una carpeta que le calza a dos personas no se le da a ninguna. Antes "Juan
# Soto Rojas", sin carpeta propia, recibía los documentos de "Juan Carlos Soto
# Pérez" porque "Juan_Soto" le calzaba a los dos.
def test_asignar_carpetas_lote():
    base = tempfile.mkdtemp()
    try:
        for nombre in ("Juan_Soto", "Ana_Rojas", "Pedro_Extra"):
            os.makedirs(os.path.join(base, nombre))
        personas = [
            ("Juan Carlos", "Soto", "Pérez"),
            ("Ana María", "Rojas", "Vera"),
            ("Juan", "Soto", "Rojas"),
            ("Karen", "Bravo", "Díaz"),
        ]

        asignacion, sin_dueno = asignar_carpetas_lote(base, personas)

        # Los dos Juan quedan sin carpeta, con el motivo.
        for j in (0, 2):
            ruta, motivo = asignacion[j]
            assert ruta is None
            assert "más de una persona" in motivo and "Juan_Soto" in motivo
        # A los demás no les cambia nada.
        assert asignacion[1] == (os.path.join(base, "Ana_Rojas"), "")
        assert asignacion[3][0] is None and "sin carpeta" in asignacion[3][1]
        # La carpeta de alguien que no está en la planilla se avisa.
        assert sin_dueno == ["Pedro_Extra"]

        # Con una carpeta más completa se resuelve: la de tres palabras le
        # gana a la de dos, y "Carlos" no está en el nombre del otro Juan.
        os.makedirs(os.path.join(base, "Juan_Carlos_Soto"))
        asignacion, sin_dueno = asignar_carpetas_lote(base, personas)
        assert asignacion[0][0] == os.path.join(base, "Juan_Carlos_Soto")
        assert asignacion[2][0] == os.path.join(base, "Juan_Soto")
        assert sin_dueno == ["Pedro_Extra"]
    finally:
        shutil.rmtree(base, ignore_errors=True)


# Los archivos que no sirven quedan aparte, con el motivo, en vez de perderse.
def test_preparar_items_carpeta():
    base = tempfile.mkdtemp()
    try:
        for nombre in ("C.I JUAN.pdf", "foto.jpg", "notas.txt"):
            open(os.path.join(base, nombre), "w").close()

        items, omitidos = preparar_items_carpeta(base)

        assert [i["tipo"] for i in items] == ["Cédula de Identidad"]
        assert any("notas.txt" in o and "extensi" in o for o in omitidos)
        assert any("foto.jpg" in o and "catálogo" in o for o in omitidos)
    finally:
        shutil.rmtree(base, ignore_errors=True)


# Las notas que salen en el reporte y en la consola. Se prueban porque son lo
# único que la persona que revisa el lote llega a ver.
def test_notas_documentos():
    from crear_o_editar import _notas_documentos

    # Si no se pudo entrar, una sola línea y nada más.
    notas, faltan = _notas_documentos(
        {"sin_rut": True, "limpieza": None, "tipos": None, "subida": None}, [])
    assert len(notas) == 1 and "no se pudo abrir" in notas[0]
    assert not faltan

    # Las tres cosas juntas dan tres líneas, en orden.
    docs = {
        "sin_rut": False,
        "limpieza": ("borrado", ["Contrato | 01/01/2026"]),
        "tipos": ["Cédula de Identidad"],
        "subida": ("subido", ["Cédula de Identidad"], [], []),
    }
    notas, faltan = _notas_documentos(docs, [])
    assert len(notas) == 3
    assert notas[0].startswith("Docs BORRADOS (1):")
    assert notas[1].startswith("Docs actuales (1):")
    assert notas[2].startswith("Docs SUBIDOS (1):")
    # Del set estándar de 8 subió uno solo, así que tiene que avisar.
    assert faltan and "FALTAN documentos del set" in notas[2]

    # "listado" es mirar sin borrar, y lo que ya tenía no se re-sube.
    docs = {
        "sin_rut": False,
        "limpieza": ("listado", []),
        "tipos": None,
        "subida": ("sin_items_nuevos", [], ["Cédula de Identidad"], []),
    }
    notas, _ = _notas_documentos(docs, ["foto.jpg (no calza)"])
    assert notas[0] == "Docs borrables (0): ninguno"
    assert "nada nuevo que subir" in notas[1]
    assert "ya tenía, no se re-subió (1)" in notas[1]
    assert "omitidos: foto.jpg (no calza)" in notas[1]

    # Lo que ya estaba cargado en el sitio cuenta como presente aunque no
    # venga en la carpeta; antes se reportaba como faltante. La grilla puede
    # traer el prefijo del catálogo.
    from documentos import DOCUMENTOS_SET_ESTANDAR
    en_sitio = ["LOGISTICA FALABELLA/" + t for t in DOCUMENTOS_SET_ESTANDAR[1:]]
    docs = {
        "sin_rut": False, "limpieza": None, "tipos": None,
        "subida": ("subido", ["Cédula de Identidad"], [], []),
        "tipos_sitio": en_sitio,
    }
    notas, faltan = _notas_documentos(docs, [])
    assert not faltan and "FALTAN" not in notas[0], notas

    # Y si en el sitio falta uno, se avisa solo ese.
    docs["tipos_sitio"] = en_sitio[:-1]
    notas, faltan = _notas_documentos(docs, [])
    assert faltan and "FALTAN documentos del set estándar (1)" in notas[0], notas


# El punto de toda la optimización: una sola visita a la pantalla de
# documentos por persona, en el orden correcto, y volviendo siempre a la lista.
def test_gestionar_documentos_una_sola_visita():
    import documentos as doc

    llamadas = []
    originales = {n: getattr(doc, n) for n in (
        "_abrir_vista_documentos", "_limpiar_en_vista_abierta",
        "_leer_tipos_en_vista_abierta", "_subir_en_vista_abierta",
        "_volver_a_trabajadores")}

    def _registrar(nombre, retorno):
        def _fake(*a, **k):
            llamadas.append(nombre)
            if nombre == "_subir_en_vista_abierta":
                # Tiene que recibir los tipos ya leídos, no volver a leerlos.
                assert k.get("tipos_ya_leidos") == ["Cédula de Identidad"]
            return retorno
        return _fake

    doc._abrir_vista_documentos = _registrar("_abrir_vista_documentos", True)
    doc._limpiar_en_vista_abierta = _registrar("_limpiar_en_vista_abierta", ("borrado", []))
    doc._leer_tipos_en_vista_abierta = _registrar(
        "_leer_tipos_en_vista_abierta", ["Cédula de Identidad"])
    doc._subir_en_vista_abierta = _registrar(
        "_subir_en_vista_abierta", ("subido", [], [], []))
    doc._volver_a_trabajadores = _registrar("_volver_a_trabajadores", None)

    try:
        resultado = doc.gestionar_documentos_trabajador(
            page=None, rut="1-9", grupo_proveedor="Grupo X",
            limpiar="borrar", verificar=True, items=[{"tipo": "Anexos"}])
        # Lo leído del sitio queda disponible para el cálculo de faltantes.
        assert resultado["tipos_sitio"] == ["Cédula de Identidad"]

        assert llamadas == [
            "_abrir_vista_documentos",
            "_limpiar_en_vista_abierta",
            "_leer_tipos_en_vista_abierta",
            "_subir_en_vista_abierta",
            "_volver_a_trabajadores",
        ], llamadas

        # Si no se pide nada, no se navega: es lo que ahorra el tiempo.
        llamadas.clear()
        doc.gestionar_documentos_trabajador(page=None, rut="1-9", grupo_proveedor="Grupo X")
        assert llamadas == []
    finally:
        for nombre, fn in originales.items():
            setattr(doc, nombre, fn)


# Corre todas las pruebas sin necesidad de instalar pytest.
def main():
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fallidas = 0
    for prueba in pruebas:
        try:
            prueba()
            print(f"  OK    {prueba.__name__}")
        except AssertionError as e:
            fallidas += 1
            print(f"  FALLA {prueba.__name__}: {e}")
        except Exception as e:
            fallidas += 1
            print(f"  ERROR {prueba.__name__}: {type(e).__name__}: {e}")

    print(f"\n{len(pruebas) - fallidas}/{len(pruebas)} pruebas OK")
    return 1 if fallidas else 0


if __name__ == "__main__":
    raise SystemExit(main())
