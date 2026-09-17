# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/).

## [1.2.0]

### Añadido
- Scaffolding del estándar para proyectos backend que todavía no lo siguen (fallback, sin tener que migrar el proyecto entero a mano primero): "Analizar proyecto" ahora también detecta si faltan `app/Services/AbstractModuleService.php`, `app/Services/CrudService.php`, el `Controller` base con anotaciones Swagger, `RouteServiceProvider.php`, una clase `Token` propia y la migración de auditoría `{prefijo}_procesosaudit` — y ofrece generar lo que falte, sin sobrescribir nunca un archivo que ya exista.
- `CrudService.php` se genera siempre completo, con auditoría activa, nunca en una versión reducida: si no existe la tabla `{prefijo}_procesosaudit`, la fase de generación crea también su migración y su modelo (con las constantes `TIPO_*`/`ESTADO_*`/`ORIGEN_*`, esquema tomado 1:1 de Auditoría.md); si no se encuentra una clase `Token` propia del proyecto para resolver el usuario autenticado, el `CrudService` generado usa `Auth::user()` nativo de Laravel en su lugar (funcionalmente equivalente bajo Sanctum), con un comentario explícito señalando esa línea por si el proyecto agrega su propio helper más adelante.
- Nuevo módulo `scaffold.py` con la detección (`detect_scaffold_status`) y la escritura no-destructiva (`write_missing_base_pieces` / `write_crud_service_with_audit`) — reutilizable independientemente de la GUI.

## [1.1.3]

### Corregido
- "Analizar proyecto" daba falso negativo del loader de `routes/modules/*.php` en proyectos Laravel 11+ que conservan un `RouteServiceProvider` propio (registrado a mano en `bootstrap/providers.php`) — justo el patrón que prescribe el estándar de rutas (`Conexiones, Migraciones y Rutas.md#4`). La detección de L11+ (por `withRouting` en `bootstrap/app.php`) descartaba `RouteServiceProvider.php` de plano, aunque el loader real viviera ahí. Ahora se revisan ambos archivos cuando los dos existen.

## [1.1.2]

### Cambiado
- La sección "Conexión — BD objetivo" se saca de la ventana principal y pasa a un diálogo aparte (mismo patrón que Logs/Preferencias), abierto desde un botón "Conexión…" o desde Archivo → Conexión… — reemplaza el enfoque colapsable de 1.1.1 (un checkbox en el título no comunicaba bien que la sección se podía ocultar, y aun así ocupaba todo el espacio la primera vez, antes de conectar). La ventana principal ahora solo muestra una fila de estado compacta (`● Conectado — db@host · N tablas`) y el diálogo se cierra solo al conectar con éxito.
- "Proyectos destino" pasa a ocupar el ancho completo de la ventana en vez de compartir fila con la conexión — más lugar para los campos de ruta backend/frontend sin apretarlos.

## [1.1.1]

### Cambiado
- La sección "Conexión — BD objetivo" ahora es colapsable (clic en el título o botón "Configurar después") y se colapsa sola al conectar con éxito, dejando el título con un resumen (`db@host ✓`) — antes quedaba siempre expandida y competía por espacio vertical con el grid/preview, que es lo que se usa todo el tiempo una vez conectado.
- El cuadro "Proyectos destino" ya no se estira para igualar la altura de la caja de conexión (dejaba un área vacía grande debajo del checkbox) — ambos cuadros quedan alineados arriba, con su altura natural.
- El preview ya no queda en blanco después de "Analizar" — se genera automáticamente, sin esperar a que el desarrollador apriete "Actualizar preview" a mano.

## [1.1.0]

### Añadido
- Generación de `{Modulo}Resource.php` (completo), `{Modulo}RelationResource.php` (mínimo, para `whenLoaded()` desde otro módulo) y `{Modulo}TinyResource.php` (mínimo, para `?tiny=true` del propio módulo) — ver "Resource triple" en la documentación del patrón. Reutilizan la misma selección de campos "tiny" que ya usaba `I{Modulo}Tiny` en las interfaces TypeScript, y el `{Modulo}Resource` referencia el `{FkModulo}RelationResource` correspondiente para cada FK cargada (`whenLoaded`).
- Documentación Swagger/OpenAPI (`darkaonline/l5-swagger` / `zircote/swagger-php`): cada Resource generado lleva su propio `@OA\Schema` (`{Modulo}Schema` / `{Modulo}RelationSchema` / `{Modulo}TinySchema`), y el `{table}Controller.php` generado documenta cada método (`index`/`show`/`store`/`update`/`destroy`) con su docblock `@OA\Get|Post|Put|Delete` completo — siempre contra el envelope real de `ApiResponse` (`status`/`message`/`data`) y referenciando el schema por `$ref`, nunca una `description` suelta.

