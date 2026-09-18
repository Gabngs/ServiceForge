# Requests y Traits

Relacionado: [[Estandar Desarrollo Backend]] | [[Controller]] | [[Service del Módulo]] | [[Model]]

---

Cada módulo tiene su carpeta de Requests con Traits reutilizables para las reglas de validación.

Los FormRequests se usan para `store` y `update`. El `index` no necesita FormRequest — los filtros los procesa `useFilters()` directamente (ver [[useFilters]]).

---

## Estructura de carpetas

```
app/Http/Requests/
└── {Prefijo}/                           ← carpeta raíz del proyecto
    ├── {Modulo}/
    │   ├── Store{Modulo}Request.php     ← reglas para crear
    │   └── Update{Modulo}Request.php    ← reglas para actualizar
    └── Traits/
        ├── {Modulo}/                    ← traits específicos del módulo
        │   └── Validates{Modulo}.php
        ├── ValidatesUsuario.php         ← opcional — un trait POR FK, solo si esa
        ├── ValidatesRol.php             ←   FK se valida exactamente igual en 2+ módulos
        └── ...                          ←   (ver "Traits genéricos por FK" más abajo)
```

**Ningún trait se comparte "entre módulos" en el sentido de una regla fija que todos usan igual** — no existe un `ValidatesRelaciones.php` único y obligatorio. Cada `Validates{Modulo}.php` es cerrado a su módulo, con sus propias reglas de `required`/`sometimes`/`nullable`. Lo único que puede vivir en `Traits/` a nivel raíz (fuera de `{Modulo}/`) es un trait **por FK específica** (`ValidatesUsuario.php`, `ValidatesRol.php`), y solo cuando 2+ módulos necesitan validar esa misma FK — el trait factoriza la parte que sí es idéntica entre módulos (`string|exists:{tabla},id` + los mensajes), pero deja la modalidad (`required` vs `sometimes` vs `nullable`) como parámetro que cada módulo decide al llamarlo — ver el patrón completo en "Traits genéricos por FK" más abajo, que resuelve exactamente el caso "obligatorio en un módulo, opcional o ausente en otro".

---

## Mapeo tipo SQL → regla de validación

Tabla de referencia para no dejar ambigüedad al escribir `rules()`: qué regla Laravel corresponde a cada tipo de columna, y cómo cambia entre `Store` (creación) y `Update` (edición parcial).

| Tipo SQL | Nullable | Regla Store | Regla Update |
|---|---|---|---|
| `varchar(n)` | NO | `required\|string\|max:n` | `sometimes\|string\|max:n` |
| `varchar(n)` | YES | `nullable\|string\|max:n` | `nullable\|string\|max:n` |
| `char(n)` | NO | `required\|string\|size:n` | `sometimes\|string\|size:n` |
| `text` / `longtext` | NO | `required\|string` | `sometimes\|string` |
| `text` / `longtext` | YES | `nullable\|string` | `nullable\|string` |
| `int` / `bigint` | NO | `required\|integer` | `sometimes\|integer` |
| `int` / `bigint` | YES | `nullable\|integer` | `nullable\|integer` |
| `tinyint(1)` | — | `sometimes\|boolean` | `sometimes\|boolean` |
| `decimal(m,d)` | NO | `required\|numeric` | `sometimes\|numeric` |
| `decimal(m,d)` | YES | `nullable\|numeric` | `nullable\|numeric` |
| `date` | NO | `required\|date` | `sometimes\|date` |
| `date` | YES | `nullable\|date` | `nullable\|date` |
| `datetime` / `timestamp` | NO | `required\|date_format:Y-m-d H:i:s` | `sometimes\|date_format:Y-m-d H:i:s` |
| `datetime` / `timestamp` | YES | `nullable\|date_format:Y-m-d H:i:s` | `nullable\|date_format:Y-m-d H:i:s` |
| `json` | NO | `required\|array` | `sometimes\|array` |
| `json` | YES | `nullable\|array` | `nullable\|array` |
| `enum(...)` | NO | `required\|in:val1,val2` | `sometimes\|in:val1,val2` |
| `*_id` (FK a UUID) | NO | `required\|string\|exists:{tabla},id` | `sometimes\|string\|exists:{tabla},id` |
| `*_id` (FK a UUID) | YES | `nullable\|string\|exists:{tabla},id` | `nullable\|string\|exists:{tabla},id` |

