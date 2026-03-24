"""src/crm/ — 고객 관계 관리(CRM) 패키지."""

from .customer_profile import CustomerProfileManager
from .segmentation import CustomerSegmentation
from .lifecycle import CustomerLifecycle

__all__ = ["CustomerProfileManager", "CustomerSegmentation", "CustomerLifecycle"]
