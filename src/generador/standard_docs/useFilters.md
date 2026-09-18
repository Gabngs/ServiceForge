# useFilters y dynamicPaginate

Relacionado: [[Estandar Desarrollo Backend]] | [[Service del Módulo]] | [[CrudService]] | [[Model]] | [[Controller]] | [[Filtros de Consulta]] (frontend)

---

Provistos por el paquete **Essa APIToolKit**. `useFilters()` aplica filtros del request al query. `dynamicPaginate()` pagina el resultado.

**`useFilters()` siempre se aplica**, sea que la respuesta se pagine o no.

---

## Cómo funciona useFilters()

```php
// En el Service:
{prefijo}_{modulo}::useFilters()
```

1. Lee el nombre del modelo (`{prefijo}_{modulo}`)
2. Busca la clase `App\Filters\{Prefijo}_{modulo}Filters` (o ruta equivalente configurada)
3. La instancia con el request actual
4. Aplica cada filtro declarado como scope al query Builder
5. Retorna el Builder con todos los filtros aplicados

Requiere que el [[Model]] use el trait `Filterable`.

---

## La clase Filters del modelo

Cada modelo tiene su propia clase Filters. Vive en `app/Filters/` o en la ruta que configure el proyecto.

```php
<?php

namespace App\Filters;

use Essa\APIToolKit\Filters\QueryFilters;

class {Prefijo}_{modulo}Filters extends QueryFilters
{
    // Campos propios incluidos en la búsqueda de texto libre (?search=)
    // OJO: la propiedad real de QueryFilters se llama $columnSearch, NO $allowedSearch
    // (nombre fácil de confundir con $allowedFilters — no existe $allowedSearch en el paquete).
    protected array $columnSearch = ['nombre', 'codigo', 'descripcion'];

    // Relaciones incluidas en la búsqueda de texto libre (?search=), vía whereHas()
    // Formato: 'relacion' => ['columna1', 'columna2']
    protected array $relationSearch = ['tienda' => ['nombre']];

    // Campos permitidos para filtro por valor exacto (WHERE campo = valor).
    // Solo columnas directas (bool, fecha, int propio, string). Los FK *_id que
    // guardan pkid NO van acá — van como método resolver (ver sección más abajo).
    protected array $allowedFilters = ['activo'];

    // Relaciones permitidas para eager loading desde query param
    // ?includes=tienda,cargo — PLURAL. FiltersDTO::buildFromRequest() lee
    // $request->get('includes'); "include" en singular no matchea nada,
    // explode(',', null) devuelve [''], array_intersect() da vacío, y la
    // relación queda sin cargar en silencio (sin error, sin warning visible).
    protected array $allowedIncludes = ['tienda', 'cargo'];

    // Campos permitidos para ordenamiento
    // ?sorts=nombre o ?sorts=-nombre (descendente)
    protected array $allowedSorts = ['nombre', 'created_at'];
}
```

### Las 5 propiedades de QueryFilters

| Propiedad | Query param | Match | Nota |
|---|---|---|---|
| `$allowedFilters` | `?campo=valor` | `WHERE campo = valor` (o `whereIn` si el valor trae comas) | Match exacto, no LIKE. **Solo columnas directas** — un FK que guarda `pkid` no va acá, va como método (ver abajo) |
| `$columnSearch` | `?search=texto` | `WHERE col LIKE '%texto%'` (OR entre todas las columnas listadas) | Búsqueda libre en columnas propias |
| `$relationSearch` | `?search=texto` | `orWhereHas('relacion', ... LIKE '%texto%')` | Búsqueda libre en columnas de relaciones, se combina con `$columnSearch` en el mismo `search=` |
| `$allowedIncludes` | `?includes=rel1,rel2` | `.with([...])` | Plural, ver nota arriba |
| `$allowedSorts` | `?sorts=campo` / `?sorts=-campo` | `ORDER BY` | Solo toma el primer valor de la lista separada por comas |

---

## Métodos personalizados por filtro (override de `allowedFilters`)

`useFilters()` primero ejecuta **todos** los métodos cuyo nombre coincide con un query param (`applyCustomFilters()`), y **después** corre el pipeline genérico que aplica `WHERE campo = valor` para cada campo listado en `$allowedFilters`. Es decir: si un campo está en `$allowedFilters` **y además** tiene método, se aplican los dos `where` — el custom y el genérico. Por eso, cuando se escribe un método para un campo, ese campo **no debe estar en `$allowedFilters`**.

```php
class {Prefijo}_{modulo}Filters extends QueryFilters
{
    // ?codigo=AB → WHERE codigo LIKE '%AB%' (en vez del exact-match que daría allowedFilters)
    public function codigo($term)
    {
        return $this->builder->where('codigo', 'LIKE', "%{$term}%");
    }

    // ?categoria=texto → filtra por descripción de la relación, no por el campo propio
    public function categoria($term)
    {
        return $this->builder->whereHas('categoria', function ($query) use ($term) {
            $query->where('descripcion', 'LIKE', "%{$term}%");
        });
    }
}
```

