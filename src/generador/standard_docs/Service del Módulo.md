# Service del Módulo

Relacionado: [[Estandar Desarrollo Backend]] | [[Controller]] | [[CrudService]] | [[Model]] | [[Mapeo UUID PKID]] | [[useFilters]]

---

El service contiene toda la lógica de negocio del módulo. Recibe datos ya validados del [[Controller]], resuelve IDs foráneos con [[Mapeo UUID PKID]] y delega las operaciones CRUD al [[CrudService]].

**El service maneja todo el flujo de datos, incluyendo `index`/`getAll` y `show`.** El Controller nunca arma queries (`useFilters()`, `->with()`, `->load()`) ni decide relaciones — solo orquesta: recibe el request/modelo, llama al método del service que corresponda y responde con [[ApiResponse]]. Esto incluye la paginación: el service decide `dynamicPaginate()` vs `get()` según el flag que le pasa el Controller (ver [[useFilters]]) — así el front, con solo agregar `?paginate=true`, obtiene datos paginados sin que el Controller tenga que cambiar.

Extiende siempre `AbstractModuleService` — la clase base abstracta que fuerza en tiempo de boot que se implementen los métodos correctos.

---

## Nombres de métodos — SIEMPRE en inglés, sin excepción

Los métodos del contrato usan los mismos nombres que Laravel espera en un resource controller (`Route::apiResource`, `php artisan make:controller --api`): **`index`, `show`, `store`, `update`, `destroy`**. Esto es intencional, no cosmético:

- El Controller ya usa estos nombres por convención de Laravel (`index`, `show`, `store`, `update`, `destroy` son los que genera `apiResource`) — si el Service usara nombres en español (`crear`, `actualizar`, `eliminar`, `mostrar`), quedarían dos vocabularios distintos para la misma operación en la misma request, lo cual genera confusión al leer el código.
- Nombrar `store()` en el Service igual que `store()` en el Controller facilita la trazabilidad: `Controller::store()` → `Service::store()` es una lectura directa, sin tener que traducir mentalmente `store → crear`.
- **No** se documentan variantes en español (`crear`/`actualizar`/`eliminar`/`mostrar`) en ningún ejemplo de esta página — si un proyecto existente las usa, es deuda técnica a corregir, no el estándar a seguir.

---

## AbstractModuleService — clase base

```php
<?php

namespace App\Services;

use Illuminate\Database\Eloquent\Model;

abstract class AbstractModuleService
{
    // Cada service DEBE declarar su mapping (puede ser vacío)
    protected array $uuidMapping = [];

    abstract public function index(bool $paginate = false): mixed;
    abstract public function show(Model $model): Model;
    abstract public function store(array $data): Model;
    abstract public function update(Model $model, array $data): Model;
    abstract public function destroy(Model $model): Model;
}
```

### Regla obligatoria — el parámetro `Model` NUNCA se angosta en el service concreto

`show`, `update` y `destroy` reciben **siempre** `Model $model` (el tipo del padre), nunca el modelo concreto (`{prefijo}_{modulo} $model`). El tipo de **retorno** sí se angosta al modelo concreto — eso es covarianza, PHP lo permite. Angostar el **parámetro** viola la regla de sustitución de Liskov y PHP tira `Fatal error: Declaration of ... must be compatible with AbstractModuleService::show(Model $model): Model` en cuanto la clase se carga — no en cada request, apenas algo la referencia (autoload), así que puede quedar dormido y romper después en producción sin relación aparente con el cambio que lo disparó.

```php
// ❌ MAL — parámetro angostado a la clase concreta, PHP fatalea al cargar la clase
public function show({prefijo}_{modulo} $model): {prefijo}_{modulo}
{
    return $model->load(self::RELATIONS);
}

// ✅ BIEN — parámetro Model (igual que el padre), retorno angostado al modelo concreto
public function show(Model $model): {prefijo}_{modulo}
{
    return $model->load(self::RELATIONS);
}
```

No hace falta castear ni validar el tipo dentro del método: Route Model Binding en el Controller ya resuelve la instancia del modelo concreto antes de llamar al Service — en runtime siempre llega el tipo correcto, PHP solo exige que la firma declarada sea compatible con el contrato del padre.

### Por qué abstract y no interface

- `abstract` permite declarar `$uuidMapping = []` con valor por defecto → los services sin FKs no necesitan redeclararlo.
- Si fuera `interface`, cada service tendría que declarar el array aunque esté vacío.
- PHP lanza `Fatal error` en boot si no se implementan los métodos abstractos → detección inmediata, sin depender de que el desarrollador recuerde el contrato.

### Qué garantiza

