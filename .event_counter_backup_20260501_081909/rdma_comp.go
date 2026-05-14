// Package rdma provides the implementation of an RDMA engine.
package rdma

import (
	"fmt"
	"log"
	"reflect"

	"github.com/sarchlab/akita/v4/mem/mem"
	"github.com/sarchlab/akita/v4/mem/vm"
	"github.com/sarchlab/akita/v4/sim"
	"github.com/sarchlab/akita/v4/tracing"
)

type transaction struct {
	fromInside  sim.Msg
	fromOutside sim.Msg
	toInside    sim.Msg
	toOutside   sim.Msg
	ack         uint64
}

// An Comp is a component that helps one GPU to access the memory on
// another GPU
type Comp struct {
	*sim.TickingComponent

	deviceID           uint64
	RDMARequestInside  sim.Port
	RDMARequestOutside sim.Port
	RDMADataInside     sim.Port
	RDMADataOutside    sim.Port
	RDMAInvInside      sim.Port

	reqFromL1Buf   []sim.Msg
	procInvReqBuf  []sim.Msg
	incomingReqBuf []sim.Msg
	procInvRspBuf  []sim.Msg

	CtrlPort sim.Port

	isDraining              bool
	pauseIncomingReqsFromL1 bool
	currentDrainReq         *DrainReq

	localModules           mem.AddressToPortMapper
	localInvModules        mem.AddressToPortMapper
	RemoteRDMAAddressTable mem.AddressToPortMapper
	localModuleBottoms     mem.AddressToPortMapper

	transactionsFromOutside []transaction
	transactionsFromInside  []transaction
	invalidationFromInside  []*mem.InvReq
	invalidationFromOutside []*mem.InvReq

	incomingReqPerCycle int
	incomingRspPerCycle int
	outgoingReqPerCycle int
	outgoingRspPerCycle int

	AccessCounter *map[vm.PID]map[uint64]uint8
	dirtyMask     *[]map[vm.PID]map[uint64][]uint8
	readMask      *[]map[vm.PID]map[uint64][]uint8

	log2PageSize      uint64
	log2CacheLineSize uint64

	tickReturn   bool
	printReturn  bool
	recordTime   sim.VTimeInSec
	returnFalse0 string
	returnFalse1 string
	returnFalse2 string
	returnFalse3 string

	traceProcess bool
	debugProcess bool
	debugAddress uint64
}

// SetLocalModuleFinder sets the table to lookup for local data.
func (c *Comp) SetLocalModuleFinder(lmf mem.AddressToPortMapper) {
	c.localModules = lmf
}

func (c *Comp) SetLocalInvModuleFinder(lmf mem.AddressToPortMapper) {
	c.localInvModules = lmf
}

// SetLocalModuleFinder sets the table to lookup for local data.
func (c *Comp) SetLocalModuleBottomFinder(lmf mem.AddressToPortMapper) {
	c.localModuleBottoms = lmf
}

// Tick checks if make progress
// func (c *Comp) Tick() bool {
// 	madeProgress := false

// 	madeProgress = c.processFromCtrlPort() || madeProgress
// 	if c.isDraining {
// 		madeProgress = c.drainRDMA() || madeProgress
// 	}

// 	for i := 0; i < c.outgoingReqPerCycle; i++ {
// 		madeProgress = c.processFromL1() || madeProgress // 1. Req. from RDMARequestInside -> RDMARequestOutside
// 	}

// 	for i := 0; i < c.outgoingRspPerCycle; i++ {
// 		madeProgress = c.processFromL2() || madeProgress // 3. Rsp. from RDMADataInside -> Rsp. to corresponding req.Src
// 	}

// 	for i := 0; i < c.incomingReqPerCycle; i++ {
// 		madeProgress = c.processIncomingReq() || madeProgress // 2. Req. from RDMADataOutside -> Req. to RDMADataInside
// 	}

// 	for i := 0; i < c.incomingRspPerCycle; i++ {
// 		madeProgress = c.processIncomingRsp() || madeProgress // 4. Rsp. from RDMARequestOutside -> Rsp. to corresponding req.Src
// 	}

// 	c.tickReturn = madeProgress
// 	return madeProgress
// }

