# baton — P0: inventario de skills + interfaz del CLI

> **baton** = familia de skills + CLI para el **ciclo de vida de work-items sobre un board** (GitHub Projects hoy, Plane u otro después). Genérico, backend-agnostic, publicable. Reemplaza las skills `idea-*` de PROJ.
>
> **Principio**: separar **juicio** (SKILL.md, lo hace el modelo) de **mecánica de backend** (CLI `baton`, adapter por backend + discovery). Cambiar de tracker = adapter nuevo, no reescribir skills.

---

## 1. Inventario de las skills actuales (`idea-*`) → verbos `baton`

| Skill actual | Verbo baton | Qué hace (juicio) | Ops de backend (→ CLI) |
|---|---|---|---|
| `idea-intake` | **`baton new`** | clarificar scope/servicio/prioridad; decidir spec-grade; escribir body | `create(title,body,labels)` · `add_to_board` · `set_stage(id,"Review")` |
| `idea-review` | **`baton triage`** | leer + **scorear** (5 criterios 0-5) + recomendar; postear review | `get(id,+comments)` · `list(filter)` · `comment(id,text)` · (reject→`close`) |
| `idea-approve` | **`baton advance`** (→Approved) | confirmar prioridad | `get_stage(id)` · `set_fields(id,{priority})` · `set_stage(id,"Approved")` |
| `idea-implement` | **`baton start`** (+`link`/`done`/`ship`) | identificar repo target; branch; desglosar; gate multi-parte | `set_stage(id,"In Progress"\|"Done"\|"Deployed")` · `edit_body`/`link_pr(id,pr)` |
| `idea-reject` | **`baton reject`** | confirmar reject vs defer | `comment(id,reason)` · `close(id,"not planned")` |

Utilidades extra del CLI: `baton list [--stage X] [--label Y]` · `baton show <id>` · `baton doctor` (verifica config/discovery/scopes).

**Nota**: el branch/commits/PR de `idea-implement` son ops de **git del repo target**, NO del tracker — quedan en la skill (o un helper aparte), no en el adapter del board.

---

## 2. Contrato del adapter (lo que TODO backend implementa)

El CLI expone estos comandos; cada backend (`github`, `plane`, ...) implementa la interfaz. Todo por **nombre** (discovery resuelve IDs internos).

```
create(title, body, labels[], fields{}) -> id
get(id) -> {title, body, stage, labels, fields, comments, url}
list(filter{stage?, label?, state?}) -> [items]
comment(id, text)
set_stage(id, stage_name)          # por NOMBRE; discovery resuelve el option id
get_stage(id) -> stage_name
list_stages() -> [stage_name...]   # lee los stages reales del board (stage-agnostic)
set_fields(id, {priority?, labels?, ...})
edit_body(id, new_body)            # para el checklist multi-parte
link_pr(id, pr_ref)                # github: nativo; plane: vía integración
close(id, reason)
add_to_board(id)                   # backends sin auto-add
```

---

## 3. Discovery (reemplaza los IDs hardcodeados)

Hoy las skills `idea-*` hardcodean (de `agents.md §4`): project `PVT_kwHOABGULc4BdatF`, field `PVTSSF_lAHOABGULc4BdatFzhX8ZJw`, options `Review=f75ad846`... Eso **se va**. El adapter descubre:

- **github**: dado el repo (o project number) → resolver `projectV2` → field `Status` (single-select) → sus **opciones por nombre** (Review/Approved/...). Cachear en `.baton/cache.json` opcional.
- **plane**: dado workspace+project → estados del proyecto por nombre (REST API).

Resultado: el usuario nunca copia un ID. Solo da repo/workspace; baton descubre el resto.

---

## 4. Config por proyecto (`.baton/config.yaml`)

Mínima; lo demás se descubre.

```yaml
backend: github          # github | plane
target:                  # github: repo | plane: workspace/project
  repo: SOSkr/proj-spec
  project: 5             # opcional: si no, descubre el linkeado
labels:                  # opcional: esquema de ejes
  axes: [type, service, priority, track]
stages:                  # opcional: alias verbo→stage (si el board no usa los defaults)
  approve: Approved
  start: In Progress
  ship: Deployed
```

Si `stages` no está, `advance` = "siguiente stage en el orden del board"; `approve/start/ship` mapean a defaults sensatos o preguntan.

---

## 5. Split juicio (skill) vs mecánica (CLI)

| Juicio → queda en SKILL.md (el modelo) | Mecánica → CLI `baton` |
|---|---|
| clarificar scope/servicio/prioridad | crear/mover/cerrar items |
| decidir spec-grade vs small | discovery de project/field/stages |
| **scoring del review** (criterios) | listar/leer items, comentar |
| confirmar prioridad, reject-vs-defer | linkear PR, editar body/checklist |
| razonamiento del gate multi-parte | (todo gh/GraphQL/API vive acá) |
| escribir bodies/reviews (idioma) | |

El texto de las skills deja de tener GraphQL/IDs → llama a `baton ...`.

---

## 6. PROJ-specifics a mover a config/opcional (dejar de hardcodear)

- Repo `SOSkr/proj-spec` → `config.target`.
- Labels `type:idea`/`service:{engine,platform,bridge,spec}`/`priority`/`track` → `config.labels.axes` (esquema del usuario).
- Pipeline `Review→Approved→In Progress→Done→Deployed` → descubierto del board (stage-agnostic).
- **Gate multi-`service:`** (checklist por servicio, no cerrar hasta todas marcadas) → **feature opcional** "checklist multi-parte" (algunos proyectos no lo usan).
- Doc spec-grade `docs/ideas/IDEA-N.md` → **opcional** (convención de PROJ, no del core).
- Regla de idioma (contenido en español) → **opcional/config** (idioma del proyecto).

PROJ queda como **primer consumidor** con su `.baton/config.yaml` — sigue andando igual, sin IDs hardcodeados.

---

## 7. Decisiones cerradas (2026-07-25)

- **Nombre**: `baton` (CLI + skills; verbos limpios `new/triage/advance/start/ship/reject`).
- **Adapter primero**: GitHub (PROJ lo usa hoy; Plane después = solo un adapter).
- **Lenguaje CLI**: Python + `uv`.

## 8. Próximo (P1)

Construir el CLI `baton` con adapter **GitHub** + discovery; refactorizar las 5 skills a llamarlo (PROJ sigue andando, ya config-driven, sin IDs). Luego P2 (rename/limpiar PROJ-specifics), P3 (adapter Plane), P4 (empaquetar/publicar).
