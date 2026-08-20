# PokémonAI Handoff: Shuffle/Draw Supporter Decision

## Goal

For cards such as **Lillie's Determination** or **Harelquin**, do not decide whether to play them merely from the probability of drawing a desired card.

Compare the **expected value of resulting game states** against not playing the Supporter.

## Core Decision

```text
Current state
    |
    +-- Don't play Supporter
    +-- Play Lillie's Determination
    `-- Play Harelquin
```

For each candidate:

```text
Q(s, action) = E[V(best continuation after action)]
```

Choose:

```text
best_action = argmax Q(s, action)
```

## Chance Outcomes

For shuffle/draw actions, sample or branch over possible resulting hands:

```text
Play Supporter
    |
    +-- hand H1 -> continuation search -> V1
    +-- hand H2 -> continuation search -> V2
    +-- hand H3 -> continuation search -> V3
    `-- ...
```

Then:

```text
Q(s, Supporter) = sum(P(Hi) * V(S_Hi))
```

Use Monte Carlo sampling when enumerating every possible hand is impractical.

## Hypergeometric Probability

Existing hypergeometric calculations remain useful for exact probabilities such as:

```text
P(draw at least one required card)
```

But they should feed the chance model rather than directly decide the action.

Actual hand sampling is stronger than simple hit/miss logic because combinations matter:

```text
Rare Candy + evolution -> strong
Rare Candy alone       -> mediocre
Boss + Energy          -> potentially strong
brick                   -> weak
```

Search/value evaluation determines their downstream worth.

## Opportunity Cost

The resulting state must include all consequences:

- hand changes according to the card
- Supporter-for-turn is consumed
- deck composition changes
- newly drawn cards become available
- subsequent actions must remain legal

This naturally compares playing the Supporter against preserving the current hand and taking another line.

## Bootstrap

```text
Supporter
   -> sample resulting hand
   -> Bellman continuation search
   -> initial leaf evaluator
   -> average outcomes
```

## Mature System

```text
Supporter
   -> sample resulting hand
   -> short selective search
   -> learned V(s)
   -> average outcomes
```

Learned `P(a|s)` may identify the Supporter as promising, but it is only a **search prior**. It should not directly decide to play it.

## Guiding Rule

Do not ask only:

> What is my probability of drawing card X?

Ask:

> Compared with my alternatives, what is the expected long-term value of the states this action produces?

Ultimately:

```text
action* = argmax_a E[V(best continuation after a)]
```
