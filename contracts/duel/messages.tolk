struct (0x4C4F4F01) OpenOffer {
    queryId: uint64
    offerId: uint64
    commitment: uint256
    chanceBps: uint16
    totalPool: coins
    expiresAt: uint32
    counterOfferId: uint64
}

struct (0x4C4F4F02) CancelOffer {
    queryId: uint64
    offerId: uint64
}

struct (0x4C4F4F03) MatchOffers {
    queryId: uint64
    firstOfferId: uint64
    secondOfferId: uint64
}

struct (0x4C4F4F04) Reveal {
    queryId: uint64
    duelId: uint64
    offerId: uint64
    secret: uint256
}

struct (0x4C4F4F05) ExpireOffer {
    queryId: uint64
    offerId: uint64
}

struct (0x4C4F4F06) ExpireDuel {
    queryId: uint64
    duelId: uint64
}

struct (0x4C4F4F07) SetPaused {
    queryId: uint64
    paused: bool
}

/// Opens a Telegram direct invite. `inviteId` is public and only identifies
/// the invite; acceptance still requires a backend Ed25519 permit bound to the
/// accepting wallet address.
struct (0x4C4F4F08) OpenDirectOffer {
    queryId: uint64
    offerId: uint64
    commitment: uint256
    chanceBps: uint16
    totalPool: coins
    expiresAt: uint32
    inviteId: uint256
}

struct DirectAcceptance {
    counterOfferId: uint64
    validUntil: uint32
    signature: bits512
}

/// Atomically opens the invited wallet's complementary offer, verifies its
/// address-bound permit and matches the pair.
struct (0x4C4F4F09) AcceptDirectOffer {
    queryId: uint64
    offerId: uint64
    commitment: uint256
    chanceBps: uint16
    totalPool: coins
    expiresAt: uint32
    acceptance: Cell<DirectAcceptance>
}

struct (0x4C4F4F0A) DuelFundReserve {
    queryId: uint64
    amount: coins
}

struct (0x4C4F4F0B) DuelWithdrawSurplus {
    queryId: uint64
    amount: coins
}

struct (0x4C4F4F0C) DuelSetFee {
    queryId: uint64
    feeBps: uint16
}

struct (0x4C4F4F0D) DuelSetTreasury {
    queryId: uint64
    treasury: address
}

struct (0x4C4F4F0E) DuelSetOwner {
    queryId: uint64
    owner: address
}

/// Attached to every terminal winner transfer so indexers can project the result.
struct (0x4C4F4F11) DuelPayout {
    queryId: uint64
    duelId: uint64
    offerId: uint64
    reason: uint8
}

/// Attached to unmatched or no-reveal refunds.
struct (0x4C4F4F12) OfferRefund {
    queryId: uint64
    offerId: uint64
    reason: uint8
}

/// Attached to the protocol fee transfer.
struct (0x4C4F4F13) ProtocolFee {
    queryId: uint64
    duelId: uint64
}

struct (0x4C4F4F14) DuelAdminWithdrawal {
    queryId: uint64
    amount: coins
}
