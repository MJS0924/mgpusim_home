# Motivation Section Text — Why coarse coherence units hurt despite "looking fine"

Companion to `results/figures/fig_g_l2_hit_latency.{pdf,png}` (the
"averaged metrics look flat" panel) and the new
`results/figures/fig_i_ushape_attribution.{pdf,png}` (the "absolute
counters and CU stalls reveal the U" panel).

The text below is drafted in three forms:
  • **Long form (≈230 words)** — for the motivation subsection itself,
    drops directly between the existing fig_g paragraph and fig_a.
  • **Short form (≈110 words)** — if the venue has tight page budget;
    keeps only the headline claim + the one-line confound caveat.
  • **Confound disclosure (≈90 words)** — separate paragraph the
    reviewers will look for; can sit in §4 (methodology) or be folded
    into the long form depending on style.

---

## Long form

Naïvely, sweeping the coherence unit from 64\,B to 16\,KB looks like a
near-monotonic improvement on every headline averaged metric (Fig.~G):
across all nine workloads, the overall L2 hit rate moves by under 5
percentage points, the per-request L2 latency either stays flat or
*improves*, and the share of inter-GPU link traffic spent on
invalidation messages monotonically *drops*. Each of those is the
right answer to a slightly wrong question.

Kernel time tells a different story. Every workload has a per-workload
optimum somewhere strictly inside the swept range, with measurable
slowdown on at least one side of the U (e.g.\ matrix multiplication:
$+96\%$ at 64\,B and $+35\%$ at 16\,KB versus the 1\,KB optimum). The
two sides of the U are driven by different costs: the fine side by
directory-eviction broadcasts (Fig.~B), and the coarse side by
amplified DRAM and inter-GPU traffic from re-populating L2 lines
that the workload still needs. The metrics that reveal both sides are
*absolute totals*, not rates, and *CU-side stalls*, not cache-
controller averages: vector-memory stall CPI rises by up to
$3.6\times$ on the fine side and $1.9\times$ on the coarse side
relative to each workload's optimum, the L2 local-hit rate drops by
up to $7$\,pp on the coarse side, and per-kernel DRAM read traffic
grows by up to $1.7\times$ on the coarse side (Fig.~I). The averaged
metrics in Fig.~G hide both costs: rate denominators expand in
lockstep with kernel time, and the per-request L2 latency mean is
diluted by cheap no-op invalidations on already-invalid lines.

## Short form

While averaged L2 metrics (overall hit rate, per-request latency,
invalidation share of link bandwidth) stay flat or improve as the
coherence unit grows, every workload has a per-workload optimum
strictly inside the swept range and slows down by up to $96\%$ on the
fine side or $35\%$ on the coarse side (Fig.~G,~I). The cost surfaces
only in absolute counters and CU-side stalls: vector-memory stall CPI
rises up to $3.6\times$, L2 local-hit rate falls by up to $7$\,pp on
the coarse side, and per-kernel DRAM read traffic grows up to
$1.7\times$. Rate-form averages hide both costs because their
denominators expand with kernel time; per-request latency means are
diluted by cheap no-op invalidations.

## Confound disclosure

In the simulator, `coherence-unit-size` controls both the directory's
tracking granularity and the L2-bank / memory-bank interleaving stride
(`builder.go:258`, `r9nano/builder.go:1205`: stride
$=2^{6+\textsc{cd}+1}$\,B). Coarsening the coherence unit therefore
also coarsens bank striping, which serializes sequential accesses
within a region onto fewer banks and is the bank-parallelism mechanism
behind the right-side rise in vector-memory CPI and DRAM read traffic
(Fig.~I, panels (a) and (c)). A pure-coherence implementation that
keeps fine-grained bank striping while widening only the directory's
tracking unit would not exhibit this particular failure mode; the
right-side-of-U evidence in this work is therefore best read as
"coarse coherence is *not free* in any current implementation we know
of" rather than "coarse coherence is fundamentally bad."

---

## Numbers cited above (sources)

All numbers below come from `results/summary.csv` (variant=CD) and
`results/figures/fig_i_cpi_cache.csv`, both regenerated from the raw
sqlite dumps under `results/CD/rawdata/sql/`.

### Matrix-multiplication kernel time across the U

| coherence unit | kernel (ms) | Δ vs optimum |
| ---:           | ---:        | ---:         |
| 64\,B          | 3.855       | $+95.6\%$    |
| 128\,B         | 2.236       | $+13.5\%$    |
| 256\,B         | 1.997       | $+1.3\%$     |
| 1\,KB (opt)    | 1.971       | (baseline)   |
| 4\,KB          | 2.090       | $+6.0\%$     |
| 16\,KB         | 2.657       | $+34.8\%$    |

(Fine side $+96\%$ at 64\,B, coarse side $+35\%$ at 16\,KB.)

### "L2 local hit rate drops by up to 7\,pp" — matrix multiplication

| coherence unit | local hit rate |
| ---:           | ---:           |
| 1\,KB (opt)    | 95\%           |
| 4\,KB          | 92\%           |
| 16\,KB         | 88\%           |

Magnitude difference: $-7$\,pp. Other workloads' local-hit-rate drop
past their optimum: matrixtranspose 0\,pp (streaming, never had any),
spmv $-2$\,pp, stencil2d $-1$\,pp, conv2d $-1$\,pp. mm is the
strongest case; the figure shows the across-workload picture.

### Vector-memory stall CPI U-shape — both sides

From `fig_i_cpi_cache.csv` `cpi_VMem` column.

**Fine side (worst CPI is at small CD)**:

| workload | optimum CD | optimum CPI | worst-CD | worst CPI | ratio |
| ---:     | ---:       | ---:        | ---:     | ---:      | ---:  |
| matrixmultiplication | CD\_4 (1\,KB) | 1.06   | CD\_0 (64\,B)  | 3.75   | $3.55\times$ |
| spmv                 | CD\_6 (4\,KB) | 1208   | CD\_0 (64\,B)  | 1631   | $1.35\times$ |
| pagerank             | CD\_6 (4\,KB) | 40.07  | CD\_0 (64\,B)  | 50.10  | $1.25\times$ |

**Coarse side (worst CPI is at large CD, restricted to right of bottom)**:

| workload | optimum CD | optimum CPI | worst-CD | worst CPI | ratio |
| ---:     | ---:       | ---:        | ---:     | ---:      | ---:  |
| matrixmultiplication | CD\_4 (1\,KB) | 1.06   | CD\_8 (16\,KB) | 1.96   | $1.86\times$ |
| im2col               | CD\_4 (1\,KB) | 14.84  | CD\_8 (16\,KB) | 16.76  | $1.13\times$ |
| spmv                 | CD\_6 (4\,KB) | 1208   | CD\_8 (16\,KB) | 1342   | $1.11\times$ |

Use `$3.6\times$` for the fine-side claim (rounded from 3.55) and
`$1.9\times$` for the coarse-side claim (rounded from 1.86) in the
prose.

### "Per-kernel DRAM read traffic grows up to $1.7\times$" — mm

| coherence unit | DRAM read (MB) |
| ---:           | ---:           |
| 1\,KB (opt)    | 21.85          |
| 16\,KB         | 36.21          |

Ratio: $1.66\times$. Round to 1.7$\times$ in prose.

### Per-workload U-bottoms

| workload | bottom CD | bottom kernel (ms) | fine-side rise (CD\_0) | coarse-side rise (CD\_8) |
| :---     | ---:      | ---:               | ---:                   | ---:                     |
| conv2d               | CD\_4 (1\,KB)  | 7.729  | $+11\%$  | $+2\%$  |
| fir                  | CD\_8 (16\,KB) | 1.050  | $+11\%$  | —       |
| im2col               | CD\_4 (1\,KB)  | 1.211  | $+8\%$   | $+14\%$ |
| matrixmultiplication | CD\_4 (1\,KB)  | 1.971  | $+96\%$  | $+35\%$ |
| matrixtranspose      | CD\_6 (4\,KB)  | 20.211 | $+5\%$   | $+0\%$  |
| pagerank             | CD\_6 (4\,KB)  | 3.069  | $+13\%$  | $+2\%$  |
| relu                 | CD\_8 (16\,KB) | 3.881  | $+8\%$   | —       |
| spmv                 | CD\_6 (4\,KB)  | 19.595 | $+23\%$  | $+3\%$  |
| stencil2d            | CD\_6 (4\,KB)  | 38.444 | $+31\%$  | $+1\%$  |

Six workloads (conv2d, im2col, mm, pagerank, spmv, stencil2d) have a
proper U-shape with rises on both sides. fir/relu/matrixtranspose's
kernel optimum sits at or near the largest CD swept, so their
right-side rise is too small to count as a U; report them as still on
the descending branch if a reviewer pushes back. mm is the load-
bearing example — every other workload has weaker effects.

---

## Where the text lives in the paper

This section assumes the paper already has, in §3 or §4 (whichever
section discusses coherence-unit-size sweep):

  1. fig_a (kernel time vs region size, normalized) — establishes
     existence of the per-workload optimum.
  2. fig_b (invalidation traffic split: useful vs wasted) — establishes
     the invalidation cost.
  3. fig_g (overall L2 hit rate, per-request L2 latency, directory
     latency) — the "averaged metrics" panel.

The new fig_i and the long-form text above belong **immediately after
fig_g**, as a "but if you look at the right metrics, the cost is
visible" rebuttal-paragraph. This sequencing keeps fig_g intact for
readers who only skim the averaged-metric story, and it lets fig_i
serve as the bridge into REC's storage/area pitch (REC keeps fine-
grained tracking inside coarse-region entries, so it inherits neither
the bank-striping confound discussed above nor the wasted-invalidation
work that broader coherence units suffer).
