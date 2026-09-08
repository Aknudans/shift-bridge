"""
Interfaz gráfica — Bot ShiftLaboral
====================================

Ventana única con 3 modos (elegidos por el usuario, uno a la vez):

    1. Comparación   -> corre buscar_y_comparar.py (Fase 1, solo lectura).
    2. Creación       -> corre crear_o_editar.py (Fase 2: crea o edita según
                         corresponda cada RUT del Excel).
    3. Subir documentos -> corre crear_o_editar.py --subir-documentos CARPETA
                         (crea/edita si hace falta y sube los documentos de
                         la carpeta indicada; ver CLAUDE.md sección 12.9).

No reimplementa la lógica de negocio de los bots: los corre como subproceso
(`python -u <script>.py --input ... --output ...`) y muestra su salida en
vivo en un log, con una barra de progreso calculada de las líneas
"[i/N] ..." que ya imprime cada script. Esto evita duplicar/romper la lógica
ya probada en vivo contra el sitio real.

Uso:
    python interfaz.py
"""

import os
import queue
import re
import subprocess
import sys
import threading
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox

import customtkinter as ctk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SCRIPT_COMPARAR = os.path.join(BASE_DIR, "buscar_y_comparar.py")
SCRIPT_CREAR = os.path.join(BASE_DIR, "crear_o_editar.py")

# Mismo perfil/puerto que abrir_chrome.bat / ejecutar_crear.bat — un solo
# perfil de depuración compartido por todos los modos de esta interfaz.
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_PROFILE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ChromeDebugShiftLaboral"
)
CHROME_DEBUG_PORT = 9222
SHIFT_URL = "https://externoslof.shiftlabor.com/"

RE_PROGRESO = re.compile(r"^\[(\d+)/(\d+)\]")
RE_RESUMEN = re.compile(r"^Resumen:")

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")


