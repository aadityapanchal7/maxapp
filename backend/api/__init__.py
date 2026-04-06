"""API Package"""

from .auth import router as auth_router
from .users import router as users_router
from .scans import router as scans_router
from .payments import router as payments_router
from .courses import router as courses_router
from .events import router as events_router
from .forums import router as forums_router
from .forums_v2 import router as forums_v2_router
from .chat import router as chat_router
from .leaderboard import router as leaderboard_router
from .admin import router as admin_router
from .admin_forums_v2 import router as admin_forums_v2_router
from .notifications import router as notifications_router
from .schedules import router as schedules_router
from .maxes import router as maxes_router
from .sendblue_webhook import router as sendblue_webhook_router
