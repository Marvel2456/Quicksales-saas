from django.utils import timezone
from subscriptions.services.gateways import (
    BachsGateway,
    get_active_gateway_name,
    validate_positive_amount,
)

# Bachs /v1/reference/banks uses CBN/Paystack-style bank codes (e.g. 011, 058, 999992),
# whereas SquadCo uses 6-digit NIBSS codes (e.g. 000016, 000013, 100004).
BACHS_BANK_CODES = {
    'Guaranty Trust Bank (GTBank)': '058',
    'Access Bank': '044',
    'Zenith Bank': '057',
    'First Bank of Nigeria': '011',
    'United Bank for Africa (UBA)': '033',
    'OPay Digital Services': '999992',
    'PalmPay': '999991',
    'Kuda Microfinance Bank': '50211',
    'Moniepoint Microfinance Bank': '50515',
    'Fidelity Bank': '070',
    'First City Monument Bank (FCMB)': '214',
    'Stanbic IBTC Bank': '221',
    'Sterling Bank': '232',
    'Union Bank of Nigeria': '032',
    'Wema Bank (ALAT)': '035',
    'Keystone Bank': '082',
    'Polaris Bank': '076',
    'Providus Bank': '101',
    'Taj Bank': '302',
    'Jaiz Bank': '301',
    'FairMoney Microfinance Bank': '51318',
}

NIBSS_TO_BACHS_CODE = {
    '000013': '058',
    '000014': '044',
    '000015': '057',
    '000016': '011',
    '000004': '033',
    '100004': '999992',
    '100033': '999991',
    '090267': '50211',
    '090405': '50515',
    '000007': '070',
    '000003': '214',
    '000012': '221',
    '000001': '232',
    '000018': '032',
    '000017': '035',
    '000002': '082',
    '000008': '076',
    '000023': '101',
    '000026': '302',
    '000006': '301',
    '090328': '51318',
}


def resolve_bank_code(bank_name, explicit_code=''):
    """Return Bachs-compatible bank code from explicit code or bank_name."""
    code = (explicit_code or '').strip()
    if code in NIBSS_TO_BACHS_CODE:
        return NIBSS_TO_BACHS_CODE[code]
    if code:
        return code
    return BACHS_BANK_CODES.get((bank_name or '').strip(), '')


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
            if bank_account.bank_code != bank_code:
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
