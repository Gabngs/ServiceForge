# Dataset de estructura de backends Laravel

> **Generado:** 24-09-2026 00:15:51 · **ServiceForge:** `2.0.1-1-g079fb73-dirty` · **Versión del dataset:** v1

Dataset para entrenar y evaluar el modelo que reconoce el **rol** de cada archivo de un backend Laravel respecto de un modelo Eloquent (Filter, Resource, Resource mínimo, Requests, trait de validación, Service, Controller, archivo de rutas). Es la ampliación del dataset actual de ServiceForge, que solo relacionaba **Model ↔ Resource**.

---

## 1. Propósito

ServiceForge genera código para un proyecto Laravel que ya existe. Cada proyecto guarda sus archivos con convenciones propias: carpetas (`Http/Request` o `Http/Requests`), singular o plural, prefijos de tabla, sufijos de rol, sub-niveles por conexión o por sistema. Un generador que asume una estructura fija duplica o pisa lo que el proyecto ya tiene.

Este dataset enseña a un modelo a decidir: **dado un modelo y un archivo candidato, ¿ese archivo es el `{rol}` de ese modelo?** Con eso el generador puede ubicar lo que ya existe y proponer dónde y con qué nombre crear lo que falta, dentro de la estructura del propio proyecto.

> **Las variaciones entre proyectos no son ruido: son la señal de entrenamiento.** Un dataset con un solo estilo aprende ese estilo y no generaliza.

Encaja con el estándar así: el estándar describe cómo se construye un proyecto **nuevo**; sobre un proyecto **existente** el generador no impone esa estructura, la detecta y la respeta.

---

## 2. Fuentes

### 2.1 Repos reales (5), solo lectura

| Repo | Commit | Rama | Laravel / PHP | Modelos | Cambios sin commitear al escanear |
|---|---|---|---|---:|---:|
| `siaw-laravel-backend` | `dfa8268` | production | ^12.0 / ^8.2 | 88 | 0 |
| `sip-laravel-backend` (SIREH) | `954baeef` | production | ^10.10 / ^8.1 | 122 | 0 |
| `gsp-back` | `c4de8dc` | dev | ^12.0 / ^8.2 | 108 | 4 archivos |
| `AgencyWeb-Back` | `e93fa23` | dev | ^12.0 / ^8.2 | 45 | 0 |
| `Peru_Lex_Back` | `c165eef` | dev | ^12.0 / ^8.2 | 26 | 2 archivos |

El dataset guarda **solo lo derivado** (rutas relativas, nombres de clase, features y etiquetas). No contiene código fuente de los repos.
Conexiones, versiones y cantidad de archivos por rol de cada repo: [`repos_manifest.json`](repos_manifest.json).

**Diferencia con los anexos previos:** SIAW y SIREH ya tenían un anexo YAML escrito a mano (commits `3edf818` y `08af16ce`). Se reprodujo cada repo en ese commit exacto y se escaneó con el scanner nuevo: los conteos de modelos coinciden (91 y 124). Desde entonces cambiaron: SIAW pasó a 88 modelos y SIREH a 122.

### 2.2 Repos sintéticos (30)

Esqueletos generados por código, con semilla fija, **borrados después de extraer las features** (ver §7): son reproducibles, no se guardan.

| Parámetro | Valor |
|---|---|
| Generador | `scripts/generate_synthetic_repos.py` (v1.0) |
| Semilla / cantidad | `20260923` / 30 |
| Modelos por repo | 15 a 60 (total 1131) |
| Ejes de variación | 23, con **cobertura garantizada**: cada valor de cada eje aparece en al menos 2 repos |
| Ejes elegidos por repo | [`synthetic_index.json`](synthetic_index.json) |

Cubren estilos que ningún repo real usa: estructura modular (`Modules/{X}/App/...`), DDD (`app/Domain/{X}/...`), controllers `Api/V1`, nombres en inglés, rutas `routes/api/{modulo}.php`, archivos con nombre en singular sobre tablas en plural, entre otros (gráfico 05).
Incluyen ruido realista: controllers legados en otra carpeta, grafías inconsistentes (`Relation`/`Relacion`), Services que atienden 2 o 3 modelos, controllers de reportes que importan de 6 a 10 modelos, carpetas vacías, modelos sin Resource o sin Service.

### 2.3 Datos públicos externos

**No se usaron.** Con 5 repos reales y 30 sintéticos hay variación suficiente y se evita mezclar licencias.

---

## 3. Cómo se armó: ground truth y negativos

### 3.1 Clasificación por rol

