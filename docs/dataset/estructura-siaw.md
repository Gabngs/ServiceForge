# Estructura del backend SIAW (siaw-laravel-backend)

Mapa de **niveles de carpetas, convenciones de nombres y ubicación de archivos** de SIAW. Sirve para:

1. que el generador ubique cada archivo dentro de la estructura propia del proyecto (ver [correcciones-generador.md §0 y §8](correcciones-generador.md));
2. **actualizar el dataset del matching** en una PC que no tiene el repo, con el anexo YAML del final.

| Dato | Valor |
|---|---|
| Ruta en la PC de origen | `C:\Users\programador01\Documents\visual code\siaw-laravel-backend` |
| Commit escaneado | `3edf818` (21-09-2026) |
| Stack | PHP ^8.2 · Laravel ^12.0 · `essa/api-tool-kit` ^1.1 (Filters, `ApiResponse`, `dynamicPaginate`) |
| Conexiones (`config/database.php`) | `mysql`, `mysql_dbsiaw`, `mysql_dbsip`, `mariadb`, `pgsql`, `sqlsrv`, `sqlite` |
| Modelos escaneados | 91 (62 `dbsiaw`, 23 `Sap`, 5 `dbsip`, 1 `User`) |

---

## 1. Árbol de niveles (solo lo relevante para el patrón)

```
app/
├── Models/
│   ├── User.php                      Authenticatable, tabla catalogo_usuario, conexión mysql_dbsiaw
│   ├── dbsiaw/{tabla}.php            ← modelo estándar (62)            conexión mysql_dbsiaw
│   ├── dbsip/{tabla}.php             ← tablas de SIREH leídas desde SIAW (5), conexión mysql_dbsip
│   ├── Sap/{NombreCamel}.php         ← FUERA DE PATRÓN: CamelCase (SapBusinessPartner, ...)
│   └── dbcatalogo/                   ⚠ VACÍA: resto del generador, ignorar
├── Filters/
│   ├── dbsiaw/{tabla}Filters.php     ← extends QueryFilters
│   └── Sap/{NombreCamel}Filters.php
├── Http/
│   ├── Controllers/
│   │   ├── Controller.php
│   │   └── Api/
│   │       ├── {tabla}Controller.php          ← LEGADO: 19 controllers en la raíz de Api (catalogo_articulos, catalogo_tienda, ...)
│   │       ├── dbsiaw/{tabla}Controller.php   ← PATRÓN ACTUAL (37)
│   │       ├── Sap/{NombreCamel}Controller.php
│   │       ├── api_externa/                   endpoints para terceros (routes/external.php)
│   │       ├── sincronizacion/
│   │       └── Catalogo/                      ⚠ VACÍA: resto del generador
│   ├── Request/                      ← OJO: "Request" en SINGULAR
│   │   ├── dbsiaw/
│   │   │   ├── {tabla}/                           ← PATRÓN ACTUAL (carpeta por tabla, 21 tablas)
│   │   │   │   ├── Base{tabla}Request.php         abstract, authorize() + messages()
│   │   │   │   ├── Store{tabla}Request.php        extends Base, use Validates{Tabla}
│   │   │   │   ├── Update{tabla}Request.php       extends Base, use Validates{Tabla}
│   │   │   │   └── {Accion}{tabla}Request.php     extras: Import, Bulk, Get...External
│   │   │   ├── Traits/{tabla}/Validates{Tabla}.php   getRelacionesRules($required) + getRelacionesMensajes()
│   │   │   ├── Base{tabla}Request.php             ← LEGADO: plano, sin carpeta (15 tablas)
│   │   │   ├── Store{tabla}Request.php
│   │   │   └── Update{tabla}Request.php
│   │   └── Sap/{Base|Store|Update|Bulk}{NombreCamel}Request.php
│   ├── Requests/Catalogo/...         ⚠ VACÍA: resto del generador (en plural), ignorar
│   ├── Resources/
│   │   ├── dbsiaw/                   ← todos los resources de un sistema en una sola carpeta (90)
│   │   │   ├── {tabla}Resource.php
│   │   │   ├── {tabla}RelationResource.php    forma mínima para anidar en otros resources
│   │   │   └── {tabla}TinyResource.php        respuesta con ?tiny=true
│   │   ├── Sap/
│   │   └── Catalogo/                 ⚠ VACÍA
│   ├── Traits/{tabla}/{Nombre}ResponseTrait.php   poco usado (catalogo_articulos, catalogo_tienda)
│   ├── Middleware/ApiToken.php, ApiExternalToken.php
│   └── Token.php                     Token::user() = session('user') → ->pkid
├── Services/
│   ├── CrudService.php               create/update/delete/bulkInsert/find + mapUuidsToPkids(+Bulk) + auditoría
│   ├── {tabla}Service.php            ← PATRÓN: nombre = tabla literal (catalogo_parametrosistemaService)
│   ├── {NombreCamel}Service.php      ← FUERA DE PATRÓN: AuthpermissionService, Sap*Service, NotificacionService ...
│   └── Sap/
├── Exports/{dbsiaw|Sap}/  Imports/dbsiaw/  Jobs/Sap/  Support/  Enums/
routes/
├── api.php                           rutas legadas en línea (Route::middleware([ApiToken::class])->apiResource(...))
├── {tabla}.php                       ← PATRÓN: un archivo por módulo (catalogo_parametrosistema.php, ...)
├── external.php, download.php, web.php, console.php
└── modules/                          ⚠ VACÍA: nada la carga, ignorar
app/Providers/RouteServiceProvider.php   ← registra CADA routes/{tabla}.php con middleware('api')->prefix('api')
```

---

## 2. Convenciones de nombres (patrón actual)

Con `{tabla}` = nombre literal de la tabla en snake (`catalogo_parametrosistema`) y `{Tabla}` = la misma cadena con la primera letra en mayúscula (`Catalogo_parametrosistema`, se usa en los traits):

| Tipo | Namespace | Clase | Archivo |
|---|---|---|---|
| Model | `App\Models\dbsiaw` | `{tabla}` | `app/Models/dbsiaw/{tabla}.php` |
| Filter | `App\Filters\dbsiaw` | `{tabla}Filters` | `app/Filters/dbsiaw/{tabla}Filters.php` |
| Base Request | `App\Http\Request\dbsiaw\{tabla}` | `Base{tabla}Request` (abstract) | `app/Http/Request/dbsiaw/{tabla}/Base{tabla}Request.php` |
| Store Request | ídem | `Store{tabla}Request` | `.../{tabla}/Store{tabla}Request.php` |
| Update Request | ídem | `Update{tabla}Request` | `.../{tabla}/Update{tabla}Request.php` |
| Request trait | `App\Http\Request\dbsiaw\Traits\{tabla}` | `Validates{Tabla}` | `app/Http/Request/dbsiaw/Traits/{tabla}/Validates{Tabla}.php` |
| Resource | `App\Http\Resources\dbsiaw` | `{tabla}Resource` | `app/Http/Resources/dbsiaw/{tabla}Resource.php` |
| Relation Resource | ídem | `{tabla}RelationResource` | `app/Http/Resources/dbsiaw/{tabla}RelationResource.php` |
| Tiny Resource | ídem | `{tabla}TinyResource` | `app/Http/Resources/dbsiaw/{tabla}TinyResource.php` |
| Service | `App\Services` | `{tabla}Service` | `app/Services/{tabla}Service.php` |
| Controller | `App\Http\Controllers\Api\dbsiaw` | `{tabla}Controller` | `app/Http/Controllers/Api/dbsiaw/{tabla}Controller.php` |
| Route | — | — | `routes/{tabla}.php` + entrada en `RouteServiceProvider::boot()` |

Sufijos de Resource que aparecen en el repo: base `Resource` (68), `RelationResource` (23), `TinyResource` (2), `RelacionResource` (1), `_fullResource` (1), `WhiteResource` (1).

---

## 3. Particularidades de datos que el generador debe respetar

### 3.1 Doble identificador `pkid` + `id`

- Casi todas las tablas tienen `pkid` (int autoincremental, usado como **destino de las FK**) e `id` (UUID string, **expuesto al frontend**).
- Las relaciones van contra `pkid`: `belongsTo(catalogo_tiposistema::class, 'tipo_sistema_id', 'pkid')`.
- El frontend envía UUID. El Service los convierte con `CrudService::mapUuidsToPkids($data, $this->uuidMapping)`, y el Filter hace lo mismo a mano (`Model::where('id', $value)->value('pkid')`).
- `$primaryKey` varía entre modelos:
  - `id` (63): string, `$incrementing = false`, `$keyType = 'string'` en 15 de ellos;
  - `pkid` (21);
  - otros (`code`, `bank_code`, `group_number`) en Sap.
- Generación del id: los servicios nuevos usan `str_replace('-', '', Str::uuid()->toString())` (char(32)). **En el generador es una opción, no un default** (ver correcciones §2).

### 3.2 Soft delete

- `SoftDeletes` con `deleted_at`: 52 modelos.
- `SoftDeletes` + `const DELETED_AT = 'deleted'`: **9 modelos**, tablas heredadas de Django: `catalogo_empresa`, `catalogo_empresatienda`, `catalogo_groupextension`, `catalogo_parametrosistema`, `catalogo_tienda`, `catalogo_tiposistema`, `catalogo_turnos`, `catalogo_ubigeo`, `catalogo_usuario`.
  `User` declara `DELETED_AT='deleted'` pero no usa el trait.
- Sin soft delete: 29.
- De esas 9, **6 no tienen `deleted_by_id`**; solo lo tienen `catalogo_empresa`, `catalogo_empresatienda` y `catalogo_tienda`. Por eso hay que mirar la columna, no suponerla.

### 3.3 Auditoría y usuario

- Columnas en `$fillable`:
  - `created_by_id, updated_by_id, deleted_by_id`: 42 modelos;
  - solo `created_by_id, updated_by_id`: 16;
  - ninguna: 31.
