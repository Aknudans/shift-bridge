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

from shift_common import normalizar_sexo, normalizar_texto, quitar_prefijo_catalogo
from crear_o_editar import (
    _buscar_carpeta_persona,
    _vacio,
    autocompletar_campos_negocio,
    formatear_fecha,
)
from documentos import _norm, preparar_items_carpeta, tipo_desde_nombre_archivo


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
        "Finiquito de Trabajo.docx": "Finiquito de Trabajo",
    }
    for archivo, esperado in casos.items():
        assert tipo_desde_nombre_archivo(archivo) == esperado, archivo

    # Lo que no calza con nada se omite, no se inventa un tipo.
    assert tipo_desde_nombre_archivo("foto vacaciones.jpg") is None


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
