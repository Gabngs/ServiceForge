# Prompt para Claude Code: dataset ampliado de estructura de backends Laravel

> **Cómo usarlo:** en la otra PC, abrir Claude Code en la raíz de ServiceForge y escribir:
> `Lee docs/dataset/prompt-generar-dataset.md y ejecútalo.`
> Todo lo que está debajo de la línea es el prompt.

---

## Rol y objetivo

Vas a construir un **dataset ampliado para entrenar el modelo de matching de ServiceForge**. Ese modelo es la red neuronal de `src/generador/match_learner.py` (`MLPClassifier`).

Hoy el modelo solo aprende a relacionar **Model ↔ Resource**. El objetivo es que aprenda a reconocer el **rol** de cada archivo de un backend Laravel respecto de un modelo (Filter, Resource, RelationResource, Base/Store/Update Request, trait de validación, Service, Controller, archivo de rutas). Tiene que reconocerlo aunque cada proyecto use **carpetas, singular/plural, prefijos, sufijos y estilos de nombre distintos**.
Con eso, el generador podrá ubicar y nombrar los archivos nuevos dentro de la estructura propia de cada proyecto.

Las variaciones entre proyectos **no son ruido**: son la señal de entrenamiento. Un dataset con un solo estilo no sirve.

Entregables:

1. un dataset de pares **(modelo → archivo, rol, etiqueta)** a partir de:
   - los **6 repos backend reales** de esta PC;
   - los anexos YAML de SIAW y SIREH;
   - **como mínimo 20 repos sintéticos** que varíen las convenciones (la meta razonable es 30);
2. el dataset **guardado y documentado para presentarlo**: dataset card, estadísticas y métricas;
3. los scripts que lo generan, para poder reproducirlo.

---

## Contexto que tenés que leer primero (en este orden)

1. `docs/dataset/correcciones-generador.md`, sobre todo **§0** (detectar la estructura y aplicar el patrón) y **§8** (tipos de archivo, qué se infiere, features candidatas y ruido a ignorar).
2. `docs/dataset/estructura-siaw.md` y `docs/dataset/estructura-sireh.md`: árbol de carpetas, convenciones, casos fuera de patrón y el **anexo YAML** con el mapeo real de 91 y 124 modelos. Esos repos **pueden no estar en esta PC**; en ese caso, los anexos son la fuente.
3. El código actual del matching:
   - `scripts/build_match_dataset.py`: cómo se arma hoy el dataset y cómo se infiere el ground truth;
   - `src/generador/model_resource_scan.py`: `scan_models`, `scan_resources`, `build_features`;
   - `src/generador/match_learner.py`: `FEATURE_NAMES`, `MatchLearner`, `bundled_pretrained_path`;
   - `src/generador/_match_dataset.json`: el dataset actual, con las features `name_similarity` y `field_jaccard`, 215 modelos de 2 proyectos.
4. **`git status` y `git diff`** del repo. En esta PC hay **cambios sin commitear relacionados con el entrenamiento de la red**. Léelos antes de tocar nada: el trabajo nuevo tiene que **construirse sobre esos cambios**, sin pisarlos ni revertirlos. Si algo de lo que sigue choca con ellos, detente y pregunta.

---

## Paso 1: inventario de repos reales

- Pregúntale al usuario las rutas de los **6 repos backend** si no las encontrás. Busca carpetas hermanas con `artisan` + `app/` + `composer.json` con `laravel/framework`.
- Para cada repo, registra en un manifiesto:
  - nombre y ruta;
  - commit (`git rev-parse --short HEAD`);
  - versión de Laravel y de PHP (`composer.json`);
  - conexiones de `config/database.php`;
  - cantidad de modelos.
- **No modifiques los repos backend.** Son solo de lectura.

## Paso 2: extraer el mapeo real (ground truth)

Para cada repo real, genera el mismo mapeo por modelo que tienen los anexos YAML:

- `path`, `connection`, `table`, `pk`, `soft_delete`, `has_factory`, `auditoria`, `relaciones`;
- `filter`, `resources`, `requests`, `service`, `controller`, `routes`;
- y las entradas `*_usado_en`, que son candidatas a **negativos duros**.

