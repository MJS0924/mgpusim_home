// Package runner defines how default benchmark samples are executed.
package runner

import (
	"fmt"
	"log"

	// Enable profiling
	_ "net/http/pprof"
	"os"
	"sync"

	"github.com/sarchlab/akita/v4/mem/cache/optdirectory"
	"github.com/sarchlab/akita/v4/mem/cache/superdirectory"
	"github.com/sarchlab/akita/v4/sim"
	"github.com/sarchlab/akita/v4/simulation"
	"github.com/sarchlab/akita/v4/tracing"
	"github.com/sarchlab/mgpusim/v4/amd/benchmarks"
	"github.com/sarchlab/mgpusim/v4/amd/driver"
	"github.com/sarchlab/mgpusim/v4/amd/samples/runner/emusystem"
	"github.com/sarchlab/mgpusim/v4/amd/samples/runner/timingconfig"
	"github.com/sarchlab/mgpusim/v4/amd/sampling"
	"github.com/sarchlab/mgpusim/v4/instrument/adapter"
)

type verificationPreEnablingBenchmark interface {
	benchmarks.Benchmark

	EnableVerification()
}

// Runner is a class that helps running the benchmarks in the official samples.
type Runner struct {
	simulation *simulation.Simulation
	platform   *sim.Domain
	reporter   *reporter

	Timing           bool
	Verify           bool
	Parallel         bool
	UseUnifiedMemory bool

	GPUIDs     []int
	benchmarks []benchmarks.Benchmark

	log2PageSize          uint64
	log2CacheBlockSize    uint64
	log2CoherenceUnitSize uint64
	pageMigrationPolicy   uint64
	coherenceDirectory    uint64
	idealDirectory        bool
	sdNumBanks            int
	sdLog2NumSubEntry     uint64
	sdByteSize            uint64
	sdDisableRSB          bool
	sdDisableCBF          bool
	mgdRegionSize         uint64
	recHalfSet            bool
}

// Init initializes the platform simulate
func (r *Runner) Init() *Runner {
	r.parseFlag()

	log.SetFlags(log.Llongfile | log.Ldate | log.Ltime)

	r.initSimulation()

	if r.Timing {
		r.buildTimingPlatform()
	} else {
		r.buildEmuPlatform()
	}

	r.createUnifiedGPUs()

	return r
}

func (r *Runner) initSimulation() {
	builder := simulation.MakeBuilder()

	if *parallelFlag {
		builder = builder.WithParallelEngine()
	}

	r.simulation = builder.Build()
}

func (r *Runner) buildEmuPlatform() {
	b := emusystem.MakeBuilder().
		WithSimulation(r.simulation).
		WithNumGPUs(r.GPUIDs[len(r.GPUIDs)-1])

	if *isaDebug {
		b = b.WithDebugISA()
	}

	r.platform = b.Build()
}

func (r *Runner) buildTimingPlatform() {
	fmt.Printf("Build Timing Platform\n")

	sampling.InitSampledEngine()

	b := timingconfig.MakeBuilder().
		WithSimulation(r.simulation).
		WithNumGPUs(r.GPUIDs[len(r.GPUIDs)-1]).
		WithLog2CacheBlockSize(r.log2CacheBlockSize).
		WithLog2PageSize(r.log2PageSize).
		WithLog2CoherenceUnitSize(r.log2CoherenceUnitSize).
		WithPageMigrationPolicy(r.pageMigrationPolicy).
		WithCoherenceDirectory(r.coherenceDirectory).
		WithIdealDirectory(r.idealDirectory).
		WithSDNumBanks(r.sdNumBanks).
		WithSDLog2NumSubEntry(r.sdLog2NumSubEntry).
		WithSDByteSize(r.sdByteSize).
		WithSDDisableRSB(r.sdDisableRSB).
		WithSDDisableCBF(r.sdDisableCBF).
		WithMGDRegionSize(r.mgdRegionSize).
		WithRECHalfSet(r.recHalfSet)

	if *magicMemoryCopy {
		b = b.WithMagicMemoryCopy()
	}

	r.platform = b.Build()
	r.reporter = newReporter(r.simulation)
	r.configureVisTracing()
}

func (r *Runner) configureVisTracing() {
	if !*visTracing {
		return
	}

	visTracer := r.simulation.GetVisTracer()
	for _, comp := range r.simulation.Components() {
		tracing.CollectTrace(comp.(tracing.NamedHookable), visTracer)
	}
}

