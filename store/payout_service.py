from django.utils import timezone
from subscriptions.services.gateways import (
    BachsGateway,
    get_active_gateway_name,
    validate_positive_amount,
)

NIGERIAN_BANK_CODES = {
    'Guaranty Trust Bank (GTBank)': '000013',
    'Access Bank': '000014',
    'Zenith Bank': '000015',
    'First Bank of Nigeria': '000016',
    'United Bank for Africa (UBA)': '000004',
    'OPay Digital Services': '100004',
    'PalmPay': '100033',
    'Kuda Microfinance Bank': '090267',
    'Moniepoint Microfinance Bank': '090405',
    'Fidelity Bank': '000007',
    'First City Monument Bank (FCMB)': '000003',
    'Stanbic IBTC Bank': '000012',
    'Sterling Bank': '000001',
    'Union Bank of Nigeria': '000018',
    'Wema Bank (ALAT)': '000017',
    'Keystone Bank': '000002',
    'Polaris Bank': '000008',
    'Providus Bank': '000023',
    'Taj Bank': '000026',
    'Jaiz Bank': '000006',
    'FairMoney Microfinance Bank': '090328',
}


def resolve_bank_code(bank_name, explicit_code=''):
    """Return explicit bank_code or fall back to known Nigerian NIBSS bank code."""
    code = (explicit_code or '').strip()
    if code:
        return code
    return NIGERIAN_BANK_CODES.get((bank_name or '').strip(), '')


def disburse_store_payout(payout, bank_account, actor_label='auto'):
    """Disburse a pending StorePayout via the active payment gateway."""
    validate_positive_amount(payout.amount, field_name='payout amount')
    if not bank_account or bank_account.account_number != payout.account_number:
        raise ValueError(
            f'Bank account snapshot mismatch for payout {payout.reference}; manual review required.'
        )

    active_gateway = get_active_gateway_name()
    if active_gateway == 'bachs':
        bachs = BachsGateway()
        dest_id = bank_account.bachs_destination_id
        if not dest_id:
            bank_code = resolve_bank_code(bank_account.bank_name, bank_account.bank_code)
            if not bank_code:
                raise ValueError(
                    f'Missing bank_code on {bank_account.bank_name or "bank account"} for Bachs payout. '
                    'Please re-select your bank in Settlement Bank Account.'
                )
            if not bank_account.bank_code:
                bank_account.bank_code = bank_code
                bank_account.save(update_fields=['bank_code', 'updated_at'])
            dest = bachs.create_payout_destination(
                currency=payout.currency,
                account_number=bank_account.account_number,
                bank_code=bank_code,
                name=bank_account.account_name,
            )
            dest_id = dest['destination_id']
            bank_account.bachs_destination_id = dest_id
            bank_account.save(update_fields=['bachs_destination_id', 'updated_at'])

        res = bachs.create_payout(
            destination_id=dest_id,
            amount=payout.amount,
            reference=payout.reference,
            narration=f'Quicksales payout {payout.reference}',
            idempotency_key=payout.idempotency_key or payout.reference,
        )
        payout.gateway = 'bachs'
        payout.gateway_reference = res['payout_id']
        payout.status = 'completed' if res['status'] in ('completed', 'succeeded', 'paid') else 'processing'
        if payout.status == 'completed':
            payout.processed_at = timezone.now()
        payout.admin_notes = (
            (payout.admin_notes + '\n' if payout.admin_notes else '')
            + f'Disbursed via Bachs by {actor_label} (ref={res["payout_id"]}).'
        )
        payout.save(update_fields=['gateway', 'gateway_reference', 'status', 'processed_at', 'admin_notes'])
        return payout

    payout.gateway = active_gateway
    payout.status = 'completed'
    payout.processed_at = timezone.now()
    payout.admin_notes = (
        (payout.admin_notes + '\n' if payout.admin_notes else '')
        + f'Approved for {active_gateway} by {actor_label}.'
    )
    payout.save(update_fields=['gateway', 'status', 'processed_at', 'admin_notes'])
    return payout