- `CrudService::create/update/delete` rellena esos campos con `Token::user()->pkid`. Además, si se le pasa `$proceso`, audita en `catalogo_procesosaudit`.
- El modelo de usuario **no es uniforme**, y el nombre de la relación tampoco:

  | Relación | Destino | Modelos |
  |---|---|---|
  | `created_by` / `updated_by` / `deleted_by` | `App\Models\User` | ~13 |
  | `create_by` / `update_by` / `delete_by` | `catalogo_usuario` | 9 |
  | `created_by` / `updated_by` / `deleted_by` | `catalogo_usuario` | 6 |
  | `createdBy` / `updatedBy` / `deletedBy` | `User` | 3 |

- `App\Models\dbsiaw\catalogo_usuario`: PK `pkid`, `DELETED_AT = 'deleted'`, tabla `catalogo_usuario`.
- Resources de usuario disponibles en `Resources/dbsiaw`: `catalogo_usuarioRelationResource` (el que usan los módulos nuevos), `catalogo_usuarioResource`, `catalogo_usuario_fullResource`, `catalogo_usuarioWhiteResource`.

### 3.4 Filters (essa/api-tool-kit)

- El modelo usa `Filterable` y declara `protected string $default_filters = {tabla}Filters::class;`.
- En el Filter: `$columnSearch`, `$allowedFilters`, `$allowedIncludes`, `$allowedSorts`, y un método por cada FK filtrable que convierte UUID → pkid.
- Service: `{tabla}::useFilters()->with(self::RELATIONS)`, y luego `dynamicPaginate()` o `get()`.

### 3.5 Controller

- `use ApiResponse;`, el Service inyectado por constructor, y respuestas con `responseSuccess('mensaje', Resource)`.
- `index` con `paginate` opcional (añade `meta`) y `tiny` opcional.
- Anotaciones OpenAPI (`@OA\...`) en cada método y `@OA\Schema` en los Resources.
- `destroy` suele estar **comentado** “por indicación” en los catálogos.

### 3.6 Rutas

```php
// routes/{tabla}.php
Route::middleware([ApiToken::class])->group(function () {
    Route::apiResource('{tabla}', {tabla}Controller::class)
        ->parameters(['{tabla}' => '{tabla}']);
});
```

```php
// app/Providers/RouteServiceProvider.php → boot() → $this->routes(...)
Route::middleware('api')->prefix('api')->group(base_path('routes/{tabla}.php'));
```

`RouteServiceProvider` tiene hoy 45 registros. Algunos módulos legados siguen en línea en `routes/api.php` (74 rutas).

---

## 4. Casos fuera de patrón (el generador **no** debe tomarlos como estándar, pero sí reconocerlos)

| Caso | Dónde | Cómo reconocerlo |
|---|---|---|
| Controllers en la raíz de `Api/` | 19 archivos (`catalogo_articulosController`, `catalogo_tiendaController`, …) | Mismo nombre `{tabla}Controller`, namespace `App\Http\Controllers\Api` |
| Requests planos sin carpeta por tabla | 15 tablas (`Basecatalogo_almacartRequest`, `Storecatalogo_preciartRequest`, …) | `app/Http/Request/dbsiaw/{Accion}{tabla}Request.php` |
| Requests con nombre abreviado | `StorecatalogBlockedpermissionsRequest`, `StorecatalogWhitelistedusersRequest` | prefijo `catalog` en vez de `catalogo_` |
| Módulo SAP en CamelCase | Models, Filters, Requests, Resources, Controllers y Services bajo `Sap/` | `SapBusinessPartner`, `SapBusinessPartnerController`, ... |
| Services CamelCase | `AuthpermissionService`, `DjangoContentTypeService`, `NotificacionService`, `PermissionGuardService`, ... | sin prefijo de tabla |
| Tablas de SIREH en SIAW | `app/Models/dbsip/*` (5) | conexión `mysql_dbsip` |
| Carpetas vacías del generador | `Models/dbcatalogo`, `Http/Requests/Catalogo`, `Resources/Catalogo`, `Controllers/Api/Catalogo`, `routes/modules` | sin archivos `.php` |

---

## 5. Regla de ubicación para una tabla nueva `{tabla}` en SIAW

1. Model → `app/Models/dbsiaw/{tabla}.php`, con la `$connection` que elija el usuario (normalmente `mysql_dbsiaw`).
2. Filter → `app/Filters/dbsiaw/{tabla}Filters.php`.
3. Requests → `app/Http/Request/dbsiaw/{tabla}/{Base|Store|Update}{tabla}Request.php` + `app/Http/Request/dbsiaw/Traits/{tabla}/Validates{Tabla}.php`.
4. Resources → `app/Http/Resources/dbsiaw/{tabla}Resource.php` (+ `RelationResource`, + `TinyResource` si se activa tiny).
5. Service → `app/Services/{tabla}Service.php`.
6. Controller → `app/Http/Controllers/Api/dbsiaw/{tabla}Controller.php`.
7. Route → `routes/{tabla}.php` + registro en `RouteServiceProvider`.

---

## Anexo: mapeo por modelo

Generado escaneando el repo en el commit `3edf818`.

**Cómo se armó cada campo:**

- `path`, `connection`, `table`, `pk`, `soft_delete`, `has_factory`, `auditoria`, `relaciones`: leídos del archivo del modelo.
- `filter`: el `$default_filters` del modelo, o el que coincide por nombre.
- `resources`: los Resources cuyo nombre empieza por el del modelo.
- `requests`: por carpeta `/{tabla}/` o por nombre de clase.
- `service` / `controller`: los que coinciden por nombre (sin prefijo `catalogo_`/`sip_`, comparando sin `_`).
  Si ninguno coincide, se listan como `*_usado_en`: archivos que lo importan, **no** sus dueños.
- `routes`: archivos de `routes/` que importan el controller.

**Valores:**

- `soft_delete`: `deleted_at`, `deleted` (hay `const DELETED_AT='deleted'`) o `no`.
- `pk.incrementing: default`: el modelo no declara `$incrementing`, así que vale `true`.

Este bloque es YAML válido (lista de modelos) y se puede parsear directamente para armar pares positivos modelo → archivo.