Criterios de asignación de dueño (ver §8.4 de correcciones):

1. primero el nombre normalizado: sin prefijos de tabla (`catalogo_`, `sip_`, …), sin sufijo de rol, sin prefijo de acción (`Store`/`Update`/`Base`), sin `_`, en minúsculas;
2. después `$default_filters` y la carpeta `/{tabla}/`;
3. el `use` del modelo, solo como señal secundaria.

Ignora las carpetas sin `.php`, que son restos de generaciones anteriores.

Guarda un YAML por repo en `datasets/structure/real/{repo}.yaml`, con el mismo formato que los anexos.
Para SIAW y SIREH, si los repos están en esta PC, **re-escanéalos** y compara con el anexo: las diferencias son cambios hechos desde el 23-09-2026. Si no están, usa el anexo tal cual.

> Nota: el scanner que produjo los anexos era un script temporal que no quedó en el repo. Escríbelo de nuevo como `scripts/scan_backend_structure.py`. La descripción de cómo se armó cada campo está en la sección "Anexo" de los .md de estructura.

## Paso 3: perfil de variaciones

Con los 6 repos reales, arma un **perfil de variaciones**: una tabla por eje, con los valores observados y su frecuencia. Guárdalo en `datasets/structure/variation_profile.json`.

Ejes mínimos, con los valores ya conocidos de SIAW y SIREH:

| Eje | Valores observados |
|---|---|
| Carpeta de Requests | `Http/Request`, `Http/Requests` |
| Sub-nivel | nombre de conexión (`dbsiaw`, `dbsip`), nombre de sistema (`Sip`, `Siaw`, `Sincro_sip`), ninguno |
| Carpeta por tabla en Requests / Resources | sí / no |
| Traits de validación | `Traits/{tabla}/Validates{X}`, `Traits/Validates{X}` plano, ninguno |
| Nombre del Service | `{tabla}Service`, `{CamelSinPrefijo}Service`, `Catalogo{Camel}Service`, sin sufijo |
| Nombre del Request | `Store{tabla}Request`, `Store{Camel}Request`, sin sufijo `Request` |
| Base Request | clase `Base…` abstracta / sin base |
| Sufijo de Resource mínimo | `Relation`, `Relacion`, `Tiny`, `Left`, `Data`, `Show` |
| Rutas | `routes/{tabla}.php`, `routes/modules/{tabla}.php`, en línea en `api.php`, nombre de área (`tardanzas.php`) |
| Registro de rutas | `RouteServiceProvider`, `require` en `api.php`, `bootstrap/app.php` (Laravel 11+) |
| Controllers | `Api/{sub}/`, raíz de `Api/`, `Api/V1/` |
| Middleware de token | `[ApiToken::class]`, `'ApiToken'` |
| Relación de auditoría | `created_by`, `create_by`, `createdBy`, ausente |
| Modelo de usuario | `User`, `catalogo_usuario`, `usuarios` |
| Soft delete | `deleted_at`, `deleted` (`DELETED_AT`), ninguno |
| PK | `id` uuid string, `pkid` int, `pkid` + `id`, natural (`code`, `codper`) |
| Estilo de nombre de clase | snake literal de tabla, StudlyCase, mixto |

Suma todo eje nuevo que aparezca en los otros 4 repos.

## Paso 4: repos sintéticos (mínimo 20, meta 30)

Escribe `scripts/generate_synthetic_repos.py`. Debe generar **esqueletos de proyectos Laravel en disco**, con archivos `.php` mínimos pero sintácticamente plausibles, para que los **mismos scanners** que se usan con los repos reales funcionen sin cambios sobre ellos.

Requisitos:

- **Semilla fija** (`--seed`) y `--count N`: el dataset tiene que ser reproducible.
- **Muestreo de ejes:** cada repo sintético toma un valor por eje del perfil del Paso 3. Muestrea con las frecuencias reales, pero **garantiza cobertura**: cada valor de cada eje aparece en al menos 2 repos.
- **Estilos fuera del conjunto real**, para que el modelo generalice y no memorice los 6 repos. Al menos 5 repos deben usar alguno de estos:
  - estructura modular tipo `nwidart/laravel-modules`: `Modules/{Modulo}/App/Http/...`;
  - DDD: `app/Domain/{Modulo}/...`;
  - Controllers versionados: `Api/V1`;
  - nombres en inglés;
  - rutas en `routes/api/{modulo}.php`;
  - Laravel 11 con `bootstrap/app.php`.
