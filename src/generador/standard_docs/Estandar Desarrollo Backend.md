# Estándar Desarrollo Backend

Nodos del flujo: [[Controller]] → [[Service del Módulo]] → [[CrudService]] → [[Model]]
Soporte: [[useFilters]] | [[Requests y Traits]] | [[Auditoría]] | [[Mapeo UUID PKID]] | [[ApiResponse]] | [[Documentación Swagger (OpenAPI)]] | [[Migraciones y Catálogos]] | [[Conexiones, Migraciones y Rutas]]
Ver también: [[Service Patron]]

---

## Convención de prefijos

Los nombres de modelos, tablas y carpetas llevan un prefijo según el proyecto. **No es parte del patrón**, es una convención de negocio, Por dar Ejemplo : 

| Proyecto               | Prefijo | Conexión Eloquent | Ejemplo        |
| ---------------------- | ------- | ------------------ | -------------- |
| Sistema de Personal    | `sip_`  | `dbsip`            | `sip_personal` |
| Mundo Destinos Travels | `mdt_`  | `dbmdt`            | `mdt_reservas` |
| Gab System Prod        | `gsp_`  | `dbgsp`            | `gsp_facturas` |

El patrón aplica igual sin importar el prefijo. La conexión Eloquent es siempre `db{prefijo}` — ver [[Conexiones, Migraciones y Rutas#1. Conexiones de base de datos — regla de nombres]] para la regla completa, incluidas las dos conexiones fijas (`dbsiaw`, `dbsincro`) que todo proyecto nuevo tiene además de la suya propia.

---

## Flujo General

```
Frontend (query params / body)
        ↓
  [[Controller]]
  solo orquesta — sin lógica de negocio
        ↓
  [[Requests y Traits]]
  valida el input (store / update) antes de que el método del Controller ejecute
        ↓
  [[Service del Módulo]]
  mapea IDs (UUID → PKID), lógica de negocio
        ↓
  [[CrudService]]
  CRUD base + [[Auditoría]]
        ↓
  [[Model]] (Eloquent)
  [[useFilters]] → [[useFilters|dynamicPaginate]]
        ↓
  [[ApiResponse]]
  transforma con Resource / RelationResource / TinyResource 
```

---

## Estructura de Carpetas

```
app/
├── Http/
│   ├── Controllers/Api/
│   │   └── {Prefijo}/
│   │       └── {prefijo}_{modulo}Controller.php    → [[Controller]]
│   ├── Requests/
│   │   └── {Prefijo}/
│   │       ├── {Modulo}/                            → [[Requests y Traits]]
│   │       │   ├── Store{Modulo}Request.php
│   │       │   └── Update{Modulo}Request.php
│   │       └── Traits/
│   │           ├── {Modulo}/
│   │           │   └── Validates{Modulo}.php
│   │           └── Validates{Fk}.php                 → opcional, un trait por FK compartida entre 2+ módulos
│   └── Resources/
│       └── {Prefijo}/                                → [[ApiResponse]]
│           ├── {Modulo}Resource.php                  → respuesta completa
│           ├── {Modulo}RelationResource.php          → versión mínima (whenLoaded desde OTRO módulo)
│           └── {Modulo}TinyResource.php               → versión mínima (`?tiny=true`, selectores del propio módulo)
├── Services/
│   ├── AbstractModuleService.php                     → [[Service del Módulo]]
│   ├── CrudService.php                               → [[CrudService]]
│   └── {Modulo}Service.php                           → [[Service del Módulo]]
├── Filters/
│   └── {Prefijo}_{modulo}Filters.php                 → [[useFilters]]
├── Models/
│   └── db{prefijo}/
│       └── {prefijo}_{modulo}.php                    → [[Model]]
└── Providers/
    ├── AppServiceProvider.php                        → registra el ledger de migraciones centralizado, ver [[Conexiones, Migraciones y Rutas#2. Migraciones — carpeta por módulo, ledger centralizado]]
    └── RouteServiceProvider.php                      → auto-carga routes/modules/*.php bajo auth, ver [[Conexiones, Migraciones y Rutas#4. Rutas — `RouteServiceProvider` y el CRUD de una línea]]

database/
└── migrations/
    └── {Modulo}/                                     → cada migración fija su propia `$connection` — ver [[Migraciones y Catálogos]] (diseño de tabla) y [[Conexiones, Migraciones y Rutas]] (conexión + ledger)
        └── ..._create_{prefijo}_{modulo}_table.php

routes/
└── modules/
    └── {modulo}.php                                  → `Route::apiResource()`, una línea — ver [[Conexiones, Migraciones y Rutas#4. Rutas — `RouteServiceProvider` y el CRUD de una línea]]
```

---

## Resumen de responsabilidades

| Capa | Responsabilidad |
|---|---|
| [[Controller]] | Orquesta. Recibe request, llama service (incluye `index`/`show`), retorna [[ApiResponse]] — nunca arma queries ni carga relaciones |
| [[Requests y Traits]] | Valida input (store/update) antes de llegar al Controller |
| [[Service del Módulo]] | Lógica de negocio completa: `index`/`getAll`, `show`, `store`, `update`, `destroy`, [[Mapeo UUID PKID]], decide paginación, carga de relaciones (`RELATIONS`) |
| [[CrudService]] | CRUD base reutilizable + [[Auditoría]] |
| [[Model]] | Estructura Eloquent: pkid/id, fillable, casts, relaciones |
| [[useFilters]] | Filtros del request + paginación dinámica |
| [[Auditoría]] | Registro de cambios con input/output JSON |
| [[Mapeo UUID PKID]] | Resolución UUID → PKID antes de persistir |
| [[ApiResponse]] | Estructura estándar de respuestas HTTP + Resource / RelationResource / TinyResource |
| [[Conexiones, Migraciones y Rutas]] | Arranque de proyecto: nombres de conexión, ledger de migraciones + seeders centralizados en `dbsincro`, registro de rutas y cuándo mapear permiso |