Cada `.php` se clasifica por **segmentos de ruta y nombre de clase**, no por carpetas fijas. Así el mismo scanner funciona con `Request` o `Requests`, `Modules/X/App/...`, DDD, etc. Roles del dataset: `filter`, `resource`, `relation_resource`, `base_request`, `store_request`, `update_request`, `request_trait`, `service`, `controller`, `route`. Las carpetas sin `.php` se ignoran.

### 3.2 Ground truth en repos reales: de quién es cada archivo

No hay etiquetas hechas a mano: el dueño de cada archivo se **infiere con una jerarquía de criterios explícita**, y el criterio queda registrado en cada fila (`via`). De más a menos fuerte:

| Criterio (`via`) | Qué significa | Positivos |
|---|---|---:|
| `declared` | el modelo lo declara (`$default_filters`) | 183 |
| `name_exact_full` | nombre normalizado **idéntico**, con prefijo de tabla | 1263 |
| `name_prefix_full` | el nombre del archivo empieza por el del modelo (prefijo más largo gana) | 148 |
| `name_exact` | idéntico sin el prefijo de tabla (`SolicitudVacacionesService` ↔ `sip_solicitudvacaciones`) | 101 |
| `name_stem` | idéntico salvo singular/plural | 21 |
| `name_prefix` | prefijo, sin el prefijo de tabla | 20 |
| `folder` | vive en una carpeta `{tabla}/` | 11 |
| `route_controller` | (rutas) importa un controller que es del modelo | 167 |
| `import_single` | importa un solo modelo **y** hay algo de parecido de nombre (señal secundaria) | 11 |

*Nombre normalizado* = minúsculas, sin `_`, sin prefijo de tabla (`sip_`, `catalogo_`; se derivan del propio repo), sin sufijo de rol (`Service`, `Request`...) y sin prefijo de acción (`Store`, `Update`, `Base`).
Un archivo que importa un modelo pero no es suyo (un reporte que importa diez modelos) **no** es positivo: queda como negativo `usado_en`.

**Validación del scanner contra los anexos previos** (repos en el commit del anexo; acuerdo entre dos criterios distintos, *no* exactitud): SIAW y SIREH coinciden en la lista de modelos, y el acuerdo por campo va de 0.55 a 1.00 en precisión y de 0.60 a 1.00 en recall. La mayor parte de la diferencia es que el anexo asignaba por prefijo simple un archivo a varios modelos, mientras el scanner nuevo prefiere el nombre exacto. Detalle en [`docs/dataset/correcciones-generador.md` §8](../../docs/dataset/correcciones-generador.md).

### 3.3 Ground truth en repos sintéticos: por construcción

Cada repo escribe su `manifest.yaml` con los archivos que **efectivamente creó** para cada modelo y rol. La etiqueta no sale de ninguna heurística de nombres.
Control de calidad: los mismos scanners de los repos reales clasificaron **10 149 de 10 149** archivos del manifiesto en el rol esperado (0 discrepancias). Ese control encontró dos defectos que se corrigieron antes de construir el dataset.

### 3.4 Filas y negativos

Cada fila es un par `(modelo, archivo candidato del mismo rol)`. Solo se generan filas de un `(modelo, rol)` si el modelo **tiene al menos un positivo** en ese rol: si no lo tuviera, no se distingue "no existe" de "existe y el scanner no lo vio".

| Tipo | Cómo se elige |
|---|---|
| **Positivo** | archivo listado por el ground truth para ese `(modelo, rol)` |
| **Negativo duro** | los 4 archivos del **mismo rol de otros modelos** más parecidos por nombre normalizado. Es lo que más cuesta distinguir |
| **Negativo `usado_en`** | archivos que importan el modelo pero no son suyos |
| **Negativo fácil** | 1 archivo del mismo rol al azar (semilla fija). Sin él el modelo nunca vería un "esto claramente no es" y sus probabilidades saldrían mal calibradas |

### 3.5 Features (25)

Las 4 primeras son las del modelo de fábrica actual y se calculan igual; el resto son nuevas. Las de señal directa son las que se quitan en la variante "soft" de la evaluación.

