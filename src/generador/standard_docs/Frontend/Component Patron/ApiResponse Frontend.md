# ApiResponse Frontend

Relacionado: [[Estandar Desarrollo Frontend]] | [[Interfaz de Modulo]] | [[Service Angular de Modulo]] | [[Filtros de Consulta]]

---

Toda respuesta del backend se tipa con una de estas formas. Reflejan la estructura real de `ApiResponse` en el backend (`status`, `message`, `data`) — el trait `Essa\APIToolKit\Api\ApiResponse::responseSuccess()` que usan todos los controllers.

`status` es un **número** (código HTTP: `200`, `201`, `204`...), nunca un string `'success'|'error'`.

---

## Las tres piezas base — `interfaces/shared/model-base.interface.ts`

Todo lo que un modelo generado desde el backend necesita para tiparse vive en este único archivo, en tres interfaces:

```typescript
// interfaces/shared/model-base.interface.ts
import { IAuditUser } from './audit-user.interface';

// Forma de CADA registro que devuelve un CRUD estándar
export interface IModelBase {
  id?:             string;
  activo?:         boolean;
  estado?:  number | string; 
  created_by_id?:  IAuditUser | null;
  updated_by_id?:  IAuditUser | null;
  deleted_by_id?:  IAuditUser | null;
  created_at?:     string;
  updated_at?:     string;
  deleted_at?:     string | null;
}

// Query params que ACEPTA cualquier endpoint de listado con useFilters()
export interface IFiltersBase {
  sorts?: string;
  page?:      number;
  per_page?:  number;
  paginate?:  boolean;   // true → el backend llama dynamicPaginate()
  activo?:    boolean;    // filtro booleano casi-universal ($allowedFilters)
  search?:    string;     // texto libre → $columnSearch / $relationSearch
  created_by?: string;
  updated_by?: string;
  deleted_by?: string;
}

// Forma de `meta` cuando el listado viene paginado
export interface IModelBasePaginate {
  current_page: number;
  per_page:     number;
  total:        number;
  last_page:    number;
  from:         number | null;
  to:           number | null;
}
```

- **`IModelBase`** — todo lo que trae cada modelo por venir de un CRUD estándar del backend: soft delete (`activo`, `deleted_at`) y auditoría (`created_by_id`/`updated_by_id`/`deleted_by_id`). Cada `I{Modelo}` (ver [[Interfaz de Modulo]]) extiende esta interfaz, nunca repite estos campos a mano. `IAuditUser` es la forma mínima del modelo que resuelve esas tres FK de auditoría — solo `id` y `nombre`, no el registro completo del usuario.
- **`IFiltersBase`** — los query params que acepta cualquier listado que use `useFilters()` en el backend (ver [[useFilters]]): paginación (`page`/`per_page`/`paginate`) más los dos filtros que casi todo módulo declara (`activo`, `search`). Cada `I{Entidad}Filtros` (ver [[Filtros de Consulta]]) **extiende esta interfaz** y solo agrega los campos propios de su clase `Filters` — nunca repite `page`/`per_page`/`activo`/`search` a mano. Antes de dar `activo`/`search` por hechos en un módulo puntual, se verifica igual contra su clase `Filters` real.
- **`IModelBasePaginate`** — la forma de `meta` cuando la respuesta de un listado viene paginada. No se usa sola: es el tipo del campo opcional `meta` dentro de `I{Modelo}Response` (ver abajo). Sus 6 claves reflejan 1:1 la clave `meta` del backend (ver [[ApiResponse#Paginación sin duplicar `data`]]).

---

## Forma estándar de una respuesta — `data` y `meta` hermanos, siempre con interfaz propia

`data` (el array, sin anidar) y `meta` (la info de paginación, presente solo si el endpoint paginó) van como hermanos dentro del mismo objeto de respuesta — `meta` **no** va metido adentro de `data`. Esta es la forma real que arma cada `I{Modelo}Response`, confirmada contra un módulo ya completo del proyecto (`interfaces/models/menu.interface.ts`):

```typescript
// interfaces/models/menu.interface.ts
export interface IMenuResponse {
  status:  number;
  message: string;
  data:    IMenu[];
  meta?:   IModelBasePaginate;   // ausente si el endpoint no pagina (no se mandó ?paginate=true)
}

export interface IMenuSingleResponse {
  status:  number;
  message: string;
  data:    IMenu;
}
```

Todo módulo — listado o registro único — tiene su propia `I{Modelo}Response`/`I{Modelo}SingleResponse`, nunca un tipo genérico compartido: cada modelo ya tiene su interfaz (ver [[Interfaz de Modulo]]), así que no hay ningún caso real sin una propia. Ver la plantilla completa en [[Interfaz de Modulo]].

**Los errores no se tipan.** Una respuesta de error (422 de validación, 400, 401, 404...) no trae `data`: trae `message` y, en el 422, `errors` por campo. El frontend **no declara ninguna interfaz para eso** — no hay `ApiErrorResponse` ni equivalente. El único que lee el cuerpo de un error es [[Helper de Mensajes]] (`notifyHttpError`), de forma dinámica, sin asumir una forma fija. Regla completa en [[Helper de Mensajes#Regla — el frontend nunca declara errores]].

---

## Uso

```typescript
// Un solo registro — I{Modelo}SingleResponse propio, no un genérico compartido
show(id: string): Observable<IContentModelSingleResponse> {
  return this.http.get<IContentModelSingleResponse>(`${this.url}/${id}`);
}

// create / update / delete — el backend responde con el Resource del registro
// (en delete, el registro eliminado), así que es el mismo I{Modelo}SingleResponse
delete(id: string): Observable<IContentModelSingleResponse> {
  return this.http.delete<IContentModelSingleResponse>(`${this.url}/${id}`);
}

// Colección, forma estándar — filters SIEMPRE tipado con la I{Entidad}Filtros del
// modelo (ver [[Filtros de Consulta]]), nunca Record<string, unknown> ni any
getIndex(filters?: IContentModelFiltros): Observable<IContentModelResponse> {
  return this.http.get<IContentModelResponse>(this.url, { params: this.buildParams(filters) });
}
```

```typescript
// En el componente:
this.svc.getIndex({ activo: true, page: 1, per_page: 20 }).subscribe(res => {
  this.data.set(res.data);              // ya es el array, sin desanidar
  this.totalRecords.set(res.meta?.total ?? res.data.length);
});
```

Si el modelo del módulo no tiene filtros declarados en el backend (`useFilters()` no aplicado a ese modelo — ver [[Filtros de Consulta]]), `getIndex` no recibe parámetro de filtros.

---

Se usa en todos los métodos de [[Service Angular de Modulo]]. Una llamada que no tiene una entidad de módulo detrás (ej. [[Auth Service]] — login, logout, me) también tipa su propia interfaz de respuesta, con la misma forma `status`/`message`/`data` — nunca un `ApiResponse<T>` genérico compartido entre módulos.
