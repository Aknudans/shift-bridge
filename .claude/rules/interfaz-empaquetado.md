---
paths:
  - interfaz.py
  - app_entry.py
  - ShiftLaboralBot.spec
  - construir_exe.bat
---

# Interfaz y empaquetado (secciones 11.10 y 11.12 de CLAUDE.md)

### 11.10 Interfaz gráfica (`interfaz.py`)

- 3 modos, selector de Excel / reporte / carpeta (solo en modo documentos),
  checkbox `--no-guardar`, checkbox "verificar documentos" y menú de limpieza
  (No tocarlos / Solo anotarlos / Borrarlos) — estos dos solo fuera del modo
  Comparación. Borrar pide confirmación extra al Iniciar.
- Corre los modos como subproceso en un hilo aparte y muestra su stdout; la
  barra de progreso lee las líneas `[i/N] ...`.
- **"Abrir Chrome de depuración"**: busca `chrome.exe` en `%ProgramFiles%`,
  `%ProgramFiles(x86)%` y `%LOCALAPPDATA%`; si no lo encuentra, permite
  elegirlo a mano (lo recuerda en la sesión). Los `.bat` usan la misma
  búsqueda.
- **Nombre del reporte (22/09/2026)**: `_sugerir_nombre_reporte` propone
  `reporte[_crear]_AAAAMMDD_HHMMSS.xlsx` y lo renueva al cambiar de modo y al
  apretar Iniciar, salvo que la persona haya escrito o elegido otro
  (`salida_sugerida` guarda el último propuesto). Los defaults de consola
  (`--output`) siguen siendo `reporte.xlsx` / `reporte_crear.xlsx`.
- **Log (22/09/2026)**: la ventana toma el alto de la pantalla (hasta 1000 px).
  "Ampliar log" oculta los pasos 1-3 y las opciones (`marcos_configuracion`,
  se re-empaquetan con `before=self.marco_accion`), y se activa solo al
  iniciar: en una pantalla de 768 px el log mide ~76 px sin ampliar y ~500
  ampliado. `_log` solo hace `see("end")` si la vista ya estaba abajo (antes
  no se podía subir mientras corría). "Descargar log (.txt)" guarda el
  contenido del recuadro; al cancelar, al terminar con código ≠ 0 o con alguna
  línea con `ERROR`/`Traceback` (`hubo_errores`) se ofrece guardarlo.
- **"Cancelar proceso"**: pide confirmación y ejecuta
  `taskkill /F /T /PID <pid>` (el `/T` termina también el driver Node.js de
  Playwright). No afecta al Chrome de depuración.
- **"¿Cómo se usa?"**: ventana `CTkToplevel` aparte (una sola instancia). El
  texto vive en la constante `AYUDA` (lista de `(título, [párrafos])`); los
  párrafos que empiezan con `⚠` se pintan en rojo. El ícono se pone con
  `after(250, ...)` porque customtkinter lo pisa en Windows.

### 11.12 Empaquetado con PyInstaller

- **`app_entry.py`** como dispatcher: empaquetado, `sys.executable` es el
  propio `.exe`, así que `interfaz.py` (`_comando_base_modo`) se relanza con
  `[sys.executable, "--modo-crear", ...]`; en desarrollo usa
  `[sys.executable, "-u", "app_entry.py", "--modo-crear", ...]`.
  `buscar_y_comparar.main(argv=None)` y `crear_o_editar.main(argv=None)`
  aceptan argumentos.
- Sin consola: `.exe` compilado con `console=False` y subproceso con
  `creationflags=subprocess.CREATE_NO_WINDOW`. Playwright ya soporta
  `sys.frozen` y oculta la consola de su driver.
- 🔴 **Ejecutar el `.exe` a mano desde una terminal** (22/09/2026): con
  `console=False`, Windows deja `stdout` y `stdin` inservibles, y el modo
  consola moría **después** de hacer todo el trabajo. Dos blindajes:
  - `app_entry._SalidaTolerante` envuelve `sys.stdout`/`sys.stderr` en
    `_forzar_salida_por_linea`: descarta el error al escribir (antes, cada
    `print` daba `OSError: [Errno 22] Invalid argument`) y cubre el caso
    `stdout is None`. Delega el resto (`reconfigure`, `encoding`, `isatty`)
    al stream original, así que el `reconfigure` de `crear_o_editar.py`
    sigue funcionando.
  - La confirmación del chequeo previo (`crear_o_editar.main`) va dentro de
    un `try/except (EOFError, OSError)`: `isatty()` responde `True` pero
    leer da EOF (`EOFError: EOF when reading a line`). Si no se puede
    preguntar, avisa y continúa, igual que cuando la interfaz lanza el
    subproceso con `stdin=DEVNULL`.
  - Lanzado desde la interfaz, que pasa una tubería válida, nada de esto
    cambia.
- `ShiftLaboralBot.spec` calcula en tiempo de build la ruta de
  `playwright/driver` (se agrega con `--add-data`, PyInstaller no la detecta)
  e incluye `collect_data_files('customtkinter')`.
- **Formato carpeta** (`exclude_binaries=True` + `COLLECT`), no onefile: el
  onefile descomprimía ~7.400 archivos en `%TEMP%` en cada apertura (dos veces,
  por el relanzamiento) y tardaba ~18 s en mostrar la ventana. En carpeta:
  ~1 s. Lista `EXCLUIDOS` (jedi, IPython, ipykernel, zmq, PIL, pygments,
  setuptools…); si algún día se usa algo de esa lista (p. ej. `CTkImage`),
  sacarlo de ahí. `upx=False`.
- Cerrar el programa antes de construir (`construir_exe.bat` usa
  `--noconfirm`).
- 🔴 **Archivos que acompañan al `.exe`** (22/09/2026): PyInstaller **borra**
  `dist\ShiftLaboralBot\` antes de recrearla, y `GUIA_EJECUCION.txt` y
  `SHIFT_ejemplo.xlsx` no están en el `.spec`. Se perdieron una vez por eso:
  `SHIFT_ejemplo.xlsx` vivía solo ahí y `dist/` está en `.gitignore`. Ahora
  vive en la raíz del proyecto (excepción `!SHIFT_ejemplo.xlsx`; una sola
  fila ficticia, sin datos reales) y `construir_exe.bat` copia los dos a
  `dist\ShiftLaboralBot\` después de construir, avisando si alguno falta.
  Al agregar otro archivo a la entrega, sumarlo a ese `for` del `.bat`.
