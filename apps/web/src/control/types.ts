export type ApplicationControl = {
  maintenance_enabled: boolean;
  bank_enabled: boolean;
  duel_enabled: boolean;
  updated_at: string;
};

export type ContractControl = {
  mode: 'bank' | 'duel';
  address: string;
  network: number;
  status: string;
  code_hash: string;
  code_hash_matches: boolean;
  balance_nano: number;
  locked_nano: number;
  withdrawable_nano: number;
  owner: string;
  treasury: string;
  fee_bps: number;
  paused: boolean;
  owner_matches_session: boolean;
  extended_controls: boolean;
  last_transaction_hash: string | null;
  error: string | null;
};

export type ControlOverview = {
  wallet: string;
  application: ApplicationControl;
  metrics: {
    users: number;
    bank_positions: number;
    active_bank_positions: number;
    duel_offers: number;
    active_duels: number;
    worker_healthy: boolean;
  };
  contracts: ContractControl[];
  audit: Array<{
    id: string;
    action: string;
    target: string;
    status: string;
    created_at: string;
  }>;
  generated_at: string;
};

export type ControlActionInput = {
  mode: 'bank' | 'duel';
  action: 'pause' | 'fund_reserve' | 'withdraw_surplus' | 'set_fee' | 'set_treasury' | 'set_owner';
  amount_nano?: number;
  fee_bps?: number;
  address?: string;
  paused?: boolean;
  confirmation?: string;
};

export type ControlTransaction = {
  audit_id: string;
  operation: string;
  address: string;
  amount_nano: string;
  payload: string;
  valid_until: number;
  query_id: number;
  network: number;
};
