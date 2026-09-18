# Conexiones, Migraciones y Rutas

Relacionado: [[Estandar Desarrollo Backend]] | [[Controller]] | [[Migraciones y Catálogos]] | [[Service del Módulo]] | [[Seguridad]]

---

Formaliza como regla del estándar lo que antes vivía como nota descriptiva de un proyecto puntual — acá es **prescriptivo**: así nace todo proyecto nuevo, no "así lo resolvió este repo en particular". Cubre tres frentes que no tienen dueño claro en el resto de las notas de [[Service Patron]] porque son de arranque de proyecto, no de un módulo individual: cómo se nombran y organizan las conexiones a base de datos, cómo migraciones y seeders quedan centralizados pese a vivir en bases físicas distintas, y cómo se registran las rutas (incluido cuándo una ruta necesita permiso explícito y cuándo no).

---

## 1. Conexiones de base de datos — regla de nombres

**Regla dura: el nombre de la conexión Eloquent es `db{prefijo}`, sin prefijo de driver.** Nunca `mysql_dbgsp`, `mysql_db{prefijo}` ni variantes con el motor en el nombre — el driver es un detalle de `config/database.php` (`'driver' => 'mysql'` dentro de esa entrada), no algo que el resto del código necesite ver. Todo lo que referencia la conexión (`protected $connection` en migraciones y en el [[Model]], `Schema::connection(...)`, `DB::connection(...)`) usa literalmente `db{prefijo}` — el mismo string que ya se usa como segmento del namespace del modelo (`App\Models\db{prefijo}\...`, ver [[Model]]). Nombre de conexión y namespace del modelo son el mismo string a propósito, para que no haya que recordar dos convenciones distintas para lo mismo.

| Prefijo del proyecto | Conexión Eloquent |
|---|---|
| `gsp_` | `dbgsp` |
| `mdt_` | `dbmdt` |
| `sip_` | `dbsip` |

**Todo proyecto nuevo nace con dos conexiones fijas, además de la suya propia**, sin importar el prefijo de negocio:

