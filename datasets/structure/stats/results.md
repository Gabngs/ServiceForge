# Resultados (test sobre repos reales no vistos)

Generado 24-09-2026 00:14:35 · leave-one-real-repo-out sobre 5 repos reales; test sobre todos los candidatos del rol · semillas por modelo: 3

## Top-1 por fold (¿el candidato mejor puntuado es de ese modelo?)

| Modelo | siaw-laravel-backend | sip-laravel-backend | gsp-back | AgencyWeb-Back | Peru_Lex_Back | **Promedio** |
|---|---|---|---|---|---|---|
| 1. Heurística actual | 0.873 | 0.758 | 0.906 | 1.000 | 0.964 | **0.900** |
| 2. Modelo de fábrica (*no held-out*) | 0.924 | 0.809 | 0.904 | 1.000 | 0.988 | **0.925** |
| 3. Nuevo, solo repos reales | 0.985 | 0.967 | 0.978 | 0.999 | 0.972 | **0.980** |
| 4. Nuevo, reales + sintéticos | 0.979 | 0.932 | 0.974 | 0.999 | 0.974 | **0.972** |
| 3s. (3) sin features de señal directa | 0.934 | 0.816 | 0.874 | 1.000 | 0.982 | **0.921** |
| 4s. (4) sin features de señal directa | 0.926 | 0.793 | 0.875 | 1.000 | 0.976 | **0.914** |

## Top-1 SOLO en grupos sin nombre exacto (donde una regla de nombres no alcanza)

Son los (modelo, rol) cuyo dueño se decidió por prefijo de nombre, carpeta, `$default_filters` o el controller de la ruta, no por igualdad de nombre. Es la parte del resultado que NO se puede explicar solo con comparar nombres.

| Modelo | siaw-laravel-backend | sip-laravel-backend | gsp-back | AgencyWeb-Back | Peru_Lex_Back | **Promedio** |
|---|---|---|---|---|---|---|
| 1. Heurística actual | 0.590 | 0.403 | 0.723 | 1.000 | 0.667 | **0.677** |
| 2. Modelo de fábrica (*no held-out*) | 0.663 | 0.448 | 0.698 | 1.000 | 0.667 | **0.695** |
| 3. Nuevo, solo repos reales | 0.928 | 0.903 | 0.983 | 0.996 | 0.593 | **0.881** |
| 4. Nuevo, reales + sintéticos | 0.924 | 0.811 | 0.962 | 0.996 | 0.519 | **0.842** |
| 3s. (3) sin features de señal directa | 0.687 | 0.470 | 0.648 | 1.000 | 0.444 | **0.650** |
| 4s. (4) sin features de señal directa | 0.651 | 0.425 | 0.629 | 1.000 | 0.444 | **0.630** |

Grupos difíciles por fold: siaw-laravel-backend=83, sip-laravel-backend=134, gsp-back=159, AgencyWeb-Back=84, Peru_Lex_Back=9


## Por rol — top-1 promedio de los 5 folds

| Rol | 1 | 2 | 3 | 4 | 3s | 4s |
|---|---|---|---|---|---|---|
| filter | 0.976 | 0.996 | 0.992 | 0.990 | 0.983 | 0.987 |
| resource | 0.966 | 0.992 | 0.992 | 0.995 | 0.991 | 0.995 |
| relation_resource | 0.986 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| base_request | 0.974 | 1.000 | 0.983 | 0.989 | 0.983 | 0.983 |
| store_request | 0.931 | 0.976 | 0.986 | 0.982 | 0.984 | 0.970 |
| update_request | 0.966 | 0.986 | 0.993 | 0.988 | 0.995 | 0.981 |
| request_trait | 0.950 | 0.908 | 0.998 | 0.965 | 1.000 | 0.929 |
| service | 0.979 | 0.990 | 1.000 | 0.990 | 0.987 | 0.974 |
| controller | 0.893 | 0.978 | 0.966 | 0.968 | 0.982 | 0.974 |
| route | 0.671 | 0.655 | 0.951 | 0.917 | 0.643 | 0.621 |

## Por rol — precision / recall / F1 (umbral 0.5, todos los pares) del modelo 4

| Rol | precision | recall | F1 | grupos (modelo×rol) |
|---|---|---|---|---|
| filter | 0.979 | 0.836 | 0.854 | 208 |
| resource | 0.934 | 0.903 | 0.916 | 266 |
| relation_resource | 0.975 | 0.919 | 0.941 | 65 |
| base_request | 0.982 | 0.978 | 0.979 | 57 |
| store_request | 0.962 | 0.951 | 0.955 | 149 |
| update_request | 0.980 | 0.962 | 0.969 | 147 |
| request_trait | 0.977 | 0.900 | 0.925 | 93 |
| service | 0.898 | 0.980 | 0.936 | 229 |
| controller | 0.926 | 0.902 | 0.910 | 301 |
| route | 0.977 | 0.880 | 0.912 | 300 |

## Diagnóstico sobre sintéticos de validación (NO es resultado principal)

Sobre pares muestreados (positivos + negativos duros/fáciles) de repos SINTÉTICOS de validación. Diagnóstico, NO resultado principal.

- Modelo 4: top-1 = 0.995, top-3 = 0.998
- Heurística: top-1 = 0.969, top-3 = 0.991