| Garantía | Sin AbstractService | Con AbstractService |
|---|---|---|
| Método `store()` existe | Depende del dev | PHP lanza error si no está |
| Método nombrado correctamente | Depende del dev | Sí — firma exacta |
| `$uuidMapping` declarado | Depende del dev | Siempre presente |
| Retorno correcto (Model) | Solo TypeScript/PHPStan | PHP 8 + return types |

---

## `const RELATIONS` — el otro miembro fijo del Service, junto a `$uuidMapping`

Todo Service concreto declara **dos** miembros de clase fijos, siempre en el mismo lugar (justo debajo de la declaración de la clase): `const RELATIONS` y `protected array $uuidMapping`. `$uuidMapping` vive en `AbstractModuleService` con default `[]` (ver arriba) porque PHP permite dar valor por defecto a una propiedad heredable; `const RELATIONS` **no** puede vivir en la clase abstracta de la misma forma — una constante de clase no es polimórfica como una propiedad, así que declararla en el padre no obliga a nada al hijo. Aun así, es la misma convención: cada Service concreto la declara, aunque PHP no lo fuerce en tiempo de boot como sí hace con los métodos abstractos.

**De dónde salen las relaciones que van en `RELATIONS`:** el `Service` no inventa relaciones — solo lista, por nombre, métodos `BelongsTo`/`HasMany` que el [[Model]] ya declaró. `RELATIONS` es el punto único donde el Service decide *cuáles* de esas relaciones ya declaradas en el modelo se cargan en `index`/`show`/`store`/`update`/`destroy` (ver [[Controller#Relaciones reutilizables — const RELATIONS]] para el porqué de centralizarlo acá y no repetir `->with()`/`->load()` suelto en cada método).

**`created_by`/`updated_by`/`deleted_by` van en `RELATIONS` por defecto, en todo módulo.** Son las tres relaciones de auditoría — quién creó/modificó/eliminó el registro — y **requieren que exista un modelo de usuario** (`App\Models\User`, o el modelo de usuarios propio del proyecto, ej. `SiawUsuarios`) al que esos `belongsTo(..., '*_by_id', 'pkid')` puedan apuntar. Sin un modelo de usuario resoluble, esas tres relaciones no se pueden declarar en el Model y por lo tanto tampoco pueden entrar en `RELATIONS` — es un prerequisito del patrón, no un detalle opcional (ver [[Script Generador Backend#`created_by` / `updated_by` / `deleted_by` — belongsTo de auditoría]] para cómo el generador resuelve qué modelo de usuario usar).

```php
const RELATIONS = ['tienda', 'created_by', 'updated_by', 'deleted_by'];
```

---

## Ejemplo completo

```php
<?php

namespace App\Services;

use App\Models\db{prefijo}\{prefijo}_{modulo};
use App\Models\dbsiaw\catalogo_tienda;
use App\Models\dbsip\sip_personalcargos;
use Illuminate\Database\Eloquent\Model;

class {Modulo}Service extends AbstractModuleService
{
    public function __construct(protected CrudService $crud) {}

    /**
     * Relaciones eager-loaded en index/show, y en la respuesta de store/update/destroy.
     * Centralizada acá — el Controller nunca decide qué relaciones cargar (ver [[Controller]]).
     */
    const RELATIONS = ['relacionUno', 'relacionDos', 'created_by', 'updated_by', 'deleted_by'];

    /**
     * Mapeo de campos UUID → PKID.
     * Clave: nombre del campo en $data que llega del frontend (UUID)
     * Valor: clase del modelo donde se busca ese UUID para obtener su pkid
     */
    protected array $uuidMapping = [
        'tienda_id' => catalogo_tienda::class,
        'cargo_id'  => sip_personalcargos::class,
    ];

    // ─── INDEX / GETALL ───────────────────────────────────────────────────────
    public function index(bool $paginate = false): mixed
    {
        // useFilters() siempre se aplica independientemente de la paginación.
        // Lee automáticamente los query params del request entrante.
        $query = {prefijo}_{modulo}::useFilters()->with(self::RELATIONS);

        // Filtro de negocio: se aplica ANTES de paginar.
        // No es un filtro del usuario — es una regla interna del sistema.
        // Ejemplo: no exponer usuarios con privilegio superUser al listado normal
        // $query = $query->where('super_user', '!=', 1);

        // El Controller solo pasa el flag $paginate (desde $request->boolean('paginate')).
        // El front activa paginado agregando "?paginate=true" sin que el Controller cambie.
        return $paginate
            ? $query->dynamicPaginate()  // retorna LengthAwarePaginator
            : $query->get();             // retorna Collection
    }

    // ─── SHOW ─────────────────────────────────────────────────────────────────
    // Recibe la instancia ya resuelta por Route Model Binding en el Controller.
    // El Controller NUNCA llama ->load() directamente — eso es flujo de datos, vive acá.
    // Parámetro Model (igual que AbstractModuleService), retorno angostado al modelo
    // concreto — angostar el parámetro rompe la clase al cargarla, ver sección de arriba.
    public function show(Model $model): {prefijo}_{modulo}
    {
        return $model->load(self::RELATIONS);
    }

    // ─── STORE ────────────────────────────────────────────────────────────────
    public function store(array $data): {prefijo}_{modulo}
    {
        // 1. Convertir campos UUID del frontend a PKID antes de persistir
        // $data['tienda_id'] viene como UUID desde el front → se convierte a pkid
        $this->crud->mapUuidsToPkids($data, $this->uuidMapping);

        // 2. Persistir con auditoría
        // El id (UUID) lo genera CrudService::create() internamente — no se genera acá
        // El nombre del proceso ('crear_{modulo}') es el identificador en la tabla de auditoría
        // (el nombre del proceso auditado puede quedar en español — es un label interno,
        // no un método del contrato del Service)
        $model = $this->crud->create(
            {prefijo}_{modulo}::class,
            $data,
            'crear_{modulo}',
        );

        // Se cargan las relaciones acá para que el Resource de la respuesta
        // tenga los mismos datos que index/show — el Controller no vuelve a tocar el modelo.
        return $model->load(self::RELATIONS);
    }

    // ─── UPDATE ───────────────────────────────────────────────────────────────
    // Recibe la instancia del modelo ya resuelta por Route Model Binding en el Controller
    public function update(Model $model, array $data): {prefijo}_{modulo}
    {
        // Solo mapear si los campos FK vienen en el request de actualización
        // mapUuidsToPkids() saltea los campos que no están en $data
        $this->crud->mapUuidsToPkids($data, $this->uuidMapping);

        $model = $this->crud->update(
            $model,
            $data,
            'actualizar_{modulo}',
        );

        return $model->load(self::RELATIONS);
    }

    // ─── DESTROY ──────────────────────────────────────────────────────────────
    public function destroy(Model $model): {prefijo}_{modulo}
    {
        // Snapshot con relaciones cargadas ANTES del soft-delete,
        // para que el Resource de la respuesta pueda mostrarlas igual que en index/show.
        $model->load(self::RELATIONS);

        return $this->crud->delete(
            $model,
            'eliminar_{modulo}',
        );
    }
}
```

---

## Caso sin relaciones FK — uuidMapping vacío

Si el módulo no tiene campos que mapear, se declara el array vacío.
`mapUuidsToPkids` no hace nada si el mapping está vacío:

```php
protected array $uuidMapping = [];
```

---

## Caso con carga masiva (bulk)

```php
public function cargarMasivo(array $rows): int
{
    // Convertir UUIDs a PKIDs en todas las filas con una sola query por modelo
    $this->crud->mapUuidsToPkidsBulk($rows, $this->uuidMapping);

    return $this->crud->bulkInsert(
        {prefijo}_{modulo}::class,
        $rows,
        'carga_masiva_{modulo}',
        500, // lote de 500 registros por INSERT
    );
}
```

---

## Caso con filtro de negocio en index

`useFilters()` retorna un Builder, por lo que se puede encadenar cualquier condición Eloquent:

```php
public function index(bool $paginate = false): mixed
{
    $query = {prefijo}_{modulo}::useFilters()
        ->with(self::RELATIONS)
        ->where('super_user', '!=', 1)          // regla de negocio
        ->whereNull('fecha_baja');               // solo activos

    return $paginate ? $query->dynamicPaginate() : $query->get();
}
```

---

## Métodos adicionales fuera del contrato abstracto

Si un módulo necesita métodos adicionales (bulk, reportes, etc.), se agregan en el service concreto sin tocar la clase abstracta. Estos sí pueden nombrarse en español si describen una operación propia del negocio sin equivalente REST (`cargarMasivo`, `reporte`, `cerrarPeriodo`, etc.) — la regla de nombres en inglés aplica únicamente a los 5 métodos del contrato (`index`, `show`, `store`, `update`, `destroy`):

```php
class {Modulo}Service extends AbstractModuleService
{
    // métodos abstractos obligatorios...

    // métodos extras del módulo
    public function cargarMasivo(array $rows): int { ... }
    public function reporte(array $filtros): array { ... }
}
```

---

## Errores de negocio — el Service los lanza, el frontend solo los muestra

Toda regla de negocio que impide una operación (un dato que falta, un estado que no lo permite, un registro que no cumple una condición) se comunica con **una sola forma**: el Service lanza `ValidationException::withMessages()` con el mensaje ya redactado para el usuario. Laravel lo responde solo como **422** con `message` y `errors` por campo — la misma forma que un `FormRequest` fallido (ver [[ApiResponse#Respuesta de validación — 422 (automática)]]), sin tocar el Controller.

```php
use Illuminate\Validation\ValidationException;

public function getTienda(Model $model): Model
{
    if (! $model->tienda_id) {
        throw ValidationException::withMessages([
            // La clave es el campo que el usuario tendría que corregir o el más relacionado
            'personal_id' => ['El personal no tiene una tienda asignada.'],
        ]);
    }

    return $model->load('catalogo_tienda')->catalogo_tienda;
}
```

```json
{
    "message": "El personal no tiene una tienda asignada.",
    "errors": { "personal_id": ["El personal no tiene una tienda asignada."] }
}
```

**Por qué es la regla:**
- El Controller sigue siendo solo orquestación (ver [[Controller]]): no atrapa nada ni arma respuestas de error; el `throw` del Service llega al handler de Laravel.
- El **mensaje lo redacta el backend** y el frontend lo lee de forma dinámica con `HelperMessage` (ver [[Helper de Mensajes]]) para mostrarlo en un toast. Por eso cada error posible se mapea aquí, en el Service, y **no existe ningún catálogo de errores en el frontend**: es imposible enumerar todas las respuestas y no depende del CRUD básico sino de cada método con lógica propia.
- Los mensajes van completos y en lenguaje del usuario (`"La caja del 2026-09-01 ya está cerrada — no se pueden registrar movimientos con esa fecha."`), no códigos ni claves técnicas.

**Requisito en `bootstrap/app.php`:** la API es JSON pura, así que el proyecto debe forzar que toda excepción responda como JSON sin importar el header `Accept` (curl, Postman y Swagger mandan `*/*` y, sin esto, Laravel intenta redirigir a un `login` que no existe):

```php
->withExceptions(function (Exceptions $exceptions): void {
    $exceptions->shouldRenderJsonWhen(fn () => true);
})
```

**Otras excepciones, cada una con su respuesta automática:**

| Situación | Se lanza | Respuesta |
|---|---|---|
| Regla de negocio no cumplida / dato inválido | `ValidationException::withMessages([...])` | 422 + `errors` |
| Credenciales, sesión o bloqueo (solo flujo de auth) | `AuthenticationException('mensaje')` | 401 + `message` |
| Registro inexistente por route model binding o `findOrFail` | (Laravel, automática) | 404 |

`abort(404)` queda reservado para middleware (ej. Swagger deshabilitado en producción, ver [[Documentación Swagger (OpenAPI)]]), no para reglas de negocio de un Service.

---

## Errores comunes a evitar

```php
// ❌ MAL — pasar $request directamente al service
public function store(Request $request)
{
    $this->service->store($request->all()); // incluye campos no validados
}

// ✅ BIEN — siempre pasar $request->validated()
public function store(Store{Modulo}Request $request)
{
    $this->service->store($request->validated());
}

// ❌ MAL — generar UUID en el Controller o en el Service
public function store(Store{Modulo}Request $request)
{
    $data = $request->validated();
    $data['id'] = Str::uuid(); // esto lo genera CrudService::create() internamente, no hay que asignarlo a mano
    $this->service->store($data);
}

// ❌ MAL — resolver UUID en el Controller
$data['tienda_id'] = catalogo_tienda::where('id', $data['tienda_id'])->value('pkid');
// esto lo hace mapUuidsToPkids() en el Service

// ❌ MAL — armar el query o cargar relaciones en el Controller (index/show)
public function show({prefijo}_{modulo} ${prefijo}_{modulo})
{
    ${prefijo}_{modulo}->load(['relacionUno', 'relacionDos']); // flujo de datos — no es orquestación
    return $this->responseSuccess('OK', new {Modulo}Resource(${prefijo}_{modulo}));
}

// ✅ BIEN — el Controller delega la carga de relaciones al Service
public function show({prefijo}_{modulo} ${prefijo}_{modulo})
{
    $model = $this->service->show(${prefijo}_{modulo});
    return $this->responseSuccess('OK', new {Modulo}Resource($model));
}

// ❌ MAL — nombrar los métodos del contrato en español (crear/actualizar/eliminar/mostrar)
// genera dos vocabularios distintos entre Controller y Service para la misma operación
public function crear(array $data): Model { ... }

// ✅ BIEN — mismo nombre que usa el Controller (store, igual que Route::apiResource)
public function store(array $data): Model { ... }
```