// Tick checks if make progress
func (c *Comp) Tick() bool {
	// now := c.Engine.CurrentTime()
	// c.printReturn = false
	// if now >= c.recordTime+0.000001 && c.deviceID == 5 {
	// 	c.recordTime = now
	// 	c.printReturn = false
	// }
	c.traceProcess = false
	c.debugProcess = false
	c.debugAddress = 12884956160

	madeProgress := false
	temp := false

	temp = c.processFromCtrlPort()
	madeProgress = temp || madeProgress
	if c.printReturn {
		fmt.Printf("[DEBUG RDMA 5]\treturn 1: %v\n", temp)
	}

	if c.isDraining {
		temp = c.drainRDMA()
		madeProgress = temp || madeProgress
		if c.printReturn {
			fmt.Printf("[DEBUG RDMA 5]\treturn 2: %v\n", temp)
		}
	}

	for i := 0; i < c.outgoingRspPerCycle; i++ {
		temp = c.processFromL2() // 3. Rsp. from RDMADataInside -> Rsp. to corresponding req.Src
		madeProgress = temp || madeProgress
		if c.printReturn {
			fmt.Printf("[DEBUG RDMA 5]\treturn 4: %v\n", temp)
		}
	}

	for i := 0; i < c.incomingRspPerCycle; i++ {
		temp = c.processIncomingRsp() // 4. Rsp. from RDMARequestOutside -> Rsp. to corresponding req.Src
		madeProgress = temp || madeProgress
		if c.printReturn {
			fmt.Printf("[DEBUG RDMA 5]\treturn 6: %v\n", temp)
		}
	}

	for i := 0; i < c.outgoingReqPerCycle; i++ {
		temp = c.processFromL1() // 1. Req. from RDMARequestInside -> RDMARequestOutside
		madeProgress = temp || madeProgress
		if c.printReturn {
			fmt.Printf("[DEBUG RDMA 5]\treturn 3: %v\n", temp)
		}
	}

	for i := 0; i < c.incomingReqPerCycle; i++ {
		temp = c.processIncomingReq() // 2. Req. from RDMADataOutside -> Req. to RDMADataInside
		madeProgress = temp || madeProgress
		if c.printReturn {
			fmt.Printf("[DEBUG RDMA 5]\treturn 5: %v\n", temp)
		}
	}

	for i := 0; i < c.outgoingRspPerCycle; i++ {
		temp = c.processFromInvInside()
		madeProgress = temp || madeProgress
	}

	c.tickReturn = madeProgress
	return madeProgress
}

func (c *Comp) processFromCtrlPort() bool {
	req := c.CtrlPort.PeekIncoming()
	if req == nil {
		// if c.deviceID == 5 {
		// 	fmt.Printf("[RDMA 5]\tReturn false: No valid request from CtrlPort\n")
		// }
		return false
	}

	switch req := req.(type) {
	case *DrainReq:
		fmt.Printf("[RDMA %d]\tStart RDMA Drain\n", c.deviceID)
		c.currentDrainReq = req
		c.isDraining = true
		c.pauseIncomingReqsFromL1 = true

		c.CtrlPort.RetrieveIncoming()

		// RDMA drain -> 현재 진행 중인 요청을 모두 없애버리기
		// L2 cache에서 요청을 받지 않음 -> L2 cache queue가 full 됨 -> RDMA 멈춤 -> drain 요청 처리 불가
		// 따라서 drain 요청 시, 진행되지 않은 요청은 없애야 할 듯?
		// c.transactionsFromInside = nil
		// c.transactionsFromOutside = nil

		return true
	case *RestartReq:
		return c.processRDMARestartReq(req)
	default:
		log.Panicf("cannot process request of type %s", reflect.TypeOf(req))
		return false
	}
}

func (c *Comp) processRDMARestartReq(req *RestartReq) bool {
	restartCompleteRsp := RestartRspBuilder{}.
		WithSrc(c.CtrlPort.AsRemote()).
		// WithDst(c.currentDrainReq.Src).
		WithDst(req.Meta().Src).
		Build()
	err := c.CtrlPort.Send(restartCompleteRsp)
	fmt.Printf("[RDMA %d]\tTry to Send Restart Rsp to driver\n", c.deviceID)

	if err != nil {
		// if c.deviceID == 5 {
		// 	fmt.Printf("[RDMA 5]\tReturn false: Fail to send restart rsp to driver\n")
		// }
		return false
	}

	c.currentDrainReq = nil
	c.pauseIncomingReqsFromL1 = false
	c.CtrlPort.RetrieveIncoming()

	fmt.Printf("\t\tSuccess to Send Restart Rsp to driver\n")
	// *(c.AccessCounter) = make(map[vm.PID]map[uint64]uint8)

	return true
}

func (c *Comp) drainRDMA() bool {
	drainCompleteRsp := DrainRspBuilder{}.
		WithSrc(c.CtrlPort.AsRemote()).
		WithDst(c.currentDrainReq.Src).
		Build()

	err := c.CtrlPort.Send(drainCompleteRsp)
	if err != nil {
		// if c.deviceID == 5 {
		// 	fmt.Printf("[RDMA 5]\tReturn false: Fail to send drain rsp to driver\n")
		// }
		return false
	}

	c.transactionsFromInside = nil
	c.transactionsFromOutside = nil
	c.invalidationFromInside = nil
	c.invalidationFromOutside = nil

	for c.RDMADataInside.RetrieveIncoming() != nil {
	}
	for c.RDMADataOutside.RetrieveIncoming() != nil {
	}
	for c.RDMARequestInside.RetrieveIncoming() != nil {
	}
	for c.RDMARequestOutside.RetrieveIncoming() != nil {
	}
	for c.RDMAInvInside.RetrieveIncoming() != nil {
	}

	c.reqFromL1Buf = nil
	c.procInvReqBuf = nil
	c.incomingReqBuf = nil
	c.procInvRspBuf = nil

	c.isDraining = false

	return true
}

func (c *Comp) fullyDrained() bool {
	return len(c.transactionsFromOutside) == 0 &&
		len(c.transactionsFromInside) == 0
}

