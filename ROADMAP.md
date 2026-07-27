# baton — roadmap

Estado a **2026-07-25**. Diseño completo en `P0-design.md`.

## Decisiones cerradas
- **Nombre**: `baton` (CLI + skills; verbos `new/triage/approve/start/ship/reject`).
- **Adapter primero**: GitHub (PROJ lo usa hoy). Plane después = solo un adapter.
- **Lenguaje**: Python + `uv`.
- **Repo**: propio (`baton`), separado de `agent-skills`. `agent-skills` se **archiva** en el cutover (su historial queda accesible); si se quiere la lineage `idea-*`→baton dentro de baton, `git filter-repo` en P4.

## Fases

| Fase | Estado | Qué |
|---|---|---|
| **P0** | ✅ | Inventario de los 5 `idea-*` + spec de la interfaz del adapter + verbos + nombre. (`P0-design.md`) |
| **P1** | ✅ | CLI `baton` + adapter GitHub con **discovery por nombre** (cero IDs hardcodeados) + ops. Verificado real contra PROJ Project #5. |
| **P2** | ✅ | Portadas las 5 skills → llaman al CLI (sin GraphQL/IDs); juicio queda en la skill; PROJ-specifics opcionales/config. Verbos `approve/start/ship` config-driven. Write path verificado (#242 Review→Approved→Review). |
| **P3** | ✅ | Adapter **Plane** (`adapters/plane.py`) contra REST directo (sin CLI oficial, a diferencia de `gh`) — endpoints/campos verificados contra la fuente del SDK oficial (`makeplane/plane-python-sdk`), no contra docs (que se contradecían issues/ vs work-items/). Test con fake HTTP en `tests/test_plane_adapter.py`. CLI y skills **intactos**. **Verificado en vivo 2026-07-26** contra PROJBOT (workspace `desarrollo`, SOPORTE_SERVER): ciclo completo create→show→approve→comment→labels→list--stage→close, incluido el auto-flag de `review_label` en retrocesos. Dos bugs reales encontrados y arreglados en la corrida: (1) `base_url` debe ser `https://`, no `http://` — la instancia redirige 308 en POST/PATCH (urllib no sigue 308) aunque el toggle de Dokploy diga https:false; (2) `state`/`labels` en la respuesta vienen como objeto expandido (`expand=state,labels`), no como UUID plano — `_to_item` asumía siempre string y crasheaba (`TypeError: unhashable type: 'dict'`). |
| **P4** | 🟡 en curso | Empaquetar + publicar (plugin/repo) + **cutover**. Hecho: repo `SOSkr/baton` en GitHub (privado), PROJ ya usa `.baton/config.yaml`, skills baton linkeadas global. Falta: publicar (skills.sh/PyPI) + flip a público + archivar `agent-skills`. |

## Probar en PROJ (siguiente paso)

1. **Instalar el CLI**: `uv tool install ~/Git-projects/baton` (o `pipx install ~/Git-projects/baton`) → `baton` en el PATH.
2. **Config** — crear `.baton/config.yaml` en el workspace PROJ (o en `proj-spec`), **gitignorear `.baton/`** si el directorio es un repo git (la raíz `~/Git-projects/proj` no lo es, ahí no aplica):
   ```yaml
   # backend: github (histórico, PROJ Project #5 en proj-spec)
   backend: github
   target: { repo: SOSkr/proj-spec, owner: SOSkr, project: 5 }
   stages: { approve: Approved, start: In Progress, ship: Deployed }
   ```
   ```yaml
   # backend: plane (activo desde 2026-07-26 — Plane self-hosted en SOPORTE_SERVER, ver plane-deployment-soporte-server)
   backend: plane
   target:
     base_url: https://plane-plane-c87bf9-72-251-5-49.sslip.io  # https obligatorio, ver nota P3
     workspace: desarrollo
     project: PROJBOT  # identifier del proyecto "PROJ Bot" en Plane, NO "PROJ"
   stages: { approve: Approved, start: In Progress, ship: Deployed }
   review_label: revisar-cambio
   ```
   Requiere `PLANE_API_KEY` exportado en el shell (mismo token que usa el MCP `plane-mcp`, nunca en el yaml — ver git-add-secrets-incident). Estados del proyecto PROJBOT renombrados 2026-07-26 (vía MCP `update_state`) de los defaults de Plane (Backlog/Todo/In Progress/Done/Cancelled) a **Review/Approved/In Progress/Deployed/Cancelled**, calcando el Status field que usaba GitHub Projects — mismos `group` (backlog/unstarted/started/completed/cancelled), solo rename, sin tocar estructura.
3. **Verificar**: `baton doctor` (discovery OK) · `baton stages` · `baton list --stage Review`.
4. **Skills** — para que las sesiones PROJ usen las skills baton, symlinkearlas (como hacía `link-proj.sh` con `idea-*`): `~/Git-projects/baton/skills/baton-*` → `.claude/skills/` de cada repo. Correr en paralelo con las `idea-*` mientras se prueba; deprecar `idea-*` cuando baton convenza.
5. **Migrar `agents.md §4`**: los IDs hardcodeados (project/field/options) dejan de ser necesarios — el discovery los resuelve. Actualizar cuando se adopte baton.

## Features futuras (gated en escala / post-cutover)

### `baton search` — retrieval por embeddings
Gated en **escala** (cientos+ items cross-proyecto). Indexa cada item al crear/actualizar en un store local (sqlite + modelo de embeddings chico) → `baton search "<query>"` devuelve top-K ids → leés solo esos. **Reusar** claude-mem / codebase-memory (ya hacen búsqueda semántica), no construir de cero. Ahorra tokens reduciendo **cuántos** items se leen, no el tamaño de cada uno. A escala chica (decenas) es prematuro — `baton list --label/--stage` + full-text search del backend alcanza.

### `baton prune` — depurar ideas obsoletas
Problema: ideas en Review que quedan obsoletas a medida que se hacen otras (superadas por decisiones/issues nuevos, pre-rebuild, ya implementadas). Depurarlas leyendo+investigando cada una es caro. Dos tiers:

- **Tier 1 (lean, recomendado — sin pre-compile)**: flag por **reglas sobre metadata que ya existe**, barato:
  - **edad + category** (ej. `category:architecture` viejo = riesgo de proceso pre-rebuild).
  - **refs colgantes/superadas**: el body referencia issues **cerrados** o decisiones **revisadas por una posterior** → probable superada. (Señal más fuerte vista en la sesión: "superada por decisión 05X / #NNN".)
  - **depende-de** un issue cerrado.
  El comando flag-ea candidatos (cheap); el **modelo revisa solo el subset flaggeado** (no las N). Captura la mayor parte de la señal de staleness.
  - **Prune SIEMPRE aplica `review_label`** a cada item que toca, **sin importar el tipo de cambio** (forward / backward / close / reclasificar). Motivo: prune es **automático/no supervisado** — el usuario no vio cada decisión, tiene que poder revisarlas **todas**. Esto es un disparador **distinto** del auto-flag backward del CLI (que solo marca retrocesos en cambios explícitos). Prune aplica el label **explícito**, no depende del backward-detection.

> **`review_label` — semántica (ya implementado en el CLI)**: `config.review_label` se aplica SOLO en **transiciones inesperadas = retroceso de estado** (ej. `Approved→Review`), detectadas por el **orden real de stages del board** (`list_stages`). El **flujo normal forward** (new/review/approve/start/ship) **NO** se flaggea — es el proceso esperado, el usuario ya está en el loop. Se marca lo **anómalo**: algo que estaba aprobado y vuelve a review, o cualquier cambio hacia atrás. Prune reusa el mismo label en sus cierres. PROJ: `review_label: revisar-cambio`.
- **Tier 2 (richer — el "pre-compile" del usuario)**: al crear/revisar, guardar un **staleness fingerprint** por idea: `{assumptions clave, componentes/decisiones/files referenciados, depends-on, claim en 1 línea}`. El fingerprint es **estable** (describe la idea); la **realidad se mueve** (decisiones/código nuevos) → prune compara fingerprint vs realidad sin re-leer todo. Más inteligente, pero cuesta generar el fingerprint (una vez por idea, al intake). Hacerlo si el Tier 1 no alcanza.

## Notas de estado
- Repo baton: **en GitHub `SOSkr/baton` (privado)** desde 2026-07-26; SOSkrAgent colaborador `write`. Flip a público al publicar (P4).
- `agent-skills` sigue con las `idea-*` en vivo para PROJ — no tocar hasta el cutover.
- P3 (Plane): trigger fue Plane self-hosted desplegado en SOPORTE_SERVER (2026-07-26, ver memoria `plane-deployment-soporte-server`). Adapter escrito y testeado con HTTP fake. Token/API verificados 100% funcionales con `X-Api-Key` directo (curl manual → 200, 2 projects) — el 403 que daba el MCP `plane-mcp` era un bug de config del MCP (env var `PLANE_BASE_URL` no existe en el paquete npm real, es `PLANE_API_HOST_URL`; con el nombre viejo caía a Plane Cloud), ya corregido, no del adapter ni del token. Falta: `.baton/config.yaml` de PROJ con `backend: plane` + probar `baton doctor` contra la instancia real.
