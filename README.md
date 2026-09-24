# Service-Forge

GUI de escritorio que genera el boilerplate repetitivo de un módulo CRUD Laravel a partir de la base de datos: analiza una tabla, detecta relaciones FK, y genera el patrón de servicio completo — Model, Service, Filters, Requests + Trait, Controller y ruta — más las interfaces TypeScript del frontend correspondientes (`I{Modulo}`, `Create`, `Update`, `Tiny`).

> **Estado: v2.2.1 — prototipo.** Segunda versión estable de la herramienta en modo prototipo: el flujo completo funciona de punta a punta, pero todavía se usa y se valida contra proyectos reales antes de considerarla de producción.

## Qué hace

- Conecta a MySQL/MariaDB y analiza la tabla elegida (`DESCRIBE`, índices únicos, tablas del schema). Botón de "Probar conexión" separado de "Conectar", con indicador de estado (conectando / conectado / error) sin congelar la ventana. Los selectores de tablas (la tabla a analizar y el "FK -> tabla" de cada columna) se pueden escribir para filtrar la lista, sin recorrerla con el scroll.
- Detecta relaciones `{campo}_id → belongsTo`: automático si hay una sola tabla candidata, pregunta si hay ambigüedad (y recuerda la respuesta). El combo "FK -> tabla" de la grilla también permite asignar la relación a mano en **cualquier** columna, no solo las que terminan en `_id` — útil para tablas legadas o con otra convención de nombres. Genera también los `belongsTo` de auditoría (`created_by`/`updated_by`/`deleted_by`) contra el modelo de usuario que configures.
- Genera el patrón completo: `Model.php`, `{Modulo}Service.php`, `{table}Filters.php`, `Store{Modulo}Request.php` / `Update{Modulo}Request.php` + `Validates{Modulo}` trait, `{Modulo}Resource.php` / `{Modulo}RelationResource.php` / `{Modulo}TinyResource.php` (con sus anotaciones `@OA\Schema`), `{table}Controller.php` (con anotaciones `@OA\Get/Post/Put/Delete` por método), `routes/modules/{modulo}.php`, y las interfaces del frontend.
- Documentación Swagger/OpenAPI (`darkaonline/l5-swagger`) lista para generar con `php artisan l5-swagger:generate`: cada Resource declara su propio schema reutilizable y cada método del Controller documenta el envelope real de [[ApiResponse]] (`status`/`message`/`data`), nunca solo una `description` suelta.
- Preview **editable** de cada archivo antes de escribir nada a disco — lo que quede en cada pestaña al confirmar es lo que se escribe. El botón "Ampliar preview ↗" abre el mismo panel en una ventana grande aparte, para editar con más espacio en pantallas chicas.
- Escribe cada archivo en la carpeta real del proyecto (`app/Models/...`, `app/Services/...`, etc.), no en una carpeta plana — elegís la raíz del backend y del frontend por separado.
- La conexión Eloquent (`$connection`) del Model no se pide junto con la BD: sale del proyecto backend. Al elegir la raíz (o con "Analizar proyecto") se listan las conexiones de `config/database.php` y se sugiere la que corresponde a la BD conectada; se puede escribir otra.
- "Analizar proyecto" revisa (de solo lectura) si el backend ya carga `routes/modules/*.php` automáticamente, y sugiere el snippet si falta — nunca edita `RouteServiceProvider`/`bootstrap/app.php` solo.
- El `audit-user.interface.ts` compartido es opcional (checkbox) — pensado para proyectos que ya existen y ya lo tienen.
- Backup manual de la BD conectada (`mysqldump`).
- `Logs → Historial de generación…`: cada módulo generado queda registrado (tabla, # de FKs, # de campos, tiempo transcurrido entre "Analizar" y "Generar archivos", archivos escritos, líneas de código) y se puede exportar a CSV — insumo directo para medir el lead time por módulo (manual vs. herramienta).
- "Analizar proyecto" también detecta si el proyecto destino todavía no tiene las piezas de base del patrón (`AbstractModuleService.php`, `CrudService.php`, `Controller` base con Swagger, `RouteServiceProvider.php`) y ofrece generar las que falten — nunca sobrescribe un archivo que ya exista. `CrudService.php` se genera siempre completo, con auditoría activa: si no existe la tabla `{prefijo}_procesosaudit`, la crea (migración + modelo, con el esquema documentado); si no encuentra una clase `Token` propia del proyecto, usa `Auth::user()` nativo de Laravel en su lugar (equivalente bajo Sanctum), dejado explícito en el código generado.
- Detección de Model/Resource ya existentes en el proyecto, asistida por un modelo entrenado para reconocer el patrón (Model → Filter → Requests → Resource → Service → Controller → ruta) aunque el proyecto use otras carpetas, nombres o prefijos: antes de generar, el diálogo "Model/Resource existentes" propone el mejor candidato y, solo como información, muestra el Filter, los Requests, el Service, el Controller y la ruta que ya existen para ese Model — nunca decide solo, siempre se confirma a mano. Sigue aprendiendo de cada confirmación del desarrollador.

Lo que falta (service Angular completo, parser de migraciones sin ejecutar, relaciones many-to-many, auto-registro de rutas) está en el roadmap.

## Descargar

Cada tag `vX.Y.Z` publica un [Release](https://github.com/Gabngs/ServiceForge/releases) con el `.exe` de Windows listo para usar.

## Correr en local

Para probar cambios sin esperar el `.exe` del workflow de CI:

```bash
./start.sh        # crea/activa .venv, instala deps y levanta la GUI con auto-restart
./start.sh --once # igual, pero corre una sola vez (sin vigilar cambios)
```

PySide6 no soporta hot-reload real de la ventana en caliente — `start.sh` corre
por default con `scripts/dev_watch.py`, que vigila los `.py`/`.j2` bajo `src/`
y, apenas detecta un cambio guardado, cierra la ventana vieja y levanta una
nueva sola (no hace falta parar y volver a correr el script a mano).

Manual, sin el wrapper:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt

python -m pytest -q      # tests
python src/main.py       # abre la GUI (requiere una BD MySQL/MariaDB accesible)
```

## Roadmap

- [x] `{Modulo}Resource.php` / `{Modulo}RelationResource.php` / `{Modulo}TinyResource.php`
- [x] Documentación Swagger/OpenAPI en el Controller y los Resources generados
- [x] Scaffolding del estándar para proyectos que todavía no lo siguen (`AbstractModuleService`, `CrudService` con auditoría, `Controller` base, `RouteServiceProvider`)
- [x] Auto-registro de `routes/modules/{modulo}.php` en el provider (hoy solo se detecta y sugiere, no se edita)
- [ ] Service Angular completo

