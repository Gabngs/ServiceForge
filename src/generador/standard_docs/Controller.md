# Controller — Orquestador

Relacionado: [[Estandar Desarrollo Backend]] | [[Service del Módulo]] | [[ApiResponse]] | [[Requests y Traits]] | [[Documentación Swagger (OpenAPI)]] | [[Conexiones, Migraciones y Rutas]]

---

El controller **no contiene lógica de negocio ni flujo de datos**. Solo recibe el request, delega al [[Service del Módulo]] y retorna la respuesta con [[ApiResponse]]. Esto aplica también a `index` y `show`: el controller nunca arma queries (`useFilters()`, `->with()`, `->load()`) directamente — eso vive en el [[Service del Módulo]] (ver `index()` y `show()` en esa página), incluida la decisión de paginar vía `dynamicPaginate()`.

El Service usa los mismos 5 nombres de método que el Controller — `index`, `show`, `store`, `update`, `destroy` — nunca variantes en español (`crear`/`actualizar`/`eliminar`/`mostrar`). Ver [[Service del Módulo#Nombres de métodos — SIEMPRE en inglés, sin excepción]].

Los FormRequests de [[Requests y Traits]] hacen la validación antes de que el método siquiera ejecute.

---

## Ejemplo completo

```php
<?php

namespace App\Http\Controllers\Api\{Prefijo};

use App\Http\Controllers\Controller;
use App\Http\Requests\{Prefijo}\{Modulo}\Store{Modulo}Request;
use App\Http\Requests\{Prefijo}\{Modulo}\Update{Modulo}Request;
use App\Http\Resources\{Prefijo}\{Modulo}Resource;
use App\Http\Resources\{Prefijo}\{Modulo}TinyResource;
use App\Models\db{prefijo}\{prefijo}_{modulo};
use App\Services\{Modulo}Service;
use Essa\APIToolKit\Api\ApiResponse;
use Illuminate\Http\Request;

class {prefijo}_{modulo}Controller extends Controller
{
    use ApiResponse;

    public function __construct(protected {Modulo}Service $service) {}

    // ─── INDEX ────────────────────────────────────────────────────────────────
    // GET /api/{prefijo}_{modulo}?paginate=true&page=1&per_page=20&tiny=true&tienda_id=uuid
    public function index(Request $request)
    {
        // $request->boolean('paginate') / ->boolean('tiny') retornan true solo si
        // llega "true"/"1"/"on"/"yes". Si el param no llega, o llega "false"/"0",
        // retornan false — nunca null. Sin tiny=true en la URL, se sobreentiende
        // tiny=false y se usa el Resource completo.
        $paginate = $request->boolean('paginate');

        $data = $this->service->index($paginate); // Collection o LengthAwarePaginator

        // El Resource a usar (completo o tiny) es una decisión de presentación —
        // vive acá, no en el Service. El Service siempre devuelve los mismos modelos
        // sin importar qué Resource los va a envolver. Ver [[ApiResponse#Resource
        // triple: completo, relación y tiny]] — tiny=true usa {Modulo}TinyResource,
        // pensado para selectores/dropdowns del frontend, no {Modulo}RelationResource
        // (ese es para whenLoaded() desde OTRO módulo, no para este endpoint).
        $resource = $request->boolean('tiny')
            ? {Modulo}TinyResource::class
            : {Modulo}Resource::class;

        if (! $paginate) {
            return $this->responseSuccess(
                'Registros obtenidos correctamente',
                $resource::collection($data)
            );
        }

        // $data es LengthAwarePaginator: no pasarlo tal cual a responseSuccess()
        // (produce data.data). Se transforman solo los items (array plano) con el
        // Resource elegido arriba, y se agrega 'meta' al mismo nivel que 'data' —
        // nunca anidada dentro de 'data'. Ver receta completa en
        // [[ApiResponse#Paginación sin duplicar `data`]].
        $response = $this->responseSuccess(
            'Registros obtenidos correctamente',
            $resource::collection($data->items())
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

    // ─── SHOW ─────────────────────────────────────────────────────────────────
    // GET /api/{prefijo}_{modulo}/{id}
    // Laravel resuelve el modelo por su campo "id" (UUID) via Route Model Binding
    public function show({prefijo}_{modulo} ${prefijo}_{modulo})
    {
        // El Service carga las relaciones (self::RELATIONS) — el Controller no llama ->load()
        $model = $this->service->show(${prefijo}_{modulo});

        return $this->responseSuccess(
            'Registro obtenido correctamente',
            new {Modulo}Resource($model)
        );
    }

    // ─── STORE ────────────────────────────────────────────────────────────────
    // POST /api/{prefijo}_{modulo}
    // Store{Modulo}Request valida antes de entrar — si falla, retorna 422 automáticamente
    public function store(Store{Modulo}Request $request)
    {
        // $request->validated() solo retorna los campos declarados en rules()
        // Nunca pasar $request->all() — incluiría campos no validados
        $model = $this->service->store($request->validated());

        return $this->responseSuccess(
            'Registro creado correctamente',
            new {Modulo}Resource($model)
        );
    }

    // ─── UPDATE ───────────────────────────────────────────────────────────────
    // PUT /api/{prefijo}_{modulo}/{id}
    // Laravel inyecta el modelo resuelto por UUID (Route Model Binding)
    public function update(Update{Modulo}Request $request, {prefijo}_{modulo} ${prefijo}_{modulo})
    {
        $model = $this->service->update(${prefijo}_{modulo}, $request->validated());

        return $this->responseSuccess(
            'Registro actualizado correctamente',
            new {Modulo}Resource($model)
        );
    }

    // ─── DESTROY ──────────────────────────────────────────────────────────────
    // DELETE /api/{prefijo}_{modulo}/{id}
    public function destroy({prefijo}_{modulo} ${prefijo}_{modulo})
    {
        $deleted = $this->service->destroy(${prefijo}_{modulo});

        return $this->responseSuccess(
            'Registro eliminado correctamente',
            new {Modulo}Resource($deleted)
        );
    }
}
```

---

## Registro de la ruta

```php
// routes/modules/{modulo}.php
Route::apiResource('{prefijo}_{modulo}', {prefijo}_{modulo}Controller::class);
```

Una sola línea, siempre — `apiResource` genera las 5 rutas del contrato (`index`, `store`, `show`, `update`, `destroy`), ya protegidas por `auth:sanctum` (aplicado centralizado, no por archivo). Detalle completo — auto-carga vía `RouteServiceProvider`, `->parameters()`, la regla de orden para endpoints extra fuera del CRUD (evita el bug de "Laravel lee un segmento del path como si fuera el `{id}`"), y cuándo una ruta sí necesita `permiso:` explícito — en [[Conexiones, Migraciones y Rutas#4. Rutas — `RouteServiceProvider` y el CRUD de una línea]].

---

## Parámetro `tiny` — colección mínima

`?tiny=true` en `index` le dice al Controller que transforme la colección con `{Modulo}TinyResource` (ver [[ApiResponse#Resource triple: completo, relación y tiny]]) en vez de `{Modulo}Resource`. **No** es `{Modulo}RelationResource` — ese Resource es para cuando OTRO módulo carga este como relación vía `whenLoaded()`, un caso distinto aunque ambos sean "livianos". Si no llega `tiny` en la URL, o llega `false`, se sobreentiende `tiny=0` y se usa el Resource completo — no hace falta mandar el param explícitamente para el caso normal. No cambia nada en el Service — el query, los filtros y la paginación son exactamente los mismos, solo cambia con qué Resource se envuelve el resultado antes de responder.

Pensado para dropdowns/selects/autocompletados que hoy piden la colección completa y descartan la mayoría de los campos: `GET /api/{prefijo}_{modulo}?tiny=true` (opcionalmente combinado con `paginate=true&per_page=50` si la lista es larga). El frontend tipa esa respuesta como `I{Modulo}Tiny[]`, no como `I{Modulo}[]` — ver [[Interfaz de Modulo#`I{Modelo}Tiny` — la interfaz que faltaba]].

```php
$resource = $request->boolean('tiny') ? {Modulo}TinyResource::class : {Modulo}Resource::class;

return $this->responseSuccess(
    'Registros obtenidos correctamente',
    $resource::collection($data)
);
```

Versión simplificada sin paginación, para mostrar solo el efecto de `tiny`. El `index()` real (ver "Ejemplo completo" arriba) combina esto con el manejo de `meta` cuando `paginate=true`.

---

## Módulos sin paginación

El "Ejemplo completo" de arriba asume que `index` siempre acepta `?paginate=true` — es el default razonable. Pero no todos los módulos lo necesitan (catálogos chicos que nunca van a superar una página, tablas de solo lectura para un dropdown, etc.). En la herramienta generadora esto es un checkbox propio ("El Controller admite `?paginate=true`") — si está desmarcado, el `index()` generado no acepta ese query param ni construye la clave `meta`, y llama directo `$this->service->index(false)`:

```php
public function index(Request $request)
{
    $data = $this->service->index(false);

    $resource = $request->boolean('tiny')
        ? {Modulo}TinyResource::class
        : {Modulo}Resource::class;

    return $this->responseSuccess(
        'Registros obtenidos correctamente',
        $resource::collection($data)
    );
}
```

`?tiny=true` sigue funcionando igual — es independiente de la paginación. Si más adelante el módulo termina necesitando paginar, se vuelve a generar (o se edita a mano) siguiendo el "Ejemplo completo".

---

## Relaciones reutilizables — `const RELATIONS`

**Esta constante vive en el [[Service del Módulo]], no en el Controller.** Cuando el módulo carga las mismas relaciones en varios métodos (`index`, `show`, `store`, `update`, `destroy`), el service declara `const RELATIONS` una sola vez y la reutiliza en sus `->with()` / `->load()` internos — evita que una relación se actualice en un método del service y se olvide en otro. El Controller nunca ve ni referencia `RELATIONS`: solo llama `$this->service->show($model)`, `$this->service->index($paginate)`, etc. Ver el ejemplo completo en [[Service del Módulo]].

---

## Route Model Binding

Laravel resuelve `{prefijo}_{modulo} $model` buscando por el campo `id` (UUID) de la URL.

Para que esto funcione, el [[Model|modelo]] debe tener la `RouteKeyName` correcta:

```php
// En el modelo, si el campo público es "id" (UUID), no hace falta nada extra.
// Solo si el campo de ruta fuera diferente se declara:
public function getRouteKeyName(): string
{
    return 'id'; // UUID — Laravel busca por este campo
}
```
	Nota : Puede no ser necesario declarado el id como primary en el model y asignado su autoincrement:false y type: string

---

## Errores comunes a evitar

```php
// ❌ MAL — lógica de negocio en el controller
public function store(Request $request)
{
    $data = $request->all();
    $data['id'] = Str::uuid();
    $data['tienda_id'] = catalogo_tienda::where('id', $data['tienda_id'])->value('pkid');
    {prefijo}_{modulo}::create($data);
}

// ✅ BIEN — el controller solo orquesta
public function store(Store{Modulo}Request $request)
{
    $model = $this->service->store($request->validated());
    return $this->responseSuccess('Creado', new {Modulo}Resource($model));
}

// ❌ MAL — armar el query o cargar relaciones en el controller (index/show)
public function index()
{
    $data = {prefijo}_{modulo}::useFilters()->with(['relacionUno'])->get();
    return $this->responseSuccess('OK', {Modulo}Resource::collection($data));
}

public function show({prefijo}_{modulo} ${prefijo}_{modulo})
{
    ${prefijo}_{modulo}->load(['relacionUno']); // flujo de datos — no es orquestación
    return $this->responseSuccess('OK', new {Modulo}Resource(${prefijo}_{modulo}));
}

// ✅ BIEN — index/show delegan al Service, igual que store/update/destroy
public function index(Request $request)
{
    $data = $this->service->index($request->boolean('paginate'));
    return $this->responseSuccess('OK', {Modulo}Resource::collection($data));
}

public function show({prefijo}_{modulo} ${prefijo}_{modulo})
{
    $model = $this->service->show(${prefijo}_{modulo});
    return $this->responseSuccess('OK', new {Modulo}Resource($model));
}
```