- Historial de generación (`Logs → Historial de generación…` en la barra de menú): cada vez que se confirma "Generar archivos" se registra una entrada persistida en `%APPDATA%\ServiceForge\generation_log.json` con el módulo, cantidad de FKs y campos, tiempo transcurrido en esa sesión entre "Analizar" y "Generar archivos", cantidad de archivos escritos y líneas de código generadas. El diálogo lista el historial completo y permite exportarlo a CSV con el mismo shape que la tabla de medición de lead time por módulo (ver 3.2.5 del informe) — falta agregar a mano solo el tiempo del proceso manual y el % de reducción, que la herramienta no puede medir por no ejecutar ese proceso.

### Corregido
- `index()` del Controller generado usaba `{Modulo}RelationResource` para `?tiny=true` — ese Resource es para cuando OTRO módulo carga este como relación (`whenLoaded`), no para el propio selector/dropdown del módulo. Ahora usa `{Modulo}TinyResource`, que es el que corresponde según el estándar documentado.

## [1.0.1]

### Añadido
- Autocompletado "por palabras" en los editores del preview (sin IA / sin Copilot): cada pestaña `.php` sugiere keywords de PHP/Eloquent/Laravel (`belongsTo`, `Illuminate\Database\Eloquent\Model`, `fillable`, etc.) y cada pestaña `.ts` sugiere keywords de TypeScript — combinadas en ambos casos con las palabras que ya aparecen en ese mismo documento. Se dispara solo (2+ letras escritas) o a mano con Ctrl+Espacio.

### Cambiado
- **La versión ya no se escribe a mano.** `__version__` (`src/generador/__init__.py`) ahora se resuelve solo: usa `_version.py` si CI lo generó al construir el `.exe` de un tag `v*`, si no corre `git describe --tags --dirty` contra el repo local (refleja el tag/commit actual y si hay cambios sin commitear). `pyproject.toml` ahora declara `version` como `dynamic` y lo lee de `generador.__version__` — un solo lugar de verdad, sin riesgo de que los dos archivos queden desincronizados (como pasó antes: `0.1.6` en pyproject vs `0.1.4` en `__init__.py`).

## [1.0.0]

### Cambiado
- **Renombrado el proyecto** de "Generador Front-Back" a **Service-Forge** — nuevo nombre de paquete (`service-forge`), ejecutable (`ServiceForge.exe`), carpeta de datos de usuario (`%APPDATA%\ServiceForge`) y referencias al repo (`github.com/Gabngs/ServiceForge`). El README y los mensajes de la GUI (título de ventana, "Acerca de") quedan actualizados al nuevo nombre.
- Primera versión `1.0.0`: se marca como release estable del flujo completo, aunque la app se sigue lanzando **en modo prototipo** (el título de ventana y el README lo indican explícitamente) mientras se valida contra proyectos reales.

### Añadido
- Botón "Ampliar preview ↗" en el panel de preview: abre el mismo `QTabWidget` (no una copia) en una ventana aparte más grande, para editar el código generado con más espacio antes de escribir a disco. Al cerrar esa ventana, el panel vuelve a su lugar en el layout principal.
- `start.sh` + `scripts/dev_watch.py`: forma de correr la GUI en local para probar cambios sin esperar el `.exe` de CI. PySide6 no soporta hot-reload real, así que `dev_watch.py` vigila los `.py`/`.j2` bajo `src/` y, ante un cambio guardado, mata la ventana vieja y levanta una nueva sola.

## [0.1.6]

### Añadido
- Backup de la BD: diálogo previo para elegir el contenido del dump — estructura y datos (completo), solo estructura (`--no-data`) o solo datos (`--no-create-info`).
- Backup de la BD: diálogo de progreso con barra real (tablas procesadas / total, parseado del `--verbose` de mysqldump) y un log tipo consola plegable ("Ver detalle") para seguir el avance en vivo, en vez de una ventana congelada.

### Cambiado
- Backup de la BD: ahora corre en un hilo aparte (mismo patrón que "Probar conexión"), así la ventana no se congela mientras `mysqldump` corre.
- Backup de la BD: si falla, el error y el stderr completo de mysqldump se muestran dentro del mismo diálogo de progreso (con el log forzado a visible) en vez de un popup separado que tapaba el detalle.

## [0.1.5]

