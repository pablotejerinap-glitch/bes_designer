# BES Designer — análisis del proyecto y spec de publicación web

Fecha: 3 de septiembre de 2026. Rama `main`, commit `b513483`.

Este documento tiene dos mitades: **qué hay hoy** (análisis, medido, no
estimado) y **qué falta para que esté en internet** (spec por fases, con
criterio de aceptación en cada paso).

---

## PARTE 1 — Análisis del estado actual

### 1.1 Tamaño y salud

| Métrica | Valor | Cómo se midió |
|---|---:|---|
| Python del paquete `bes` | 22 371 líneas | `wc -l` sobre `backend/src/**/*.py` |
| Tests | 30 archivos, 13 934 líneas | idem sobre `backend/tests` |
| Suite | **1278 pasan, 4 se saltean, 0 fallan** (68.7 s) | `pytest -q` |
| TypeScript del front | 8 499 líneas | `wc -l` sobre `frontend/src/**/*.ts*` |
| Typecheck del front | **limpio** | `npx tsc --noEmit` |
| Endpoints HTTP | 14 en 9 routers | `grep @router` |
| Catálogos JSON | 1.8 MB, 10 archivos | `du -sh backend/src/bes/catalogs` |

Reparto del backend por capa (líneas):

```
core        15 224   dominio puro, sin frameworks
api          1 920   FastAPI: routers, schemas, mappers
reports      1 503   PDF (reportlab) + Excel (openpyxl)
recommender  1 314   selección y ordenamiento
plotting     1 007   builders Plotly
catalogs       700   loader + queries
services       685   orquestación
```

La proporción es la correcta para el tipo de proyecto: **el 68 % del código es
dominio**, y la capa HTTP es delgada (8.6 %). La regla de dirección de
dependencias de `.claude/rules/architecture.md` se sostiene y hay un test que
la vigila (`tests/test_architecture.py`).

### 1.2 Rendimiento medido (in-process, sin red)

| Endpoint | Tiempo | Respuesta |
|---|---:|---:|
| `GET /api/catalogs` | 0.18 s | — |
| `POST /api/design` (n=3) | **0.22 s** | 77 KB |
| `POST /api/reports/xlsx` | 0.21 s | 13 KB |
| `POST /api/reports/pdf` | **2.88 s** | 222 KB |

El PDF es, por lejos, la operación cara: 2.9 s de CPU por request. Es el número
que gobierna el dimensionamiento del servidor y el timeout del proxy.

### 1.3 Qué ya está resuelto para desplegar

- **Docker completo y funcionando**: `backend/Dockerfile` (python:3.13-slim +
  uvicorn), `frontend/Dockerfile` (build node:20 → nginx:alpine),
  `docker-compose.yml` con healthcheck del backend y `depends_on: service_healthy`.
- **Mismo origen sin CORS**: `frontend/nginx.conf` proxya `/api/` al servicio
  `api`, y el cliente usa base relativa (`frontend/src/api/client.ts:23`).
- **CORS configurable por entorno**: `BES_CORS_ORIGINS`
  (`backend/src/bes/api/main.py:38`).
- **Sin estado y sin secretos**: no hay base de datos, ni login, ni archivos
  subidos, ni claves de API. Cada request es independiente. Esto simplifica
  enormemente la operación y elimina de raíz la mitad de los problemas de
  seguridad de una app web.
- **Catálogo cargado una vez por proceso** (`backend/src/bes/api/deps.py:8`,
  `lru_cache`): no se relee el 1.8 MB de JSON en cada request.
- **SPA fallback** y `proxy_read_timeout 300s` ya configurados en nginx.
- **Errores del dominio → HTTP 422** con mensaje legible, central en
  `backend/src/bes/api/main.py:56`.
- **Versiones pinneadas** en los tres `requirements*.txt` (todas con `==`).

### 1.4 Deudas y riesgos, ordenados por lo que muerde primero

**Bloqueantes para publicar**

1. **El bundle del front pesa 5.2 MB sin comprimir y nginx no tiene gzip.**
   `frontend/dist/assets/index-*.js` = 5 193 657 bytes; `grep -c gzip
   frontend/nginx.conf` devuelve 0. En una conexión móvil eso es medio minuto de
   pantalla en blanco. Con gzip baja a ~1.3 MB.
2. **Sin TLS ni dominio.** Hoy el compose expone HTTP plano en `:8080`.
3. **CORS por defecto apunta a localhost** (`backend/src/bes/api/main.py:34-37`).
   En producción hay que fijar `BES_CORS_ORIGINS` al dominio real o dejarlo
   vacío (el front va por el mismo origen y no lo necesita).
