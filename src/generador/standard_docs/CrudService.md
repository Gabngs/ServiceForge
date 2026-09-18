# CrudService

Relacionado: [[Estandar Desarrollo Backend]] | [[Service del Módulo]] | [[Model]] | [[Auditoría]] | [[useFilters]] | [[Mapeo UUID PKID]] | [[Seguridad]]

---

Clase base inyectada en todos los [[Service del Módulo|services del módulo]]. Centraliza las operaciones CRUD estándar con [[Auditoría]] opcional.

**No se extiende** — se inyecta como dependencia en el constructor del service.

---

## Firmas completas de los métodos

```php
// Crea un registro. Retorna el modelo creado.
// $proceso = null  → sin auditoría
// $proceso = 'nombre_proceso'  → registra en tabla de auditoría
public function create(string $modelClass, array $data, ?string $proceso = null): Model

// Actualiza un modelo. Retorna el modelo actualizado y refrescado.
// Internamente guarda el estado anterior en $input para la auditoría.
public function update(Model $model, array $data, ?string $proceso = null): Model

// Soft-delete. Asigna deleted_by_id antes de eliminar. Retorna snapshot del modelo.
public function delete(Model $model, ?string $proceso = null): Model

// Revierte un soft-delete. Asigna updated_by_id, llama a $model->restore()
// (Eloquent pone deleted_at en null) y retorna el modelo ya restaurado.
public function restore(Model $model, ?string $proceso = null): Model

// Inserta múltiples filas en lotes. Retorna el total de filas insertadas.
// No dispara eventos Eloquent (created, saving, etc.) — usa DB::table directamente.
public function bulkInsert(string $modelClass, array $rows, ?string $proceso = null, int $chunkSize = 500): int

// findOrFail genérico. Lanza ModelNotFoundException si no encuentra el registro.
public function find(string $modelClass, int|string $id): Model

// useFilters() + paginate o get. Solo para casos sin lógica extra.
public function getAll(string $modelClass, bool $paginate = true): mixed

// Convierte campos UUID → PKID en una sola fila. Modifica $data por referencia.
public function mapUuidsToPkids(array &$data, array $mapping): void

// Convierte campos UUID → PKID en múltiples filas. 1 query por modelo.
public function mapUuidsToPkidsBulk(array &$rows, array $mapping): void
```

---

## Token::user() — qué es

`Token::user()` es una helper class del proyecto que extrae el usuario autenticado del token de la request.

- Si hay usuario autenticado → retorna el objeto usuario con su `pkid`
- Si no hay usuario (proceso automático, job, comando) → retorna `null`

El CrudService lo usa para asignar automáticamente `created_by_id`, `updated_by_id`, `deleted_by_id` y para determinar el `origen` en la auditoría.

```php
// Internamente en CrudService — no hay que llamarlo manualmente:
$token = Token::user() ?? null;
if (isset($token)) {
    $data['created_by_id'] = $token->pkid;
    $data['updated_by_id'] = $token->pkid;
}
```

---

## Ejemplo — create

```php
// El Service prepara $data antes de llamar a create (sin generar el id — eso lo hace create() internamente):
public function store(array $data): {prefijo}_{modulo}
{
    $this->crud->mapUuidsToPkids($data, $this->uuidMapping);

    // create() agrega automáticamente id (UUID), created_by_id y updated_by_id
    return $this->crud->create(
        {prefijo}_{modulo}::class,
        $data,
        'crear_{modulo}',   // nombre en tabla de auditoría
    );
}
```

**Por qué el `id` lo genera `create()` y no el Service:** si cada Service tuviera que hacer `$data['id'] = Str::uuid()->toString();`, esa línea se repetiría en todos los módulos. Al generarlo dentro de `CrudService::create()` queda centralizado una sola vez.

---

## Ejemplo — update

```php
public function update({prefijo}_{modulo} $model, array $data): {prefijo}_{modulo}
{
    $this->crud->mapUuidsToPkids($data, $this->uuidMapping);

    // update() captura el estado anterior del modelo automáticamente,
    // y llama a $model->refresh() al terminar — el Service siempre devuelve
    // el modelo ya actualizado, nunca el snapshot previo a la escritura.
    return $this->crud->update($model, $data, 'actualizar_{modulo}');
}
```

---

## No auditar updates sin cambios reales — comparación estricta input vs output

`update()` captura `$input` (snapshot del modelo ANTES) y `$output` (snapshot DESPUÉS) para la fila de [[Auditoría]]. Antes de escribir esa fila, `CrudService::update()` compara ambos snapshots con `===` (estrictamente igual: mismas claves, mismos valores, mismo tipo) — si son idénticos, no hubo cambio real (el frontend reenvió el mismo formulario sin que el usuario tocara nada) y **no se escribe la fila de auditoría**.

```php
public function update(Model $model, array $data, ?string $proceso = null): Model
{
    return DB::transaction(function () use ($model, $data, $proceso) {
        $input = $model->toArray(); // snapshot ANTES

        $model->update($data);
        $output = $model->refresh()->toArray(); // snapshot DESPUÉS

        // Comparación estricta — si nada cambió, no saturar la tabla de auditoría
        // con filas idénticas input/output que no aportan nada al historial.
        if ($proceso && $input !== $output) {
            $this->audit(proceso: $proceso, tipo: {Prefijo}_procesosaudit::TIPO_ACTUALIZACION, model: $model, input: $input, output: $output);
        }

        return $model;
    });
}
```

**Por qué estricta (`!==`), no floja (`!=`):** una comparación floja trata `"1"` y `1`, o `null` y `""`, como iguales — dos estados que en la práctica sí son distintos y valdría la pena auditar. `===` entre dos arrays de la misma forma compara clave por clave, con el tipo incluido: solo se salta la auditoría cuando el registro es matemáticamente idéntico antes y después, nunca por una coincidencia de tipos sueltos.

