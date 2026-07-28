# ollama-plugin-cc

Delega tareas mecánicas de codificación desde [Claude Code](https://claude.com/claude-code)
a un modelo local de [Ollama](https://ollama.com), corriendo enteramente en tu
propio hardware.

Claude Code se mantiene como el orquestador — escribe la lógica de dominio, define cada
contrato de subtarea y revisa el resultado. Ollama absorbe el trabajo puramente
mecánico (código estándar, renombramientos, limpieza de código muerto, especificaciones
simples, mapeo de DTOs, descripciones de PR) en segundo plano, gratis, para que tu
contexto y tokens de Claude se dediquen únicamente al trabajo que solo Claude puede
hacer. Es el carril de delegación más barato posible — probalo antes de recurrir a un
delegado de pago por CLI.

Inspirado en la estructura de
[santiquiroz/copilot-plugin-cc](https://github.com/santiquiroz/copilot-plugin-cc),
con el que este plugin combina bien como carril de respaldo (ver
[docs/delegation-guide.md](docs/delegation-guide.md)).
**No afiliado a Ollama, Meta, Mistral, Alibaba, Zhipu/Z.ai ni Anthropic.**

> Read this in English: [README.md](README.md)

## Requisitos

- Claude Code
- [Ollama](https://ollama.com/download) instalado y corriendo localmente
- Una GPU (o suficiente RAM del sistema) para correr al menos un modelo de
  código local de ~15-25GB a velocidad usable — ver
  [Eligiendo un modelo](#eligiendo-un-modelo) abajo. También funciona solo con
  CPU, más lento.

## Instalación

En Claude Code:

```
/plugin marketplace add santiquiroz/ollama-plugin-cc
/plugin install ollama@ollama-plugin-cc
```

Luego configurá el modelo al que este plugin delega:

```
/ollama:setup
```

Esto verifica que Ollama esté instalado y corriendo, y te guía para elegir un
modelo base y construir un tag derivado con contexto acotado
(`ollama-rescue-mechanical`) — ver
[Por qué el límite de contexto](#por-qué-el-límite-de-contexto) abajo para
entender por qué ese paso importa.

## Uso

Delegación explícita:

```
/ollama:rescue remove all unused imports under src/ and fix the import order
/ollama:rescue --background generate boilerplate test specs for src/services/user-mapper.ts
/ollama:rescue --model ollama-rescue-vision describe the layout in this screenshot and scaffold a matching component
```

Delegación proactiva: el agente `ollama-rescue` se describe a sí mismo para
que Claude Code lo seleccione automáticamente para tareas mecánicas. Para
integrarlo en tus propias reglas de delegación, copiá el bloque de
[docs/claude-md-snippet.md](docs/claude-md-snippet.md) en tu `CLAUDE.md`.

Patrones de orquestación completa — la división Ollama/delegado de
pago/delegado de razonamiento, el patrón paralelo, límites de WIP,
concurrencia en una sola GPU y la cadena de fallback de disponibilidad —
están en [docs/delegation-guide.md](docs/delegation-guide.md).

## Por qué el límite de contexto (y el límite de salida)

La mayoría de los modelos de código locales actuales traen por defecto una
ventana de contexto nativa grande (100K-256K+ tokens). Ollama reserva
KV-cache proporcional a ese contexto *por defecto*, incluso para una
completación de una sola línea — en una GPU de consumo esto desborda la VRAM
y fuerza un offload pesado a CPU, haciendo cada llamada delegada mucho más
lenta de lo necesario, sin ningún beneficio (las tareas mecánicas rara vez
necesitan más que unos pocos archivos de contexto).

`/ollama:setup` corrige esto construyendo un pequeño Modelfile derivado:

```
FROM <tu modelo base elegido>
PARAMETER num_ctx 32768
PARAMETER num_predict 4096
```

...y etiquetando el resultado como `ollama-rescue-mechanical`. El agente y la
skill de este plugin solo llaman a ese tag, nunca a uno crudo recién bajado.

`num_predict` acota la longitud de SALIDA, y sirve por una razón distinta a
`num_ctx`: los modelos de razonamiento híbrido ("thinking") a veces se quedan
divagando en su traza de razonamiento y nunca llegan a una respuesta —
confirmado en la práctica con un modelo clase Qwen3.6 que registró 1800+
tokens decodificados y subiendo, a menos de 4 tok/s, en una sola solicitud
que nunca terminó. Sin un límite de salida eso se ve exactamente igual a un
cuelgue y puede durar horas; con el límite, una generación trabada corta en
unos minutos en vez de nunca. Si tus tareas delegadas son agénticas/con
tool-calling (no solo el forwarder de una sola pasada de este plugin),
preferí también un modelo base sin razonamiento (`devstral:24b` no tiene modo
"thinking" visible; `qwen3.6:27b` sí) — la traza de razonamiento es
justamente lo que tiende a descontrolarse.

## Eligiendo un modelo

Cualquier modelo capaz de programar que entre en tu VRAM funciona. Al momento
de escribir esto, estos son puntos de partida confirmados en una GPU de
consumo clase 16GB (revisá `ollama.com/library` o `ollama search <name>` por
si hay algo más nuevo — este panorama cambia rápido):

| Modelo | Tamaño aprox. | Notas |
|---|---|---|
| `devstral:24b` | ~14GB | Denso, latencia más predecible, sin modo "thinking" visible, afinado específicamente para leer código multi-archivo y escribir parches. Default recomendado para el caso de uso puramente mecánico de este plugin, y la opción más segura para uso agéntico/tool-calling en general. |
| `qwen3.6:27b` | ~17GB | Con visión — útil si algunas tareas delegadas referencian una imagen o captura de pantalla. Modelo de razonamiento híbrido; acotá `num_predict` si lo usás, ver arriba. |
| `qwen3-coder:30b` | ~18GB | MoE, ampliamente probado en la comunidad para tool-calling agéntico. |
| `glm-4.7-flash:q4_K_M` | ~19GB | MoE, descrito por sus autores como el modelo más fuerte en la clase 30B. Requiere una versión reciente de Ollama. |

Ninguno de estos necesita ser el modelo que usás para programar
interactivamente en otro lado — el caso de uso de este plugin es acotado
(mecánico, sin contexto de dominio), así que un modelo más chico/rápido que
tu driver diario suele ser mejor opción.

## Modelo de seguridad

A diferencia de un delegado CLI agéntico, `ollama run` es una **llamada de
completación de texto pura** — no tiene acceso a filesystem ni a git y no
puede ejecutar nada por su cuenta. No hay un conjunto de flags allow/deny que
configurar, porque no hay nada que el modelo pueda hacer más allá de devolver
texto: Claude (quien llama) lo aplica con sus propias herramientas Edit/Write
después de revisarlo.

Ese paso de revisión importa más acá que con un delegado de pago: los
modelos locales de este tamaño son más propensos a errores sutiles que un
modelo frontera en la nube, y a diferencia del diff ya aplicado de un CLI
agéntico, acá nada fue validado por nada más que un modelo mucho más chico.

## Problemas conocidos que este plugin mitiga

| Problema | Solución integrada |
|---|---|
| Desborde de VRAM por contexto nativo — la mayoría de los modelos traen por defecto una ventana de contexto enorme que desborda la VRAM de consumo y fuerza offload pesado a CPU | `/ollama:setup` siempre construye un tag derivado con contexto acotado (`PARAMETER num_ctx 32768` por defecto) y el agente/skill solo llaman a ese tag |
| Traza de razonamiento descontrolada en modelos "thinking" — la generación nunca converge, se ve exactamente igual a un cuelgue | `/ollama:setup` también acota `PARAMETER num_predict 4096` por defecto, así una generación trabada corta en vez de durar horas |

## Concurrencia

Si más de una sesión de Claude Code delega a la misma instancia local de
Ollama al mismo tiempo, las solicitudes se ponen en cola en vez de fallar.
Mantené todas las sesiones en el mismo modelo default
(`ollama-rescue-mechanical`) — si dos sesiones piden modelos *distintos* al
mismo tiempo, Ollama intenta mantener ambos cargados, lo cual en una tarjeta
limitada de VRAM es más lento para ambos que simplemente hacer cola detrás de
un modelo compartido. Ver
[docs/delegation-guide.md](docs/delegation-guide.md#concurrency-on-one-gpu)
para la explicación completa.

## Qué hay en el plugin

| Componente | Propósito |
|---|---|
| `agents/ollama-rescue.md` | Agente forwarder delgado — una llamada `ollama run`, salida devuelta textualmente |
| `/ollama:rescue` | Delega una tarea explícitamente (`--background`, `--wait`, `--model <tag>`) |
| `/ollama:setup` | Verifica que Ollama esté instalado/corriendo y construye el modelo con contexto acotado |
| `docs/delegation-guide.md` | Guía completa de orquestación multi-carril (Ollama + delegado de pago + delegado de razonamiento) |
| `docs/claude-md-snippet.md` | Bloque listo para copiar en CLAUDE.md, con variante solo-Ollama |
| `.codex-plugin/plugin.json` | Manifiesto de plugin para Codex CLI (instalación nativa experimental) |
| `skills/ollama-rescue/SKILL.md` | Skill para Codex — misma lógica de reenvío, Codex ejecuta la llamada de shell directamente (sin capa de subagente) |
| `docs/agents-md-snippet.md` | Bloque listo para copiar en `AGENTS.md` para usuarios de Codex |

## Codex CLI

La misma idea, para [Codex CLI](https://developers.openai.com/codex/):
delegar trabajo mecánico a un modelo local de Ollama, para que el
razonamiento de Codex se dedique solo al trabajo que únicamente él puede
hacer. Se distribuye como una **skill** de Codex
(`skills/ollama-rescue/SKILL.md`) en vez de un subagente — Codex ejecuta el
comando `ollama run ...` reenviado él mismo, ya que Codex no tiene una capa
separada de subagente/Task.

### Requisitos

- Codex CLI
- Ollama instalado, corriendo, y configurado según
  [Instalación](#instalación) arriba

### Instalación

**Manual (funcionamiento confirmado):**

```bash
mkdir -p ~/.agents/skills
cp -r skills/ollama-rescue ~/.agents/skills/ollama-rescue
```

O solo a nivel de repo: copiá en `<tu-repo>/.agents/skills/ollama-rescue/` en su lugar.

**Marketplace de plugins nativo (experimental — el sistema de plugins de
Codex es nuevo; abrí un issue si las rutas no coinciden con tu versión de
Codex CLI):**

```
codex plugin marketplace add santiquiroz/ollama-plugin-cc
```

Luego abrí el navegador de plugins (`/plugins` dentro de Codex) e instalá `ollama`.

### Uso

Codex empareja skills de forma implícita por su `description`, o podés
invocarla explícitamente. Pedí una tarea mecánica y Codex debería elegir
`ollama-rescue` por su cuenta; para integrar delegación proactiva en tus
propias instrucciones, copiá el bloque de
[docs/agents-md-snippet.md](docs/agents-md-snippet.md) en tu `AGENTS.md`.

### Modelo de seguridad

Igual que en el lado de Claude Code — ver
[Modelo de seguridad](#modelo-de-seguridad) arriba. `ollama run` no tiene
acceso a filesystem/git sin importar qué agente lo llame.

## Licencia

[MIT](LICENSE)