- **Vocabulario de tablas:**
  - mezcla nombres de los repos reales (reusa los de los anexos) con dominios nuevos: inventario, ventas, clínica, colegio, logística, RRHH, contabilidad;
  - usa prefijos por sistema (`inv_`, `vta_`, `cli_`, …) y también tablas sin prefijo;
  - entre 15 y 60 modelos por repo.
- **Ruido realista**, en proporciones parecidas a las reales:
  - archivos legados en otra carpeta (como los 19 controllers en la raíz de `Api/` de SIAW);
  - grafías inconsistentes (`Relacion`/`Relation`, `StorecatalogX`);
  - Services que agrupan varios modelos;
  - controllers de reportes que importan 10 modelos;
  - carpetas vacías;
  - un modelo sin Resource, o sin Service.
- **Ground truth por construcción:** cada repo sintético escribe su `manifest.yaml`, con el mismo formato que los anexos, más la lista de ejes elegidos. La etiqueta sale del manifiesto, no de una heurística.
- **Relaciones y columnas:** genera `belongsTo` entre modelos del mismo repo y **migraciones** en `database/migrations/`. Así `_load_table_columns` y `field_jaccard` tienen datos, igual que en los repos reales.
- Salida en `datasets/structure/synthetic/repo_{NN}/`.

## Paso 5 (opcional, pregunta antes): datos públicos

Busca en línea datasets o repos públicos que sirvan como **más variación real**:

- repos Laravel de API en GitHub con licencia **MIT o Apache-2.0**, con al menos 20 modelos y estructura CRUD (Resources + Requests + Controllers);
- datasets de código ya publicados (por ejemplo, subconjuntos PHP de Hugging Face). Revisa los términos de uso antes de usarlos.

Reglas:

- **Antes de descargar nada, muéstrale al usuario la lista de candidatos** (URL, licencia, tamaño, por qué sirve) y espera su OK.
- Clona con `--depth 1` fuera del repo de ServiceForge (por ejemplo `../datasets-externos/`).
- Registra URL, commit y licencia en el manifiesto.
- En el dataset guarda **solo lo derivado** (rutas, nombres de clase, features, etiquetas), nunca el código fuente de terceros.
- Si no hay nada que valga la pena, sigue sin este paso: no es bloqueante.

## Paso 6: construir el dataset de entrenamiento

Escribe `scripts/build_structure_dataset.py`. Toma los repos reales, los sintéticos y los externos (si hay) y produce:

- **Filas:** `(repo, origen[real|sintetico|externo], modelo, rol, candidato_path, label, features...)`.
  - Positivos: los archivos del manifiesto.
  - Negativos duros: archivos del mismo rol de otros modelos del mismo repo, ordenados por similitud, máximo 3 a 5 por modelo; también las entradas `*_usado_en`.
- **Roles:** `filter`, `resource`, `relation_resource`, `base_request`, `store_request`, `update_request`, `request_trait`, `service`, `controller`, `route`.
- **Features:**
  - las dos actuales (`name_similarity`, `field_jaccard`), calculadas igual que hoy;
  - las candidatas de §8.3 de correcciones:
    - similitud de nombre normalizada;
    - coincidencia del modelo con un segmento de la ruta;
    - el archivo importa el modelo;
    - `$default_filters`;
    - la ruta importa el controller;
    - el candidato está en la carpeta dominante del proyecto para ese rol (el **perfil de estructura**, calculado sin mirar la etiqueta);
  - el rol, como one-hot.
- **Compatibilidad:** el subconjunto `rol == resource` con solo las dos features actuales tiene que poder exportarse en el formato exacto de `_match_dataset.json` (`X`, `y`, `feature_names`, `stats`). Así el modelo actual se puede reentrenar sin cambios de código.

Formato de salida en `datasets/structure/`:

