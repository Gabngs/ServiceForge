# Mapeo UUID → PKID

Relacionado: [[Estandar Desarrollo Backend]] | [[Service del Módulo]] | [[CrudService]] | [[Model]] | [[useFilters]]

---

El frontend trabaja con `id` (UUID público). El backend persiste con `pkid` (autoincremental privado).

El [[Service del Módulo]] resuelve esta conversión **antes** de llamar al [[CrudService]].

El mismo mapeo aplica **en sentido de lectura**: los filtros por FK (`?habitacion_id={uuid}`) también reciben el UUID y deben resolverlo a `pkid` antes de armar el `WHERE`. Eso NO lo cubre `$allowedFilters` — se implementa como método resolver en la clase Filters, ver [[useFilters#FKs que guardan `pkid` — el filtro `*_id` SIEMPRE necesita método resolver]].

---

## Por qué existe este patrón

- El frontend nunca debe conocer los PKIDs internos
- Las FKs en la base de datos usan `pkid` (int) por performance
- El UUID expuesto (`id`) es estable y seguro para la API pública

---

## Declaración del mapping en el Service

```php
// Clave: nombre del campo en $data tal como llega del frontend
// Valor: clase del modelo donde se busca ese UUID para obtener su pkid

use App\Models\dbsiaw\catalogo_tienda
use App\Models\dbsip\sip_personalcargos
use App\Models\dbsip\sip_periodoestandar

protected array $uuidMapping = [
    'tienda_id'  => catalogo_tienda::class,
    'cargo_id'   => sip_personalcargos::class,
    'periodo_id' => sip_periodoestandar::class,
];
```

---

## Para una fila — create / update

```php
// $data ANTES de mapUuidsToPkids:
$data = [
    'nombre'    => 'Producto A',
    'tienda_id' => 'a1b2c3d4e5f6...',  // UUID que envió el frontend
    'cargo_id'  => 'f6e5d4c3b2a1...',  // UUID que envió el frontend
];

$this->crud->mapUuidsToPkids($data, $this->uuidMapping);

// $data DESPUÉS de mapUuidsToPkids:
$data = [
    'nombre'    => 'Producto A',
    'tienda_id' => 42,   // pkid resuelto
    'cargo_id'  => 7,    // pkid resuelto
];
```

**Notas importantes:**
- Modifica `$data` **por referencia** — no retorna nada
- Si el campo no está en `$data`, lo salta (útil en `update` donde no todos los campos son obligatorios)
- Si el UUID no existe en la tabla, el campo queda en `0` — se debe validar con `exists:` en el [[Requests y Traits|FormRequest]] antes para evitar esto y enviar un mensaje desde antes de procesar como "el {parametro} no existe"
---

## Protección adicional: UUID inválido que igual llega en `0`

La validación `exists:` en el FormRequest cubre el caso normal, pero si por algún motivo (bulk sin validar, proceso automático) igual llega un valor no resuelto, el service debe protegerse **antes** de persistir — insertar `0` en una FK es un bug silencioso difícil de detectar después:

```php
// Post-mapeo, antes de persistir — en el service del módulo
foreach ($this->uuidMapping as $field => $_) {
    if (array_key_exists($field, $data) && $data[$field] === 0) {
        throw new \InvalidArgumentException("UUID inválido para '{$field}'");
    }
}
```

---

## Para múltiples filas — bulk

```php
// $rows ANTES:
$rows = [
    ['nombre' => 'Producto A', 'tienda_id' => 'uuid-tienda-1', 'cargo_id' => 'uuid-cargo-1'],
    ['nombre' => 'Producto B', 'tienda_id' => 'uuid-tienda-1', 'cargo_id' => 'uuid-cargo-2'],
    ['nombre' => 'Producto C', 'tienda_id' => 'uuid-tienda-2', 'cargo_id' => 'uuid-cargo-1'],
];

$this->crud->mapUuidsToPkidsBulk($rows, $this->uuidMapping);

// $rows DESPUÉS:
$rows = [
    ['nombre' => 'Producto A', 'tienda_id' => 42, 'cargo_id' => 7],
    ['nombre' => 'Producto B', 'tienda_id' => 42, 'cargo_id' => 9],
    ['nombre' => 'Producto C', 'tienda_id' => 55, 'cargo_id' => 7],
];
```

**Cómo funciona internamente (1 query por modelo, no N queries por fila):**

```
1. Recopila todos los UUIDs únicos de cada campo:
   catalogo_tienda  → ['uuid-tienda-1', 'uuid-tienda-2']
   sip_personalcargos → ['uuid-cargo-1', 'uuid-cargo-2']

2. Ejecuta 1 query por modelo:
   SELECT pkid, id FROM catalogo_tienda WHERE id IN ('uuid-tienda-1', 'uuid-tienda-2')
   SELECT pkid, id FROM sip_personalcargos WHERE id IN ('uuid-cargo-1', 'uuid-cargo-2')
   → diccionario [uuid => pkid] por modelo

3. Reemplaza en todas las filas usando el diccionario (sin más queries)
```

---

## Flujo completo en el Service para bulk

```php
public function cargarMasivo(array $rows): int
{
    // 1. Resolver UUIDs antes de insertar (operación bulk eficiente)
    $this->crud->mapUuidsToPkidsBulk($rows, $this->uuidMapping);

    // 2. bulkInsert agrega id, created_by_id, timestamps automáticamente
    return $this->crud->bulkInsert(
        {prefijo}_{modulo}::class,
        $rows,
        'carga_masiva_{modulo}',
    );
}
```
