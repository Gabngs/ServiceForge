# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/).

## [2.2.1]

### Añadido
- **Selectores con búsqueda** (`SearchableComboBox`): el combo de "Tabla", el de "FK -> tabla" de la grilla y el de la resolución manual de FKs ambiguas se pueden escribir para filtrar la lista, en vez de recorrerla con el scroll (con una BD de cientos de tablas era tedioso).
  - Filtra por coincidencia en cualquier parte del nombre y sin distinguir mayúsculas (`usu` encuentra `catalogo_usuario`).
  - Al entrar al campo se selecciona el valor actual, así se puede empezar a escribir sin borrarlo.
  - Se confirma con Enter, eligiendo del popup o saliendo del campo: vale el texto exacto o el único ítem que contiene lo escrito; si no, vuelve al último valor válido (el combo nunca queda con una tabla que no existe).
  - En la grilla, la relación se aplica al confirmar y no con cada tecla, para no asignar tablas intermedias mientras se escribe (escribir `auth_group_permissions` pasa por `auth_group`, que también es una tabla).
- `project_scan.scan_eloquent_connections` y `suggest_eloquent_connection`: leen las conexiones de `config/database.php` (solo las claves de `connections`, sin ejecutar PHP ni resolver `env()`; ignoran `options`, `cache`, comentarios y `array(...)`) y sugieren la que corresponde a la BD conectada (`mysql_dbsiaw` para `dbsiaw`). "Analizar proyecto" también las lista.

### Cambiado
- **`$connection` de Eloquent ya no se pide en el diálogo de conexión.** Es una propiedad del proyecto backend y no de la BD a la que se conecta la herramienta, así que pasó a "Proyectos destino" como un selector que se llena solo al elegir la raíz del backend, al usar "Analizar proyecto" y al conectar la BD. Conserva lo que el desarrollador ya eligió y permite escribir un nombre que no esté en la lista. Sin backend ni elección, se sigue usando el nombre de la BD (o `mysql`), como antes.

## [2.1.1]

### Añadido
- Dataset de estructura de backends Laravel (`datasets/structure/`): 72 179 pares (modelo, archivo) de 5 repos reales y 30 sintéticos, con features y etiqueta, para reconocer el ROL de cada archivo (Filter, Resource, Resource mínimo, Requests, trait de validación, Service, Controller, rutas) aunque cada proyecto use otras carpetas, nombres y prefijos. Incluye dataset card (`README.md`) con fuentes, criterios de etiquetado, estadísticas, resultados y limitaciones.
- Pipeline offline y reproducible en `scripts/` (`scan_backend_structure.py`, `build_variation_profile.py`, `generate_synthetic_repos.py`, `build_structure_dataset.py`, `train_structure_models.py`, `make_dataset_stats.py`, núcleo en `structure_lib.py`). Los repos sintéticos salen de código y semilla y se borran solos al terminar. Dependencias aparte en `requirements-dataset.txt`; la app y el `.exe` no las necesitan.
- **Modelo de estructura integrado a la app** (`match_learner.StructureLearner`, `structure_scan.py`, `structure_matcher_pretrained.joblib`): al analizar una tabla, los Resources existentes se puntúan con un modelo entrenado con el dataset nuevo (25 features; en repos reales no vistos acierta el archivo correcto el 98 % de las veces frente al 90 % de la regla anterior) y el diálogo "Model/Resource existentes" muestra además, solo como información, el Filter, los Requests, el Service, el Controller y las rutas que ya existen para ese Model. Sigue aprendiendo de cada confirmación del desarrollador (se guarda en `structure_matcher.joblib`, aparte del archivo del modelo anterior). `scripts/export_structure_model.py` empaqueta el modelo con la app y `generador.spec` lo incluye en el `.exe`.
- `scripts/build_match_dataset.py --append`: suma proyectos al dataset de fábrica en vez de reemplazarlo. El dataset de fábrica pasó de 2 a 5 proyectos (394 Models) y se reentrenó el modelo empaquetado.

### Cambiado
- Estándar: se eliminó el `ApiResponse<T>` genérico del frontend. Solo quedan las piezas base compartidas (`IModelBase`, `IFiltersBase`, `IModelBasePaginate`) y cada modelo declara sus interfaces de respuesta; `delete` devuelve `I{Modelo}SingleResponse`, como el `destroy` del backend. Se documentó que el frontend nunca declara errores de negocio: el Service los lanza con `ValidationException::withMessages()` y `HelperMessage` los muestra.
- `find_candidates` escanea el proyecto con `structure_scan` (mismo código que el dataset, para que las features de entrenamiento y las de uso no diverjan) y conserva su firma; `ModelResourceMatch` suma `others`. El modelo anterior (`MatchLearner`, 4 features) queda en el código pero la app ya no lo usa.
- `start.sh` detecta un intérprete de Python que funcione (`python`, `py` o `python3`), sin caer en el stub de la Microsoft Store.

