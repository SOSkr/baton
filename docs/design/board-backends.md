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
| `list_groups` — **capacidad opcional** | no tiene | `versions` con fecha |

El contrato ya clasificó esas dos cosas. `list_groups` está declarado opcional y con
degradación prevista: *"a backend that lacks a concept says so, instead of every backend
faking it"*. `set_labels` es abstracto: todo board lo implementa.

**El hueco de Kanboard cae donde el contrato dice que puede faltar. El de Redmine, sobre
algo obligatorio.** Y en uso, `type:` y `area:` van en cada item; las épicas, en algunos.

## Lo que Kanboard cuesta

- **`baton-roadmap` no funciona** ahí. Los swimlanes son filas del tablero, no
  entregables con fecha. `baton groups` va a dar el error de capacidad ausente, que es
  el comportamiento previsto, no una falla.
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
