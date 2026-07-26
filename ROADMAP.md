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
| **P3** | ⬜ pendiente | Adapter **Plane** (`adapters/plane.py` implementando el contrato de `base.py`). CLI y skills **intactos**. Depende de confirmar Plane como tracker. |
| **P4** | ⬜ pendiente | Empaquetar + publicar (plugin/repo) + **cutover**: crear repo `baton` en GitHub, migrar PROJ a `.baton/config.yaml`, linkear skills baton en los repos, archivar `agent-skills`. |

## Probar en PROJ (siguiente paso)

1. **Instalar el CLI**: `uv tool install ~/Git-projects/baton` (o `pipx install ~/Git-projects/baton`) → `baton` en el PATH.
2. **Config** — crear `.baton/config.yaml` en el workspace PROJ (o en `proj-spec`), **gitignorear `.baton/`**:
   ```yaml
   backend: github
   target: { repo: SOSkr/proj-spec, owner: SOSkr, project: 5 }
   stages: { approve: Approved, start: In Progress, ship: Deployed }
   ```
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
  - **Stamp de governance**: los cambios de estado del prune (cerrar/reclasificar) deben aplicar `config.stamp_label` (reusar los comandos ya stampeados `advance`/`close`), para que **también** queden flaggeados para revisión del usuario — igual que cualquier cambio del agente.
- **Tier 2 (richer — el "pre-compile" del usuario)**: al crear/revisar, guardar un **staleness fingerprint** por idea: `{assumptions clave, componentes/decisiones/files referenciados, depends-on, claim en 1 línea}`. El fingerprint es **estable** (describe la idea); la **realidad se mueve** (decisiones/código nuevos) → prune compara fingerprint vs realidad sin re-leer todo. Más inteligente, pero cuesta generar el fingerprint (una vez por idea, al intake). Hacerlo si el Tier 1 no alcanza.

## Notas de estado
- Repo baton: local, sin remote todavía (crear en GitHub en P4 / cuando se quiera pushear).
- `agent-skills` sigue con las `idea-*` en vivo para PROJ — no tocar hasta el cutover.
- P3 (Plane) sin arrancar: si PROJ migra a Plane (ver decisión de tracker pendiente), es el trigger.
