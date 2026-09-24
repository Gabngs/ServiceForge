# ApiResponse

Relacionado: [[Estandar Desarrollo Backend]] | [[Controller]]

---

Trait de **Essa APIToolKit** usado en todos los [[Controller|controllers]]. Estandariza la estructura de respuestas HTTP. 
Es Requerido por lo que se debe validar que este disponible.

---

## Declaración en el Controller

```php
use Essa\APIToolKit\Api\ApiResponse;

class {prefijo}_{modulo}Controller extends Controller
{
    use ApiResponse;
}
```

---

## Métodos y sus respuestas

### responseSuccess — 200

```php
return $this->responseSuccess('Registros obtenidos correctamente', $data);
```

```json
{
    "status": 200,
    "message": "Registros obtenidos correctamente",
    "data": { }
}
```

### responseNotFound — 404

```php
return $this->responseNotFound('Registro no encontrado', 'Error');
```

```json
{
    "status": 404,
    "message": "Registro no encontrado",
    "errors": "Error"
}
```

### responseBadRequest — 400

```php
return $this->responseBadRequest('El parámetro parent_name es requerido', 'Error');
```

```json
{
    "status": 400,
    "message": "El parámetro parent_name es requerido",
    "errors": "Error"
}
```

### responseError — 500

```php
return $this->responseError('No se pudo procesar la solicitud', 'Error');
```

```json
{
    "status": 500,
    "message": "No se pudo procesar la solicitud",
    "errors": "Error"
}
```

### Respuesta de validación — 422 (automática)

Cuando un FormRequest falla, Laravel retorna automáticamente:

```json
{
    "status": 422,
    "message": "The given data was invalid.",
    "errors": {
        "nombre": ["El nombre es requerido"],
        "tienda_id": ["La tienda no existe"]
    }
}
```

No hay que llamar nada en el controller — el FormRequest lo maneja solo.

