# Optimización del Workflow de GitHub Actions

Este documento resume los problemas detectados en el paso **"Instalar dependencias"** del workflow (Windows, Python 3.12, PySide6 + PyInstaller) y las acciones recomendadas para reducir el tiempo de ejecución.

## Diagnóstico

Según el log, el mayor costo de tiempo viene de:

- Descarga de paquetes pesados en cada ejecución:
  - `pyside6` (578 KB)
  - `pyside6_addons` (**168.8 MB**)
  - `pyside6_essentials` (**77.5 MB**)
  - `shiboken6` (1.2 MB)
- Sin cache configurado, estas descargas (~250 MB) se repiten en **cada corrida del workflow**, aunque las dependencias no hayan cambiado.
- Actualización de `pip` (`--upgrade pip`) en cada ejecución, aunque no sea estrictamente necesario.

## Recomendaciones

### 1. Habilitar cache de pip (mayor impacto)

Si usás `actions/setup-python`, activá el cache integrado:

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: '3.12'
    cache: 'pip'
    cache-dependency-path: requirements-dev.txt
```

Alternativa manual con `actions/cache`:

```yaml
- uses: actions/cache@v4
  with:
    path: ~\AppData\Local\pip\Cache
    key: ${{ runner.os }}-pip-${{ hashFiles('requirements-dev.txt') }}
    restore-keys: |
      ${{ runner.os }}-pip-
```

Esto evita re-descargar los `.whl` pesados si `requirements-dev.txt` no cambió entre ejecuciones.

### 2. Revisar si se necesita PySide6 completo

`pyside6-addons` y `pyside6-essentials` suman ~246 MB. Si la app no usa módulos como WebEngine o Multimedia, conviene evaluar si:

- Alcanza con `pyside6-essentials` solamente.
- Se pueden excluir extras no utilizados del paquete `pyside6`.

### 3. Usar `uv` en lugar de `pip`

[`uv`](https://github.com/astral-sh/uv) es un instalador de paquetes Python mucho más rápido que pip, con resolución de dependencias optimizada y cache nativo:

```yaml
- run: pip install uv
- run: uv pip install --system -r requirements-dev.txt
```

### 4. Evitar el upgrade de pip si no es necesario

El paso `python -m pip install --upgrade pip` agrega overhead en cada run. Si no se requiere la última versión, se puede fijar una versión específica o saltar este paso.

### 5. Separar cache por sistema operativo

Si el workflow corre en múltiples runners (Windows, Linux, macOS), usar `runner.os` en la key del cache evita que un cache mixto invalide las dependencias entre plataformas.

### 6. Considerar runners self-hosted o imagen Docker custom

Si el workflow se ejecuta muy frecuentemente, un runner self-hosted (o una imagen Docker con las dependencias preinstaladas) elimina por completo el tiempo de descarga.

## Resumen de impacto esperado

| Acción | Impacto en tiempo |
|---|---|
| Cache de pip | Alto — evita ~250 MB de descarga por run |
| `uv` en vez de `pip` | Medio-Alto — instalación y resolución más rápida |
| Revisar extras de PySide6 | Medio — depende de cuánto se pueda recortar |
| Evitar upgrade de pip | Bajo |
| Cache por SO | Bajo-Medio (solo aplica en workflows multiplataforma) |
| Runner self-hosted / Docker | Alto (pero requiere más mantenimiento) |

## Próximo paso sugerido

Empezar por el **cache de pip** (cambio de bajo esfuerzo, alto impacto) y luego evaluar `uv` como reemplazo de `pip install`.