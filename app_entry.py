import os
import sys


# Envoltorio de sys.stdout / sys.stderr que no deja que un fallo al escribir
# mate el programa. El ejecutable se construye sin consola (ver 11.12), así que
# al llamarlo a mano desde una terminal Windows rechaza cada escritura con
# "OSError: [Errno 22] Invalid argument": el trabajo se hacía completo y el bot
# moría al imprimir la última línea, después de guardar el reporte. Lanzado
# desde la interfaz, que le pasa una tubería válida, esto no cambia nada.
class _SalidaTolerante:
    def __init__(self, stream):
        self._stream = stream if stream is not None else open(os.devnull, "w")

    def write(self, texto):
        try:
            return self._stream.write(texto)
        except Exception:
            return len(texto)

    def flush(self):
        try:
            self._stream.flush()
        except Exception:
            pass

    # El resto (encoding, reconfigure, isatty…) lo resuelve el stream original.
    def __getattr__(self, nombre):
        return getattr(self._stream, nombre)


# Hace que cada línea salga apenas se escribe. Si no, el bot va guardando lo
# que imprime y la interfaz muestra el log recién al final, con la barra de
# avance congelada toda la corrida.
def _forzar_salida_por_linea():
    sys.stdout = _SalidaTolerante(sys.stdout)
    sys.stderr = _SalidaTolerante(sys.stderr)
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(line_buffering=True)
        except Exception:
            pass


# Puerta de entrada única del programa: sin argumentos abre la ventana, y con
# un modo corre esa parte y se va. Sirve para que, ya empaquetado, la interfaz
# pueda volver a llamarse a sí misma para lanzar el bot.
def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--modo-comparar":
        _forzar_salida_por_linea()
        import buscar_y_comparar
        sys.exit(buscar_y_comparar.main(sys.argv[2:]))

    if len(sys.argv) > 1 and sys.argv[1] == "--modo-crear":
        _forzar_salida_por_linea()
        import crear_o_editar
        sys.exit(crear_o_editar.main(sys.argv[2:]))

    import interfaz
    app = interfaz.InterfazBot()
    app.mainloop()


if __name__ == "__main__":
    main()
