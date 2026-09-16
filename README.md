# Generador Front-Back

GUI de escritorio que genera el boilerplate repetitivo de un módulo CRUD Laravel a partir de la base de datos: analiza una tabla, detecta relaciones FK, y genera el patrón de servicio completo — Model, Service, Filters, Requests + Trait, Controller y ruta — más las interfaces TypeScript del frontend correspondientes (`I{Modulo}`, `Create`, `Update`, `Tiny`).

> **Estado: beta.** Versionando `0.x` hasta llegar a un `1.0.0` estable — cada release es un paso intermedio, no el producto final.

## Qué hace

- Conecta a MySQL/MariaDB y analiza la tabla elegida (`DESCRIBE`, índices únicos, tablas del schema). Botón de "Probar conexión" separado de "Conectar", con indicador de estado (conectando / conectado / error) sin congelar la ventana.
- Detecta relaciones `{campo}_id → belongsTo`: automático si hay una sola tabla candidata, pregunta si hay ambigüedad (y recuerda la respuesta). Genera también los `belongsTo` de auditoría (`created_by`/`updated_by`/`deleted_by`) contra el modelo de usuario que configures.
- Genera el patrón completo: `Model.php`, `{Modulo}Service.php`, `{table}Filters.php`, `Store{Modulo}Request.php` / `Update{Modulo}Request.php` + `Validates{Modulo}` trait, `{table}Controller.php`, `routes/modules/{modulo}.php`, y las interfaces del frontend.
- Preview **editable** de cada archivo antes de escribir nada a disco — lo que quede en cada pestaña al confirmar es lo que se escribe.
- Escribe cada archivo en la carpeta real del proyecto (`app/Models/...`, `app/Services/...`, etc.), no en una carpeta plana — elegís la raíz del backend y del frontend por separado.
- "Analizar proyecto" revisa (de solo lectura) si el backend ya carga `routes/modules/*.php` automáticamente, y sugiere el snippet si falta — nunca edita `RouteServiceProvider`/`bootstrap/app.php` solo.
- El `audit-user.interface.ts` compartido es opcional (checkbox) — pensado para proyectos que ya existen y ya lo tienen.
- Backup manual de la BD conectada (`mysqldump`).

Lo que falta (Resources, service Angular completo, parser de migraciones sin ejecutar, relaciones many-to-many, auto-registro de rutas) está en el roadmap.

## Descargar

Cada tag `vX.Y.Z` publica un [Release](https://github.com/Gabngs/generador-front-back/releases) con el `.exe` de Windows listo para usar.

## Correr en local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt

python -m pytest -q      # tests
python src/main.py       # abre la GUI (requiere una BD MySQL/MariaDB accesible)
```

## Roadmap

- [ ] `{Modulo}Resource.php` / `{Modulo}RelationResource.php`
- [ ] Auto-registro de `routes/modules/{modulo}.php` en el provider (hoy solo se detecta y sugiere, no se edita)
- [ ] Service Angular completo
- [ ] Parser de migraciones `.php` sin ejecutar (sin depender de conexión a BD)
- [ ] Relaciones many-to-many (tabla pivot)
- [ ] Documentación Swagger/OpenAPI en el Controller generado

## Licencia

Sin licencia explícita por el momento — todos los derechos reservados por defecto.
