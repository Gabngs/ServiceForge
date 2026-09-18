# Migraciones y Catálogos

Relacionado: [[Estandar Desarrollo Backend]] | [[Model]] | [[Mapeo UUID PKID]] | [[Requests y Traits]] | [[Service del Módulo]] | [[Conexiones, Migraciones y Rutas]]

---

## Regla dura: sin `enum`, sin FKs

Ninguna migración del proyecto usa `$table->enum(...)` ni
`$table->foreign(...)`. Las dos cosas se resuelven por lógica PHP.

### Sin `enum` en BD → tabla catálogo
Todo conjunto cerrado de valores (estados, tipos, modos, políticas) es una
**tabla catálogo** con esta forma mínima:

```php
Schema::connection($this->connection)->create('{prefijo}_tipos_algo', function (Blueprint $table) {
    $table->bigInteger('pkid')->autoIncrement()->index();
    $table->string('id', 36)->unique()->index();
    $table->string('codigo', 40)->unique();   // slug estable que usa el código PHP
    $table->string('nombre', 100);
    $table->string('descripcion', 255)->nullable();
    // ... metadatos propios del catálogo (signo, tasa, afecta_x, ...)
    $table->tinyInteger('activo')->default(1);
    $table->bigInteger('created_by_id')->nullable()->index();
    $table->bigInteger('updated_by_id')->nullable()->index();
    $table->bigInteger('deleted_by_id')->nullable()->index();
    $table->timestamps();
    $table->softDeletes();
});
```

- Las filas base se **siembran en el `up()` de la misma migración**, siempre en
  el mismo orden → el `pkid` es estable en todo entorno.
- El modelo expone constantes de `pkid` para que el Service no dependa de
  strings: `const ENTRADA_COMPRA = 1;`.
- La columna que referencia el catálogo es `{catalogo_singular}_id`
  (`bigInteger`, `index`), nunca el string del valor.
- **Aunque sean solo 2 valores.** Si alguna lógica los distingue, van a tabla.
  Ej.: RUC de persona jurídica (`20…`) vs. persona natural con negocio (`10…`)
  en Perú → filas `RUC-20` / `RUC-10` en `{prefijo}_tipos_identificador`, no un
  `if (substr($ruc, 0, 2) === '20')`.

Referencia histórica: las migraciones `replace_enums_in_agh_*` /
`replace_enum_in_agh_*` convirtieron los `enum` originales de AGH a este patrón
(mapa `valor viejo → pkid nuevo`, backfill, `dropColumn`).

### Catálogo genérico de dos niveles — `{prefijo}_catalogo` / `{prefijo}_catalogo_det`

Cuando un proyecto acumula **muchos catálogos simples que comparten la misma
forma** (código + nombre + descripción + un par de campos cortos), crear una
tabla dedicada por cada uno (`{prefijo}_monedas`, `{prefijo}_metodos_pago`,
`{prefijo}_aerolineas`, ...) es repetir el mismo par migración+modelo N veces
para el mismo problema. En ese caso se usa **un solo par de tablas** para
todos esos catálogos simples:

- **`{prefijo}_catalogo`** — el "tipo" de catálogo (una fila por catálogo).
- **`{prefijo}_catalogo_det`** — los valores de cada catálogo, con
  `catalogo_id` apuntando al `pkid` de su fila padre en `{prefijo}_catalogo`.

