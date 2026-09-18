# Model

Relacionado: [[Estandar Desarrollo Backend]] | [[CrudService]] | [[Mapeo UUID PKID]] | [[useFilters]] | [[Requests y Traits]]

---

Plantilla estándar del modelo Eloquent. Toda tabla de negocio sigue esta misma estructura: `pkid` (interno) + `id` (UUID público) + `*_by_id` de auditoría + soft deletes.

---

## Plantilla completa

```php
<?php

namespace App\Models\db{prefijo};

use Essa\APIToolKit\Filters\Filterable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\SoftDeletes;

class {prefijo}_{modulo} extends Model
{
    use SoftDeletes, Filterable;

    protected $connection  = '{conexion}';
    protected $table       = '{prefijo}_{modulo}';

    // Toda tabla de negocio del patrón (crud básico) tiene pkid + id:
    protected $primaryKey  = 'id';
    public    $incrementing = false;
    protected $keyType     = 'string';

    // Campos asignables por el Service.
    // Excluye siempre: pkid, id, created_at, updated_at, deleted_at
    // (id y los *_by_id los asigna el CrudService automáticamente)
    protected $fillable = [
        'id',
        'campo_uno',
        'campo_dos',
        'fk_id',            // almacena pkid (int) — llega como UUID del front
        'created_by_id',
        'updated_by_id',
        'deleted_by_id',
    ];

    protected $casts = [
        'activo' => 'boolean',
    ];

    // Relaciones con return type explícito.
    // El owner key siempre es 'pkid', nunca 'id'.
    public function relacion(): BelongsTo
    {
        return $this->belongsTo(OtroModelo::class, 'fk_id', 'pkid');
    }
}
```

---

## Relaciones — nombre de método vs. clave pública del Resource

El método `belongsTo` usa el **nombre literal de la tabla relacionada**, no una abreviatura sacada de la columna. Ejemplo: la columna `tienda_id` apunta a `catalogo_tienda` → el método se llama `catalogo_tienda()`, no `tienda()`.

```php
public function catalogo_tienda(): BelongsTo
{
    return $this->belongsTo(catalogo_tienda::class, 'tienda_id', 'pkid');
}
```

