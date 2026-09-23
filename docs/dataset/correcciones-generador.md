# Correcciones pendientes del generador (backlog)

Origen: generación de `catalogo_parametrosistema` en **siaw-laravel-backend** (sept. 2026). Una revisión posterior del código generado encontró los defectos de abajo, y luego se ajustaron los criterios.
Este archivo es solo un **registro**; todavía no se implementó nada.
Referencias de estructura real: [estructura-siaw.md](estructura-siaw.md) y [estructura-sireh.md](estructura-sireh.md).

---

## 0. Principio general: primero detectar la estructura del proyecto y después aplicar el patrón

El patrón de servicios (Model → Filter → Requests → Resource → Service → Controller → Route) es **por conveniencia y orden**. No depende de una estructura de carpetas concreta. Un proyecto que ya tiene varios modelos usa su propia estructura, que puede estar fuera del estándar, y el patrón se aplica igual.

Regla:

1. Escanear el proyecto y detectar **dónde** guarda cada tipo de archivo y **cómo** los nombra: carpetas, namespaces, prefijos y sufijos (ver §8).
2. Si hay una estructura existente, generar **dentro de ella**, con sus namespaces y nombres.
3. Usar la estructura estándar del generador **solo** si el proyecto no tiene una propia para ese tipo de archivo.
4. El **modelo se valida junto** con esa estructura: el namespace del modelo, el de los Resources, el del Controller y el `use` de la ruta tienen que ser coherentes entre sí.

Ejemplo real: en SIAW el generador creó estas carpetas propias:

