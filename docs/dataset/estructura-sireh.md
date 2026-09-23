# Estructura del backend SIREH (sip-laravel-backend)

Mapa de **niveles de carpetas, convenciones de nombres y ubicación de archivos** de SIREH (repo `sip-laravel-backend`). Sirve para:

1. que el generador ubique cada archivo dentro de la estructura propia del proyecto (ver [correcciones-generador.md §0 y §8](correcciones-generador.md));
2. **actualizar el dataset del matching** en una PC que no tiene el repo, con el anexo YAML del final.

| Dato | Valor |
|---|---|
| Ruta en la PC de origen | `C:\Users\programador01\Documents\visual code\sip-laravel-backend` |
| Commit escaneado | `08af16ce` (22-09-2026) |
| Stack | PHP ^8.1 · Laravel ^10.10 · `essa/api-tool-kit` ^2.1 |
| Conexiones (`config/database.php`) | `mysql` (BD de sincronización, `dbsincro`), `mysql_dbsiaw`, `mysql_dbsip`, `pgsql`, `sqlsrv`, `sqlite` |
| Modelos escaneados | 124 (95 `dbsip`, 20 `dbsiaw`, 8 `dbsincro`, 1 `User`) |

**Diferencia clave con SIAW:** los mismos roles se guardan en carpetas con otro nombre, y los Requests y Services usan CamelCase sin prefijo. Estas variaciones son justo lo que el dataset tiene que enseñarle a la red: reconocer el mismo rol en estructuras distintas (ver [correcciones-generador.md §8.3](correcciones-generador.md#83-dataset-las-variaciones-entre-proyectos-son-la-señal-de-entrenamiento)).

| Concepto | SIAW | SIREH |
|---|---|---|
| Carpeta de Requests | `Http/Request` (singular) | `Http/Requests` (plural) |
| Sub-nivel de Requests/Resources/Controllers | `dbsiaw` (nombre de conexión) | `Sip`, `Siaw`, `Sincro_sip` (nombre de sistema) |
| Sub-nivel de Models/Filters | `dbsiaw` | `dbsip`, `dbsiaw`, `dbsincro` |
| Nombre del Request | `Store{tabla}Request` | `Store{NombreCamel}Request` |
| Nombre del Service | `{tabla}Service` | `{NombreCamel}Service` |
| Carpeta de rutas | `routes/{tabla}.php` | `routes/modules/{tabla}.php` |
| Middleware de token | `[ApiToken::class]` | `'ApiToken'` (alias en `Kernel.php`) |
| Relación de auditoría | `created_by` | `createdBy` o `created_by` |

`{NombreCamel}` es la tabla sin prefijo `sip_`, en StudlyCase y con palabras separadas a criterio: `sip_solicitudvacaciones` → `SolicitudVacaciones`, `sip_personalmovimientosconsumo` → `Personalmovimientosconsumo`. **No es derivable de forma determinística**: el matching tiene que aprender la asociación, por eso está el anexo.

---

## 1. Árbol de niveles (solo lo relevante para el patrón)

```
app/
├── Models/
│   ├── User.php                          Authenticatable, tabla catalogo_usuario, conexión mysql_dbsiaw
│   ├── dbsip/{tabla}.php                 ← modelo estándar (95)      conexión mysql_dbsip
│   ├── dbsiaw/{tabla}.php                ← tablas de SIAW (20)       conexión mysql_dbsiaw
│   │   └── usuarios.php                  modelo de usuario para auditoría (tabla catalogo_usuario)
│   └── dbsincro/{tabla}.php              ← BD de sincronización (8)  conexión mysql (bitacora_*, pl_*, int_*)
├── Filters/
│   ├── dbsip/{tabla}Filters.php          (50)
│   ├── dbsiaw/{tabla}Filters.php         (4, incluye UserFilters)
│   └── dbsincro/{tabla}Filters.php       (2)
├── Observers/UserActionsObserver.php     lo registran 47 modelos en boot(): self::observe(UserActionsObserver::class)
├── Http/
│   ├── Controllers/
│   │   ├── Controller.php
│   │   └── Api/
│   │       ├── Sip/{tabla}Controller.php          ← PATRÓN (82), p. ej. sip_solicitudvacacionesController
│   │       ├── Sip/{Nombre}Controller.php         fuera de patrón: CommandController, ReporteHorariosAuditController, ...
│   │       ├── Sip/Traits/                        traits de controller (ResolvesAuditoraTiendas)
│   │       ├── Siaw/{tabla}Controller.php         tablas de SIAW expuestas en SIREH
│   │       ├── Sincro_sip/{tabla}Controller.php
│   │       ├── Reports/  Logs/  Sun/  Sig/  SempiTerno/  api_externa/
│   │       └── {nombre}Controller.php             raíz: usuariosController, downloadController, testController
│   ├── Requests/                         ← "Requests" en PLURAL
│   │   └── Sip/
│   │       ├── {tabla}/                              ← PATRÓN ACTUAL (carpeta por tabla)
│   │       │   ├── Store{NombreCamel}Request.php     extends FormRequest (sin clase Base), use Validates{NombreCamel}
│   │       │   ├── Update{NombreCamel}Request.php
│   │       │   └── {Accion}{NombreCamel}Request.php  Bulk, Autorizar, UpdateEstado, Export, Cerrar...
│   │       ├── Traits/{tabla}/Validates{NombreCamel}.php   get{NombreCamel}Messages(), getBulkMessages(), ...
│   │       ├── Traits/Validates{NombreCamel}.php     ← LEGADO: trait plano sin carpeta
│   │       ├── Base{NombreCamel}Request.php          ← LEGADO: plano (BasePeriodoEstandarRequest, BasePersonalPivotRequest, ...)
│   │       └── {Store|Update}{NombreCamel}Request.php ← LEGADO: plano
│   ├── Resources/
│   │   ├── Sip/{tabla}Resource.php           ← PATRÓN (121 en una sola carpeta)
│   │   ├── Sip/{tabla}RelationResource.php
│   │   ├── Sip/{tabla}RelacionResource.php   variante de grafía (4)
│   │   ├── Sip/{tabla}{Variante}Resource.php Show, Pendientes, Left, Tiny, Data
│   │   ├── Siaw/                             resources de tablas SIAW (catalogo_usuarioResource, catalogo_tiendaRelacionResource, ...)
│   │   ├── Sincro_sip/
│   │   ├── Sempiterno/                       resources para la API de consulta externa ({tabla}DataResource)
│   │   └── {tabla}/{tabla}Resource.php       ← FUERA DE PATRÓN: carpeta por tabla (7: sip_personal, sip_personalmovimiento*)
│   ├── Middleware/ApiToken.php, ApiExternalToken.php
│   └── Token.php                         Token::user() = session('user') → ->pkid
├── Services/
│   ├── CrudService.php                   create/update/delete/restore/bulkInsert/find/getAll + mapUuidsToPkids(+Bulk)
│   ├── {NombreCamel}Service.php          ← PATRÓN: SolicitudVacacionesService, PeriodoVacacionalService, ...
│   └── Reportes/{Nombre}Service.php
├── Functions/Helpers/                    HelpersGeneral, HelpersPlanilla, HelpersCalcularTiempos
├── Exports/{Area}/  Imports/  Jobs/{Area}/  Mail/  Constants/  Enums/
routes/
├── api.php                               legado: ~348 rutas en línea (Route::middleware('ApiToken')->...)
├── modules/{tabla}.php                   ← PATRÓN: un archivo por módulo (21)
└── modules/{nombre}.php                  sin prefijo: tardanzas.php, consultaMaestros.php, tiendacargo.php, terminalesbiometricos.php
app/Providers/RouteServiceProvider.php    ← registra CADA routes/modules/*.php con middleware('api')->prefix('api')
```

---

## 2. Convenciones de nombres (patrón actual)

Con `{tabla}` = `sip_solicitudvacaciones` y `{NombreCamel}` = `SolicitudVacaciones`:

| Tipo | Namespace | Clase | Archivo |
|---|---|---|---|
| Model | `App\Models\dbsip` | `{tabla}` | `app/Models/dbsip/{tabla}.php` |
| Filter | `App\Filters\dbsip` | `{tabla}Filters` | `app/Filters/dbsip/{tabla}Filters.php` |
| Store Request | `App\Http\Requests\Sip\{tabla}` | `Store{NombreCamel}Request` | `app/Http/Requests/Sip/{tabla}/Store{NombreCamel}Request.php` |
| Update Request | ídem | `Update{NombreCamel}Request` | `.../{tabla}/Update{NombreCamel}Request.php` |
| Request trait | `App\Http\Requests\Sip\Traits\{tabla}` | `Validates{NombreCamel}` | `app/Http/Requests/Sip/Traits/{tabla}/Validates{NombreCamel}.php` |
| Resource | `App\Http\Resources\Sip` | `{tabla}Resource` | `app/Http/Resources/Sip/{tabla}Resource.php` |
| Relation Resource | ídem | `{tabla}RelationResource` | `app/Http/Resources/Sip/{tabla}RelationResource.php` |
| Service | `App\Services` | `{NombreCamel}Service` | `app/Services/{NombreCamel}Service.php` |
| Controller | `App\Http\Controllers\Api\Sip` | `{tabla}Controller` | `app/Http/Controllers/Api/Sip/{tabla}Controller.php` |
| Route | — | — | `routes/modules/{tabla}.php` + entrada en `RouteServiceProvider::boot()` |

Para tablas de SIAW usadas en SIREH, se cambia `dbsip` por `dbsiaw` y `Sip` por `Siaw`, y la conexión es `mysql_dbsiaw`.

Sufijos de Resource que aparecen en el repo: base `Resource` (110), `RelationResource` (10), `RelacionResource` (4), `ShowResource` (3), `PendientesResource` (2), `LeftResource`, `DataResource`, `TinyResource` (1 cada uno).

---

## 3. Particularidades de datos que el generador debe respetar

### 3.1 Doble identificador `pkid` + `id`

- Es igual que en SIAW: `pkid` int es el destino de las FK e `id` UUID es lo que se expone. La mayoría de los modelos declaran `$primaryKey = 'id'` y `$incrementing = false` (99 modelos).
- 34 modelos incluyen `pkid` en `$fillable`.
- En `getRouteKeyName()` se usa `id`.
- El formato del UUID es **mixto**:
  - `SolicitudVacacionesService` usa `Str::uuid()->toString()` (con guiones);
  - los Filters de `sip_personal` y `catalogo_tienda` hacen `str_replace('-', '', $value)`, porque esas tablas guardan el id sin guiones.

  Por eso la generación del id es **opción del generador** (ver correcciones §2).
- El Service convierte UUID → pkid con `CrudService::mapUuidsToPkids` / `mapUuidsToPkidsBulk` y `protected array $uuidMapping`.

### 3.2 Soft delete

- `SoftDeletes` con `deleted_at`: 58 modelos.
- `SoftDeletes` + `const DELETED_AT = 'deleted'`: **21 modelos**:
  - de SIAW: `catalogo_empresa`, `catalogo_empresatienda`, `catalogo_parametrosistema`, `catalogo_tienda`, `catalogo_tiposistema`;
  - de SIREH: `sip_personal`, `sip_personalmovimiento*`, `sip_multitabla*`, `sip_personalcargos`, `sip_regimenlaboral`, `sip_tipomovimiento`.
- Sin soft delete: 44.
- **Ninguno** de los 21 con `deleted` tiene `deleted_by_id`.
- Las reglas `exists` indican la columna de borrado del modelo relacionado: `exists:mysql_dbsip.sip_personal,id,deleted,NULL` y `exists:mysql_dbsip.sip_periodovacacional,id,deleted_at,NULL`.

### 3.3 Auditoría y usuario

- Columnas en `$fillable`:
  - `created_by_id, updated_by_id`: 62 modelos;
  - con `deleted_by_id` además: 16;
  - solo `created_by_id`: 7;
  - ninguna: 38.
- `CrudService` rellena `*_by_id` con `Token::user()->pkid`. Tiene además `restore()` y `getAll($modelClass, $paginate)`.
- 47 modelos registran `UserActionsObserver` en `boot()`.
- Modelo de usuario:
  - `App\Models\dbsiaw\usuarios` (tabla `catalogo_usuario`, conexión `mysql_dbsiaw`);
  - `App\Models\User` (misma tabla).
- Nombre de la relación:

  | Relación | Destino | Modelos |
  |---|---|---|
  | `createdBy` / `updatedBy` / `deletedBy` | `usuarios` | módulos nuevos, p. ej. `sip_solicitudvacaciones` |
  | `created_by` / `updated_by` / `deleted_by` | `User` o `usuarios` | el resto |

- Resource de usuario: `App\Http\Resources\Siaw\catalogo_usuarioResource`. **No existe** `catalogo_usuarioRelationResource` en SIREH; es justo el caso de “no dar por hecho el nombre” (correcciones §6).
- Fechas en los Resources: helper `dateTimeFormat($this->created_at)` de essa/api-tool-kit. El formato sale de `config/api-tool-kit.php` → `datetime_format` (`Y-m-d H:i:s`). SIAW, en cambio, usa `Carbon::parse(...)->format(...)` en línea.

### 3.4 Filters

- Como en SIAW: `Filterable` en el modelo + `$default_filters`, y los Filters extienden `QueryFilters`.
- Los métodos por FK convierten UUID → pkid. Si no encuentran el registro, devuelven `whereRaw('0 = 1')`.
- `CrudService::getAll()` usa `useFilters()` y luego `dynamicPaginate()` o `get()`.

### 3.5 Controller

- `use ApiResponse;`, Service inyectado con *constructor property promotion* (`private XService $xService`).
- Muchos controllers tienen endpoints extra además del `apiResource`: `bulk`, `updateEstado`, `autorizar`, `descargarFormato`, …

### 3.6 Rutas

```php
// routes/modules/{tabla}.php
Route::middleware('ApiToken')->group(function () {
    Route::post('{tabla}/bulk', [{tabla}Controller::class, 'bulk']);   // extras ANTES del apiResource
    Route::apiResource('{tabla}', {tabla}Controller::class)
        ->parameters(['{tabla}' => '{tabla}']);
});
```

```php
// app/Providers/RouteServiceProvider.php → boot() → $this->routes(...)
Route::middleware('api')->prefix('api')->group(base_path('routes/modules/{tabla}.php'));
```

`RouteServiceProvider` tiene hoy 23 registros. El resto de los módulos siguen en línea en `routes/api.php`.

---

## 4. Casos fuera de patrón (reconocer, no imitar)

| Caso | Dónde | Cómo reconocerlo |
|---|---|---|
| Resources en carpeta por tabla | `Resources/sip_personal/`, `Resources/sip_personalmovimiento{cargo,ingresocese,sueldo,tienda,turno}/`, `Resources/sip_personalprocesoadministrativo/` | `App\Http\Resources\{tabla}\{tabla}Resource` |
| Requests planos con clase Base | `Requests/Sip/Base{NombreCamel}Request.php` + `Store/Update` planos | sin sub-carpeta por tabla |
| Requests sin sufijo `Request` | `StoreMultiTablaDetalle`, `UpdateMultiTablaDetalle` | clase `extends FormRequest` sin sufijo |
| Traits planos | `Requests/Sip/Traits/Validates{NombreCamel}.php` | sin sub-carpeta por tabla |
| Services con nombre inconsistente | `PersonalmovimientosconsumoService` (sin Camel interno), `PersonalMovimientoSueldoDetalle` (sin sufijo `Service`), `CatalogoParametroSistemaService` / `CatalogoTiendaService` (con prefijo `Catalogo`) | sufijo `Service` o archivo en `app/Services` |
| Controllers no CRUD en `Api/Sip` | `CommandController`, `ReporteHorariosAuditController`, `planillaMasivacusppController`, … | nombre sin `{tabla}` |
| Rutas de módulo sin prefijo de tabla | `routes/modules/tardanzas.php`, `consultaMaestros.php`, `tiendacargo.php`, `terminalesbiometricos.php` | nombre de área, no de tabla |
| Tablas `dbsincro` | `Models/dbsincro/*` con conexión `mysql` (no `mysql_dbsincro`) | la conexión no sigue el patrón `mysql_{bd}`: **por eso la conexión la elige el usuario** |

---

## 5. Regla de ubicación para una tabla nueva `{tabla}` en SIREH

1. Model → `app/Models/dbsip/{tabla}.php`, con la `$connection` que elija el usuario (normalmente `mysql_dbsip`), `HasFactory`, `Filterable`, `SoftDeletes` según las columnas.
2. Filter → `app/Filters/dbsip/{tabla}Filters.php`.
3. Requests → `app/Http/Requests/Sip/{tabla}/{Store|Update}{NombreCamel}Request.php` + `app/Http/Requests/Sip/Traits/{tabla}/Validates{NombreCamel}.php`.
4. Resources → `app/Http/Resources/Sip/{tabla}Resource.php` (+ `{tabla}RelationResource`).
5. Service → `app/Services/{NombreCamel}Service.php`.
6. Controller → `app/Http/Controllers/Api/Sip/{tabla}Controller.php`.
7. Route → `routes/modules/{tabla}.php` + registro en `RouteServiceProvider`.

---

## Anexo: mapeo por modelo

Generado escaneando el repo en el commit `08af16ce`. Usa los mismos criterios que el anexo de [estructura-siaw.md](estructura-siaw.md#anexo-mapeo-por-modelo).

- `service` / `controller`: los que coinciden por nombre, normalizando (sin `sip_`/`catalogo_`, sin `_`, en minúsculas). Así, `SolicitudVacacionesService` se asocia a `sip_solicitudvacaciones`.
- `*_usado_en`: archivos que importan el modelo pero no son sus dueños.
- `observer: true`: el modelo registra `UserActionsObserver`.

Pocos modelos tienen `service` propio (31 de 124), porque muchos Services agrupan varios modelos (`PersonalMovimientosService`, …). Esa relación aparece en `service_usado_en`.

```yaml
- model: User
  path: app/Models/User.php
  connection: mysql_dbsiaw
  table: catalogo_usuario
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: const deleted sin trait SoftDeletes
  has_factory: true
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Sip/sip_personalmodificacionsolicitudController.php, app/Http/Controllers/Auth/RegisterController.php]
  routes: [routes/api.php]
- model: actualizacion_archivos
  path: app/Models/dbsiaw/actualizacion_archivos.php
  connection: mysql_dbsiaw
  table: actualizacion_archivos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Siaw/actualizacionSunController.php]
  routes: [routes/api.php]
- model: actualizacion_terminales
  path: app/Models/dbsiaw/actualizacion_terminales.php
  connection: mysql_dbsiaw
  table: actualizacion_terminales
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Siaw/actualizacionSunController.php]
  routes: [routes/api.php]
- model: actualizacion_tiendas
  path: app/Models/dbsiaw/actualizacion_tiendas.php
  connection: mysql_dbsiaw
  table: actualizacion_tiendas
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Siaw/actualizacionSunController.php]
  routes: [routes/api.php]
- model: actualizacion_transacciones
  path: app/Models/dbsiaw/actualizacion_transacciones.php
  connection: mysql_dbsiaw
  table: actualizacion_transacciones
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Siaw/actualizacionSunController.php]
  routes: [routes/api.php]
- model: auditlog_logentry
  path: app/Models/dbsiaw/auditlog_logentry.php
  connection: mysql_dbsiaw
  table: auditlog_logentry
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Logs/sip_logsasistenciaController.php, app/Http/Controllers/Api/Logs/sip_logspersonalController.php, app/Http/Controllers/Api/Sip/ReporteModificacionesAsistenciaController.php]
  routes: [routes/api.php]
- model: auth_permission
  path: app/Models/dbsiaw/auth_permission.php
  connection: mysql_dbsiaw
  table: auth_permission
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Sip/sip_tipolegajosController.php]
  routes: [routes/api.php]
- model: catalogo_articulos
  path: app/Models/dbsiaw/catalogo_articulos.php
  connection: mysql_dbsiaw
  table: catalogo_articulos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  filter: [app/Filters/dbsiaw/catalogo_articulosFilters.php]
  controller_usado_en: [app/Http/Controllers/Api/SempiTerno/consulta_articulosController.php]
  routes: [routes/api.php]
- model: catalogo_empresa
  path: app/Models/dbsiaw/catalogo_empresa.php
  connection: mysql_dbsiaw
  table: catalogo_empresa
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: true
  auditoria: []
  relaciones:
    - catalogo_tienda: belongsToMany catalogo_tienda
  resources:
    - app/Http/Resources/Siaw/catalogo_empresaRelationResource.php
    - app/Http/Resources/Siaw/catalogo_empresaResource.php
  requests:
    - app/Http/Requests/Sip/sip_personalboletabeneficios/GenerarMacroCtsRequest.php
    - app/Http/Requests/Sip/sip_personalboletavacaciones/GenerarMacroPlanillaRequest.php
  service_usado_en: [app/Services/PeriodoVacacionalService.php, app/Services/SolicitudVacacionesService.php]
  controller_usado_en: [app/Http/Controllers/Api/Logs/sip_logspersonalController.php, app/Http/Controllers/Api/Reports/sip_empresasreportsController.php, app/Http/Controllers/Api/Reports/sip_personalasistenciareportsController.php, app/Http/Controllers/Api/Reports/sip_personaldescuentosreportsController.php, ...]
  routes: [routes/api.php]
- model: catalogo_empresatienda
  path: app/Models/dbsiaw/catalogo_empresatienda.php
  connection: mysql_dbsiaw
  table: catalogo_empresatienda
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: true
  auditoria: []
  service_usado_en: [app/Services/CatalogoEmpresaTiendaService.php, app/Services/PersonalBoletaBeneficiosService.php, app/Services/PersonalBoletaVacacionesService.php, app/Services/ProcesarCtsService.php, ...]
  controller_usado_en: [app/Http/Controllers/Api/Reports/sip_empresasreportsController.php, app/Http/Controllers/Api/Reports/sip_personalasistenciareportsController.php, app/Http/Controllers/Api/Reports/sip_personaldescuentosreportsController.php, app/Http/Controllers/Api/Reports/sip_personalreportsController.php, ...]
  routes: [routes/api.php, routes/modules/sip_personalboletabeneficios.php]
- model: catalogo_parametrosistema
  path: app/Models/dbsiaw/catalogo_parametrosistema.php
  connection: mysql_dbsiaw
  table: catalogo_parametrosistema
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  relaciones:
    - user_created: hasOne User (pkid, created_by_id)
    - user_updated: hasOne User (pkid, updated_by_id)
    - tipo_sistema: hasOne catalogo_tiposistema (pkid, tipo_sistema_id)
  filter: [app/Filters/dbsiaw/catalogo_parametrosistemaFilters.php]
  resources:
    - app/Http/Resources/Siaw/catalogo_parametrosistemaResource.php
  service_usado_en: [app/Services/AsignacionFamiliarService.php, app/Services/CatalogoParametroSistemaService.php, app/Services/PersonalmovimientosconsumoService.php, app/Services/TardanzasService.php]
  controller: [app/Http/Controllers/Api/Siaw/catalogo_parametrosistemaController.php]
  routes: [routes/api.php, routes/modules/sip_personalboletabeneficios.php]
- model: catalogo_tienda
  path: app/Models/dbsiaw/catalogo_tienda.php
  connection: mysql_dbsiaw
  table: catalogo_tienda
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: true
  auditoria: []
  relaciones:
    - catalogo_empresa: belongsToMany catalogo_empresa
  resources:
    - app/Http/Resources/Siaw/catalogo_tiendaRelacionResource.php
    - app/Http/Resources/Siaw/catalogo_tiendaResource.php
    - app/Http/Resources/Siaw/catalogo_tienda_dnsResource.php
    - app/Http/Resources/Siaw/catalogo_tiendaturnosResource.php
  requests:
    - app/Http/Requests/Sip/StoreAuditorasTiendasRequest.php
    - app/Http/Requests/Sip/sip_personalboletabeneficios/GenerarMacroCtsRequest.php
    - app/Http/Requests/Sip/sip_personalboletavacaciones/GenerarMacroPlanillaRequest.php
  service_usado_en: [app/Services/AuditorasService.php, app/Services/AuditorasTiendasService.php, app/Services/CatalogoTiendaService.php, app/Services/EstandarPersonalService.php, ...]
  controller: [app/Http/Controllers/Api/Siaw/catalogo_tiendaController.php]
  routes: [routes/api.php, routes/modules/sip_personalboletabeneficios.php, routes/modules/sip_personalmovimientocargo.php, routes/modules/terminalesbiometricos.php, ...]
- model: catalogo_tienda_dns
  path: app/Models/dbsiaw/catalogo_tienda_dns.php
  connection: mysql_dbsiaw
  table: catalogo_tienda_dns
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: []
  resources:
    - app/Http/Resources/Siaw/catalogo_tienda_dnsResource.php
  controller: [app/Http/Controllers/Api/Siaw/catalogo_tienda_dnsController.php]
  routes: [routes/api.php]
- model: catalogo_tiendaturnos
  path: app/Models/dbsiaw/catalogo_tiendaturnos.php
  connection: mysql_dbsiaw
  table: catalogo_tiendaturnos
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  resources:
    - app/Http/Resources/Siaw/catalogo_tiendaturnosResource.php
  service_usado_en: [app/Services/EstandarPersonalService.php]
  controller_usado_en: [app/Http/Controllers/Api/Logs/sip_logspersonalController.php, app/Http/Controllers/Api/Sip/sip_personalmodificacionsolicitudController.php, app/Http/Controllers/Api/Sip/sip_personaltiemposasistenciaController.php, app/Http/Controllers/Api/Sip/sip_tiendacargoController.php]
  routes: [routes/api.php, routes/modules/tiendacargo.php]
- model: catalogo_tiendazona
  path: app/Models/dbsiaw/catalogo_tiendazona.php
  connection: mysql_dbsiaw
  table: catalogo_tiendazona
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  service_usado_en: [app/Services/PersonalTiemposAsistenciaService.php, app/Services/PersonalmovimientosconsumoService.php]
  controller_usado_en: [app/Http/Controllers/Api/SempiTerno/consulta_personalController.php, app/Http/Controllers/Api/Sincro_sip/sip_personalmovimientotiendaController.php, app/Http/Controllers/Api/Sip/sip_personalmovimientotiendaController.php]
  routes: [routes/api.php]
- model: catalogo_tiposistema
  path: app/Models/dbsiaw/catalogo_tiposistema.php
  connection: mysql_dbsiaw
  table: catalogo_tiposistema
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: true
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Siaw/catalogo_parametrosistemaController.php]
  routes: [routes/api.php]
- model: catalogo_turnos
  path: app/Models/dbsiaw/catalogo_turnos.php
  connection: mysql_dbsiaw
  table: catalogo_turnos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
- model: catalogo_ubigeo
  path: app/Models/dbsiaw/catalogo_ubigeo.php
  connection: mysql_dbsiaw
  table: catalogo_ubigeo
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  resources:
    - app/Http/Resources/Siaw/catalogo_ubigeoResource.php
    - app/Http/Resources/Siaw/catalogo_ubigeofromparentResource.php
  controller: [app/Http/Controllers/Api/Siaw/catalogo_ubigeoController.php]
  routes: [routes/api.php, routes/web.php]
- model: catalogo_zona
  path: app/Models/dbsiaw/catalogo_zona.php
  connection: mysql_dbsiaw
  table: catalogo_zona
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  resources:
    - app/Http/Resources/Siaw/catalogo_zonaResource.php
  service_usado_en: [app/Services/PersonalTiemposAsistenciaService.php, app/Services/PersonalmovimientosconsumoService.php]
  controller_usado_en: [app/Http/Controllers/Api/SempiTerno/consulta_personalController.php, app/Http/Controllers/Api/Sincro_sip/sip_personalmovimientotiendaController.php, app/Http/Controllers/Api/Sip/sip_personalcentralController.php, app/Http/Controllers/Api/Sip/sip_personalmovimientotiendaController.php, ...]
  routes: [routes/api.php]
- model: django_content_type
  path: app/Models/dbsiaw/django_content_type.php
  connection: mysql_dbsiaw
  table: django_content_type
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Logs/sip_logsasistenciaController.php, app/Http/Controllers/Api/Logs/sip_logspersonalController.php, app/Http/Controllers/Api/Sip/ReporteModificacionesAsistenciaController.php]
  routes: [routes/api.php]
- model: usuarios
  path: app/Models/dbsiaw/usuarios.php
  connection: mysql_dbsiaw
  table: catalogo_usuario
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: true}
  soft_delete: no
  has_factory: false
  auditoria: [created_by_id]
  relaciones:
    - sip_personal: hasOne sip_personal (codigo, idusuario)
  filter: [app/Filters/dbsiaw/UserFilters.php]
  controller: [app/Http/Controllers/Api/usuariosController.php]
  routes: [routes/api.php]
- model: bitacora_procesos_sip
  path: app/Models/dbsincro/bitacora_procesos_sip.php
  connection: mysql
  table: bitacora_procesos_sip
  pk: {name: pkid, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  filter: [app/Filters/dbsincro/bitacora_procesos_sipFilters.php]
  resources:
    - app/Http/Resources/Sincro_sip/bitacora_procesos_sipResource.php
  controller: [app/Http/Controllers/Api/Sincro_sip/bitacora_procesos_sipController.php]
  routes: [routes/api.php]
- model: bitacora_sincronizacion
  path: app/Models/dbsincro/bitacora_sincronizacion.php
  connection: mysql
  table: bitacora_sincronizacion
  pk: {name: pkid, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  filter: [app/Filters/dbsincro/bitacora_sincronizacionFilters.php]
  resources:
    - app/Http/Resources/Sincro_sip/bitacora_sincronizacionResource.php
  controller: [app/Http/Controllers/Api/Sincro_sip/bitacora_sincronizacionController.php]
  routes: [routes/api.php]
- model: int_motivoscese
  path: app/Models/dbsincro/int_motivoscese.php
  connection: mysql
  table: int_motivoscese
  pk: {name: codper, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
- model: pl_cargos
  path: app/Models/dbsincro/pl_cargos.php
  connection: mysql
  table: pl_cargos
  pk: {name: codper, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
- model: pl_descuentos
  path: app/Models/dbsincro/pl_descuentos.php
  connection: mysql
  table: pl_descuentos
  pk: {name: iddescuentos, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
- model: pl_movimientos
  path: app/Models/dbsincro/pl_movimientos.php
  connection: mysql
  table: pl_movimientos
  pk: {name: idmovimientos, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
- model: pl_personal
  path: app/Models/dbsincro/pl_personal.php
  connection: mysql
  table: pl_personal
  pk: {name: codper, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
- model: pl_tiendas
  path: app/Models/dbsincro/pl_tiendas.php
  connection: mysql
  table: pl_tiendas
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
- model: SipPersonalMovimientoContableTemp
  path: app/Models/dbsip/SipPersonalMovimientoContableTemp.php
  connection: mysql_dbsip
  table: sip_personalmovimientocontable_temp
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
- model: sip_anios
  path: app/Models/dbsip/sip_anios.php
  connection: mysql_dbsip
  table: sip_anios
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  filter: [app/Filters/dbsip/sip_aniosFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_aniosResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_aniosController.php]
  routes: [routes/api.php]
- model: sip_aportespensionarios
  path: app/Models/dbsip/sip_aportespensionarios.php
  connection: mysql_dbsip
  table: sip_aportespensionarios
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - user_deleted: belongsTo User (deleted_by_id, pkid)
  filter: [app/Filters/dbsip/sip_aportespensionariosFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_aportespensionariosResource.php
  requests:
    - app/Http/Requests/Sip/Traits/sip_aportespensionarios/ValidatesAportesPensionarios.php
    - app/Http/Requests/Sip/sip_aportespensionarios/StoreAportesPensionariosRequest.php
    - app/Http/Requests/Sip/sip_aportespensionarios/UpdateAportesPensionariosRequest.php
  service: [app/Services/AportesPensionariosService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_aportespensionariosController.php]
  routes: [routes/api.php, routes/modules/sip_aportespensionarios.php]
- model: sip_auditoras
  path: app/Models/dbsip/sip_auditoras.php
  connection: mysql_dbsip
  table: sip_auditoras
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - sip_personal: belongsTo sip_personal (personal_id, pkid)
    - catalogo_tienda: belongsTo catalogo_tienda (tienda_id, pkid)
    - sip_auditoras_tiendas: hasMany sip_auditoras_tiendas (auditora_id, pkid)
    - created_by: belongsTo User (created_by_id, pkid)
    - updated_by: belongsTo User (updated_by_id, pkid)
    - deleted_by: belongsTo User (deleted_by_id, pkid)
  filter: [app/Filters/dbsip/sip_auditorasFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_auditorasRelationResource.php
    - app/Http/Resources/Sip/sip_auditorasResource.php
    - app/Http/Resources/Sip/sip_auditorasTiendasResource.php
  service: [app/Services/AuditorasService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_auditorasController.php]
  routes: [routes/modules/sip_auditoras.php]
- model: sip_auditoras_tiendas
  path: app/Models/dbsip/sip_auditoras_tiendas.php
  connection: mysql_dbsip
  table: sip_auditoras_tiendas
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - sip_auditoras: belongsTo sip_auditoras (auditora_id, pkid)
    - catalogo_tienda: belongsTo catalogo_tienda (tienda_id, pkid)
    - created_by: belongsTo User (created_by_id, pkid)
    - updated_by: belongsTo User (updated_by_id, pkid)
    - deleted_by: belongsTo User (deleted_by_id, pkid)
  filter: [app/Filters/dbsip/sip_auditoras_tiendasFilters.php]
  service: [app/Services/AuditorasTiendasService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_auditoras_tiendasController.php]
  routes: [routes/modules/sip_auditoras.php]
- model: sip_auditoriadesctotardanzas
  path: app/Models/dbsip/sip_auditoriadesctotardanzas.php
  connection: mysql_dbsip
  table: sip_auditoriadesctotardanzas
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  relaciones:
    - sip_personal: belongsTo sip_personal (personal_id, pkid)
    - sip_personalmovimiento: belongsTo sip_personalmovimientos (personalmovimiento_id, pkid)
    - catalogo_usuario: belongsTo usuarios (usuario_id, pkid)
  service_usado_en: [app/Services/TardanzasService.php]
- model: sip_baseplanillacontable
  path: app/Models/dbsip/sip_baseplanillacontable.php
  connection: mysql_dbsip
  table: sip_baseplanillacontable
  pk: {name: pkid, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  filter: [app/Filters/dbsip/sip_baseplanillacontableFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_baseplanillacontableResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_baseplanillacontableController.php]
  routes: [routes/api.php]
- model: sip_cargamasivajobs
  path: app/Models/dbsip/sip_cargamasivajobs.php
  connection: mysql_dbsip
  table: sip_cargamasivajobs
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: [created_by_id]
  controller: [app/Http/Controllers/Api/Sip/sip_cargamasivajobsController.php]
  routes: [routes/api.php]
- model: sip_categoriaocupacionaltrabajador
  path: app/Models/dbsip/sip_categoriaocupacionaltrabajador.php
  connection: mysql_dbsip
  table: sip_categoriaocupacionaltrabajador
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  resources:
    - app/Http/Resources/Sip/sip_categoriaocupacionaltrabajadorResource.php
  controller_usado_en: [app/Http/Controllers/Api/Logs/sip_logspersonalController.php, app/Http/Controllers/Api/Sip/sip_categoriaocupacionalController.php, app/Http/Controllers/Api/Sip/sip_personalmodificacionsolicitudController.php]
  routes: [routes/api.php]
- model: sip_confighorariosjornada
  path: app/Models/dbsip/sip_confighorariosjornada.php
  connection: mysql_dbsip
  table: sip_confighorariosjornada
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
- model: sip_descansosmedicospendientes
  path: app/Models/dbsip/sip_descansosmedicospendientes.php
  connection: mysql_dbsip
  table: sip_descansosmedicospendientes
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  resources:
    - app/Http/Resources/Sip/sip_descansosmedicospendientesRelationResource.php
    - app/Http/Resources/Sip/sip_descansosmedicospendientesResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_descansosmedicospendientesController.php]
  routes: [routes/api.php]
- model: sip_estandarpersonal
  path: app/Models/dbsip/sip_estandarpersonal.php
  connection: mysql_dbsip
  table: sip_estandarpersonal
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  observer: true
  relaciones:
    - sip_periodoestandar: belongsTo sip_periodoestandar (periodo_id, pkid)
    - sip_tiendacargo: belongsTo sip_tiendacargo (tiendacargo_id, pkid)
    - catalogo_tienda: belongsTo catalogo_tienda (tienda_id, pkid)
    - catalogo_tiendaturnos: belongsTo catalogo_tiendaturnos (tiendaturno_id, pkid)
    - usuario_creacion: belongsTo usuarios (created_by_id, pkid)
    - usuario_actualizacion: belongsTo usuarios (updated_by_id, pkid)
    - usuario_eliminacion: belongsTo usuarios (deleted_by_id, pkid)
  filter: [app/Filters/dbsip/sip_estandarpersonalFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_estandarpersonalResource.php
  service: [app/Services/EstandarPersonalService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_estandarpersonalController.php]
  routes: [routes/modules/sip_estandarpersonal.php]
- model: sip_feriados
  path: app/Models/dbsip/sip_feriados.php
  connection: mysql_dbsip
  table: sip_feriados
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  relaciones:
    - anio: hasOne sip_anios (pkid, anio_id)
  filter: [app/Filters/dbsip/sip_feriadosFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_feriadosResource.php
  service_usado_en: [app/Services/TardanzasService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_feriadosController.php]
  routes: [routes/api.php]
- model: sip_lugares
  path: app/Models/dbsip/sip_lugares.php
  connection: mysql_dbsip
  table: sip_lugares
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: no
  has_factory: true
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Sip/sip_personaltiemposasistenciaController.php]
  routes: [routes/api.php]
- model: sip_motivoasistencia
  path: app/Models/dbsip/sip_motivoasistencia.php
  connection: mysql_dbsip
  table: sip_motivoasistencia
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  filter: [app/Filters/dbsip/sip_motivoasistenciaFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_motivoasistenciaRelationResource.php
    - app/Http/Resources/Sip/sip_motivoasistenciaResource.php
  service: [app/Services/MotivoAsistenciaService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_motivoasistenciaController.php]
  routes: [routes/api.php]
- model: sip_motivospremiacion
  path: app/Models/dbsip/sip_motivospremiacion.php
  connection: mysql_dbsip
  table: sip_motivospremiacion
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  filter: [app/Filters/dbsip/sip_motivospremiacionFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_motivospremiacionRelationResource.php
    - app/Http/Resources/Sip/sip_motivospremiacionResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_motivospremiacionController.php]
  routes: [routes/api.php]
- model: sip_multitabla
  path: app/Models/dbsip/sip_multitabla.php
  connection: mysql_dbsip
  table: sip_multitabla
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  filter: [app/Filters/dbsip/sip_multitabladetalleFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_multitablaResource.php
    - app/Http/Resources/Sip/sip_multitabladetalleItemResource.php
    - app/Http/Resources/Sip/sip_multitabladetalleResource.php
    - app/Http/Resources/Sip/sip_multitabladetalleTinyResource.php
  service_usado_en: [app/Services/MultiTablaDetalleService.php, app/Services/PersonalSegurosService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_multitablaController.php]
  routes: [routes/api.php, routes/modules/sip_multitabladetalle.php]
- model: sip_multitabladetalle
  path: app/Models/dbsip/sip_multitabladetalle.php
  connection: mysql_dbsip
  table: sip_multitabladetalle
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  relaciones:
    - sip_multitabla_parent: belongsTo sip_multitabla (parent_id, pkid)
  filter: [app/Filters/dbsip/sip_multitabladetalleFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_multitabladetalleItemResource.php
    - app/Http/Resources/Sip/sip_multitabladetalleResource.php
    - app/Http/Resources/Sip/sip_multitabladetalleTinyResource.php
  requests:
    - app/Http/Requests/Sip/Traits/ValidatesPersonalSeguros.php
    - app/Http/Requests/Sip/sip_personalboletabeneficios/GenerarMacroCtsRequest.php
    - app/Http/Requests/Sip/sip_personalboletavacaciones/GenerarMacroPlanillaRequest.php
  service: [app/Services/MultiTablaDetalleService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_multitabladetalleController.php]
  routes: [routes/api.php, routes/modules/consultaMaestros.php, routes/modules/sip_multitabladetalle.php, routes/modules/sip_personalboletabeneficios.php]
- model: sip_nivel_salarial_cab
  path: app/Models/dbsip/sip_nivel_salarial_cab.php
  connection: mysql_dbsip
  table: sip_nivel_salarial_cab
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  filter: [app/Filters/dbsip/sip_nivel_salarial_cabFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_nivel_salarial_cabResource.php
    - app/Http/Resources/Sip/sip_nivel_salarial_cab_collectionResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_nivel_salarial_cabController.php]
  routes: [routes/api.php]
- model: sip_nivel_salarial_det
  path: app/Models/dbsip/sip_nivel_salarial_det.php
  connection: mysql_dbsip
  table: sip_nivel_salarial_det
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  resources:
    - app/Http/Resources/Sip/sip_nivel_salarial_detResource.php
  controller_usado_en: [app/Http/Controllers/Api/Sip/sip_nivel_salarial_cabController.php]
  routes: [routes/api.php]
- model: sip_nivel_salarial_tiendas
  path: app/Models/dbsip/sip_nivel_salarial_tiendas.php
  connection: mysql_dbsip
  table: sip_nivel_salarial_tiendas
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  filter: [app/Filters/dbsip/sip_nivel_salarial_tiendasFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_nivel_salarial_tiendasResource.php
    - app/Http/Resources/Sip/sip_nivel_salarial_tiendas_collectionResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_nivel_salarial_tiendasController.php]
  routes: [routes/api.php]
- model: sip_periodocontable
  path: app/Models/dbsip/sip_periodocontable.php
  connection: mysql_dbsip
  table: sip_periodocontable
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  filter: [app/Filters/dbsip/sip_periodocontableFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_periodocontableResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_periodocontableController.php]
  routes: [routes/api.php]
- model: sip_periodoestandar
  path: app/Models/dbsip/sip_periodoestandar.php
  connection: mysql_dbsip
  table: sip_periodoestandar
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  observer: true
  filter: [app/Filters/dbsip/sip_periodoestandarFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_periodoestandarResource.php
  service: [app/Services/PeriodoEstandarService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_periodoestandarController.php]
  routes: [routes/modules/sip_periodoestandar.php]
- model: sip_periodovacacional
  path: app/Models/dbsip/sip_periodovacacional.php
  connection: mysql_dbsip
  table: sip_periodovacacional
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  observer: true
  relaciones:
    - createdBy: belongsTo usuarios (created_by_id, pkid)
    - updatedBy: belongsTo usuarios (updated_by_id, pkid)
    - deletedBy: belongsTo usuarios (deleted_by_id, pkid)
  filter: [app/Filters/dbsip/sip_periodovacacionalFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_periodovacacionalRelacionResource.php
    - app/Http/Resources/Sip/sip_periodovacacionalResource.php
  requests:
    - app/Http/Requests/Sip/sip_periodovacacional/StorePeriodoVacacionalRequest.php
    - app/Http/Requests/Sip/sip_periodovacacional/UpdatePeriodoVacacionalRequest.php
  service: [app/Services/PeriodoVacacionalService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_periodovacacionalController.php]
  routes: [routes/modules/sip_periodovacacional.php]
- model: sip_personal
  path: app/Models/dbsip/sip_personal.php
  connection: mysql_dbsip
  table: sip_personal
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id]
  observer: true
  relaciones:
    - sueldoEnRango: hasOne sip_personalmovimientosueldo (personal_id, id)
    - tiendaData: hasOneThrough catalogo_tienda
  filter: [app/Filters/dbsip/sip_periodovacacionalFilters.php, app/Filters/dbsip/sip_personalboletavacacionesFilters.php, app/Filters/dbsip/sip_personalmovimientosconsumoFilters.php, app/Filters/dbsip/sip_personalmovimientovacacionesFilters.php, app/Filters/dbsip/sip_personalventavacacionesFilters.php, app/Filters/dbsip/sip_solicitudvacacionesFilters.php]
  resources:
    - app/Http/Resources/Sempiterno/sip_personalDataCargoResource.php
    - app/Http/Resources/Sempiterno/sip_personalDataResource.php
    - app/Http/Resources/Sip/sip_personalAsistenciaResource.php
    - app/Http/Resources/Sip/sip_personalHorarioConsolidadoResource.php
    - app/Http/Resources/Sip/sip_personalIndexResource.php
    - app/Http/Resources/Sip/sip_personalRelacionResource.php
    - app/Http/Resources/Sip/sip_personalResource.php
    - app/Http/Resources/Sip/sip_personalShowResource.php
    - app/Http/Resources/Sip/sip_personalTinyRelacionResource.php
    - app/Http/Resources/Sip/sip_personal_segurosRelationResource.php
    - app/Http/Resources/Sip/sip_personal_segurosResource.php
    - app/Http/Resources/Sip/sip_personalautorizacionResource.php
    - app/Http/Resources/Sip/sip_personalautorizacionpaRelationResource.php
    - app/Http/Resources/Sip/sip_personalbaseplanilladetalleResource.php
    - app/Http/Resources/Sip/sip_personalbasicResource.php
    - app/Http/Resources/Sip/sip_personalbloqueoasistenciaResource.php
    - app/Http/Resources/Sip/sip_personalboletabeneficiosPeriodoResource.php
    - app/Http/Resources/Sip/sip_personalboletabeneficiosResource.php
    - app/Http/Resources/Sip/sip_personalboletabeneficiosdetResource.php
    - app/Http/Resources/Sip/sip_personalboletapagoInconsistenciaDiasResource.php
    - app/Http/Resources/Sip/sip_personalboletapagoInconsistenciaNegativosResource.php
    - app/Http/Resources/Sip/sip_personalboletapagoListResource.php
    - app/Http/Resources/Sip/sip_personalboletapagoResource.php
    - app/Http/Resources/Sip/sip_personalboletapagoShowResource.php
    - app/Http/Resources/Sip/sip_personalboletapagodetResource.php
    - app/Http/Resources/Sip/sip_personalboletavacacionesShowResource.php
    - app/Http/Resources/Sip/sip_personalboletavacacionesdetResource.php
    - app/Http/Resources/Sip/sip_personalcargosResource.php
    - app/Http/Resources/Sip/sip_personalcentralResource.php
    - app/Http/Resources/Sip/sip_personalcesadoResource.php
    - app/Http/Resources/Sip/sip_personaldescuentosResource.php
    - app/Http/Resources/Sip/sip_personalingresoscesesResource.php
    - app/Http/Resources/Sip/sip_personalliquidacionResource.php
    - app/Http/Resources/Sip/sip_personalmodificacionsolicitudResource.php
    - app/Http/Resources/Sip/sip_personalmovcargosResource.php
    - app/Http/Resources/Sip/sip_personalmovimientocargosResource.php
    - app/Http/Resources/Sip/sip_personalmovimientohorarioItemResource.php
    - app/Http/Resources/Sip/sip_personalmovimientohorarioResource.php
    - app/Http/Resources/Sip/sip_personalmovimientohorariodetResource.php
    - app/Http/Resources/Sip/sip_personalmovimientohorariosResource.php
    - app/Http/Resources/Sip/sip_personalmovimientoingresoceseResource.php
    - app/Http/Resources/Sip/sip_personalmovimientolegajosResource.php
    - app/Http/Resources/Sip/sip_personalmovimientolegajosdetLeftResource.php
    - app/Http/Resources/Sip/sip_personalmovimientolegajosdetResource.php
    - app/Http/Resources/Sip/sip_personalmovimientosAbonosResource.php
    - app/Http/Resources/Sip/sip_personalmovimientosPendientesResource.php
    - app/Http/Resources/Sip/sip_personalmovimientosResource.php
    - app/Http/Resources/Sip/sip_personalmovimientosconsumoResource.php
    - app/Http/Resources/Sip/sip_personalmovimientosueldocontabledetResource.php
    - app/Http/Resources/Sip/sip_personalmovimientosueldosdetallesResource.php
    - app/Http/Resources/Sip/sip_personalmovimientotiendaResource.php
    - app/Http/Resources/Sip/sip_personalmovimientoturnoResource.php
    - app/Http/Resources/Sip/sip_personalmovimientovacacionesResumenResource.php
    - app/Http/Resources/Sip/sip_personalpivotResource.php
    - app/Http/Resources/Sip/sip_personalplanillaDetResource.php
    - app/Http/Resources/Sip/sip_personalplanillaRelationResource.php
    - app/Http/Resources/Sip/sip_personalplanillaResource.php
    - app/Http/Resources/Sip/sip_personalplanillatdaBoletaResource.php
    - app/Http/Resources/Sip/sip_personalplanillatdaResource.php
    - app/Http/Resources/Sip/sip_personalsolicitudLiquidacionesResource.php
    - app/Http/Resources/Sip/sip_personalsolicitudespremiacionListResource.php
    - app/Http/Resources/Sip/sip_personalsolicitudespremiacionRelationResource.php
    - app/Http/Resources/Sip/sip_personalsolicitudespremiacionResource.php
    - app/Http/Resources/Sip/sip_personaltiemposasistencia2Resource.php
    - app/Http/Resources/Sip/sip_personaltiemposasistenciaResource.php
    - app/Http/Resources/Sip/sip_personaltiendasResource.php
    - app/Http/Resources/Sip/sip_personalturnosResource.php
    - app/Http/Resources/Sip/sip_personalvacacionesylicenciasResource.php
    - app/Http/Resources/Sip/sip_personalventavacacionesResource.php
    - app/Http/Resources/Sip/sip_personalzonalResource.php
    - app/Http/Resources/sip_personal/sip_personalResource.php
    - app/Http/Resources/sip_personalmovimientocargo/sip_personalmovimientocargoResource.php
    - app/Http/Resources/sip_personalmovimientoingresocese/sip_personalmovimientoingresoceseResource.php
    - app/Http/Resources/sip_personalmovimientosueldo/sip_personalmovimientosueldoResource.php
    - app/Http/Resources/sip_personalmovimientotienda/sip_personalmovimientotiendaResource.php
    - app/Http/Resources/sip_personalmovimientoturno/sip_personalmovimientoturnoResource.php
    - app/Http/Resources/sip_personalprocesoadministrativo/sip_personalprocesoadministrativoResource.php
  requests:
    - app/Http/Requests/Sip/sip_personalmovimientohorariodet/ReplicarHorarioDetRequest.php
  service: [app/Services/PersonalService.php]
  controller: [app/Http/Controllers/Api/Sincro_sip/sip_personalController.php, app/Http/Controllers/Api/Sip/sip_personalController.php]
  routes: [routes/api.php, routes/modules/sip_personal_seguros.php]
- model: sip_personal_seguros
  path: app/Models/dbsip/sip_personal_seguros.php
  connection: mysql_dbsip
  table: sip_personal_seguros
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  observer: true
  relaciones:
    - sip_personal: belongsTo sip_personal (personal_id, pkid)
    - tipo_seguro: belongsTo sip_multitabladetalle (tipo_seguro_id, pkid)
    - aseguradora_empresa: belongsTo sip_multitabladetalle (aseguradora_empresa_id, pkid)
    - created_by: belongsTo usuarios (created_by_id, pkid)
    - updated_by: belongsTo usuarios (updated_by_id, pkid)
    - deleted_by: belongsTo usuarios (deleted_by_id, pkid)
  filter: [app/Filters/dbsip/sip_personal_segurosFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personal_segurosRelationResource.php
    - app/Http/Resources/Sip/sip_personal_segurosResource.php
  service: [app/Services/PersonalSegurosService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personal_segurosController.php]
  routes: [routes/modules/sip_personal_seguros.php]
- model: sip_personalasistencia
  path: app/Models/dbsip/sip_personalasistencia.php
  connection: mysql_dbsip
  table: sip_personalasistencia
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  observer: true
  resources:
    - app/Http/Resources/Sip/sip_personalAsistenciaResource.php
  service_usado_en: [app/Services/PersonalTiemposAsistenciaService.php, app/Services/TardanzasService.php]
  controller_usado_en: [app/Http/Controllers/Api/Logs/sip_logsasistenciaController.php, app/Http/Controllers/Api/Sig/sip_tiemposasistenciaController.php, app/Http/Controllers/Api/Sip/ReporteModificacionesAsistenciaController.php, app/Http/Controllers/Api/Sip/sip_personalboletapagoController.php, ...]
  routes: [routes/api.php]
- model: sip_personalautorizacionpa
  path: app/Models/dbsip/sip_personalautorizacionpa.php
  connection: mysql_dbsip
  table: sip_personalautorizacionpa
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  resources:
    - app/Http/Resources/Sip/sip_personalautorizacionpaRelationResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_personalautorizacionpaController.php]
  routes: [routes/api.php]
- model: sip_personalbaseplanilladetalle
  path: app/Models/dbsip/sip_personalbaseplanilladetalle.php
  connection: mysql_dbsip
  table: sip_personalbaseplanilladetalle
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  filter: [app/Filters/dbsip/sip_personalbaseplanilladetalleFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalbaseplanilladetalleResource.php
- model: sip_personalbloqueoasistencia
  path: app/Models/dbsip/sip_personalbloqueoasistencia.php
  connection: mysql_dbsip
  table: sip_personalbloqueoasistencia
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  resources:
    - app/Http/Resources/Sip/sip_personalbloqueoasistenciaResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_personalbloqueoasistenciaController.php]
  routes: [routes/api.php]
- model: sip_personalboletabeneficios
  path: app/Models/dbsip/sip_personalboletabeneficios.php
  connection: mysql_dbsip
  table: sip_personalboletabeneficios
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  observer: true
  relaciones:
    - created_by: belongsTo User (created_by_id, pkid)
    - updated_by: belongsTo User (updated_by_id, pkid)
    - deleted_by: belongsTo User (deleted_by_id, pkid)
    - paid_by: belongsTo User (paid_by, pkid)
    - personal: belongsTo sip_personal (personal_id, pkid)
    - tienda: belongsTo catalogo_tienda (tienda_id, pkid)
    - sip_personalplanilla: belongsTo sip_personalplanilla (personalplanilla_id, pkid)
    - sip_personalplanillatda: belongsTo sip_personalplanillatda (personalplanillatda_id, pkid)
    - sip_personalboletabeneficiosdet: hasMany sip_personalboletabeneficiosdet (personalboletabeneficios_id, pkid)
    - empresa: belongsTo catalogo_empresa (empresa_id, pkid)
  filter: [app/Filters/dbsip/sip_personalboletabeneficiosFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalboletabeneficiosPeriodoResource.php
    - app/Http/Resources/Sip/sip_personalboletabeneficiosResource.php
    - app/Http/Resources/Sip/sip_personalboletabeneficiosdetResource.php
  requests:
    - app/Http/Requests/Sip/StorePersonalBoletaBeneficiosRequest.php
    - app/Http/Requests/Sip/sip_personalboletabeneficios/GenerarMacroCtsRequest.php
  service: [app/Services/PersonalBoletaBeneficiosService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalboletabeneficiosController.php]
  routes: [routes/modules/sip_personalboletabeneficios.php]
- model: sip_personalboletabeneficiosdet
  path: app/Models/dbsip/sip_personalboletabeneficiosdet.php
  connection: mysql_dbsip
  table: sip_personalboletabeneficiosdet
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  observer: true
  relaciones:
    - sip_personalboletabeneficios: belongsTo sip_personalboletabeneficios (personalboletabeneficios_id, pkid)
    - sip_tipomovimiento: belongsTo sip_tipomovimiento (tipomov_id, pkid)
    - sip_personaldescuentos: belongsTo sip_personaldescuentos (descuento_id, pkid)
    - created_by: belongsTo User (created_by_id, pkid)
    - updated_by: belongsTo User (updated_by_id, pkid)
    - deleted_by: belongsTo User (deleted_by_id, pkid)
  filter: [app/Filters/dbsip/sip_personalboletabeneficiosdetFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalboletabeneficiosdetResource.php
  service: [app/Services/PersonalBoletaBeneficiosDetService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalboletabeneficiosdetController.php]
  routes: [routes/modules/sip_personalboletabeneficiosdet.php]
- model: sip_personalboletapago
  path: app/Models/dbsip/sip_personalboletapago.php
  connection: mysql_dbsip
  table: sip_personalboletapago
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  filter: [app/Filters/dbsip/sip_personalboletapagoFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalboletapagoInconsistenciaDiasResource.php
    - app/Http/Resources/Sip/sip_personalboletapagoInconsistenciaNegativosResource.php
    - app/Http/Resources/Sip/sip_personalboletapagoListResource.php
    - app/Http/Resources/Sip/sip_personalboletapagoResource.php
    - app/Http/Resources/Sip/sip_personalboletapagoShowResource.php
    - app/Http/Resources/Sip/sip_personalboletapagodetResource.php
  service: [app/Services/PersonalBoletaPagoService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalboletapagoController.php]
  routes: [routes/api.php]
- model: sip_personalboletapagodet
  path: app/Models/dbsip/sip_personalboletapagodet.php
  connection: mysql_dbsip
  table: sip_personalboletapagodet
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  resources:
    - app/Http/Resources/Sip/sip_personalboletapagodetResource.php
  service: [app/Services/PersonalBoletaPagoDetService.php]
  controller_usado_en: [app/Http/Controllers/Api/Reports/sip_personaldescuentosreportsController.php, app/Http/Controllers/Api/Sip/sip_personalboletapagoController.php, app/Http/Controllers/Api/Sip/sip_personalmovimientosController.php, app/Http/Controllers/Api/Sip/sip_planillacontableController.php]
  routes: [routes/api.php]
- model: sip_personalboletavacaciones
  path: app/Models/dbsip/sip_personalboletavacaciones.php
  connection: mysql_dbsip
  table: sip_personalboletavacaciones
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  relaciones:
    - created_by: belongsTo User (created_by_id, pkid)
    - paidBy: belongsTo User (paid_by, pkid)
    - sip_personal: hasOne sip_personal (pkid, personal_id)
    - sip_personalmovimientosueldo: hasOne sip_personalmovimientosueldo (pkid, sueldo_id)
    - sip_solicitudvacaciones: hasOne sip_solicitudvacaciones (pkid, solicitud_vacaciones_id)
    - sip_personalboletavacacionesdet: hasMany sip_personalboletavacacionesdet (boletavacaciones_id, pkid)
    - sip_personalplanilla: belongsTo sip_personalplanilla (personalplanilla_id, pkid)
    - sip_personalplanillatda: belongsTo sip_personalplanillatda (personalplanillatda_id, pkid)
  filter: [app/Filters/dbsip/sip_personalboletavacacionesFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalboletavacacionesShowResource.php
    - app/Http/Resources/Sip/sip_personalboletavacacionesdetResource.php
  requests:
    - app/Http/Requests/Sip/Traits/sip_personalboletavacaciones/ValidatesBoletaVacaciones.php
    - app/Http/Requests/Sip/sip_personalboletavacaciones/CambiarEstadoBoletaVacacionesRequest.php
    - app/Http/Requests/Sip/sip_personalboletavacaciones/CerrarLoteRequest.php
    - app/Http/Requests/Sip/sip_personalboletavacaciones/GenerarMacroPlanillaRequest.php
    - app/Http/Requests/Sip/sip_personalboletavacaciones/ProcesarVentaBoletaRequest.php
    - app/Http/Requests/Sip/sip_personalboletavacaciones/RecalcularBoletaVacacionesRequest.php
  service: [app/Services/PersonalBoletaVacacionesService.php]
  controller_usado_en: [app/Http/Controllers/Api/Sip/sip_planillacontableController.php]
  routes: [routes/api.php]
- model: sip_personalboletavacacionesdet
  path: app/Models/dbsip/sip_personalboletavacacionesdet.php
  connection: mysql_dbsip
  table: sip_personalboletavacacionesdet
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  relaciones:
    - sip_personalboletavacaciones: belongsTo sip_personalboletavacaciones (boletavacaciones_id, pkid)
    - sip_tipomovimiento: belongsTo sip_tipomovimiento (tipomov_id, pkid)
    - sip_personaldescuentos: belongsTo sip_personaldescuentos (descuento_id, pkid)
  resources:
    - app/Http/Resources/Sip/sip_personalboletavacacionesdetResource.php
  service_usado_en: [app/Services/PersonalBoletaVacacionesService.php]
- model: sip_personalcargos
  path: app/Models/dbsip/sip_personalcargos.php
  connection: mysql_dbsip
  table: sip_personalcargos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  filter: [app/Filters/dbsip/sip_personalcargosFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalcargosResource.php
  service_usado_en: [app/Services/PersonalPivotService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalcargosController.php]
  routes: [routes/api.php, routes/modules/tiendacargo.php]
- model: sip_personalcentral
  path: app/Models/dbsip/sip_personalcentral.php
  connection: mysql_dbsip
  table: sip_personalcentral
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  resources:
    - app/Http/Resources/Sip/sip_personalcentralResource.php
  service_usado_en: [app/Services/PersonalTiemposAsistenciaService.php, app/Services/PersonalmovimientosconsumoService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalcentralController.php]
  routes: [routes/api.php]
- model: sip_personalcesado
  path: app/Models/dbsip/sip_personalcesado.php
  connection: mysql_dbsip
  table: sip_personalcesado
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - sip_personal: belongsTo sip_personal (personal_id, pkid)
  filter: [app/Filters/dbsip/sip_personalcesadoFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalcesadoResource.php
  service_usado_en: [app/Services/PersonalSegurosService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalcesadoController.php]
  routes: [routes/api.php]
- model: sip_personaldescuentos
  path: app/Models/dbsip/sip_personaldescuentos.php
  connection: mysql_dbsip
  table: sip_personaldescuentos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  relaciones:
    - user_created: belongsTo usuarios (created_by_id, pkid)
    - user_updated: belongsTo usuarios (updated_by_id, pkid)
  resources:
    - app/Http/Resources/Sip/sip_personaldescuentosResource.php
  service: [app/Services/PersonalDescuentosService.php]
  controller_usado_en: [app/Http/Controllers/Api/Reports/sip_personaldescuentosreportsController.php, app/Http/Controllers/Api/Sig/SubirMovimientosController.php, app/Http/Controllers/Api/Sip/sip_descansosmedicospendientesController.php, app/Http/Controllers/Api/Sip/sip_personalautorizacionpaController.php, ...]
  routes: [routes/api.php]
- model: sip_personalgratificaciones
  path: app/Models/dbsip/sip_personalgratificaciones.php
  connection: mysql_dbsip
  table: sip_personalgratificaciones
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  service_usado_en: [app/Services/CalcularCtsService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalgratificacionesController.php]
  routes: [routes/api.php]
- model: sip_personalliquidacion
  path: app/Models/dbsip/sip_personalliquidacion.php
  connection: mysql_dbsip
  table: sip_personalliquidacion
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  resources:
    - app/Http/Resources/Sip/sip_personalliquidacionResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_personalliquidacionController.php]
  routes: [routes/api.php]
- model: sip_personalmodificacionsolicitud
  path: app/Models/dbsip/sip_personalmodificacionsolicitud.php
  connection: mysql_dbsip
  table: sip_personalmodificacionsolicitud
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  resources:
    - app/Http/Resources/Sip/sip_personalmodificacionsolicitudResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_personalmodificacionsolicitudController.php]
  routes: [routes/api.php]
- model: sip_personalmodificacionsolicituddet
  path: app/Models/dbsip/sip_personalmodificacionsolicituddet.php
  connection: mysql_dbsip
  table: sip_personalmodificacionsolicituddet
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  controller_usado_en: [app/Http/Controllers/Api/Sip/sip_personalmodificacionsolicitudController.php]
  routes: [routes/api.php]
- model: sip_personalmovimientocargo
  path: app/Models/dbsip/sip_personalmovimientocargo.php
  connection: mysql_dbsip
  table: sip_personalmovimientocargo
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id]
  observer: true
  resources:
    - app/Http/Resources/Sip/sip_personalmovimientocargosResource.php
    - app/Http/Resources/sip_personalmovimientocargo/sip_personalmovimientocargoResource.php
  service_usado_en: [app/Services/PersonalPivotService.php]
  controller: [app/Http/Controllers/Api/Sincro_sip/sip_personalmovimientocargoController.php]
  routes: [routes/api.php, routes/modules/sip_personalmovimientocargo.php]
- model: sip_personalmovimientocontable
  path: app/Models/dbsip/sip_personalmovimientocontable.php
  connection: mysql_dbsip
  table: sip_personalmovimientocontable
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  controller: [app/Http/Controllers/Api/Sip/sip_personalmovimientocontableController.php]
  routes: [routes/api.php]
- model: sip_personalmovimientoderechohabiente
  path: app/Models/dbsip/sip_personalmovimientoderechohabiente.php
  connection: mysql_dbsip
  table: sip_personalmovimientoderechohabiente
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  relaciones:
    - sip_personal: hasOne sip_personal (pkid, personal_id)
    - sip_personalmovimientotienda: hasOne sip_personalmovimientotienda (personal_id, personal_id)
    - sip_personalmovimientoempresa: hasOne sip_personalmovimientoempresa (personal_id, personal_id)
  controller_usado_en: [app/Http/Controllers/Api/Reports/sip_personalreportsController.php]
  routes: [routes/api.php]
- model: sip_personalmovimientoempresa
  path: app/Models/dbsip/sip_personalmovimientoempresa.php
  connection: mysql_dbsip
  table: sip_personalmovimientoempresa
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  filter: [app/Filters/dbsip/sip_personalmovimientoempresaFilters.php]
  controller_usado_en: [app/Http/Controllers/Api/Logs/sip_logspersonalController.php, app/Http/Controllers/Api/Sip/sip_personalController.php, app/Http/Controllers/Api/Sip/sip_personalmodificacionsolicitudController.php, app/Http/Controllers/Api/Sip/sip_planillacontableController.php, ...]
  routes: [routes/api.php]
- model: sip_personalmovimientohorario
  path: app/Models/dbsip/sip_personalmovimientohorario.php
  connection: mysql_dbsip
  table: sip_personalmovimientohorario
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  relaciones:
    - sip_personal: hasOne sip_personal (pkid, personal_id)
    - sip_personalmovimientohorariodet: hasMany sip_personalmovimientohorariodet (horario_id, pkid)
  resources:
    - app/Http/Resources/Sip/sip_personalmovimientohorarioItemResource.php
    - app/Http/Resources/Sip/sip_personalmovimientohorarioResource.php
    - app/Http/Resources/Sip/sip_personalmovimientohorariodetResource.php
    - app/Http/Resources/Sip/sip_personalmovimientohorariosResource.php
  requests:
    - app/Http/Requests/Sip/sip_personalmovimientohorariodet/ReplicarHorarioDetRequest.php
  service: [app/Services/PersonalMovimientoHorarioService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalmovimientohorarioController.php]
  routes: [routes/api.php]
- model: sip_personalmovimientohorariodet
  path: app/Models/dbsip/sip_personalmovimientohorariodet.php
  connection: mysql_dbsip
  table: sip_personalmovimientohorariodet
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - created_by: belongsTo usuarios (created_by_id, pkid)
    - updated_by: belongsTo usuarios (updated_by_id, pkid)
    - deleted_by: belongsTo usuarios (deleted_by_id, pkid)
    - sip_personalmovimientohorario: belongsTo sip_personalmovimientohorario (horario_id, pkid)
  filter: [app/Filters/dbsip/sip_personalmovimientohorariodetFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalmovimientohorariodetResource.php
  requests:
    - app/Http/Requests/Sip/Traits/sip_personalmovimientohorariodet/ValidatesHorarioDet.php
    - app/Http/Requests/Sip/sip_personalmovimientohorariodet/BulkUpdateHorarioDetRequest.php
    - app/Http/Requests/Sip/sip_personalmovimientohorariodet/ReplicarHorarioDetRequest.php
    - app/Http/Requests/Sip/sip_personalmovimientohorariodet/StoreDefaultHorarioDetRequest.php
    - app/Http/Requests/Sip/sip_personalmovimientohorariodet/StoreHorarioDetRequest.php
    - app/Http/Requests/Sip/sip_personalmovimientohorariodet/UpdateHorarioDetRequest.php
  service: [app/Services/PersonalMovimientoHorarioDetService.php]
- model: sip_personalmovimientoingresocese
  path: app/Models/dbsip/sip_personalmovimientoingresocese.php
  connection: mysql_dbsip
  table: sip_personalmovimientoingresocese
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: true
  auditoria: []
  resources:
    - app/Http/Resources/Sip/sip_personalmovimientoingresoceseResource.php
    - app/Http/Resources/sip_personalmovimientoingresocese/sip_personalmovimientoingresoceseResource.php
  service: [app/Services/PersonalMovimientoIngresoCeseService.php]
  controller: [app/Http/Controllers/Api/Sincro_sip/sip_personalmovimientoingresoceseController.php]
  routes: [routes/api.php]
- model: sip_personalmovimientolegajos
  path: app/Models/dbsip/sip_personalmovimientolegajos.php
  connection: mysql_dbsip
  table: sip_personalmovimientolegajos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  filter: [app/Filters/dbsip/sip_personalmovimientolegajosFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalmovimientolegajosResource.php
    - app/Http/Resources/Sip/sip_personalmovimientolegajosdetLeftResource.php
    - app/Http/Resources/Sip/sip_personalmovimientolegajosdetResource.php
- model: sip_personalmovimientolegajosdet
  path: app/Models/dbsip/sip_personalmovimientolegajosdet.php
  connection: mysql_dbsip
  table: sip_personalmovimientolegajosdet
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  filter: [app/Filters/dbsip/sip_personalmovimientolegajosdetFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalmovimientolegajosdetLeftResource.php
    - app/Http/Resources/Sip/sip_personalmovimientolegajosdetResource.php
  service: [app/Services/PersonalMovimientoLegajosDetService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalmovimientolegajosdetController.php]
  routes: [routes/api.php]
- model: sip_personalmovimientos
  path: app/Models/dbsip/sip_personalmovimientos.php
  connection: mysql_dbsip
  table: sip_personalmovimientos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  filter: [app/Filters/dbsip/sip_personalmovimientosFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalmovimientosAbonosResource.php
    - app/Http/Resources/Sip/sip_personalmovimientosPendientesResource.php
    - app/Http/Resources/Sip/sip_personalmovimientosResource.php
    - app/Http/Resources/Sip/sip_personalmovimientosconsumoResource.php
    - app/Http/Resources/Sip/sip_personalmovimientosueldocontabledetResource.php
    - app/Http/Resources/Sip/sip_personalmovimientosueldosdetallesResource.php
    - app/Http/Resources/sip_personalmovimientosueldo/sip_personalmovimientosueldoResource.php
  service: [app/Services/PersonalMovimientosService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalmovimientosController.php]
  routes: [routes/api.php]
- model: sip_personalmovimientosconsumo
  path: app/Models/dbsip/sip_personalmovimientosconsumo.php
  connection: mysql_dbsip
  table: sip_personalmovimientosconsumo
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  observer: true
  relaciones:
    - personal: belongsTo sip_personal (personal_id, pkid)
    - cajero: belongsTo sip_personal (cajero_id, pkid)
    - tienda_consumo_rel: belongsTo catalogo_tienda (tienda_consumo, pkid)
    - tienda_personal_rel: belongsTo catalogo_tienda (tienda_personal, pkid)
  filter: [app/Filters/dbsip/sip_personalmovimientosconsumoFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalmovimientosconsumoResource.php
  requests:
    - app/Http/Requests/Sip/Traits/sip_personalmovimientosconsumo/ValidatesConsumoExternal.php
    - app/Http/Requests/Sip/Traits/sip_personalmovimientosconsumo/ValidatesPersonalmovimientosconsumo.php
    - app/Http/Requests/Sip/sip_personalmovimientosconsumo/ConsultarConsumoExternalRequest.php
    - app/Http/Requests/Sip/sip_personalmovimientosconsumo/ConsultarConsumoHistoricoRequest.php
    - app/Http/Requests/Sip/sip_personalmovimientosconsumo/ExportPersonalmovimientosconsumoRequest.php
    - app/Http/Requests/Sip/sip_personalmovimientosconsumo/StoreConsumoExternalRequest.php
    - app/Http/Requests/Sip/sip_personalmovimientosconsumo/StorePersonalmovimientosconsumoRequest.php
    - app/Http/Requests/Sip/sip_personalmovimientosconsumo/UpdatePersonalmovimientosconsumoRequest.php
  service: [app/Services/PersonalmovimientosconsumoService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalmovimientosconsumoController.php]
  routes: [routes/modules/sip_personalmovimientosconsumo.php]
- model: sip_personalmovimientosueldo
  path: app/Models/dbsip/sip_personalmovimientosueldo.php
  connection: mysql_dbsip
  table: sip_personalmovimientosueldo
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  resources:
    - app/Http/Resources/Sip/sip_personalmovimientosueldocontabledetResource.php
    - app/Http/Resources/Sip/sip_personalmovimientosueldosdetallesResource.php
    - app/Http/Resources/sip_personalmovimientosueldo/sip_personalmovimientosueldoResource.php
  service: [app/Services/PersonalMovimientoSueldoService.php]
  controller: [app/Http/Controllers/Api/Sincro_sip/sip_personalmovimientosueldoController.php]
  routes: [routes/api.php]
- model: sip_personalmovimientosueldocontable
  path: app/Models/dbsip/sip_personalmovimientosueldocontable.php
  connection: mysql_dbsip
  table: sip_personalmovimientosueldocontable
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  filter: [app/Filters/dbsip/sip_personalmovimientosueldocontableFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalmovimientosueldocontabledetResource.php
  controller_usado_en: [app/Http/Controllers/Api/Sip/sip_personalmovimientosueldocontabledetController.php, app/Http/Controllers/Api/Sip/sip_planillacontableController.php]
  routes: [routes/api.php]
- model: sip_personalmovimientosueldocontabledet
  path: app/Models/dbsip/sip_personalmovimientosueldocontabledet.php
  connection: mysql_dbsip
  table: sip_personalmovimientosueldocontabledet
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  relaciones:
    - tipoMovimientoSueldoContable: belongsTo sip_multitabladetalle (tipo_mov_sueldocont_id, pkid)
    - sueldocontable: belongsTo SipPersonalmovimientosueldocontable (sueldocontable_id, pkid)
  filter: [app/Filters/dbsip/sip_personalmovimientosueldocontabledetFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalmovimientosueldocontabledetResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_personalmovimientosueldocontabledetController.php]
  routes: [routes/api.php]
- model: sip_personalmovimientosueldodetalle
  path: app/Models/dbsip/sip_personalmovimientosueldodetalle.php
  connection: mysql_dbsip
  table: sip_personalmovimientosueldodetalle
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  service_usado_en: [app/Services/TardanzasService.php]
  controller_usado_en: [app/Http/Controllers/Api/Reports/sip_personalreportsController.php, app/Http/Controllers/Api/Reports/sip_personaltiendasreportsController.php, app/Http/Controllers/Api/Sip/sip_personalController.php, app/Http/Controllers/Api/Sip/sip_personalautorizacionpaController.php, ...]
  routes: [routes/api.php]
- model: sip_personalmovimientotienda
  path: app/Models/dbsip/sip_personalmovimientotienda.php
  connection: mysql_dbsip
  table: sip_personalmovimientotienda
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  resources:
    - app/Http/Resources/Sip/sip_personalmovimientotiendaResource.php
    - app/Http/Resources/sip_personalmovimientotienda/sip_personalmovimientotiendaResource.php
  service: [app/Services/PersonalMovimientoTiendaService.php]
  controller: [app/Http/Controllers/Api/Sincro_sip/sip_personalmovimientotiendaController.php, app/Http/Controllers/Api/Sip/sip_personalmovimientotiendaController.php]
  routes: [routes/api.php]
- model: sip_personalmovimientoturno
  path: app/Models/dbsip/sip_personalmovimientoturno.php
  connection: mysql_dbsip
  table: sip_personalmovimientoturno
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id]
  observer: true
  resources:
    - app/Http/Resources/Sip/sip_personalmovimientoturnoResource.php
    - app/Http/Resources/sip_personalmovimientoturno/sip_personalmovimientoturnoResource.php
  controller: [app/Http/Controllers/Api/Sincro_sip/sip_personalmovimientoturnoController.php]
  routes: [routes/api.php]
- model: sip_personalmovimientovacaciones
  path: app/Models/dbsip/sip_personalmovimientovacaciones.php
  connection: mysql_dbsip
  table: sip_personalmovimientovacaciones
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  observer: true
  relaciones:
    - sip_personal: belongsTo sip_personal (personal_id, pkid)
    - sip_periodovacacional: belongsTo sip_periodovacacional (periodovacacional_id, pkid)
    - tienda: belongsTo catalogo_tienda (tienda_id, pkid)
    - created_by: belongsTo usuarios (created_by_id, pkid)
    - updated_by: belongsTo usuarios (updated_by_id, pkid)
    - deleted_by: belongsTo usuarios (deleted_by_id, pkid)
  filter: [app/Filters/dbsip/sip_personalmovimientovacacionesFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalmovimientovacacionesResumenResource.php
  requests:
    - app/Http/Requests/Sip/Traits/sip_personalmovimientovacaciones/ValidatesPersonalmovimientovacaciones.php
    - app/Http/Requests/Sip/sip_personalmovimientovacaciones/ExportPersonalmovimientovacacionesRequest.php
    - app/Http/Requests/Sip/sip_personalmovimientovacaciones/StorePersonalmovimientovacacionesRequest.php
    - app/Http/Requests/Sip/sip_personalmovimientovacaciones/UpdatePersonalmovimientovacacionesRequest.php
  service: [app/Services/PersonalMovimientoVacacionesService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalmovimientovacacionesController.php]
  routes: [routes/modules/sip_personalmovimientovacaciones.php]
- model: sip_personalpivot
  path: app/Models/dbsip/sip_personalpivot.php
  connection: mysql_dbsip
  table: sip_personalpivot
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - sip_personal: belongsTo sip_personal (personal_id, pkid)
    - catalogo_tienda: belongsTo catalogo_tienda (tienda_id, pkid)
    - sip_personalcargos: belongsTo sip_personalcargos (cargo_id, pkid)
    - created_by: belongsTo usuarios (created_by_id, pkid)
    - updated_by: belongsTo usuarios (updated_by_id, pkid)
    - deleted_by: belongsTo usuarios (deleted_by_id, pkid)
  filter: [app/Filters/dbsip/sip_personalpivotFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalpivotResource.php
  service: [app/Services/PersonalPivotService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalpivotController.php]
  routes: [routes/modules/sip_personalpivot.php]
- model: sip_personalplanilla
  path: app/Models/dbsip/sip_personalplanilla.php
  connection: mysql_dbsip
  table: sip_personalplanilla
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  filter: [app/Filters/dbsip/sip_personalplanillaFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalplanillaDetResource.php
    - app/Http/Resources/Sip/sip_personalplanillaRelationResource.php
    - app/Http/Resources/Sip/sip_personalplanillaResource.php
    - app/Http/Resources/Sip/sip_personalplanillatdaBoletaResource.php
    - app/Http/Resources/Sip/sip_personalplanillatdaResource.php
  requests:
    - app/Http/Requests/Sip/sip_personalboletabeneficios/GenerarMacroCtsRequest.php
    - app/Http/Requests/Sip/sip_personalboletavacaciones/CerrarLoteRequest.php
    - app/Http/Requests/Sip/sip_personalboletavacaciones/GenerarMacroPlanillaRequest.php
  service_usado_en: [app/Services/PersonalBoletaBeneficiosService.php, app/Services/PersonalBoletaVacacionesService.php, app/Services/PersonalTiemposAsistenciaService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalplanillaController.php]
  routes: [routes/api.php]
- model: sip_personalplanillatda
  path: app/Models/dbsip/sip_personalplanillatda.php
  connection: mysql_dbsip
  table: sip_personalplanillatda
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  resources:
    - app/Http/Resources/Sip/sip_personalplanillatdaBoletaResource.php
    - app/Http/Resources/Sip/sip_personalplanillatdaResource.php
  service_usado_en: [app/Services/PersonalBoletaBeneficiosService.php, app/Services/PersonalBoletaVacacionesService.php, app/Services/PersonalTiemposAsistenciaService.php, app/Services/ProcesarCtsService.php, ...]
  controller_usado_en: [app/Http/Controllers/Api/Reports/sip_empresasreportsController.php, app/Http/Controllers/Api/Reports/sip_personalasistenciareportsController.php, app/Http/Controllers/Api/Reports/sip_personalhorarioreportsController.php, app/Http/Controllers/Api/Reports/sip_personalplanillareportsController.php, ...]
  routes: [routes/api.php]
- model: sip_personalprocesoadministrativo
  path: app/Models/dbsip/sip_personalprocesoadministrativo.php
  connection: mysql_dbsip
  table: sip_personalprocesoadministrativo
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  resources:
    - app/Http/Resources/sip_personalprocesoadministrativo/sip_personalprocesoadministrativoResource.php
  controller: [app/Http/Controllers/Api/Sincro_sip/sip_personalprocesoadministrativoController.php]
  routes: [routes/api.php]
- model: sip_personalprocesosaudit
  path: app/Models/dbsip/sip_personalprocesosaudit.php
  connection: mysql_dbsip
  table: sip_personalprocesosaudit
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: no
  has_factory: false
  auditoria: [created_by_id]
  service_usado_en: [app/Services/TardanzasService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalprocesosauditController.php]
  routes: [routes/api.php]
- model: sip_personalrelacion
  path: app/Models/dbsip/sip_personalrelacion.php
  connection: mysql_dbsip
  table: sip_personalrelacion
  pk: {name: pkid, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  controller_usado_en: [app/Http/Controllers/Api/Sip/sip_personalController.php, app/Http/Controllers/Api/Sip/sip_personaltiemposasistenciaController.php]
  routes: [routes/api.php]
- model: sip_personalsolicitudLiquidaciones
  path: app/Models/dbsip/sip_personalsolicitudLiquidaciones.php
  connection: mysql_dbsip
  table: sip_personalsolicitudLiquidaciones
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  resources:
    - app/Http/Resources/Sip/sip_personalsolicitudLiquidacionesResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_personalsolicitudLiquidacionesController.php]
  routes: [routes/api.php]
- model: sip_personalsolicitudespremiacion
  path: app/Models/dbsip/sip_personalsolicitudespremiacion.php
  connection: mysql_dbsip
  table: sip_personalsolicitudespremiacion
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  resources:
    - app/Http/Resources/Sip/sip_personalsolicitudespremiacionListResource.php
    - app/Http/Resources/Sip/sip_personalsolicitudespremiacionRelationResource.php
    - app/Http/Resources/Sip/sip_personalsolicitudespremiacionResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_personalsolicitudespremiacionController.php]
  routes: [routes/api.php]
- model: sip_personaltiempos
  path: app/Models/dbsip/sip_personaltiempos.php
  connection: mysql_dbsip
  table: sip_personaltiempos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  resources:
    - app/Http/Resources/Sip/sip_personaltiemposasistencia2Resource.php
    - app/Http/Resources/Sip/sip_personaltiemposasistenciaResource.php
  controller_usado_en: [app/Http/Controllers/Api/Reports/sip_personalasistenciareportsController.php, app/Http/Controllers/Api/Sig/sip_tiemposasistenciaController.php, app/Http/Controllers/Api/Sip/sip_personalplanillaController.php, app/Http/Controllers/Api/Sip/sip_personaltiemposasistenciaController.php, ...]
  routes: [routes/api.php]
- model: sip_personaltiemposasistencia
  path: app/Models/dbsip/sip_personaltiemposasistencia.php
  connection: mysql_dbsip
  table: sip_personaltiemposasistencia
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  filter: [app/Filters/dbsip/sip_personaltiemposasistenciaFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personaltiemposasistencia2Resource.php
    - app/Http/Resources/Sip/sip_personaltiemposasistenciaResource.php
  service: [app/Services/PersonalTiemposAsistenciaService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personaltiemposasistenciaController.php]
  routes: [routes/api.php]
- model: sip_personalvacacionestruncas
  path: app/Models/dbsip/sip_personalvacacionestruncas.php
  connection: mysql_dbsip
  table: sip_personalvacacionestruncas
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - sip_personal: belongsTo sip_personal (personal_id)
    - sip_periodovacacional: belongsTo sip_periodovacacional (periodovacacional_id)
  service: [app/Services/PersonalVacacionesTruncasService.php]
- model: sip_personalvacacionesylicencias
  path: app/Models/dbsip/sip_personalvacacionesylicencias.php
  connection: mysql_dbsip
  table: sip_personalvacacionesylicencias
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  filter: [app/Filters/dbsip/sip_personalvacacionesylicenciasFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalvacacionesylicenciasResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_personalvacacionesylicenciasController.php]
  routes: [routes/api.php]
- model: sip_personalventavacaciones
  path: app/Models/dbsip/sip_personalventavacaciones.php
  connection: mysql_dbsip
  table: sip_personalventavacaciones
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  relaciones:
    - sip_personal: belongsTo sip_personal (personal_id, pkid)
    - sip_periodovacacional: belongsTo sip_periodovacacional (periodovacacional_id, pkid)
    - catalogo_tienda: belongsTo catalogo_tienda (tienda_id, pkid)
  filter: [app/Filters/dbsip/sip_personalventavacacionesFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_personalventavacacionesResource.php
  service: [app/Services/PersonalVentaVacacionesService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalventavacacionesController.php]
  routes: [routes/modules/sip_personalventavacaciones.php]
- model: sip_personalzonal
  path: app/Models/dbsip/sip_personalzonal.php
  connection: mysql_dbsip
  table: sip_personalzonal
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  resources:
    - app/Http/Resources/Sip/sip_personalzonalResource.php
  service_usado_en: [app/Services/PersonalTiemposAsistenciaService.php, app/Services/PersonalmovimientosconsumoService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_personalzonalController.php]
  routes: [routes/api.php]
- model: sip_planillacontable
  path: app/Models/dbsip/sip_planillacontable.php
  connection: mysql_dbsip
  table: sip_planillacontable
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  filter: [app/Filters/dbsip/sip_planillacontableFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_planillacontableResource.php
    - app/Http/Resources/Sip/sip_planillacontableper_detResource.php
    - app/Http/Resources/Sip/sip_planillacontablepersonalResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_planillacontableController.php]
  routes: [routes/api.php]
- model: sip_planillacontableper_det
  path: app/Models/dbsip/sip_planillacontableper_det.php
  connection: mysql_dbsip
  table: sip_planillacontableper_det
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  relaciones:
    - sip_planillacontablepersonal: belongsTo sip_planillacontablepersonal (planillacontablepersonal_id, pkid)
    - tipoMovimientoPlanilla: belongsTo sip_tipomovimientoplanilla (tipomovimientoplanilla_id, pkid)
  filter: [app/Filters/dbsip/sip_planillacontableper_detFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_planillacontableper_detResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_planillacontableper_detController.php]
  routes: [routes/api.php]
- model: sip_planillacontablepersonal
  path: app/Models/dbsip/sip_planillacontablepersonal.php
  connection: mysql_dbsip
  table: sip_planillacontablepersonal
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  relaciones:
    - sip_planillacontable: belongsTo sip_planillacontable (planillacontable_id, pkid)
    - sip_personal: hasOne sip_personal (pkid, personal_id)
  filter: [app/Filters/dbsip/sip_planillacontablepersonalFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_planillacontablepersonalResource.php
  service_usado_en: [app/Services/CalcularCtsService.php, app/Services/ProcesarCtsService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_planillacontablepersonalController.php]
  routes: [routes/api.php]
- model: sip_procesos_jobs
  path: app/Models/dbsip/sip_procesos_jobs.php
  connection: mysql_dbsip
  table: sip_procesos_jobs
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  filter: [app/Filters/dbsip/sip_procesos_jobsFilters.php]
  controller: [app/Http/Controllers/Api/Sip/sip_procesos_jobsController.php]
  routes: [routes/api.php, routes/modules/sip_personalboletabeneficios.php]
- model: sip_procesosaudit
  path: app/Models/dbsip/sip_procesosaudit.php
  connection: mysql_dbsip
  table: sip_procesosaudit
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: [created_by_id]
  relaciones:
    - created_by: belongsTo usuarios (created_by_id, pkid)
  filter: [app/Filters/dbsip/sip_procesosauditFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_procesosauditResource.php
  service_usado_en: [app/Services/CrudService.php, app/Services/PersonalSegurosService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_procesosauditController.php]
  routes: [routes/api.php]
- model: sip_regimenlaboral
  path: app/Models/dbsip/sip_regimenlaboral.php
  connection: mysql_dbsip
  table: sip_regimenlaboral
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  controller: [app/Http/Controllers/Api/Sip/sip_regimenlaboralController.php]
  routes: [routes/api.php]
- model: sip_solicitudvacaciones
  path: app/Models/dbsip/sip_solicitudvacaciones.php
  connection: mysql_dbsip
  table: sip_solicitudvacaciones
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  observer: true
  relaciones:
    - legajo: belongsTo sip_personalmovimientolegajosdet (legajo_id, pkid)
    - sip_periodovacacional: belongsTo sip_periodovacacional (periodovacacional_id, pkid)
    - sip_personal: belongsTo sip_personal (personal_id, pkid)
    - tienda: belongsTo catalogo_tienda (tienda_id, pkid)
    - sip_personalboletapago: hasMany sip_personalboletapago (solicitud_vacaciones_id, pkid)
    - sip_personalboletavacaciones: hasMany sip_personalboletavacaciones (solicitud_vacaciones_id, pkid)
    - createdBy: belongsTo usuarios (created_by_id, pkid)
    - updatedBy: belongsTo usuarios (updated_by_id, pkid)
    - deletedBy: belongsTo usuarios (deleted_by_id, pkid)
  filter: [app/Filters/dbsip/sip_solicitudvacacionesFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_solicitudvacacionesPendientesResource.php
    - app/Http/Resources/Sip/sip_solicitudvacacionesRelationResource.php
    - app/Http/Resources/Sip/sip_solicitudvacacionesResource.php
  requests:
    - app/Http/Requests/Sip/Traits/sip_solicitudvacaciones/ValidatesSolicitudVacaciones.php
    - app/Http/Requests/Sip/sip_solicitudvacaciones/AutorizarSolicitudVacacionesRequest.php
    - app/Http/Requests/Sip/sip_solicitudvacaciones/BulkSolicitudVacacionesRequest.php
    - app/Http/Requests/Sip/sip_solicitudvacaciones/StoreSolicitudVacacionesRequest.php
    - app/Http/Requests/Sip/sip_solicitudvacaciones/UpdateEstadoSolicitudVacacionesRequest.php
    - app/Http/Requests/Sip/sip_solicitudvacaciones/UpdateSolicitudVacacionesRequest.php
  service: [app/Services/SolicitudVacacionesService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_solicitudvacacionesController.php]
  routes: [routes/modules/sip_solicitudvacaciones.php]
- model: sip_temp_tiempos
  path: app/Models/dbsip/sip_temp_tiempos.php
  connection: mysql_dbsip
  table: sip_temp_tiempos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: no
  has_factory: true
  auditoria: []
  relaciones:
    - sip_personal: hasOne sip_personal (codigo, codper)
  controller_usado_en: [app/Http/Controllers/Api/Sig/sip_tiemposasistenciaController.php]
  routes: [routes/api.php]
- model: sip_terminales_biometricos
  path: app/Models/dbsip/sip_terminales_biometricos.php
  connection: mysql_dbsip
  table: sip_terminales_biometricos
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: true}
  soft_delete: no
  has_factory: true
  auditoria: [updated_by_id]
  relaciones:
    - tienda_by_codigo: belongsTo catalogo_tienda (idtienda, codigo)
    - tienda: belongsTo catalogo_tienda (tienda_id, pkid)
  resources:
    - app/Http/Resources/Sip/sip_terminales_biometricosResource.php
  controller_usado_en: [app/Http/Controllers/Api/Sip/sip_maestroslectoresController.php, app/Http/Controllers/Api/Sun/sun_consultaboletaController.php]
  routes: [routes/api.php, routes/modules/terminalesbiometricos.php]
- model: sip_tiempos_configuracion
  path: app/Models/dbsip/sip_tiempos_configuracion.php
  connection: mysql_dbsip
  table: sip_tiempos_configuracion
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: no
  has_factory: true
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Sig/sip_tiemposasistenciaController.php]
  routes: [routes/api.php]
- model: sip_tiendacargo
  path: app/Models/dbsip/sip_tiendacargo.php
  connection: mysql_dbsip
  table: sip_tiendacargo
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  relaciones:
    - catalogo_tienda: hasOne catalogo_tienda (pkid, tienda_id)
  filter: [app/Filters/dbsip/sip_tiendacargoFilter.php]
  resources:
    - app/Http/Resources/Sip/sip_tiendacargoResource.php
  service_usado_en: [app/Services/EstandarPersonalService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_tiendacargoController.php]
  routes: [routes/api.php, routes/modules/tiendacargo.php]
- model: sip_tiendaoperaciones
  path: app/Models/dbsip/sip_tiendaoperaciones.php
  connection: mysql_dbsip
  table: sip_tiendaoperaciones
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: []
  controller: [app/Http/Controllers/Api/Sip/sip_tiendaoperacionesController.php]
  routes: [routes/api.php]
- model: sip_tipodocumentoidentidad
  path: app/Models/dbsip/sip_tipodocumentoidentidad.php
  connection: mysql_dbsip
  table: sip_tipodocumentoidentidad
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Reports/sip_personalreportsController.php, app/Http/Controllers/Api/Sip/sip_multitablaController.php, app/Http/Controllers/Api/Sip/sip_personalController.php, app/Http/Controllers/Api/Sip/sip_tiposdocumentosController.php]
  routes: [routes/api.php]
- model: sip_tipolegajos
  path: app/Models/dbsip/sip_tipolegajos.php
  connection: mysql_dbsip
  table: sip_tipolegajos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  filter: [app/Filters/dbsip/sip_tipolegajosFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_tipolegajosResource.php
  service_usado_en: [app/Services/TipoLegajoService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_tipolegajosController.php]
  routes: [routes/api.php]
- model: sip_tipomovimiento
  path: app/Models/dbsip/sip_tipomovimiento.php
  connection: mysql_dbsip
  table: sip_tipomovimiento
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  resources:
    - app/Http/Resources/Sip/sip_tipomovimientoResource.php
    - app/Http/Resources/Sip/sip_tipomovimientodataResource.php
    - app/Http/Resources/Sip/sip_tipomovimientoplanillaResource.php
  service: [app/Services/TipoMovimientoService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_tipomovimientoController.php]
  routes: [routes/api.php, routes/modules/sip_tipomovimiento.php]
- model: sip_tipomovimientoplanilla
  path: app/Models/dbsip/sip_tipomovimientoplanilla.php
  connection: mysql_dbsip
  table: sip_tipomovimientoplanilla
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  relaciones:
    - sip_planillacontableper_det: belongsTo sip_planillacontableper_det (pkid, tipomovimientoplanilla_id)
  filter: [app/Filters/dbsip/sip_tipomovimientoplanillaFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_tipomovimientoplanillaResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_tipomovimientoplanillaController.php]
  routes: [routes/api.php]
- model: sip_tipoplanillatiendas
  path: app/Models/dbsip/sip_tipoplanillatiendas.php
  connection: mysql_dbsip
  table: sip_tipoplanillatiendas
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  observer: true
  filter: [app/Filters/dbsip/sip_tipoplanillatiendasFilters.php]
  resources:
    - app/Http/Resources/Sip/sip_tipoplanillatiendasResource.php
  service_usado_en: [app/Services/ProcesarCtsService.php]
  controller: [app/Http/Controllers/Api/Sip/sip_tipoplanillatiendasController.php]
  routes: [routes/api.php, routes/modules/sip_personalboletabeneficios.php]
- model: sip_usuariosexternos
  path: app/Models/dbsip/sip_usuariosexternos.php
  connection: mysql_dbsip
  table: sip_usuariosexternos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  controller: [app/Http/Controllers/Api/Sip/sip_usuariosexternoscontroller.php]
  routes: [routes/api.php]
- model: sip_zonalmovimientozona
  path: app/Models/dbsip/sip_zonalmovimientozona.php
  connection: mysql_dbsip
  table: sip_zonalmovimientozona
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  resources:
    - app/Http/Resources/Sip/sip_zonalmovimientozonaResource.php
  controller: [app/Http/Controllers/Api/Sip/sip_zonalmovimientozonaController.php]
  routes: [routes/api.php]
```
