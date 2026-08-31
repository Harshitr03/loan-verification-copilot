from backend.app.models.user import User
from backend.app.models.dataset import Dataset
from backend.app.models.raw_record import RawRecord
from backend.app.models.loan import Loan
from backend.app.models.exception import Exception
from backend.app.models.ai_recommendation import AIRecommendation
from backend.app.models.verified_record import VerifiedRecord
from backend.app.models.audit_entry import AuditEntry
from backend.app.models.counter import Counter

ALL_DOCUMENTS = [User, Dataset, RawRecord, Loan, Exception, AIRecommendation,
                 VerifiedRecord, AuditEntry, Counter]
__all__ = [d.__name__ for d in ALL_DOCUMENTS] + ["ALL_DOCUMENTS"]
