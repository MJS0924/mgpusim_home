// Package r9nano contains the configuration of GPUs similar to AMD Radeon R9
// Nano.
package r9nano

import (
	"fmt"

	"github.com/sarchlab/akita/v4/mem/cache/MGD"
	"github.com/sarchlab/akita/v4/mem/cache/REC"
	"github.com/sarchlab/akita/v4/mem/cache/largeblkcache"
	"github.com/sarchlab/akita/v4/mem/cache/optdirectory"
	"github.com/sarchlab/akita/v4/mem/cache/superdirectory"
	"github.com/sarchlab/akita/v4/mem/cache/writebackcoh"

	"github.com/sarchlab/akita/v4/mem/dram"
	"github.com/sarchlab/akita/v4/mem/idealmemcontroller"
	"github.com/sarchlab/akita/v4/mem/mem"
	"github.com/sarchlab/akita/v4/mem/vm"
	"github.com/sarchlab/akita/v4/mem/vm/gmmu"
	"github.com/sarchlab/akita/v4/mem/vm/mmu"
	"github.com/sarchlab/akita/v4/mem/vm/tlb"
	"github.com/sarchlab/akita/v4/sim"
	"github.com/sarchlab/akita/v4/sim/directconnection"
	"github.com/sarchlab/akita/v4/simulation"
	"github.com/sarchlab/mgpusim/v4/amd/driver"
	"github.com/sarchlab/mgpusim/v4/amd/samples/runner/timingconfig/shaderarray"
	"github.com/sarchlab/mgpusim/v4/amd/timing/cp"
	"github.com/sarchlab/mgpusim/v4/amd/timing/pagemigrationcontroller"
	"github.com/sarchlab/mgpusim/v4/amd/timing/rdma"
)

// Builder builds a hardware platform for timing simulation.
type Builder struct {
	simulation *simulation.Simulation

	gpuID                          uint64
	name                           string
	freq                           sim.Freq
	numCUPerShaderArray            int
	numShaderArray                 int
	l2CacheSize                    uint64
	numMemoryBank                  int
	log2CacheLineSize              uint64
	log2PageSize                   uint64
	log2CoherenceUnitSize          uint64
	log2MemoryBankInterleavingSize uint64
	cohDirSize                     uint64 // 실제 크기는 아니고 커버하는 범위가 될 것
	sdNumBanks                     int
	sdLog2NumSubEntry              uint64
	sdDisableRSB                   bool
	sdDisableCBF                   bool
	sdParallelBankSearch           bool
	mgdRegionSize                  uint64
	recHalfSet                     bool
	memAddrOffset                  uint64
	dramSize                       uint64
	globalStorage                  *mem.Storage
	mmu                            *mmu.Comp
	rdmaAddressMapper              mem.AddressToPortMapper
	rdmaLowModuleFinder            *mem.InterleavedAddressPortMapper
	rdmaInvLowModuleFinder         *mem.InterleavedAddressPortMapper
	rdmaBottomAddressMapper        *mem.InterleavedAddressPortMapper
	driver                         *driver.Driver

	gpu        *sim.Domain
	cp         *cp.CommandProcessor
	rdmaEngine *rdma.Comp
	pmc        *pagemigrationcontroller.PageMigrationController
	dmaEngine  *cp.DMAEngine
	sas        []*sim.Domain
	// cohDir     *coherence.Comp
	cohDir   *optdirectory.Comp   // b.coherenceDirectory == 0 || 1 || 4
	superDir *superdirectory.Comp // b.coherenceDirectory == 2
	recDir   *REC.Comp            // b.coherenceDirectory == 3
	mgdDir   *MGD.Comp            // b.coherenceDirectory == 5
	// l2Caches []*writeback.Comp
	l2Caches       []*writebackcoh.Comp  // b.coherenceDirectory == 0 || 2 || 3 || 4
	largeBlkCaches []*largeblkcache.Comp // b.coherenceDirectory == 1

	l2TLBs                          []*tlb.Comp
	drams                           []sim.Component
	internalConn                    *directconnection.Comp
	l2ToDramConnection              *directconnection.Comp
	l1AddressMapper                 *mem.InterleavedAddressPortMapper
	cohDirAddressMapper             *mem.InterleavedAddressPortMapper
	cohDirAddressMapperForRemoteReq *mem.InterleavedAddressPortMapper
	l1TLBAddressMapper              *mem.SinglePortMapper
	pmcAddressMapper                mem.AddressToPortMapper
	gmmu                            *gmmu.Comp

	accessCounter       *map[vm.PID]map[uint64]uint8
	dirtyMask           *[]map[vm.PID]map[uint64][]uint8
	readMask            *[]map[vm.PID]map[uint64][]uint8
	pageMigrationPolicy uint64
	coherenceDirectory  uint64
	idealDirectory      bool
}

// MakeBuilder creates a new builder.
func MakeBuilder() Builder {
	return Builder{
		freq:                           1 * sim.GHz,
		numCUPerShaderArray:            4,
		numShaderArray:                 16,
		l2CacheSize:                    2 * mem.MB,
		numMemoryBank:                  16,
		log2CacheLineSize:              6,
		log2PageSize:                   12,
		log2MemoryBankInterleavingSize: 7,
		cohDirSize:                     512 * mem.KB,
		sdNumBanks:                     5,
		sdLog2NumSubEntry:              2,
		mgdRegionSize:                  1024,
		memAddrOffset:                  0,
		dramSize:                       4 * mem.GB,
		// l2CacheSize:                    2 * mem.MB,
		// cohDirSize:                     512 * mem.KB,
	}
}

// WithSimulation sets the simulation to use.
func (b Builder) WithSimulation(sim *simulation.Simulation) Builder {
	b.simulation = sim
	return b
}

// WithGPUID sets the GPU ID to use.
func (b Builder) WithGPUID(id uint64) Builder {
	b.gpuID = id
	return b
}

// WithFreq sets the frequency that the GPU works at.
func (b Builder) WithFreq(freq sim.Freq) Builder {
	b.freq = freq
	return b
}

// WithLog2MemoryBankInterleavingSize sets the log2 memory bank interleaving
// size.
func (b Builder) WithLog2MemoryBankInterleavingSize(size uint64) Builder {
	b.log2MemoryBankInterleavingSize = size
	return b
}

// WithLog2CacheLineSize sets the log2 cache line size.
func (b Builder) WithLog2CacheLineSize(size uint64) Builder {
	b.log2CacheLineSize = size
	return b
}

// WithLog2PageSize sets the log2 page size.
func (b Builder) WithLog2PageSize(size uint64) Builder {
	b.log2PageSize = size
	return b
}

func (b Builder) WithLog2CoherenceUnitSize(size uint64) Builder {
	b.log2CoherenceUnitSize = size
	return b
}

// WithMemAddrOffset sets the memory address offset.
func (b Builder) WithMemAddrOffset(offset uint64) Builder {
	b.memAddrOffset = offset
	return b
}

// WithNumCUPerShaderArray sets the number of CUs per shader array.
func (b Builder) WithNumCUPerShaderArray(numCUPerShaderArray int) Builder {
	b.numCUPerShaderArray = numCUPerShaderArray
	return b
}

// WithNumShaderArray sets the number of shader arrays.
func (b Builder) WithNumShaderArray(numShaderArray int) Builder {
	b.numShaderArray = numShaderArray
	return b
}