func (c *Comp) processFromL1() bool {
	if c.pauseIncomingReqsFromL1 {
		c.returnFalse0 = "pauseIncomingReqsFromL1"
		return false
	}

	madeProgress := false
	for {
		if len(c.reqFromL1Buf) > 0 {
			item := c.reqFromL1Buf[0]
			err := c.RDMARequestOutside.Send(item)

			if err == nil {
				c.reqFromL1Buf = c.reqFromL1Buf[1:]
				madeProgress = true

				continue
			}
		}

		req := c.RDMARequestInside.PeekIncoming()
		if req == nil {
			if !madeProgress {
				c.returnFalse0 = "There is no req from RDMAReqInside"
			}

			return madeProgress
		}

		switch req := req.(type) {
		case mem.AccessReq:
			ret := c.processReqFromL1(req)
			if !ret {
				if !madeProgress {
					c.returnFalse0 = "[processReqFromL1]"
				}

				return madeProgress
			} else if c.debugProcess && req.GetAddress() == c.debugAddress {
				fmt.Printf("[%s] [bottomSender]\tSend remote read req - 0: addr %x\n", c.Name(), req.GetAddress())
			}

			c.recordMsgSend(req)
			madeProgress = true
		default:
			log.Panicf("cannot process request of type %s", reflect.TypeOf(req))
			return false
		}
	}
}

func (c *Comp) processReqFromL1(
	req mem.AccessReq,
) bool {
	dst := c.RemoteRDMAAddressTable.Find(req.GetAddress())
	cloned := c.cloneReq(req)
	cloned.Meta().Src = c.RDMARequestOutside.AsRemote()
	cloned.Meta().Dst = dst
	cloned.SetSrcRDMA(cloned.Meta().Src)

	err := (*sim.SendError)(nil)
	if !c.RDMARequestOutside.CanSend() {
		c.reqFromL1Buf = append(c.reqFromL1Buf, cloned)
	} else {
		err = c.RDMARequestOutside.Send(cloned)
	}

	if err != nil {
		return false
	}

	c.RDMARequestInside.RetrieveIncoming()

	trans := transaction{
		fromInside: req,
		toOutside:  cloned,
	}
	c.transactionsFromInside = append(c.transactionsFromInside, trans)

	return true
}

func (c *Comp) processFromL2() bool {
	for {
		req := c.RDMADataInside.PeekIncoming()
		if req == nil {
			c.returnFalse1 = "There is no req from RDMADataInside"
			return false
		}

		switch req := req.(type) {
		case mem.AccessRsp:
			c.returnFalse1 = ""
			ret := c.processRspFromL2(req)
			if ret {
				c.recordMsgSend(req)
			} else if c.debugProcess && req.GetOrigin().GetAddress() == c.debugAddress {
				fmt.Printf("[%s] [bottomSender]\tSend remote read rsp - 2: addr %x\n", c.Name(), req.GetOrigin().GetAddress())
			}

			return ret
		default:
			panic(fmt.Sprintf("unknown req type %T, Src %s", req, req.Meta().Src))
		}
	}
}

func (c *Comp) processRspFromL2(
	rsp mem.AccessRsp,
) bool {
	c.returnFalse1 = "[processRspFromL2]"
	if !c.RDMADataOutside.CanSend() {
		c.returnFalse1 = "[processRspFromL2] Cannot send to RDMADataOutside"
		return false
	}

	transactionIndex := c.findTransactionByRspToID(
		rsp.GetRspTo(), c.transactionsFromOutside)
	if transactionIndex == -1 {
		c.RDMADataInside.RetrieveIncoming()

		c.returnFalse1 = "[processRspFromL2] Cannot find transaction"
		// return false
		return true

		// fmt.Printf("[%s]\t４. Cannot find transaction for DataReadyRsp with RspTo %s, Addr %x\n", c.Name(), rsp.GetRspTo(), rsp.GetOrigin().GetAddress())
	}
	trans := &(c.transactionsFromOutside[transactionIndex])

	// rspToOutside := c.cloneRsp(rsp, trans.fromOutside.Meta().ID)
	rspToOutside := c.cloneRsp(rsp, trans.fromOutside.Meta().ID, trans.fromOutside.(mem.AccessReq).GetAddress())
	rspToOutside.Meta().Src = c.RDMADataOutside.AsRemote()
	rspToOutside.Meta().Dst = trans.fromOutside.Meta().Src

	err := c.RDMADataOutside.Send(rspToOutside)
	if err != nil {
		c.returnFalse1 = "[processRspFromL2] Failed to send to RDMADataOutside"
		return false
	}
	c.RDMADataInside.RetrieveIncoming()

	trans.ack++
	if trans.ack >= rsp.GetWaitFor() {
		// if rsp.GetWaitFor() != 1 {
		// 	fmt.Printf("[RDMA %d]\tSend last rsp for %x from %s to %s\n\t\t\tack: %d %d\n", c.deviceID,
		// 		trans.fromOutside.(mem.AccessReq).GetAddress(), rsp.Meta().Src, rspToOutside.Meta().Dst, trans.ack, rsp.GetWaitFor())
		// }

		c.traceOutsideInEnd(*trans)

		c.transactionsFromOutside =
			append(c.transactionsFromOutside[:transactionIndex],
				c.transactionsFromOutside[transactionIndex+1:]...)
	}

	// if strings.Contains(c.Name(), "GPU[3]") {
	// 	fmt.Printf("[%s]\t4. Response(%s) %x from %s to %s\n", c.Name(), rsp.GetRspTo(), trans.fromOutside.(mem.AccessReq).GetAddress(), rspToOutside.Meta().Src, rspToOutside.Meta().Dst)
	// }
	return true

}