| Feature | Qué mide |
|---|---|
| `name_similarity` | similitud de texto entre el nombre del archivo y la tabla/módulo (legada) |
| `field_jaccard` | solapamiento entre columnas del modelo (migraciones, `$fillable`, `$casts`) y las keys de `toArray()`/`rules()`/filtros (legada) |
| `mixin_match` | el docblock declara `@mixin` al modelo (legada) |
| `same_namespace` | mismo sub-nivel de negocio entre modelo y archivo (legada) |
| `name_sim_norm` | similitud difusa de nombres **normalizados** |
| `name_contains` | un nombre normalizado contiene al otro (singular/plural, variantes) |
| `path_segment_match` ★ | alguna carpeta del archivo coincide con el nombre del modelo (`{tabla}/`) |
| `imports_model` ★ | el archivo importa (`use`) la clase del modelo |
| `declared_by_model` ★ | el modelo declara al archivo (`$default_filters`) |
| `route_names_controller` ★ | (rutas) el archivo referencia un controller que se llama como el modelo |
| `dominant_root` | el archivo está en la carpeta raíz más frecuente del proyecto para ese rol (**perfil de estructura**, calculado sin mirar etiquetas) |
| `subfolder_share` | fracción de los archivos de ese rol que comparten el sub-nivel del candidato |
| `has_columns`, `has_keys` | presencia de columnas conocidas / keys, para interpretar un solape 0 |
| `import_breadth` | cuántos modelos distintos importa el archivo (alto = archivo compartido) |
| `role_*` (10) | rol, en one-hot |

★ = **señal directa**: coincide con el criterio con el que se etiquetan los repos reales.

---

## 4. Estadísticas

**72 179 filas**: 12 074 positivas (16.7 %) y 60 105 negativas.

| Origen | Filas | Repos |
|---|---:|---:|
| Real | 11 759 | 5 |
| Sintético | 60 420 | 30 |

| Rol | Filas |
|---|---:|
| controller | 9321 |
| resource | 8140 |
| filter | 7819 |
| store_request | 7688 |
| update_request | 7671 |
| route | 7503 |
| service | 7262 |
| relation_resource | 6888 |
| request_trait | 5930 |
| base_request | 3957 |

Splits **por repo, nunca por fila**: los 5 reales van como *fold* de prueba (uno cada vez), 24 sintéticos entrenan y 6 sintéticos validan. Ver [`splits.json`](splits.json).

**Gráficos** (8 PNG: filas por rol y origen, balance de clases, criterio del ground truth, filas por repo, ejes real vs. sintético, separación de features, resultados por rol y resultado completo vs. sin nombre exacto). No se versionan: se regeneran con `python scripts/make_dataset_stats.py` desde `pairs.parquet` y `stats/results.json`. Tablas CSV en `stats/tables/`.

Perfil de variaciones de los 5 repos reales (23 ejes, con los repos que usa cada valor): [`variation_profile.json`](variation_profile.json). Ejemplos: `Requests` en 4 de 5 repos y `Request` en 1; el sub-nivel es nombre de conexión en 2, nombre de sistema en 2 y ninguno en 1; el Service se llama `{ClaseModelo}Service` en 3, `{tabla}Service` en 1 y `{CamelSinPrefijo}Service` en 1.

---

## 5. Resultados

Protocolo: **leave-one-real-repo-out**. En cada uno de los 5 folds se prueba en **un repo real que el modelo no vio** y se entrena con los otros 4 (más, según la variante, los sintéticos de entrenamiento). La prueba usa **todos los candidatos del rol**, no solo la muestra de negativos. *Top-1* = el candidato mejor puntuado es de ese modelo. Modelos nuevos: promedio de 3 semillas.

| Modelo | siaw | sip | gsp | agency | perulex | **Promedio** |
|---|---:|---:|---:|---:|---:|---:|
| 1. Heurística actual | 0.873 | 0.758 | 0.906 | 1.000 | 0.964 | **0.900** |
| 2. Modelo de fábrica actual ¹ | 0.924 | 0.809 | 0.904 | 1.000 | 0.988 | **0.925** |
| 3. Nuevo, solo repos reales | 0.985 | 0.967 | 0.978 | 0.999 | 0.972 | **0.980** |
| 4. Nuevo, reales + sintéticos | 0.979 | 0.932 | 0.974 | 0.999 | 0.974 | **0.972** |
| 3s. (3) sin features de señal directa | 0.934 | 0.816 | 0.874 | 1.000 | 0.982 | **0.921** |
| 4s. (4) sin features de señal directa | 0.926 | 0.793 | 0.875 | 1.000 | 0.976 | **0.914** |

¹ Se entrenó con estos mismos 5 repos: **no es un modelo held-out** en este experimento. Se muestra como referencia, no como rival justo.

Solo en los grupos **sin nombre exacto** (los `(modelo, rol)` cuyo dueño se decidió por prefijo, carpeta, `$default_filters` o el controller de la ruta, donde una regla de nombres no alcanza):

