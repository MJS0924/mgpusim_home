// Package timingconfig contains the configuration for the timing simulation.
package timingconfig

import (
	"fmt"

	"github.com/sarchlab/akita/v4/mem/mem"
	"github.com/sarchlab/akita/v4/mem/vm"
	"github.com/sarchlab/akita/v4/mem/vm/mmu"
	"github.com/sarchlab/akita/v4/noc/networking/pcie"
	"github.com/sarchlab/akita/v4/sim"
	"github.com/sarchlab/akita/v4/simulation"
	"github.com/sarchlab/mgpusim/v4/amd/driver"
	"github.com/sarchlab/mgpusim/v4/amd/samples/runner/timingconfig/r9nano"
)

// Builder builds a hardware platform for timing simulation.
type Builder struct {
	simulation *simulation.Simulation

	numGPUs               int
	numCUPerSA            int
	numSAPerGPU           int
	cpuMemSize            uint64
	gpuMemSize            uint64
	log2PageSize          uint64
	log2CacheBlockSize    uint64
	log2CoherenceUnitSize uint64
	useMagicMemoryCopy    bool
	pageMigrationPolicy   uint64
	coherenceDirectory    uint64
	sdNumBanks            int
	sdLog2NumSubEntry     uint64
	sdByteSize            uint64
	sdDisableRSB          bool
	sdDisableCBF          bool
	sdParallelBankSearch  bool
	mgdRegionSize         uint64
	recHalfSet            bool

	platform          *sim.Domain
	globalStorage     *mem.Storage
	rdmaAddressMapper *mem.BankedAddressPortMapper
	idealDirectory    bool
}

// MakeBuilder creates a new Builder with default parameters.
func MakeBuilder() Builder {
	return Builder{
		numGPUs:            1,
		numCUPerSA:         4,
		numSAPerGPU:        16,
		cpuMemSize:         4 * mem.GB,
		gpuMemSize:         4 * mem.GB,
		log2PageSize:       12,
		useMagicMemoryCopy: false,
		sdNumBanks:         5,
		sdLog2NumSubEntry:  2,
		sdByteSize:         512 * mem.KB,
		mgdRegionSize:      1024,
	}
}

// WithSimulation sets the simulation to use.
func (b Builder) WithSimulation(sim *simulation.Simulation) Builder {
	b.simulation = sim
	return b
}

// WithNumGPUs sets the number of GPUs to simulate.
func (b Builder) WithNumGPUs(numGPUs int) Builder {
	b.numGPUs = numGPUs
	return b
}

// WithMagicMemoryCopy sets whether to use the magic memory copy middleware.
func (b Builder) WithMagicMemoryCopy() Builder {
	b.useMagicMemoryCopy = true
	return b
}

func (b Builder) WithLog2PageSize(size uint64) Builder {
	b.log2PageSize = size
	return b
}

func (b Builder) WithLog2CacheBlockSize(size uint64) Builder {
	b.log2CacheBlockSize = size
	return b
}

func (b Builder) WithLog2CoherenceUnitSize(size uint64) Builder {
	b.log2CoherenceUnitSize = size
	return b
}

func (b Builder) WithPageMigrationPolicy(policy uint64) Builder {
	b.pageMigrationPolicy = policy
	return b
}

func (b Builder) WithCoherenceDirectory(dir uint64) Builder {
	b.coherenceDirectory = dir
	return b
}

func (b Builder) WithIdealDirectory(bo bool) Builder {
	b.idealDirectory = bo
	return b
}

func (b Builder) WithSDNumBanks(n int) Builder {
	b.sdNumBanks = n
	return b
}

func (b Builder) WithSDLog2NumSubEntry(n uint64) Builder {
	b.sdLog2NumSubEntry = n
	return b
}

func (b Builder) WithSDByteSize(size uint64) Builder {
	b.sdByteSize = size
	return b
}

func (b Builder) WithSDDisableRSB(v bool) Builder {
	b.sdDisableRSB = v
	return b
}

func (b Builder) WithSDDisableCBF(v bool) Builder {
	b.sdDisableCBF = v
	return b
}

func (b Builder) WithSDParallelBankSearch(v bool) Builder {
	b.sdParallelBankSearch = v
	return b
}

func (b Builder) WithMGDRegionSize(bytes uint64) Builder {
	b.mgdRegionSize = bytes
	return b
}

// WithRECHalfSet halves REC's number of sets to reflect REC's 2x entry-size
// hardware overhead.
func (b Builder) WithRECHalfSet(v bool) Builder {
	b.recHalfSet = v
	return b
}

