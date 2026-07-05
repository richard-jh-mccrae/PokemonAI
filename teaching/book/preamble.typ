// ============================================================================
//  Shared template + styled environments for the PokemonAI ML textbook
// ============================================================================

// math operators not built into Typst
#let argmax = math.op("arg max", limits: true)
#let argmin = math.op("arg min", limits: true)

#let accent   = rgb("#1f4e79")   // deep blue  — structure / key ideas
#let poke      = rgb("#0a7d5a")   // green      — Pokémon worked examples
#let contrastc = rgb("#9a5b00")   // amber      — road-not-taken / compare
#let toolc     = rgb("#5a3a91")   // purple     — toolbox tidbits
#let probc     = rgb("#333333")   // near-black — problems
#let paper     = rgb("#fbfbf9")

// ---- page + text defaults -------------------------------------------------
#let book(title: "", body) = {
  set page(
    paper: "a4",
    margin: (top: 2.4cm, bottom: 2.4cm, inside: 2.4cm, outside: 2.4cm),
    numbering: "1",
    fill: paper,
  )
  set text(font: "New Computer Modern", size: 10.5pt, lang: "en")
  set par(justify: true, leading: 0.7em, first-line-indent: 1.2em)
  show par: set block(spacing: 0.9em)
  set heading(numbering: "1.1")

  // Chapter headings (level 1): big, start a new page, accent colour.
  show heading.where(level: 1): it => {
    pagebreak(weak: true)
    set text(font: "New Computer Modern Sans", size: 20pt, fill: accent, weight: "bold")
    block(above: 1.2em, below: 0.9em)[
      #if it.numbering != none [
        #text(size: 12pt, fill: accent.lighten(20%))[Chapter #counter(heading).display("1")]
        #linebreak()
      ]
      #it.body
    ]
  }
  show heading.where(level: 2): it => {
    set text(font: "New Computer Modern Sans", size: 13pt, fill: accent, weight: "bold")
    block(above: 1.1em, below: 0.5em)[#counter(heading).display() #h(0.4em) #it.body]
  }
  show heading.where(level: 3): it => {
    set text(font: "New Computer Modern Sans", size: 11pt, fill: accent.darken(10%), weight: "bold")
    block(above: 0.9em, below: 0.3em)[#it.body]
  }

  // Links a subtle blue.
  show link: set text(fill: accent)

  body
}

// ---- callout environments -------------------------------------------------
#let callout(col, tag, title, body) = block(
  width: 100%, above: 1.0em, below: 1.0em, breakable: true,
  fill: col.lighten(90%), stroke: (left: 3pt + col), radius: 2pt,
  inset: (left: 10pt, rest: 9pt),
)[
  #text(font: "New Computer Modern Sans", size: 8pt, fill: col, weight: "bold", tracking: 0.6pt)[#upper(tag)]
  #if title != none [ #h(0.5em) #text(font: "New Computer Modern Sans", size: 9.5pt, fill: col.darken(15%), weight: "bold")[#title] ]
  #linebreak()
  #body
]

#let example(title, body)  = callout(poke,      "Pokémon example", title, body)
#let contrast(title, body) = callout(contrastc, "The road not taken", title, body)
#let toolbox(title, body)  = callout(toolc,     "Toolbox tidbit", title, body)

#let keyidea(body) = block(
  width: 100%, above: 1.0em, below: 1.0em, breakable: true,
  fill: accent.lighten(93%), stroke: 0.6pt + accent.lighten(40%), radius: 3pt, inset: 10pt,
)[
  #text(font: "New Computer Modern Sans", size: 8pt, fill: accent, weight: "bold", tracking: 0.6pt)[KEY IDEA] #linebreak()
  #body
]

#let defn(term, body) = block(width: 100%, above: 0.8em, below: 0.8em)[
  #text(weight: "bold", fill: accent)[#term. ] #body
]

// ---- problem sets ---------------------------------------------------------
// Usage: #problems("2", (
//   [statement one],
//   [statement two],
// ))
// Numbers appear as 2.1, 2.2, ... to match the answer key.
#let problems(chap, items) = {
  block(width: 100%, above: 1.3em, breakable: true,
    fill: white, stroke: (top: 1.2pt + probc, bottom: 1.2pt + probc), inset: (y: 8pt, x: 0pt))[
    #text(font: "New Computer Modern Sans", size: 12pt, fill: probc, weight: "bold")[Problems]
    #v(0.3em)
    #for (i, it) in items.enumerate() {
      block(above: 0.5em, below: 0.5em)[
        #grid(columns: (1.4em, 1fr), gutter: 0.4em,
          text(weight: "bold", fill: accent)[#chap.#(i+1)],
          it)
      ]
    }
  ]
}

// answer key entry
#let ans(label, body) = block(above: 0.5em, below: 0.5em)[
  #grid(columns: (1.7em, 1fr), gutter: 0.4em,
    text(weight: "bold", fill: poke)[#label], body)
]