| Modelo | siaw | sip | gsp | agency | perulex | **Promedio** |
|---|---:|---:|---:|---:|---:|---:|
| 1. Heurística actual | 0.590 | 0.403 | 0.723 | 1.000 | 0.667 | **0.677** |
| 2. Fábrica ¹ | 0.663 | 0.448 | 0.698 | 1.000 | 0.667 | **0.695** |
| 3. Nuevo, solo reales | 0.928 | 0.903 | 0.983 | 0.996 | 0.593 | **0.881** |
| 4. Nuevo, reales + sintéticos | 0.924 | 0.811 | 0.962 | 0.996 | 0.519 | **0.842** |
| 3s. (3) sin señal directa | 0.687 | 0.470 | 0.648 | 1.000 | 0.444 | **0.650** |
| 4s. (4) sin señal directa | 0.651 | 0.425 | 0.629 | 1.000 | 0.444 | **0.630** |

Grupos de este subconjunto por fold: 83, 134, 159, 84 y **9** (Peru_Lex: muy pocos, poco confiable).

Detalle por rol, precision/recall/F1 y diagnóstico: [`stats/results.md`](stats/results.md) (gráficos 07 y 08).

### Cómo leer estos números, sin adornar

1. **El modelo nuevo entrenado con repos reales mejora al actual**: 0.980 frente a 0.900 (heurística) y 0.925 (fábrica, que además vio estos repos). En los grupos sin nombre exacto, de 0.68 a 0.88.
2. **Agregar los repos sintéticos NO mejoró el resultado en repos reales**: (4) rinde 0.972, un poco *peor* que (3) con 0.980, y en el subconjunto difícil 0.842 frente a 0.881. Las métricas altas sobre los sintéticos (top-1 0.995) **no cuentan como resultado**: evaluar sobre ellos mide al generador, no a los proyectos.
3. **Buena parte de la mejora viene de las features de señal directa.** Sin ellas (3s, 4s) el modelo queda en 0.92 y 0.91, en el nivel del modelo de fábrica, y en el subconjunto difícil en 0.65. Esas features (importar el modelo, `$default_filters`, carpeta `{tabla}/`, el controller de la ruta) **son el mismo criterio con el que se etiquetan los repos reales**: para los positivos `declared` y `route_controller` la coincidencia es por definición. Por eso el resultado mide sobre todo *acuerdo con las reglas del scanner*, no exactitud frente a una verdad verificada a mano.
4. **La mejora más grande está en `route`** (0.67 → 0.95) y en `controller`, dos roles que el modelo actual nunca cubrió; en `resource`, el rol para el que fue entrenado, ya rendía 0.97 a 0.99 y no cambia.
5. **AgencyWeb da 1.000 con cualquier modelo**: sus archivos siguen el nombre exacto, es el caso trivial.

---

## 6. Limitaciones

- **Etiquetas inferidas, no verificadas a mano.** El 65 % de los positivos reales se decide por igualdad exacta de nombre y otro ~19 % por señales que el modelo también ve como feature (punto 3 arriba). Una muestra revisada a mano por una persona del equipo daría una medida independiente.
- **Solo 5 repos reales, y de la misma familia.** SIAW, SIREH, GSP y AgencyWeb comparten autor y convenciones (`ApiToken`, `AbstractModuleService`, etc.): que un repo sea "no visto" no lo hace independiente. Todos son en español, Laravel clásico y con catálogos de negocio (sesgo de dominio).
- **Los sintéticos son esqueletos** sin lógica de negocio. Sus nombres son más regulares que los reales, porque salen de reglas del generador; eso probablemente explica por qué no ayudan.
- **Los sintéticos son el 84 % de las filas.** Pueden desplazar al modelo hacia su regularidad.
- **Escaneo por regex, no un parser PHP.** Falla con `toArray()` armado con `array_merge`, campos dinámicos o clases con varios modelos; los falsos negativos bajan features, no inventan matches.
- **Solo evalúa emparejar archivos existentes.** Todavía no evalúa la propuesta de *carpeta y nombre* de un archivo nuevo.

**Estado del modelo:** el modelo `real_only` **ya está integrado a la app** (§9). Cada punto de abajo es una mejora futura del dataset, no un requisito para usarlo:
1. Pesar o limitar los sintéticos (por ejemplo 1:1 con los reales) y volver a comparar (3) y (4).
2. Hacer que el generador produzca nombres **irregulares**: abreviaturas, plurales inconsistentes, archivos cuyo nombre no contiene el del modelo, para que las etiquetas dejen de ser derivables por nombre.
3. Agregar más repos reales, de otra familia, y revisar a mano una muestra de etiquetas.
4. Revisar `route` y `controller` con una etiqueta independiente de "la ruta importa el controller".

---

## 7. Cómo regenerarlo