func (c *Comp) processIncomingRsp() bool {
	madeProgress := false
	popInvReqBuf := false

	if len(c.procInvReqBuf) > 0 {
		item := c.procInvReqBuf[0]
		err := c.RDMADataInside.Send(item)
		if err == nil {
			c.procInvReqBuf = c.procInvReqBuf[1:]

			madeProgress = true
			popInvReqBuf = true
		}
	}

	req := c.RDMARequestOutside.PeekIncoming()
	if req == nil {
		if !madeProgress {
			c.returnFalse3 = "There is no req from RDMARequestOutside"
		}
		return madeProgress
	}

	switch req := req.(type) {
	case mem.AccessRsp:
		ret := c.processRspFromRDMARequestOutside(req)
		if ret {
			c.recordMsgSend(req)
			madeProgress = true
			if c.debugProcess && req.GetOrigin().GetAddress() == c.debugAddress {
				fmt.Printf("[%s] [bottomSender]\tReceive remote read rsp - 3: addr %x\n", c.Name(), req.GetOrigin().GetAddress())
			}
		}

		if !madeProgress {
			c.returnFalse3 = "[processRspFromRDMARequestOutside]"
		}
	case *mem.InvReq:
		if !popInvReqBuf {
			ret := c.processInvReq(req)
			if ret {
				c.recordMsgSend(req)
				madeProgress = true
			}

			if !madeProgress {
				c.returnFalse3 = "[processInvReq]"
			}
		}
	default:
		log.Panicf("cannot process request of type %s", reflect.TypeOf(req))
		return false
	}

	return madeProgress
}

func (c *Comp) processRspFromRDMARequestOutside(
	rsp mem.AccessRsp,
) bool {
	if !c.RDMARequestInside.CanSend() {
		// if c.deviceID == 5 {
		// 	fmt.Printf("[RDMA 5]\tReturn false: processRspFromRDMARequestOutside: Cannot send to RDMARequestInside 1\n")
		// }
		return false
	}

	transactionIndex := c.findTransactionByRspToID(
		rsp.GetRspTo(), c.transactionsFromInside)
	var trans transaction
	var rspToInside mem.AccessRsp

	if transactionIndex == -1 {
		rspToInside = c.cloneRsp(rsp, "", rsp.GetOrigin().GetAddress())
		rspToInside.Meta().Src = c.RDMARequestInside.AsRemote()
		rspToInside.Meta().Dst = c.localModuleBottoms.Find(rsp.GetOrigin().GetAddress())

		// fmt.Printf("[RDMA %d]\tSend prefetched data %x to %s\n",
		// 	c.deviceID, rsp.GetOrigin().GetAddress(), rspToInside.Meta().Dst)

		// c.RDMARequestOutside.RetrieveIncoming()
		// fmt.Printf("[%s]\t4. Cannot find transaction for DataReadyRsp with RspTo %s\n", c.Name(), rsp.GetRspTo())
		// return false
	} else {
		trans = c.transactionsFromInside[transactionIndex]
		rspToInside = c.cloneRsp(rsp, trans.fromInside.Meta().ID, trans.fromInside.(mem.AccessReq).GetAddress())
		rspToInside.Meta().Src = c.RDMARequestInside.AsRemote()
		rspToInside.Meta().Dst = trans.fromInside.Meta().Src

		// fmt.Printf("[RDMA %d]\tSend data %x to %s\n",
		// 	c.deviceID, rsp.GetOrigin().GetAddress(), rspToInside.Meta().Dst)
	}

	err := c.RDMARequestInside.Send(rspToInside)
	if err != nil {
		// if c.deviceID == 5 {
		// 	fmt.Printf("[RDMA 5]\tReturn false: processRspFromRDMARequestOutside: Cannot send to RDMARequestInside 2\n")
		// }
		return false
	}

	c.RDMARequestOutside.RetrieveIncoming()

	if transactionIndex != -1 {
		c.transactionsFromInside =
			append(c.transactionsFromInside[:transactionIndex],
				c.transactionsFromInside[transactionIndex+1:]...)

		// c.recordAccessCount(trans)

		c.traceInsideOutEnd(trans)
	}

	// fmt.Printf("[%s]\t4. Response %x from %s to %s\n", c.Name(), trans.fromInside.(mem.AccessReq).GetAddress(), rsp.Meta().Src, rspToInside.Meta().Dst)
	return true
}