4. **Un solo worker de uvicorn** (`backend/Dockerfile:22`). Un PDF de 2.9 s
   ocupa un hilo del threadpool; con varios usuarios simultáneos la app se
   siente colgada.
5. **`restart:` ausente en `docker-compose.yml`.** Si el contenedor se cae, no
   vuelve solo.
6. **Trabajo sin commitear**: 24 archivos modificados y 4 sin trackear, incluido
   `frontend/openapi.json`. No se despliega desde un árbol sucio.

**Importantes, no bloqueantes**

7. **Sin rate limiting.** `POST /api/reports/pdf` es un generador de carga de
   2.9 s de CPU accesible sin autenticación. Un solo script lo satura.
8. **`kaleido` no está en `requirements`** y `backend/src/bes/reports/pdf_generator.py:202`
   prefiere Plotly+kaleido con respaldo matplotlib. En producción el PDF sale
   siempre por el camino de respaldo, en silencio. Hay que decidir: instalarlo o
   documentar que el camino real es matplotlib.
9. **Sin CI.** No existe `.github/workflows/`. Los 1278 tests se corren a mano.
10. **Tres versiones de Python conviviendo**: venv 3.14, imagen 3.13,
    `requires-python = ">=3.11"`. Funciona, pero nada declara cuál es la de
    verdad.
11. **`backend/.dockerignore` no excluye `build/`**, que es una copia vieja del
    paquete y se cuela en la imagen.
12. **`frontend/index.html` sin favicon ni meta description.**
13. **Sin logs estructurados ni monitoreo**: si algo falla en producción, la
    única evidencia es `docker logs`.

**Cuestión de fondo, decidir antes de publicar**

14. **Qué se publica al mundo.** Los catálogos son digitalizaciones de material
    de REDA, Centrilift y Wood Group. Usarlos en una tesis es una cosa; servir
    una app pública que los expone por `GET /api/catalogs` es otra. Ver §2.2.

**Documentación desactualizada**

15. `docs/_trabajo/TESIS_CONTEXTO_COMPLETO.md:210` sigue mencionando
    `SensitivityView.tsx` y `sensitivity_service.py`, que se retiraron en
    agosto. Ese archivo es el que se pega como contexto en conversaciones
    nuevas: si miente, arrastra el error.

---

## PARTE 2 — Qué hace falta para subirlo a la web

### 2.1 Decisión de hosting

Tres caminos posibles. La recomendación es el A.

| | A — VPS con Docker (**recomendado**) | B — Estático + PaaS | C — Todo en una PaaS |
|---|---|---|---|
| Frontend | nginx del propio compose | Cloudflare Pages / Netlify | Render / Railway |
| Backend | contenedor en el mismo VPS | Fly.io / Render | idem |
| Costo | ~5 USD/mes (Hetzner, DigitalOcean) | 0 a 7 USD/mes | 0 a 7 USD/mes |
| Esfuerzo | bajo: el `docker-compose.yml` ya existe | medio: hay que separar orígenes y activar CORS | bajo |
| Riesgo | ninguno técnico | el free tier duerme: primera visita a 30-50 s | idem |

La imagen del backend carga numpy, scipy, pandas y matplotlib: **512 MB de RAM
es justo, 1 GB es cómodo.**

**Por qué el A.** El proyecto ya está containerizado y probado con
`docker compose up --build`; un VPS es literalmente ese mismo comando en otra
máquina, más un reverse proxy con TLS. Los free tiers de PaaS duermen el
contenedor por inactividad, y con una imagen que importa scipy y matplotlib el
arranque en frío se va a decenas de segundos — inaceptable si el tribunal abre
el link durante la defensa.

**Reverse proxy: Caddy**, no nginx a nivel host. Saca certificado de Let's
Encrypt solo, lo renueva solo, y su archivo de configuración son cuatro líneas.
El nginx interno del front se queda como está.

### 2.2 Acceso: público, o con clave

Dos escenarios, y hay que elegir uno antes de empezar:

- **Con clave** (recomendado para la defensa): Caddy con `basic_auth`, una
  contraseña compartida en el informe. Resuelve de un saque el rate limiting, la
  cuestión de los catálogos de fabricante y el abuso.
- **Público**: exige rate limiting real, revisar qué expone `/api/catalogs`, y
  poner un aviso de uso académico bien visible.

### 2.3 Dominio

No hace falta comprar uno. Alcanza con el subdominio gratuito del proveedor, o
un dominio propio (~15 USD/año) si querés que quede prolijo en el informe. Caddy
funciona igual con cualquiera de los dos.

