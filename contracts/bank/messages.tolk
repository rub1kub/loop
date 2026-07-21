struct (0x4C424E01) CreatePosition {
    queryId: uint64
    positionId: uint64
    principal: coins
    multiplierBps: uint16
}

struct (0x4C424E02) SetBankPaused {
    queryId: uint64
    paused: bool
}

struct (0x4C424E11) BankPayout {
    queryId: uint64
    positionId: uint64
    principal: coins
    targetPayout: coins
}

struct (0x4C424E12) BankProtocolFee {
    queryId: uint64
    positionId: uint64
}
