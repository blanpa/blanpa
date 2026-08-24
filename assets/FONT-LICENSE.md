# JetBrains Mono

`jetbrains-mono-400.woff2` and `jetbrains-mono-600.woff2` are subsets of
JetBrains Mono, designed by Philipp Nurullin and Konstantin Bulenkov. They are
cut down to Basic Latin, the same face blanpa.github.io serves for code and
labels.

Licensed under the SIL Open Font License 1.1:
https://openfontlicense.org/

Upstream: https://github.com/JetBrains/JetBrainsMono

The files are embedded into the generated SVG cards as data URIs, because SVGs
that GitHub renders through `<img>` cannot load external resources. The card
headings need no embedded file: they use the same system serif stack the site
falls back to.