## [2.0.1]

### Añadido
- Detección de Models/Resources ya existentes en el proyecto backend antes de generar (`model_resource_scan.py`): compara por convención de nombre, `@mixin`, solapamiento de campos (incluyendo claves de relación, ej. `articulo`/`created_by`, no solo columnas planas — reusa la resolución de FK ya cacheada/importada por `fk_resolver`) y namespace, aunque el proyecto no siga la convención de esta herramienta.
- Modelo de aprendizaje persistente (`match_learner.py`, red neuronal chica de scikit-learn entrenada online) que mejora ese matching con cada confirmación del desarrollador ("Revisar Model/Resource detectado…" en el análisis de tabla) — nunca decide solo, arranca de un modelo de fábrica entrenado con proyectos Laravel reales (`scripts/build_match_dataset.py`) en vez de en frío.
- Aviso de "ya existen archivos en el destino" antes de "Generar archivos" (ruta convencional + Resources confirmados manualmente) — confirma antes de sobreescribir un Model/Resource en vez de hacerlo en silencio.
- Soporte para tablas con columna de soft-delete legada (`deleted` en vez de `deleted_at`): el Model generado declara `const DELETED_AT` para que el trait `SoftDeletes` no rompa contra una columna inexistente.
- Plantilla de estándar frontend `ApiResponse Frontend.md`.

### Cambiado
- "Conf. de generación" pasó a un diálogo propio (antes ocupaba espacio fijo en la ventana principal); "Relación" ahora aparece antes que "Tiny" en el mapeo de columnas; la columna "FK -> tabla" ya no se estira a ocupar todo el ancho sobrante; el panel de mapeo se ajusta al contenido en vez de dejar un bloque vacío grande cuando la tabla tiene pocas columnas; "Salida backend"/"Salida frontend" quedan ocultas hasta marcar "Generar en una carpeta de salida separada".

### Corregido
- Autocompletado del editor de preview: confirmar una sugerencia justo antes de un carácter que no es de identificador (`;`, `(`) duplicaba el prefijo tipeado (ej. "dele" + Tab → "deledeleted") en vez de completar la palabra.

## [1.5.1]

### Añadido
- Resaltado de sintaxis en el preview editable (Model/Service/Filters/Requests/Controller/etc.): PHP y TypeScript, misma paleta de colores que el visor de estándar.
- Checkbox "Añadir comentarios explicativos en el código generado" (activado por defecto): desmarcado, quita los comentarios `//` de racional/referencias a .md de los archivos generados por módulo — los bloques `/** */` (PHPDoc, anotaciones `@OA` de Swagger) nunca se tocan, son funcionales.

### Cambiado
- Los checkboxes que controlan cómo se genera (paginación, audit-user.interface.ts compartido, carpeta de salida separada, comentarios) ahora viven agrupados en su propio panel "Conf. de generación", en vez de repartidos sueltos por la ventana.

## [1.5.0]

### Corregido
- `{table}Filters.php`: el método resolver de cada FK usaba `whereNull('{campo}')` cuando el UUID recibido no resolvía a ningún `pkid` — eso trae de vuelta TODAS las filas con esa FK nula (el resultado opuesto al filtro pedido) en vez de devolver vacío. Ahora fuerza `$pkid ?? 0`, tal como documenta useFilters.md#FKs que guardan pkid.
- `{table}Filters.php`: los campos de búsqueda libre se declaraban en `$allowedSearch`, una propiedad que no existe en `QueryFilters` (el paquete la ignora en silencio — `?search=` no filtraba nada). Corregido a `$columnSearch`, el nombre real de la propiedad.

### Añadido
- Visor de estándar (menú "Estándar" → "Ver estándar del proyecto…"): las notas de `Service Patron` (Model, CrudService, useFilters, etc.) se empaquetan con la app y se muestran en una ventana de solo lectura, con navegación por `[[wikilinks]]` y resaltado de sintaxis en los bloques de código PHP/TS. "Actualizar estándar…" reemplaza el contenido mostrado por una carpeta `.md` elegida a mano (queda en `%APPDATA%/ServiceForge/standard_docs`, no pisa el paquete original) — pensado para cuando el estándar documentado cambia y eso no se refleja solo por regenerar código.

## [1.4.0]