Requiere Python con `pip install -r requirements-dataset.txt` (solo el pipeline offline; la app y el `.exe` no lo necesitan) y los repos reales como carpetas hermanas.

```bash
# 1. Ground truth de cada repo real (solo lectura) y manifiesto de repos
for r in siaw-laravel-backend sip-laravel-backend gsp-back AgencyWeb-Back Peru_Lex_Back; do
  python scripts/scan_backend_structure.py --repo ../$r --out-dir datasets/structure/real
done
# 2. Perfil de variaciones de los repos reales
python scripts/build_variation_profile.py
# 3. Repos sintéticos (semilla fija => mismos repos)
python scripts/generate_synthetic_repos.py --count 30 --seed 20260923
# 4. Dataset. Al terminar BORRA los esqueletos sintéticos (--keep-synthetic para conservarlos)
python scripts/build_structure_dataset.py
# 5. Entrenamiento y evaluación (leave-one-real-repo-out, 3 semillas)
python scripts/train_structure_models.py --seeds 3
# 6. Gráficos y tablas
python scripts/make_dataset_stats.py
```

Validar el scanner contra un anexo: `python scripts/scan_backend_structure.py --repo <ruta> --compare-annex docs/dataset/estructura-siaw.md`.

## 8. Contenido de esta carpeta

| Archivo | Qué es |
|---|---|
| `pairs.parquet` | las 72 179 filas con features y etiqueta (`--csv` genera además `pairs.csv`, 23 MB) |
| `splits.json` | qué repo va a prueba, entrenamiento o validación |
| `real/{repo}.yaml` | ground truth de cada repo real (formato de los anexos + `roles` con el criterio) |
| `variation_profile.json` | ejes de variación y frecuencias en los repos reales |
| `synthetic_index.json` | semilla y ejes elegidos de cada repo sintético |
| `repos_manifest.json` | commit, versiones y conexiones de los repos reales |
| `match_dataset_resource.json` | subconjunto `resource` con las 4 features legadas, en el formato exacto de `src/generador/_match_dataset.json` |
| `models/` | modelos entrenados (Pipeline con escalador), con versión y fecha en el nombre. El de `real_only` es el que se empaqueta con la app (§9) |
| `stats/` | resultados (`results.md/json`), resumen y tablas CSV (los PNG se regeneran) |

`src/generador/_match_dataset.json` y `src/generador/model_resource_matcher_pretrained.joblib` **no fueron modificados**: el modelo anterior queda como estaba, solo que la app ya no lo usa.

---

## 9. Uso en la app

ServiceForge usa este modelo para reconocer lo que **ya existe** en el proyecto backend antes de generar, en vez del modelo anterior (que solo emparejaba Model ↔ Resource con 4 features).

| Pieza | Dónde |
|---|---|
| Escáner y features (un solo código para entrenar y para usar) | `src/generador/structure_scan.py` |
| Aprendiz (`StructureLearner`, 25 features, escalador propio) | `src/generador/match_learner.py` |
| Modelo empaquetado, variante `real_only` | `src/generador/structure_matcher_pretrained.joblib` (lo incluye `generador.spec`) |
| Cómo se empaqueta | `python scripts/export_structure_model.py` (la variante se elige con `--variant`) |

Qué cambia para el desarrollador: al analizar una tabla, los Resources existentes se puntúan con el modelo nuevo, y el diálogo "Model/Resource existentes" lista además, **solo como información**, el Filter, los Requests, el Service, el Controller y las rutas que el modelo reconoce como de ese Model. La generación todavía **solo** usa los Resources confirmados; usar los demás roles para ubicar y nombrar archivos nuevos es el siguiente paso.

El aprendizaje online se conserva: cada confirmación del desarrollador ajusta el modelo y se guarda en `%APPDATA%/ServiceForge/structure_matcher.joblib`, aparte del archivo del modelo anterior (tiene otro esquema de features). Lo aprendido con el modelo anterior no se traslada.

**Dos detalles que salieron al integrarlo:**
- Las features que calcula la app son **idénticas** a las del dataset: se compararon 86 550 valores de dos repos reales contra `pairs.parquet` (diferencia máxima 0.0), y el modelo empaquetado da las mismas predicciones que el evaluado.
- El modelo se entrenó con `early_stopping`, que scikit-learn no permite junto con `partial_fit`: el aprendizaje online habría fallado. `make_partial_fit_ready` repone lo que falta sin tocar los pesos, y hay un test de regresión.

**Costo:** escanear el proyecto al analizar una tabla tarda unos 0,2 a 0,8 s en los repos de prueba (88 a 122 modelos).