### Corregido
- Backup por SSH: `mysqldump` (cliente 8.0+) fallaba con error 1109 (`Unknown table 'COLUMN_STATISTICS' in information_schema`) contra servidores MySQL <8.0 o MariaDB, porque el cliente pide por defecto histogramas de columnas que esas versiones no exponen. Ahora se detecta ese error puntual y se reintenta el dump con `--column-statistics=0`, sin afectar a clientes mysqldump viejos que no soportan ese flag.

## [0.1.4]

### Corregido
- CI: el job `test` fallaba en Windows después de que **todos los tests pasaran** ("71 passed" seguido de exit code 1) — un crash de PySide6 al cerrar el intérprete de Python (`STATUS_STACK_BUFFER_OVERRUN`), no una falla real de los tests. Causa: `QApplication`/widgets creados a mano sin un orden de destrucción controlado. Solución: los tests de GUI (`test_gui_smoke.py`) ahora usan `pytest-qt` (`qtbot.addWidget(...)`), que maneja el ciclo de vida de Qt correctamente. Reproducido y confirmado localmente antes y después del fix.

## [0.1.3]

### Corregido
- `{table}Filters.php`: los campos FK (`tienda_id`, `rol_id`, ...) ahora generan un método de resolución UUID→pkid (`public function tienda_id($value)`) además de aparecer en `$allowedFilters` — antes, filtrar por una FK comparaba el UUID crudo del frontend contra la columna `pkid` y nunca matcheaba nada.

### Añadido
- Mapeo de relaciones portable (`.md`): importar/exportar un archivo `columna -> tabla` para compartir resoluciones de FK entre desarrolladores/máquinas, sin depender de la caché local. Tiene prioridad sobre la caché y la detección automática.
- Barra de menú (Archivo/Editar/Ayuda) y diálogo de Preferencias: tema oscuro/claro (persistido), acceso a importar/exportar el mapeo de relaciones. "Idioma" queda como placeholder deshabilitado (i18n real todavía no implementado).
- Layout: Conexión y Proyectos destino ahora van en dos cards lado a lado; la grilla de columnas y el preview ahora comparten un panel redimensionable (splitter) en vez de una altura fija — el preview era chico y difícil de editar.
- Tests de humo de la GUI (offscreen) agregados a la suite de CI.

### Cambiado
- "Analizar proyecto": el aviso de "no se detectó el loader de rutas" pasó de alarmante (rojo) a informativo (amarillo) — la detección es una heurística de texto que puede dar falsos negativos, confirmado contra un proyecto real que ya funcionaba sin que la detección lo reconociera.

## [0.1.2]

### Añadido
- Generación del patrón de servicio completo: `{table}Filters.php`, `Store{Modulo}Request.php` / `Update{Modulo}Request.php` + trait `Validates{Modulo}`, `{table}Controller.php` (con soporte `?tiny=true`) y `routes/modules/{modulo}.php`.
- `belongsTo` de auditoría (`created_by`, `updated_by`, `deleted_by`) en el Model generado, contra un modelo de usuario configurable desde la GUI.
- Los archivos se escriben en la estructura real del proyecto (`app/Models/...`, `app/Services/...`, etc.) — ahora se eligen por separado la raíz del proyecto backend y del frontend, en vez de una carpeta de salida plana.
- "Analizar proyecto": escaneo de solo lectura del backend elegido para detectar si `routes/modules/*.php` ya se carga automáticamente (Laravel 10- vs 11+), con snippet sugerido si falta — nunca edita el proyecto en automático.
- El `audit-user.interface.ts` compartido ahora es opcional (checkbox, apagado por default) — pensado para cuando el programa se usa sobre un proyecto que ya existe y ya lo tiene.
- Preview editable: el contenido de cada pestaña al momento de generar es lo que se escribe a disco, no necesariamente el render de fábrica.
- Botón "Probar conexión" separado de "Conectar", con indicador de estado (conectando/conectado/error) — la conexión corre en un thread aparte para no congelar la ventana.
- Tema oscuro moderno para toda la interfaz (antes usaba el estilo por defecto de Qt).

### Cambiado
- README simplificado a landing page del repo (el detalle de diseño vive en el documento de arquitectura).

## [0.1.1]

### Añadido
- Primer prototipo funcional: conexión a MySQL/MariaDB, análisis de tabla (`DESCRIBE`, índices únicos), detección de relaciones FK con resolución manual cacheada por conexión+columna.
- Generación de `Model.php`, `{Modulo}Service.php` y las interfaces TypeScript del frontend (`I{Modulo}`, `Create`, `Update`, `Tiny` + `IAuditUser` compartido).
- Backup manual de la BD conectada vía `mysqldump`.
- Empaquetado a `.exe` con PyInstaller y workflow de GitHub Actions que corre los tests y publica el `.exe` como artifact / adjunto de Release en cada tag `v*`.