### Añadido
- Importación desde migración Laravel (`Schema::create(...)`) como fuente alternativa a la conexión a BD: archivo elegido o texto pegado a mano, parseado por un nuevo `migration_import.py` que traduce la DSL de `Blueprint` a la misma forma que ya usa el flujo de conexión (columnas + índices únicos), así el resto del pipeline (resolución de FK, mapeo, preview, generación) no distingue el origen. Sin conexión a BD, la lista de tablas necesaria para reconocer candidatas de FK se completa escaneando `database/migrations/**/*.php` del propio proyecto; los FK explícitos de la migración (`->constrained()` / `->references()->on()`) tienen la misma prioridad que un mapeo `.md` importado.
- Checkbox "Relación" propio en el mapeo de columnas, independiente de "Tiny" — `{Modulo}RelationResource` y `{Modulo}TinyResource` ya no comparten forzosamente el mismo conjunto de campos (ver ApiResponse.md#Resource triple).
- Checkbox "El Controller admite ?paginate=true": desmarcado, el `index()` generado no ofrece paginación ni construye `meta` (ver Controller.md#Módulos sin paginación); marcado (default), genera el patrón completo ya documentado.
- Carpeta de salida separada: opción para escribir los archivos generados en una carpeta distinta de la raíz del proyecto backend/frontend (que sigue usándose para analizar/escanear tablas, migraciones y estructura existente) — útil para revisar el resultado antes de copiarlo a mano, o generar sin usar el proyecto real como destino directo de escritura.

### Cambiado
- El método `belongsTo` generado en el Model usa ahora el nombre LITERAL de la tabla relacionada (ej. `catalogo_tienda()`), no una abreviatura derivada de la columna — ver Model.md#Relaciones. La clave pública que expone el Resource (y la interfaz TypeScript) sigue siendo la corta (`tienda`), ahora en un campo propio (`relation_alias`) desacoplado del método real. Excepción: si dos columnas del mismo módulo apuntan a la misma tabla, se mantiene el nombre derivado de columna para evitar que ambos métodos colisionen.

## [1.3.0]

### Corregido
- `{table}Filters.php`: los campos FK (`*_id`) quedaban listados en `$allowedFilters` y `$allowedSorts` ADEMÁS de tener su método resolver — QueryFilters aplica los dos WHERE (el del método y el genérico), y el genérico compara el UUID crudo del frontend contra una columna que guarda el `pkid` (entero). Esa segunda condición nunca matchea, y en AND con la primera el resultado quedaba siempre vacío: el filtro (y el sort) por cualquier FK no funcionaba nunca, aunque el método resolver estuviera bien generado. Ahora los FK se excluyen de ambos arrays — ver useFilters.md#FKs que guardan pkid.
- `{table}Filters.php`: el método resolver de cada FK referenciaba el modelo relacionado con la ruta completa inline (`\App\Models\db{prefijo}\Tabla::where(...)`) en vez de un `use` al principio del archivo + nombre corto en el cuerpo — no coincidía con la convención documentada (ver el ejemplo `AghTareasLimpiezaFilters` de useFilters.md). Mismo fix aplicado a `Model.php` (las relaciones `belongsTo` y el modelo de usuario de auditoría) y a `{Modulo}Service.php` (`$uuidMapping`).
- `{Modulo}Service.php`: `$uuidMapping` armaba la ruta del modelo relacionado con el prefijo del **módulo actual** en vez del prefijo de la **tabla relacionada** — para una FK que cruza de prefijo (ej. módulo `mdt_pedidos` con una FK a `catalogo_tienda`, prefijo `catalogo`), el `use` generado apuntaba a una clase que no existe (`App\Models\dbmdt\catalogo_tienda`). `ManifestRelation` ahora carga su propio `fk_table_prefijo` en vez de asumir el del módulo.
- `Model.php`: la relación `belongsTo` de una FK cruzando de prefijo no tenía ningún `use`, dependía de que la clase relacionada estuviera por casualidad en el mismo namespace — ahora se agrega el `use` solo cuando el prefijo de la FK es distinto del propio (agregarlo cuando es el mismo sería un fatal error de PHP: "already in use").

### Añadido
- El combo "FK -> tabla" de la grilla de columnas ahora permite asignar manualmente CUALQUIER columna a una tabla relacionada, no solo las que terminan en `_id` (la detección automática de `fk_resolver` exige ese sufijo; la asignación manual no). Útil para tablas legadas o con una convención de nombres distinta. La asignación manual queda cacheada igual que una resolución automática (se recuerda en próximas conexiones y es exportable al mapeo de relaciones compartido).

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
