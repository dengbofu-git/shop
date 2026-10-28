"""Owner-bound display references, never permissions or real order identifiers."""
from django.utils.crypto import salted_hmac


def support_order_reference(owner_id, order_id):
    digest = salted_hmac('buyer-support-order-link-v1', '{}:{}'.format(owner_id, order_id),
                         algorithm='sha256').hexdigest()
    # Letter-only encoding survives the generic phone/number history redactor.
    return 'os-' + digest.translate(str.maketrans('0123456789', 'ghijklmnop'))
