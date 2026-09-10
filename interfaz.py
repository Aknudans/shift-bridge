import os
import queue
import re
import subprocess
import sys
import threading
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox

import customtkinter as ctk

# La carpeta donde vive el programa, que es donde se van a proponer el Excel y
# el reporte. Si está empaquetado hay que mirar dónde está el ejecutable, y no
# la carpeta temporal donde se descomprime solo, porque esa se borra al salir.
FROZEN = getattr(sys, "frozen", False)
BASE_DIR = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))

APP_ENTRY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_entry.py")

# Para que no aparezca ni parpadee una consola negra al lanzar el bot.
CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# El mismo Chrome de depuración que abren los .bat: un solo perfil aparte,
# compartido por todos los modos, para no chocar con el Chrome de siempre.
CHROME_PROFILE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ChromeDebugShiftLaboral"
)
CHROME_DEBUG_PORT = 9222
SHIFT_URL = "https://externoslof.shiftlabor.com/"

# Chrome no siempre está en el mismo lugar: cambia entre la versión de 64 y 32
# bits y la que se instala solo para un usuario. Se prueban las tres, y si no
# aparece en ninguna se le pregunta a la persona dónde está.
CHROME_CANDIDATOS = [
    os.path.join(base, r"Google\Chrome\Application\chrome.exe")
    for base in (
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    )
]

# Una vez encontrado, se recuerda para no volver a preguntar en esta sesión.
_chrome_recordado = None


def _buscar_chrome() -> str:
    global _chrome_recordado
    if _chrome_recordado and os.path.isfile(_chrome_recordado):
        return _chrome_recordado
    for ruta in CHROME_CANDIDATOS:
        if os.path.isfile(ruta):
            _chrome_recordado = ruta
            return ruta
    return ""

# Las tres opciones del menú de documentos anteriores, tal como se leen en
# pantalla. Se traducen al flag correspondiente al armar el comando.
LIMPIAR_NO_TOCAR = "No tocarlos"
LIMPIAR_LISTAR = "Solo anotarlos en el reporte"
LIMPIAR_BORRAR = "Borrarlos (no se puede deshacer)"

RE_PROGRESO = re.compile(r"^\[(\d+)/(\d+)\]")
RE_RESUMEN = re.compile(r"^Resumen:")

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")


# El ícono está al lado del código cuando se corre con Python, y dentro de la
# carpeta temporal que arma el ejecutable cuando está empaquetado.
def _ruta_icono() -> str:
    if FROZEN:
        base = getattr(sys, "_MEIPASS", BASE_DIR)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "icono.ico")


