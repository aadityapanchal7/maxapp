import asyncio
from supabase import create_client, Client
from config import settings

supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

async def test_signup():
    """Test user signup"""
    try:
        # Signup creates user in auth.users
        response = supabase.auth.sign_up({
            "email": "test@example.com",
            "password": "TestPassword123!"
        })
        print(f"✅ Signup successful: {response.user.id}")
        return response.user.id
    except Exception as e:
        print(f"❌ Signup failed: {e}")
        return None

async def test_login():
    """Test user login"""
    try:
        response = supabase.auth.sign_in_with_password({
            "email": "test@example.com",
            "password": "TestPassword123!"
        })
        print(f"✅ Login successful, token: {response.session.access_token[:20]}...")
        return response.session.access_token
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return None

async def test_insert_profile():
    """Test inserting user profile (as service role)"""
    try:
        response = supabase.table("users").insert({
            "id": "550e8400-e29b-41d4-a716-446655440000",  # Use actual UUID
            "email": "profile@example.com",
            "is_paid": False,
            "phone_number": "+1234567890"
        }).execute()
        print(f"✅ Profile inserted: {response.data}")
    except Exception as e:
        print(f"❌ Insert failed: {e}")

if __name__ == "__main__":
    # Uncomment to test
    # asyncio.run(test_signup())
    # asyncio.run(test_login())
    # asyncio.run(test_insert_profile())
    print("Tests ready to run")