```php
Schema::connection($this->connection)->create('{prefijo}_catalogo', function (Blueprint $table) {
    $table->bigInteger('pkid')->autoIncrement()->index();
    $table->string('id', 36)->unique()->index();
    $table->string('codigo', 60)->unique();      // ej: 'catalogo_monedas'
    $table->string('nombre', 150);                // ej: 'Catálogo de monedas'
    $table->string('descripcion', 255)->nullable();
    $table->tinyInteger('activo')->default(1);
    $table->bigInteger('created_by_id')->nullable()->index();
    $table->bigInteger('updated_by_id')->nullable()->index();
    $table->bigInteger('deleted_by_id')->nullable()->index();
    $table->timestamps();
    $table->softDeletes();
});

Schema::connection($this->connection)->create('{prefijo}_catalogo_det', function (Blueprint $table) {
    $table->bigInteger('pkid')->autoIncrement()->index();
    $table->string('id', 36)->unique()->index();
    $table->bigInteger('catalogo_id')->index();    // FK lógica → {prefijo}_catalogo.pkid
    $table->string('codigo', 60);                  // ej: 'USD' — único DENTRO del catálogo, no global
    $table->string('abreviatura', 20)->nullable();  // ej: 'US$', 'S/'
    $table->string('nombre', 150);                  // ej: 'Dólar Americano'
    $table->string('descripcion', 255)->nullable();
    // Par de campos genéricos, comunes a distintos catálogos, para no tener
    // que agregar una columna nueva cada vez que un catálogo necesita "un
    // dato más" (ej: tasa de una moneda, comisión de un método de pago):
    $table->decimal('valor_numerico', 18, 6)->nullable();
    $table->string('valor_texto', 255)->nullable();
    $table->tinyInteger('activo')->default(1);
    $table->bigInteger('created_by_id')->nullable()->index();
    $table->bigInteger('updated_by_id')->nullable()->index();
    $table->bigInteger('deleted_by_id')->nullable()->index();
    $table->timestamps();
    $table->softDeletes();

    $table->unique(['catalogo_id', 'codigo']);
});
```