func (c *Comp) processInvReq(
	req *mem.InvReq,
) bool {
	reqToBottom := mem.InvReqBuilder{}.
		WithSrc(c.RDMAInvInside.AsRemote()).
		WithDst(c.localInvModules.Find(req.Address)).
		WithPID(req.PID).
		WithAddress(req.Address).
		WithReqFrom(req.Meta().ID).
		WithDstRDMA(req.DstRDMA).
		WithRegionID(req.RegionID).
		WithIsWriteInv(req.IsWriteInv).
		Build()

	err := (*sim.SendError)(nil)
	if !c.RDMAInvInside.CanSend() {
		c.procInvReqBuf = append(c.procInvReqBuf, reqToBottom)
	} else {
		err = c.RDMAInvInside.Send(reqToBottom)
	}
	if err == nil {
		c.RDMARequestOutside.RetrieveIncoming()
		c.invalidationFromOutside = append(c.invalidationFromOutside, req)

		// fmt.Printf("[%s]\tC. (%s -> %s) Send InvReq for Addr %x from %s to %s\n",
		// 	c.Name(), req.Meta().ID, reqToBottom.Meta().ID, req.Address, req.Meta().Src, reqToBottom.Meta().Dst)
		return true
	}

	// if c.deviceID == 5 {
	// 	fmt.Printf("[RDMA 5]\tReturn false: processInvReq: Cannot send to RDMARequestOutside\n")
	// }
	return false
}

func (c *Comp) recordAccessCount(
	trans transaction,
) bool {

	req := trans.fromInside.(mem.AccessReq)
	vAddr := req.GetVAddr()
	byteSize := req.GetByteSize()
	pid := req.GetPID()

	startPage := vAddr >> c.log2PageSize
	endPage := (vAddr + byteSize - 1) >> c.log2PageSize

	ac := *(c.AccessCounter)
	innerMap, found := ac[pid]

	if !found {
		innerMap = make(map[uint64]uint8)
		ac[pid] = innerMap
	}

	for addr := startPage; addr <= endPage; addr++ {
		if innerMap[addr] < 255 {
			innerMap[addr]++
		}
	}

	return true
}

func (c *Comp) processIncomingReq() bool {
	madeProgress := false
	popIncomingReqBuf := false
	popProcInvRspBuf := false

	if len(c.incomingReqBuf) > 0 {
		item := c.incomingReqBuf[0]
		err := c.RDMADataInside.Send(item)
		if err == nil {
			c.incomingReqBuf = c.incomingReqBuf[1:]
			madeProgress = true
			popIncomingReqBuf = true
		}
	}

	if len(c.procInvRspBuf) > 0 {
		item := c.procInvRspBuf[0]
		err := c.RDMADataInside.Send(item)
		if err == nil {
			c.procInvRspBuf = c.procInvRspBuf[1:]
			madeProgress = true
			popProcInvRspBuf = true
		}
	}

	req := c.RDMADataOutside.PeekIncoming()
	if req == nil {
		if !madeProgress {
			c.returnFalse2 = "There is no req from RDMADataOutside"
		}
		return madeProgress
	}

	switch req := req.(type) {
	case mem.AccessReq:
		if !popIncomingReqBuf {
			ret := c.processReqFromRDMADataOutside(req)
			if ret {
				c.recordMsgSend(req)
				madeProgress = true
			} else if c.debugProcess && req.GetAddress() == c.debugAddress {
				fmt.Printf("[%s] [bottomSender]\tReceive remote read req - 1: addr %x\n", c.Name(), req.GetAddress())
			}

			if !madeProgress {

				c.returnFalse2 = "[processReqFromRDMADataOutside]"
			}
		}
	case *mem.InvRsp:
		if !popProcInvRspBuf {
			ret := c.processInvRsp(req)
			if ret {
				c.recordMsgSend(req)
				madeProgress = true
			}

			if !madeProgress {
				c.returnFalse2 = "[processReqFromRDMADataOutside]"
			}
		}
	default:
		log.Panicf("cannot process request of type %s", reflect.TypeOf(req))
		return false
	}

	return madeProgress
}

func (c *Comp) processReqFromRDMADataOutside(
	req mem.AccessReq,
) bool {
	dst := c.localModules.Find(req.GetAddress())

	cloned := c.cloneReq(req)
	cloned.Meta().Src = c.RDMADataInside.AsRemote()
	cloned.Meta().Dst = dst

	err := (*sim.SendError)(nil)
	if !c.RDMADataInside.CanSend() {
		c.incomingReqBuf = append(c.incomingReqBuf, cloned)
	} else {
		err = c.RDMADataInside.Send(cloned)
	}

	if err == nil {
		c.RDMADataOutside.RetrieveIncoming()

		trans := transaction{
			fromOutside: req,
			toInside:    cloned,
		}
		c.transactionsFromOutside =
			append(c.transactionsFromOutside, trans)

		return true
	}

	// if c.deviceID == 5 {
	// 	fmt.Printf("[RDMA 5]\tReturn false: processReqFromRDMADataOutside: Cannot send to RDMADataInside\n")
	// }
	return false
}