// Build builds the hardware platform.
func (b Builder) Build() *sim.Domain {
	b.cpuGPUMemSizeMustEqual()

	b.platform = &sim.Domain{}

	b.globalStorage = mem.NewStorage(
		uint64(b.numGPUs+1)*b.gpuMemSize + b.cpuMemSize)

	mmuComp, pageTable := b.createMMU()
	gpuDriver := b.buildGPUDriver(pageTable)

	gpuBuilder := b.createGPUBuilder(gpuDriver, mmuComp)
	pcieConnector, rootComplexID :=
		b.createConnection(gpuDriver, mmuComp)

	mmuComp.MigrationServiceProvider = gpuDriver.GetPortByName("MMU").AsRemote()

	b.createRDMAAddrTable()
	pmcAddressTable := b.createPMCPageTable()

	b.createGPUs(
		rootComplexID, pcieConnector,
		gpuBuilder, gpuDriver,
		pmcAddressTable)

	pcieConnector.EstablishRoute()

	return b.platform
}

func (b *Builder) cpuGPUMemSizeMustEqual() {
	if b.cpuMemSize != b.gpuMemSize {
		panic("currently only support cpuMemSize == gpuMemSize")
	}
}

func (b *Builder) createMMU() (*mmu.Comp, vm.LevelPageTable) {
	pageTable := vm.NewLevelPageTable(b.log2PageSize, 6, "MMU.PT")
	mmuBuilder := mmu.MakeBuilder().
		WithEngine(b.simulation.GetEngine()).
		WithFreq(1 * sim.GHz).
		WithPageWalkingLatency(100).
		WithLog2PageSize(b.log2PageSize).
		WithPageTable(pageTable).
		WithPageMigrationPolicy(b.pageMigrationPolicy)

	mmuComponent := mmuBuilder.Build("MMU")

	b.simulation.RegisterComponent(mmuComponent)

	return mmuComponent, pageTable
}

func (b *Builder) buildGPUDriver(
	pageTable vm.LevelPageTable,
) *driver.Driver {
	gpuDriverBuilder := driver.MakeBuilder()

	if b.useMagicMemoryCopy {
		gpuDriverBuilder = gpuDriverBuilder.WithMagicMemoryCopyMiddleware()
	}

	gpuDriver := gpuDriverBuilder.
		WithEngine(b.simulation.GetEngine()).
		WithPageTable(pageTable).
		WithLog2PageSize(b.log2PageSize).
		WithLog2CacheLineSize(b.log2CacheBlockSize).
		WithGlobalStorage(b.globalStorage).
		WithD2HCycles(8500).
		WithH2DCycles(14500).
		WithVisTracer(b.simulation.GetVisTracer()).
		WithPageMigrationPolicy(b.pageMigrationPolicy).
		Build("Driver")

	b.simulation.RegisterComponent(gpuDriver)

	return gpuDriver
}

func (b *Builder) createGPUBuilder(
	gpuDriver *driver.Driver,
	mmuComponent *mmu.Comp,
) r9nano.Builder {
	gpuBuilder := r9nano.MakeBuilder().
		WithFreq(1 * sim.GHz).
		WithSimulation(b.simulation).
		WithMMU(mmuComponent).
		WithNumCUPerShaderArray(b.numCUPerSA).
		WithNumShaderArray(b.numSAPerGPU).
		WithNumMemoryBank(16).
		// WithLog2MemoryBankInterleavingSize(7).
		WithLog2MemoryBankInterleavingSize(b.log2CacheBlockSize + b.log2CoherenceUnitSize + 1).
		WithLog2PageSize(b.log2PageSize).
		WithLog2CacheLineSize(b.log2CacheBlockSize).
		WithLog2CoherenceUnitSize(b.log2CoherenceUnitSize).
		WithGlobalStorage(b.globalStorage).
		WithDriver(gpuDriver).
		WithPageMigrationPolicy(b.pageMigrationPolicy).
		WithCoherenceDirectory(b.coherenceDirectory).
		WithIdealDirectory(b.idealDirectory).
		WithCohDirSize(b.sdByteSize).
		WithSDNumBanks(b.sdNumBanks).
		WithSDLog2NumSubEntry(b.sdLog2NumSubEntry).
		WithSDDisableRSB(b.sdDisableRSB).
		WithSDDisableCBF(b.sdDisableCBF).
		WithSDParallelBankSearch(b.sdParallelBankSearch).
		WithMGDRegionSize(b.mgdRegionSize).
		WithRECHalfSet(b.recHalfSet)
	fmt.Printf("[r9nano Builder]\tCreating GPU Builder with log2CacheLineSize %d, log2PageSize %d coherenceDirectory %d.\n",
		b.log2CacheBlockSize, b.log2PageSize, b.coherenceDirectory)

	b.createRDMAAddressMapper()

	// gpuBuilder = b.setMemTracer(gpuBuilder)
	// gpuBuilder = b.setISADebugger(gpuBuilder)

	return gpuBuilder
}