---

## PARTE 3 — Spec de publicación

### Objetivo

Que `https://<dominio>` sirva la SPA con el backend detrás del mismo origen,
sobre HTTPS, con arranque automático, y que un revisor pueda correr un diseño
completo y bajarse el PDF sin ayuda.

### Fuera de alcance (explícito)

Base de datos, cuentas de usuario, guardado de casos, CDN, escalado horizontal,
alta disponibilidad. Nada de eso hace falta para una app de tesis, y cada uno
agrega superficie de falla. `bes.db` sigue sin existir y está bien así.

### Arquitectura destino

```
Internet ──HTTPS──▶ Caddy (host, TLS automático, basic_auth opcional)
                      │
                      ▼  HTTP
                 frontend  (nginx + dist estático, gzip)
                      │  proxy /api/
                      ▼
                    api  (uvicorn, 2 workers, healthcheck)
```

---

### FASE 0 — Higiene del repositorio (antes de tocar nada de infra)

| # | Paso | Criterio de aceptación |
|---|---|---|
| 0.1 | Revisar los 24 archivos modificados y los 4 sin trackear; commitear en rama y mergear | `git status` limpio |
| 0.2 | Regenerar `frontend/openapi.json` y correr `npm run gen:api` (comandos en `CLAUDE.md`) | el contrato tipado coincide con los schemas Pydantic |
| 0.3 | Correr la suite completa | 1278 pasan, 0 fallan |
| 0.4 | `npx tsc --noEmit` y `npm run build` | sin errores, `dist/` se genera |
| 0.5 | Corregir `docs/_trabajo/TESIS_CONTEXTO_COMPLETO.md:210` (sensibilidad retirada) | el doc no menciona archivos inexistentes |

**Sin la fase 0 no se sigue.** Desplegar desde un árbol sucio es la forma más
común de subir algo distinto de lo que se probó.

---

### FASE 1 — Preparar las imágenes para producción

| # | Paso | Archivo | Criterio de aceptación |
|---|---|---|---|
| 1.1 | Activar **gzip** para JS, CSS, JSON y SVG | `frontend/nginx.conf` | `curl -H "Accept-Encoding: gzip" -I` sobre el bundle devuelve `Content-Encoding: gzip`; el JS viaja en ~1.3 MB en vez de 5.2 |
| 1.2 | Cache headers: `immutable, max-age=31536000` para `/assets/*` (los nombres llevan hash) y `no-cache` para `index.html` | `frontend/nginx.conf` | segunda visita sin descargar el bundle |
| 1.3 | Subir a **2 workers** de uvicorn | `backend/Dockerfile:22` | dos PDF simultáneos no se serializan |
| 1.4 | Agregar `build/` y `data/` a `.dockerignore` del backend | `backend/.dockerignore` | la imagen no lleva la copia vieja del paquete |
| 1.5 | Decidir el motor de gráficos del PDF: agregar `kaleido` a `requirements-api.txt`, **o** dejar constancia de que el camino de producción es matplotlib | `backend/requirements-api.txt` | el PDF generado dentro del contenedor tiene las figuras esperadas |
| 1.6 | Favicon y `<meta name="description">` | `frontend/index.html` | la pestaña del browser muestra ícono y nombre |
| 1.7 | Declarar la versión de Python de una sola forma | `backend/pyproject.toml`, `backend/Dockerfile` | coinciden entre sí |

Verificación de la fase: `docker compose up --build`, entrar a
`http://localhost:8080`, correr un diseño, bajar el PDF y el Excel.

**Opcional (1.8):** cargar `frontend/src/components/PlotFigure.tsx` con
`React.lazy` para que Plotly no entre en el bundle inicial. Baja el primer
render, pero no es requisito para publicar — con gzip el bundle ya es
manejable.

---

### FASE 2 — Endurecer para internet

| # | Paso | Dónde | Criterio de aceptación |
|---|---|---|---|
| 2.1 | `restart: unless-stopped` en los dos servicios | `docker-compose.yml` | `docker kill` al contenedor y vuelve solo |
| 2.2 | Fijar `BES_CORS_ORIGINS` al dominio real (o vacío) | `docker-compose.yml` | un `fetch` desde otro origen recibe error de CORS |
| 2.3 | Rate limiting en `/api/` con `limit_req_zone`, más estricto para `/api/reports/` | `frontend/nginx.conf` | 20 requests seguidos a `/api/reports/pdf` devuelven 429 a partir del N |
| 2.4 | Límite de tamaño de request (`client_max_body_size 256k`) | `frontend/nginx.conf` | un body grande recibe 413 |
| 2.5 | Healthcheck también para el front | `docker-compose.yml` | `docker compose ps` muestra los dos healthy |
| 2.6 | Límites de recursos (`mem_limit`, `cpus`) para que el VPS no muera por swap | `docker-compose.yml` | el contenedor no pasa de lo asignado bajo carga |