```
datasets/structure/
├── README.md                    ← dataset card (ver Paso 8)
├── variation_profile.json
├── real/{repo}.yaml
├── synthetic/repo_{NN}/...      ← esqueletos + manifest.yaml
├── pairs.parquet  y  pairs.csv  ← todas las filas
├── splits.json                  ← qué repo va a train / val / test
├── match_dataset_resource.json  ← subconjunto compatible con _match_dataset.json
└── stats/                       ← tablas y gráficos de distribución
```

## Paso 7: entrenamiento y evaluación honesta

- **Split por repo, no por fila.** Ningún repo aporta filas a dos splits a la vez.
  - El **test** tiene que tener al menos **2 repos reales no vistos**.
  - Si hay pocos, usa leave-one-real-repo-out.
  - Los sintéticos van solo a train/val.

  Evaluar sobre sintéticos infla las métricas: el modelo aprendería el generador, no los proyectos.
- **Compara:**
  1. la heurística actual (`_heuristic_score`);
  2. el modelo de fábrica actual;
  3. el modelo nuevo, entrenado solo con reales;
  4. el modelo nuevo, entrenado con reales + sintéticos (+ externos).
- **Métricas por rol:** precision, recall, F1, y **top-1 accuracy por modelo** (¿el candidato mejor puntuado es el correcto?).
- Si (4) no mejora a (3) en los repos reales de test, dilo tal cual y propón qué ajustar: proporción de sintéticos, ejes, ruido. No presentes números del conjunto sintético como resultado principal.
- **No sobrescribas** `src/generador/_match_dataset.json` ni `src/generador/model_resource_matcher_pretrained.joblib`.
  - `scripts/build_match_dataset.py` hoy los sobrescribe: no lo corras tal cual.
  - Guarda los modelos nuevos en `datasets/structure/models/`, con fecha y versión en el nombre.
  - Reemplazar el modelo de fábrica es una decisión del usuario: pregunta.

## Paso 8: dejarlo presentable

`datasets/structure/README.md` (dataset card) debe tener:

- **Propósito:** reconocer el rol de archivos Laravel en estructuras heterogéneas.
- **Fuentes:**
  - los 6 repos reales, con commit y sin exponer código;
  - N repos sintéticos, con semilla y parámetros;
  - los externos, con licencia.
- **Proceso:**
  - cómo se asigna el ground truth en reales y en sintéticos;
  - cómo se eligen los negativos;
  - la lista de features.
- **Estadísticas:**
  - filas por rol, por origen y por split;
  - balance positivos/negativos;
  - distribución de cada eje de variación;
  - un par de gráficos en `stats/`.
- **Resultados** del Paso 7, en tabla y con el test **sobre repos reales**.
- **Limitaciones:**
  - los sintéticos son esqueletos, sin lógica de negocio;
  - pocos repos reales;
  - posibles sesgos de dominio (catálogos en español).
- **Cómo regenerarlo:** los comandos exactos, con semilla.
- **Metadatos:** fecha en formato `dd-mm-aaaa HH:mm:ss` y la versión de ServiceForge (`generador.__version__`).

Si el usuario quiere presentarlo como página, ofrécelo al final. No lo publiques sin que lo pida.

---

## Reglas generales

- **No hagas commit** sin que el usuario lo pida. Cuando lo pida, **no agregues líneas `Co-Authored-By`** ni atribución de IA (regla del `CLAUDE.md` de este repo).
- No modifiques los repos backend reales.
- No cambies el comportamiento de la app (`gui.py`, `generator.py`) en esta tarea. Es solo dataset, scripts y entrenamiento offline.
- Agrega `datasets/structure/synthetic/` y `../datasets-externos/` al `.gitignore` si pesan mucho, y pregunta antes. El README, el perfil, los manifiestos y `pairs.*` sí se versionan.
- **Detente y pregunta** en estos casos:
  - antes de descargar datos externos;
  - antes de reemplazar el modelo de fábrica;
  - si un cambio choca con el trabajo sin commitear;
  - si encontrás menos de 6 repos reales.
- **Al terminar, reporta:**
  - cuántos repos reales, sintéticos y externos entraron;
  - filas por rol;
  - la tabla comparativa de métricas en test real;
  - qué quedó pendiente.
