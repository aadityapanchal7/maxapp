"""
Storage Service - S3 or local fallback for image storage
"""

import os
from typing import Optional
import uuid
from datetime import datetime
from config import settings


class LocalStorageService:
    """Local file storage fallback for development/testing"""
    
    def __init__(self):
        self.storage_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
        os.makedirs(self.storage_dir, exist_ok=True)
    
    async def upload_image(
        self,
        image_data: bytes,
        user_id: str,
        image_type: str = "front"
    ) -> Optional[str]:
        """Save image to local filesystem"""
        try:
            # Create user directory
            user_dir = os.path.join(self.storage_dir, user_id)
            os.makedirs(user_dir, exist_ok=True)
            
            # Generate unique filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            filename = f"{timestamp}_{image_type}_{unique_id}.jpg"
            filepath = os.path.join(user_dir, filename)
            
            # Write file
            with open(filepath, "wb") as f:
                f.write(image_data)
            
            # Return a local URL (relative path)
            return f"/uploads/{user_id}/{filename}"
            
        except Exception as e:
            print(f"Local storage error: {e}")
            return None

    async def upload_video(
        self,
        video_data: bytes,
        user_id: str
    ) -> Optional[str]:
        """Save video to local filesystem"""
        try:
            # Create user directory
            user_dir = os.path.join(self.storage_dir, user_id)
            os.makedirs(user_dir, exist_ok=True)
            
            # Generate unique filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            filename = f"{timestamp}_scan_{unique_id}.mp4"
            filepath = os.path.join(user_dir, filename)
            
            # Write file
            with open(filepath, "wb") as f:
                f.write(video_data)
            
            # Return a local URL (relative path)
            return f"/uploads/{user_id}/{filename}"
            
        except Exception as e:
            print(f"Local video storage error: {e}")
            return None
    
    async def get_image(self, key: str) -> Optional[bytes]:
        """Read image from local filesystem"""
        try:
            # Convert URL path to file path
            filepath = os.path.join(self.storage_dir, key.replace("/uploads/", ""))
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    return f.read()
            return None
        except Exception as e:
            print(f"Local read error: {e}")
            return None
    
    async def delete_image(self, key: str) -> bool:
        """Delete image from local filesystem"""
        try:
            filepath = os.path.join(self.storage_dir, key.replace("/uploads/", ""))
            if os.path.exists(filepath):
                os.remove(filepath)
            return True
        except Exception as e:
            print(f"Local delete error: {e}")
            return False
    
    def get_presigned_url(self, key: str, expiration: int = 3600) -> Optional[str]:
        """For local storage, just return the path"""
        return key


class S3StorageService:
    """AWS S3 storage for production"""
    
    def __init__(self):
        import boto3
        from botocore.exceptions import ClientError
        self.ClientError = ClientError
        
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_s3_region
        )
        self.bucket = settings.aws_s3_bucket
    
    async def upload_image(
        self,
        image_data: bytes,
        user_id: str,
        image_type: str = "front"
    ) -> Optional[str]:
        """Upload an image to S3"""
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            key = f"scans/{user_id}/{timestamp}_{image_type}_{unique_id}.jpg"
            
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=image_data,
                ContentType="image/jpeg"
            )
            
            url = f"https://{self.bucket}.s3.{settings.aws_s3_region}.amazonaws.com/{key}"
            return url
            
        except self.ClientError as e:
            print(f"S3 upload error: {e}")
            return None

    async def upload_video(
        self,
        video_data: bytes,
        user_id: str
    ) -> Optional[str]:
        """Upload a video to S3"""
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            key = f"scans/{user_id}/{timestamp}_scan_{unique_id}.mp4"
            
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=video_data,
                ContentType="video/mp4"
            )
            
            url = f"https://{self.bucket}.s3.{settings.aws_s3_region}.amazonaws.com/{key}"
            return url
            
        except self.ClientError as e:
            print(f"S3 video upload error: {e}")
            return None
    
    async def get_image(self, key: str) -> Optional[bytes]:
        """Download an image from S3"""
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket,
                Key=key
            )
            return response["Body"].read()
        except self.ClientError as e:
            print(f"S3 download error: {e}")
            return None
    
    async def delete_image(self, key: str) -> bool:
        """Delete an image from S3"""
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket,
                Key=key
            )
            return True
        except self.ClientError as e:
            print(f"S3 delete error: {e}")
            return False
    
    def get_presigned_url(self, key: str, expiration: int = 3600) -> Optional[str]:
        """Generate a presigned URL for temporary access"""
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expiration
            )
            return url
        except self.ClientError as e:
            print(f"Presigned URL error: {e}")
            return None


def _extract_s3_key(url: str, bucket: str, region: str) -> Optional[str]:
    """Extract S3 object key from a standard S3 URL."""
    if not url:
        return None
    if url.startswith("s3://"):
        # s3://bucket/key
        parts = url.replace("s3://", "", 1).split("/", 1)
        if len(parts) == 2 and parts[0] == bucket:
            return parts[1]
        return None
    prefix = f"https://{bucket}.s3.{region}.amazonaws.com/"
    if url.startswith(prefix):
        return url[len(prefix):]
    return None


def create_storage_service():
    """
    Factory function to create appropriate storage service.
    Uses S3 if AWS credentials are configured, otherwise falls back to local storage.
    """
    aws_key = settings.aws_access_key_id
    aws_secret = settings.aws_secret_access_key
    
    # Check if AWS credentials are properly configured
    if aws_key and aws_secret and aws_key != "your-aws-access-key":
        print("[OK] Using AWS S3 storage")
        return S3StorageService()
    else:
        print("[WARN] AWS not configured - using local file storage")
        return LocalStorageService()


# Singleton instance - automatically picks the right storage
storage_service = create_storage_service()


def delete_by_url(url: str) -> bool:
    """
    Delete a stored image by URL or key.
    Supports local "/uploads/..." paths and S3 URLs/keys.
    """
    if not url:
        return False
    # Local storage paths
    if url.startswith("/uploads/"):
        return storage_service.delete_image(url)
    # S3 keys or URLs
    if isinstance(storage_service, S3StorageService):
        key = _extract_s3_key(url, settings.aws_s3_bucket, settings.aws_s3_region) or url
        return storage_service.delete_image(key)
    return False