# La ventana del programa. No repite nada de la automatización: lanza los
# scripts de siempre como un proceso aparte y va mostrando lo que imprimen.
class InterfazBot(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Bot ShiftLaboral")
        self.geometry("880x760")
        self.minsize(760, 620)
        try:
            self.iconbitmap(_ruta_icono())
        except Exception:
            pass  # quedarse sin ícono no es razón para no abrir la ventana

        self.proceso: subprocess.Popen | None = None
        self.cola_salida: "queue.Queue[str]" = queue.Queue()
        self.total_filas = None
        self.cancelado_por_usuario = False

        self._construir_widgets()
        self._actualizar_visibilidad_modo()
        self.after(100, self._drenar_cola)

    # Arma la ventana de arriba a abajo, siguiendo el orden en que se usa:
    # abrir Chrome, elegir el modo, elegir los archivos, y recién ahí iniciar.
    def _construir_widgets(self):
        pad = {"padx": 14, "pady": 8}

        ctk.CTkLabel(
            self, text="Bot ShiftLaboral", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w", **pad)

        # Paso 1: abrir el Chrome de depuración e iniciar sesión a mano.
        marco_chrome = ctk.CTkFrame(self)
        marco_chrome.pack(fill="x", **pad)
        ctk.CTkLabel(
            marco_chrome, text="1. Abrir Chrome e iniciar sesión (una vez por sesión)",
            font=ctk.CTkFont(weight="bold"),
        ).pack(side="left", padx=10, pady=10)
        ctk.CTkButton(
            marco_chrome, text="Abrir Chrome de depuración", command=self._abrir_chrome
        ).pack(side="right", padx=10, pady=10)

        # Paso 2: qué se va a hacer.
        marco_modo = ctk.CTkFrame(self)
        marco_modo.pack(fill="x", **pad)
        ctk.CTkLabel(
            marco_modo, text="2. Seleccionar el modo", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=10, pady=(10, 2))

        self.modo = ctk.StringVar(value="comparar")
        opciones = [
            ("Comparación (solo lectura, no modifica nada)", "comparar"),
            ("Creación / edición de colaboradores", "crear"),
            ("Subir documentos", "documentos"),
        ]
        for texto, valor in opciones:
            ctk.CTkRadioButton(
                marco_modo, text=texto, variable=self.modo, value=valor,
                command=self._actualizar_visibilidad_modo,
            ).pack(anchor="w", padx=20, pady=4)

        # Paso 3: de dónde sale el Excel y dónde va el reporte.
        marco_archivos = ctk.CTkFrame(self)
        marco_archivos.pack(fill="x", **pad)
        ctk.CTkLabel(
            marco_archivos, text="3. Archivos", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=10, pady=(10, 2))

        self.entry_excel = self._fila_archivo(
            marco_archivos, "Excel de entrada:", self._elegir_excel
        )
        self.entry_salida = self._fila_archivo(
            marco_archivos, "Reporte de salida:", self._elegir_salida
        )
        self.entry_salida.insert(0, os.path.join(BASE_DIR, "reporte.xlsx"))

        self.fila_carpeta_docs = ctk.CTkFrame(marco_archivos, fg_color="transparent")
        self.entry_carpeta_docs = self._fila_archivo(
            self.fila_carpeta_docs, "Carpeta de documentos:", self._elegir_carpeta_docs
        )

        # La corrida de prueba y las dos opciones de documentos.
        marco_opciones = ctk.CTkFrame(self)
        marco_opciones.pack(fill="x", **pad)
        self.var_no_guardar = ctk.BooleanVar(value=False)
        self.check_no_guardar = ctk.CTkCheckBox(
            marco_opciones,
            text="Modo prueba: llenar el formulario pero NO guardar",
            variable=self.var_no_guardar,
        )
        self.check_no_guardar.pack(anchor="w", padx=10, pady=(8, 4))

        self.var_verificar_docs = ctk.BooleanVar(value=False)
        self.check_verificar_docs = ctk.CTkCheckBox(
            marco_opciones,
            text="Anotar en el reporte qué documentos tiene ya cada persona (no sube ni borra nada)",
            variable=self.var_verificar_docs,
        )
        self.check_verificar_docs.pack(anchor="w", padx=10, pady=4)

        # Borrar documentos es lo único irreversible de toda la app, así que va
        # apagado por default y vuelve a pedir confirmación al iniciar.
        self.fila_limpiar = ctk.CTkFrame(marco_opciones, fg_color="transparent")
        self.fila_limpiar.pack(fill="x", padx=10, pady=(4, 8))
        ctk.CTkLabel(
            self.fila_limpiar, text="Documentos anteriores de quienes ya existían:",
            anchor="w",
        ).pack(side="left")
        self.var_limpiar_docs = ctk.StringVar(value=LIMPIAR_NO_TOCAR)
        ctk.CTkOptionMenu(
            self.fila_limpiar, width=260, variable=self.var_limpiar_docs,
            values=[LIMPIAR_NO_TOCAR, LIMPIAR_LISTAR, LIMPIAR_BORRAR],
        ).pack(side="left", padx=8)

        # Botones de iniciar y cortar, con la barra de avance al lado.
        marco_accion = ctk.CTkFrame(self)
        marco_accion.pack(fill="x", **pad)
        self.boton_iniciar = ctk.CTkButton(
            marco_accion, text="Iniciar", font=ctk.CTkFont(weight="bold"),
            command=self._iniciar, height=40,
        )
        self.boton_iniciar.pack(side="left", padx=10, pady=10)

        # Botón de emergencia: corta todo al instante. Solo se puede apretar
        # mientras hay algo corriendo.
        self.boton_cancelar = ctk.CTkButton(
            marco_accion, text="Cancelar proceso", font=ctk.CTkFont(weight="bold"),
            command=self._cancelar, height=40, state="disabled",
            fg_color="#b3261e", hover_color="#8c1d17",
        )
        self.boton_cancelar.pack(side="left", padx=10, pady=10)

        self.label_progreso = ctk.CTkLabel(marco_accion, text="")
        self.label_progreso.pack(side="left", padx=10)

        self.barra_progreso = ctk.CTkProgressBar(self)
        self.barra_progreso.set(0)
        self.barra_progreso.pack(fill="x", **pad)

        # Todo lo que el bot va contando mientras trabaja.
        ctk.CTkLabel(self, text="Log en vivo:", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=14
        )
        self.texto_log = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=12))
        self.texto_log.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.texto_log.configure(state="disabled")

    def _fila_archivo(self, contenedor, etiqueta, comando_elegir):
        fila = ctk.CTkFrame(contenedor, fg_color="transparent")
        fila.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(fila, text=etiqueta, width=160, anchor="w").pack(side="left")
        entrada = ctk.CTkEntry(fila)
        entrada.pack(side="left", fill="x", expand=True, padx=6)
        ctk.CTkButton(fila, text="Elegir...", width=90, command=lambda: comando_elegir(entrada)).pack(
            side="left"
        )
        return entrada

    def _actualizar_visibilidad_modo(self):
        modo = self.modo.get()
        if modo == "documentos":
            self.fila_carpeta_docs.pack(fill="x")
        else:
            self.fila_carpeta_docs.pack_forget()

        # El modo de comparación es de solo lectura: ninguna de estas opciones
        # tiene sentido ahí, así que se apagan y se dejan grises.
        if modo == "comparar":
            self.check_no_guardar.configure(state="disabled")
            self.var_no_guardar.set(False)
            self.check_verificar_docs.configure(state="disabled")
            self.var_verificar_docs.set(False)
            self.var_limpiar_docs.set(LIMPIAR_NO_TOCAR)
            self.fila_limpiar.pack_forget()
        else:
            self.check_no_guardar.configure(state="normal")
            self.check_verificar_docs.configure(state="normal")
            self.fila_limpiar.pack(fill="x", padx=10, pady=(4, 8))

        # Se sugiere un nombre de reporte según el modo, pero sin pisar el
        # que la persona haya escrito a mano.
        actual = self.entry_salida.get().strip()
        defaults = {
            os.path.join(BASE_DIR, "reporte.xlsx"),
            os.path.join(BASE_DIR, "reporte_crear.xlsx"),
        }
        if actual in defaults or actual == "":
            nuevo = "reporte.xlsx" if modo == "comparar" else "reporte_crear.xlsx"
            self.entry_salida.delete(0, "end")
            self.entry_salida.insert(0, os.path.join(BASE_DIR, nuevo))

    # Los tres botones de "Elegir...".

    def _elegir_excel(self, entrada):
        ruta = filedialog.askopenfilename(
            title="Seleccionar el Excel de entrada",
            filetypes=[("Excel", "*.xlsx"), ("Todos los archivos", "*.*")],
        )
        if ruta:
            entrada.delete(0, "end")
            entrada.insert(0, ruta)

    def _elegir_salida(self, entrada):
        ruta = filedialog.asksaveasfilename(
            title="Seleccionar dónde guardar el reporte",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if ruta:
            entrada.delete(0, "end")
            entrada.insert(0, ruta)

    def _elegir_carpeta_docs(self, entrada):
        ruta = filedialog.askdirectory(title="Seleccionar la carpeta con los documentos")
        if ruta:
            entrada.delete(0, "end")
            entrada.insert(0, ruta)

    # Abre el Chrome de depuración en su perfil aparte. La sesión la inicia
    # la persona a mano: el bot nunca ve ni guarda la clave.

    def _abrir_chrome(self):
        global _chrome_recordado
        chrome = _buscar_chrome()
        if not chrome:
            messagebox.showinfo(
                "No se encontró Chrome",
                "No se encontró Chrome en las ubicaciones habituales.\n\n"
                "En la ventana siguiente, buscar el archivo chrome.exe "
                "(normalmente en Archivos de programa \\ Google \\ Chrome \\ Application).",
            )
            chrome = filedialog.askopenfilename(
                title="Buscar chrome.exe",
                filetypes=[("Chrome", "chrome.exe"), ("Programas", "*.exe")],
            )
            if not chrome:
                return
            _chrome_recordado = chrome

        try:
            os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)
            subprocess.Popen(
                [
                    chrome,
                    f"--remote-debugging-port={CHROME_DEBUG_PORT}",
                    f"--user-data-dir={CHROME_PROFILE_DIR}",
                    SHIFT_URL,
                ]
            )
            self._log(
                "Se abrió Chrome de depuración. Iniciar sesión manualmente en la "
                "ventana que se abrió (el bot nunca ve ni guarda la clave)."
            )
        except Exception as e:
            messagebox.showerror("Error al abrir Chrome", str(e))

    # De acá para abajo, lanzar y seguir la corrida.

    def _validar_antes_de_iniciar(self) -> str:
        excel = self.entry_excel.get().strip()
        salida = self.entry_salida.get().strip()
        if not excel:
            return "Seleccionar el Excel de entrada."
        if not os.path.isfile(excel):
            return f"El Excel de entrada no existe:\n{excel}"
        if not salida:
            return "Seleccionar dónde guardar el reporte de salida."
        if self.modo.get() == "documentos":
            carpeta = self.entry_carpeta_docs.get().strip()
            if not carpeta:
                return "Seleccionar la carpeta de documentos."
            if not os.path.isdir(carpeta):
                return f"La carpeta de documentos no existe:\n{carpeta}"
        return ""

    # Arma la orden para lanzar el bot en un proceso aparte. Empaquetado, el
    # programa se llama a sí mismo con el modo como argumento; corriendo con
    # Python hay que indicarle además qué archivo ejecutar.
    def _comando_base_modo(self, flag_modo: str) -> list[str]:
        if FROZEN:
            return [sys.executable, flag_modo]
        return [sys.executable, "-u", APP_ENTRY, flag_modo]

    def _armar_comando(self) -> list[str]:
        excel = self.entry_excel.get().strip()
        salida = self.entry_salida.get().strip()
        modo = self.modo.get()

        if modo == "comparar":
            return self._comando_base_modo("--modo-comparar") + ["--input", excel, "--output", salida]

        comando = self._comando_base_modo("--modo-crear") + ["--input", excel, "--output", salida]
        if self.var_no_guardar.get():
            comando.append("--no-guardar")
        if self.var_verificar_docs.get():
            comando.append("--verificar-documentos")
        limpiar = self.var_limpiar_docs.get()
        if limpiar == LIMPIAR_LISTAR:
            comando += ["--limpiar-documentos", "listar"]
        elif limpiar == LIMPIAR_BORRAR:
            comando += ["--limpiar-documentos", "borrar"]
        if modo == "documentos":
            carpeta = self.entry_carpeta_docs.get().strip()
            comando += ["--subir-documentos", carpeta]
        return comando

    def _iniciar(self):
        if self.proceso is not None:
            return  # ya hay algo corriendo

        error = self._validar_antes_de_iniciar()
        if error:
            messagebox.showwarning("Falta información", error)
            return

        # Borrar documentos no se puede deshacer, así que se pregunta de nuevo
        # aunque ya esté elegido en el menú.
        if self.var_limpiar_docs.get() == LIMPIAR_BORRAR:
            confirmar = messagebox.askyesno(
                "Borrar documentos anteriores",
                "A cada persona que YA EXISTÍA en ShiftLaboral se le van a BORRAR "
                "los documentos que subió el proveedor.\n\n"
                "Esto no se puede deshacer. Los documentos cargados por el mandante "
                "no se tocan.\n\n"
                "¿Confirma?",
                icon="warning",
            )
            if not confirmar:
                return

        comando = self._armar_comando()
        self.total_filas = None
        self.cancelado_por_usuario = False
        self.barra_progreso.set(0)
        self.label_progreso.configure(text="")
        self._limpiar_log()
        self._log("Ejecutando: " + " ".join(comando))
        self.boton_iniciar.configure(state="disabled", text="Corriendo...")
        self.boton_cancelar.configure(state="normal")

        hilo = threading.Thread(target=self._correr_proceso, args=(comando,), daemon=True)
        hilo.start()

    # Corta el proceso al instante, sin esperar a que termine la persona que
    # esté procesando. Por eso pregunta antes: puede dejar un formulario a
    # medio llenar en el sitio y el reporte final no se alcanza a escribir.
    def _cancelar(self):
        if self.proceso is None:
            return
        confirmar = messagebox.askyesno(
            "Cancelar proceso",
            "Esto corta el proceso DE INMEDIATO, a mitad de lo que esté haciendo.\n\n"
            "- Puede dejar un formulario a medio llenar abierto en ShiftLaboral "
            "(revisar manualmente después).\n"
            "- El reporte final NO se va a generar — solo queda el log de arriba "
            "con lo que se alcanzó a procesar.\n\n"
            "¿Confirma la cancelación?",
            icon="warning",
        )
        if not confirmar:
            return
        self.cancelado_por_usuario = True
        self.boton_cancelar.configure(state="disabled", text="Cancelando...")
        self._log("\n=== Cancelando por pedido del usuario... ===")
        hilo = threading.Thread(target=self._matar_proceso, daemon=True)
        hilo.start()

    # Mata el proceso de verdad, con todo lo que haya lanzado por debajo.
    def _matar_proceso(self):
        proceso = self.proceso
        if proceso is None:
            return
        try:
            if os.name == "nt":
                # Hay que matar también a los procesos hijos, porque el que
                # maneja el navegador queda dando vueltas si no.
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proceso.pid)],
                    capture_output=True,
                    creationflags=CREATIONFLAGS,
                )
            else:
                proceso.terminate()
        except Exception as e:
            self.cola_salida.put(f"ERROR al cancelar: {e}")

    # Corre el bot en un hilo aparte y va pasando cada línea que imprime a una
    # cola, para que la ventana no se congele mientras trabaja.
    def _correr_proceso(self, comando):
        try:
            self.proceso = subprocess.Popen(
                comando,
                cwd=BASE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=CREATIONFLAGS,
            )
            for linea in self.proceso.stdout:
                self.cola_salida.put(linea.rstrip("\n"))
            self.proceso.wait()
            self.cola_salida.put(f"__FIN__{self.proceso.returncode}")
        except Exception as e:
            self.cola_salida.put(f"ERROR al ejecutar el proceso: {e}")
            self.cola_salida.put("__FIN__1")
        finally:
            self.proceso = None

    # Cada décima de segundo saca lo que haya en la cola y lo muestra. De las
    # líneas del tipo "[3/20]" sale el avance de la barra, y de la del resumen
    # final, el texto que queda al lado.
    def _drenar_cola(self):
        try:
            while True:
                linea = self.cola_salida.get_nowait()
                if linea.startswith("__FIN__"):
                    codigo = linea.replace("__FIN__", "")
                    self._al_terminar(codigo)
                else:
                    self._procesar_linea(linea)
        except queue.Empty:
            pass
        self.after(100, self._drenar_cola)

    def _procesar_linea(self, linea: str):
        self._log(linea)

        m = RE_PROGRESO.match(linea)
        if m:
            actual, total = int(m.group(1)), int(m.group(2))
            self.total_filas = total
            self.barra_progreso.set(actual / total if total else 0)
            self.label_progreso.configure(text=f"{actual} / {total}")

        if RE_RESUMEN.match(linea):
            self.label_progreso.configure(text=linea.replace("Resumen: ", ""))

    # Deja los botones como estaban y avisa cómo terminó la cosa.
    def _al_terminar(self, codigo: str):
        self.boton_iniciar.configure(state="normal", text="Iniciar")
        self.boton_cancelar.configure(state="disabled", text="Cancelar proceso")
        if self.cancelado_por_usuario:
            self._log("\n=== Proceso CANCELADO por el usuario. El reporte final no se generó — "
                      "revisar el log de arriba y el estado de ShiftLaboral manualmente. ===")
            self.cancelado_por_usuario = False
            return
        if self.total_filas:
            self.barra_progreso.set(1)
        if codigo == "0":
            self._log("\n=== Terminado correctamente. ===")
        else:
            self._log(f"\n=== Terminó con errores (código {codigo}). Revisar el log arriba. ===")
            messagebox.showwarning(
                "Terminó con errores",
                "El proceso terminó con errores. Revisar el log en la ventana principal.",
            )

    # Escribir y limpiar el recuadro del log.

    def _log(self, texto: str):
        self.texto_log.configure(state="normal")
        self.texto_log.insert("end", texto + "\n")
        self.texto_log.see("end")
        self.texto_log.configure(state="disabled")

    def _limpiar_log(self):
        self.texto_log.configure(state="normal")
        self.texto_log.delete("1.0", "end")
        self.texto_log.configure(state="disabled")


if __name__ == "__main__":
    app = InterfazBot()
    app.mainloop()