**Qué NO aplica este criterio:** solo `update()`. `create()` siempre pasa de "no existía" a "existe" (`input=null`), `delete()` siempre pasa de "vivo" a "eliminado", `restore()` siempre revierte un `deleted_at` que antes no era `null` — las tres son transiciones de estado por definición, nunca hay un "no cambió nada" que evaluar.

---

## Ejemplo — delete

```php
public function destroy({prefijo}_{modulo} $model): {prefijo}_{modulo}
{
    // delete() asigna deleted_by_id, luego hace soft-delete
    // retorna un snapshot (clone) del modelo antes de borrarlo
    return $this->crud->delete($model, 'eliminar_{modulo}');
}
```

---

## Ejemplo — restore

```php
public function restore({prefijo}_{modulo} $model): {prefijo}_{modulo}
{
    // restore() asigna updated_by_id, revierte el soft-delete y registra
    // TIPO_RESTAURACION en la auditoría — el modelo hay que resolverlo
    // con withTrashed() en el controller/route model binding, porque un
    // registro soft-deleted no aparece en las queries normales.
    return $this->crud->restore($model, 'restaurar_{modulo}');
}
```

---

## Ejemplo — bulkInsert

```php
// $rows: array de arrays, cada uno con los campos de una fila
// bulkInsert agrega automáticamente: id (UUID), created_by_id, created_at, updated_at
$rows = [
    ['nombre' => 'Producto A', 'tienda_id' => 5, 'activo' => 1],
    ['nombre' => 'Producto B', 'tienda_id' => 5, 'activo' => 1],
];

// OJO: los PKIDs ya deben estar resueltos antes de llamar a bulkInsert
$this->crud->mapUuidsToPkidsBulk($rows, $this->uuidMapping);

$total = $this->crud->bulkInsert(
    {prefijo}_{modulo}::class,
    $rows,
    'carga_masiva_{modulo}',
    500,
);
// Retorna int: total de filas insertadas
```

**Importante:** `bulkInsert` usa `DB::table()->insert()` directamente.
Esto significa que **no** dispara eventos Eloquent (`creating`, `created`, `saving`, etc.) ni `Observers`.

---

## getAll — cuándo usar y cuándo no

```php
// ✅ Usar getAll cuando no hay lógica extra en el index
public function index(bool $paginate = false): mixed
{
    return $this->crud->getAll({prefijo}_{modulo}::class, $paginate);
}

// ❌ No usar getAll si necesitas encadenar condiciones o eager loading
// En ese caso, usar useFilters() directamente en el service:
public function index(bool $paginate = false): mixed
{
    $query = {prefijo}_{modulo}::useFilters()
        ->with(['tienda', 'cargo'])
        ->where('activo', 1);

    return $paginate ? $query->dynamicPaginate() : $query->get();
}
```

---

## Campos auto-asignados por CrudService

| Operación    | Campos asignados automáticamente                                     |
| ------------ | -------------------------------------------------------------------- |
| `create`     | `id` (UUID), `created_by_id`, `updated_by_id`                        |
| `update`     | `updated_by_id`                                                      |
| `delete`     | `deleted_by_id`                                                      |
| `restore`    | `updated_by_id` (Eloquent pone `deleted_at` en `null`)                |
| `bulkInsert` | `id` (UUID con guiones), `created_by_id`, `created_at`, `updated_at` |

Estos campos deben existir en la tabla — ver [[Model]] para la estructura estándar. No hay que incluirlos en `$data` al llamar al service.
Nota: Todo registro de ID en la db debe realizarse con guiones,

---

## Transacciones — atomicidad entre dato y auditoría

**Todo método que escribe más de una fila debe envolverse en `DB::transaction()`.** `create()`, `update()` y `delete()` hacen dos escrituras separadas — el registro de negocio y, si se pasó `$proceso`, su fila en la tabla de auditoría ([[Auditoría]]) — como dos statements independientes. Sin transacción, si el proceso muere entre medio (corte de red, OOM kill, timeout del pod), el cambio de negocio queda persistido **sin su registro de auditoría**, de forma silenciosa — nadie se entera hasta que hace falta reconstruir qué pasó y el rastro no está.

```php
public function create(string $modelClass, array $data, ?string $proceso = null): Model
{
    return DB::transaction(function () use ($modelClass, $data, $proceso) {
        $data['id'] ??= Str::uuid()->toString();
        // ... asignar created_by_id/updated_by_id vía Token::user() ...
        $model = $modelClass::create($data);

        if ($proceso) {
            $this->audit(proceso: $proceso, tipo: ..., model: $model, input: null, output: $model->toArray());
        }

        return $model;
    });
}
```

Mismo criterio para `bulkInsert()`: cada chunk de `DB::table()->insert()` va dentro de la transacción junto con la fila de auditoría del resumen (`total_insertados`) — si falla el chunk 3 de 5, no deben quedar 1000 filas insertadas sin ninguna señal de que la operación fue parcial.

**Por qué no rompe el best-effort de la auditoría de seguridad:** esto es la [[Auditoría]] de datos CRUD (tabla `{prefijo}_procesosaudit`), no la [[Auditoría de Seguridad]] de eventos de login — son conceptos distintos con reglas distintas. La de seguridad es intencionalmente best-effort (un fallo al auditar un intento de login nunca debe bloquear el login real). La de CRUD es lo opuesto: si la auditoría del dato falla, es preferible que **toda la operación falle y se reintente** antes que dejar un cambio de negocio sin su rastro — por eso va en la misma transacción, no en un `try/catch` aparte.