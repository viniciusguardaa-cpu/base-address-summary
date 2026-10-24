# Base Address Activity Summary

Fast, cheap wallet triage for agents screening many Base addresses.

## Endpoint
- `GET /health` — free
- `GET /summary?address=0x...` — 0.001 USDC per call
- `POST /summary` — 0.001 USDC per call (body `{"address":"0x..."}`)

## What you get
```json
{
  "address": "0x...",
  "eth_balance": 1.234,
  "usdc_balance": 5.678,
  "nonce": 42,
  "is_contract": false,
  "code_size": 0
}
```

## Payment
- Chain: Base mainnet
- Asset: USDC (0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913)
- Price: 0.001 USDC per call
- PayTo: 0x65aa59025C4AcD8CD7ba2051ecb9152abaE4fcC6
- Header: `X-Payment-Tx: <tx_hash>` (after sending USDC to pay_to)

## Use cases
- Screen hundreds of addresses for activity level before deep analysis
- Quick contract-vs-EOA classification
- Balance triage for airdrop/eligibility checks
- Cheaper alternative to deep oracle when you only need surface-level data

## Links
- Source: https://github.com/viniciusguardaa-cpu/base-address-summary
- Complement: https://github.com/viniciusguardaa-cpu/base-oracle (deep analysis, $0.05/call)
