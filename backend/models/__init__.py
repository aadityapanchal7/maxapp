"""Pydantic Models Package"""

from .user import (
    UserCreate,
    UserLogin,
    UserResponse,
    UserInDB,
    OnboardingData,
    UserProfile
)
from .scan import (
    ScanCreate,
    ScanResponse,
    ScanAnalysis,
    FaceMetrics,
    ScanInDB
)
from .payment import (
    PaymentCreate,
    PaymentResponse,
    SubscriptionStatus,
    PaymentInDB
)
from .course import (
    CourseCreate,
    CourseResponse,
    CourseChapter,
    CourseModule,
    CourseProgress
)
from .event import (
    EventCreate,
    EventResponse,
    EventInDB
)
from .forum import (
    ChannelCreate,
    ChannelResponse,
    ChannelInDB,
    MessageCreate,
    MessageResponse,
    MessageInDB,
    # Legacy aliases
    ForumCreate,
    ForumResponse,
    ForumInDB
)
from .schedule import (
    ModuleGuideline,
    ScheduleTask,
    DailySchedule,
    SchedulePreferences,
    GenerateScheduleRequest,
    ScheduleResponse,
    ScheduleInDB,
    CompleteTaskRequest,
    AdaptScheduleRequest,
)
