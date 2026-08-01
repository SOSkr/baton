# Elegir el backend del board

**Decisión: Kanboard.** Tomada el 2026-08-01, midiendo — no leyendo documentación.
Este documento existe para que nadie repita la investigación, y para que quien no esté
de acuerdo discuta contra datos y no contra una preferencia.

## Por qué se abrió la pregunta

Plane guarda cuerpos y comentarios como HTML de TipTap. Eso costó cuatro items en un
solo día (BATON-3, 7, 15, 18), y ninguno era el mismo bug: texto que desaparecía al
guardar, marcado que volvía en la lectura, el cuerpo deformándose solo, el estado
elegido por orden en vez de por nombre.

El detonante fue medir esto:

```
BATON-2   antes de abrirlo en el navegador:   2193 bytes, markdown intacto
          después de abrirlo, SIN editar:      8761 bytes, HTML del editor
BATON-3   control, nunca abierto:              idéntico
```

**Abrir un item lo reescribe.** No hace falta editarlo. Y como `baton body` reescribe lo
que leyó, cada corrección de un criterio hornea la pérdida.

## El filtro, en orden

Aplicado en este orden porque descarta barato antes que caro.

**Requisito** — no se compara, se cumple o el candidato no sirve:

- Estados nombrados, ordenados y modificables **por API**. `advance`, `approve`,
  `verify` y `ship` resuelven un nombre de columna, y el gate de verify compara
  posiciones en el orden del board.

**Criterios de decisión**, fijados por el mantenedor:

1. API de lectura y escritura
2. Multiproyecto: varios proyectos con una sola credencial
3. Markdown que vuelve como se escribió — **incluso después de que un humano abra el
   item en la UI**

**Informativo**: peso en tokens, épicas nativas.

## Candidatos y por qué cayeron