func (c *Comp) processInvRsp(
	rsp *mem.InvRsp,
) bool {
	i := c.findInvReqByRspToID(rsp.RespondTo, c.invalidationFromInside)
	if i == -1 {
		fmt.Printf("[RDMA %d]\t3. Cannot find invalidation request for InvRsp with RespondTo %s\n", c.deviceID, rsp.RespondTo)
		c.RDMADataOutside.RetrieveIncoming()
		// return false
		return true
	}
	req := c.invalidationFromInside[i]

	rspToBottom := mem.InvRspBuilder{}.
		WithSrc(c.RDMAInvInside.AsRemote()).
		WithDst(req.Meta().Src).
		WithRspTo(req.ReqFrom).
		WithSrcRDMA(rsp.SrcRDMA).
		Build()

	err := (*sim.SendError)(nil)
	if !c.RDMAInvInside.CanSend() {
		c.procInvRspBuf = append(c.procInvRspBuf, rspToBottom)
	} else {
		err = c.RDMAInvInside.Send(rspToBottom)
	}

	if err == nil {
		c.RDMADataOutside.RetrieveIncoming()
		c.invalidationFromInside = append(c.invalidationFromInside[:i], c.invalidationFromInside[i+1:]...)
		// fmt.Printf("[RDMA %d]\tFinalize Inv Req - 2: %s -> %s, %s\n", c.deviceID, rsp.RespondTo, req.ReqFrom, rspToBottom.Dst)

		return true
	}

	return false
}

func (c *Comp) processFromInvInside() bool {
	req := c.RDMAInvInside.PeekIncoming()
	if req == nil {
		return false
	}

	switch req := req.(type) {
	case *mem.InvReq:
		if c.sendInvReq(req) {
			c.recordMsgSend(req)
			return true
		}
		return false

	case *mem.InvRsp:
		if c.sendInvRsp(req) {
			c.recordMsgSend(req)
			return true
		}
		return false

	default:
		panic(fmt.Sprintf("unknown req type in RDMAInvInside: %s", reflect.TypeOf(req)))
	}
}

func (c *Comp) sendInvReq(
	req *mem.InvReq,
) bool {
	if !c.RDMADataOutside.CanSend() {
		// if c.deviceID == 5 {
		// 	fmt.Printf("[RDMA 5]\tReturn false: sendInvReq: Cannot send to RDMADataOutside 1\n")
		// }
		return false
	}

	reqToOutside := mem.InvReqBuilder{}.
		WithSrc(c.RDMADataOutside.AsRemote()).
		WithDst(req.DstRDMA).
		WithPID(req.PID).
		WithAddress(req.Address).
		WithReqFrom(req.Meta().ID).
		WithDstRDMA(req.DstRDMA).
		WithRegionID(req.RegionID).
		WithIsWriteInv(req.IsWriteInv).
		Build()

	err := c.RDMADataOutside.Send(reqToOutside)
	if err == nil {
		c.RDMAInvInside.RetrieveIncoming()
		c.invalidationFromInside = append(c.invalidationFromInside, req)

		// fmt.Printf("[%s]\tB. (%s -> %s) Send InvReq for Addr %x from %s to %s\n",
		// 	c.Name(), req.Meta().ID, reqToOutside.Meta().ID, req.Address, req.Meta().Src, reqToOutside.Meta().Dst)
		return true
	}

	// if c.deviceID == 5 {
	// 	fmt.Printf("[RDMA 5]\tReturn false: sendInvReq: Cannot send to RDMADataOutside 2\n")
	// }
	return false
}

func (c *Comp) sendInvRsp(
	rsp *mem.InvRsp,
) bool {
	if !c.RDMADataOutside.CanSend() {
		// if c.deviceID == 5 {
		// 	fmt.Printf("[RDMA 5]\tReturn false: sendInvRsp: Cannot send to RDMADataOutside 1 \n")
		// }
		return false
	}

	i := c.findInvReqByRspToID(rsp.RespondTo, c.invalidationFromOutside)
	if i == -1 {
		fmt.Printf("[RDMA %d]\t2. Cannot find invalidation request for InvRsp with RespondTo %s\n", c.deviceID, rsp.RespondTo)
		c.RDMAInvInside.RetrieveIncoming()
		// return false
		return true
	}
	req := c.invalidationFromOutside[i]

	rspToOutside := mem.InvRspBuilder{}.
		WithSrc(c.RDMADataOutside.AsRemote()).
		WithDst(req.Meta().Src).
		WithRspTo(req.ReqFrom).
		WithSrcRDMA(c.RDMARequestOutside.AsRemote()).
		Build()

	err := c.RDMADataOutside.Send(rspToOutside)
	if err == nil {
		c.RDMAInvInside.RetrieveIncoming()
		c.invalidationFromOutside = append(c.invalidationFromOutside[:i], c.invalidationFromOutside[i+1:]...)
		// fmt.Printf("[RDMA %d]\tFinalize Inv Req - 1: %s -> %s\n", c.deviceID, rsp.RespondTo, req.ReqFrom)

		return true
	}

	// if c.deviceID == 5 {
	// 	fmt.Printf("[RDMA 5]\tReturn false: sendInvRsp: Cannot send to RDMADataOutside 2\n")
	// }
	return false
}

func (c *Comp) findTransactionByRspToID(
	rspTo string,
	transactions []transaction,
) int {
	for i, trans := range transactions {
		if trans.toOutside != nil && trans.toOutside.Meta().ID == rspTo {
			return i
		}

		if trans.toInside != nil && trans.toInside.Meta().ID == rspTo {
			return i
		}
	}

	// log.Panicf("transaction %s not found", rspTo)
	// return 0
	return -1
}