| Conexión fija | Para qué |
|---|---|
| `dbsiaw` | Usuarios/roles/permisos compartidos. Es la conexión de la que salen los modelos de usuario que resuelven `created_by`/`updated_by`/`deleted_by` en cualquier módulo (ver [[Service del Módulo#`const RELATIONS`...]]) — sin `dbsiaw` (o un equivalente), esas tres relaciones de auditoría no tienen a qué apuntar. |
| `dbsincro` | Infraestructura: ledger centralizado de migraciones + `seeders_log` (ver secciones 2 y 3). No guarda tablas de negocio de ningún módulo. |

---

## 2. Migraciones — carpeta por módulo, ledger centralizado

- Cada módulo con base propia declara `protected $connection = 'db{prefijo}'` en
  la migración y `Schema::connection($this->connection)->...` — nunca hardcodea
  el nombre de la base física ni el driver.
- Las migraciones van en `database/migrations/{Modulo}/` (ver también [[Migraciones y Catálogos]]
  para el diseño de las tablas en sí) — `AppServiceProvider` hace
  `loadMigrationsFrom(glob(database_path('migrations/*'), GLOB_ONLYDIR))`, así que
  basta crear la carpeta para que un módulo nuevo quede registrado, sin tocar el provider.

**Regla dura: el ledger de "qué migración ya corrió" vive centralizado en `dbsincro`, sin importar en qué conexión corra cada migración.** Por defecto Laravel guarda la tabla `migrations` en la conexión de cada migración — sin esta regla, un proyecto con 3+ conexiones termina con una tabla `migrations` distinta por base, y `php artisan migrate:status` deja de ser una fuente de verdad única. Se resuelve reemplazando el *binding* del repositorio de migraciones para que siempre escriba en `dbsincro`, sin importar qué `$connection` declare cada `up()`/`down()`:

```php
// app/Providers/AppServiceProvider.php — register()
$this->app->extend('migration.repository', function ($repository, $app) {
    $migrations = $app['config']['database.migrations'];
    $table = is_array($migrations) ? ($migrations['table'] ?? 'migrations') : $migrations;

    return new CentralMigrationRepository($app['db'], $table);
});
```

```php
// app/Database/CentralMigrationRepository.php
class CentralMigrationRepository extends \Illuminate\Database\Migrations\DatabaseMigrationRepository
{
    public const LEDGER_CONNECTION = 'dbsincro';

    public function setSource($name)
    {
        parent::setSource(self::LEDGER_CONNECTION);   // ignora la conexión de la migración...
    }

    public function getConnection()
    {
        return $this->resolver->connection(self::LEDGER_CONNECTION); // ...y fuerza dbsincro
    }
}
```

Efecto: un solo `php artisan migrate --force`, **sin flags** (ni `--database`, ni `--path`), migra todas las conexiones del proyecto y deja un único historial consultable en `dbsincro`.

---

## 3. Seeders — idempotentes entre deploys vía `seeders_log`

Problema que resuelve: si `php artisan db:seed --force` corre en cada deploy (patrón estándar en CI/CD, ver [[Despliegue]]), un seeder no idempotente duplica filas en cada push. La tabla de control vive en `dbsincro`, igual que el ledger de migraciones:

```php
// database/migrations/Sincro/..._create_seeders_log_table.php
protected $connection = 'dbsincro';

Schema::connection($this->connection)->create('seeders_log', function (Blueprint $table) {
    $table->id();
    $table->string('seeder')->unique();
    $table->timestamp('ran_at');
});
```

`DatabaseSeeder` consulta `seeders_log` antes de correr cada seeder de la lista, y solo ejecuta (y registra) los que todavía no están:

```php
// database/seeders/DatabaseSeeder.php
$log        = DB::connection('dbsincro')->table('seeders_log');
$yaCorridos = $log->pluck('seeder')->all();

foreach ($seeders as $seederClass) {   // array ordenado a mano — el orden importa
    if (in_array($seederClass, $yaCorridos, true)) {
        continue;
    }

    $this->call($seederClass);

    $log->insert(['seeder' => $seederClass, 'ran_at' => now()]);
}
```

**Agregar un seeder nuevo = agregarlo al final de `$seeders`** — en el siguiente deploy solo ese corre, porque el resto ya está en `seeders_log`. `$seeders` se ordena a mano porque el orden es semántico (ej. roles → usuarios → catálogos → permisos), no alfabético.

**Resumen del patrón (migraciones + seeders):** cada módulo trabaja en su propia conexión física, pero el "libro de contabilidad" de qué ya se ejecutó vive en un solo lugar (`dbsincro`) — `migrations` para DDL, `seeders_log` para DML de seeders. Eso es lo que permite correr `migrate --force && db:seed --force` de forma segura en cada deploy sin duplicar nada ni rastrear una tabla `migrations` por conexión.

---

## 4. Rutas — `RouteServiceProvider` y el CRUD de una línea

### `RouteServiceProvider` — auto-carga con auth ya aplicado

El proyecto **no** declara rutas directamente en `routes/api.php`. `RouteServiceProvider` autoincluye cada archivo de `routes/modules/` (uno por recurso) dentro de un único grupo que ya exige token válido — así ningún archivo de módulo tiene que repetir `prefix('api')`/`middleware(['auth:sanctum'])` por su cuenta:

```php
// app/Providers/RouteServiceProvider.php — boot()
$files = glob(base_path('routes/modules') . DIRECTORY_SEPARATOR . '*.php') ?: [];

Route::prefix('api')->middleware(['auth:sanctum'])->group(function () use ($files) {
    foreach ($files as $file) {
        require $file;
    }
});
```

Agregar un módulo = crear `routes/modules/{modulo}.php`, sin tocar el provider.

### `routes/modules/{modulo}.php` — una sola línea para el CRUD base

```php
<?php

use App\Http\Controllers\Api\{Prefijo}\{prefijo}_{modulo}Controller;
use Illuminate\Support\Facades\Route;

Route::apiResource('{prefijo}_{modulo}', {prefijo}_{modulo}Controller::class);
```

`apiResource` genera automáticamente las 5 rutas del contrato: `index`, `store`, `show`, `update`, `destroy` (ver [[Controller]]). **Regla dura: el CRUD base va siempre en esta única línea**, encadenando lo que haga falta sin romperla:

```php
Route::apiResource('{prefijo}_{modulo}', {prefijo}_{modulo}Controller::class)
    ->parameters(['{prefijo}_{modulo}' => '{prefijo}_{modulo}']); // nombre del parámetro de ruta — evita el plural mal resuelto por Laravel al formar la URL
```

No es una preferencia de estilo: un proyecto puede legítimamente optar por declarar cada verbo a mano (por ejemplo, para dar un permiso distinto por verbo — `apiResource()` solo acepta un `->middleware()` para todo el grupo) y esa no es una forma "incorrecta" de usar Laravel. Simplemente **no es lo que este estándar prescribe** — acá el CRUD base siempre es la línea única de arriba; si un módulo necesita autorización granular por verbo más allá de la regla de la sección 5, eso se resuelve con un endpoint extra explícito (ver más abajo), no reventando el `apiResource()` en 5 rutas sueltas.

### Regla de orden — endpoints extra SIEMPRE antes del `apiResource()`

Si el controller tiene métodos fuera del contrato CRUD (ej. `reporte`, `housekeeping`), su ruta se declara **arriba** de la línea `apiResource()` en el mismo archivo, nunca abajo. Laravel resuelve rutas en el orden en que se registran — `show` (`GET {modulo}/{id}`) matchea *cualquier* segmento como `{id}`, incluido uno que en realidad era el path literal de otro endpoint:

```php
// ❌ MAL — apiResource() antes del endpoint extra
Route::apiResource('agh_habitaciones', AghHabitacionesController::class);

// Esta ruta nunca se alcanza: GET agh_habitaciones/housekeeping matchea primero
// contra GET agh_habitaciones/{agh_habitacion} (show, ya registrada arriba) —
// Laravel entra a show() con $agh_habitacion = "housekeeping" y busca ese
// "id" en la tabla. Es exactamente el bug de "lee un parámetro como si fuera
// un id" que aparece cuando el orden de registro es el que no toca.
Route::get('agh_habitaciones/housekeeping', [AghHabitacionesController::class, 'housekeeping']);
```

```php
// ✅ BIEN — el endpoint extra se declara primero, el apiResource() después
Route::get('agh_habitaciones/housekeeping', [AghHabitacionesController::class, 'housekeeping']);

Route::apiResource('agh_habitaciones', AghHabitacionesController::class);
```

---

## 5. Permisos en rutas — cuándo mapear y cuándo no

**El CRUD básico (`index`/`show`/`store`/`update`/`destroy`) no lleva middleware de permiso mapeado en la ruta.** No es un descuido — es la regla: qué puede hacer cada usuario con el CRUD estándar de un módulo (ver/crear/editar/eliminar) se resuelve del lado del frontend, contra la lista de permisos que trae el usuario autenticado (oculta/deshabilita botones según lo que el rol permite). La ruta del `apiResource()` (sección 4) se deja sin `permiso:` — el único guard que lleva es `auth:sanctum`, aplicado centralizado en `RouteServiceProvider`: cualquier usuario logueado puede llegar al endpoint, y es el frontend el que decide qué mostrarle.

**Excepción — rutas sensibles: SÍ necesitan protegerse en el backend.** Cuando una acción está restringida a un rol elevado (`isSuperUser`, `isAdmin`) o dispara algo que no es un simple CRUD de negocio (una operación masiva, un proceso irreversible, una acción sobre datos de otro usuario), confiar solo en que el frontend oculte el botón no alcanza — cualquiera con un token válido puede llamar al endpoint directo (Postman, curl) sin pasar por la UI. Esas rutas sí llevan `->middleware('permiso:isSuperUser,isAdmin')` (o el permiso puntual que corresponda) explícito en la ruta:

```php
// routes/modules/{modulo}.php
Route::apiResource('{prefijo}_{modulo}', {prefijo}_{modulo}Controller::class);

// Endpoint sensible del mismo módulo — SÍ lleva permiso explícito en la ruta
Route::post('{prefijo}_{modulo}/cerrar-periodo', [{prefijo}_{modulo}Controller::class, 'cerrarPeriodo'])
    ->middleware('permiso:isSuperUser,isAdmin');
```

Recordar la regla de orden de la sección 4: si ese endpoint sensible cae bajo el mismo prefijo que el recurso (`{prefijo}_{modulo}/algo`), igual va declarado **antes** del `apiResource()`.

**Por qué esto no lo resuelve el CORS del proyecto (no son la misma barrera):** CORS lo aplica el **navegador**, no el servidor — decide si el JavaScript de una página de otro origen puede *leer* la respuesta de un `fetch`/`XHR`, vía el header `Access-Control-Allow-Origin` (más un preflight `OPTIONS` cuando la request no es "simple", que es el caso de cualquier llamada con `Authorization: Bearer ...`). Postman, curl, un script o una app nativa **no son navegadores** — no implementan CORS, no hay ningún chequeo de origen en su camino. Si a curl o Postman se le da un token válido, la request sale con ese header, Laravel la ve como una request autenticada normal, y si la ruta no tiene `permiso:`, se ejecuta — el `Access-Control-Allow-Origin` restringido al dominio del frontend no entra en juego para nada, porque esa restricción es comportamiento del navegador, no algo que el servidor pueda usar para rechazar la request. Lo que CORS protege es un escenario distinto: una página maliciosa corriendo en el navegador de la víctima intentando leer la respuesta de una llamada a la API usando la sesión de ese navegador — no protege contra alguien que ya tiene un token válido y lo usa fuera del navegador. Por eso la única barrera real para una ruta sensible vive en el servidor: `auth:sanctum` (token válido) + `permiso:` (ese usuario en particular puede hacer esa acción en particular) — ninguno de los dos depende de por dónde llegó la request.

**Regla práctica para decidir:** ¿el peor caso de que alguien llame este endpoint sin pasar por la UI es que un usuario autenticado normal toque un registro para el que ya tenía permiso de negocio? → no hace falta `permiso:` en la ruta, el frontend alcanza. ¿El peor caso es una escalada de privilegio o una operación que un usuario normal nunca debería poder disparar? → `permiso:` explícito en la ruta, no negociable.

El mecanismo real del middleware `permiso:` (cómo resuelve `isSuperUser`/`isAdmin`/permisos por sistema) vive en [[Middleware de Seguridad]] y [[Permisos Multi-Sistema]] — fuera del alcance de este documento, que solo cubre la regla de *cuándo* mapear un permiso en la ruta, no *cómo* funciona el middleware por dentro.