### Campos siempre excluidos del Request

```
pkid           → PK interna, nunca del usuario
id             → UUID, asignado por CrudService al crear
created_at     → timestamps de Laravel
updated_at     → timestamps de Laravel
deleted_at     → SoftDeletes de Laravel
created_by_id  → asignado por CrudService via Token
updated_by_id  → asignado por CrudService via Token
deleted_by_id  → asignado por CrudService via Token
```

### Casts automáticos en el Model según el tipo SQL

| Tipo SQL | Cast en [[Model]] |
|---|---|
| `tinyint(1)` | `'campo' => 'boolean'` |
| `decimal(m,d)` | `'campo' => 'decimal:d'` |
| `json` | `'campo' => 'array'` |
| `date` | `'campo' => 'date'` |
| `datetime` | `'campo' => 'datetime'` |

---

## Regla para unique constraints — pkid vs id en el ignore

Toda tabla de negocio del patrón (crud básico) tiene `pkid` + `id`, así que el ignore del `unique` en `UpdateRequest` siempre va contra `pkid` (ver [[Model#Regla: pkid vs id como PK]]):

```php
// Caso estándar — toda tabla del crud básico (tiene pkid + id):
'campo' => "sometimes|string|unique:{tabla},campo,{$model->pkid},pkid"

// Caso fuera del patrón — tablas sin pkid (infraestructura/Laravel/Docker, no son parte del crud básico):
'campo' => "sometimes|string|unique:{tabla},campo,{$model->id},id"
```

Regla práctica: en un módulo del patrón, el ignore siempre va contra `pkid`, nunca contra `id`. El segundo caso solo aplica a tablas que no pasan por este patrón (no tienen Controller/Service/Request propios).

---

## Store Request — ejemplo completo

```php
<?php

namespace App\Http\Requests\{Prefijo}\{Modulo};

use App\Http\Requests\{Prefijo}\Traits\{Modulo}\Validates{Modulo};
use Illuminate\Foundation\Http\FormRequest;

class Store{Modulo}Request extends FormRequest
{
    use Validates{Modulo};

    // authorize() decide si el usuario tiene permiso de hacer este request.
    // Retornar true = permitido para todos los autenticados.
    // Se puede consultar permisos específicos aquí si el proyecto los usa.
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        return array_merge(
            $this->getRelacionesRules(),   // reglas FK del trait — Store usa el default 'required'
            [
                // Campos propios del módulo
                'nombre'      => 'required|string|max:150',
                'codigo'      => 'required|string|max:20|unique:{prefijo}_{modulo},codigo',
                'descripcion' => 'nullable|string|max:500',
                'activo'      => 'sometimes|boolean',
            ]
        );
    }

    public function messages(): array
    {
        return array_merge(
            $this->getRelacionesMensajes(), // mensajes FK del trait
            [
                'nombre.required'    => 'El nombre es requerido',
                'nombre.max'         => 'El nombre no puede superar 150 caracteres',
                'codigo.required'    => 'El código es requerido',
                'codigo.unique'      => 'El código ya existe',
            ]
        );
    }
}
```

---

## Update Request — ejemplo completo

```php
<?php

namespace App\Http\Requests\{Prefijo}\{Modulo};

use App\Http\Requests\{Prefijo}\Traits\{Modulo}\Validates{Modulo};
use Illuminate\Foundation\Http\FormRequest;

class Update{Modulo}Request extends FormRequest
{
    use Validates{Modulo};

    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        // $this->route('{prefijo}_{modulo}') obtiene el modelo inyectado por Route Model Binding
        // Se usa para excluir el registro actual de la validación unique
        $modelId = $this->route('{prefijo}_{modulo}')?->pkid;

        return array_merge(
            $this->getRelacionesRules('sometimes'),   // Update: FK opcional en el body, igual que el resto de campos
            [
                'nombre'      => 'sometimes|string|max:150',
                // ignore el pkid actual para no fallar unique al actualizar el mismo registro
                'codigo'      => "sometimes|string|max:20|unique:{prefijo}_{modulo},codigo,{$modelId},pkid",
                'descripcion' => 'nullable|string|max:500',
                'activo'      => 'sometimes|boolean',
            ]
        );
    }

    public function messages(): array
    {
        return array_merge(
            $this->getRelacionesMensajes(),
            [
                'nombre.max'    => 'El nombre no puede superar 150 caracteres',
                'codigo.unique' => 'El código ya existe',
            ]
        );
    }
}
```

---

## Trait — ejemplo completo

```php
<?php

namespace App\Http\Requests\{Prefijo}\Traits\{Modulo};

trait Validates{Modulo}
{
    /**
     * Reglas para campos que son FK (llegan como UUID desde el frontend).
     * La validación 'exists' confirma que el UUID existe en la tabla antes de persistir.
     * El mapeo UUID → PKID lo hace el Service después (ver [[Mapeo UUID PKID]]).
     *
     * $modality: 'required' (Store) o 'sometimes' (Update) — la parte que SÍ
     * cambia entre los dos FormRequests. 'string|exists:...' es la parte fija
     * que no cambia, por eso vive hardcodeada acá y no se repite en cada caller.
     */
    protected function getRelacionesRules(string $modality = 'required', string $prefix = ''): array
    {
        return [
            "{$prefix}tienda_id"  => "{$modality}|string|exists:catalogo_tienda,id",
            "{$prefix}cargo_id"   => "{$modality}|string|exists:{prefijo}_personalcargos,id",
        ];
    }

    protected function getRelacionesMensajes(string $prefix = ''): array
    {
        return [
            "{$prefix}tienda_id.required" => 'La tienda es requerida',
            "{$prefix}tienda_id.exists"   => 'La tienda no existe',
            "{$prefix}cargo_id.required"  => 'El cargo es requerido',
            "{$prefix}cargo_id.exists"    => 'El cargo no existe',
        ];
    }
}
```

**Antes esta página tenía un bug: el comentario decía "usar `sometimes` en update" pero el código dejaba `required` fijo** — `Update{Modulo}Request` llamaba `getRelacionesRules()` y heredaba `required` igual que `Store`, contradiciendo la regla de "Update es todo opcional" de la tabla de mapeo del inicio de esta página. `$modality` con default `'required'` corrige esto: `Store` llama `getRelacionesRules()` sin argumentos (usa el default), `Update` llama `getRelacionesRules('sometimes')` explícitamente — ver los dos call sites abajo.

---

## Traits genéricos por FK — reutilización entre módulos

En vez de un trait por módulo, cuando la misma FK aparece en 2 o más módulos conviene un trait por FK reutilizable:

```
app/Http/Requests/{Prefijo}/Traits/
├── ValidatesUsuario.php      ← usuario_id reutilizable en N módulos
├── ValidatesRol.php          ← rol_id reutilizable en N módulos
└── Validates{Modulo}.php     ← solo si tiene reglas únicas
```

**Regla:** si la misma FK aparece en 2+ módulos, merece su propio Trait en vez de repetir la regla `exists:` en cada `Validates{Modulo}`.

### Trait de FK reutilizable — obligatorio en un módulo, opcional (o ausente) en otro

Compartir el trait de una FK **no** significa que todos los módulos que la usan tengan la misma modalidad (`required`/`sometimes`/`nullable`) — eso casi nunca es cierto. Lo único realmente idéntico entre módulos es la parte mecánica: el tipo (`string`) y la tabla contra la que se valida (`exists:catalogo_tienda,id`). La modalidad la decide cada módulo al llamar el método, igual que en `Validates{Modulo}` (ver más arriba):

```php
<?php

namespace App\Http\Requests\{Prefijo}\Traits;

trait ValidatesTienda
{
    // $modality: 'required' | 'sometimes' | 'nullable' — la decide el caller.
    protected function getTiendaRules(string $modality = 'required', string $prefix = ''): array
    {
        return [
            "{$prefix}tienda_id" => "{$modality}|string|exists:catalogo_tienda,id",
        ];
    }

    protected function getTiendaMensajes(string $prefix = ''): array
    {
        return [
            "{$prefix}tienda_id.required" => 'La tienda es requerida',
            "{$prefix}tienda_id.exists"   => 'La tienda no existe',
        ];
    }
}
```

Caso concreto — `tienda_id` obligatorio siempre en el módulo A, opcional en el módulo B, y el módulo C ni siquiera lo usa:

```php
// StoreARequest — obligatorio en Store
use ValidatesTienda;
public function rules(): array
{
    return array_merge($this->getTiendaRules(), [...]); // default 'required'
}

// UpdateARequest — sometimes en Update (igual que cualquier otro campo del módulo)
public function rules(): array
{
    return array_merge($this->getTiendaRules('sometimes'), [...]);
}

// StoreBRequest / UpdateBRequest — opcional siempre, tienda no es obligatoria en B
public function rules(): array
{
    return array_merge($this->getTiendaRules('nullable'), [...]);
}

// StoreCRequest / UpdateCRequest — C no tiene tienda_id: simplemente no usa ValidatesTienda
```

Si un módulo necesita una regla que ninguna combinación de `$modality` puede expresar (ej. `tienda_id` requerido solo cuando otro campo tiene cierto valor — `required_if`), ese caso puntual **no** fuerza a complicar el trait compartido: se declara directo en el `Validates{Modulo}` de ese módulo, sin usar `ValidatesTienda`. El trait compartido cubre el caso común (mismo tipo + misma tabla, modalidad variable); lo que se sale de eso va con reglas directas, como ya dice la tabla "Cuándo usar Trait vs reglas directas" más abajo.

### Trait con reglas reutilizables entre módulos — ejemplo días de la semana

```php
<?php

namespace App\Http\Requests\{Prefijo}\Traits;

trait ValidatesDiasSemana
{
    // $prefix permite reutilizar en validaciones anidadas (ej: filas de un bulk)
    // Sin prefix: 'lunes' => ...
    // Con prefix 'horario.': 'horario.lunes' => ...
    protected function getDiasRules(string $prefix = ''): array
    {
        $rules = [];
        foreach (['lunes','martes','miercoles','jueves','viernes','sabado','domingo'] as $dia) {
            $rules["{$prefix}{$dia}"] = 'sometimes|integer|min:0|max:24';
        }
        return $rules;
    }

    protected function getDiasMensajes(string $prefix = ''): array
    {
        $msgs = [];
        foreach (['lunes','martes','miercoles','jueves','viernes','sabado','domingo'] as $dia) {
            $msgs["{$prefix}{$dia}.integer"] = "El {$dia} debe ser un número entero";
            $msgs["{$prefix}{$dia}.min"]     = "El {$dia} no puede ser negativo";
            $msgs["{$prefix}{$dia}.max"]     = "El {$dia} no puede superar 24 horas";
        }
        return $msgs;
    }
}
```

---

## Reglas de validación más usadas

```php
// Campo FK (UUID que se mapea a PKID en el service)
'tienda_id' => 'required|string|exists:catalogo_tienda,id'

// UUID opcional
'otra_id' => 'nullable|string|exists:otra_tabla,id'

// Unique excluyendo el registro actual (siempre en Update)
'codigo' => "sometimes|string|unique:{prefijo}_{modulo},codigo,{$modelId},pkid"

// Boolean que puede venir como "true"/"false" string desde el frontend
'activo' => 'sometimes|boolean'

// Array para carga masiva
'filas'          => 'required|array|min:1'
'filas.*.nombre' => 'required|string|max:150'
'filas.*.activo' => 'sometimes|boolean'
```

---

## Cuándo usar Trait vs reglas directas

| Usar Trait | Usar reglas directas |
|---|---|
| Las mismas reglas se repiten en `Store` y `Update` | Las reglas son únicas para ese request |
| Varios módulos comparten los mismos campos FK | Son campos simples sin reutilización |
| Las reglas de días, montos, etc. aplican en múltiples lugares | El campo solo existe en un módulo |
