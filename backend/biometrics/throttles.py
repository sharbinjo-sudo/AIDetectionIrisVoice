import hashlib

from rest_framework.throttling import SimpleRateThrottle


class PinCustomerThrottle(SimpleRateThrottle):
    scope = "pin_customer"
    rate = "5/min"

    def get_cache_key(self, request, view):
        customer_id = str(request.data.get("customer_id", "")).strip().casefold()
        identity = hashlib.sha256(customer_id.encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": identity}


class PinAddressThrottle(SimpleRateThrottle):
    scope = "pin_address"
    rate = "30/min"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
