# Documentación Swagger (OpenAPI)

Relacionado: [[Controller]] | [[ApiResponse]] | [[Estandar Desarrollo Backend]] | [[Requests y Traits]]
Producción: [[Seguridad]] — la UI/JSON de Swagger **debe** estar apagada en producción, ver sección final.

---


## Stack

- `darkaonline/l5-swagger` (auto-descubierto por Laravel, no hace falta registrar el provider a mano) — sirve la UI en `/api/documentation` y el JSON crudo en `/docs`.
- `zircote/swagger-php` (dependencia de l5-swagger) — parsea anotaciones `@OA\...` en comentarios PHPDoc de todo `app/`.
- Generación: `php artisan l5-swagger:generate` (regenera `storage/api-docs/api-docs.json` a partir de las anotaciones). No hay watcher — hay que correrlo a mano tras cambiar anotaciones, o activar `L5_SWAGGER_GENERATE_ALWAYS=true` en local para que se regenere en cada request.

---

## Anatomía de las anotaciones

### 1. Global — en `App\Http\Controllers\Controller` (la clase base)

```php
/**
 * @OA\Info(title="{NombreProyecto} API", version="1.0.0", description="...")
 * @OA\Server(url=L5_SWAGGER_CONST_HOST, description="Servidor Principal")
 * @OA\SecurityScheme(
 *     securityScheme="bearerAuth",
 *     type="http",
 *     scheme="bearer",
 *     description="Token de sesión retornado por /api/auth/login (campo data.token)."
 * )
 */
abstract class Controller {}
```

`L5_SWAGGER_CONST_HOST` es una constante que l5-swagger define en tiempo de generación a partir de `env('L5_SWAGGER_CONST_HOST')` (ver `config/l5-swagger.php` → `constants`) — sin esa env var, cae al placeholder `http://my-default-host.com`. Definirla en `.env`.

### 2. Por controller — tag + un docblock completo por método

```php
/**
 * @OA\Tag(name="{Modulo}")
 */
class {prefijo}_{modulo}Controller extends Controller
{
    /**
     * @OA\Get(
     *      path="/api/{prefijo}_{modulo}",
     *      tags={"{Modulo}"},
     *      summary="Listar {modulo}",
     *      security={{"bearerAuth":{}}},
     *      @OA\Parameter(name="paginate", in="query", @OA\Schema(type="boolean")),
     *      @OA\Response(
     *          response=200,
     *          description="Listado de {modulo}",
     *          @OA\JsonContent(
     *              @OA\Property(property="status", type="integer", example=200),
     *              @OA\Property(property="message", type="string", example="{Modulo} obtenidos correctamente"),
     *              @OA\Property(property="data", type="array", @OA\Items(ref="#/components/schemas/{Modulo}Schema"))
     *          )
     *      )
     * )
     */
    public function index(Request $request) { ... }
}
```

