# Mental model

> **Why ARDA exists.** Make interoperability practical for the agents people already
> use. Herdr is the shipped integration, Orca is next, and broader A2A interoperability
> is the long-term direction.

People use different agents for research, planning, writing, design, business operations,
development and execution. Connecting their complementary capabilities should be a
reusable integration, not another project for every pair of tools.

The human sets goals, boundaries and decisions. Agents are the workers; machines and
runtimes are resources. Existing environments host those agents. ARDA adds the
communication convention instead of taking over their execution or choosing their models.

## A2A is the direction; Herdr is the current implementation

The [A2A open standard](https://a2a-protocol.org/v1.0.0/) lets independently implemented
agents communicate without exposing their internal tools, memory or proprietary logic.
ARDA aims to make that model installable in systems people already use. Closed-source
products still need a supported interface or adapter.

- **Shipped and VERIFIED:** the Herdr plugin uses `arda/1` messages and Herdr's discovery
  and prompting. The [support table](../README.md#current-support-and-limitations) states
  its tested scope.
- **Next, FUTURE:** integrate [Orca](https://github.com/stablyai/orca), another system the
  creator already uses. There is no Orca adapter or Herdr-to-Orca bridge yet.
- **Long-term, FUTURE:** learn from more integrations and work toward broader
  interoperability through an installable implementation of the A2A model.

Today's task conventions are conceptually related to A2A, but the code does not implement
its data models, discovery documents, operations or bindings. See the
[implementation comparison](protocol.md#relationship-to-a2a). The diagrams below explain
the current Herdr integration and illustrative teams, not universal connectivity.

## The shift: resources organized around work

AI has changed how much one person or a small team can take on. One person can work across
the stack, run work in parallel and hand work to agents.

The old model organized resources around people. The new one organizes them around work.

```mermaid
flowchart LR
    subgraph OLD["Before: resources follow the person"]
        direction TB
        P["Developer"] --- M1["Their machine"]
        P --- S1["Their session"]
        P --- W1["Work happens where they are"]
    end
    subgraph NEW["Now: resources follow the work"]
        direction TB
        W2["Work"] --> AG["Agents with different roles"]
        AG --> RS["Any machine in the environment"]
    end
    OLD ~~~ NEW
```

| Before | Now |
| --- | --- |
| A machine belongs to a person. | A machine is a resource. |
| A session belongs to a person. | An agent is a worker. |
| Work happens where the developer is. | Work moves to the agent that fits it. |

## The problem: the human is the relay

Agents are workers now, but each one is isolated by its harness, session, machine or
runtime. When one agent needs another, a person copies context from one terminal to the
next.

```mermaid
flowchart LR
    A["Agent A<br/>implements"] -->|"copy, paste, explain"| H(("You"))
    H -->|"copy, paste, explain"| B["Agent B<br/>reviews"]
```

## The idea: one working team

```mermaid
flowchart LR
    A["Different agents<br/>Claude Code, Codex, ..."] --> T(("One working<br/>team"))
    C["Different capabilities<br/>implement, review, test, ..."] --> T
    R["Distributed resources<br/>laptop, desktop, GPU, ..."] --> T
```

[Herdr](https://herdr.dev) already brings the sessions and machines those agents run on
into one environment. ARDA is the Herdr plugin that lets the agents inside it find each
other, address each other by name, hand work over and get the results back.

```mermaid
flowchart LR
    A["Agent A<br/>implements"] -->|"arda task"| B["Agent B<br/>reviews"]
    B -->|"arda result"| A
```

## Why a team of different agents

- **They are worth having because they differ:** in model, tools, runtime, cost, speed and
  the machine they sit on. Give each piece of work to the agent it fits, not to the
  strongest agent every time.
- **The agent holding the task decides whom to ask.** It has the context. ARDA does not
  rank models or assign work; it only lets agents reach each other.
- **Name agents by role** (`@reviewer`, `@tester`), so whatever agent fills a role can
  change without changing how the team works. Agents can also say what they do
  (`arda describe`), and `arda peers` shows it.
- **Hand off with a clear contract:** what to do, what done looks like and what to send
  back. The [protocol](protocol.md#handing-over-work) lists the conventions.
- **More agents is not automatically better.** Watch whether the handoffs improve the work.

Typical roles:

| Role | Example work |
| --- | --- |
| Implementer | Builds the change. |
| Reviewer | Reviews it independently, ideally on another model. |
| Tester | Runs validation and reports pass or fail with evidence. |
| Security | Audits a change for risky patterns. |
| Researcher | Reads sources and summarizes what matters. |
| Local-model specialist | Runs heavy or private work next to a local model. |

## Herdr is the environment; ARDA lives inside it

```mermaid
flowchart TB
    subgraph HERDR["One Herdr environment"]
        direction TB
        subgraph TEAM["Agents with different capabilities"]
            direction TB
            I["implementer"] & V["reviewer"] & T["tester"] & S["specialist"] --- ARDA(["ARDA<br/>find · address<br/>hand off · reply"])
        end
        subgraph RES["Shared resources"]
            direction LR
            L["laptop"] ~~~ D["desktop"] ~~~ G["GPU workstation"] ~~~ X["remote server"]
        end
        TEAM -.->|"agents run wherever the work needs them"| RES
    end
```

Text equivalent: Herdr is the container. Inside it are agents with different roles and
the machines they can run on. ARDA is the capability that lets the agents reach each other.
Which machine an agent runs on is routing detail, handled by Herdr.

| ARDA is | ARDA is not |
| --- | --- |
| A Herdr plugin: a short-lived `arda` command that agents run | A daemon, server, database, queue or MCP server |
| Addresses and a small protocol for handing work over | A control plane, scheduler or orchestrator |
| Peer to peer: the agent with the task picks the peer | A router that decides who does what |
| Built on Herdr's discovery, routing and delivery | A second runtime beside Herdr |

## Compared with other approaches

| | Released ARDA | Relaying by hand | Plain `herdr agent prompt` |
| --- | --- | --- | --- |
| Extra message service to operate | None | None | None |
| Finds agents by name across Herdr sessions and saved machines | Yes | You do it | One Herdr server at a time |
| Task, ack, result convention | Yes | You do it | No |
| Uses the Claude Code and Codex you already run in Herdr | Yes | Yes | Yes |
| Durable message history maintained by this layer | No; agents keep their own context | No | No |

A2A is a communication standard rather than a directly interchangeable product. ARDA's
message conventions are not an A2A implementation; see [the comparison](protocol.md#relationship-to-a2a).

## Next

- [Architecture](architecture.md): what Herdr does and what ARDA does.
- [Getting started](getting-started.md): install and send a first task.