| Candidato | Cae por |
|---|---|
| devaslanphp/project-management | **no tiene API**: `routes/api.php` es el stub por defecto de Laravel |
| Huly | la API **son sus paquetes npm**; los cuatro clientes que existen usan el SDK, ninguno habla HTTP |
| Vikunja | su editor llama `editor.getHTML()` y guarda eso: **mismo defecto que Plane** |
| GitHub Projects | descartado por el mantenedor, por multiproyecto — ya lo usó |
| Gitea | **sin API de projects**: pedida desde 2021 (#14299), cuatro PRs abiertos sin mergear |
| OpenProject | 191 coincidencias de CKEditor: entra con la misma sospecha que Vikunja |

El patrón: **las apps modernas usan editores de texto rico y guardan HTML**. Las que
guardan markdown crudo son las orientadas a desarrolladores, y esas fallan en otra cosa.

## Los dos finalistas, medidos en vivo

Levantados en Docker, escritos por API, abiertos con un navegador real y releídos.

### Ida y vuelta por API

| | Kanboard | Redmine | Plane |
|---|---|---|---|
| idéntico byte a byte | **sí** | sí, salvo `\n` → `\r\n` | no |
| `## encabezado`, `- [ ]`, tablas | sobreviven | sobreviven | se pierden |
| `<id>`, `List<T>` | sobreviven | sobreviven | se borraban |

### La prueba que ninguna documentación contesta

Abrir el item en la UI, sin editar nada, y releer por API:

```
Kanboard   sha fc729a4a43fa -> fc729a4a43fa   IDÉNTICO    221 -> 221 bytes
Redmine    sha bb6ca014e05d -> bb6ca014e05d   IDÉNTICO    233 -> 233 bytes
Plane                                          CAMBIÓ    2193 -> 8761 bytes
```

Kanboard además **renderiza** el markdown en la UI —encabezados, tabla, cita, `<id>` como
código— sin tocar lo guardado. Renderiza al mostrar, no al guardar: es exactamente la
distinción que Plane no hace.

### Lo que decidió entre los dos

Los dos pasan el requisito y los tres criterios. Cada uno tiene **un** hueco:

| | Kanboard | Redmine |
|---|---|---|
| `set_labels` — **abstracto en `BoardBase`** | nativo (`setTaskTags`, múltiples) | **no existe**: categoría de a una, o custom fields por proyecto |
| `list_groups` — **capacidad opcional** | derivable de los task links | `versions` con fecha |

El contrato ya clasificó esas dos cosas. `list_groups` está declarado opcional y con
degradación prevista: *"a backend that lacks a concept says so, instead of every backend
faking it"*. `set_labels` es abstracto: todo board lo implementa.

**El hueco de Kanboard cae donde el contrato dice que puede faltar. El de Redmine, sobre
algo obligatorio.** Y en uso, `type:` y `area:` van en cada item; las épicas, en algunos.

### Lo que cuesta leerlo, en tokens

Medido con `tiktoken` (cl100k_base) sobre el cuerpo real de BATON-2, tal como devuelve
cada backend:

```
Plane, crudo (description_html)             8761 bytes   2908 tokens
Plane, después de _strip_html                2057 bytes    539 tokens
Kanboard, crudo (= exactamente lo escrito)   2057 bytes    539 tokens
```

**El payload crudo de Plane cuesta 5.4x.** El matiz importa: baton lo limpia, así que un
agente que pasa por baton no paga esa diferencia. La paga quien lee la API directo — y
eso incluye al MCP de Plane, que devuelve `description_html` tal cual, que es el camino
que un agente usa a diario.

Los 6704 bytes de diferencia no son texto del item: son `<p class="editor-paragraph-block"
data-id="61d2c88d-...">` repetido por párrafo, con un UUID por bloque. Ninguno de esos
tokens le dice nada a quien lee.

## Lo que Kanboard cuesta

- **`baton-roadmap` sale, pero no gratis.** No hay un objeto "épica" nativo. Hay algo
  mejor de lo que parece: los **task links** relacionan tareas completas, y dos de los
  tipos que trae de fábrica son `targets milestone` / `is a milestone of`.

  Probado contra la instancia: la épica es una tarea, así que ya tiene `date_due`,
  cuerpo y comentarios; y `getAllTaskLinks` devuelve las hijas **con `is_active` y
  `column_title` en la misma respuesta**, así que el progreso es una llamada y sale de
  datos vivos — no de una lista mantenida a mano, que es lo que el contrato prohíbe.

  Lo que Kanboard no hace y Plane sí: mantener el progreso él mismo. Acá lo cuenta el
  adapter. Y queda una decisión de diseño abierta —una épica es una tarea, así que
  aparece en el tablero como cualquier otra— resuelta en BATON-22.

  **Las subtareas no sirven para esto** y conviene decirlo, porque el nombre invita: la
  API devuelve `id, title, status, time_estimated, time_spent, task_id, user_id,
  position`. Sin cuerpo, sin comentarios, sin columna, sin tags, sin prioridad, sin URL.
  Es un ítem de checklist, no una tarea.
- **JSON-RPC, no REST.** Un POST a `jsonrpc.php` con `{method, params}`. No es peor, es
  distinto, y el adapter lo absorbe.
- **Prioridad es un entero**, no un conjunto cerrado como `PRIORITIES`. Hay que mapear.

## Lo que Kanboard regala

- Un `createProject` y el proyecto ya viene con `Backlog · Ready · Work in progress ·
  Done`. Nada que sembrar.
- `priority`, `tags`, `category`, comentarios y subtareas, todos por API.
- Columnas creables, renombrables y **reordenables** por API — lo que le falta a Gitea.

## Cuándo reabrir esto

- **Gitea mergea su API de projects.** Es lo único que lo devolvería a la mesa, y es
  observable: cuatro PRs abiertos.
- **Plane deja de reescribir el cuerpo al abrirlo.** El issue upstream #9077 documenta la
  familia del problema, abierto desde mayo de 2026 sin respuesta.
- **Huly publica un CLI oficial** al nivel de `gh`. Hoy hay cuatro intentos comunitarios
  (⭐0 a ⭐3), ninguno consolidado.