```yaml
- model: ProveedoresSap
  path: app/Models/Sap/ProveedoresSap.php
  connection: mysql_dbsiaw
  table: proveedores_sap
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
- model: SapAddressIdentifier
  path: app/Models/Sap/SapAddressIdentifier.php
  connection: mysql_dbsiaw
  table: sap_address_identifiers
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
  relaciones:
    - address: belongsTo SapBusinessPartnerAddress (address_pkid, pkid)
    - empresaConfig: belongsTo SapEmpresaConfig (sap_empresa_config_pkid, pkid)
  service_usado_en: [app/Services/SapBusinessPartnerService.php]
- model: SapBank
  path: app/Models/Sap/SapBank.php
  connection: mysql_dbsiaw
  table: sap_banks
  pk: {name: bank_code, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Sap/SapMasterDataController.php]
  routes: [routes/sap_master_data.php]
- model: SapBankIdentifier
  path: app/Models/Sap/SapBankIdentifier.php
  connection: mysql_dbsiaw
  table: sap_bank_identifiers
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
  relaciones:
    - bank: belongsTo SapBusinessPartnerBank (bank_pkid, pkid)
    - empresaConfig: belongsTo SapEmpresaConfig (sap_empresa_config_pkid, pkid)
  service_usado_en: [app/Services/SapBusinessPartnerService.php]
- model: SapBpGroup
  path: app/Models/Sap/SapBpGroup.php
  connection: mysql_dbsiaw
  table: sap_bp_groups
  pk: {name: code, incrementing: false, keyType: int, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
  service_usado_en: [app/Services/SapBusinessPartnerService.php, app/Services/catalogo_solicitud_proveedorService.php]
  controller_usado_en: [app/Http/Controllers/Api/Sap/SapMasterDataController.php]
  routes: [routes/sap_master_data.php]
- model: SapBusinessPartner
  path: app/Models/Sap/SapBusinessPartner.php
  connection: mysql_dbsiaw
  table: sap_businesspartners
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: false
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - companies: hasMany SapBusinessPartnerCompany (sap_businesspartner_pkid, pkid)
    - empresas: hasMany SapBusinessPartnerEmpresa (sap_businesspartner_pkid, pkid)
    - addresses: hasMany SapBusinessPartnerAddress (sap_businesspartner_pkid, pkid)
    - banks: hasMany SapBusinessPartnerBank (sap_businesspartner_pkid, pkid)
    - contacts: hasMany SapBusinessPartnerContact (businesspartner_id, pkid)
    - salesPersonAssignments: hasMany SapBusinessPartnerSalesPerson (businesspartner_pkid, pkid)
    - salesPersons: belongsToMany SapSalesPerson (sap_businesspartner_salespersons, businesspartner_pkid)
    - solicitudProveedor: hasOne catalogo_solicitud_proveedor (business_partner_id, pkid)
    - solicitudes: hasMany catalogo_solicitud_proveedor (business_partner_id, pkid)
    - createdBy: belongsTo User (created_by_id, pkid)
    - updatedBy: belongsTo User (updated_by_id, pkid)
  filter: [app/Filters/Sap/SapBusinessPartnerFilters.php]
  resources:
    - app/Http/Resources/Sap/SapBusinessPartnerAddressResource.php
    - app/Http/Resources/Sap/SapBusinessPartnerBankResource.php
    - app/Http/Resources/Sap/SapBusinessPartnerCompanyResource.php
    - app/Http/Resources/Sap/SapBusinessPartnerContactRelationResource.php
    - app/Http/Resources/Sap/SapBusinessPartnerContactResource.php
    - app/Http/Resources/Sap/SapBusinessPartnerResource.php
    - app/Http/Resources/Sap/SapBusinessPartnerSalesPersonResource.php
  requests:
    - app/Http/Request/Sap/BaseSapBusinessPartnerRequest.php
    - app/Http/Request/Sap/StoreSapBusinessPartnerRequest.php
    - app/Http/Request/Sap/UpdateSapBusinessPartnerRequest.php
  service: [app/Services/SapBusinessPartnerService.php]
  controller: [app/Http/Controllers/Api/Sap/SapBusinessPartnerController.php]
  routes: [routes/sap_businesspartners.php, routes/sap_sync_master.php]
- model: SapBusinessPartnerAddress
  path: app/Models/Sap/SapBusinessPartnerAddress.php
  connection: mysql_dbsiaw
  table: sap_businesspartner_addresses
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: false
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - businessPartner: belongsTo SapBusinessPartner (sap_businesspartner_pkid, pkid)
    - sapIdentifiers: hasMany SapAddressIdentifier (address_pkid, pkid)
  resources:
    - app/Http/Resources/Sap/SapBusinessPartnerAddressResource.php
- model: SapBusinessPartnerBank
  path: app/Models/Sap/SapBusinessPartnerBank.php
  connection: mysql_dbsiaw
  table: sap_businesspartner_banks
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: false
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - businessPartner: belongsTo SapBusinessPartner (sap_businesspartner_pkid, pkid)
    - sapIdentifiers: hasMany SapBankIdentifier (bank_pkid, pkid)
  resources:
    - app/Http/Resources/Sap/SapBusinessPartnerBankResource.php
- model: SapBusinessPartnerCompany
  path: app/Models/Sap/SapBusinessPartnerCompany.php
  connection: mysql_dbsiaw
  table: sap_businesspartner_companies
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: false
  auditoria: []
  relaciones:
    - businessPartner: belongsTo SapBusinessPartner (sap_businesspartner_pkid, pkid)
    - empresaConfig: belongsTo SapEmpresaConfig (sap_empresa_config_pkid, pkid)
  resources:
    - app/Http/Resources/Sap/SapBusinessPartnerCompanyResource.php
  service_usado_en: [app/Services/Sap/SapSyncDispatcher.php, app/Services/SapBusinessPartnerService.php, app/Services/catalogo_solicitud_proveedorService.php]
  controller_usado_en: [app/Http/Controllers/Api/Sap/SapBusinessPartnerController.php]
  routes: [routes/sap_businesspartners.php]
- model: SapBusinessPartnerContact
  path: app/Models/Sap/SapBusinessPartnerContact.php
  connection: mysql_dbsiaw
  table: sap_businesspartner_contacts
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: false
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - businessPartner: belongsTo SapBusinessPartner (businesspartner_id, pkid)
    - created_by: belongsTo User (created_by_id)
    - updated_by: belongsTo User (updated_by_id)
    - deleted_by: belongsTo User (deleted_by_id)
  filter: [app/Filters/Sap/SapBusinessPartnerContactFilters.php]
  resources:
    - app/Http/Resources/Sap/SapBusinessPartnerContactRelationResource.php
    - app/Http/Resources/Sap/SapBusinessPartnerContactResource.php
  requests:
    - app/Http/Request/Sap/BaseSapBusinessPartnerContactRequest.php
    - app/Http/Request/Sap/BulkSapBusinessPartnerContactRequest.php
    - app/Http/Request/Sap/StoreSapBusinessPartnerContactRequest.php
    - app/Http/Request/Sap/UpdateSapBusinessPartnerContactRequest.php
  service: [app/Services/SapBusinessPartnerContactService.php]
  controller: [app/Http/Controllers/Api/Sap/SapBusinessPartnerContactController.php]
  routes: [routes/sap_businesspartner_contacts.php, routes/sap_sync_master.php]
- model: SapBusinessPartnerEmpresa
  path: app/Models/Sap/SapBusinessPartnerEmpresa.php
  connection: mysql_dbsiaw
  table: sap_businesspartner_empresas
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: false
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - businessPartner: belongsTo SapBusinessPartner (sap_businesspartner_pkid, pkid)
    - empresaConfig: belongsTo SapEmpresaConfig (sap_empresa_config_pkid, pkid)
    - solicitud: belongsTo catalogo_solicitud_proveedor (solicitud_proveedor_id, id)
  service: [app/Services/Sap/SapBusinessPartnerEmpresaService.php]
- model: SapBusinessPartnerSalesPerson
  path: app/Models/Sap/SapBusinessPartnerSalesPerson.php
  connection: mysql_dbsiaw
  table: sap_businesspartner_salespersons
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: false
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - businessPartner: belongsTo SapBusinessPartner (businesspartner_pkid, pkid)
    - empresaConfig: belongsTo SapEmpresaConfig (sap_empresa_config_pkid, pkid)
    - salesPerson: belongsTo SapSalesPerson (salesperson_pkid, pkid)
  resources:
    - app/Http/Resources/Sap/SapBusinessPartnerSalesPersonResource.php
  requests:
    - app/Http/Request/Sap/BulkSapBusinessPartnerSalesPersonRequest.php
    - app/Http/Request/Sap/StoreSapBusinessPartnerSalesPersonRequest.php
    - app/Http/Request/Sap/UpdateSapBusinessPartnerSalesPersonRequest.php
  service: [app/Services/SapBusinessPartnerSalesPersonService.php]
  controller: [app/Http/Controllers/Api/Sap/SapBusinessPartnerSalesPersonController.php]
  routes: [routes/sap_businesspartner_salespersons.php]
- model: SapContactIdentifier
  path: app/Models/Sap/SapContactIdentifier.php
  connection: mysql_dbsiaw
  table: sap_contact_identifiers
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
  relaciones:
    - contact: belongsTo SapBusinessPartnerContact (contact_pkid, pkid)
    - empresaConfig: belongsTo SapEmpresaConfig (sap_empresa_config_pkid, pkid)
  service_usado_en: [app/Services/SapBusinessPartnerContactService.php, app/Services/SapBusinessPartnerService.php]
- model: SapCountry
  path: app/Models/Sap/SapCountry.php
  connection: mysql_dbsiaw
  table: sap_countries
  pk: {name: code, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Sap/SapMasterDataController.php]
  routes: [routes/sap_master_data.php]
- model: SapCurrency
  path: app/Models/Sap/SapCurrency.php
  connection: mysql_dbsiaw
  table: sap_currencies
  pk: {name: code, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
  service_usado_en: [app/Services/catalogo_solicitud_proveedorService.php]
  controller_usado_en: [app/Http/Controllers/Api/Sap/SapMasterDataController.php, app/Http/Controllers/Api/Sap/SapSyncMasterController.php]
  routes: [routes/sap_master_data.php, routes/sap_sync_master.php]
- model: SapEmpresaConfig
  path: app/Models/Sap/SapEmpresaConfig.php
  connection: mysql_dbsiaw
  table: sap_empresa_config
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: false
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - empresa: belongsTo catalogo_empresa (catalogo_empresa_id, pkid)
  resources:
    - app/Http/Resources/Sap/SapEmpresaConfigResource.php
  requests:
    - app/Http/Request/Sap/StoreSapEmpresaConfigRequest.php
    - app/Http/Request/Sap/UpdateSapEmpresaConfigRequest.php
  service_usado_en: [app/Services/Sap/SapBusinessPartnerEmpresaService.php, app/Services/Sap/SapServiceLayerClient.php, app/Services/Sap/SapSyncDispatcher.php, app/Services/SapBusinessPartnerSalesPersonService.php, ...]
  controller: [app/Http/Controllers/Api/Sap/SapEmpresaConfigController.php]
  routes: [routes/sap_businesspartners.php, routes/sap_empresa_config.php, routes/sap_master_data.php, routes/sap_sales_persons.php, ...]
- model: SapEmpresaPaymentTerm
  path: app/Models/Sap/SapEmpresaPaymentTerm.php
  connection: mysql_dbsiaw
  table: sap_empresa_payment_terms
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
  relaciones:
    - empresaConfig: belongsTo SapEmpresaConfig (sap_empresa_config_id, pkid)
    - mappings: hasMany SapPaymentTermMapping (sap_empresa_payment_term_id)
  controller_usado_en: [app/Http/Controllers/Api/Sap/SapPaymentTermMappingController.php]
  routes: [routes/sap_master_data.php]
- model: SapImportRuc
  path: app/Models/Sap/SapImportRuc.php
  connection: mysql_dbsiaw
  table: sap_import_rucs
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
- model: SapPaymentTerm
  path: app/Models/Sap/SapPaymentTerm.php
  connection: mysql_dbsiaw
  table: sap_payment_terms
  pk: {name: group_number, incrementing: false, keyType: int, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
  requests:
    - app/Http/Request/dbsiaw/catalogo_solicitud_proveedor/Storecatalogo_solicitud_proveedorRequest.php
    - app/Http/Request/dbsiaw/catalogo_solicitud_proveedor/Updatecatalogo_solicitud_proveedorRequest.php
  service_usado_en: [app/Services/catalogo_solicitud_proveedorService.php]
  controller_usado_en: [app/Http/Controllers/Api/Sap/SapMasterDataController.php, app/Http/Controllers/Api/Sap/SapPaymentTermMappingController.php]
  routes: [routes/sap_master_data.php]
- model: SapPaymentTermMapping
  path: app/Models/Sap/SapPaymentTermMapping.php
  connection: mysql_dbsiaw
  table: sap_payment_term_mappings
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
  relaciones:
    - paymentTerm: belongsTo SapPaymentTerm (group_number, group_number)
    - empresaPaymentTerm: belongsTo SapEmpresaPaymentTerm (sap_empresa_payment_term_id)
  service_usado_en: [app/Services/SapBusinessPartnerService.php]
  controller: [app/Http/Controllers/Api/Sap/SapPaymentTermMappingController.php]
  routes: [routes/sap_master_data.php]
- model: SapSalesPerson
  path: app/Models/Sap/SapSalesPerson.php
  connection: mysql_dbsiaw
  table: sap_sales_persons
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: false
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - empresaConfig: belongsTo SapEmpresaConfig (sap_company_id, pkid)
    - businessPartners: belongsToMany SapBusinessPartner (sap_businesspartner_salespersons, salesperson_pkid)
  resources:
    - app/Http/Resources/Sap/SapSalesPersonResource.php
  service_usado_en: [app/Services/SapBusinessPartnerSalesPersonService.php]
  controller: [app/Http/Controllers/Api/Sap/SapSalesPersonController.php]
  routes: [routes/sap_sales_persons.php]
- model: SapSalesTaxCode
  path: app/Models/Sap/SapSalesTaxCode.php
  connection: mysql_dbsiaw
  table: sap_salestaxcodes
  pk: {name: code, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Sap/SapMasterDataController.php]
  routes: [routes/sap_master_data.php]
- model: SapState
  path: app/Models/Sap/SapState.php
  connection: mysql_dbsiaw
  table: sap_states
  pk: {name: code, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/Sap/SapMasterDataController.php]
  routes: [routes/sap_master_data.php]
- model: User
  path: app/Models/User.php
  connection: mysql_dbsiaw
  table: catalogo_usuario
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: const deleted sin trait SoftDeletes
  has_factory: true
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/dbsiaw/catalogo_estructuraController.php]
  routes: [routes/catalogo_estructura.php]
- model: auth_group
  path: app/Models/dbsiaw/auth_group.php
  connection: mysql_dbsiaw
  table: auth_group
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
- model: auth_group_permission
  path: app/Models/dbsiaw/auth_group_permission.php
  connection: mysql_dbsiaw
  table: auth_group_permissions
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
- model: auth_permission
  path: app/Models/dbsiaw/auth_permission.php
  connection: mysql_dbsiaw
  table: auth_permission
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
- model: catalogo_almacart
  path: app/Models/dbsiaw/catalogo_almacart.php
  connection: mysql_dbsiaw
  table: catalogo_almacart
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: []
  relaciones:
    - catalogo_almacenes: belongsTo catalogo_almacenes (almacen_id, pkid)
    - catalogo_articulos: belongsTo catalogo_articulos (articulo_id, pkid)
    - catalogo_unidadmed: belongsTo catalogo_unidadmed (unidadmed2_id, idunidadmed)
  filter: [app/Filters/dbsiaw/catalogo_almacartFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_almacartResource.php
  requests:
    - app/Http/Request/dbsiaw/Basecatalogo_almacartRequest.php
    - app/Http/Request/dbsiaw/Storecatalogo_almacartRequest.php
    - app/Http/Request/dbsiaw/Updatecatalogo_almacartRequest.php
  service: [app/Services/catalogo_almacartService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_almacartController.php]
  routes: [routes/api.php, routes/catalogo_almacart.php]
- model: catalogo_almacenes
  path: app/Models/dbsiaw/catalogo_almacenes.php
  connection: mysql_dbsiaw
  table: catalogo_almacenes
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - tienda: belongsTo catalogo_tienda (tienda_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_almacenesFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_almacenesRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_almacenesResource.php
  requests:
    - app/Http/Request/dbsiaw/Basecatalogo_almacenesRequest.php
    - app/Http/Request/dbsiaw/Storecatalogo_almacenesRequest.php
    - app/Http/Request/dbsiaw/Updatecatalogo_almacenesRequest.php
  service: [app/Services/catalogo_almacenesService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_almacenesController.php]
  routes: [routes/api.php, routes/catalogo_almacenes.php]
- model: catalogo_ambientes
  path: app/Models/dbsiaw/catalogo_ambientes.php
  connection: mysql_dbsiaw
  table: catalogo_ambientes
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - createdBy: belongsTo User (created_by_id, pkid)
    - updatedBy: belongsTo User (updated_by_id, pkid)
    - deletedBy: belongsTo User (deleted_by_id, pkid)
    - ambientestiendas: hasMany catalogo_ambientestiendas (ambientes_id, pkid)
    - tipoprecio: belongsTo catalogo_tipoprecio (tipoprecio_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_ambientesFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_ambientesRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_ambientesResource.php
    - app/Http/Resources/dbsiaw/catalogo_ambientestiendasResource.php
  requests:
    - app/Http/Request/dbsiaw/Basecatalogo_ambientesRequest.php
    - app/Http/Request/dbsiaw/Storecatalogo_ambientesRequest.php
    - app/Http/Request/dbsiaw/Updatecatalogo_ambientesRequest.php
  service: [app/Services/catalogo_ambientesService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_ambientesController.php]
  routes: [routes/api.php, routes/catalogo_ambientes.php]
- model: catalogo_ambientestiendas
  path: app/Models/dbsiaw/catalogo_ambientestiendas.php
  connection: mysql_dbsiaw
  table: catalogo_ambientestiendas
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - createdBy: belongsTo User (created_by_id, pkid)
    - updatedBy: belongsTo User (updated_by_id, pkid)
    - deletedBy: belongsTo User (deleted_by_id, pkid)
    - tienda: belongsTo catalogo_tienda (tienda_id, pkid)
    - ambiente: belongsTo catalogo_ambientes (ambientes_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_ambientestiendasFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_ambientestiendasResource.php
  requests:
    - app/Http/Request/dbsiaw/Basecatalogo_ambientestiendasRequest.php
    - app/Http/Request/dbsiaw/BulkStorecatalogo_ambientestiendasRequest.php
    - app/Http/Request/dbsiaw/Storecatalogo_ambientestiendasRequest.php
    - app/Http/Request/dbsiaw/Updatecatalogo_ambientestiendasRequest.php
  service: [app/Services/catalogo_ambientestiendasService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_ambientestiendasController.php]
  routes: [routes/api.php, routes/catalogo_ambientestiendas.php]
- model: catalogo_areaproduccion
  path: app/Models/dbsiaw/catalogo_areaproduccion.php
  connection: mysql_dbsiaw
  table: catalogo_areaproduccion
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  filter: [app/Filters/dbsiaw/catalogo_areaproduccionFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_areaproduccionRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_areaproduccionResource.php
  service_usado_en: [app/Services/catalogo_articulosService.php]
  controller: [app/Http/Controllers/Api/catalogo_areaproduccionController.php]
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
  resources:
    - app/Http/Resources/dbsiaw/catalogo_articulosExternalResource.php
    - app/Http/Resources/dbsiaw/catalogo_articulosRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_articulosResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_articulos/Basecatalogo_articuloRequest.php
    - app/Http/Request/dbsiaw/catalogo_articulos/FindAllcatalogo_articulosRequest.php
    - app/Http/Request/dbsiaw/catalogo_articulos/FindMultiplecatalogo_articulosRequest.php
    - app/Http/Request/dbsiaw/catalogo_articulos/FindOnecatalogo_articuloRequest.php
    - app/Http/Request/dbsiaw/catalogo_articulos/GetSinAlmacenRequest.php
    - app/Http/Request/dbsiaw/catalogo_articulos/GetSinPrecioTdaRequest.php
    - app/Http/Request/dbsiaw/catalogo_articulos/Storecatalogo_articuloRequest.php
    - app/Http/Request/dbsiaw/catalogo_articulos/Updatecatalogo_articuloRequest.php
  service: [app/Services/catalogo_articulosService.php]
  controller: [app/Http/Controllers/Api/catalogo_articulosController.php]
  routes: [routes/api.php]
- model: catalogo_authgroup
  path: app/Models/dbsiaw/catalogo_authgroup.php
  connection: mysql_dbsiaw
  table: auth_group
  pk: {name: id, incrementing: true, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  relaciones:
    - extensions: hasMany catalogo_groupextension (group_id, id)
  resources:
    - app/Http/Resources/dbsiaw/catalogo_authgroupResource.php
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_auth_groupController.php]
  routes: [routes/api.php]
- model: catalogo_authpermission
  path: app/Models/dbsiaw/catalogo_authpermission.php
  connection: mysql_dbsiaw
  table: auth_permission
  pk: {name: id, incrementing: true, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  relaciones:
    - contentType: belongsTo catalogo_djangocontenttype (content_type_id, id)
  resources:
    - app/Http/Resources/dbsiaw/catalogo_authpermissionResource.php
  service: [app/Services/AuthpermissionService.php]
- model: catalogo_blockedpermissions
  path: app/Models/dbsiaw/catalogo_blockedpermissions.php
  connection: mysql_dbsiaw
  table: catalogo_blockedpermissions
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - permission: belongsTo catalogo_authpermission (permission_id, id)
    - group: belongsTo catalogo_authgroup (group_id, id)
    - created_by: belongsTo User (created_by_id, pkid)
    - updated_by: belongsTo User (updated_by_id, pkid)
    - deleted_by: belongsTo User (deleted_by_id, pkid)
  resources:
    - app/Http/Resources/dbsiaw/catalogo_blockedpermissionsResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_blockedpermissions/BulkStorecatalogBlockedpermissionsRequest.php
    - app/Http/Request/dbsiaw/catalogo_blockedpermissions/StorecatalogBlockedpermissionsRequest.php
  service: [app/Services/catalogo_blockedpermissionsService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_blockedpermissionsController.php]
  routes: [routes/catalogo_blockedpermissions.php]
- model: catalogo_cajas
  path: app/Models/dbsiaw/catalogo_cajas.php
  connection: mysql_dbsiaw
  table: catalogo_cajas
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: false
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - terminal: belongsTo catalogo_terminales (terminal_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_cajasFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_cajasResource.php
  controller: [app/Http/Controllers/Api/catalogo_cajasController.php]
  routes: [routes/api.php]
- model: catalogo_casafinanciera
  path: app/Models/dbsiaw/catalogo_casafinanciera.php
  connection: mysql_dbsiaw
  table: catalogo_casafinanciera
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  relaciones:
    - tarjetascredito: hasMany catalogo_tarjetascredito (casafinanciera_id, pkid)
  controller_usado_en: [app/Http/Controllers/Api/sincronizacion/subir_casafinancieraController.php, app/Http/Controllers/Api/sincronizacion/subir_tarjetascreditoController.php]
  routes: [routes/api.php]
- model: catalogo_clasesgasto
  path: app/Models/dbsiaw/catalogo_clasesgasto.php
  connection: mysql_dbsiaw
  table: catalogo_clasesgasto
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - create_by: belongsTo catalogo_usuario (created_by_id, pkid)
    - update_by: belongsTo catalogo_usuario (updated_by_id, pkid)
    - delete_by: belongsTo catalogo_usuario (deleted_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_clasesgastoFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_clasesgastoRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_clasesgastoResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_clasesgasto/Basecatalogo_clasesgastoRequest.php
    - app/Http/Request/dbsiaw/catalogo_clasesgasto/Storecatalogo_clasesgastoRequest.php
    - app/Http/Request/dbsiaw/catalogo_clasesgasto/Updatecatalogo_clasesgastoRequest.php
  service: [app/Services/catalogo_clasesgastoService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_clasesgastoController.php]
  routes: [routes/catalogo_clasesgasto.php]
- model: catalogo_clasificacion
  path: app/Models/dbsiaw/catalogo_clasificacion.php
  connection: mysql_dbsiaw
  table: catalogo_clasificacion
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  filter: [app/Filters/dbsiaw/catalogo_clasificacionFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_clasificacionRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_clasificacionResource.php
  controller: [app/Http/Controllers/Api/catalogo_clasificacionController.php]
  routes: [routes/api.php]
- model: catalogo_clientes
  path: app/Models/dbsiaw/catalogo_clientes.php
  connection: mysql_dbsiaw
  table: catalogo_clientes
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - created_by: belongsTo catalogo_usuario (created_by_id, pkid)
    - updated_by: belongsTo catalogo_usuario (updated_by_id, pkid)
    - deleted_by: belongsTo catalogo_usuario (deleted_by_id, pkid)
    - tipodocumento: belongsTo catalogo_tipodocumento (tipodocumento_id, pkid)
    - regalos: hasMany catalogo_regalos (cliente_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_clientesFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_clientesResource.php
  requests:
    - app/Http/Request/dbsiaw/Basecatalogo_clientesRequest.php
    - app/Http/Request/dbsiaw/Storecatalogo_clientesRequest.php
    - app/Http/Request/dbsiaw/Updatecatalogo_clientesRequest.php
  service: [app/Services/catalogo_clientesService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_clientesController.php]
  routes: [routes/catalogo_clientes.php]
- model: catalogo_correos
  path: app/Models/dbsiaw/catalogo_correos.php
  connection: mysql_dbsiaw
  table: catalogo_correos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - procesos: belongsToMany catalogo_procesos (catalogo_procesoscorreo, correo_id)
    - create_by: belongsTo User (created_by_id, pkid)
    - update_by: belongsTo User (updated_by_id, pkid)
    - delete_by: belongsTo User (deleted_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_correosFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_correosRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_correosResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_correos/Basecatalogo_correosRequest.php
    - app/Http/Request/dbsiaw/catalogo_correos/BulkStorecatalogo_correosRequest.php
    - app/Http/Request/dbsiaw/catalogo_correos/GetCorreosSinProcesocatalogo_correosRequest.php
    - app/Http/Request/dbsiaw/catalogo_correos/Storecatalogo_correosRequest.php
    - app/Http/Request/dbsiaw/catalogo_correos/Updatecatalogo_correosRequest.php
  service: [app/Services/catalogo_correosService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_correosController.php]
  routes: [routes/catalogo_correos.php, routes/catalogo_procesos.php]
- model: catalogo_djangocontenttype
  path: app/Models/dbsiaw/catalogo_djangocontenttype.php
  connection: mysql_dbsiaw
  table: django_content_type
  pk: {name: id, incrementing: true, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: true
  auditoria: []
  service: [app/Services/DjangoContentTypeService.php]
  controller_usado_en: [app/Http/Controllers/Api/catalogo_djangocontentController.php]
  routes: [routes/api.php]
- model: catalogo_empresa
  path: app/Models/dbsiaw/catalogo_empresa.php
  connection: mysql_dbsiaw
  table: catalogo_empresa
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - catalogo_ubigeo: belongsTo catalogo_ubigeo (ubigeo_id, pkid)
    - created_by: belongsTo User (created_by_id, pkid)
    - updated_by: belongsTo User (updated_by_id, pkid)
    - deleted_by: belongsTo User (deleted_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_empresaFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_empresaRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_empresaResource.php
    - app/Http/Resources/dbsiaw/catalogo_empresatiendaResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_empresa/Basecatalogo_empresaRequest.php
    - app/Http/Request/dbsiaw/catalogo_empresa/Storecatalogo_empresaRequest.php
    - app/Http/Request/dbsiaw/catalogo_empresa/Updatecatalogo_empresaRequest.php
  service: [app/Services/catalogo_empresaService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_empresaController.php]
  routes: [routes/catalogo_empresa.php]
- model: catalogo_empresatienda
  path: app/Models/dbsiaw/catalogo_empresatienda.php
  connection: mysql_dbsiaw
  table: catalogo_empresatienda
  pk: {name: pkid, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - created_by: belongsTo User (created_by_id, pkid)
    - updated_by: belongsTo User (updated_by_id, pkid)
    - deleted_by: belongsTo User (deleted_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_empresatiendaFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_empresatiendaResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_empresatienda/Basecatalogo_empresatiendaRequest.php
    - app/Http/Request/dbsiaw/catalogo_empresatienda/Storecatalogo_empresatiendaRequest.php
    - app/Http/Request/dbsiaw/catalogo_empresatienda/Updatecatalogo_empresatiendaRequest.php
  service: [app/Services/catalogo_empresatiendaService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_empresatiendaController.php]
  routes: [routes/catalogo_empresatienda.php]
- model: catalogo_estructura
  path: app/Models/dbsiaw/catalogo_estructura.php
  connection: mysql_dbsiaw
  table: catalogo_estructuras
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - childs: hasMany self (parent_id, pkid)
    - catalogo_personal_estructura: hasMany catalogo_personal_estructura (estructura_id, pkid)
  resources:
    - app/Http/Resources/dbsiaw/catalogo_estructuraResource.php
    - app/Http/Resources/dbsiaw/catalogo_estructuraSimpleResource.php
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_estructuraController.php]
  routes: [routes/catalogo_estructura.php]
- model: catalogo_familias
  path: app/Models/dbsiaw/catalogo_familias.php
  connection: mysql_dbsiaw
  table: catalogo_familias
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  filter: [app/Filters/dbsiaw/catalogo_familiasFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_familiasRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_familiasResource.php
  controller: [app/Http/Controllers/Api/catalogo_familiasController.php]
  routes: [routes/api.php]
- model: catalogo_formulaciones
  path: app/Models/dbsiaw/catalogo_formulaciones.php
  connection: mysql_dbsiaw
  table: catalogo_formulaciones
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: []
- model: catalogo_groupextension
  path: app/Models/dbsiaw/catalogo_groupextension.php
  connection: mysql_dbsiaw
  table: catalogo_groupextension
  pk: {name: pkid, incrementing: true, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted
  has_factory: true
  auditoria: [updated_by_id]
  relaciones:
    - catalogo_group: belongsTo catalogo_authgroup (group_id, id)
  resources:
    - app/Http/Resources/dbsiaw/catalogo_groupextensionResource.php
  controller_usado_en: [app/Http/Controllers/Api/catalogo_gruposController.php]
  routes: [routes/api.php]
- model: catalogo_grupogasto
  path: app/Models/dbsiaw/catalogo_grupogasto.php
  connection: mysql_dbsiaw
  table: catalogo_grupogasto
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - create_by: belongsTo catalogo_usuario (created_by_id, pkid)
    - update_by: belongsTo catalogo_usuario (updated_by_id, pkid)
    - delete_by: belongsTo catalogo_usuario (deleted_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_grupogastoFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_grupogastoResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_grupogasto/Basecatalogo_grupogastoRequest.php
    - app/Http/Request/dbsiaw/catalogo_grupogasto/Storecatalogo_grupogastoRequest.php
    - app/Http/Request/dbsiaw/catalogo_grupogasto/Updatecatalogo_grupogastoRequest.php
  service: [app/Services/catalogo_grupogastoService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_grupogastoController.php]
  routes: [routes/catalogo_grupogasto.php]
- model: catalogo_insumo
  path: app/Models/dbsiaw/catalogo_insumo.php
  connection: mysql_dbsiaw
  table: catalogo_insumos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - bp_group: belongsTo SapBpGroup (bp_group_code, code)
    - proveedor_insumos: hasMany catalogo_proveedor_insumo (insumo_id, pkid)
    - created_by: belongsTo User (created_by_id, pkid)
    - updated_by: belongsTo User (updated_by_id, pkid)
    - deleted_by: belongsTo User (deleted_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_insumoFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_insumoRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_insumoResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_insumo/Basecatalogo_insumoRequest.php
    - app/Http/Request/dbsiaw/catalogo_insumo/Storecatalogo_insumoRequest.php
    - app/Http/Request/dbsiaw/catalogo_insumo/Updatecatalogo_insumoRequest.php
  service: [app/Services/catalogo_insumoService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_insumoController.php]
  routes: [routes/catalogo_insumo.php]
- model: catalogo_monedas
  path: app/Models/dbsiaw/catalogo_monedas.php
  connection: mysql_dbsiaw
  table: catalogo_monedas
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: no
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  relaciones:
    - catalogo_tiendas: hasMany catalogo_tienda
- model: catalogo_motivosgasto
  path: app/Models/dbsiaw/catalogo_motivosgasto.php
  connection: mysql_dbsiaw
  table: catalogo_motivosgasto
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - create_by: belongsTo catalogo_usuario (created_by_id, pkid)
    - update_by: belongsTo catalogo_usuario (updated_by_id, pkid)
    - delete_by: belongsTo catalogo_usuario (deleted_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_motivosgastoFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_motivosgastoExternalResource.php
    - app/Http/Resources/dbsiaw/catalogo_motivosgastoRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_motivosgastoResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_motivosgasto/Basecatalogo_motivosgastoRequest.php
    - app/Http/Request/dbsiaw/catalogo_motivosgasto/Storecatalogo_motivosgastoRequest.php
    - app/Http/Request/dbsiaw/catalogo_motivosgasto/Updatecatalogo_motivosgastoRequest.php
  service: [app/Services/catalogo_motivosgastoService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_motivosgastoController.php]
  routes: [routes/catalogo_motivosgasto.php]
- model: catalogo_motivostipogasto
  path: app/Models/dbsiaw/catalogo_motivostipogasto.php
  connection: mysql_dbsiaw
  table: catalogo_motivostipogasto
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - create_by: belongsTo catalogo_usuario (created_by_id, pkid)
    - update_by: belongsTo catalogo_usuario (updated_by_id, pkid)
    - delete_by: belongsTo catalogo_usuario (deleted_by_id, pkid)
    - catalogo_motivosgasto: belongsTo catalogo_motivosgasto (motivosgasto_id, pkid)
    - catalogo_tiposgasto: belongsTo catalogo_tiposgasto (tiposgasto_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_motivostipogastoFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_motivostipogastoResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_motivostipogasto/Basecatalogo_motivostipogastoRequest.php
    - app/Http/Request/dbsiaw/catalogo_motivostipogasto/Storecatalogo_motivostipogastoRequest.php
    - app/Http/Request/dbsiaw/catalogo_motivostipogasto/Updatecatalogo_motivostipogastoRequest.php
  service: [app/Services/catalogo_motivostipogastoService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_motivostipogastoController.php]
  routes: [routes/catalogo_motivostipogasto.php]
- model: catalogo_nivel
  path: app/Models/dbsiaw/catalogo_nivel.php
  connection: mysql_dbsiaw
  table: catalogo_niveles
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_nivelResource.php
  controller_usado_en: [app/Http/Controllers/Api/dbsiaw/catalogo_estructuraController.php]
  routes: [routes/catalogo_estructura.php]
- model: catalogo_parametrosistema
  path: app/Models/dbsiaw/catalogo_parametrosistema.php
  connection: mysql_dbsiaw
  table: catalogo_parametrosistema
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: false
  auditoria: [created_by_id, updated_by_id]
  relaciones:
    - tiposistema: belongsTo catalogo_tiposistema (tipo_sistema_id, pkid)
    - created_by: belongsTo catalogo_usuario (created_by_id, pkid)
    - updated_by: belongsTo catalogo_usuario (updated_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_parametrosistemaFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_parametrosistemaRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_parametrosistemaResource.php
    - app/Http/Resources/dbsiaw/catalogo_parametrosistemaTinyResource.php
  requests:
    - app/Http/Request/dbsiaw/Traits/catalogo_parametrosistema/ValidatesCatalogo_parametrosistema.php
    - app/Http/Request/dbsiaw/catalogo_parametrosistema/Basecatalogo_parametrosistemaRequest.php
    - app/Http/Request/dbsiaw/catalogo_parametrosistema/Storecatalogo_parametrosistemaRequest.php
    - app/Http/Request/dbsiaw/catalogo_parametrosistema/Updatecatalogo_parametrosistemaRequest.php
  service: [app/Services/catalogo_parametrosistemaService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_parametrosistemaController.php]
  routes: [routes/catalogo_parametrosistema.php]
- model: catalogo_personal_estructura
  path: app/Models/dbsiaw/catalogo_personal_estructura.php
  connection: mysql_dbsiaw
  table: catalogo_personal_estructura
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - sipPersonal: belongsTo sip_personal (personal_id, pkid)
    - ultimoCargo: hasOneThrough sip_personal_cargo
  controller_usado_en: [app/Http/Controllers/Api/dbsiaw/catalogo_estructuraController.php]
  routes: [routes/catalogo_estructura.php]
- model: catalogo_preciart
  path: app/Models/dbsiaw/catalogo_preciart.php
  connection: mysql_dbsiaw
  table: catalogo_preciart
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - create_by: belongsTo catalogo_usuario (created_by_id, pkid)
    - update_by: belongsTo catalogo_usuario (updated_by_id, pkid)
    - delete_by: belongsTo catalogo_usuario (deleted_by_id, pkid)
    - catalogo_articulos: belongsTo catalogo_articulos (articulos_id, pkid)
    - catalogo_tienda: belongsTo catalogo_tienda (tienda_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_preciartFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_preciartExternalResource.php
    - app/Http/Resources/dbsiaw/catalogo_preciartRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_preciartResource.php
    - app/Http/Resources/dbsiaw/catalogo_preciart_logResource.php
  requests:
    - app/Http/Request/dbsiaw/Basecatalogo_preciartRequest.php
    - app/Http/Request/dbsiaw/Storecatalogo_preciartRequest.php
    - app/Http/Request/dbsiaw/Updatecatalogo_preciartRequest.php
  service: [app/Services/catalogo_preciartService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_preciartController.php]
  routes: [routes/api.php, routes/catalogo_preciart.php]
- model: catalogo_preciart_log
  path: app/Models/dbsiaw/catalogo_preciart_log.php
  connection: mysql_dbsiaw
  table: catalogo_preciart_log
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - create_by: belongsTo catalogo_usuario (created_by_id, pkid)
    - update_by: belongsTo catalogo_usuario (updated_by_id, pkid)
    - delete_by: belongsTo catalogo_usuario (deleted_by_id, pkid)
    - articulo: belongsTo catalogo_articulos (articulos_id, pkid)
    - catalogo_tienda: belongsTo catalogo_tienda (tienda_id, pkid)
    - catalogo_preciart: belongsTo catalogo_preciart (preciart_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_preciart_logFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_preciart_logResource.php
  requests:
    - app/Http/Request/dbsiaw/Basecatalogo_preciart_logRequest.php
    - app/Http/Request/dbsiaw/Storecatalogo_preciart_logRequest.php
    - app/Http/Request/dbsiaw/Updatecatalogo_preciart_logRequest.php
  service: [app/Services/catalogo_preciart_logService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_preciart_logController.php]
  routes: [routes/catalogo_preciart_log.php]
- model: catalogo_premiaciones
  path: app/Models/dbsiaw/catalogo_premiaciones.php
  connection: mysql_dbsiaw
  table: catalogo_premiaciones
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - created_by: belongsTo catalogo_usuario (created_by_id, pkid)
    - updated_by: belongsTo catalogo_usuario (updated_by_id, pkid)
    - deleted_by: belongsTo catalogo_usuario (deleted_by_id, pkid)
    - tienda: belongsTo catalogo_tienda (tienda_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_premiacionesFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_premiacionesExternalResource.php
    - app/Http/Resources/dbsiaw/catalogo_premiacionesResource.php
  requests:
    - app/Http/Request/dbsiaw/Traits/catalogo_premiaciones/ValidatesCatalogo_premiaciones.php
    - app/Http/Request/dbsiaw/catalogo_premiaciones/Basecatalogo_premiacionesRequest.php
    - app/Http/Request/dbsiaw/catalogo_premiaciones/GetPremiacionesExternalRequest.php
    - app/Http/Request/dbsiaw/catalogo_premiaciones/Importcatalogo_premiacionesRequest.php
    - app/Http/Request/dbsiaw/catalogo_premiaciones/Storecatalogo_premiacionesRequest.php
    - app/Http/Request/dbsiaw/catalogo_premiaciones/Updatecatalogo_premiacionesRequest.php
  service: [app/Services/catalogo_premiacionesService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_premiacionesController.php]
  routes: [routes/catalogo_premiaciones.php]
- model: catalogo_procesos
  path: app/Models/dbsiaw/catalogo_procesos.php
  connection: mysql_dbsiaw
  table: catalogo_procesos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - correos: belongsToMany catalogo_correos (catalogo_procesoscorreo, proceso_id)
    - create_by: belongsTo catalogo_usuario (created_by_id, pkid)
    - update_by: belongsTo catalogo_usuario (updated_by_id, pkid)
    - delete_by: belongsTo catalogo_usuario (deleted_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_procesosFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_procesosRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_procesosResource.php
    - app/Http/Resources/dbsiaw/catalogo_procesosauditResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_procesos/Basecatalogo_procesosRequest.php
    - app/Http/Request/dbsiaw/catalogo_procesos/Storecatalogo_procesosRequest.php
    - app/Http/Request/dbsiaw/catalogo_procesos/Updatecatalogo_procesosRequest.php
  service: [app/Services/catalogo_procesosService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_procesosController.php]
  routes: [routes/catalogo_procesos.php]
- model: catalogo_procesosaudit
  path: app/Models/dbsiaw/catalogo_procesosaudit.php
  connection: mysql_dbsiaw
  table: catalogo_procesosaudit
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: [created_by_id]
  relaciones:
    - created_by: belongsTo User (created_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_procesosauditFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_procesosauditResource.php
  service: [app/Services/catalogo_procesosauditService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_procesosauditController.php]
  routes: [routes/catalogo_procesosaudit.php]
- model: catalogo_procesoscorreo
  path: app/Models/dbsiaw/catalogo_procesoscorreo.php
  connection: mysql_dbsiaw
  table: catalogo_procesoscorreo
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - proceso: belongsTo catalogo_procesos (proceso_id, pkid)
    - correo: belongsTo catalogo_correos (correo_id, pkid)
    - tienda: belongsTo catalogo_tienda (tienda_id, pkid)
    - created_by: belongsTo User (created_by_id, pkid)
    - updated_by: belongsTo User (updated_by_id, pkid)
    - deleted_by: belongsTo User (deleted_by_id, pkid)
  requests:
    - app/Http/Request/dbsiaw/catalogo_procesoscorreo/Basecatalogo_procesoscorreoRequest.php
    - app/Http/Request/dbsiaw/catalogo_procesoscorreo/Storecatalogo_procesoscorreoRequest.php
    - app/Http/Request/dbsiaw/catalogo_procesoscorreo/Updatecatalogo_procesoscorreoRequest.php
  service: [app/Services/catalogo_procesoscorreoService.php]
- model: catalogo_proveedor_insumo
  path: app/Models/dbsiaw/catalogo_proveedor_insumo.php
  connection: mysql_dbsiaw
  table: catalogo_proveedor_insumos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - business_partner: belongsTo SapBusinessPartner (businesspartners_id, pkid)
    - solicitud_proveedor: belongsTo catalogo_solicitud_proveedor (proveedor_id, pkid)
    - insumo: belongsTo catalogo_insumo (insumo_id, pkid)
    - created_by: belongsTo User (created_by_id, pkid)
    - updated_by: belongsTo User (updated_by_id, pkid)
    - deleted_by: belongsTo User (deleted_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_proveedor_insumoFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_proveedor_insumoRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_proveedor_insumoResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_proveedor_insumo/Basecatalogo_proveedor_insumoRequest.php
    - app/Http/Request/dbsiaw/catalogo_proveedor_insumo/Storecatalogo_proveedor_insumoRequest.php
    - app/Http/Request/dbsiaw/catalogo_proveedor_insumo/Updatecatalogo_proveedor_insumoRequest.php
  service: [app/Services/catalogo_proveedor_insumoService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_proveedor_insumoController.php]
  routes: [routes/catalogo_proveedor_insumo.php]
- model: catalogo_regalos
  path: app/Models/dbsiaw/catalogo_regalos.php
  connection: mysql_dbsiaw
  table: catalogo_regalos
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - created_by: belongsTo catalogo_usuario (created_by_id, pkid)
    - updated_by: belongsTo catalogo_usuario (updated_by_id, pkid)
    - deleted_by: belongsTo catalogo_usuario (deleted_by_id, pkid)
    - cliente: belongsTo catalogo_clientes (cliente_id, pkid)
    - tienda: belongsTo catalogo_tienda (tienda_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_regalosFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_regalosResource.php
    - app/Http/Resources/dbsiaw/catalogo_regalos_articulosResource.php
  requests:
    - app/Http/Request/dbsiaw/Basecatalogo_regalosRequest.php
    - app/Http/Request/dbsiaw/Storecatalogo_regalosRequest.php
    - app/Http/Request/dbsiaw/Updatecatalogo_regalosRequest.php
  service: [app/Services/catalogo_regalosService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_regalosController.php]
  routes: [routes/catalogo_clientes.php]
- model: catalogo_regalos_articulos
  path: app/Models/dbsiaw/catalogo_regalos_articulos.php
  connection: mysql_dbsiaw
  table: catalogo_regalos_articulos
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - articulo: belongsTo catalogo_articulos (articulo_id, pkid)
    - created_by: belongsTo catalogo_usuario (created_by_id, pkid)
    - updated_by: belongsTo catalogo_usuario (updated_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_regalos_articulosFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_regalos_articulosResource.php
  requests:
    - app/Http/Request/dbsiaw/Basecatalogo_regalos_articulosRequest.php
    - app/Http/Request/dbsiaw/Storecatalogo_regalos_articulosRequest.php
    - app/Http/Request/dbsiaw/Updatecatalogo_regalos_articulosRequest.php
  service: [app/Services/catalogo_regalos_articulosService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_regalos_articulosController.php]
  routes: [routes/catalogo_clientes.php]
- model: catalogo_solicitud_proveedor
  path: app/Models/dbsiaw/catalogo_solicitud_proveedor.php
  connection: mysql_dbsiaw
  table: catalogo_solicitudproveedor
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - usuario_atencion: belongsTo User (usuario_atencion, pkid)
    - tienda: belongsTo catalogo_tienda (tienda_id, pkid)
    - created_by: belongsTo User (created_by_id, pkid)
    - updated_by: belongsTo User (updated_by_id, pkid)
    - deleted_by: belongsTo User (deleted_by_id, pkid)
    - business_partner: belongsTo SapBusinessPartner (business_partner_id, pkid)
    - departamento: belongsTo catalogo_ubigeo (departamento_id, pkid)
    - provincia: belongsTo catalogo_ubigeo (provincia_id, pkid)
    - distrito: belongsTo catalogo_ubigeo (distrito_id, pkid)
    - proveedor_insumos: hasMany catalogo_proveedor_insumo (proveedor_id, pkid)
    - empresaSap: belongsTo SapEmpresaConfig (sap_empresa_config_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_solicitud_proveedorFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_solicitud_proveedorRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_solicitud_proveedorResource.php
    - app/Http/Resources/dbsiaw/catalogo_solicitud_proveedorTinyResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_solicitud_proveedor/Basecatalogo_solicitud_proveedorRequest.php
    - app/Http/Request/dbsiaw/catalogo_solicitud_proveedor/StoreExternalProveedorRequest.php
    - app/Http/Request/dbsiaw/catalogo_solicitud_proveedor/Storecatalogo_solicitud_proveedorRequest.php
    - app/Http/Request/dbsiaw/catalogo_solicitud_proveedor/Updatecatalogo_solicitud_proveedorRequest.php
  service: [app/Services/catalogo_solicitud_proveedorService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_solicitud_proveedorController.php]
  routes: [routes/catalogo_solicitud_proveedor.php]
- model: catalogo_subfamilias
  path: app/Models/dbsiaw/catalogo_subfamilias.php
  connection: mysql_dbsiaw
  table: catalogo_subfamilias
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  filter: [app/Filters/dbsiaw/catalogo_subfamiliasFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_subfamiliasRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_subfamiliasResource.php
  service_usado_en: [app/Services/catalogo_articulosService.php]
  controller: [app/Http/Controllers/Api/catalogo_subfamiliasController.php]
  routes: [routes/api.php]
- model: catalogo_tarjetascredito
  path: app/Models/dbsiaw/catalogo_tarjetascredito.php
  connection: mysql_dbsiaw
  table: catalogo_tarjetascredito
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  relaciones:
    - casafinanciera: belongsTo catalogo_casafinanciera (casafinanciera_id, pkid)
  resources:
    - app/Http/Resources/dbsiaw/catalogo_tarjetascreditoResource.php
  controller: [app/Http/Controllers/Api/catalogo_tarjetascreditoController.php]
  routes: [routes/api.php]
- model: catalogo_terminales
  path: app/Models/dbsiaw/catalogo_terminales.php
  connection: mysql_dbsiaw
  table: None
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: false
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - cajas: hasMany catalogo_cajas (terminal_id, pkid)
    - tienda: belongsTo catalogo_tienda (tienda_id, pkid)
    - created_by: belongsTo catalogo_usuario (created_by_id, pkid)
    - updated_by: belongsTo catalogo_usuario (updated_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_terminalesFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_terminalesResource.php
  requests:
    - app/Http/Request/dbsiaw/Traits/catalogo_terminales/ValidatesCatalogo_terminales.php
    - app/Http/Request/dbsiaw/catalogo_terminales/Basecatalogo_terminalesRequest.php
    - app/Http/Request/dbsiaw/catalogo_terminales/Storecatalogo_terminalesRequest.php
    - app/Http/Request/dbsiaw/catalogo_terminales/Updatecatalogo_terminalesRequest.php
  service: [app/Services/catalogo_terminalesService.php]
  controller_usado_en: [app/Http/Controllers/Api/catalogo_cajasController.php]
  routes: [routes/api.php]
- model: catalogo_tienda
  path: app/Models/dbsiaw/catalogo_tienda.php
  connection: mysql_dbsiaw
  table: catalogo_tienda
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - created_by: belongsTo User (created_by_id, pkid)
    - updated_by: belongsTo User (updated_by_id, pkid)
    - deleted_by: belongsTo User (deleted_by_id, pkid)
    - catalogo_empresa: belongsToMany catalogo_empresa
    - ambientestiendas: hasMany catalogo_ambientestiendas (tienda_id, pkid)
    - catalogo_ubigeo: belongsTo catalogo_ubigeo (ubigeo_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_tiendaFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_tiendaByUpdatedAtResource.php
    - app/Http/Resources/dbsiaw/catalogo_tiendaConAmbientesResource.php
    - app/Http/Resources/dbsiaw/catalogo_tiendaRelacionResource.php
    - app/Http/Resources/dbsiaw/catalogo_tiendaResource.php
    - app/Http/Resources/dbsiaw/catalogo_tiendazonaResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_tienda/Basecatalogo_tiendaRequest.php
    - app/Http/Request/dbsiaw/catalogo_tienda/GetTiendasByUpdatedAtRequest.php
    - app/Http/Request/dbsiaw/catalogo_tienda/GetTiendasExternalRequest.php
    - app/Http/Request/dbsiaw/catalogo_tienda/Storecatalogo_tiendaRequest.php
    - app/Http/Request/dbsiaw/catalogo_tienda/Updatecatalogo_tiendaRequest.php
  service: [app/Services/catalogo_tiendaService.php]
  controller: [app/Http/Controllers/Api/catalogo_tiendaController.php]
  routes: [routes/api.php, routes/catalogo_estructura.php]
- model: catalogo_tiendazona
  path: app/Models/dbsiaw/catalogo_tiendazona.php
  connection: mysql_dbsiaw
  table: catalogo_tiendazona
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_tiendazonaResource.php
  controller: [app/Http/Controllers/Api/catalogo_tiendazonaController.php]
  routes: [routes/api.php]
- model: catalogo_tipodocumento
  path: app/Models/dbsiaw/catalogo_tipodocumento.php
  connection: mysql_dbsiaw
  table: catalogo_tipodocumento
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  filter: [app/Filters/dbsiaw/catalogo_tipodocumentoFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_tipodocumentoResource.php
  requests:
    - app/Http/Request/dbsiaw/Basecatalogo_tipodocumentoRequest.php
    - app/Http/Request/dbsiaw/Storecatalogo_tipodocumentoRequest.php
    - app/Http/Request/dbsiaw/Updatecatalogo_tipodocumentoRequest.php
  service: [app/Services/catalogo_tipodocumentoService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_tipodocumentoController.php]
  routes: [routes/catalogo_clientes.php]
- model: catalogo_tipoprecio
  path: app/Models/dbsiaw/catalogo_tipoprecio.php
  connection: mysql_dbsiaw
  table: catalogo_tipoprecio
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - created_by: belongsTo User (created_by_id, pkid)
    - updated_by: belongsTo User (updated_by_id, pkid)
    - deleted_by: belongsTo User (deleted_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_tipoprecioFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_tipoprecioRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_tipoprecioResource.php
  requests:
    - app/Http/Request/dbsiaw/Basecatalogo_tipoprecioRequest.php
    - app/Http/Request/dbsiaw/Storecatalogo_tipoprecioRequest.php
    - app/Http/Request/dbsiaw/Updatecatalogo_tipoprecioRequest.php
  service: [app/Services/catalogo_tipoprecioService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_tipoprecioController.php]
  routes: [routes/api.php, routes/catalogo_tipoprecio.php]
- model: catalogo_tiposgasto
  path: app/Models/dbsiaw/catalogo_tiposgasto.php
  connection: mysql_dbsiaw
  table: catalogo_tiposgasto
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - create_by: belongsTo catalogo_usuario (created_by_id, pkid)
    - update_by: belongsTo catalogo_usuario (updated_by_id, pkid)
    - delete_by: belongsTo catalogo_usuario (deleted_by_id, pkid)
    - catalogo_clasesgasto: belongsTo catalogo_clasesgasto (clasesgasto_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_tiposgastoFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_tiposgastoExternalResource.php
    - app/Http/Resources/dbsiaw/catalogo_tiposgastoRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_tiposgastoResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_tiposgasto/Basecatalogo_tiposgastoRequest.php
    - app/Http/Request/dbsiaw/catalogo_tiposgasto/Storecatalogo_tiposgastoRequest.php
    - app/Http/Request/dbsiaw/catalogo_tiposgasto/Updatecatalogo_tiposgastoRequest.php
  service: [app/Services/catalogo_tiposgastoService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_tiposgastoController.php]
  routes: [routes/catalogo_tiposgasto.php]
- model: catalogo_tiposistema
  path: app/Models/dbsiaw/catalogo_tiposistema.php
  connection: mysql_dbsiaw
  table: catalogo_tiposistema
  pk: {name: pkid, incrementing: true, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_tiposistemaRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_tiposistemaResource.php
  service_usado_en: [app/Services/catalogo_parametrosistemaService.php]
  controller_usado_en: [app/Http/Controllers/Api/catalogo_sistemasController.php]
  routes: [routes/api.php]
- model: catalogo_topesconsumotienda
  path: app/Models/dbsiaw/catalogo_topesconsumotienda.php
  connection: mysql_dbsiaw
  table: catalogo_topesconsumotienda
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: false
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - tienda: belongsTo catalogo_tienda (tienda_id, pkid)
    - UsuarioCreate: belongsTo catalogo_usuario (created_by_id, pkid)
    - UsuarioUpdate: belongsTo catalogo_usuario (updated_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_topesconsumotiendaFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_topesconsumotiendaExternalResource.php
    - app/Http/Resources/dbsiaw/catalogo_topesconsumotiendaResource.php
  requests:
    - app/Http/Request/dbsiaw/Basecatalogo_topesconsumotiendaRequest.php
    - app/Http/Request/dbsiaw/StoreBulkcatalogo_topesconsumotiendaRequest.php
    - app/Http/Request/dbsiaw/Storecatalogo_topesconsumotiendaRequest.php
    - app/Http/Request/dbsiaw/Updatecatalogo_topesconsumotiendaRequest.php
    - app/Http/Request/dbsiaw/UpsertAllcatalogo_topesconsumotiendaRequest.php
  service: [app/Services/catalogo_topesconsumotiendaService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_topesconsumotiendaController.php]
  routes: [routes/topes_consumo_tienda.php]
- model: catalogo_turnos
  path: app/Models/dbsiaw/catalogo_turnos.php
  connection: mysql_dbsiaw
  table: catalogo_turnos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  filter: [app/Filters/dbsiaw/catalogo_turnosFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_turnosResource.php
  service_usado_en: [app/Services/catalogo_articulosService.php]
  controller: [app/Http/Controllers/Api/catalogo_turnosController.php]
  routes: [routes/api.php]
- model: catalogo_ubigeo
  path: app/Models/dbsiaw/catalogo_ubigeo.php
  connection: mysql_dbsiaw
  table: catalogo_ubigeo
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: false}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  relaciones:
    - created_by: belongsTo User (created_by_id, pkid)
    - updated_by: belongsTo User (updated_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_ubigeoFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_ubigeoRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_ubigeoResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_ubigeo/Basecatalogo_ubigeoRequest.php
    - app/Http/Request/dbsiaw/catalogo_ubigeo/Storecatalogo_ubigeoRequest.php
    - app/Http/Request/dbsiaw/catalogo_ubigeo/Updatecatalogo_ubigeoRequest.php
  service: [app/Services/catalogo_ubigeoService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_ubigeoController.php]
  routes: [routes/catalogo_ubigeo.php]
- model: catalogo_unidadmed
  path: app/Models/dbsiaw/catalogo_unidadmed.php
  connection: mysql_dbsiaw
  table: catalogo_unidadmed
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  filter: [app/Filters/dbsiaw/catalogo_unidadmedFilters.php]
  service_usado_en: [app/Services/catalogo_almacartService.php, app/Services/catalogo_articulosService.php]
  controller: [app/Http/Controllers/Api/catalogo_unidadmedController.php]
  routes: [routes/api.php]
- model: catalogo_usuario
  path: app/Models/dbsiaw/catalogo_usuario.php
  connection: mysql_dbsiaw
  table: catalogo_usuario
  pk: {name: pkid, incrementing: true, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  relaciones:
    - catalogo_whitelistedusers: hasMany catalogo_whitelistedusers (user_id, pkid)
    - groupsRelation: hasMany catalogo_usuario_group (user_id, pkid)
  resources:
    - app/Http/Resources/dbsiaw/catalogo_usuarioRelationResource.php
    - app/Http/Resources/dbsiaw/catalogo_usuarioResource.php
    - app/Http/Resources/dbsiaw/catalogo_usuarioWhiteResource.php
    - app/Http/Resources/dbsiaw/catalogo_usuario_fullResource.php
  service_usado_en: [app/Services/PermissionGuardService.php, app/Services/catalogo_solicitud_proveedorService.php, app/Services/catalogo_whitelistedusersService.php]
  controller_usado_en: [app/Http/Controllers/Api/catalogo_usuariosController.php]
  routes: [routes/api.php]
- model: catalogo_usuario_group
  path: app/Models/dbsiaw/catalogo_usuario_group.php
  connection: mysql_dbsiaw
  table: catalogo_usuario_groups
  pk: {name: id, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
  relaciones:
    - groupRelation: belongsTo auth_group (group_id, id)
- model: catalogo_usuariosexternos
  path: app/Models/dbsiaw/catalogo_usuariosexternos.php
  connection: mysql_dbsiaw
  table: catalogo_usuariosexternos
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: no
  has_factory: true
  auditoria: []
  controller_usado_en: [app/Http/Controllers/Api/api_externa/AuthExternalController.php]
  routes: [routes/external.php]
- model: catalogo_variables
  path: app/Models/dbsiaw/catalogo_variables.php
  connection: mysql_dbsiaw
  table: catalogo_variables
  pk: {name: id, incrementing: false, keyType: string, pkid_en_fillable: false}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - create_by: belongsTo catalogo_usuario (created_by_id, pkid)
    - update_by: belongsTo catalogo_usuario (updated_by_id, pkid)
    - delete_by: belongsTo catalogo_usuario (deleted_by_id, pkid)
  filter: [app/Filters/dbsiaw/catalogo_variablesFilters.php]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_variablesExternalResource.php
    - app/Http/Resources/dbsiaw/catalogo_variablesResource.php
  requests:
    - app/Http/Request/dbsiaw/Basecatalogo_variablesRequest.php
    - app/Http/Request/dbsiaw/Storecatalogo_variablesRequest.php
    - app/Http/Request/dbsiaw/Updatecatalogo_variablesRequest.php
  service: [app/Services/catalogo_variablesService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_variablesController.php]
  routes: [routes/catalogo_variables.php]
- model: catalogo_whitelistedusers
  path: app/Models/dbsiaw/catalogo_whitelistedusers.php
  connection: mysql_dbsiaw
  table: catalogo_whitelistedusers
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id, deleted_by_id]
  relaciones:
    - user: belongsTo User (user_id, pkid)
    - created_by: belongsTo User (created_by_id, pkid)
    - updated_by: belongsTo User (updated_by_id, pkid)
    - deleted_by: belongsTo User (deleted_by_id, pkid)
  resources:
    - app/Http/Resources/dbsiaw/catalogo_whitelistedusersResource.php
  requests:
    - app/Http/Request/dbsiaw/catalogo_whitelistedusers/StorecatalogWhitelistedusersRequest.php
  service: [app/Services/catalogo_whitelistedusersService.php]
  controller: [app/Http/Controllers/Api/dbsiaw/catalogo_whitelistedusersController.php]
  routes: [routes/catalogo_whitelistedusers.php]
- model: catalogo_zona
  path: app/Models/dbsiaw/catalogo_zona.php
  connection: mysql_dbsiaw
  table: catalogo_zona
  pk: {name: id, incrementing: false, keyType: default, pkid_en_fillable: true}
  soft_delete: deleted_at
  has_factory: true
  auditoria: [created_by_id, updated_by_id]
  resources:
    - app/Http/Resources/dbsiaw/catalogo_zonaResource.php
  controller: [app/Http/Controllers/Api/catalogo_zonaController.php]
  routes: [routes/api.php]
- model: sip_multitabladetalle
  path: app/Models/dbsip/sip_multitabladetalle.php
  connection: mysql_dbsip
  table: sip_multitabladetalle
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
- model: sip_personal
  path: app/Models/dbsip/sip_personal.php
  connection: mysql_dbsip
  table: sip_personal
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
  controller: [app/Http/Controllers/Api/dbsiaw/sip_personalController.php]
  routes: [routes/catalogo_estructura.php, routes/sip_personal.php]
- model: sip_personal_cargo
  path: app/Models/dbsip/sip_personal_cargo.php
  connection: mysql_dbsip
  table: sip_personalcargos
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
- model: sip_personalmovimientocargo
  path: app/Models/dbsip/sip_personalmovimientocargo.php
  connection: mysql_dbsip
  table: sip_personalmovimientocargo
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: false}
  soft_delete: no
  has_factory: false
  auditoria: []
  relaciones:
    - cargos: belongsTo sip_personal_cargo (cargo_personal_id, pkid)
  controller_usado_en: [app/Http/Controllers/Api/dbsiaw/catalogo_estructuraController.php, app/Http/Controllers/Api/dbsiaw/sip_personalController.php]
  routes: [routes/catalogo_estructura.php, routes/sip_personal.php]
- model: sip_personalplanillatda
  path: app/Models/dbsip/sip_personalplanillatda.php
  connection: mysql_dbsip
  table: sip_personalplanillatda
  pk: {name: pkid, incrementing: default, keyType: default, pkid_en_fillable: true}
  soft_delete: no
  has_factory: false
  auditoria: []
```
