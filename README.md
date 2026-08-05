# Bot de búsqueda y comparación — ShiftLaboral

Fase 1 del proyecto: **solo lectura**. Busca cada RUT de tu Excel en ShiftLaboral,
compara los datos personales, y genera un reporte. No crea, edita ni borra nada.

## Instalación (una sola vez por computador)

1. Instalar Python 3.9 o superior (https://www.python.org/downloads/).
2. Abrir una terminal en esta carpeta y correr:
   ```
   pip install -r requirements.txt
   ```

## Cómo correrlo (cada vez)

### Paso 1 — Abrir Chrome en modo depuración
Cerrar todas las ventanas de Chrome primero, y luego abrirlo así:

**Windows** (Símbolo del sistema / cmd):
```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

**Mac** (Terminal):
```
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

### Paso 2 — Iniciar sesión manualmente
En esa ventana de Chrome que se abrió, entra a https://externoslof.shiftlabor.com/
e inicia sesión con tu usuario y contraseña, como siempre. Déjala abierta.

### Paso 3 — Preparar tu Excel de entrada
Debe tener (al menos) estas columnas, con esos nombres exactos, en la primera hoja del archivo:

```
RUT | NOMBRES | apellidoPaterno | apellidoMaterno | SEXO | AFP | ISAPRE | sueldoBase | PROVEEDOR | CARGO | TIENDA
```

Columnas adicionales como `fechaContratacion` y `fechaTermino` pueden estar
presentes (se usarán en la Fase 2 de creación) pero por ahora se ignoran.

Nota: `PROVEEDOR`, `CARGO` y `TIENDA` pueden traer el prefijo
`LOGISTICA FALABELLA/` (igual que en los catálogos) — el script lo quita
automáticamente antes de comparar.

### Paso 4 — Correr el script
En otra terminal (sin cerrar la de Chrome), en esta carpeta:

```
python buscar_y_comparar.py --input mi_lista.xlsx --output reporte.xlsx
```

Al terminar, se genera `reporte.xlsx` con una fila por colaborador y su estado:
- 🟩 **OK**: todo coincide
- 🟨 **ADVERTENCIA**: el RUT existe pero algún dato no coincide (se detalla cuál)
- 🟥 **NO_ENCONTRADO**: el RUT no existe en ShiftLaboral

## Si algo falla

- **"No se pudo conectar a Chrome en el puerto 9222"** → revisa que Chrome esté
  abierto con el comando del Paso 1, y que no tengas otra ventana de Chrome normal
  abierta en simultáneo (puede confundir la conexión).
- **El script no encuentra el proveedor / se traba seleccionando el grupo** → el
  texto del dropdown de proveedores puede no calzar exacto con lo que dice tu
  columna "Proveedor" del Excel. Revisar `seleccionar_grupo_proveedor()` en el
  código y ajustar el texto de búsqueda.
- **ShiftLaboral cambió algo en su sitio** → los selectores usados están todos
  centralizados al inicio del archivo `buscar_y_comparar.py` (sección
  CONFIGURACIÓN), para poder ajustarlos rápido sin tocar el resto del código.

## Importante

Este script interactúa con la interfaz web de ShiftLaboral, no con una API
oficial (no existe una para este propósito — ver contexto del proyecto). Por
eso: no correr muchas instancias en paralelo con el mismo usuario (recordar el
límite de sesión única), y probar siempre primero con 2-3 filas antes de correr
el lote completo.