class InterfazBot(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Bot ShiftLaboral")
        self.geometry("880x680")
        self.minsize(760, 560)

        self.proceso: subprocess.Popen | None = None
        self.cola_salida: "queue.Queue[str]" = queue.Queue()
        self.total_filas = None

        self._construir_widgets()
        self._actualizar_visibilidad_modo()
        self.after(100, self._drenar_cola)

    # -----------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------

    def _construir_widgets(self):
        pad = {"padx": 14, "pady": 8}

        ctk.CTkLabel(
            self, text="Bot ShiftLaboral", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w", **pad)

        # --- Paso 1: Chrome -------------------------------------------------
        marco_chrome = ctk.CTkFrame(self)
        marco_chrome.pack(fill="x", **pad)
        ctk.CTkLabel(
            marco_chrome, text="1. Abrir Chrome e iniciar sesión (una vez por sesión)",
            font=ctk.CTkFont(weight="bold"),
        ).pack(side="left", padx=10, pady=10)
        ctk.CTkButton(
            marco_chrome, text="Abrir Chrome de depuración", command=self._abrir_chrome
        ).pack(side="right", padx=10, pady=10)

        # --- Paso 2: modo -----------------------------------------------------
        marco_modo = ctk.CTkFrame(self)
        marco_modo.pack(fill="x", **pad)
        ctk.CTkLabel(
            marco_modo, text="2. ¿Qué querés hacer?", font=ctk.CTkFont(weight="bold")
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

        # --- Paso 3: archivos ---------------------------------------------
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

        # --- Opciones extra ---------------------------------------------
        marco_opciones = ctk.CTkFrame(self)
        marco_opciones.pack(fill="x", **pad)
        self.var_no_guardar = ctk.BooleanVar(value=False)
        self.check_no_guardar = ctk.CTkCheckBox(
            marco_opciones,
            text="Modo prueba: llenar el formulario pero NO guardar (--no-guardar)",
            variable=self.var_no_guardar,
        )
        self.check_no_guardar.pack(anchor="w", padx=10, pady=8)

        # --- Iniciar + progreso ---------------------------------------------
        marco_accion = ctk.CTkFrame(self)
        marco_accion.pack(fill="x", **pad)
        self.boton_iniciar = ctk.CTkButton(
            marco_accion, text="Iniciar", font=ctk.CTkFont(weight="bold"),
            command=self._iniciar, height=40,
        )
        self.boton_iniciar.pack(side="left", padx=10, pady=10)

        self.label_progreso = ctk.CTkLabel(marco_accion, text="")
        self.label_progreso.pack(side="left", padx=10)

        self.barra_progreso = ctk.CTkProgressBar(self)
        self.barra_progreso.set(0)
        self.barra_progreso.pack(fill="x", **pad)

        # --- Log ---------------------------------------------------------
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

        if modo == "comparar":
            self.check_no_guardar.configure(state="disabled")
            self.var_no_guardar.set(False)
        else:
            self.check_no_guardar.configure(state="normal")

        # Nombre de reporte por defecto sugerido según el modo, solo si el
        # usuario no lo cambió a mano todavía (heurística simple: si sigue
        # siendo uno de los 2 defaults conocidos).
        actual = self.entry_salida.get().strip()
        defaults = {
            os.path.join(BASE_DIR, "reporte.xlsx"),
            os.path.join(BASE_DIR, "reporte_crear.xlsx"),
        }
        if actual in defaults or actual == "":
            nuevo = "reporte.xlsx" if modo == "comparar" else "reporte_crear.xlsx"
            self.entry_salida.delete(0, "end")
            self.entry_salida.insert(0, os.path.join(BASE_DIR, nuevo))

    # -----------------------------------------------------------------
    # Selección de archivos
    # -----------------------------------------------------------------

    def _elegir_excel(self, entrada):
        ruta = filedialog.askopenfilename(
            title="Elegí el Excel de entrada",
            filetypes=[("Excel", "*.xlsx"), ("Todos los archivos", "*.*")],
        )
        if ruta:
            entrada.delete(0, "end")
            entrada.insert(0, ruta)

    def _elegir_salida(self, entrada):
        ruta = filedialog.asksaveasfilename(
            title="Elegí dónde guardar el reporte",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if ruta:
            entrada.delete(0, "end")
            entrada.insert(0, ruta)

    def _elegir_carpeta_docs(self, entrada):
        ruta = filedialog.askdirectory(title="Elegí la carpeta con los documentos")
        if ruta:
            entrada.delete(0, "end")
            entrada.insert(0, ruta)

    # -----------------------------------------------------------------
    # Chrome
    # -----------------------------------------------------------------

    def _abrir_chrome(self):
        try:
            os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)
            subprocess.Popen(
                [
                    CHROME_EXE,
                    f"--remote-debugging-port={CHROME_DEBUG_PORT}",
                    f"--user-data-dir={CHROME_PROFILE_DIR}",
                    SHIFT_URL,
                ]
            )
            self._log(
                "Se abrió Chrome de depuración. Iniciá sesión manualmente en la "
                "ventana que se abrió (el bot nunca ve ni guarda tu clave)."
            )
        except FileNotFoundError:
            messagebox.showerror(
                "No se encontró Chrome",
                f"No se encontró Chrome en:\n{CHROME_EXE}\n\n"
                "Abrilo manualmente con --remote-debugging-port=9222.",
            )
        except Exception as e:
            messagebox.showerror("Error al abrir Chrome", str(e))

    # -----------------------------------------------------------------
    # Ejecución del bot
    # -----------------------------------------------------------------

    def _validar_antes_de_iniciar(self) -> str:
        excel = self.entry_excel.get().strip()
        salida = self.entry_salida.get().strip()
        if not excel:
            return "Elegí el Excel de entrada."
        if not os.path.isfile(excel):
            return f"El Excel de entrada no existe:\n{excel}"
        if not salida:
            return "Elegí dónde guardar el reporte de salida."
        if self.modo.get() == "documentos":
            carpeta = self.entry_carpeta_docs.get().strip()
            if not carpeta:
                return "Elegí la carpeta de documentos."
            if not os.path.isdir(carpeta):
                return f"La carpeta de documentos no existe:\n{carpeta}"
        return ""

    def _armar_comando(self) -> list[str]:
        excel = self.entry_excel.get().strip()
        salida = self.entry_salida.get().strip()
        modo = self.modo.get()

        if modo == "comparar":
            return [sys.executable, "-u", SCRIPT_COMPARAR, "--input", excel, "--output", salida]

        comando = [sys.executable, "-u", SCRIPT_CREAR, "--input", excel, "--output", salida]
        if self.var_no_guardar.get():
            comando.append("--no-guardar")
        if modo == "documentos":
            carpeta = self.entry_carpeta_docs.get().strip()
            comando += ["--subir-documentos", carpeta]
        return comando

    def _iniciar(self):
        if self.proceso is not None:
            return  # ya hay una corrida en curso

        error = self._validar_antes_de_iniciar()
        if error:
            messagebox.showwarning("Falta información", error)
            return

        comando = self._armar_comando()
        self.total_filas = None
        self.barra_progreso.set(0)
        self.label_progreso.configure(text="")
        self._limpiar_log()
        self._log("Ejecutando: " + " ".join(comando))
        self.boton_iniciar.configure(state="disabled", text="Corriendo...")

        hilo = threading.Thread(target=self._correr_proceso, args=(comando,), daemon=True)
        hilo.start()

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

    def _al_terminar(self, codigo: str):
        self.boton_iniciar.configure(state="normal", text="Iniciar")
        if self.total_filas:
            self.barra_progreso.set(1)
        if codigo == "0":
            self._log("\n=== Terminado correctamente. ===")
        else:
            self._log(f"\n=== Terminó con errores (código {codigo}). Revisá el log arriba. ===")
            messagebox.showwarning(
                "Terminó con errores",
                "El proceso terminó con errores. Revisá el log en la ventana principal.",
            )

    # -----------------------------------------------------------------
    # Log
    # -----------------------------------------------------------------

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