func (c *Comp) findInvReqByRspToID(
	rspTo string,
	req []*mem.InvReq,
) int {
	for i, rq := range req {
		if rq.Meta().ID == rspTo {
			return i
		}
	}

	return -1
}

func (c *Comp) cloneReq(origin mem.AccessReq) mem.AccessReq {
	switch origin := origin.(type) {
	case *mem.ReadReq:
		read := mem.ReadReqBuilder{}.
			WithSrc(origin.Src).
			WithDst(origin.Dst).
			WithReqFrom(c.Name()).
			WithPID(origin.GetPID()).
			WithAddress(origin.Address).
			WithVAddr(origin.GetVAddr()).
			WithByteSize(origin.AccessByteSize).
			Build()
		read.SetSrcRDMA(origin.SrcRDMA)
		return read
	case *mem.WriteReq:
		write := mem.WriteReqBuilder{}.
			WithSrc(origin.Src).
			WithDst(origin.Dst).
			WithReqFrom(c.Name()).
			WithPID(origin.GetPID()).
			WithAddress(origin.Address).
			WithVAddr(origin.GetVAddr()).
			WithData(origin.Data).
			WithDirtyMask(origin.DirtyMask).
			WithInfo((*(c.dirtyMask))[c.deviceID-1][origin.GetPID()][origin.GetVAddr()>>c.log2PageSize]).
			Build()
		write.SetSrcRDMA(origin.SrcRDMA)
		return write
	default:
		log.Panicf("cannot clone request of type %s",
			reflect.TypeOf(origin))
	}
	return nil
}

func (c *Comp) cloneRsp(origin mem.AccessRsp, rspTo string, addr uint64) mem.AccessRsp {
	if addr != origin.GetOrigin().GetAddress() {
		rspTo = ""
	}

	switch origin := origin.(type) {
	case *mem.DataReadyRsp:
		rsp := mem.DataReadyRspBuilder{}.
			WithSrc(origin.Src).
			WithDst(origin.Dst).
			WithRspTo(rspTo).
			WithData(origin.Data).
			WithOrigin(origin.Origin).
			Build()
		return rsp
	case *mem.WriteDoneRsp:
		rsp := mem.WriteDoneRspBuilder{}.
			WithSrc(origin.Src).
			WithDst(origin.Dst).
			WithRspTo(rspTo).
			WithOrigin(origin.Origin).
			Build()
		return rsp
	default:
		log.Panicf("cannot clone request of type %s",
			reflect.TypeOf(origin))
	}
	return nil
}

// SetFreq sets freq
func (c *Comp) SetFreq(freq sim.Freq) {
	c.TickingComponent.Freq = freq
}

func (c *Comp) traceInsideOutStart(req mem.AccessReq, cloned mem.AccessReq) {
	if !c.traceProcess {
		return
	}

	if len(c.Hooks()) == 0 {
		return
	}

	tracing.StartTaskWithSpecificLocation(
		tracing.MsgIDAtReceiver(req, c),
		req.Meta().ID+"_req_out",
		c,
		"req_in",
		reflect.TypeOf(req).String(),
		c.Name()+".InsideOut",
		req,
	)

	tracing.StartTaskWithSpecificLocation(
		cloned.Meta().ID+"_req_out",
		tracing.MsgIDAtReceiver(req, c),
		c,
		"req_out",
		reflect.TypeOf(req).String(),
		c.Name()+".InsideOut",
		cloned,
	)
}

func (c *Comp) traceOutsideInStart(req mem.AccessReq, cloned mem.AccessReq) {
	if !c.traceProcess {
		return
	}

	if len(c.Hooks()) == 0 {
		return
	}

	tracing.StartTaskWithSpecificLocation(
		tracing.MsgIDAtReceiver(req, c),
		req.Meta().ID+"_req_out",
		c,
		"req_in",
		reflect.TypeOf(req).String(),
		c.Name()+".OutsideIn",
		req,
	)

	tracing.StartTaskWithSpecificLocation(
		cloned.Meta().ID+"_req_out",
		tracing.MsgIDAtReceiver(req, c),
		c,
		"req_out",
		reflect.TypeOf(req).String(),
		c.Name()+".OutsideIn",
		cloned,
	)
}

func (c *Comp) traceInsideOutEnd(trans transaction) {
	if !c.traceProcess {
		return
	}

	if len(c.Hooks()) == 0 {
		return
	}

	tracing.TraceReqFinalize(trans.toOutside, c)
	tracing.TraceReqComplete(trans.fromInside, c)
}

func (c *Comp) traceOutsideInEnd(trans transaction) {
	tracing.TraceReqFinalize(trans.toInside, c)
	tracing.TraceReqComplete(trans.fromOutside, c)
}