**Cuidado con LIKE en IDs:** usar `LIKE` en vez de `=` sobre un ID produce matches parciales indeseados — `?tienda_id=1` con `LIKE '%1%'` también trae `tienda_id` 10, 11, 21, 100... Un método custom para un FK siempre usa `=`, nunca `LIKE`.

---

## FKs que guardan `pkid` — el filtro `*_id` SIEMPRE necesita método resolver

Ver [[Mapeo UUID PKID]]. En los módulos donde el modelo expone `id` (UUID) al front pero las columnas FK persisten el `pkid` (int) del registro relacionado (todo AGH, `dbgsp_agh`; también `dbgsp` almuerzos y varias tablas SIAW), **`$allowedFilters` no sirve para los campos `*_id`**: el genérico haría `WHERE habitacion_id = '9c1f...uuid'` contra una columna que contiene enteros y no matchea nunca — el filtro se ignora en silencio (sin 400, sin error), la tabla simplemente trae de más.

Regla: **cada campo `*_id` que apunte a una tabla con `pkid` se saca de `$allowedFilters` y se implementa como método** que resuelve el UUID a su `pkid` antes de filtrar. Solo quedan en `$allowedFilters` los campos que son columna directa: booleanos (`activo`, `es_vendible`), fechas (`fecha`, `fecha_checkin`), enteros propios (`piso`) y strings (`referencia_tipo`).

```php
<?php

namespace App\Filters\Agh;

use App\Models\dbgsp_agh\AghHabitaciones;
use App\Models\dbgsp_agh\AghEstadosTareaLimpieza;
use App\Models\dbgsp_siaw\SiawUsuarios;
use Essa\APIToolKit\Filters\QueryFilters;

class AghTareasLimpiezaFilters extends QueryFilters
{
    // Sin *_id acá: cada uno tiene su método resolver abajo
    protected array $allowedFilters  = [];
    protected array $allowedSorts    = ['created_at', 'iniciada_en', 'finalizada_en'];
    protected array $allowedIncludes = ['habitacion', 'tipoTarea', 'estadoTarea', 'asignadoA'];
    protected array $columnSearch    = ['notas'];

    /** ?habitacion_id={uuid} → resuelve a pkid. */
    public function habitacion_id($value)
    {
        if ($value === null || $value === '') {
            return $this->builder;
        }

        $pkid = AghHabitaciones::where('id', $value)->value('pkid');

        return $this->builder->where('habitacion_id', $pkid ?? 0);
    }

    /** ?estado_tarea_id={uuid} → resuelve a pkid. */
    public function estado_tarea_id($value)
    {
        if ($value === null || $value === '') {
            return $this->builder;
        }

        $pkid = AghEstadosTareaLimpieza::where('id', $value)->value('pkid');

        return $this->builder->where('estado_tarea_id', $pkid ?? 0);
    }

    /** ?asignado_a_id={uuid} → resuelve a pkid (FK a siaw_usuarios). */
    public function asignado_a_id($value)
    {
        if ($value === null || $value === '') {
            return $this->builder;
        }

        $pkid = SiawUsuarios::where('id', $value)->value('pkid');

        return $this->builder->where('asignado_a_id', $pkid ?? 0);
    }
}
```

Puntos del patrón:

| Detalle | Por qué |
|---|---|
| Guard `null`/`''` → `return $this->builder` sin tocar el query | El front manda el param vacío cuando el usuario limpia el filtro; no debe filtrar por nada |
| `Modelo::where('id', $value)->value('pkid')` | 1 sola columna, sin hidratar el modelo |
| `->where('col', $pkid ?? 0)` | Si el UUID no existe, `pkid` es `null`; forzar `0` hace que el filtro devuelva vacío (correcto) en vez de `WHERE col IS NULL` (traería las filas con FK nula) |
| El modelo resolver es **la tabla destino de la FK**, no la propia | `habitacion_id` en tareas → `AghHabitaciones`; `asignado_a_id` → `SiawUsuarios` (cruza conexión sin problema) |
| Nombre del método = nombre exacto del query param | `applyCustomFilters()` hace `method_exists($this, $name)` |

El mapeo campo→modelo destino sale del `belongsTo(..., 'fk_col', 'pkid')` del [[Model]]. Es el mismo diccionario que el `$uuidMapping` del [[Service del Módulo]] para create/update — conviene mantenerlos alineados.

### Params que acepta según la configuración

| Query param | Tipo | Ejemplo | Resultado |
|---|---|---|---|
| `search=texto` | LIKE en `columnSearch` (+ `relationSearch` si aplica) | `?search=lima` | `WHERE nombre LIKE '%lima%'` |
| `activo=1` | Exact match (columna directa en `$allowedFilters`) | `?activo=1` | `WHERE activo = 1` |
| `tienda_id={uuid}` | Método resolver UUID→pkid (FK que guarda `pkid`) | `?tienda_id=9c1f...` | `WHERE tienda_id = 42` |
| `includes=tienda` | Eager load (plural, no "include") | `?includes=tienda` | `.with(['tienda'])` |
| `sorts=nombre` | Order ASC | `?sorts=nombre` | `ORDER BY nombre ASC` |
| `sorts=-created_at` | Order DESC | `?sorts=-created_at` | `ORDER BY created_at DESC` |