func (b *Builder) createGPUs(
	rootComplexID int,
	pcieConnector *pcie.Connector,
	gpuBuilder r9nano.Builder,
	gpuDriver *driver.Driver,
	pmcAddressTable *mem.BankedAddressPortMapper,
) {
	lastSwitchID := rootComplexID
	for i := 1; i < b.numGPUs+1; i++ {
		if i%2 == 1 {
			lastSwitchID = pcieConnector.AddSwitch(rootComplexID)
		}

		fmt.Printf("\nCreate GPU %d\n", i)
		b.createGPU(i, gpuBuilder, gpuDriver, pmcAddressTable,
			pcieConnector, lastSwitchID)

	}
}

func (b *Builder) createPMCPageTable() *mem.BankedAddressPortMapper {
	pmcAddressTable := new(mem.BankedAddressPortMapper)
	pmcAddressTable.BankSize = 4 * mem.GB
	pmcAddressTable.LowModules = append(pmcAddressTable.LowModules, "")
	return pmcAddressTable
}

func (b *Builder) createRDMAAddrTable() *mem.BankedAddressPortMapper {
	rdmaAddressTable := new(mem.BankedAddressPortMapper)
	rdmaAddressTable.BankSize = 4 * mem.GB
	rdmaAddressTable.LowModules = append(rdmaAddressTable.LowModules, "")
	return rdmaAddressTable
}

func (b *Builder) createConnection(
	gpuDriver *driver.Driver,
	mmuComponent *mmu.Comp,
) (*pcie.Connector, int) {
	// connection := sim.NewDirectConnection(engine)
	// connection := noc.NewFixedBandwidthConnection(32, engine, 1*sim.GHz)
	// connection.SrcBufferCapacity = 40960000
	pcieConnector := pcie.NewConnector().
		WithEngine(b.simulation.GetEngine()).
		WithVersion(4, 16).
		WithSwitchLatency(140)

	pcieConnector.CreateNetwork("PCIe")
	rootComplexID := pcieConnector.AddRootComplex(
		[]sim.Port{
			gpuDriver.GetPortByName("GPU"),
			gpuDriver.GetPortByName("MMU"),
			mmuComponent.GetPortByName("Migration"),
			mmuComponent.GetPortByName("Top"),
		})

	return pcieConnector, rootComplexID
}

func (b *Builder) createRDMAAddressMapper() {
	b.rdmaAddressMapper = new(mem.BankedAddressPortMapper)
	b.rdmaAddressMapper.BankSize = b.gpuMemSize
	b.rdmaAddressMapper.LowModules = append(b.rdmaAddressMapper.LowModules,
		sim.RemotePort("CPU"))
}

func (b *Builder) createGPU(
	index int,
	gpuBuilder r9nano.Builder,
	gpuDriver *driver.Driver,
	pmcAddressTable *mem.BankedAddressPortMapper,
	pcieConnector *pcie.Connector,
	pcieSwitchID int,
) *sim.Domain {
	name := fmt.Sprintf("GPU[%d]", index)
	memAddrOffset := uint64(index) * 4 * mem.GB
	gpu := gpuBuilder.
		WithGPUID(uint64(index)).
		WithMemAddrOffset(memAddrOffset).
		WithRDMAAddressMapper(b.rdmaAddressMapper).
		Build(name)

	gpuDriver.RegisterGPU(
		gpu.GetPortByName("CommandProcessor"),
		gpu.GetPortByName("PageMigrationController"),
		driver.DeviceProperties{
			CUCount:  b.numCUPerSA * b.numSAPerGPU,
			DRAMSize: 4 * mem.GB,
		},
	)
	// gpu.CommandProcessor.Driver = gpuDriver.GetPortByName("GPU")

	b.configRDMAEngine(gpu)
	// b.configPMC(gpu, gpuDriver, pmcAddressTable)

	pcieConnector.PlugInDevice(pcieSwitchID, gpu.Ports())

	// b.gpus = append(b.gpus, gpu)

	return gpu
}

func (b *Builder) configRDMAEngine(
	gpu *sim.Domain,
) {
	b.rdmaAddressMapper.LowModules = append(
		b.rdmaAddressMapper.LowModules,
		gpu.GetPortByName("RDMAData").AsRemote())
}

// func (b *Builder) configPMC(
// 	gpu *GPU,
// 	gpuDriver *driver.Driver,
// 	addrTable *mem.BankedAddressPortMapper,
// ) {
// 	gpu.PMC.RemotePMCAddressTable = addrTable
// 	addrTable.LowModules = append(
// 		addrTable.LowModules,
// 		gpu.PMC.GetPortByName("Remote").AsRemote())
// 	gpuDriver.RemotePMCPorts = append(
// 		gpuDriver.RemotePMCPorts, gpu.PMC.GetPortByName("Remote"))
// }