Por qué: el método identifica a la entidad real sin importar cómo se llame la columna que guarda la FK (una columna asignada a mano — ver [[Requests y Traits]] — puede no terminar en `_id`, o el mismo módulo puede tener dos columnas distintas apuntando a la misma tabla). El nombre corto ("tienda") no se pierde — se usa como **clave pública** en el `{Modulo}Resource` al exponer la relación (ver [[ApiResponse#Resource triple: completo, relación y tiny]]):

```php
'tienda' => $this->whenLoaded('catalogo_tienda', fn () => new TiendaRelationResource($this->catalogo_tienda)),
```

`const RELATIONS` en el [[Service del Módulo]] y `$allowedIncludes` en [[useFilters]] usan el nombre de MÉTODO (`catalogo_tienda`), nunca el alias corto — son los que Eloquent/`?include=` resuelven contra el Model.

**Excepción — colisión:** si dos columnas del mismo módulo apuntan a la MISMA tabla (ej. `tienda_origen_id` y `tienda_destino_id`, ambas a `catalogo_tienda`), el nombre literal no alcanza para distinguir los dos métodos. Ahí sí se cae al nombre derivado de columna (`tienda_origen()` / `tienda_destino()`) — es la única forma de tener dos métodos distintos hacia la misma tabla.

---

## Propiedades clave y para qué sirven

| Propiedad / método              | Para qué sirve                                                                                              |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `$fillable`                     | Define qué campos puede escribir el Service — también guía las reglas de [[Requests y Traits]]              |
| `$casts`                        | Tipado automático al leer/escribir (`boolean`, `decimal:2`, `array`, `date`, `datetime`)                    |
| `$primaryKey` + `$incrementing` | Determina si el `unique ignore` de [[Requests y Traits]] usa `pkid` o `id`                                  |
| `getRouteKeyName()`             | Determina el campo que usa el Route Model Binding del [[Controller]] para resolver el modelo desde la URL. Con `$primaryKey = 'id'` (el caso normal del patrón), Laravel ya devuelve `'id'` por defecto sin declarar el método — por eso no está en la plantilla de arriba. Solo hace falta declararlo si el campo de ruta fuera distinto de `$primaryKey` (ver [[Controller#Route Model Binding]]) |
| Métodos `BelongsTo`             | Insumo para `$uuidMapping` en [[Service del Módulo]] y para `whenLoaded()` en [[ApiResponse\|Resource]]     |
| Métodos `HasMany`               | Relaciones a cargar con `with()` en index/show y `whenLoaded()` en el Resource                              |
| `use Filterable`                | Habilita `Model::useFilters()` — ver [[useFilters]]                                                         |

---

## Regla: pkid vs id como PK

Toda tabla de negocio que sigue el patrón (crud básico) tiene **ambos** campos: `pkid` (autoincrement, para relaciones/FK en código y DB) e `id` (UUID, expuesto al front). El ignore del `unique` en Update siempre va contra `pkid`.

| Tipo de tabla                                                          | `$primaryKey` | `$incrementing` | unique ignore en Update  |
| ----------------------------------------------------------------------- | ------------- | --------------- | ------------------------- |
| Tabla de negocio (patrón completo, con `pkid` + `id`)                  | `id`          | `false`         | `, {$model->pkid}, pkid` |
| Tabla fuera del patrón (infraestructura/Laravel/Docker, sin `pkid`)     | `id`          | `false`         | `, {$model->id}, id`     |

La segunda fila **no aplica a los módulos del crud básico** — es solo para tablas que no forman parte del patrón (migraciones base generadas por `artisan`, tablas de infraestructura, etc.), que no pasan por Service/Controller de este estándar.

Esta distinción se replica en:
- [[Mapeo UUID PKID]] — a qué campo apunta la FK
- [[Requests y Traits]] — formato del `unique` en `UpdateRequest`

---

## Campos siempre presentes en la tabla

```
pkid           → autoincrement interno (si aplica el patrón completo)
id             → UUID, PK pública, asignada por el CrudService al crear
...campos propios del modelo...
created_by_id  → asignado por CrudService via Token
updated_by_id  → asignado por CrudService via Token
deleted_by_id  → asignado por CrudService via Token
created_at / updated_at → timestamps de Laravel
deleted_at     → SoftDeletes de Laravel
```

Estos campos **nunca** van en el `$fillable` de usuario ni en las reglas de validación de [[Requests y Traits]] (excepto `id`, que el CrudService asigna, y los `*_by_id`, que asigna el CrudService).

---

## Modelos catálogo — trait compartido (Concerns)

Cuando 2 o más tablas del proyecto son catálogos puros con la misma forma (`id`, `nombre`, `descripcion`, `activo` + auditoría, sin relaciones de negocio propias), extraer lo común a un trait en `app/Models/db{prefijo}/Concerns/{Prefijo}CatalogoModel.php` y usarlo en cada modelo concreto — no repetir `$fillable`/`$casts` base ni los `belongsTo` de auditoría en cada clase.

**Regla dura — qué NUNCA va en el trait:** `$connection`, `$primaryKey`, `$incrementing`, `$keyType`, `$fillable`, `$casts` y `$table` se declaran **siempre en el modelo concreto**, nunca en el trait — incluso si el valor es idéntico en todos los modelos que lo usan. PHP exige que una propiedad compuesta por un trait sea idéntica a la misma propiedad ya declarada en la jerarquía de la clase (`Illuminate\Database\Eloquent\Model` ya declara `$connection`, `$primaryKey`, `$keyType`, `$incrementing`) o en la propia clase que usa el trait; si difiere, es fatal error de composición ("Class was composed") en tiempo de carga — no en tiempo de ejecución de un método puntual, así que revienta cualquier request o comando que toque el modelo.

En el trait solo van: métodos (relaciones, scopes) y propiedades que ningún ancestro de `Model` ni ninguna clase concreta vuelven a declarar (ej. una propiedad propia del proyecto como `$default_filters`).

### Trait — plantilla

```php
<?php

namespace App\Models\db{prefijo}\Concerns;

use App\Models\db{prefijo_siaw}\{Prefijo}Usuarios;

trait {Prefijo}CatalogoModel
{
    // Solo propiedades/métodos que NINGÚN modelo concreto va a redeclarar con otro valor.

    public function created_by(): BelongsTo
    {
        return $this->belongsTo({Prefijo}Usuarios::class, 'created_by_id', 'pkid');
    }
    public function updated_by(): BelongsTo
    {
        return $this->belongsTo({Prefijo}Usuarios::class, 'updated_by_id', 'pkid');
    }
    public function deleted_by(): BelongsTo
    {
        return $this->belongsTo({Prefijo}Usuarios::class, 'deleted_by_id', 'pkid');
    }
}
```

### Modelo concreto — plantilla (copiar el bloque de 7 propiedades tal cual en cada catálogo)

```php
<?php

namespace App\Models\db{prefijo};

use App\Models\db{prefijo}\Concerns\{Prefijo}CatalogoModel;
use Essa\APIToolKit\Filters\Filterable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\SoftDeletes;

class {Prefijo}{Catalogo} extends Model
{
    use SoftDeletes, Filterable, {Prefijo}CatalogoModel;

    protected $connection   = '{conexion}';
    protected $primaryKey   = 'id';
    public    $incrementing = false;
    protected $keyType      = 'string';

    protected $table = '{prefijo}_{catalogo}';

    // Base común a todo catálogo — copiar siempre estos 7 campos.
    // Si el catálogo tiene columnas propias (ej: codigo_iso, comision_pct),
    // agregarlas acá — nunca en el trait.
    // created_at/updated_at/deleted_at NUNCA van acá — Laravel los escribe
    // solo (timestamps() + SoftDeletes), no son asignables por el Service
    // (ver "Campos siempre presentes en la tabla" más arriba).
    protected $fillable = [
        'id',
        'nombre',
        'descripcion',
        'activo',
        'created_by_id',
        'updated_by_id',
        'deleted_by_id',
    ];

    // Base común — agregar acá los casts de columnas propias del catálogo.
    // created_at/updated_at NO se castean a mano: Eloquent ya los trata como
    // Carbon (datetime) automáticamente — castearlos a 'date' acá truncaría
    // la hora.
    protected $casts = [
        'activo' => 'boolean',
    ];
}
```

---

## Convención de nombres de migraciones (`php artisan make:migration`)

Laravel adivina la tabla (`--table`) y si es creación o no a partir del **nombre** de la migración — pero solo reconoce patrones específicos. Usar el nombre correcto evita pasar `--table=` a mano y evita migraciones sin la tabla detectada.

| Operación | Patrón de nombre | Detecta tabla | `create` |
|---|---|---|---|
| Crear tabla nueva | `create_{tabla}_table` | Sí | `true` |
| Agregar columna(s) | `add_{campo}_to_{tabla}_table` | Sí | `false` |
| Quitar columna(s) | `remove_{campo}_from_{tabla}_table` | Sí | `false` |
| Quitar columna(s) (alias) | `drop_{campo}_from_{tabla}_table` | Sí | `false` |

```bash
php artisan make:migration create_siaw_permiso_usuario_table
php artisan make:migration add_audit_columns_to_siaw_permiso_usuario_table
php artisan make:migration remove_activo_from_siaw_menus_table
```

**Ojo:** no existe un prefijo `mod_` reconocido por Laravel. Para cualquier otra modificación que no sea agregar/quitar columnas (cambiar tipo, renombrar, agregar índice compuesto, etc.), el nombre no importa para la detección — pasar la tabla explícita:

```bash
php artisan make:migration cambiar_tipo_columna_activo --table=siaw_menus
```

Regla práctica: si el nombre no calza en alguno de los 3 patrones de la tabla de arriba, agregar `--table={tabla}` siempre, para no depender de que el archivo generado adivine bien.