---

## dynamicPaginate()

Se encadena sobre el Builder. Lee `page` y `per_page` del request.

```php
{prefijo}_{modulo}::useFilters()->dynamicPaginate();
```

| Query param | Descripción | Default |
|---|---|---|
| `page` | Número de página | 1 |
| `per_page` | Registros por página | 15 |
| `pagination=none` | Desactiva paginación — retorna todo | — |

---

## Condicional de paginación

```php
// ── En el Controller ─────────────────────────────────────────────────────────
public function index(Request $request)
{
    // boolean() retorna true solo si el valor es "true", "1", "on", "yes"
    // Si no llega el param, o llega "false"/"0" → retorna false
    $paginate = $request->boolean('paginate');

    $data = $this->service->index($paginate);

    return $this->responseSuccess(
        'Registros obtenidos correctamente',
        {Modulo}Resource::collection($data)
    );
}

// ── En el Service ─────────────────────────────────────────────────────────────
public function index(bool $paginate = false): mixed
{
    $query = {prefijo}_{modulo}::useFilters()->with(['tienda']);

    return $paginate
        ? $query->dynamicPaginate()  // LengthAwarePaginator
        : $query->get();             // Collection
}
```

---

## Respuesta paginada — `?paginate=true&page=1&per_page=30`

**Ojo:** `responseSuccess()` NO tiene manejo especial para paginadores — si se le pasa el `LengthAwarePaginator` tal cual (sin pasar por el Resource primero), su `toArray()` trae sus propias claves (`current_page`, `data`, `total`, ...), y esas quedan anidadas dentro del `data` de la respuesta → **`data.data`**, que es justamente lo que hay que evitar. La forma correcta transforma los items con el Resource y manda la metadata de paginación en una clave `meta` al mismo nivel que `data` — ver [[ApiResponse#Paginación sin duplicar `data`]] para el código completo del Controller.

```json
{
    "status": 200,
    "message": "Registros obtenidos correctamente",
    "data": [
        { "id": "abc123", "nombre": "Producto A", "activo": 1 },
        { "id": "def456", "nombre": "Producto B", "activo": 1 }
    ],
    "meta": {
        "current_page": 1,
        "last_page": 3,
        "per_page": 30,
        "total": 75,
        "from": 1,
        "to": 30
    }
}
```

Las 6 claves de `meta` reflejan 1:1 `IModelBasePaginate` del frontend — ver [[ApiResponse#Paginación sin duplicar `data`]].

## Respuesta sin paginar — sin `paginate` o `?paginate=false`

```json
{
    "status": 200,
    "message": "Registros obtenidos correctamente",
    "data": [
        { "id": "abc123", "nombre": "Producto A", "activo": 1 },
        { "id": "def456", "nombre": "Producto B", "activo": 1 }
    ]
}
```

---

## Uso en el frontend — cómo armar los filtros

**Corrección:** la versión anterior de esta nota armaba los filtros con `const filters: any = {}`. Eso pierde el único chequeo que evita mandar un query param que `$allowedFilters` no reconoce — y como `useFilters()` ignora en silencio cualquier campo no declarado (no hay 400, el filtro simplemente no aplica), un typo ahí no se nota en el request, se nota en que la tabla trae de más. La forma correcta tipa una interfaz `I{Entidad}Filtros` que **extiende `IFiltersBase`** y se mapea 1:1 contra la clase `Filters` del modelo — ver [[Filtros de Consulta]] para el patrón completo (interfaz, `buildFiltros()` del componente, `buildParams()` del service). `paginate`/`page`/`per_page` y los filtros casi-universales `activo`/`search` los aporta `IFiltersBase` (ver [[ApiResponse Frontend]]); `I{Entidad}Filtros` solo agrega los campos propios del módulo.

```typescript
// interfaces/models/{entidad}.ts — campos propios; el resto viene de IFiltersBase
import { IFiltersBase } from '../shared/model-base.interface';

export interface I{Entidad}Filtros extends IFiltersBase {
  tienda_id?: string;
}

// Con paginación — 'meta' es sibling de 'data', no anidado (ver [[ApiResponse#Paginación sin duplicar `data`]])
const filters: I{Entidad}Filtros = { ...this.buildFiltros(), paginate: true, page: this.currentPage, per_page: 20 };

this.service.getIndex(filters).subscribe(response => {
    this.rows  = response.data;
    this.total = response.meta?.total ?? 0;
});

// Sin paginación (ej: para un select/dropdown) — mismo buildFiltros(), sin page/per_page
this.service.getIndex(this.buildFiltros()).subscribe(response => {
    this.opciones = response.data; // array plano
});
```