// WithL2CacheSize sets the size of the L2 cache.
func (b Builder) WithL2CacheSize(size uint64) Builder {
	b.l2CacheSize = size
	return b
}

// WithNumMemoryBank sets the number of memory banks.
func (b Builder) WithNumMemoryBank(numMemoryBank int) Builder {
	b.numMemoryBank = numMemoryBank
	return b
}

// WithDramSize sets the size of the DRAM.
func (b Builder) WithDramSize(size uint64) Builder {
	b.dramSize = size
	return b
}

// WithMMU sets the MMU that can provide the ultimate address translation.
func (b Builder) WithMMU(mmu *mmu.Comp) Builder {
	b.mmu = mmu
	return b
}

// WithGlobalStorage sets the global storage that can provide the ultimate address translation.
func (b Builder) WithGlobalStorage(
	globalStorage *mem.Storage,
) Builder {
	b.globalStorage = globalStorage
	return b
}

// WithDRAMSize sets the size of the DRAM.
func (b Builder) WithDRAMSize(size uint64) Builder {
	b.dramSize = size
	return b
}

// WithRDMAAddressMapper sets the RDMA address mapper.
func (b Builder) WithRDMAAddressMapper(mapper mem.AddressToPortMapper) Builder {
	b.rdmaAddressMapper = mapper
	return b
}