La **misma respuesta** se obtiene cuando un [[Service del Módulo]] lanza `ValidationException::withMessages([...])` por una regla de negocio (ver [[Service del Módulo#Errores de negocio — el Service los lanza, el frontend solo los muestra]]): el Controller no cambia. Por eso los errores de negocio no pasan por `responseBadRequest`/`responseError` en el Controller — esos métodos quedan para casos puntuales de infraestructura, no para reglas de negocio.

---

## Con Resource — transformación de datos

```php
use App\Http\Resources\{Prefijo}\{Modulo}Resource;

// Un solo registro
return $this->responseSuccess(
    'Registro obtenido correctamente',
    new {Modulo}Resource($model)
);

// Colección (index sin paginación)
return $this->responseSuccess(
    'Registros obtenidos correctamente',
    {Modulo}Resource::collection($data)
);

// Colección paginada (index con paginate=true)
// OJO: si $data es un LengthAwarePaginator y se pasa TAL CUAL a responseSuccess(),
// su propio toArray() trae 'current_page', 'data', 'total', etc. — eso produce
// data.data (el array de items queda anidado dos niveles). Ver "Paginación sin
// duplicar `data`" más abajo para la forma correcta.
return $this->responseSuccess(
    'Registros obtenidos correctamente',
    {Modulo}Resource::collection($data)
);
```

---

## Paginación sin duplicar `data`

`responseSuccess($message, $data)` simplemente asigna `$data` tal cual a la clave `data` — no tiene ningún manejo especial para paginadores. Esto tiene una consecuencia poco intuitiva según qué se le pase:

| Qué se pasa como `$data` | Resultado |
|---|---|
| `{Modulo}Resource::collection($paginator)` | `data` queda como **array plano** de items — la metadata de paginación (`total`, `current_page`, etc.) se pierde por completo |
| El `$paginator` (LengthAwarePaginator) sin envolver en Resource | `data` queda con `{current_page, data: [...], total, ...}` — **esto es el `data.data` que hay que evitar** |

Ninguna de las dos por sí sola es correcta si el frontend necesita armar un paginador (total de páginas, etc.). La forma correcta es transformar los items con el Resource, extraerlos como array plano, y mandar la metadata de paginación como una clave `meta` **al mismo nivel que `data`** — nunca anidada dentro de `data`:

```php
public function index(Request $request)
{
    $paginate = $request->boolean('paginate');
    $data = $this->service->index($paginate); // Collection o LengthAwarePaginator

    if (! $paginate) {
        return $this->responseSuccess(
            'Registros obtenidos correctamente',
            {Modulo}Resource::collection($data)
        );
    }

    // $data es LengthAwarePaginator: se transforman solo los items (array plano)
    // y se agrega 'meta' al mismo nivel que 'data' — nunca dentro de 'data'.
    $response = $this->responseSuccess(
        'Registros obtenidos correctamente',
        {Modulo}Resource::collection($data->items())
    );

    return $response->setData(array_merge($response->getData(true), [
        'meta' => [
            'current_page' => $data->currentPage(),
            'last_page'    => $data->lastPage(),
            'per_page'     => $data->perPage(),
            'total'        => $data->total(),
            'from'         => $data->firstItem(),
            'to'           => $data->lastItem(),
        ],
    ]));
}
```

Simplificado a propósito para mostrar solo el mecanismo de `meta`. El `index()` real del Controller combina esto con la selección de Resource por `?tiny=true` (`{Modulo}Resource` vs `{Modulo}TinyResource`) — ver el ejemplo completo en [[Controller#Ejemplo completo]].

Resultado — `status`/`message`/`data` se respetan siempre, `data` es siempre un array (paginado o no), y la metadata vive aparte:

```json
{
    "status": 200,
    "message": "Registros obtenidos correctamente",
    "data": [
        { "id": "abc123", "nombre": "Producto A" },
        { "id": "def456", "nombre": "Producto B" }
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

**Regla práctica:** `data` nunca contiene otra clave `data` adentro. Si un método de `index` puede pagar o no (`?paginate=true`), la metadata de paginación va en `meta`, sibling de `data` — nunca reemplazando la forma de `data` (que siempre es un array de items, paginado o no).

**Las 6 claves de `meta` no son arbitrarias — reflejan 1:1 `IModelBasePaginate` del frontend** (`interfaces/shared/model-base.interface.ts`: `current_page, per_page, total, last_page, from, to`). `firstItem()`/`lastItem()` son métodos nativos de `LengthAwarePaginator` (ordinal del primer/último item de la página actual, `null` si la página está vacía) — no hace falta calcularlos a mano. Si `meta` se arma con menos de estas 6 claves, el frontend recibe `from`/`to` como `undefined` en runtime aunque la interfaz los declare como requeridos — mismo problema que describe [[Interfaz de Modulo]] para `IModelBase` y los campos de auditoría no poblados.

---

## Resource triple: completo, relación y tiny

Cada módulo define **tres** Resources, cada uno para una audiencia distinta:

- **`{Modulo}Resource`** — completo. Respuesta directa de `index`/`show`/`store`/`update`/`destroy` cuando no se pide `?tiny=true`.
- **`{Modulo}RelationResource`** — mínimo, para cuando **otro** módulo carga este como relación anidada (`whenLoaded()`). Evita exponer campos de más y previene N+1 por relaciones anidadas dentro del Resource completo.
- **`{Modulo}TinyResource`** — mínimo, para cuando **este propio** módulo responde a `?tiny=true` en su `index`. Pensado para selectores/dropdowns del frontend que solo necesitan mostrar una etiqueta y guardar un id — mandar el Resource completo ahí es desperdiciar payload en campos que la UI nunca usa.

`RelationResource` y `TinyResource` suelen tener una forma parecida (ambos "livianos"), pero resuelven problemas distintos: uno lo arma OTRO módulo al cargar `whenLoaded()`, el otro lo arma el propio Controller del módulo al recibir `?tiny=true` — ver la tabla "Regla para saber cuál usar" más abajo.

### `{Modulo}Resource` — completo

Usado en `index`, `show`, `store`, `update`, `destroy`. Expone todos los campos relevantes del módulo.

```php
<?php

namespace App\Http\Resources\{Prefijo};

use Illuminate\Http\Resources\Json\JsonResource;

class {Modulo}Resource extends JsonResource
{
    public function toArray($request): array
    {
        return [
            'id'          => $this->id,           // UUID — nunca exponer pkid
            'nombre'      => $this->nombre,
            'codigo'      => $this->codigo,
            'activo'      => (bool) $this->activo,
            // Clave pública corta ("tienda") vs. método real del Model
            // ("catalogo_tienda", nombre literal de la tabla relacionada) —
            // ver [[Model#Relaciones — nombre de método vs. clave pública del Resource]].
            'tienda'      => $this->whenLoaded('catalogo_tienda', fn() =>
                new catalogo_tiendaRelationResource($this->catalogo_tienda)
            ),
            // created_by/updated_by son relaciones belongsTo hacia la tabla de usuarios,
            // no el pkid crudo — se cargan igual que cualquier otra relación (ver
            // `const RELATIONS` en [[Service del Módulo]]) y se exponen con el MISMO
            // Resource mínimo para cualquier módulo, porque siempre apuntan a la misma
            // tabla de usuarios. En el frontend esto tipa como `IAuditUser`, no una
            // interfaz por módulo — ver [[Interfaz de Modulo#Campos de auditoría]].
            'created_by_id' => $this->whenLoaded('created_by', fn() =>
                new UsuarioRelationResource($this->created_by)
            ),
            'updated_by_id' => $this->whenLoaded('updated_by', fn() =>
                new UsuarioRelationResource($this->updated_by)
            ),
            'created_at'  => $this->created_at?->toDateTimeString(),
            'updated_at'  => $this->updated_at?->toDateTimeString(),
        ];
    }
}
```

### `{Modulo}RelationResource` — mínimo

Usado cuando OTRO módulo carga este como relación con `whenLoaded()`, o en dropdowns/selectores. Solo expone lo necesario para identificar el registro en el contexto del módulo padre.

```php
<?php

namespace App\Http\Resources\{Prefijo};

use Illuminate\Http\Resources\Json\JsonResource;

class {Modulo}RelationResource extends JsonResource
{
    public function toArray($request): array
    {
        return [
            'id'     => $this->id,
            'nombre' => $this->nombre,
            'codigo' => $this->codigo,
        ];
    }
}
```

### `{Modulo}TinyResource` — mínimo para `?tiny=true`

Usado por el propio `index` del módulo cuando el Controller recibe `?tiny=true` (ver [[Controller#Parámetro `tiny` — colección mínima]]). Máximo 3-4 campos: `id` + el campo que sirve de etiqueta (`nombre` o `descripcion`) + `activo` si el selector necesita filtrar/marcar inactivos. Este es el default razonable para el caso general (catálogos simples); si el frontend necesita otros campos puntuales para ese selector en particular (una fecha, una relación mínima), se agregan ahí mismo — sigue siendo "lo mínimo que ese selector necesita", no una copia del Resource completo con menos líneas.

```php
<?php

namespace App\Http\Resources\{Prefijo};

use Illuminate\Http\Resources\Json\JsonResource;

class {Modulo}TinyResource extends JsonResource
{
    public function toArray($request): array
    {
        return [
            'id'     => $this->id,
            'nombre' => $this->nombre,
            'activo' => (bool) $this->activo,
        ];
    }
}
```

### Cómo se usa en el Resource del módulo padre

```php
class {ModuloPadre}Resource extends JsonResource
{
    public function toArray($request): array
    {
        return [
            'id'      => $this->id,
            'tienda'  => $this->whenLoaded('catalogo_tienda', fn() => new TiendaRelationResource($this->catalogo_tienda)),
            'usuario' => $this->whenLoaded('siaw_usuarios', fn() => new UsuarioRelationResource($this->siaw_usuarios)),
        ];
    }
}
```

### Selección de campos — checkbox propio para `RelationResource`

En la herramienta generadora, el checkbox **"Relación"** del mapeo de columnas es independiente del checkbox **"Tiny"**: un módulo puede necesitar mostrar campos distintos cuando lo carga OTRO módulo por `whenLoaded()` (`RelationResource`) que cuando responde su propio `?tiny=true` (`TinyResource`). No asumir que ambos Resources van a tener siempre la misma forma solo porque los dos son "livianos".

### Regla para saber cuál usar

| Caso                                                                                                    | Resource a usar            |
| --------------------------------------------------------------------------------------------------------- | --------------------------- |
| Respuesta directa de un endpoint del módulo (`index` sin `tiny`, `show`, `store`, `update`, `destroy`)     | `{Modulo}Resource`         |
| Relación cargada desde otro módulo (`whenLoaded`)                                                         | `{Modulo}RelationResource` |
| `index` con `?tiny=true` (dropdown/selector propio del módulo)                                            | `{Modulo}TinyResource`     |

**Regla importante:** Nunca exponer `pkid` en ningún Resource — completo, de relación o tiny. El frontend solo debe ver `id` (UUID).


---

## Cuándo NO usar Resource

Para respuestas internas entre servicios o cuando la data ya viene transformada y no se expone al frontend directamente, se puede pasar el modelo o array directo:

```php
return $this->responseSuccess('Proceso completado', ['total' => $total]);
```
