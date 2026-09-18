# Auditoría

Relacionado: [[Estandar Desarrollo Backend]] | [[CrudService]]

---

El [[CrudService]] registra opcionalmente cada operación CRUD en la tabla de auditoría del proyecto. El nombre de la tabla varía por proyecto (referencia: `{prefijo}_procesosaudit`).

---

## Campos de la tabla de auditoría

```
pkid             - AutoIncrement (PK)
id               — UUID - STRING 
nombre_proceso   — string: identificador del proceso ('crear_modulo', 'actualizar_modulo')
tipo_proceso     — int: constante TIPO_INSERCION | TIPO_ACTUALIZACION | TIPO_ELIMINACION | TIPO_RESTAURACION
estado_proceso   — int: constante ESTADO_EXITO | ESTADO_ERROR
origen           — int: constante ORIGEN_MANUAL | ORIGEN_AUTOMATICO
modelo_afectado  — string: class_basename del modelo ('sip_personal', 'catalogo_tienda')
registro_id      — int|null: pkid del registro afectado (null en operaciones bulk)
input            — json: estado ANTERIOR al cambio (null en create)
output           — json: estado POSTERIOR (null en delete, {total_insertados: N} en bulk)
error            — string|null: mensaje de error si estado_proceso = ESTADO_ERROR
created_by_id    — int|null: pkid del usuario del token
created_at       — timestamp
```

---

## Constantes del modelo de auditoría

```php
// tipo_proceso
{Prefijo}_procesosaudit::TIPO_INSERCION     // create / bulkInsert
{Prefijo}_procesosaudit::TIPO_ACTUALIZACION // update
{Prefijo}_procesosaudit::TIPO_ELIMINACION   // delete
{Prefijo}_procesosaudit::TIPO_RESTAURACION  // restore

// estado_proceso
{Prefijo}_procesosaudit::ESTADO_EXITO
{Prefijo}_procesosaudit::ESTADO_ERROR  // para procesos que atrapan sus propias excepciones

// origen
{Prefijo}_procesosaudit::ORIGEN_MANUAL     // hay token de usuario → acción humana
{Prefijo}_procesosaudit::ORIGEN_AUTOMATICO // sin token → job, comando artisan, proceso cron
```

---

## Activar / desactivar por operación

```php
// ✅ Con auditoría — tercer parámetro = nombre del proceso (string identificador)
$this->crud->create({prefijo}_{modulo}::class, $data, 'crear_{modulo}');
$this->crud->update($model, $data, 'actualizar_{modulo}');
$this->crud->delete($model, 'eliminar_{modulo}');
$this->crud->restore($model, 'restaurar_{modulo}');

// ✅ Sin auditoría — omitir el tercer parámetro (queda null por defecto)
$this->crud->create({prefijo}_{modulo}::class, $data);
$this->crud->update($model, $data);
$this->crud->delete($model);
$this->crud->restore($model);
```

---

## Qué se registra en input/output por operación

### create

```json
// input — estado antes (null, no existía)
null

// output — el registro creado completo
{
    "pkid": 42,
    "id": "abc123...",
    "nombre": "Producto A",
    "tienda_id": 5,
    "created_by_id": 10,
    "created_at": "2025-06-08 10:00:00"
}
```

### update

```json
// input — estado ANTES del cambio
{
    "pkid": 42,
    "nombre": "Producto A",
    "activo": 1
}

// output — estado DESPUÉS del cambio
{
    "pkid": 42,
    "nombre": "Producto A modificado",
    "activo": 0
}
```

### delete

```json
// input — snapshot del registro antes de eliminarlo
{
    "pkid": 42,
    "nombre": "Producto A",
    "activo": 1
}

// output — null (ya no existe)
null
```

### restore

```json
// input — snapshot del registro antes de restaurarlo (deleted_at aún no nulo)
{
    "pkid": 42,
    "nombre": "Producto A",
    "deleted_at": "2025-06-08 10:00:00"
}

// output — estado DESPUÉS de restaurar (deleted_at ya en null)
{
    "pkid": 42,
    "nombre": "Producto A",
    "deleted_at": null
}
```

### bulkInsert

```json
// input — null (no aplica por fila)
null

// output — resumen del proceso
{
    "total_insertados": 150
}
```

---

## Origen: MANUAL vs AUTOMATICO

```php
// MANUAL → el token existe → acción iniciada por un usuario desde el frontend
Token::user() // retorna el usuario con su pkid

// AUTOMATICO → no hay token → proceso programado, job, comando artisan, sincronización
Token::user() // retorna null
```

El [[CrudService]] determina el origen automáticamente — no hay que configurar nada.

---

## Cuándo auditar y cuándo no

| Auditar                                                                 | No auditar                                                |
| ----------------------------------------------------------------------- | --------------------------------------------------------- |
| Creación/modificación de datos críticos (personal, planilla, contratos) | Lecturas (index, show)                                    |
| Eliminación de cualquier registro                                       | Procesos de solo lectura                                  |
| Procesos automáticos que modifican datos masivamente                    | Actualizaciones de campos triviales (last_seen, contador) |