---

### FASE 3 — Servidor, TLS y dominio

| # | Paso | Criterio de aceptación |
|---|---|---|
| 3.1 | Contratar VPS (2 vCPU / 2 GB recomendado; 1 GB es el mínimo) e instalar Docker | `docker compose version` responde |
| 3.2 | Apuntar el registro DNS `A` al IP del VPS | `dig +short <dominio>` devuelve el IP |
| 3.3 | Instalar Caddy y escribir el `Caddyfile` (dominio → `reverse_proxy localhost:8080`) | `https://<dominio>` responde con certificado válido |
| 3.4 | Decidir acceso: `basic_auth` en el Caddyfile, o público con aviso de uso académico | entrar desde otra red y verificar el comportamiento elegido |
| 3.5 | Firewall: exponer sólo 22, 80 y 443; **no** publicar el `8000` del backend al exterior (hoy `docker-compose.yml` lo hace) | un escaneo desde afuera no ve el 8000 |
| 3.6 | Clonar el repo y `docker compose up -d --build` | los dos contenedores healthy |
| 3.7 | Habilitar el arranque en el boot del VPS | reiniciar la máquina y verificar que la app vuelve sola |

El paso **3.5 es importante y fácil de pasar por alto**: el compose actual mapea
`8000:8000`, lo que dejaría la API accesible sin pasar por el proxy — sin TLS,
sin rate limit y con la CORS que sea.

---

### FASE 4 — Verificación de aceptación

Recorrido completo, hecho desde otra computadora y otra red:

1. Abrir `https://<dominio>` — carga en menos de 5 s con red normal.
2. Cargar un caso de ejemplo (`frontend/src/exampleCases.ts`) y correr el diseño
   — responde en menos de 2 s.
3. Verificar que rendericen los gráficos: curva de bomba, nodal y escalera de
   incrementos del pozo con gas.
4. Descargar el PDF y el Excel — se abren correctamente.
5. Correr el camino de **pozo con gas** (`POST /api/gas/design`) de punta a
   punta.
6. Forzar un error de validación (una Pwf mayor que la presión estática) — sale
   el mensaje en castellano, no un 500.
7. `https://<dominio>/api/docs` — decidir si se deja visible (es buena carta de
   presentación para el tribunal) o se cierra.
8. Probar en un celular: el layout de dos paneles tiene que ser usable.

---

### FASE 5 — Sostenerlo (opcional, pero barato)

| # | Paso | Por qué |
|---|---|---|
| 5.1 | `.github/workflows/ci.yml`: pytest + `tsc --noEmit` + `npm run build` en cada push | es la deuda #9, y es lo que evita desplegar algo roto |
| 5.2 | Monitoreo externo gratuito (UptimeRobot) sobre `/api/health` | te enterás antes que el tribunal |
| 5.3 | Rotación de logs de Docker (`max-size` en el logging driver) | un VPS chico se llena de logs |
| 5.4 | Script de despliegue de una línea (`git pull && docker compose up -d --build`) | reproducible, sin pasos recordados de memoria |

---

## Resumen ejecutivo

El proyecto está **técnicamente listo**: 1278 tests verdes, typecheck limpio,
Docker que funciona, sin base de datos ni secretos que administrar. Lo que falta
no es código de aplicación sino **empaquetado y operación**.

El camino corto —lo mínimo real para tener el link andando— son cinco cosas:

1. Limpiar el árbol de git (Fase 0).
2. Activar gzip en nginx (Fase 1.1). Es el mayor impacto por lejos: 5.2 MB → 1.3 MB.
3. `restart: unless-stopped` y sacar el `8000:8000` del compose (Fases 2.1, 3.5).
4. VPS + Caddy con TLS (Fase 3).
5. Recorrer la lista de aceptación (Fase 4).

Estimación: **una tarde de trabajo** para las fases 0 a 3, más lo que tarde el
DNS en propagar. La fase 5 y los opcionales se pueden hacer después, con la app
ya publicada.

La única decisión que no es técnica y conviene tomar antes de empezar es la de
**§2.2: público o con clave**. Si es con clave, las fases 2.3 y 2.4 pasan a ser
opcionales y el trabajo se acorta.
