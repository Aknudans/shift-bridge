# Tipos de documento del sitio y las palabras clave que los identifican en el
# nombre de un archivo. Este archivo es solo una tabla: la lógica que la usa
# está en documentos.py (clasificar_nombre_archivo).
#
# CÓMO SE LEE CADA LÍNEA
#   ("Tipo tal como aparece en el sitio, sin 'LOGISTICA FALABELLA/'",
#    ["alternativa 1", "alternativa 2", ...]),
#
#   Un archivo es de ese tipo si su nombre contiene TODAS las palabras de
#   ALGUNA de las alternativas, en cualquier orden y con cualquier texto
#   adicional alrededor. Ejemplo: la alternativa "CONTRATO TRABAJO" reconoce
#   "Contrato Trabajo.pdf", "trabajo_contrato.pdf" y
#   "Copia de contrato de trabajo Juan.pdf".
#
# QUÉ SE IGNORA AL COMPARAR (no hace falta preverlo al escribir palabras)
#   - Mayúsculas y tildes: "Cédula" = "CEDULA" = "cedula".
#   - Separadores en el nombre del archivo: espacio, "_", "-", "." y ",".
#   - Plurales simples: "ANEXO" también reconoce "ANEXOS" y "LIQUIDACION"
#     reconoce "LIQUIDACIONES" (se acepta la palabra terminada en S o ES).
#   - Palabras de relleno escritas en una alternativa (ver PALABRAS_RELLENO):
#     escribir "CONTACTO DE EMERGENCIA" equivale a "CONTACTO EMERGENCIA".
#
# QUÉ PASA SI UN NOMBRE CALZA CON DOS TIPOS
#   Gana el tipo cuya alternativa tenga MÁS palabras (la más específica). Si
#   empatan, el archivo no se sube y se reporta como "tipo ambiguo". Ejemplo:
#   "Anexo contrato trabajo" calza con "ANEXO CONTRATO TRABAJO" (3 palabras,
#   Anexos de Contrato) y con "CONTRATO TRABAJO" (2 palabras, Contrato de
#   Trabajo): gana Anexos de Contrato.
#
# PARA AGREGAR UNA VARIANTE NUEVA
#   1. Agregar la alternativa en la lista del tipo que corresponde.
#   2. Preferir alternativas de 2 o más palabras. Una palabra sola solo si es
#      inequívoca (p. ej. "RIOHS", "FINIQUITO"); una genérica como "EPP" o
#      "CONTRATO" sola calzaría con varios tipos.
#   3. Correr `python test_datos.py` y, si se quiere dejar fijo el caso,
#      agregarlo en test_tipo_desde_nombre_archivo.
#
# PARA AGREGAR UN TIPO NUEVO
#   Agregar una línea con el nombre EXACTO del tipo en el sitio (sin el
#   prefijo "LOGISTICA FALABELLA/"). El bot elige esa opción en la lista
#   desplegable del sitio comparando ese texto, así que si no coincide el
#   archivo no se puede subir. Un archivo que se llame exactamente como el
#   tipo se reconoce siempre, aunque no tenga alternativas.

PALABRAS_RELLENO = {"DE", "DEL", "EN", "LA", "LAS", "EL", "LOS", "A", "Y", "O", "CASO"}

REGLAS_TIPO_DOCUMENTO = [
    ("Cédula de Identidad",
     ["CEDULA", "CARNET", "CI", "C I"]),
    ("Contrato puesta a disposición",
     ["CPD", "CD", "CONTRATO DISPOSICION", "CONTRATO PUESTA"]),
    ("Contrato de Trabajo",
     ["CONTRATO TRABAJO"]),
    ("Anexos de Contrato",
     ["ANEXO CONTRATO", "ANEXO CONTRATO TRABAJO"]),
    ("Anexos de contrato personal EST",
     ["ANEXO PERSONAL EST", "ANEXO CONTRATO PERSONAL EST"]),
    ("Anexos",
     ["ANEXO"]),
    ("Contacto en caso de Emergencia",
     ["EMERGENCIA", "CONTACTO EMERGENCIA"]),
    ("Toma de conocimiento marca en biometrico (EST)",
     ["BIOMETRICO", "MARCAJE", "TOMA CONOCIMIENTO MARCA"]),
    ("Registro Entrega EPP",
     ["ENTREGA EPP"]),
    ("Registro de Capacitación Uso EPP",
     ["USO EPP"]),
    ("Registro de Capacitación IRL (Ex Odi) Mandante",
     ["IRL", "ODI", "EXODI"]),
    ("TC Reglamento Interno RIOHS mandante",
     ["RIOHS", "REGLAMENTO INTERNO"]),
    ("Finiquito de Trabajo",
     ["FINIQUITO"]),
    ("Visa de trabajo o ATT",
     ["VISA", "ATT"]),
    ("Comprobante de Entrevista del personal EST y OUT",
     ["ENTREVISTA", "COMPROBANTE ENTREVISTA"]),
    ("Liquidaciones de Sueldo",
     ["LIQUIDACION", "LIQ"]),
]