func (c *Comp) printWriteMask(req mem.AccessReq) {
	if req.GetVAddr() == 0 {
		return
	}

	switch req := req.(type) {
	case *mem.WriteReq:
		fmt.Printf("\n======================================================================================\n")
		pid := req.GetPID()
		vpn := req.GetVAddr() >> c.log2PageSize
		// var reqFrom uint64
		// fmt.Sscanf(req.ReqFrom, "GPU[%d].RDMA", &reqFrom)

		fmt.Printf("[GPU[%d].RDMA]\tRemote Write Req VPN %x from %s\n", c.deviceID, vpn, req.ReqFrom)
		for i, list := range *(c.dirtyMask) {
			fmt.Printf("\t\tDirtyMask GPU %d: %v\n", i+1, list[pid][vpn])
		}
		for i, list := range *(c.readMask) {
			fmt.Printf("\t\tReadMask  GPU %d: %v\n", i+1, list[pid][vpn])
		}

		// for j, mask := range *(c.dirtyMask) {
		// 	if uint64(j) == reqFrom-1 {
		// 		continue
		// 	}
		// 	if list, _ := mask[pid][vpn]; len(list) != 0 {
		// 		sharing := false
		// 		for idx, b := range req.Info.([]uint8) {
		// 			if b == 1 && list[idx] == 1 {
		// 				fmt.Printf("\t\tShared Write Detected with GPU %d and GPU %d\n", j+1, c.deviceID)
		// 				sharing = true
		// 				break
		// 			}
		// 		}
		// 		if !sharing {
		// 			fmt.Printf("\t\tFalse Shared Write Detected\n")
		// 		}
		// 	}
		// }
		// for j, mask := range *(c.readMask) {
		// 	if uint64(j) == reqFrom-1 {
		// 		continue
		// 	}
		// 	if list, _ := mask[pid][vpn]; len(list) != 0 {
		// 		sharing := false
		// 		for idx, b := range req.Info.([]uint8) {
		// 			if b == 1 && list[idx] == 1 {
		// 				fmt.Printf("\t\tShared Read/Write Detected with GPU %d and GPU %d\n", j+1, c.deviceID)
		// 				sharing = true
		// 				break
		// 			}
		// 		}
		// 		if !sharing {
		// 			fmt.Printf("\t\tFalse Shared Read/Write Detected\n")
		// 		}
		// 	}
		// }
		fmt.Printf("======================================================================================\n\n")
	case *mem.ReadReq:
		fmt.Printf("\n======================================================================================\n")
		pid := req.GetPID()
		vpn := req.GetVAddr() >> c.log2PageSize
		// var reqFrom uint64
		// fmt.Sscanf(req.ReqFrom, "GPU[%d].RDMA", &reqFrom)

		fmt.Printf("[GPU[%d].RDMA]\tRemote Read Req VPN %x from %s\n", c.deviceID, vpn, req.ReqFrom)
		for i, list := range *(c.dirtyMask) {
			fmt.Printf("\t\tDirtyMask GPU %d: %v\n", i+1, list[pid][vpn])
		}
		for i, list := range *(c.readMask) {
			fmt.Printf("\t\tReadMask  GPU %d: %v\n", i+1, list[pid][vpn])
		}

		// for j, mask := range *(c.dirtyMask) {
		// 	if uint64(j) == reqFrom-1 {
		// 		continue
		// 	}
		// 	if list, _ := mask[pid][vpn]; len(list) != 0 {
		// 		sharing := false
		// 		for idx, b := range req.Info.([]uint8) {
		// 			if b == 1 && list[idx] == 1 {
		// 				fmt.Printf("\t\tShared Write Detected with GPU %d and GPU %d\n", j+1, c.deviceID)
		// 				sharing = true
		// 				break
		// 			}
		// 		}
		// 		if !sharing {
		// 			fmt.Printf("\t\tFalse Shared Write Detected\n")
		// 		}
		// 	}
		// }
		// for j, mask := range *(c.readMask) {
		// 	if uint64(j) == reqFrom-1 {
		// 		continue
		// 	}
		// 	if list, _ := mask[pid][vpn]; len(list) != 0 {
		// 		sharing := false
		// 		for idx, b := range req.Info.([]uint8) {
		// 			if b == 1 && list[idx] == 1 {
		// 				fmt.Printf("\t\tShared Read/Write Detected with GPU %d and GPU %d\n", j+1, c.deviceID)
		// 				sharing = true
		// 				break
		// 			}
		// 		}
		// 		if !sharing {
		// 			fmt.Printf("\t\tFalse Shared Read/Write Detected\n")
		// 		}
		// 	}
		// }
		fmt.Printf("======================================================================================\n\n")
	default:
	}
}

func (c *Comp) recordMsgSend(req sim.Msg) {
	req = req.Clone()

	what := ""
	switch req := req.(type) {
	case *mem.ReadReq:
		what = "Read Req" + fmt.Sprintf(" %d", req.TrafficBytes)
	case *mem.WriteReq:
		what = "Write Req" + fmt.Sprintf(" %d", req.TrafficBytes)
	case *mem.InvReq:
		what = "Inv Req" + fmt.Sprintf(" %d", req.TrafficBytes)
	case *mem.DataReadyRsp:
		what = "Read Rsp" + fmt.Sprintf(" %d", req.TrafficBytes)
	case *mem.WriteDoneRsp:
		what = "Write Rsp" + fmt.Sprintf(" %d", req.TrafficBytes)
	case *mem.InvRsp:
		what = "Inv Rsp" + fmt.Sprintf(" %d", req.TrafficBytes)
	default:
	}

	tracing.TraceReqReceive(req, c)
	tracing.AddTaskStep(req.Meta().ID, c, what)
	tracing.TraceReqComplete(req, c)
}