**Regla dura: la respuesta documentada siempre es el envelope real** que produce [[ApiResponse]] (`{status, message, data}`) — nunca una `description` suelta sin `JsonContent`. Documentar solo la `description` es lo que dejaba a `gsp-back` con Swagger UI mostrando rutas sin poder probarlas de verdad (\"Try it out\" sin saber qué esperar de vuelta).

---

## Schemas reutilizables — uno por Resource

En vez de repetir la lista de campos en cada `index`/`show`/`store`/`update` del mismo módulo, el schema se declara **una sola vez** como `@OA\Schema` en el docblock de la clase `{Modulo}Resource` (ver [[ApiResponse#Resource triple: completo, relación y tiny]]), y se referencia con `$ref` desde los controllers.

```php
// app/Http/Resources/{Prefijo}/{Modulo}Resource.php
/**
 * @OA\Schema(
 *     schema="{Modulo}Schema",
 *     @OA\Property(property="id", type="string", format="uuid"),
 *     @OA\Property(property="nombre", type="string"),
 *     @OA\Property(property="activo", type="boolean"),
 *     @OA\Property(property="relacion", ref="#/components/schemas/{ModuloRelacionado}RelationSchema", nullable=true),
 *     @OA\Property(property="created_at", type="string", format="date-time", nullable=true),
 *     @OA\Property(property="updated_at", type="string", format="date-time", nullable=true)
 * )
 */
class {Modulo}Resource extends JsonResource { ... }
```

El `{Modulo}RelationResource` (el mínimo, para `whenLoaded` desde OTRO módulo) y el `{Modulo}TinyResource` (el mínimo para `?tiny=true` del propio módulo — ver [[ApiResponse#Resource triple: completo, relación y tiny]]) también llevan cada uno su propio `@OA\Schema(schema="{Modulo}RelationSchema" / "{Modulo}TinySchema", ...)` con solo los campos que exponen. El schema del Resource completo referencia el schema de relación con `ref`, nunca redefine sus campos.

**Por qué en el Resource y no en el Controller:** el Resource es la única fuente de verdad de qué campos se exponen — si el schema viviera en el controller, un cambio en `toArray()` no forzaría a tocar la documentación y quedarían desincronizados en silencio.

En el controller, el `data` de cada respuesta referencia el schema:

```php
// Un solo registro (show/store/update/destroy)
@OA\Property(property="data", ref="#/components/schemas/{Modulo}Schema")

// Colección (index)
@OA\Property(property="data", type="array", @OA\Items(ref="#/components/schemas/{Modulo}Schema"))
```

---

## RequestBody — Store vs Update

Refleja exactamente las reglas de [[Requests y Traits]]: `StoreRequest` marca todo `required`, `UpdateRequest` es todo opcional (`sometimes` en las rules → sin `required` a nivel de schema en el OA\JsonContent).

```php
// Store
@OA\RequestBody(
    required=true,
    @OA\JsonContent(
        required={"nombre","tienda_id"},
        @OA\Property(property="nombre", type="string", maxLength=100),
        @OA\Property(property="tienda_id", type="string", format="uuid")
    )
)

// Update — mismos properties, sin el array "required"
@OA\RequestBody(
    @OA\JsonContent(
        @OA\Property(property="nombre", type="string", maxLength=100),
        @OA\Property(property="tienda_id", type="string", format="uuid")
    )
)
```

Acciones restringidas a `permiso:isSuperUser,isAdmin` (ver [[Middleware de Seguridad]]) llevan `description="Solo superuser/admin."` en el docblock — así queda visible en la UI sin tener que ir a leer la ruta.

---

## Apagar Swagger en producción

**No negociable** — la UI y el JSON crudo exponen la forma completa de la API (rutas, params, hasta ejemplos de payloads). L5-swagger, por defecto, registra esas rutas (`/api/documentation`, `/docs`, `/docs/asset/{asset}`) sin ningún middleware — quedan públicas si no se hace nada.

### 1. Publicar el config (una vez por proyecto)

```bash
php artisan vendor:publish --provider="L5Swagger\L5SwaggerServiceProvider"
```

### 2. Middleware que corta con 404

```php
// app/Http/Middleware/EnsureSwaggerEnabled.php
class EnsureSwaggerEnabled
{
    public function handle(Request $request, Closure $next): Response
    {
        if (!config('l5-swagger.documentations.default.enabled')) {
            abort(404); // 404, no 403 — no confirma que la ruta existe
        }
        return $next($request);
    }
}
```

Alias en `bootstrap/app.php`:

```php
$middleware->alias([
    'swagger.enabled' => \App\Http\Middleware\EnsureSwaggerEnabled::class,
]);
```

### 3. `config/l5-swagger.php` — flag + aplicar el middleware a TODAS las rutas del paquete

```php
'documentations' => [
    'default' => [
        'enabled' => env('L5_SWAGGER_ENABLED', !app()->environment('production')),
        // ...
    ],
],
'defaults' => [
    'routes' => [
        'group_options' => [
            'middleware' => ['swagger.enabled'],   // cubre api + docs + asset + oauth2_callback de una sola vez
        ],
    ],
],
```

`group_options.middleware` envuelve las 4 rutas que registra l5-swagger (`api`, `docs`, `asset`, `oauth2_callback`) en un único `Route::group`, así que un solo middleware las cubre todas — no hace falta repetirlo por ruta.

### 4. Default seguro sin tocar nada

Con `env('L5_SWAGGER_ENABLED', !app()->environment('production'))`, el comportamiento por defecto es: **encendido en local/staging, apagado automáticamente si `APP_ENV=production`**, sin que nadie tenga que acordarse de setear una env var al desplegar. Si alguna vez hace falta exponerlo en producción (ej. debugging puntual con un equipo externo), se fuerza explícitamente con `L5_SWAGGER_ENABLED=true` — nunca al revés (que el default sea "encendido" y dependa de que alguien lo apague a mano).

---

## Checklist para un proyecto nuevo

- [ ] `composer require darkaonline/l5-swagger`
- [ ] `@OA\Info` / `@OA\Server` / `@OA\SecurityScheme` en `Controller.php`
- [ ] `L5_SWAGGER_CONST_HOST` en `.env` (si no, la UI muestra un host placeholder)
- [ ] Un `@OA\Schema` por cada `{Modulo}Resource`, `{Modulo}RelationResource` y `{Modulo}TinyResource`
- [ ] Un docblock completo (envelope + `$ref`) por cada método de cada controller — nunca solo `description`
- [ ] `EnsureSwaggerEnabled` + `config/l5-swagger.php` con `enabled` y `group_options.middleware` desde el día 1, no como parche posterior
- [ ] `php artisan l5-swagger:generate` corrido al menos una vez (o `L5_SWAGGER_GENERATE_ALWAYS=true` en local)