- Las filas de `{prefijo}_catalogo` (los "tipos") se siembran en un seeder,
  igual que cualquier catálogo — ver [[Model#Regla: pkid vs id como PK]] para
  el resto del patrón de modelo (`pkid` interno + `id` UUID público).
- El modelo de `{prefijo}_catalogo_det` expone constantes agrupadas por
  catálogo si el código PHP necesita referenciar un valor puntual (ej.
  `MdtCatalogoDet::MONEDA_USD = 1;`), igual que cualquier catálogo cerrado.
- **Cuándo usar este patrón vs. una tabla dedicada:** si el catálogo es
  cerrado y simple (código + nombre + 1-2 campos cortos, sin relaciones de
  negocio propias) → `catalogo`/`catalogo_det`. Si el catálogo tiene columnas
  propias y numerosas que no tiene sentido generalizar (ej. un aeropuerto con
  IATA/ciudad/país/lat/long, un proveedor con RUC/contacto/dirección) → tabla
  dedicada con el patrón normal de arriba. La pregunta guía es la misma que
  para `enum`: *¿esta forma se repite igual en 2 o más catálogos del
  proyecto?* Si sí, va al genérico; si no, tabla propia.
- El filtro por catálogo (`?catalogo_id={uuid}`) en `{prefijo}_catalogo_det`
  sigue la regla normal de FK que guarda `pkid` — ver
  [[useFilters#FKs que guardan `pkid` — el filtro `*_id` SIEMPRE necesita método resolver]].

### Sin FKs en la migración

Solo `$table->bigInteger('x_id')->index();`. La integridad referencial la
garantizan:

- El **Form Request** ([[Requests y Traits]]): `exists:` lógico o regla propia
  que valida que el uuid recibido corresponde a una fila viva.
- El **Service** ([[Mapeo UUID PKID]]): `mapUuidsToPkids()` resuelve el uuid a
  `pkid` antes de persistir y deja `0` (que no existe) si no lo encuentra.

Motivo: las tablas viven en bases físicas distintas (`dbgsp`, `dbagh`,
`dbnexo`, `dbsiaw`) y muchas relaciones cruzan de base — una FK real no
es posible ni deseable. El `pkid` es un id lógico.

---

## Precisión y columnas

- `decimal` con precisión explícita: **cantidades `(18,4)`**, **costos/tasas
  `(18,6)`**, **valores monetarios `(18,2)`**. Nada de `decimal(10,2)` por
  inercia.
- Doble id en toda tabla de negocio: `pkid` (bigint, interno, para joins y FKs
  lógicas) + `id` (`char(36)` uuid, único, lo único que ve el front).
- Auditoría estándar: `created_by_id`, `updated_by_id`, `deleted_by_id`
  (nullable, index) + `timestamps()` + `softDeletes()`.

### Excepción: tablas append-only (ledger / kardex / logs)

Una tabla que es un **libro de asientos** (movimientos de stock, log de envíos,
bitácora inmutable) **no** lleva `softDeletes()` **ni** `updated_at`:

```php
$table->bigInteger('created_by_id')->nullable()->index();
$table->timestamp('created_at')->useCurrent();
// SIN updated_at, SIN softDeletes
$table->string('clave_idempotencia', 120)->nullable()->unique();
```

Un error se corrige con una **fila de contrapartida** (`es_reversa = 1` +
`movimiento_par_id`), nunca con `UPDATE` / `DELETE`. Ver
`StockMovementService` (AGH y Nexo).

---

## Configuración del sistema — `{prefijo}_configuracion_sistema`

Tabla de parámetros clave/valor que el sistema lee en tiempo de ejecución
para cálculos y procesos (ej. valor de dólar del día, hora de corte de caja,
credenciales de una integración externa) sin tener que hardcodear el dato ni
crear una columna nueva cada vez que aparece un parámetro nuevo.

```php
Schema::connection($this->connection)->create('{prefijo}_configuracion_sistema', function (Blueprint $table) {
    $table->bigInteger('pkid')->autoIncrement()->index();
    $table->string('id', 36)->unique()->index();
    $table->string('codigo', 80)->unique();         // ej: 'valor_dolar'
    $table->string('descripcion', 255);              // ej: 'Valor de dólar del sistema'
    $table->string('valor', 255)->nullable();         // SIEMPRE varchar — ver regla abajo
    $table->string('grupo', 60)->nullable();          // ej: 'integraciones', 'finanzas' — agrupa en el form admin
    $table->string('tipo_dato', 20)->default('string'); // 'string'|'int'|'decimal'|'bool'|'date'|'time'|'datetime'|'json'
    $table->tinyInteger('activo')->default(1);
    $table->bigInteger('created_by_id')->nullable()->index();
    $table->bigInteger('updated_by_id')->nullable()->index();
    $table->bigInteger('deleted_by_id')->nullable()->index();
    $table->timestamps();
    $table->softDeletes();
});
```

**Regla dura: `valor` siempre es `varchar`, nunca un tipo tipado.** La tabla
guarda un solo parámetro por fila, y distintos parámetros tienen tipos de
dato distintos (un número como `3.6`, una hora como `08:00:00`, un booleano,
un JSON de credenciales) — una sola columna no puede ser `decimal` para unos
y `time` para otros. Se persiste como string y **cada proceso que lo
consume** es responsable de convertirlo al tipo que necesita, guiado por la
columna `tipo_dato` (que documenta la intención, no que la aplica la BD):

```php
// Leer y castear en el punto de consumo — no en un lugar centralizado,
// porque cada proceso conoce el tipo real que espera para SU parámetro.
$valorDolar = (float) Mdt_configuracion_sistema::where('codigo', 'valor_dolar')->value('valor');

$horaCorte = Mdt_configuracion_sistema::where('codigo', 'hora_corte_caja')->value('valor'); // '08:00:00'
$horaCorte = \Carbon\Carbon::createFromFormat('H:i:s', $horaCorte);
```

- `codigo` es el identificador estable que usa el código PHP (como el
  `codigo` de una tabla catálogo) — nunca se traduce ni se muestra tal cual
  al usuario final, para eso está `descripcion`.
- `grupo` permite que el panel admin agrupe parámetros relacionados en el
  mismo formulario (ej. todas las credenciales de una integración externa
  bajo `grupo = 'integraciones'`) sin necesitar una tabla de grupos aparte.
- No lleva `catalogo_id` ni relación con `{prefijo}_catalogo_det` — son dos
  patrones distintos: `catalogo_det` son **listas** de valores relacionados
  (monedas, métodos de pago); `configuracion_sistema` son **parámetros
  sueltos** sin relación entre sí, uno por fila.

---

## Conexión, migraciones centralizadas y seeders

Esta nota cubre el **diseño de las tablas** (arriba). Todo lo de arranque de proyecto — nombre de la conexión Eloquent (`db{prefijo}`, nunca `mysql_db{prefijo}`), las conexiones fijas `dbsiaw`/`dbsincro` que trae todo proyecto nuevo, el ledger de migraciones centralizado en `dbsincro`, y los seeders idempotentes vía `seeders_log` — vive en [[Conexiones, Migraciones y Rutas]], para no repetirlo (y desincronizarlo) en dos notas.