func (r *Runner) createUnifiedGPUs() {
	if *unifiedGPUFlag == "" {
		return
	}

	driver := r.simulation.GetComponentByName("Driver").(*driver.Driver)
	unifiedGPUID := driver.CreateUnifiedGPU(nil, r.GPUIDs)
	r.GPUIDs = []int{unifiedGPUID}
}

// AddBenchmark adds an benchmark that the driver runs
func (r *Runner) AddBenchmark(b benchmarks.Benchmark) {
	b.SelectGPU(r.GPUIDs)
	if r.UseUnifiedMemory {
		b.SetUnifiedMemory()
	}

	r.benchmarks = append(r.benchmarks, b)
}

// AddBenchmarkWithoutSettingGPUsToUse allows for user specified GPUs for
// the benchmark to run.
func (r *Runner) AddBenchmarkWithoutSettingGPUsToUse(b benchmarks.Benchmark) {
	if r.UseUnifiedMemory {
		b.SetUnifiedMemory()
	}

	r.benchmarks = append(r.benchmarks, b)
}

// Run runs the benchmark
func (r *Runner) Run() {
	r.Driver().Run()

	var wg sync.WaitGroup
	for _, b := range r.benchmarks {
		wg.Add(1)
		go func(b benchmarks.Benchmark, wg *sync.WaitGroup) {
			if r.Verify {
				if b, ok := b.(verificationPreEnablingBenchmark); ok {
					b.EnableVerification()
				}
			}

			b.Run()

			if r.Verify {
				b.Verify()
			}
			wg.Done()
		}(b, &wg)
	}
	wg.Wait()

	if r.reporter != nil {
		r.reporter.log2BlockSize = r.log2CacheBlockSize + r.log2CoherenceUnitSize
		r.reporter.report()
	}

	r.emitCoalescabilityReports()

	r.Driver().Terminate()

	fmt.Printf("Simulation Terminate\n")

	r.simulation.Terminate()

	r.flushSuperdirectoryEventLog()
}

// flushSuperdirectoryEventLog collects all superdirectory EventLoggers and
// writes their buffered events to a parquet file.
// Output path: $EVENT_LOG_PATH if set, otherwise /tmp/superdirectory_events.parquet.
// No-ops silently if no superdirectory components are found.
func (r *Runner) flushSuperdirectoryEventLog() {
	path, set := os.LookupEnv("EVENT_LOG_PATH")
	if set && path == "" {
		// Caller explicitly disabled event logging (e.g. cmd/m1 without -enable-event-log).
		return
	}
	if path == "" {
		path = "/tmp/superdirectory_events.parquet"
	}

	var loggers []*superdirectory.EventLogger
	for _, comp := range r.simulation.Components() {
		if sd, ok := comp.(*superdirectory.Comp); ok {
			loggers = append(loggers, sd.EventLogger())
		}
	}
	if len(loggers) == 0 {
		return
	}

	sink, err := adapter.NewMotionEventSink(path)
	if err != nil {
		log.Printf("[runner] event-log: failed to create sink: %v", err)
		return
	}
	if err := sink.FlushLoggers(loggers); err != nil {
		log.Printf("[runner] event-log: flush error: %v", err)
	}
	if err := sink.Close(); err != nil {
		log.Printf("[runner] event-log: close error: %v", err)
	}
	promos, demotos := sink.Counts()
	log.Printf("[runner] event-log written: promotions=%d demotions=%d path=%s",
		promos, demotos, path)
}

// Driver returns the GPU driver used by the current runner.
func (r *Runner) Driver() *driver.Driver {
	return r.simulation.GetComponentByName("Driver").(*driver.Driver)
}

// Engine returns the event-driven simulation engine used by the current runner.
func (r *Runner) Engine() sim.Engine {
	return r.simulation.GetEngine()
}

// Simulation returns the simulation object, allowing callers to iterate
// components and register hooks after Init() but before Run().
func (r *Runner) Simulation() *simulation.Simulation {
	return r.simulation
}

// emitCoalescabilityReports calls EmitCumulativeReport on every
// optdirectory.Comp registered in the simulation. This is the end-of-sim
// hook that writes motivation_cumulative_GPU{N}.csv and prints the PHASE 0 /
// R6 exit-criterion verdict to stdout.
func (r *Runner) emitCoalescabilityReports() {
	if r.simulation == nil {
		return
	}
	for _, comp := range r.simulation.Components() {
		if cd, ok := comp.(*optdirectory.Comp); ok {
			cd.EmitCumulativeReport()
		}
	}
}
