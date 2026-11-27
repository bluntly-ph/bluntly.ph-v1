"""SQLAlchemy models — the 15-table Data Dictionary.

Importing this package registers every model on `Base.metadata`, which Alembic's
env.py uses as the migration target.
"""

from app.models.comment import (  # noqa: F401
    CommentFollow,
    CommentSave,
    ReviewComment,
    ReviewCommentVote,
)
from app.models.commission import Commission, MarketplaceRemittance  # noqa: F401
from app.models.contract import ReviewContract  # noqa: F401
from app.models.conversation import (  # noqa: F401
    Conversation,
    ConversationMessage,
    ConversationMessageHide,
    ConversationMessageRevision,
)
from app.models.email_change import EmailChangeRequest  # noqa: F401
from app.models.email_outbox import EmailOutbox  # noqa: F401
from app.models.honesty_fund import HonestyFundDistribution  # noqa: F401
from app.models.integrity import ImageFingerprint, VoteNetworkFingerprint  # noqa: F401
from app.models.maintenance import CronCredential, CronRun  # noqa: F401
from app.models.membership import MembershipTierConfig  # noqa: F401
from app.models.moderation import ModerationLog  # noqa: F401
from app.models.notification import Notification, NotificationReceipt  # noqa: F401
from app.models.otp import EmailOtp  # noqa: F401
from app.models.payout import Payout  # noqa: F401
from app.models.postback import AffiliatePostback  # noqa: F401
from app.models.product import (  # noqa: F401
    PriceHistory,
    Product,
    ProductAlias,
    ProductPlatform,
)
from app.models.qa import (  # noqa: F401
    Answer,
    AnswerReply,
    QAVote,
    Question,
    QuestionSubscription,
)
from app.models.request_board import RequestUpvote, ReviewRequest  # noqa: F401
from app.models.review import ReferralLink, Review, ReviewVersion  # noqa: F401
from app.models.review_draft import ReviewDraft  # noqa: F401
from app.models.seller import (  # noqa: F401
    Seller,
    SellerClaim,
    SellerReview,
    SellerReviewAppeal,
    SellerReviewReply,
    SellerReviewVote,
    StoreProduct,
)
from app.models.session import Session  # noqa: F401
from app.models.store_change import StoreChangeRequest  # noqa: F401
from app.models.support import SellerSupportRequest  # noqa: F401
from app.models.telemetry import ReviewReadingSession  # noqa: F401
from app.models.token import TokenTransaction  # noqa: F401
from app.models.traffic import (  # noqa: F401
    RequestGeoBucket,
    ReviewFirstVoteGeoBucket,
    ReviewViewBucket,
)
from app.models.triage import PlatformSetting, QueueTriage  # noqa: F401
from app.models.user import Badge, User, UserBadge  # noqa: F401
from app.models.vote import EarnEligibleVote, ReviewVote  # noqa: F401

__all__ = [
    "User", "Badge", "UserBadge", "MembershipTierConfig",
    "Product", "ProductPlatform", "PriceHistory",
    "Review", "ReviewVersion", "ReferralLink", "Question", "Answer",
    "Session", "Commission", "HonestyFundDistribution",
    "ModerationLog", "EarnEligibleVote", "ReviewVote", "TokenTransaction",
    "ReviewRequest", "RequestUpvote", "ReviewContract", "Payout", "EmailOtp",
    "AffiliatePostback", "ReviewComment", "ReviewCommentVote",
    "ReviewReadingSession", "ReviewFirstVoteGeoBucket",
    "Seller", "SellerClaim", "SellerReview", "SellerReviewAppeal", "SellerReviewReply",
    "SellerReviewVote", "Notification",
    "ProductAlias", "QuestionSubscription", "MarketplaceRemittance", "ReviewDraft",
    "PlatformSetting", "QueueTriage", "CommentFollow", "CommentSave", "NotificationReceipt",
    "AnswerReply", "QAVote",
]
