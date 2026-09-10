import sys


# Hace que cada línea salga apenas se escribe. Si no, el bot va guardando lo
# que imprime y la interfaz muestra el log recién al final, con la barra de
# avance congelada toda la corrida.
def _forzar_salida_por_linea():
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
