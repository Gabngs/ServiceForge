# Service Patron

Ver documentación completa: [[Estandar Desarrollo Backend]]

---

Resumen del flujo:

[[Controller]] → orquesta
[[Requests y Traits]] → `{modulo}` → Store, Update validaciones y mensajes reutilizables
[[Service del Módulo]] → lógica de datos / validaciones, extiende `AbstractModuleService`
[[Model]] → `pkid` (interno) + `id` (UUID público), fillable, casts, relaciones
[[Migraciones y Catálogos]] → sin `enum` ni FKs: catálogo + `*_id`; precisión decimal; append-only
[[useFilters]] → el modelo aplica filtros del request automáticamente
[[CrudService]] → base CRUD + [[Auditoría]]
[[Mapeo UUID PKID]] → resolución de IDs foráneos
[[ApiResponse]] → estructura estándar de respuestas, con Resource / RelationResource / TinyResource
[[Conexiones, Migraciones y Rutas]] → arranque de proyecto: conexiones DB, migraciones/seeders centralizados en `dbsincro`, registro de rutas y permisos