| Tipo | Lo que generó (incorrecto en este proyecto) | Lo que usa el proyecto |
|---|---|---|
| Model | `App\Models\dbcatalogo` | `App\Models\dbsiaw` |
| Requests | `App\Http\Requests\Catalogo\...` | `App\Http\Request\dbsiaw\{tabla}\` (**Request** en singular) |
| Request trait | `App\Http\Requests\Catalogo\Traits\...` | `App\Http\Request\dbsiaw\Traits\{tabla}\Validates{Tabla}` |
| Resources | `App\Http\Resources\Catalogo` | `App\Http\Resources\dbsiaw` |
| Controller | `App\Http\Controllers\Api\Catalogo\...` | `App\Http\Controllers\Api\dbsiaw\{tabla}Controller` |
| Route | `routes/modules/` (nada lo carga) | `routes/{tabla}.php` + registro en `RouteServiceProvider` |

Esas carpetas vacías quedaron en el repo (`app/Models/dbcatalogo`, `app/Http/Requests/Catalogo`, `app/Http/Resources/Catalogo`, `app/Http/Controllers/Api/Catalogo`, `routes/modules`). **No** deben contar como “estructura existente” en el escaneo (ver §8.4).

---

## 1. Soft delete legado (`deleted` en vez de `deleted_at`)

**Defecto:** la tabla tenía la columna `deleted` y el generador asumió `deleted_at` y `deleted_by_id`.

**Comportamiento esperado** (lo decide el esquema real de la tabla, no una suposición):

| Columnas en la tabla | Qué generar |
|---|---|
| `deleted_at` | `use SoftDeletes;` (normal) |
| `deleted` (datetime/nullable) | `use SoftDeletes;` + `const DELETED_AT = 'deleted';` |
| ni `deleted` ni `deleted_at` | sin `SoftDeletes` |
| `deleted_by_id` existe | agregarlo a `$fillable`, crear la relación `deleted_by` y el include en el Filter |
| `deleted_by_id` **no** existe | nada de lo anterior; `destroy` **no** usa `CrudService::delete` (que escribe `deleted_by_id`), sino `$model->delete()` directo |

Aplica también a las reglas `exists` de los Requests: la columna del soft delete del **modelo relacionado** puede ser `deleted` o `deleted_at` (en SIREH se ven las dos: `exists:mysql_dbsip.sip_personal,id,deleted,NULL` y `exists:mysql_dbsip.sip_periodovacacional,id,deleted_at,NULL`).

Frecuencia real: SIAW tiene 10 modelos con `DELETED_AT='deleted'` y SIREH 22. No es un caso raro.

---

## 2. Generación del id (PK `char(32)` sin autoincremento): **opción de generación**

**Defecto:** la PK era `char(32)` sin autoincremento y el Service no generaba el id.

**Decisión:** la generación del id en el Service **no se hardcodea**. Es una **opción de configuración de la generación**, desactivada por defecto porque normalmente no se usa. Opciones propuestas:

- `ninguna` (default): el id lo pone la BD o el modelo.
- `uuid_sin_guiones`: `str_replace('-', '', Str::uuid()->toString())` (char(32)), como `catalogo_parametrosistemaService` en SIAW.
- `uuid`: `Str::uuid()->toString()` (char(36)), como `SolicitudVacacionesService` en SIREH.

Sugerencia: si el análisis de la tabla detecta una PK `char(32)` o `char(36)` sin `AUTO_INCREMENT`, preseleccionar la opción correspondiente, pero dejar que el usuario la cambie.

---

## 3. `$connection` del modelo: la elige el usuario, no se hardcodea

**Defecto:** el modelo salió con `$connection = 'dbsiaw'` cuando la conexión real es `mysql_dbsiaw`.

**Decisión:** la conexión **no se infiere ni se hardcodea** a partir del nombre de la BD. El usuario la declara. El análisis del proyecto **ofrece las opciones** leyendo las claves de `config/database.php` → `connections` (SIAW y SIREH: `mysql`, `mysql_dbsiaw`, `mysql_dbsip`, …).

La conexión elegida se usa en:

- `protected $connection` del modelo;
- las reglas `exists` / `unique` del trait de validación (`Rule::exists('mysql_dbsiaw.catalogo_tiposistema', 'id')`);
- cualquier `DB::connection(...)` del Service.

---

## 4. Modelo: `HasFactory` y sintaxis de imports

- **HasFactory:** agregar `use Illuminate\Database\Eloquent\Factories\HasFactory;` y `use HasFactory, ...;` en el modelo generado. Hoy no se agrega.
  (SIAW: 54 de 91 modelos lo tienen; SIREH: 121 de 124.)
- **Import con `.php`:** se generó `use App\Models\dbsiaw\catalogo_usuario.php;`, que es un error de sintaxis. Los `use` se arman desde el FQCN de la clase y nunca desde la ruta del archivo.

---

## 5. Service: nombre, herencia y persistencia

**Defectos:** se generó `ParametrosistemaService extends AbstractModuleService`, una clase base que no existe en el proyecto.

**Decisión:**

- No extender clases base que el proyecto no tenga. Si se usa una base, el escaneo tiene que confirmar que existe.
- El nombre del Service sigue la convención **detectada** en el proyecto:
  - SIAW: `{tabla}Service` → `catalogo_parametrosistemaService`;
  - SIREH: `{NombreCamelSinPrefijo}Service` → `SolicitudVacacionesService` (para `sip_solicitudvacaciones`).
- Si el usuario decide crear el Service, **se genera y se guarda**. No es un paso opcional que se pueda perder.
- El Service inyecta `CrudService` (existe en ambos repos) y usa `mapUuidsToPkids` para las FK que llegan como UUID.

---

## 6. Usuario de auditoría (`created_by` / `updated_by` / `deleted_by`)

**Defecto:** el Resource usaba `created_by_id` como objeto. Además, la corrección manual asumió `catalogo_usuarioRelationResource`, que **no siempre va a existir**.

**Decisión:** analizar cómo maneja usuarios el proyecto y respetar su patrón. Si no existe, generarlo.

1. **Detectar el modelo de usuario:**
   - relaciones `belongsTo` sobre `created_by_id` / `updated_by_id` en los modelos existentes;
   - modelo `User` (Authenticatable);
   - tabla `catalogo_usuario`.

   Casos reales:
   - SIAW: `App\Models\dbsiaw\catalogo_usuario` (PK `pkid`, `DELETED_AT='deleted'`) y también `App\Models\User` (misma tabla).
   - SIREH: `App\Models\dbsiaw\usuarios` y `App\Models\User` (misma tabla `catalogo_usuario`).
2. **Detectar el nombre de las relaciones de auditoría:** varía incluso dentro de un mismo proyecto.
   - SIAW: `created_by` (con `User` o `catalogo_usuario`), `create_by`, `createdBy`.
   - SIREH: `createdBy` / `created_by`.

   Usar la variante **más frecuente** en el proyecto.
3. **Detectar el Resource de usuario:** buscar `{modeloUsuario}RelationResource`, `{modeloUsuario}Resource` o un Resource con `@mixin` al modelo de usuario.
   - SIAW: `Resources\dbsiaw\catalogo_usuarioRelationResource`.
   - SIREH: `Resources\Siaw\catalogo_usuarioResource`.

   Si no hay nada parecido, **generar** uno mínimo (`id`, `nombre`/`username`), siguiendo la convención de Relation Resources del proyecto.
4. **Detectar cómo se obtiene el usuario autenticado:** en ambos repos, `App\Http\Token::user()` (= `session('user')`), del que se lee `->pkid`.
   - `CrudService::create/update/delete` ya rellena `created_by_id` / `updated_by_id` / `deleted_by_id` con ese valor.
   - Si el proyecto tiene un `CrudService` con esa lógica, **no** duplicarla en el Service generado.
5. **Proyecto recién acoplado**, sin tabla ni modelo de usuario: generar un Resource que referencia un modelo inexistente es difícil de ejecutar. En ese caso:
   - no generar relaciones ni Resources de auditoría;
   - dejar los campos `*_by_id` como escalares;
   - avisar en el log de generación que falta el modelo de usuario.

---

## 7. RelationResources de las FK

**Defecto:** `ParametrosistemaResource` importaba `Catalogo\TiposistemaRelationResource`, que no existe. Habría fallado al serializar.

**Decisión:** para cada relación `belongsTo` que el Resource va a serializar:

1. buscar un Resource existente para el modelo relacionado: `{modelo}RelationResource`, luego `{modelo}RelacionResource` (SIREH usa las dos grafías), luego `{modelo}TinyResource` y por último `{modelo}Resource`;
2. si existe, importarlo desde **su** namespace real;
3. si no existe, **generarlo** con los campos mínimos (`id`, un campo descriptivo, `activo`), en la carpeta de Resources del proyecto y con la convención de sufijo más usada (en ambos repos es `Relation`).
   El caso real fue `catalogo_tiposistemaRelationResource` (`id`, `descripcion`, `orden`, `activo`).

---

## 8. Mapeo de carpetas y nombres (para el matching y para ubicar archivos)

Hoy el matching asistido (modelo persistente) relaciona **Model ↔ Resource**. Hay que extenderlo para que también ubique **carpetas y nombres** de los demás tipos de archivo.

### 8.1 Tipos de archivo a reconocer

| Tipo | Señales de nombre | Señales de contenido |
|---|---|---|
| Model | carpeta `Models/**` | `extends Model` / `Authenticatable`, `$table`, `$connection` |
| Filter | sufijo `Filters` / `Filter` | `extends QueryFilters`, `$allowedFilters`, `$allowedIncludes` |
| Resource | sufijo `Resource` | `extends JsonResource`, `toArray` |
| Relation Resource | sufijo `RelationResource` / `RelacionResource` / `TinyResource` / `LeftResource` | igual que Resource, con pocos campos |
| Base Request | prefijo `Base`, `abstract class` | `extends FormRequest`, `messages()` |
| Store Request | prefijo `Store` | `rules()` con `required` |
| Update Request | prefijo `Update` | `rules()` con `sometimes` |
| Request trait | prefijo `Validates`, carpeta `Traits/` | `trait`, `getRelacionesRules` / `get*Messages` |
| Service | sufijo `Service` | `CrudService` inyectado, `mapUuidsToPkids` |
| Controller | sufijo `Controller` | `use ApiResponse`, `responseSuccess` |
| Route | `routes/*.php`, `routes/modules/*.php` | `Route::apiResource`, `middleware(ApiToken…)` |

### 8.2 Qué se infiere por tipo

- Carpeta **base** (`app/Http/Request` o `app/Http/Requests`).
- **Sub-nivel por conexión o sistema**:
  - SIAW: `dbsiaw`, `Sap`;
  - SIREH: `Sip`, `Siaw`, `Sincro_sip`, y en Filters/Models `dbsip`, `dbsiaw`, `dbsincro`.
- Si existe **sub-carpeta por tabla**: Requests en ambos repos; Resources en SIREH solo para algunos `sip_personal*`.
- Si los traits van en `Traits/{tabla}/`.
- Patrón de **nombre de clase**:
  - `{tabla}` literal (`catalogo_parametrosistema`);
  - `{Accion}{tabla}` (`Storecatalogo_parametrosistemaRequest`);
  - `{Accion}{CamelSinPrefijo}` (`StoreSolicitudVacacionesRequest`).
- Dónde se **registra** la ruta: `RouteServiceProvider` (ambos repos) o un `require` en `api.php`.

### 8.3 Dataset: las variaciones entre proyectos son la señal de entrenamiento

SIAW y SIREH guardan los mismos tipos de archivo con convenciones distintas:

| Variación | SIAW | SIREH |
|---|---|---|
| Carpeta de Requests | `Http/Request` (singular) | `Http/Requests` (plural) |
| Carpeta de rutas | `routes/{tabla}.php` | `routes/modules/{tabla}.php` |
| Nombre del Service | `{tabla}Service` | `{NombreCamelSinPrefijo}Service` |
| Nombre del Request | `Store{tabla}Request` | `Store{NombreCamel}Request` |
| Sub-nivel | nombre de conexión (`dbsiaw`) | nombre de sistema (`Sip`, `Siaw`) |

Estas diferencias **no se resuelven con reglas fijas**: justamente para eso está el dataset. El objetivo es que la red aprenda a reconocer el mismo **rol** (Service, Request, Route, …) aunque cambien la carpeta, el singular/plural, el prefijo o el estilo de nombre. Así el generador puede ubicar y nombrar los archivos en un proyecto que no vio nunca.
Por eso tener **los dos repos juntos** en el dataset aporta más que cada uno por separado: la red ve la misma relación expresada de dos formas.

**Qué aporta cada modelo al dataset:**

- **Pares positivos (modelo → archivo de tipo T)**, con la ruta relativa. Ejemplos:
  - `sip_solicitudvacaciones` → `app/Services/SolicitudVacacionesService.php`;
  - `catalogo_parametrosistema` → `app/Services/catalogo_parametrosistemaService.php`.
- **Negativos duros:** archivos del mismo tipo de otros modelos del mismo proyecto, sobre todo los de nombre parecido (`PersonalMovimientosService` frente a `PersonalMovimientoSueldoService`). También sirven las entradas `*_usado_en` del anexo, que importan el modelo pero no son suyas.

**Features candidatas**, que se suman a las actuales `name_similarity` y `field_jaccard`:

- similitud de nombre **normalizada**: sin prefijo de tabla (`sip_`, `catalogo_`), sin sufijo de rol (`Service`, `Request`, `Controller`, `Resource`), sin prefijo de acción (`Store`, `Update`, `Base`), sin `_` y en minúsculas;
- coincidencia del nombre del modelo con algún **segmento de la ruta** (carpeta `/{tabla}/` en Requests y Resources);
- **señales de contenido**:
  - el archivo importa el modelo (`use`);
  - el modelo lo declara (`$default_filters`);
  - la ruta importa el controller;
- **perfil de estructura del proyecto**: la carpeta más frecuente para cada rol (`Request` o `Requests`, `routes` o `routes/modules`, el sub-nivel). Así, un candidato en la carpeta “habitual” del proyecto suma.

**Para ubicar un archivo nuevo** (no solo emparejar los existentes), el mismo perfil de estructura da la carpeta y el patrón de nombre dominantes por rol. El generador los propone, y usa el estándar solo si el proyecto no tiene ejemplos de ese rol.

Los mapeos completos de SIAW y SIREH están en los anexos YAML de [estructura-siaw.md](estructura-siaw.md#anexo-mapeo-por-modelo) y [estructura-sireh.md](estructura-sireh.md#anexo-mapeo-por-modelo). Se armaron para reconstruir el dataset en una PC que no tiene los repos.
Agregar el dataset nuevo no afecta lo ya entrenado para Model ↔ Resource, que sigue siendo un subconjunto del nuevo: los pares de tipo `resource`.

### 8.4 Ruido que el escaneo debe ignorar

- Carpetas vacías (sin `.php`): son restos de generaciones anteriores.
- Clases que referencian a un modelo pero no son “suyas”. Ejemplos: un Filter de otro modelo que lo importa, o un Controller de reportes que usa 10 modelos.
  Para asignar dueño: primero el **nombre**, después `$default_filters` del modelo, y la referencia por `use` solo como señal secundaria.

---

## 9. Requests

- **Update Request:** se declaraba `$modelId` y no se usaba. No generar variables sin uso.
- **Trait de validación:** las reglas `exists` llevan la conexión explícita (`Rule::exists('{conexion}.{tabla}', 'id')`). Sin ella, Laravel valida contra la conexión por defecto. No se llegó a probar si fallaba, pero así lo hacen todos los módulos del repo.

---

## 10. Controller: paginado como **opción de generación**

**Decisión:** agregar o no `paginate` al `index` es una **opción de configuración**, no algo fijo.

- Si está activa, el `index` sigue el patrón de SIAW:
  - `$request->boolean('paginate')` → `Service::index($paginate)` → `dynamicPaginate()`;
  - respuesta con `meta` (`current_page`, `last_page`, `per_page`, `total`, `from`, `to`).
- Opcional también: `?tiny=true` alterna entre `{tabla}TinyResource` y `{tabla}Resource`.

---

## 11. Rutas

- Archivo en la carpeta de rutas **detectada**:
  - SIAW: `routes/{tabla}.php`;
  - SIREH: `routes/modules/{tabla}.php`.
- Registrarlo donde el proyecto registra las demás. En ambos repos es `RouteServiceProvider::boot()` con `Route::middleware('api')->prefix('api')->group(base_path(...))`.
  Un archivo de rutas que nadie carga es un defecto.
- El middleware de token también se escribe según lo detectado:
  - SIAW: `Route::middleware([ApiToken::class])`;
  - SIREH: `Route::middleware('ApiToken')`, alias en `Kernel.php`.

---

## 12. Interface TypeScript: respetar `interface.ts` (IBaseInterface)

**Defecto:** la plantilla `templates/interfaces.ts.j2` no respeta la documentación de `interface.ts`:

- declara `created_by_id` / `updated_by_id` como `IAuditUser`;
- repite los campos de auditoría en cada interface en vez de extender una base;
- no tiene `IFiltersBase` ni `IPaginateMeta`.

**Forma esperada** (base compartida, se genera una sola vez):

```ts
import { IAuditUser } from "./audit-user.interface";

export interface IPaginateMeta {
    current_page?: number;
    last_page?: number;
    per_page?: number;
    total?: number;
    from?: number;
    to?: number;
}

export interface IFiltersBase {
    tiny?: boolean;
    search?: string;
    activo?: boolean;
    paginate?: boolean;
    per_page?: number;
    page?: number;
    created_by?: string;
    updated_by?: string;
}

export interface IBaseInterface {
    created_at?: string;
    updated_at?: string;
    deleted_at?: string;
    created_by?: IAuditUser;
    updated_by?: IAuditUser;
    deleted_by?: IAuditUser;
    activo?: boolean;
    estado?: string;
    id?: string;
}
```

**Por módulo:**

- `I{Modulo} extends IBaseInterface`: solo los campos propios; las FK van con el alias de la relación y el tipo `I{Rel}Tiny`.
- `I{Modulo}Filters extends IFiltersBase`: los filtros propios, a partir de `$allowedFilters` y los métodos del Filter.
- Se mantienen `I{Modulo}Create`, `I{Modulo}Update` e `I{Modulo}Tiny`.
- Los campos de auditoría se llaman `created_by` / `updated_by` / `deleted_by`, igual que el Resource, no `*_id`.

---

## 13. Logs de generación: versión y formato de fecha

**Hoy** (`src/generador/logs.py`):

- `timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")` → `2026-09-23T15:04:05+00:00`.
- `GenerationLogEntry` **no tiene campo de versión**: no hay forma de saber con qué versión del generador se generó cada módulo.

**Esperado:**

### 13.1 Registrar la versión en cada generación

- Agregar el campo `version: str` a `GenerationLogEntry`.
- En `build_entry()`, llenarlo con `generador.__version__`. Esa versión ya se resuelve sola en [`__init__.py`](../../src/generador/__init__.py) (`_version.py` del build de CI → `git describe --tags --always --dirty` → `0.0.0-dev`). Así queda registrada tanto en el `.exe` de un release (`2.0.1`) como corriendo desde código fuente (`2.0.1-3-g505b331-dirty`).
- Mostrarla también en la tabla de `GenerationLogDialog` (gui.py) y como columna **"Versión"** en `CSV_HEADERS` / `export_csv()`.

**Compatibilidad con logs existentes (importante):** `load_log()` construye cada entrada con `GenerationLogEntry(**item)` y **descarta** las que dan `TypeError`. Si `version` se agrega como campo obligatorio, todas las entradas anteriores desaparecerían del historial al cargarlo.

- Hay que declararlo con valor por defecto, por ejemplo `version: str = "desconocida"`, **después** de los campos obligatorios y antes de `files`.
- Las entradas viejas cargan con ese valor, y las nuevas llevan la versión real.

### 13.2 Formato de fecha

- Fecha en formato estándar **día-mes-año hora:min:seg** y en hora local: `datetime.now().strftime("%d-%m-%Y %H:%M:%S")` → `23-09-2026 10:04:05`.
- Hay que actualizar el comentario del campo (`# ISO 8601 UTC ...`) y el encabezado del CSV (`"Fecha (UTC)"` → `"Fecha"`).
- Las entradas viejas quedan en ISO UTC. Al mostrarlas o exportarlas conviene convertirlas al formato nuevo: si el valor parsea con `datetime.fromisoformat`, se convierte a hora local con `strftime("%d-%m-%Y %H:%M:%S")`. Así el CSV no mezcla dos formatos.

### 13.3 Ejemplo de entrada esperada

```json
{
  "timestamp": "23-09-2026 10:04:05",
  "version": "2.0.1",
  "table": "catalogo_parametrosistema",
  "fk_count": 1,
  "field_count": 6,
  "elapsed_seconds": 84.3,
  "file_count": 9,
  "line_count": 612,
  "files": ["app/Models/dbsiaw/catalogo_parametrosistema.php", "..."]
}
```

---

## 14. Resumen de defectos del caso `catalogo_parametrosistema`

| # | Archivo | Defecto | Corrección / decisión |
|---|---|---|---|
| 1 | Model | `use ...catalogo_usuario.php;` | Imports desde el FQCN (§4) |
| 2 | Model | `$connection = 'dbsiaw'` | Conexión elegida por el usuario entre las de `config/database.php` (§3) |
| 3 | Model | soft delete en `deleted_at`, pero la columna es `deleted` | `DELETED_AT` según el esquema (§1) |
| 4 | Model | `deleted_by_id` inexistente en fillable y relación | Solo si la columna existe (§1) |
| 5 | Model | sin `HasFactory` | Agregar (§4) |
| 6 | Service | `extends AbstractModuleService` (no existe) | Sin base inexistente; nombre según convención (§5) |
| 7 | Service | no generaba el id char(32) | Opción de generación (§2) |
| 8 | Service | `destroy` con `CrudService::delete` sin `deleted_by_id` | `delete()` directo si falta la columna (§1) |
| 9 | Resource | `TiposistemaRelationResource` no existe | Buscar o generar el RelationResource (§7) |
| 10 | Resource | `created_by_id` como objeto | Relación + Resource de usuario detectados (§6) |
| 11 | Request | `$modelId` sin usar | No generarlo (§9) |
| 12 | Trait | `exists` sin conexión | Conexión explícita (§9) |
| 13 | Controller | sin `paginate` | Opción de generación (§10) |
| 14 | Route | en `routes/modules/` sin cargar | Carpeta y registro detectados (§11) |
| 15 | Estructura | namespaces y carpetas propios del generador | Detectar la estructura del proyecto (§0, §8) |
| 16 | Interface TS | no sigue `IBaseInterface` | Plantilla nueva (§12) |
| 17 | Logs | no registra la versión; fecha ISO en UTC | Campo `version` (con default para logs viejos) en entrada, diálogo y CSV + `dd-mm-aaaa HH:mm:ss` local (§13) |

Los archivos que se consideraron correctos fueron:

- el Controller, al que solo le faltaba `paginate`;
- los Requests, con una variable sin usar;
- el Filter: el filtro por `tipo_sistema_id` (UUID → pkid) estaba bien, y se agregaron los includes de auditoría por consistencia.