// WithRDMAAddressMapper sets the RDMA address mapper.
func (b Builder) WithDriver(driver *driver.Driver) Builder {
	b.driver = driver
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

func (b Builder) WithCohDirSize(size uint64) Builder {
	b.cohDirSize = size
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
func (b Builder) Build(name string) *sim.Domain {
	b.name = name
	b.gpu = sim.NewDomain(name)

	b.l1AddressMapper = mem.NewInterleavedAddressPortMapper(
		1 << b.log2MemoryBankInterleavingSize,
	)
	b.l1AddressMapper.UseAddressSpaceLimitation = false

	b.cohDirAddressMapper = mem.NewInterleavedAddressPortMapper(
		1 << b.log2MemoryBankInterleavingSize,
	)
	b.cohDirAddressMapper.UseAddressSpaceLimitation = false

	b.cohDirAddressMapperForRemoteReq = mem.NewInterleavedAddressPortMapper(
		1 << b.log2MemoryBankInterleavingSize,
	)
	b.cohDirAddressMapperForRemoteReq.UseAddressSpaceLimitation = false

	b.rdmaLowModuleFinder = mem.NewInterleavedAddressPortMapper(
		1 << b.log2MemoryBankInterleavingSize,
	)
	b.rdmaLowModuleFinder.UseAddressSpaceLimitation = false

	b.rdmaInvLowModuleFinder = mem.NewInterleavedAddressPortMapper(
		1 << b.log2MemoryBankInterleavingSize,
	)
	b.rdmaInvLowModuleFinder.UseAddressSpaceLimitation = false

	b.rdmaBottomAddressMapper = mem.NewInterleavedAddressPortMapper(
		1 << b.log2MemoryBankInterleavingSize,
	)
	b.rdmaBottomAddressMapper.UseAddressSpaceLimitation = false

	b.l1TLBAddressMapper = &mem.SinglePortMapper{}

	b.accessCounter = &map[vm.PID]map[uint64]uint8{}
	targetLen := int(b.gpuID)
	if len(b.driver.DirtyMask) < targetLen {
		diff := targetLen - len(b.driver.DirtyMask)
		for i := 0; i < diff; i++ {
			b.driver.DirtyMask = append(b.driver.DirtyMask, make(map[vm.PID]map[uint64][]uint8))
			b.driver.ReadMask = append(b.driver.ReadMask, make(map[vm.PID]map[uint64][]uint8))
		}
	}
	b.dirtyMask = &(b.driver.DirtyMask)
	b.readMask = &(b.driver.ReadMask)

	if b.dirtyMask == nil {
		fmt.Printf("[r9nanoBuilder]\tWarning: GPU %d has no dirty mask set.\n", b.gpuID)
	}
	if b.readMask == nil {
		fmt.Printf("[r9nanoBuilder]\tWarning: GPU %d has no read mask set.\n", b.gpuID)
	}

	b.buildSAs()
	b.buildDRAMControllers()
	b.buildCoherenceDirectory()
	b.buildL2Caches()
	b.buildCP()
	b.buildGMMU()
	b.buildL2TLB()

	b.connectCP()
	b.connectL2AndDRAM()
	b.connectL1ToCohDir()
	b.connectCohDirToL2()
	b.connectL1TLBToL2TLB()
	b.connectL2TLBToGMMU()

	b.populateExternalPorts()

	return b.gpu
}

func (b *Builder) populateExternalPorts() {
	b.gpu.AddPort("CommandProcessor", b.cp.ToDriver)
	b.gpu.AddPort("RDMARequest", b.rdmaEngine.RDMARequestOutside)
	b.gpu.AddPort("RDMAData", b.rdmaEngine.RDMADataOutside)

	b.gpu.AddPort("PageMigrationController",
		b.pmc.GetPortByName("Remote"))

	b.gpu.AddPort("Translation", b.gmmu.GetPortByName("Bottom"))
}

func (b *Builder) connectCP() {
	b.internalConn = directconnection.MakeBuilder().
		WithEngine(b.simulation.GetEngine()).
		WithFreq(b.freq).
		Build(b.name + ".InternalConn")
	b.simulation.RegisterComponent(b.internalConn)

	b.internalConn.PlugIn(b.cp.ToDMA)
	b.internalConn.PlugIn(b.cp.ToCohDir)
	b.internalConn.PlugIn(b.cp.ToCaches)
	b.internalConn.PlugIn(b.cp.ToCUs)
	b.internalConn.PlugIn(b.cp.ToTLBs)
	b.internalConn.PlugIn(b.cp.ToAddressTranslators)
	b.internalConn.PlugIn(b.cp.ToRDMA)
	b.internalConn.PlugIn(b.cp.ToPMC)
	b.internalConn.PlugIn(b.cp.ToGMMU)
	b.internalConn.PlugIn(b.cp.ToROBs)

	b.cp.RDMA = b.rdmaEngine.CtrlPort
	b.internalConn.PlugIn(b.cp.RDMA)

	b.cp.DMAEngine = b.dmaEngine.ToCP
	b.internalConn.PlugIn(b.dmaEngine.ToCP)

	pmcControlPort := b.pmc.GetPortByName("Control")
	b.cp.PMC = pmcControlPort
	b.internalConn.PlugIn(pmcControlPort)

	gmmuControlPort := b.gmmu.GetPortByName("Control")
	b.cp.GMMU = gmmuControlPort
	b.internalConn.PlugIn(gmmuControlPort)

	b.connectCPWithCUs()
	b.connectCPWithAddressTranslators()
	b.connectCPWithTLBs()
	b.connectCPWithCohDir()
	b.connectCPWithCaches()
	b.connectCPWithROBs()
}

func (b *Builder) connectL1ToCohDir() {
	l1ToCohDir := directconnection.MakeBuilder().
		WithEngine(b.simulation.GetEngine()).
		WithFreq(b.freq).
		Build(b.name + ".L1ToCohDir")

	RDMAToCohDir := directconnection.MakeBuilder().
		WithEngine(b.simulation.GetEngine()).
		WithFreq(b.freq).
		Build(b.name + ".RDMAToCohDir")

	RDMAToCohDirForInv := directconnection.MakeBuilder().
		WithEngine(b.simulation.GetEngine()).
		WithFreq(b.freq).
		Build(b.name + ".RDMAToCohDirForInv")

	RDMAToCohDir.PlugIn(b.rdmaEngine.RDMADataInside)
	RDMAToCohDirForInv.PlugIn(b.rdmaEngine.RDMAInvInside)

	if b.coherenceDirectory == 0 { // coherenceDirectory
		l1ToCohDir.PlugIn(b.cohDir.GetPortByName("Top"))
		RDMAToCohDir.PlugIn(b.cohDir.GetPortByName("RDMA"))
		RDMAToCohDirForInv.PlugIn(b.cohDir.GetPortByName("RDMAInv"))

	} else if b.coherenceDirectory == 1 { // large block cache
		l1ToCohDir.PlugIn(b.cohDir.GetPortByName("Top"))
		RDMAToCohDir.PlugIn(b.cohDir.GetPortByName("RDMA"))
		RDMAToCohDirForInv.PlugIn(b.cohDir.GetPortByName("RDMAInv"))

	} else if b.coherenceDirectory == 2 { // superDirectory
		l1ToCohDir.PlugIn(b.superDir.GetPortByName("Top"))
		RDMAToCohDir.PlugIn(b.superDir.GetPortByName("RDMA"))
		RDMAToCohDirForInv.PlugIn(b.superDir.GetPortByName("RDMAInv"))

	} else if b.coherenceDirectory == 3 { // REC
		l1ToCohDir.PlugIn(b.recDir.GetPortByName("Top"))
		RDMAToCohDir.PlugIn(b.recDir.GetPortByName("RDMA"))
		RDMAToCohDirForInv.PlugIn(b.recDir.GetPortByName("RDMAInv"))

	} else if b.coherenceDirectory == 4 { // HMG
		l1ToCohDir.PlugIn(b.cohDir.GetPortByName("Top"))
		RDMAToCohDir.PlugIn(b.cohDir.GetPortByName("RDMA"))
		RDMAToCohDirForInv.PlugIn(b.cohDir.GetPortByName("RDMAInv"))

	} else if b.coherenceDirectory == 5 { // MGD
		l1ToCohDir.PlugIn(b.mgdDir.GetPortByName("Top"))
		RDMAToCohDir.PlugIn(b.mgdDir.GetPortByName("RDMA"))
		RDMAToCohDirForInv.PlugIn(b.mgdDir.GetPortByName("RDMAInv"))

	}
	// b.rdmaEngine.SetLocalModuleFinder(b.l1AddressMapper)
	b.rdmaEngine.SetLocalModuleFinder(b.rdmaLowModuleFinder)
	b.rdmaEngine.SetLocalInvModuleFinder(b.rdmaInvLowModuleFinder)
	b.rdmaEngine.SetLocalModuleBottomFinder(b.rdmaBottomAddressMapper)

	for _, sa := range b.sas {
		for i := range b.numCUPerShaderArray {
			l1ToCohDir.PlugIn(
				sa.GetPortByName(fmt.Sprintf("L1VCacheBottom[%d]", i)))
		}

		l1ToCohDir.PlugIn(sa.GetPortByName("L1SCacheBottom"))
		l1ToCohDir.PlugIn(sa.GetPortByName("L1ICacheBottom"))
	}

	if b.coherenceDirectory == 0 { // coherenceDirectory
		b.cohDir.ToRDMA = b.rdmaEngine.RDMADataInside.AsRemote()
		b.cohDir.ToRDMAInv = b.rdmaEngine.RDMAInvInside.AsRemote()
	} else if b.coherenceDirectory == 1 { // large block cache
		b.cohDir.ToRDMA = b.rdmaEngine.RDMADataInside.AsRemote()
		b.cohDir.ToRDMAInv = b.rdmaEngine.RDMAInvInside.AsRemote()
	} else if b.coherenceDirectory == 2 { // superDirectory
		b.superDir.ToRDMA = b.rdmaEngine.RDMADataInside.AsRemote()
		b.superDir.ToRDMAInv = b.rdmaEngine.RDMAInvInside.AsRemote()
	} else if b.coherenceDirectory == 3 { // REC
		b.recDir.ToRDMA = b.rdmaEngine.RDMADataInside.AsRemote()
		b.recDir.ToRDMAInv = b.rdmaEngine.RDMAInvInside.AsRemote()
	} else if b.coherenceDirectory == 4 { // HMG
		b.cohDir.ToRDMA = b.rdmaEngine.RDMADataInside.AsRemote()
		b.cohDir.ToRDMAInv = b.rdmaEngine.RDMAInvInside.AsRemote()
	} else if b.coherenceDirectory == 5 { // MGD
		b.mgdDir.ToRDMA = b.rdmaEngine.RDMADataInside.AsRemote()
		b.mgdDir.ToRDMAInv = b.rdmaEngine.RDMAInvInside.AsRemote()
	}
}

func (b *Builder) connectCohDirToL2() {
	CohDirToL2Conn := directconnection.MakeBuilder().
		WithEngine(b.simulation.GetEngine()).
		WithFreq(b.freq).
		Build(b.name + ".CohDirToL2")
	CohDirToL2ConnForRemote := directconnection.MakeBuilder().
		WithEngine(b.simulation.GetEngine()).
		WithFreq(b.freq).
		Build(b.name + ".CohDirToL2ForRemote")

	if b.coherenceDirectory == 0 { // coherenceDirectory
		CohDirToL2Conn.PlugIn(b.cohDir.GetPortByName("Bottom"))
		CohDirToL2ConnForRemote.PlugIn(b.cohDir.GetPortByName("RemoteBottom"))

		for _, l2 := range b.l2Caches {
			CohDirToL2Conn.PlugIn(l2.GetPortByName("Top"))
			CohDirToL2ConnForRemote.PlugIn(l2.GetPortByName("RemoteTop"))
		}
		b.cohDir.SetAddressToPortMapper(b.cohDirAddressMapper)
		b.cohDir.SetAddressToPortMapperForRemoteReq(b.cohDirAddressMapperForRemoteReq)

	} else if b.coherenceDirectory == 1 { // large block cache
		CohDirToL2Conn.PlugIn(b.cohDir.GetPortByName("Bottom"))
		CohDirToL2ConnForRemote.PlugIn(b.cohDir.GetPortByName("RemoteBottom"))

		for _, l2 := range b.largeBlkCaches {
			CohDirToL2Conn.PlugIn(l2.GetPortByName("Top"))
			CohDirToL2ConnForRemote.PlugIn(l2.GetPortByName("RemoteTop"))
		}
		b.cohDir.SetAddressToPortMapper(b.cohDirAddressMapper)
		b.cohDir.SetAddressToPortMapperForRemoteReq(b.cohDirAddressMapperForRemoteReq)

	} else if b.coherenceDirectory == 2 { // superDirectory
		CohDirToL2Conn.PlugIn(b.superDir.GetPortByName("Bottom"))
		CohDirToL2ConnForRemote.PlugIn(b.superDir.GetPortByName("RemoteBottom"))

		for _, l2 := range b.l2Caches {
			CohDirToL2Conn.PlugIn(l2.GetPortByName("Top"))
			CohDirToL2ConnForRemote.PlugIn(l2.GetPortByName("RemoteTop"))
		}
		b.superDir.SetAddressToPortMapper(b.cohDirAddressMapper)
		b.superDir.SetAddressToPortMapperForRemoteReq(b.cohDirAddressMapperForRemoteReq)

	} else if b.coherenceDirectory == 5 { // MGD
		CohDirToL2Conn.PlugIn(b.mgdDir.GetPortByName("Bottom"))
		CohDirToL2ConnForRemote.PlugIn(b.mgdDir.GetPortByName("RemoteBottom"))

		for _, l2 := range b.l2Caches {
			CohDirToL2Conn.PlugIn(l2.GetPortByName("Top"))
			CohDirToL2ConnForRemote.PlugIn(l2.GetPortByName("RemoteTop"))
		}
		b.mgdDir.SetAddressToPortMapper(b.cohDirAddressMapper)
		b.mgdDir.SetAddressToPortMapperForRemoteReq(b.cohDirAddressMapperForRemoteReq)

	} else if b.coherenceDirectory == 3 { // REC
		CohDirToL2Conn.PlugIn(b.recDir.GetPortByName("Bottom"))
		CohDirToL2ConnForRemote.PlugIn(b.recDir.GetPortByName("RemoteBottom"))

		for _, l2 := range b.l2Caches {
			CohDirToL2Conn.PlugIn(l2.GetPortByName("Top"))
			CohDirToL2ConnForRemote.PlugIn(l2.GetPortByName("RemoteTop"))
		}
		b.recDir.SetAddressToPortMapper(b.cohDirAddressMapper)
		b.recDir.SetAddressToPortMapperForRemoteReq(b.cohDirAddressMapperForRemoteReq)

	} else if b.coherenceDirectory == 4 { // HMG
		CohDirToL2Conn.PlugIn(b.cohDir.GetPortByName("Bottom"))
		CohDirToL2ConnForRemote.PlugIn(b.cohDir.GetPortByName("RemoteBottom"))

		for _, l2 := range b.l2Caches {
			CohDirToL2Conn.PlugIn(l2.GetPortByName("Top"))
			CohDirToL2ConnForRemote.PlugIn(l2.GetPortByName("RemoteTop"))
		}
		b.cohDir.SetAddressToPortMapper(b.cohDirAddressMapper)
		b.cohDir.SetAddressToPortMapperForRemoteReq(b.cohDirAddressMapperForRemoteReq)
	}
}

func (b *Builder) connectL2AndDRAM() {
	b.l2ToDramConnection = directconnection.MakeBuilder().
		WithEngine(b.simulation.GetEngine()).
		WithFreq(b.freq).
		Build(b.name + ".L2ToDRAM")
	b.simulation.RegisterComponent(b.l2ToDramConnection)

	lowModuleFinder := mem.NewInterleavedAddressPortMapper(
		1 << b.log2MemoryBankInterleavingSize)

	b.l2ToDramConnection.PlugIn(b.rdmaEngine.RDMARequestInside)

	var mapperForDir *mem.L2BottomMapper
	if b.coherenceDirectory == 1 {
		for i, l2 := range b.largeBlkCaches {
			b.l2ToDramConnection.PlugIn(l2.GetPortByName("Bottom"))

			mapper := &mem.L2BottomMapper{
				LocalBank: b.drams[i].GetPortByName("Top").AsRemote(),
				RDMAPort:  b.rdmaEngine.RDMARequestInside.AsRemote(),
				LocalLow:  b.memAddrOffset,
				LocalHigh: b.memAddrOffset + b.dramSize,
			}
			l2.SetAddressToPortMapper(mapper)

			if i == 0 { // request가 remote/local data에 대한 것인지 판단하기 위함
				mapperForDir = mapper
			}
		}
	} else {
		for i, l2 := range b.l2Caches {
			b.l2ToDramConnection.PlugIn(l2.GetPortByName("Bottom"))

			mapper := &mem.L2BottomMapper{
				LocalBank: b.drams[i].GetPortByName("Top").AsRemote(),
				RDMAPort:  b.rdmaEngine.RDMARequestInside.AsRemote(),
				LocalLow:  b.memAddrOffset,
				LocalHigh: b.memAddrOffset + b.dramSize,
			}
			l2.SetAddressToPortMapper(mapper)

			if i == 0 { // request가 remote/local data에 대한 것인지 판단하기 위함
				mapperForDir = mapper
			}
		}
	}

	if b.coherenceDirectory == 0 { // coherenceDirectory
		b.cohDir.SetL2AddressToPortMapper(mapperForDir)
	} else if b.coherenceDirectory == 1 { // large block cache
		b.cohDir.SetL2AddressToPortMapper(mapperForDir)
	} else if b.coherenceDirectory == 2 { // superDirectory
		b.superDir.SetL2AddressToPortMapper(mapperForDir)
	} else if b.coherenceDirectory == 3 { // REC
		b.recDir.SetL2AddressToPortMapper(mapperForDir)
	} else if b.coherenceDirectory == 4 { // HMG
		b.cohDir.SetL2AddressToPortMapper(mapperForDir)
	} else if b.coherenceDirectory == 5 { // MGD
		b.mgdDir.SetL2AddressToPortMapper(mapperForDir)
	}

	for _, dram := range b.drams {
		b.l2ToDramConnection.PlugIn(dram.GetPortByName("Top"))
		lowModuleFinder.LowModules = append(lowModuleFinder.LowModules,
			dram.GetPortByName("Top").AsRemote())
	}

	b.dmaEngine.SetLocalDataSource(lowModuleFinder)
	b.l2ToDramConnection.PlugIn(b.dmaEngine.ToMem)

	b.pmc.MemCtrlFinder = lowModuleFinder
	b.l2ToDramConnection.PlugIn(b.pmc.GetPortByName("LocalMem"))
}

func (b *Builder) connectL1TLBToL2TLB() {
	tlbConn := directconnection.MakeBuilder().
		WithEngine(b.simulation.GetEngine()).
		WithFreq(b.freq).
		Build(b.name + ".L1TLBToL2TLB")

	tlbConn.PlugIn(b.l2TLBs[0].GetPortByName("Top"))

	for _, sa := range b.sas {
		for i := range b.numCUPerShaderArray {
			tlbConn.PlugIn(
				sa.GetPortByName(fmt.Sprintf("L1VTLBBottom[%d]", i)))
		}

		tlbConn.PlugIn(sa.GetPortByName("L1STLBBottom"))
		tlbConn.PlugIn(sa.GetPortByName("L1ITLBBottom"))
	}
}

func (b *Builder) connectL2TLBToGMMU() {

	gmmuConn := directconnection.MakeBuilder().
		WithEngine(b.simulation.GetEngine()).
		WithFreq(b.freq).
		Build(b.name + ".L2TLBToGMMU")

	gmmuConn.PlugIn(b.gmmu.GetPortByName("Top"))

	for _, l2 := range b.l2TLBs {
		gmmuConn.PlugIn(l2.GetPortByName("Bottom"))
	}
}

type cuInterfaceForCP struct {
	ctrlPort        sim.RemotePort
	dispatchingPort sim.RemotePort
	wfPoolSizes     []int
	vRegCounts      []int
	sRegCount       int
	ldsBytes        int
}

func (cu cuInterfaceForCP) ControlPort() sim.RemotePort {
	return cu.ctrlPort
}

func (cu cuInterfaceForCP) DispatchingPort() sim.RemotePort {
	return cu.dispatchingPort
}

func (cu cuInterfaceForCP) WfPoolSizes() []int {
	return cu.wfPoolSizes
}

func (cu cuInterfaceForCP) VRegCounts() []int {
	return cu.vRegCounts
}

func (cu cuInterfaceForCP) SRegCount() int {
	return cu.sRegCount
}

func (cu cuInterfaceForCP) LDSBytes() int {
	return cu.ldsBytes
}

func (b *Builder) connectCPWithCUs() {
	for _, sa := range b.sas {
		for i := range b.numCUPerShaderArray {
			cuDispatchingPort := sa.GetPortByName(
				fmt.Sprintf("CU[%d]", i))
			cuCtrlPort := sa.GetPortByName(
				fmt.Sprintf("CUCtrl[%d]", i))
			cu := cuInterfaceForCP{
				ctrlPort:        cuCtrlPort.AsRemote(),
				dispatchingPort: cuDispatchingPort.AsRemote(),
				wfPoolSizes:     []int{10, 10, 10, 10},
				vRegCounts:      []int{16384, 16384, 16384, 16384},
				sRegCount:       3200,
				ldsBytes:        64 * 1024,
			}

			b.cp.RegisterCU(cu)

			b.internalConn.PlugIn(cuDispatchingPort)
			b.internalConn.PlugIn(cuCtrlPort)
		}
	}
}

func (b *Builder) connectCPWithAddressTranslators() {
	for _, sa := range b.sas {
		for i := range b.numCUPerShaderArray {
			at := sa.GetPortByName(fmt.Sprintf("L1VAddrTransCtrl[%d]", i))
			b.cp.AddressTranslators = append(b.cp.AddressTranslators, at)
			b.internalConn.PlugIn(at)
		}

		l1sAT := sa.GetPortByName("L1SAddrTransCtrl")
		b.cp.AddressTranslators = append(b.cp.AddressTranslators, l1sAT)
		b.internalConn.PlugIn(l1sAT)

		l1iAT := sa.GetPortByName("L1IAddrTransCtrl")
		b.cp.AddressTranslators = append(b.cp.AddressTranslators, l1iAT)
		b.internalConn.PlugIn(l1iAT)
	}
}

func (b *Builder) connectCPWithTLBs() {
	for _, sa := range b.sas {
		for i := range b.numCUPerShaderArray {
			tlb := sa.GetPortByName(fmt.Sprintf("L1VTLBCtrl[%d]", i))
			b.cp.TLBs = append(b.cp.TLBs, tlb)
			b.internalConn.PlugIn(tlb)
		}

		l1sTLB := sa.GetPortByName("L1STLBCtrl")
		b.cp.TLBs = append(b.cp.TLBs, l1sTLB)
		b.internalConn.PlugIn(l1sTLB)

		l1iTLB := sa.GetPortByName("L1ITLBCtrl")
		b.cp.TLBs = append(b.cp.TLBs, l1iTLB)
		b.internalConn.PlugIn(l1iTLB)
	}

	for _, tlb := range b.l2TLBs {
		ctrlPort := tlb.GetPortByName("Control")
		b.cp.TLBs = append(b.cp.TLBs, ctrlPort)
		b.internalConn.PlugIn(ctrlPort)
	}
}

func (b *Builder) connectCPWithCohDir() {
	var cohDirPort sim.Port

	if b.coherenceDirectory == 0 { // coherenceDirectory
		cohDirPort = b.cohDir.GetPortByName("Control")
	} else if b.coherenceDirectory == 1 { // large block cache
		cohDirPort = b.cohDir.GetPortByName("Control")
	} else if b.coherenceDirectory == 2 { // superDirectory
		cohDirPort = b.superDir.GetPortByName("Control")
	} else if b.coherenceDirectory == 3 { // REC
		cohDirPort = b.recDir.GetPortByName("Control")
	} else if b.coherenceDirectory == 4 { // HMG
		cohDirPort = b.cohDir.GetPortByName("Control")
	} else if b.coherenceDirectory == 5 { // MGD
		cohDirPort = b.mgdDir.GetPortByName("Control")
	}

	b.cp.CohDirectory = cohDirPort
	b.internalConn.PlugIn(cohDirPort)
}

func (b *Builder) connectCPWithCaches() {
	for _, sa := range b.sas {
		for i := range b.numCUPerShaderArray {
			cache := sa.GetPortByName(fmt.Sprintf("L1VCacheCtrl[%d]", i))
			b.cp.L1VCaches = append(b.cp.L1VCaches, cache)
			b.internalConn.PlugIn(cache)
		}

		l1sCache := sa.GetPortByName("L1SCacheCtrl")
		b.cp.L1SCaches = append(b.cp.L1SCaches, l1sCache)
		b.internalConn.PlugIn(l1sCache)

		l1iCache := sa.GetPortByName("L1ICacheCtrl")
		b.cp.L1ICaches = append(b.cp.L1ICaches, l1iCache)
		b.internalConn.PlugIn(l1iCache)
	}

	if b.coherenceDirectory == 1 {
		for _, c := range b.largeBlkCaches {
			ctrlPort := c.GetPortByName("Control")
			b.cp.L2Caches = append(b.cp.L2Caches, ctrlPort)
			b.internalConn.PlugIn(ctrlPort)
		}
	} else {
		for _, c := range b.l2Caches {
			ctrlPort := c.GetPortByName("Control")
			b.cp.L2Caches = append(b.cp.L2Caches, ctrlPort)
			b.internalConn.PlugIn(ctrlPort)
		}

	}
}

func (b *Builder) connectCPWithROBs() {
	for _, sa := range b.sas {
		for i := range b.numCUPerShaderArray {
			l1vrob := sa.GetPortByName(fmt.Sprintf("L1VROBCtrl[%d]", i))
			b.cp.L1VROBs = append(b.cp.L1VROBs, l1vrob)
			b.internalConn.PlugIn(l1vrob)
		}

		l1srob := sa.GetPortByName("L1SROBCtrl")
		b.cp.L1SROBs = append(b.cp.L1SROBs, l1srob)
		b.internalConn.PlugIn(l1srob)

		l1irob := sa.GetPortByName("L1IROBCtrl")
		b.cp.L1IROBs = append(b.cp.L1IROBs, l1irob)
		b.internalConn.PlugIn(l1irob)
	}
}

func (b *Builder) buildSAs() {
	saBuilder := shaderarray.MakeBuilder().
		WithSimulation(b.simulation).
		WithFreq(b.freq).
		WithGPUID(b.gpuID).
		WithNumCUs(b.numCUPerShaderArray).
		WithLog2CacheLineSize(b.log2CacheLineSize).
		WithLog2PageSize(b.log2PageSize).
		WithL1AddressMapper(b.l1AddressMapper).
		WithL1TLBAddressMapper(b.l1TLBAddressMapper).
		WithVisTracer(b.simulation.GetVisTracer()).
		WithAccessCounter(b.accessCounter).
		WithDirtyMask(b.dirtyMask).
		WithReadMask(b.readMask).
		WithPageMigrationPolicy(b.pageMigrationPolicy)

	// if b.enableISADebugging {
	// 	saBuilder = saBuilder.withIsaDebugging()
	// }

	// if b.enableMemTracing {
	// 	saBuilder = saBuilder.withMemTracer(b.memTracer)
	// }

	for i := 0; i < b.numShaderArray; i++ {
		saName := fmt.Sprintf("%s.SA[%d]", b.name, i)
		sa := saBuilder.Build(saName)

		b.sas = append(b.sas, sa)
	}
}

func (b *Builder) buildCoherenceDirectory() {
	if b.coherenceDirectory == 0 { // coherenceDirectory
		byteSize := b.cohDirSize
		// dir := coherence.MakeBuilder().
		dir := optdirectory.MakeBuilder().
			WithEngine(b.simulation.GetEngine()).
			WithFreq(b.freq).
			WithDeviceID(int(b.gpuID)).
			WithLog2BlockSize(b.log2CacheLineSize).
			WithLog2PageSize(b.log2PageSize).
			WithLog2UnitSize(b.log2CoherenceUnitSize).
			WithWayAssociativity(8).
			WithByteSize(byteSize).
			WithNumMSHREntry(64).
			WithNumReqPerCycle(16).
			WithDirectoryLatency(1).
			WithAddressMapperType("interleaved").
			// WithToRDMA(b.rdmaEngine.RDMADataInside.AsRemote()).
			WithIdealDirectory(b.idealDirectory).
			WithFetchSingleCacheLine(true).
			WithReadMask(b.readMask).
			WithDirtyMask(b.dirtyMask).
			Build(fmt.Sprintf("%s.CohDir", b.name))

		b.simulation.RegisterComponent(dir)
		b.cohDir = dir
		b.l1AddressMapper.LowModules = append(
			b.l1AddressMapper.LowModules,
			dir.GetPortByName("Top").AsRemote(),
		)
		b.rdmaLowModuleFinder.LowModules = append(
			b.rdmaLowModuleFinder.LowModules,
			dir.GetPortByName("RDMA").AsRemote(),
		)
		b.rdmaInvLowModuleFinder.LowModules = append(
			b.rdmaInvLowModuleFinder.LowModules,
			dir.GetPortByName("RDMAInv").AsRemote(),
		)

	} else if b.coherenceDirectory == 1 { // largeBlkCache
		byteSize := b.cohDirSize * 1 << b.log2CoherenceUnitSize
		// dir := coherence.MakeBuilder().
		dir := optdirectory.MakeBuilder().
			WithEngine(b.simulation.GetEngine()).
			WithFreq(b.freq).
			WithDeviceID(int(b.gpuID)).
			WithLog2BlockSize(b.log2CacheLineSize + b.log2CoherenceUnitSize).
			WithLog2PageSize(b.log2PageSize).
			WithLog2UnitSize(0).
			WithWayAssociativity(8).
			WithByteSize(byteSize).
			WithNumMSHREntry(64).
			WithNumReqPerCycle(16).
			WithDirectoryLatency(1).
			WithAddressMapperType("interleaved").
			// WithToRDMA(b.rdmaEngine.RDMADataInside.AsRemote()).
			WithIdealDirectory(b.idealDirectory).
			WithReadMask(b.readMask).
			WithDirtyMask(b.dirtyMask).
			Build(fmt.Sprintf("%s.CohDir", b.name))

		b.simulation.RegisterComponent(dir)
		b.cohDir = dir
		b.l1AddressMapper.LowModules = append(
			b.l1AddressMapper.LowModules,
			dir.GetPortByName("Top").AsRemote(),
		)
		b.rdmaLowModuleFinder.LowModules = append(
			b.rdmaLowModuleFinder.LowModules,
			dir.GetPortByName("RDMA").AsRemote(),
		)
		b.rdmaInvLowModuleFinder.LowModules = append(
			b.rdmaInvLowModuleFinder.LowModules,
			dir.GetPortByName("RDMAInv").AsRemote(),
		)

	} else if b.coherenceDirectory == 2 { // superDirectory
		byteSize := b.cohDirSize
		dir := superdirectory.MakeBuilder().
			WithEngine(b.simulation.GetEngine()).
			WithFreq(b.freq).
			WithDeviceID(int(b.gpuID)).
			WithLog2BlockSize(b.log2CacheLineSize).
			WithLog2PageSize(b.log2PageSize).
			WithLog2NumSubEntry(b.sdLog2NumSubEntry).
			WithNumBanks(b.sdNumBanks).
			WithWayAssociativity(8).
			WithByteSize(byteSize).
			WithNumMSHREntry(64).
			WithNumReqPerCycle(16).
			WithBankLatency(1).
			WithDirectoryLatency(1).
			WithAddressMapperType("interleaved").
			WithFetchSingleCacheLine(true).
			WithDisableRSB(b.sdDisableRSB).
			WithDisableCBF(b.sdDisableCBF).
			WithParallelBankSearch(b.sdParallelBankSearch).
			WithReadMask(b.readMask).
			WithDirtyMask(b.dirtyMask).
			Build(fmt.Sprintf("%s.SuperDir", b.name))

		b.simulation.RegisterComponent(dir)
		b.superDir = dir
		b.l1AddressMapper.LowModules = append(
			b.l1AddressMapper.LowModules,
			dir.GetPortByName("Top").AsRemote(),
		)
		b.rdmaLowModuleFinder.LowModules = append(
			b.rdmaLowModuleFinder.LowModules,
			dir.GetPortByName("RDMA").AsRemote(),
		)
		b.rdmaInvLowModuleFinder.LowModules = append(
			b.rdmaInvLowModuleFinder.LowModules,
			dir.GetPortByName("RDMAInv").AsRemote(),
		)

	} else if b.coherenceDirectory == 3 { // REC
		byteSize := b.cohDirSize
		dir := REC.MakeBuilder().
			WithEngine(b.simulation.GetEngine()).
			WithFreq(b.freq).
			WithDeviceID(int(b.gpuID)).
			WithLog2BlockSize(b.log2CacheLineSize).
			WithLog2PageSize(b.log2PageSize).
			WithLog2NumSubEntry(4).
			// WithLog2UnitSize(0).
			WithWayAssociativity(8).
			WithByteSize(byteSize).
			WithNumMSHREntry(64).
			WithNumReqPerCycle(16).
			WithBankLatency(1).
			WithDirectoryLatency(1).
			WithAddressMapperType("interleaved").
			// WithToRDMA(b.rdmaEngine.RDMADataInside.AsRemote()).
			// WithIdealDirectory(b.idealDirectory).
			WithHalfSet(b.recHalfSet).
			WithReadMask(b.readMask).
			WithDirtyMask(b.dirtyMask).
			Build(fmt.Sprintf("%s.RECDir", b.name))

		b.simulation.RegisterComponent(dir)
		b.recDir = dir
		b.l1AddressMapper.LowModules = append(
			b.l1AddressMapper.LowModules,
			dir.GetPortByName("Top").AsRemote(),
		)
		b.rdmaLowModuleFinder.LowModules = append(
			b.rdmaLowModuleFinder.LowModules,
			dir.GetPortByName("RDMA").AsRemote(),
		)
		b.rdmaInvLowModuleFinder.LowModules = append(
			b.rdmaInvLowModuleFinder.LowModules,
			dir.GetPortByName("RDMAInv").AsRemote(),
		)

	} else if b.coherenceDirectory == 5 { // MGD
		byteSize := b.cohDirSize
		dir := MGD.MakeBuilder().
			WithEngine(b.simulation.GetEngine()).
			WithFreq(b.freq).
			WithDeviceID(int(b.gpuID)).
			WithLog2BlockSize(b.log2CacheLineSize).
			WithLog2PageSize(b.log2PageSize).
			WithRegionSize(b.mgdRegionSize).
			WithWayAssociativity(8).
			WithByteSize(byteSize).
			WithNumMSHREntry(64).
			WithNumReqPerCycle(16).
			WithBankLatency(1).
			WithDirectoryLatency(1).
			WithAddressMapperType("interleaved").
			WithFetchSingleCacheLine(true).
			WithDisableRSB(b.sdDisableRSB).
			WithDisableCBF(b.sdDisableCBF).
			WithReadMask(b.readMask).
			WithDirtyMask(b.dirtyMask).
			Build(fmt.Sprintf("%s.MGDDir", b.name))

		b.simulation.RegisterComponent(dir)
		b.mgdDir = dir
		b.l1AddressMapper.LowModules = append(
			b.l1AddressMapper.LowModules,
			dir.GetPortByName("Top").AsRemote(),
		)
		b.rdmaLowModuleFinder.LowModules = append(
			b.rdmaLowModuleFinder.LowModules,
			dir.GetPortByName("RDMA").AsRemote(),
		)
		b.rdmaInvLowModuleFinder.LowModules = append(
			b.rdmaInvLowModuleFinder.LowModules,
			dir.GetPortByName("RDMAInv").AsRemote(),
		)

	} else if b.coherenceDirectory == 4 { // HMG
		byteSize := b.cohDirSize
		// dir := coherence.MakeBuilder().
		dir := optdirectory.MakeBuilder().
			WithEngine(b.simulation.GetEngine()).
			WithFreq(b.freq).
			WithDeviceID(int(b.gpuID)).
			WithLog2BlockSize(b.log2CacheLineSize).
			WithLog2PageSize(b.log2PageSize).
			WithLog2UnitSize(2).
			WithFetchSingleCacheLine(true).
			WithWayAssociativity(8).
			WithByteSize(byteSize).
			WithNumMSHREntry(64).
			WithNumReqPerCycle(16).
			WithDirectoryLatency(1).
			WithAddressMapperType("interleaved").
			// WithToRDMA(b.rdmaEngine.RDMADataInside.AsRemote()).
			WithIdealDirectory(b.idealDirectory).
			WithReadMask(b.readMask).
			WithDirtyMask(b.dirtyMask).
			Build(fmt.Sprintf("%s.HMGDir", b.name))

		b.simulation.RegisterComponent(dir)
		b.cohDir = dir
		b.l1AddressMapper.LowModules = append(
			b.l1AddressMapper.LowModules,
			dir.GetPortByName("Top").AsRemote(),
		)
		b.rdmaLowModuleFinder.LowModules = append(
			b.rdmaLowModuleFinder.LowModules,
			dir.GetPortByName("RDMA").AsRemote(),
		)
		b.rdmaInvLowModuleFinder.LowModules = append(
			b.rdmaInvLowModuleFinder.LowModules,
			dir.GetPortByName("RDMAInv").AsRemote(),
		)
	}
}

func (b *Builder) buildL2Caches() {
	if b.coherenceDirectory == 1 {
		byteSize := b.l2CacheSize / uint64(b.numMemoryBank)
		l2Builder := largeblkcache.MakeBuilder().
			WithEngine(b.simulation.GetEngine()).
			WithFreq(b.freq).
			WithDeviceID(int(b.gpuID)).
			WithLog2BlockSize(b.log2CacheLineSize).
			WithLog2PageSize(b.log2PageSize).
			WithLog2UnitSize(b.log2CoherenceUnitSize).
			WithWayAssociativity(16).
			WithByteSize(byteSize).
			WithNumMSHREntry(64).
			WithNumReqPerCycle(16).
			WithReadMask(b.readMask).
			WithDirtyMask(b.dirtyMask)

		for i := 0; i < b.numMemoryBank; i++ {
			cacheName := fmt.Sprintf("%s.L2Cache[%d]", b.name, i)
			l2 := l2Builder.WithInterleaving(
				1<<(b.log2MemoryBankInterleavingSize-b.log2CacheLineSize),
				b.numMemoryBank,
				i).
				WithAddressMapperType("single").
				WithRemotePorts(b.drams[i].GetPortByName("Top").AsRemote()).
				Build(cacheName)

			b.simulation.RegisterComponent(l2)
			b.largeBlkCaches = append(b.largeBlkCaches, l2)

			// b.l1AddressMapper.LowModules = append(
			b.cohDirAddressMapper.LowModules = append(
				b.cohDirAddressMapper.LowModules,
				l2.GetPortByName("Top").AsRemote(),
			)

			// b.l1AddressMapper.LowModules = append(
			b.cohDirAddressMapperForRemoteReq.LowModules = append(
				b.cohDirAddressMapperForRemoteReq.LowModules,
				l2.GetPortByName("RemoteTop").AsRemote(),
			)

			b.rdmaBottomAddressMapper.LowModules = append(
				b.rdmaBottomAddressMapper.LowModules,
				l2.GetPortByName("Bottom").AsRemote(),
			)

			// if b.enableMemTracing {
			// 	tracing.CollectTrace(l2, b.memTracer)
			// }
		}
	} else {
		byteSize := b.l2CacheSize / uint64(b.numMemoryBank)
		l2Builder := writebackcoh.MakeBuilder().
			WithEngine(b.simulation.GetEngine()).
			WithFreq(b.freq).
			WithDeviceID(int(b.gpuID)).
			WithLog2BlockSize(b.log2CacheLineSize).
			WithLog2PageSize(b.log2PageSize).
			WithLog2UnitSize(b.log2CoherenceUnitSize).
			WithWayAssociativity(16).
			WithByteSize(byteSize).
			WithNumMSHREntry(64).
			WithNumReqPerCycle(16).
			WithReadMask(b.readMask).
			WithDirtyMask(b.dirtyMask)

		for i := 0; i < b.numMemoryBank; i++ {
			cacheName := fmt.Sprintf("%s.L2Cache[%d]", b.name, i)
			l2 := l2Builder.WithInterleaving(
				1<<(b.log2MemoryBankInterleavingSize-b.log2CacheLineSize),
				b.numMemoryBank,
				i).
				WithAddressMapperType("single").
				WithRemotePorts(b.drams[i].GetPortByName("Top").AsRemote()).
				Build(cacheName)

			b.simulation.RegisterComponent(l2)
			b.l2Caches = append(b.l2Caches, l2)

			// b.l1AddressMapper.LowModules = append(
			b.cohDirAddressMapper.LowModules = append(
				b.cohDirAddressMapper.LowModules,
				l2.GetPortByName("Top").AsRemote(),
			)

			// b.l1AddressMapper.LowModules = append(
			b.cohDirAddressMapperForRemoteReq.LowModules = append(
				b.cohDirAddressMapperForRemoteReq.LowModules,
				l2.GetPortByName("RemoteTop").AsRemote(),
			)

			b.rdmaBottomAddressMapper.LowModules = append(
				b.rdmaBottomAddressMapper.LowModules,
				l2.GetPortByName("Bottom").AsRemote(),
			)

			// if b.enableMemTracing {
			// 	tracing.CollectTrace(l2, b.memTracer)
			// }
		}
	}
}

func (b *Builder) buildDRAMControllers() {
	// memCtrlBuilder := b.createDramControllerBuilder()

	for i := 0; i < b.numMemoryBank; i++ {
		dramName := fmt.Sprintf("%s.DRAM[%d]", b.name, i)
		dram := idealmemcontroller.MakeBuilder().
			WithEngine(b.simulation.GetEngine()).
			WithFreq(b.freq).
			WithLatency(100).
			WithStorage(b.globalStorage).
			Build(dramName)
		b.simulation.RegisterComponent(dram)
		b.drams = append(b.drams, dram)

		// if b.enableMemTracing {
		// 	tracing.CollectTrace(dram, b.memTracer)
		// }
	}
}

func (b *Builder) createDramControllerBuilder() dram.Builder {
	memBankSize := 4 * mem.GB / uint64(b.numMemoryBank)
	if 4*mem.GB%uint64(b.numMemoryBank) != 0 {
		panic("GPU memory size is not a multiple of the number of memory banks")
	}

	dramCol := 64
	dramRow := 16384
	dramDeviceWidth := 128
	dramBankSize := dramCol * dramRow * dramDeviceWidth
	dramBank := 4
	dramBankGroup := 4
	dramBusWidth := 256
	dramDevicePerRank := dramBusWidth / dramDeviceWidth
	dramRankSize := dramBankSize * dramDevicePerRank * dramBank
	dramRank := int(memBankSize * 8 / uint64(dramRankSize))

	memCtrlBuilder := dram.MakeBuilder().
		WithEngine(b.simulation.GetEngine()).
		WithFreq(500 * sim.MHz).
		WithProtocol(dram.HBM).
		WithBurstLength(4).
		WithDeviceWidth(dramDeviceWidth).
		WithBusWidth(dramBusWidth).
		WithNumChannel(1).
		WithNumRank(dramRank).
		WithNumBankGroup(dramBankGroup).
		WithNumBank(dramBank).
		WithNumCol(dramCol).
		WithNumRow(dramRow).
		WithCommandQueueSize(8).
		WithTransactionQueueSize(32).
		WithTCL(7).
		WithTCWL(2).
		WithTRCDRD(7).
		WithTRCDWR(7).
		WithTRP(7).
		WithTRAS(17).
		WithTREFI(1950).
		WithTRRDS(2).
		WithTRRDL(3).
		WithTWTRS(3).
		WithTWTRL(4).
		WithTWR(8).
		WithTCCDS(1).
		WithTCCDL(1).
		WithTRTRS(0).
		WithTRTP(3).
		WithTPPD(2)

	if b.globalStorage != nil {
		memCtrlBuilder = memCtrlBuilder.WithGlobalStorage(b.globalStorage)
	}

	return memCtrlBuilder
}

func (b *Builder) buildRDMAEngine() {
	name := fmt.Sprintf("%s.RDMA", b.name)
	b.rdmaEngine = rdma.MakeBuilder().
		WithDeviceID(b.gpuID).
		WithEngine(b.simulation.GetEngine()).
		WithVisTracer(b.simulation.GetVisTracer()).
		WithFreq(1 * sim.GHz).
		WithBufferSize(4096).
		// WithLocalModules(b.l1AddressMapper).
		WithLocalModules(b.rdmaLowModuleFinder).
		WithAccessCounter(b.accessCounter).
		WithDirtyMask(b.dirtyMask).
		WithReadMask(b.readMask).
		WithLog2CacheLineSize(b.log2CacheLineSize).
		WithLog2PageSize(b.log2PageSize).
		Build(name)

	b.rdmaEngine.RemoteRDMAAddressTable = b.rdmaAddressMapper

	b.simulation.RegisterComponent(b.rdmaEngine)
}

func (b *Builder) buildPageMigrationController() {
	b.pmc = pagemigrationcontroller.NewPageMigrationController(
		fmt.Sprintf("%s.PMC", b.name),
		b.gpuID,
		b.simulation.GetEngine(),
		b.pmcAddressMapper,
		nil)

	b.simulation.RegisterComponent(b.pmc)
}

func (b *Builder) buildDMAEngine() {
	b.dmaEngine = cp.NewDMAEngine(
		fmt.Sprintf("%s.DMA", b.name),
		b.simulation.GetEngine(),
		nil)

	b.simulation.RegisterComponent(b.dmaEngine)
}

func (b *Builder) buildCP() {
	b.cp = cp.MakeBuilder().
		WithDeviceID(uint32(b.gpuID)).
		WithEngine(b.simulation.GetEngine()).
		WithVisTracer(b.simulation.GetVisTracer()).
		WithFreq(b.freq).
		WithMonitor(b.simulation.GetMonitor()).
		WithDriver(b.driver).
		WithPageMigrationPolicy(b.pageMigrationPolicy).
		Build(b.name + ".CommandProcessor")

	b.simulation.RegisterComponent(b.cp)

	b.buildDMAEngine()
	b.buildRDMAEngine()
	b.buildPageMigrationController()
}

func (b *Builder) buildL2TLB() {
	numWays := 64
	builder := tlb.MakeBuilder().
		WithEngine(b.simulation.GetEngine()).
		WithFreq(b.freq).
		WithNumWays(numWays).
		WithNumSets(int(b.dramSize / (1 << b.log2PageSize) / uint64(numWays))).
		WithNumMSHREntry(64).
		WithNumReqPerCycle(1024).
		// WithPageSize(1 << b.log2PageSize).
		WithLog2PageSize(b.log2PageSize).
		WithLowModule(b.gmmu.GetPortByName("Top").AsRemote()).
		WithPageMigrationPolicy(b.pageMigrationPolicy).
		WithAccessCounter(b.accessCounter)
		// WithAddressMapper(&mem.SinglePortMapper{
		// 	Port: b.gmmu.GetPortByName("Top").AsRemote(),
		// })

	l2TLB := builder.Build(fmt.Sprintf("%s.L2TLB", b.name))

	b.simulation.RegisterComponent(l2TLB)
	b.l2TLBs = append(b.l2TLBs, l2TLB)

	b.l1TLBAddressMapper.Port = l2TLB.GetPortByName("Top").AsRemote()
}

func (b *Builder) buildGMMU() {
	builder := gmmu.MakeBuilder().
		WithEngine(b.simulation.GetEngine()).
		WithFreq(b.freq).
		WithLog2PageSize(b.log2PageSize).
		WithPageTable(vm.NewLevelPageTable(b.log2PageSize, 6, fmt.Sprintf("GMMU[%d].PT", b.gpuID))).
		// WithMaxNumReqInFlight(16).
		WithMaxNumReqInFlight(8).
		WithPageWalkingLatency(100).
		WithDeviceID(b.gpuID).
		WithAccessCounter(b.accessCounter).
		WithLowModule(b.mmu.GetPortByName("Top").AsRemote()).
		WithPageTableLogSize(20).
		WithDirtyMask(b.dirtyMask).
		WithReadMask(b.readMask).
		WithPageMigrationPolicy(b.pageMigrationPolicy)

	b.gmmu = builder.Build(fmt.Sprintf("%s.GMMU", b.name))

	b.simulation.RegisterComponent(b.gmmu)
}

func (b *Builder) numCU() int {
	return b.numCUPerShaderArray * b.numShaderArray
}
